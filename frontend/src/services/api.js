/**
 * Centralized API Service for Breakout Scanner frontend.
 * Provides unified HTTP fetching for backend endpoints with error handling,
 * timeout defaults, and clean fallbacks.
 */

export const BACKEND_URL = 'https://breakout-scanner-xg9f.onrender.com';
export const DEFAULT_TIMEOUT_MS = 35000;

/**
 * Fetch wrapper with AbortController timeout.
 *
 * @param {string} url
 * @param {object} options
 * @param {number} timeoutMs
 * @returns {Promise<Response>}
 */
export async function fetchWithTimeout(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Fetches capitulation signals with primary backend endpoint and local fallback.
 * Returns empty array [] on total failure.
 *
 * @param {object} options
 * @returns {Promise<Array>}
 */
export async function fetchCapitulationSignals(options = {}) {
  const timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;
  const baseUrl = options.baseUrl || BACKEND_URL;

  try {
    const resp = await fetchWithTimeout(`${baseUrl}/api/capitulation`, {}, timeoutMs);
    if (resp.ok) {
      const data = await resp.json();
      if (Array.isArray(data)) {
        return data;
      }
    }
  } catch (err) {
    console.warn('Primary capitulation fetch failed, attempting local fallback:', err);
  }

  // Fallback fetch
  try {
    const fallbackResp = await fetchWithTimeout('/capitulation_signals.json', {}, timeoutMs);
    if (fallbackResp.ok) {
      const data = await fallbackResp.json();
      if (Array.isArray(data)) {
        return data;
      }
    }
  } catch (err) {
    console.error('Capitulation fallback fetch failed:', err);
  }

  return [];
}

/**
 * Fetches breakout candidate signals with primary backend endpoint and local fallback.
 * Returns empty array [] on total failure.
 *
 * @param {object} options
 * @returns {Promise<Array>}
 */
export async function fetchCandidates(options = {}) {
  const timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;
  const baseUrl = options.baseUrl || BACKEND_URL;

  try {
    const resp = await fetchWithTimeout(`${baseUrl}/api/candidates`, {}, timeoutMs);
    if (resp.ok) {
      const data = await resp.json();
      if (Array.isArray(data)) {
        return data;
      }
    }
  } catch (err) {
    console.warn('Primary candidates fetch failed, attempting local fallback:', err);
  }

  // Fallback fetch
  try {
    const fallbackResp = await fetchWithTimeout('/recent_signals.json', {}, timeoutMs);
    if (fallbackResp.ok) {
      const data = await fallbackResp.json();
      if (Array.isArray(data)) {
        return data;
      }
    }
  } catch (err) {
    console.error('Candidates fallback fetch failed:', err);
  }

  return [];
}

/**
 * Fetches live price map for given tickers.
 *
 * @param {string[]} tickers
 * @param {object} options
 * @returns {Promise<Record<string, number>>}
 */
export async function fetchLivePrices(tickers, options = {}) {
  if (!Array.isArray(tickers) || tickers.length === 0) return {};

  const uniqueTickers = [...new Set(tickers)].filter(Boolean);
  if (uniqueTickers.length === 0) return {};

  const timeoutMs = options.timeoutMs || 8000;
  const baseUrl = options.baseUrl || BACKEND_URL;
  const tickersParam = uniqueTickers.join(',');

  try {
    const resp = await fetchWithTimeout(`${baseUrl}/api/prices?tickers=${tickersParam}`, {}, timeoutMs);
    if (resp.ok) {
      const data = await resp.json();
      return data || {};
    }
  } catch (err) {
    console.warn('Live price fetch failed:', err);
  }

  return {};
}
