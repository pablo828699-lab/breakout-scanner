/**
 * Date Utility module for Breakout Scanner frontend.
 * Provides robust date parsing and formatting handling:
 * - Unix timestamps in seconds or milliseconds (number or numeric string)
 * - ISO 8601 strings (e.g., "2026-07-21T18:00:00Z", "2026-07-21T18:00:00.123456Z")
 * - Microsecond strings (e.g., "2026-07-21 18:00:00.123456", "2026-07-21T18:00:00.123456Z")
 * - UTC format strings (e.g., "2026-07-21 18:00:00 UTC", "2026-07-21 18:00:00")
 * - Graceful fallback preventing any output of "NaN" or "Invalid Date".
 */

/**
 * Parses any valid input date into a JS Date object.
 * Returns null if parsing fails or input is invalid.
 *
 * @param {string | number | Date | null | undefined} input
 * @returns {Date | null}
 */
export function parseDate(input) {
  if (input == null || input === '') return null;

  if (input instanceof Date) {
    return isNaN(input.getTime()) ? null : input;
  }

  // Handle numbers or pure numeric strings (Unix timestamps)
  if (typeof input === 'number' || (typeof input === 'string' && /^\d+(\.\d+)?$/.test(input.trim()))) {
    const num = Number(input);
    if (isNaN(num)) return null;
    // If <= 1e11, assume seconds; otherwise assume milliseconds
    const ms = num <= 1e11 ? num * 1000 : num;
    const d = new Date(ms);
    return isNaN(d.getTime()) ? null : d;
  }

  if (typeof input === 'string') {
    let str = input.trim();

    // Clean legacy UTC suffix
    str = str.replace(/\s+UTC$/i, 'Z');

    // Replace space between date and time with 'T' (e.g. "2026-07-21 18:00:00" -> "2026-07-21T18:00:00")
    if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/.test(str)) {
      str = str.replace(/\s+/, 'T');
    }

    // Truncate microsecond sub-second digits down to milliseconds (3 digits) for JS Date compatibility
    // e.g. "2026-07-21T18:00:00.123456Z" -> "2026-07-21T18:00:00.123Z"
    str = str.replace(/(\.\d{3})\d+/, '$1');

    // If string has no timezone offset (no Z or +/-HH:MM), append 'Z' so it is parsed as UTC
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(str)) {
      str += 'Z';
    }

    const timestamp = Date.parse(str);
    if (!isNaN(timestamp)) {
      return new Date(timestamp);
    }

    const directDate = new Date(str);
    if (!isNaN(directDate.getTime())) {
      return directDate;
    }
  }

  return null;
}

/**
 * Parses input date and returns Unix timestamp in milliseconds.
 *
 * @param {string | number | Date | null | undefined} input
 * @param {number} fallbackMs
 * @returns {number}
 */
export function safeDateParse(input, fallbackMs = Date.now()) {
  const d = parseDate(input);
  return d ? d.getTime() : fallbackMs;
}

/**
 * Formats input timestamp to a readable date/time string.
 * Guaranteed never to return "NaN" or "Invalid Date".
 *
 * @param {string | number | Date | null | undefined} input
 * @param {string} fallback
 * @param {object} options
 * @returns {string}
 */
export function formatTimestamp(input, fallback = 'N/A', options = {}) {
  const d = parseDate(input);
  if (!d) return fallback;

  try {
    const locale = options.locale || 'es-AR';
    const fmtOpts = options.formatOptions || {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    };
    const result = d.toLocaleString(locale, fmtOpts);
    if (result.includes('NaN') || result.includes('Invalid Date')) {
      return fallback;
    }
    return result;
  } catch (e) {
    return fallback;
  }
}

/**
 * Formats input timestamp to ISO 8601 string (e.g. "2026-07-21T18:00:00.000Z").
 *
 * @param {string | number | Date | null | undefined} input
 * @param {string} fallback
 * @returns {string}
 */
export function formatISO(input, fallback = 'N/A') {
  const d = parseDate(input);
  if (!d) return fallback;
  try {
    return d.toISOString();
  } catch (e) {
    return fallback;
  }
}

/**
 * Formats input timestamp into relative time string (e.g., "5 mins ago", "Just now").
 * Guaranteed never to return "NaN" or "Invalid Date".
 *
 * @param {string | number | Date | null | undefined} input
 * @param {string} fallback
 * @returns {string}
 */
export function formatRelativeTime(input, fallback = 'Just now') {
  const d = parseDate(input);
  if (!d) return fallback;

  const now = Date.now();
  const diffMs = now - d.getTime();
  const diffSecs = Math.floor(diffMs / 1000);

  if (isNaN(diffSecs) || diffSecs < 0) return 'Just now';
  if (diffSecs < 10) return 'Just now';
  if (diffSecs < 60) return `${diffSecs} secs ago`;

  const diffMins = Math.floor(diffSecs / 60);
  if (diffMins < 60) return `${diffMins} ${diffMins === 1 ? 'min' : 'mins'} ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} ${diffHours === 1 ? 'hour' : 'hours'} ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays} ${diffDays === 1 ? 'day' : 'days'} ago`;

  return formatTimestamp(d, fallback);
}
