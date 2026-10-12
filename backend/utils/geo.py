import math

def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two lat/lon points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def gaussian_decay(distance_km, sigma=3.5):
    """Returns impact factor 0-1 based on distance from event venue."""
    return math.exp(-(distance_km ** 2) / (2 * sigma ** 2))

def time_profile(delta_hours):
    """
    Returns surge multiplier based on hours relative to event start.
    delta_hours: hour - event_start_hour
    Negative = before event, positive = after event start
    """
    profile = {
        -3: 0.05, -2: 0.12, -1: 0.31, 0: 0.65,
        1: 1.43, 2: 0.92, 3: 0.28, 4: 0.10
    }
    # Interpolate for values not in dict
    if delta_hours in profile:
        return profile[delta_hours]
    if delta_hours < -3 or delta_hours > 4:
        return 0.0
    # Linear interpolation
    lower = max(k for k in profile if k <= delta_hours)
    upper = min(k for k in profile if k >= delta_hours)
    if lower == upper:
        return profile[lower]
    t = (delta_hours - lower) / (upper - lower)
    return profile[lower] + t * (profile[upper] - profile[lower])
