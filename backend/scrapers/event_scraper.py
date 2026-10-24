"""
scrapers/event_scraper.py
-------------------------
Event scraper module for the HMR (Hyderabad Metro Rail) demand optimization
system.  Pulls live event data from BookMyShow, Paytm Insider, IPL schedule
feeds, and Hyderabad Police traffic advisories, then normalises everything
into a single schema understood by the rest of the backend.

All HTTP calls are wrapped in try/except and fall back to mock data so the
pipeline never crashes on network or parsing errors.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
DATA_DIR = BASE_DIR / "data"
LIVE_EVENTS_FILE = DATA_DIR / "live_events.json"

# Map of event types to the keys used by the multiplier table elsewhere
EVENT_TYPE_MAP: dict[str, str] = {
    "concert": "concert",
    "comedy": "concert",
    "music": "concert",
    "festival": "concert",
    "sports": "cricket_ipl",
    "cricket": "cricket_ipl",
    "ipl": "cricket_ipl",
    "cricket_international": "cricket_international",
    "football": "football",
    "soccer": "football",
    "rally": "political_rally",
    "political": "political_rally",
    "ganesh": "ganesh_procession",
    "procession": "ganesh_procession",
    "tech": "tech_summit",
    "summit": "tech_summit",
    "exhibition": "exhibition",
    "expo": "exhibition",
    "trade": "exhibition",
    "other": "other",
}

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

HTTP_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _normalise_event_type(raw: str) -> str:
    """Map a raw event-type string to an EVENT_MULTIPLIERS-compatible key."""
    lower = raw.lower().strip()
    for keyword, mapped in EVENT_TYPE_MAP.items():
        if keyword in lower:
            return mapped
    return "other"


def _make_event_id(name: str, start_time: str) -> str:
    """Deterministic short ID from name + start_time."""
    raw = f"{name}|{start_time}".encode()
    return hashlib.md5(raw).hexdigest()[:12]


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _build_event(
    *,
    name: str,
    event_type: str,
    venue_name: str,
    venue_id: str,
    venue_lat: float,
    venue_lon: float,
    start_time: str,
    end_time: str,
    expected_attendance: int,
    crowd_estimate: str,
    source: str,
    event_url: str | None = None,
    status: str = "scheduled",
) -> dict[str, Any]:
    """Build a fully-normalised event dict with lifecycle status."""
    normalised_type = _normalise_event_type(event_type)
    is_cancelled = status.lower() in ("cancelled", "canceled", "postponed")
    return {
        "id": _make_event_id(name, start_time),
        "name": name,
        "event_type": normalised_type,
        "venue_name": venue_name,
        "venue_id": venue_id,
        "venue_lat": venue_lat,
        "venue_lon": venue_lon,
        "start_time": start_time,
        "end_time": end_time,
        "expected_attendance": 0 if is_cancelled else expected_attendance,
        "crowd_estimate": "none" if is_cancelled else crowd_estimate,
        "status": status,
        "source": source,
        "event_url": event_url,
        "scraped_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# BookMyShow scraper
# ---------------------------------------------------------------------------

class BookMyShowScraper:
    """Scrapes Hyderabad events from BookMyShow's public listing page."""

    URL = "https://in.bookmyshow.com/explore/events-hyderabad"

    def fetch(self) -> list[dict[str, Any]]:
        """Return list of normalised event dicts, returning [] on error."""
        try:
            resp = requests.get(self.URL, headers=COMMON_HEADERS, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            return self._parse(resp.text)
        except Exception as exc:  # noqa: BLE001
            logger.info("BookMyShow scrape unavailable (%s); skipping.", exc)
            return []

    def _parse(self, html: str) -> list[dict[str, Any]]:
        """Parse BMS events from Schema.org JSON-LD structured data with fallback to cards."""
        soup = BeautifulSoup(html, "html.parser")
        events: list[dict[str, Any]] = []

        # 1. Primary: Extract official Schema.org JSON-LD ItemList
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "{}")
                if data.get("@type") == "ItemList":
                    for it in data.get("itemListElement", []):
                        item = it.get("item", {})
                        name = item.get("name")
                        if not name:
                            continue
                        loc = item.get("location", {})
                        addr = loc.get("address", {})
                        loc_text = f"{loc.get('name', '')} {addr.get('addressLocality', '')} {addr.get('streetAddress', '')}"
                        # Filter strictly for Hyderabad region
                        if not any(k in loc_text.lower() for k in ["hyderabad", "telangana", "500", "gachibowli", "kukatpally", "hitec"]):
                            continue

                        raw_start = item.get("startDate")
                        if not raw_start:
                            continue
                        start_time = raw_start if raw_start.endswith("Z") else raw_start + "Z"
                        end_time = item.get("endDate")
                        if not end_time:
                            try:
                                end_time = (datetime.fromisoformat(start_time.rstrip("Z")) + timedelta(hours=3)).isoformat() + "Z"
                            except Exception:
                                end_time = start_time

                        venue_name = loc.get("name") or "Hyderabad Venue"
                        raw_type = item.get("@type", "MusicEvent").lower().replace("event", "")
                        attendance = self._infer_attendance(raw_type)
                        lat, lon = 17.3850, 78.4867
                        # Resolve prominent venues
                        v_lower = loc_text.lower()
                        if "sandhya" in v_lower or "gachibowli" in v_lower:
                            lat, lon = 17.4399, 78.3490
                        elif "lakeshore" in v_lower or "kukatpally" in v_lower:
                            lat, lon = 17.4842, 78.4116
                        elif "aaromale" in v_lower or "film nagar" in v_lower:
                            lat, lon = 17.4150, 78.4120
                        elif "birla" in v_lower or "saifabad" in v_lower:
                            lat, lon = 17.4062, 78.4691
                        elif "hicc" in v_lower or "novotel" in v_lower:
                            lat, lon = 17.4448, 78.3766

                        # Detect event status (scheduled vs cancelled vs postponed)
                        raw_status = str(item.get("eventStatus", "")).lower()
                        if "cancel" in raw_status:
                            ev_status = "cancelled"
                        elif "postpone" in raw_status:
                            ev_status = "postponed"
                        elif "reschedule" in raw_status:
                            ev_status = "rescheduled"
                        else:
                            ev_status = "scheduled"

                        events.append(
                            _build_event(
                                name=name,
                                event_type=raw_type,
                                venue_name=venue_name,
                                venue_id=self._slugify(venue_name),
                                venue_lat=lat,
                                venue_lon=lon,
                                start_time=start_time,
                                end_time=end_time,
                                expected_attendance=attendance,
                                crowd_estimate=self._crowd_label(attendance),
                                source="bookmyshow_live",
                                event_url=item.get("url"),
                                status=ev_status,
                            )
                        )
            except Exception as exc:
                logger.debug("BMS JSON-LD extraction skipped: %s", exc)

        if events:
            return events

        # BMS renders card wrappers with several possible class names
        card_selectors = [
            {"data-testid": re.compile(r"event-card", re.I)},
        ]
        cards = []
        for selector in card_selectors:
            cards = soup.find_all("div", attrs=selector)
            if cards:
                break

        if not cards:
            # Broader fallback: any anchor with /events/ in href
            cards = soup.find_all("a", href=re.compile(r"/events/", re.I))

        for card in cards[:20]:  # cap at 20 to avoid noise
            try:
                name = self._extract_text(card, ["h2", "h3", "strong", "span"])
                if not name:
                    continue
                venue_tag = card.find(attrs={"data-testid": re.compile(r"venue", re.I)})
                venue = venue_tag.get_text(strip=True) if venue_tag else "Hyderabad"
                date_tag = card.find(attrs={"data-testid": re.compile(r"date|time", re.I)})
                raw_date = date_tag.get_text(strip=True) if date_tag else ""
                start_time = self._parse_date(raw_date)
                end_time = (
                    datetime.fromisoformat(start_time.rstrip("Z")) + timedelta(hours=3)
                ).isoformat() + "Z"
                genre_tag = card.find(attrs={"data-testid": re.compile(r"genre|category", re.I)})
                raw_type = genre_tag.get_text(strip=True) if genre_tag else "other"
                attendance = self._infer_attendance(raw_type)

                events.append(
                    _build_event(
                        name=name,
                        event_type=raw_type,
                        venue_name=venue,
                        venue_id=self._slugify(venue),
                        venue_lat=17.3850,
                        venue_lon=78.4867,
                        start_time=start_time,
                        end_time=end_time,
                        expected_attendance=attendance,
                        crowd_estimate=self._crowd_label(attendance),
                        source="bookmyshow",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("BMS card parse error: %s", exc)
                continue

        return events

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(tag: Any, element_types: list[str]) -> str:
        for et in element_types:
            found = tag.find(et)
            if found:
                return found.get_text(strip=True)
        return tag.get_text(strip=True)[:80]

    @staticmethod
    def _parse_date(raw: str) -> str:
        """Best-effort date parsing; defaults to tomorrow noon UTC."""
        try:
            dt = datetime.strptime(raw, "%d %b %Y")
            return dt.replace(hour=18).isoformat() + "Z"
        except ValueError:
            pass
        tomorrow = datetime.utcnow() + timedelta(days=1)
        return tomorrow.replace(hour=12, minute=0, second=0, microsecond=0).isoformat() + "Z"

    @staticmethod
    def _infer_attendance(event_type: str) -> int:
        """Rough crowd estimate by event category."""
        lower = event_type.lower()
        if any(k in lower for k in ("concert", "music", "festival")):
            return 15000
        if any(k in lower for k in ("comedy", "stand-up")):
            return 3000
        if any(k in lower for k in ("sport", "cricket", "football")):
            return 40000
        return 5000

    @staticmethod
    def _crowd_label(n: int) -> str:
        if n >= 40000:
            return "very_high"
        if n >= 15000:
            return "high"
        if n >= 5000:
            return "medium"
        return "low"

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"\W+", "_", text.lower()).strip("_")

    def _mock_events(self) -> list[dict[str, Any]]:
        """No mock fallbacks. Only genuinely verified scraped events are allowed."""
        return []


# ---------------------------------------------------------------------------
# Paytm Insider scraper
# ---------------------------------------------------------------------------

class PaytmInsiderScraper:
    """Queries the Paytm Insider API for Hyderabad events."""

    API_URL = "https://api-preprod.insider.in/v1/events"

    def fetch(self) -> list[dict[str, Any]]:
        """Return normalised events; falls back to mock on any error."""
        try:
            params = {"city": "hyderabad", "size": 30}
            resp = requests.get(
                self.API_URL,
                params=params,
                headers=COMMON_HEADERS,
                timeout=HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            return self._parse(resp.json())
        except Exception as exc:  # noqa: BLE001
            logger.info("PaytmInsider fetch unavailable (%s); skipping.", exc)
            return []

    def _parse(self, data: Any) -> list[dict[str, Any]]:
        """Parse JSON response from Insider API."""
        events: list[dict[str, Any]] = []

        # Insider wraps results under different top-level keys depending on API version
        items = []
        if isinstance(data, dict):
            items = data.get("events", data.get("data", data.get("results", [])))
        elif isinstance(data, list):
            items = data

        for item in items[:30]:
            try:
                name = item.get("name") or item.get("title") or ""
                if not name:
                    continue
                venue_info = item.get("venue") or {}
                venue_name = venue_info.get("name") or item.get("venue_name") or "Hyderabad"
                venue_lat = float(venue_info.get("lat") or 17.3850)
                venue_lon = float(venue_info.get("lng") or 78.4867)

                raw_start = item.get("start_time") or item.get("start_at") or ""
                start_time = self._normalise_datetime(raw_start)
                raw_end = item.get("end_time") or item.get("end_at") or ""
                end_time = (
                    self._normalise_datetime(raw_end)
                    if raw_end
                    else (
                        datetime.fromisoformat(start_time.rstrip("Z")) + timedelta(hours=3)
                    ).isoformat() + "Z"
                )

                raw_type = item.get("type") or item.get("category") or "other"
                attendance = int(item.get("expected_count") or 5000)

                events.append(
                    _build_event(
                        name=name,
                        event_type=raw_type,
                        venue_name=venue_name,
                        venue_id=re.sub(r"\W+", "_", venue_name.lower()),
                        venue_lat=venue_lat,
                        venue_lon=venue_lon,
                        start_time=start_time,
                        end_time=end_time,
                        expected_attendance=attendance,
                        crowd_estimate=BookMyShowScraper._crowd_label(attendance),
                        source="paytm_insider",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Insider item parse error: %s", exc)

        return events

    @staticmethod
    def _normalise_datetime(raw: str) -> str:
        """Parse an ISO / epoch / human-readable timestamp to ISO-Z string."""
        if not raw:
            return (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
        # epoch milliseconds
        if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.isdigit()):
            ts = int(raw)
            if ts > 1e10:
                ts //= 1000
            return datetime.utcfromtimestamp(ts).isoformat() + "Z"
        # already ISO
        raw_clean = raw.replace("Z", "").split("+")[0]
        try:
            return datetime.fromisoformat(raw_clean).isoformat() + "Z"
        except ValueError:
            return (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"

    def _mock_events(self) -> list[dict[str, Any]]:
        """No mock fallbacks. Only genuine scraped events are allowed."""
        return []


# ---------------------------------------------------------------------------
# Cricket Match Schedule Fetcher (International, IPL, and Ranji Domestic)
# ---------------------------------------------------------------------------

class CricketScheduleFetcher:
    """
    Fetches and manages cricket match fixtures across Hyderabad's key venues:
    1. Rajiv Gandhi International Cricket Stadium, Uppal (International & IPL, 55,000 capacity)
    2. Gymkhana Ground, Secunderabad (Ranji Trophy 2026-27 & Domestic, 10,000 capacity, adjacent to Parade Ground Metro)
    """

    SCHEDULE_URL = "https://www.iplt20.com/matches/schedule"

    # Venues
    UPPAL_ID = "uppal_stadium"
    UPPAL_NAME = "Rajiv Gandhi International Cricket Stadium, Uppal"
    UPPAL_LAT = 17.4063
    UPPAL_LON = 78.5480
    UPPAL_CAPACITY = 55000

    GYMKHANA_ID = "gymkhana_ground"
    GYMKHANA_NAME = "Gymkhana Ground, Secunderabad"
    GYMKHANA_LAT = 17.4428
    GYMKHANA_LON = 78.4988
    GYMKHANA_CAPACITY = 10000

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch cricket fixtures from live schedule if any are officially scheduled in Hyderabad."""
        events = []
        try:
            resp = requests.get(
                self.SCHEDULE_URL, headers=COMMON_HEADERS, timeout=HTTP_TIMEOUT
            )
            if resp.status_code == 200:
                events.extend(self._parse_ipl(resp.text))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cricket live scrape unavailable (%s)", exc)

        return events

    def _parse_ipl(self, html: str) -> list[dict[str, Any]]:
        """Extract Hyderabad fixtures from live IPL table if available."""
        soup = BeautifulSoup(html, "html.parser")
        events: list[dict[str, Any]] = []
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                row_text = " ".join(cells).lower()
                if "hyderabad" not in row_text and "uppal" not in row_text:
                    continue
                if len(cells) < 3:
                    continue
                try:
                    name = " vs ".join(c for c in cells if re.search(r"[A-Z]{2,}", c))[:80]
                    date_str = next((c for c in cells if re.search(r"\d{4}", c)), "")
                    start_time = self._parse_ipl_date(date_str)
                    if not start_time:
                        continue
                    end_time = (
                        datetime.fromisoformat(start_time.rstrip("Z")) + timedelta(hours=4)
                    ).isoformat() + "Z"
                    events.append(
                        _build_event(
                            name=name or "IPL Match - Hyderabad",
                            event_type="cricket_ipl",
                            venue_name=self.UPPAL_NAME,
                            venue_id=self.UPPAL_ID,
                            venue_lat=self.UPPAL_LAT,
                            venue_lon=self.UPPAL_LON,
                            start_time=start_time,
                            end_time=end_time,
                            expected_attendance=self.UPPAL_CAPACITY,
                            crowd_estimate="very_high",
                            source="iplt20_live",
                        )
                    )
                except Exception as exc:
                    logger.debug("IPL row parse error: %s", exc)
        return events

    @staticmethod
    def _parse_ipl_date(raw: str) -> Optional[str]:
        for fmt in ("%d %b %Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                return dt.replace(hour=14, minute=0).isoformat() + "Z"
            except ValueError:
                continue
        return None

# Backwards compatibility alias
IPLScheduleFetcher = CricketScheduleFetcher


# ---------------------------------------------------------------------------
# Traffic Advisory fetcher
# ---------------------------------------------------------------------------

class TrafficAdvisoryFetcher:
    """
    Fetches Hyderabad Police traffic advisories and public social-media
    signals about traffic disruptions.
    """

    ADVISORY_URL = "https://hydcitypolice.gov.in/TrafficAdvisory/"
    NITTER_URL = "https://nitter.net/search"

    def fetch(self) -> list[dict[str, Any]]:
        """Combine police advisories and social signals; returns real events only."""
        events: list[dict[str, Any]] = []
        events.extend(self._fetch_police_advisory())
        events.extend(self._fetch_nitter())
        return events

    # ------------------------------------------------------------------
    # Police advisory page
    # ------------------------------------------------------------------

    def _fetch_police_advisory(self) -> list[dict[str, Any]]:
        try:
            resp = requests.get(
                self.ADVISORY_URL, headers=COMMON_HEADERS, timeout=HTTP_TIMEOUT
            )
            resp.raise_for_status()
            return self._parse_advisory_html(resp.text)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Police advisory fetch failed: %s", exc)
            return []

    def _parse_advisory_html(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        events: list[dict[str, Any]] = []
        for item in soup.find_all(["li", "p", "div"], limit=20):
            text = item.get_text(separator=" ", strip=True)
            if len(text) < 20 or not re.search(r"\d{1,2}[/-]\d{1,2}", text):
                continue
            event_type = self._classify_advisory(text)
            start_time = self._extract_date_from_text(text)
            events.append(
                _build_event(
                    name=text[:120],
                    event_type=event_type,
                    venue_name="Hyderabad City",
                    venue_id="hyderabad_city",
                    venue_lat=17.3850,
                    venue_lon=78.4867,
                    start_time=start_time,
                    end_time=(
                        datetime.fromisoformat(start_time.rstrip("Z")) + timedelta(hours=6)
                    ).isoformat() + "Z",
                    expected_attendance=50000,
                    crowd_estimate="very_high",
                    source="hyderabad_police_advisory",
                )
            )
        return events

    # ------------------------------------------------------------------
    # Nitter (Twitter public search proxy)
    # ------------------------------------------------------------------

    def _fetch_nitter(self) -> list[dict[str, Any]]:
        try:
            params = {"q": "Hyderabad traffic advisory", "f": "tweets"}
            resp = requests.get(
                self.NITTER_URL, params=params, headers=COMMON_HEADERS, timeout=HTTP_TIMEOUT
            )
            resp.raise_for_status()
            return self._parse_nitter_html(resp.text)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Nitter fetch failed: %s", exc)
            return []

    def _parse_nitter_html(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        events: list[dict[str, Any]] = []
        for tweet in soup.find_all("div", class_=re.compile(r"tweet-content|timeline-item", re.I)):
            text = tweet.get_text(separator=" ", strip=True)
            if "hyderabad" not in text.lower():
                continue
            event_type = self._classify_advisory(text)
            start_time = self._extract_date_from_text(text)
            events.append(
                _build_event(
                    name=text[:120],
                    event_type=event_type,
                    venue_name="Hyderabad City",
                    venue_id="hyderabad_city",
                    venue_lat=17.3850,
                    venue_lon=78.4867,
                    start_time=start_time,
                    end_time=(
                        datetime.fromisoformat(start_time.rstrip("Z")) + timedelta(hours=4)
                    ).isoformat() + "Z",
                    expected_attendance=30000,
                    crowd_estimate="high",
                    source="nitter_social",
                )
            )
            if len(events) >= 5:
                break
        return events

    # ------------------------------------------------------------------
    # Classification helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_advisory(text: str) -> str:
        lower = text.lower()
        if any(k in lower for k in ("ganesh", "visarjan", "procession", "nimajjanam")):
            return "ganesh_procession"
        if any(k in lower for k in ("rally", "political", "election", "protest", "bjp", "congress")):
            return "political_rally"
        if any(k in lower for k in ("concert", "music", "festival")):
            return "concert"
        if any(k in lower for k in ("cricket", "ipl", "match")):
            return "cricket_ipl"
        return "other"

    @staticmethod
    def _extract_date_from_text(text: str) -> str:
        """Try to find a date like 05/09 or 5-Sep in text; default tomorrow."""
        match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", text)
        if match:
            day, month = int(match.group(1)), int(match.group(2))
            year_raw = match.group(3)
            year = int(year_raw) if year_raw else datetime.utcnow().year
            if year < 100:
                year += 2000
            try:
                dt = datetime(year, month, day, 8, 0)
                return dt.isoformat() + "Z"
            except ValueError:
                pass
        return (datetime.utcnow() + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        ).isoformat() + "Z"

    def _mock_events(self) -> list[dict[str, Any]]:
        """Mock traffic advisory events for common Hyderabad disruptions."""
        base = datetime.utcnow()

        # Ganesh Visarjan — typically in August/September
        ganesh_dt = base.replace(month=9, day=15, hour=6, minute=0, second=0, microsecond=0)
        ganesh_end = ganesh_dt.replace(hour=23)

        # Major political rally
        rally_dt = (base + timedelta(days=20)).replace(hour=14, minute=0, second=0, microsecond=0)
        rally_end = rally_dt + timedelta(hours=4)

        return [
            _build_event(
                name="Ganesh Visarjan Procession 2026 - Tank Bund & PVNR Expressway",
                event_type="ganesh_procession",
                venue_name="Tank Bund / PVNR Expressway",
                venue_id="tank_bund",
                venue_lat=17.4239,
                venue_lon=78.4738,
                start_time=ganesh_dt.isoformat() + "Z",
                end_time=ganesh_end.isoformat() + "Z",
                expected_attendance=500000,
                crowd_estimate="very_high",
                source="traffic_advisory_mock",
            ),
            _build_event(
                name="BRS State-Wide Political Rally - LB Stadium",
                event_type="political_rally",
                venue_name="Lal Bahadur Shastri Stadium",
                venue_id="lb_stadium",
                venue_lat=17.3997,
                venue_lon=78.4724,
                start_time=rally_dt.isoformat() + "Z",
                end_time=rally_end.isoformat() + "Z",
                expected_attendance=80000,
                crowd_estimate="very_high",
                source="traffic_advisory_mock",
            ),
        ]


# ---------------------------------------------------------------------------
# AllEvents.in Scraper (Live Multi-Source Real-Time Events)
# ---------------------------------------------------------------------------

class AllEventsScraper:
    """Scrapes real-time live events across Hyderabad from AllEvents.in across categories and dates."""
    URLS = [
        ("https://allevents.in/hyderabad/all", 2),
        ("https://allevents.in/hyderabad/tomorrow", 1),
        ("https://allevents.in/hyderabad/this-week", 3),
        ("https://allevents.in/hyderabad/business", 2),
        ("https://allevents.in/hyderabad/sports", 2),
        ("https://allevents.in/hyderabad/festivals", 2),
    ]

    def fetch(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        seen_names = set()
        for url, fallback_days in self.URLS:
            try:
                resp = requests.get(url, headers=COMMON_HEADERS, timeout=HTTP_TIMEOUT)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                # 1. Primary: Extract rich Schema.org JSON-LD events with exact geo and eventStatus
                for s in soup.find_all("script", type="application/ld+json"):
                    try:
                        ld_data = json.loads(s.string or "[]")
                        if isinstance(ld_data, list):
                            for item in ld_data:
                                if item.get("@type") == "Event":
                                    e_name = item.get("name")
                                    if not e_name or e_name.lower() in seen_names:
                                        continue
                                    seen_names.add(e_name.lower())
                                    raw_start = item.get("startDate")
                                    if not raw_start:
                                        continue
                                    start_time = raw_start if "T" in raw_start else f"{raw_start}T18:00:00"
                                    if not start_time.endswith("Z"):
                                        start_time += "Z"
                                    end_time = item.get("endDate") or (datetime.fromisoformat(start_time.rstrip("Z")) + timedelta(hours=3)).isoformat() + "Z"
                                    
                                    loc_info = item.get("location", {})
                                    venue_name = loc_info.get("name") or "Hyderabad Venue"
                                    geo = loc_info.get("geo", {})
                                    lat = float(geo.get("latitude") or 17.3850)
                                    lon = float(geo.get("longitude") or 78.4867)

                                    raw_status = str(item.get("eventStatus", "")).lower()
                                    if "cancel" in raw_status:
                                        ev_status = "cancelled"
                                    elif "postpone" in raw_status:
                                        ev_status = "postponed"
                                    elif "reschedule" in raw_status:
                                        ev_status = "rescheduled"
                                    else:
                                        ev_status = "scheduled"

                                    ev_type = _normalise_event_type(e_name)
                                    att = BookMyShowScraper._infer_attendance(ev_type)

                                    events.append(
                                        _build_event(
                                            name=e_name,
                                            event_type=ev_type,
                                            venue_name=venue_name,
                                            venue_id=re.sub(r"\W+", "_", venue_name.lower()),
                                            venue_lat=lat,
                                            venue_lon=lon,
                                            start_time=start_time,
                                            end_time=end_time,
                                            expected_attendance=att,
                                            crowd_estimate=BookMyShowScraper._crowd_label(att),
                                            source="allevents_live_ld",
                                            event_url=item.get("url"),
                                            status=ev_status,
                                        )
                                    )
                    except Exception as ld_err:
                        logger.debug("AllEvents JSON-LD parse skip: %s", ld_err)

                # 2. Secondary fallback: HTML cards
                cards = soup.select("li.event-card, [data-event-id], li.res-card")
                for card in cards[:40]:
                    name = card.get("data-name") or ""
                    if not name:
                        name_el = card.find(["h3", "h2", "h4"])
                        name = name_el.get_text(strip=True) if name_el else ""
                    if not name or len(name) < 4 or name.lower() in seen_names:
                        continue

                    date_el = card.select_one(".date, .time")
                    date_raw = date_el.get_text(strip=True) if date_el else ""
                    start_time = self._parse_date_from_text(date_raw or card.get_text(" | ", strip=True))
                    if not start_time:
                        continue

                    seen_names.add(name.lower())
                    link = card.get("data-link") or "https://allevents.in/hyderabad"

                    loc_el = card.select_one(".location, .subtitle")
                    loc_text = loc_el.get_text(strip=True) if loc_el else "Hyderabad"
                    text_content = f"{name} {loc_text}"

                    venue_name = loc_text if len(loc_text) > 3 else "Hyderabad"
                    venue_lat, venue_lon = 17.3850, 78.4867
                    v_lower = text_content.lower()

                    if "uppal" in v_lower:
                        venue_name = "Rajiv Gandhi International Cricket Stadium, Uppal"
                        venue_lat, venue_lon = 17.4063, 78.5480
                    elif "gymkhana" in v_lower:
                        venue_name = "Gymkhana Cricket Grounds, Secunderabad"
                        venue_lat, venue_lon = 17.4445, 78.4976
                    elif "gachibowli" in v_lower or "the league" in v_lower:
                        venue_name = "Gachibowli Indoor Stadium"
                        venue_lat, venue_lon = 17.4399, 78.3490
                    elif "hitex" in v_lower:
                        venue_name = "Hitex Exhibition Centre, HITEC City"
                        venue_lat, venue_lon = 17.4517, 78.3727
                    elif "hicc" in v_lower or "novotel" in v_lower or "district 150" in v_lower or "le meridien" in v_lower:
                        venue_name = "Hyderabad International Convention Centre (HICC)"
                        venue_lat, venue_lon = 17.4448, 78.3766
                    elif "shilpakala" in v_lower:
                        venue_name = "Shilpakala Vedika, HITEC City"
                        venue_lat, venue_lon = 17.4503, 78.3756
                    elif "shilparamam" in v_lower:
                        venue_name = "Shilparamam Arts Village, Madhapur"
                        venue_lat, venue_lon = 17.4521, 78.3712
                    elif "tank bund" in v_lower or "hussain sagar" in v_lower:
                        venue_name = "Tank Bund Waterfront"
                        venue_lat, venue_lon = 17.4239, 78.4738
                    elif "lb stadium" in v_lower:
                        venue_name = "Lal Bahadur Shastri Stadium, Basheerbagh"
                        venue_lat, venue_lon = 17.3997, 78.4724
                    elif "visvesvaraya" in v_lower or "khairatabad" in v_lower:
                        venue_name = "Visvesvaraya Bhavan, Khairatabad"
                        venue_lat, venue_lon = 17.4125, 78.4610

                    end_time = (datetime.fromisoformat(start_time.rstrip("Z")) + timedelta(hours=3)).isoformat() + "Z"
                    raw_type = _normalise_event_type(name)
                    attendance = BookMyShowScraper._infer_attendance(raw_type)

                    events.append(
                        _build_event(
                            name=name,
                            event_type=raw_type,
                            venue_name=venue_name,
                            venue_id=re.sub(r"\W+", "_", venue_name.lower()),
                            venue_lat=venue_lat,
                            venue_lon=venue_lon,
                            start_time=start_time,
                            end_time=end_time,
                            expected_attendance=attendance,
                            crowd_estimate=BookMyShowScraper._crowd_label(attendance),
                            source="allevents_live",
                            event_url=link
                        )
                    )
            except Exception as exc:
                logger.warning("AllEvents scraper failed for %s: %s", url, exc)
        return events

    @staticmethod
    def _parse_date_from_text(text: str) -> Optional[str]:
        raw = text.split("+")[0].strip()
        now = datetime.utcnow()

        # Check explicit day + month + time: e.g. "17 Oct, 2026 - 07:00 PM" or "24 Oct · 06:30 PM"
        m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})(?:,?\s*(\d{4}))?.*?(\d{1,2}):(\d{2})\s*(AM|PM)", raw, re.I)
        if m:
            day, mon, yr, hr, mn, ampm = m.groups()
            yr = yr or str(now.year)
            hr_int = int(hr)
            if ampm.upper() == "PM" and hr_int != 12:
                hr_int += 12
            elif ampm.upper() == "AM" and hr_int == 12:
                hr_int = 0
            months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
            mon_lower = mon.lower()
            if mon_lower in months:
                mon_num = months.index(mon_lower) + 1
                try:
                    dt = datetime(int(yr), mon_num, int(day), hr_int, int(mn))
                    return dt.isoformat() + "Z"
                except Exception:
                    pass

        # Check relative "today" or "tomorrow"
        lower = raw.lower()
        if "tomorrow" in lower:
            dt = (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
            return dt.isoformat() + "Z"
        if "today" in lower:
            dt = now.replace(hour=18, minute=0, second=0, microsecond=0)
            return dt.isoformat() + "Z"

        return None


# ---------------------------------------------------------------------------
# Telangana Tourism & Cultural Official Events Scraper
# ---------------------------------------------------------------------------

class TelanganaTourismScraper:
    """Telangana Tourism & Cultural Heritage scraper; returns only verified live listings."""

    def fetch(self) -> list[dict[str, Any]]:
        # Do not hallucinate or hardcode unverified schedules.
        return []


# ---------------------------------------------------------------------------
# Unified Event Aggregator
# ---------------------------------------------------------------------------

class EventAggregator:
    """
    Aggregates events from all scrapers, deduplicates, and normalises them
    into the common HMR event schema. Only genuine verified events are used.
    """

    def __init__(self) -> None:
        self.bms = BookMyShowScraper()
        self.allevents = AllEventsScraper()
        self.tourism = TelanganaTourismScraper()
        self.insider = PaytmInsiderScraper()
        self.ipl = IPLScheduleFetcher()

    def fetch_all_events(self, city: str = "Hyderabad") -> list[dict[str, Any]]:
        """
        Fetch events from live verified sources, deduplicate by (name, start_time), and
        return a sorted list of normalised event dicts.
        """
        logger.info("Fetching real-time verified events for %s …", city)

        raw: list[dict[str, Any]] = []
        for scraper_name, scraper_fn in [
            ("allevents", self.allevents.fetch),
            ("bookmyshow", self.bms.fetch),
            ("paytm_insider", self.insider.fetch),
            ("cricket_live", self.ipl.fetch),
        ]:
            try:
                results = scraper_fn()
                logger.info("  [%s] returned %d events", scraper_name, len(results))
                raw.extend(results)
            except Exception as exc:  # noqa: BLE001
                logger.error("  [%s] uncaught error: %s", scraper_name, exc)

        deduped = self._deduplicate(raw)
        deduped.sort(key=lambda e: e.get("start_time", ""))
        logger.info("Total unique verified events after deduplication: %d", len(deduped))
        return deduped

    @staticmethod
    def _deduplicate(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Deduplicate by a (name-slug, date) composite key.  When duplicates
        exist, prefer real-source records over mock ones.
        """
        seen: dict[str, dict[str, Any]] = {}
        for event in events:
            name_slug = re.sub(r"\W+", "", event.get("name", "").lower())
            date_part = (event.get("start_time") or "")[:10]
            key = f"{name_slug}|{date_part}"

            if key not in seen:
                seen[key] = event
            else:
                # Prefer the non-mock source
                existing_source = seen[key].get("source", "")
                if "mock" in existing_source and "mock" not in event.get("source", ""):
                    seen[key] = event
        return list(seen.values())


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def save_live_events(events: list[dict[str, Any]]) -> None:
    """
    Persist scraped events to ``backend/data/live_events.json``.

    Parameters
    ----------
    events : list[dict]
        Normalised event dicts produced by ``EventAggregator.fetch_all_events``.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _now_iso(),
        "count": len(events),
        "events": events,
    }
    LIVE_EVENTS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d events to %s", len(events), LIVE_EVENTS_FILE)


def load_live_events() -> list[dict[str, Any]]:
    """
    Load events from ``backend/data/live_events.json``.

    Returns
    -------
    list[dict]
        Previously persisted events, or an empty list if the file does not exist
        or cannot be parsed.
    """
    if not LIVE_EVENTS_FILE.exists():
        logger.debug("live_events.json not found; returning empty list.")
        return []
    try:
        data = json.loads(LIVE_EVENTS_FILE.read_text(encoding="utf-8"))
        events = data.get("events", []) if isinstance(data, dict) else data
        logger.info("Loaded %d events from %s", len(events), LIVE_EVENTS_FILE)
        return events
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load live_events.json: %s", exc)
        return []


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    aggregator = EventAggregator()
    events = aggregator.fetch_all_events(city="Hyderabad")

    print(f"\n{'='*60}")
    print(f"  HMR Event Scraper — {len(events)} events found")
    print(f"{'='*60}\n")
    for ev in events:
        print(
            f"  [{ev['event_type']:22s}] {ev['name'][:50]:50s} "
            f"| {ev['start_time'][:10]}  crowd={ev['crowd_estimate']}"
        )

    save_live_events(events)
    print(f"\nSaved to {LIVE_EVENTS_FILE}\n")
