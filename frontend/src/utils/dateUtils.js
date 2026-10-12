/**
 * Utility functions for local date formatting and navigation.
 * Guarantees local timezone accuracy and avoids UTC drift (e.g. toISOString() shifting Indian Standard Time backwards).
 */

export function getLocalDateString(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function getDateOffset(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return getLocalDateString(d);
}

export function shiftDate(dateStr, days) {
  if (!dateStr) return getDateOffset(days);
  const [y, m, d] = dateStr.split('-').map(Number);
  const dateObj = new Date(y, m - 1, d + days);
  return getLocalDateString(dateObj);
}

export function formatDate(dateStr) {
  if (!dateStr) return '';
  const [y, m, d] = dateStr.split('-').map(Number);
  const dateObj = new Date(y, m - 1, d);
  return dateObj.toLocaleDateString('en-IN', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}
