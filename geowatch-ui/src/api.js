/*
 * API access — base URL, credentials, and the fetch helpers.
 * Build item 43 (the second half), closing live breakage introduced by item 70.
 *
 * Item 70 put an API-key check at the perimeter of api.py: every route AND the
 * /runs static mount now require an `X-API-Key` header. This frontend sent no
 * header on any request, so from the moment that middleware shipped, every call
 * returned 401 — analysis, OSM overlays, and the landcover image alike. This
 * module is what makes the app work again.
 *
 * ── AN HONEST NOTE ON WHAT THIS KEY IS AND IS NOT ───────────────────────────
 *
 * `import.meta.env.VITE_*` values are INLINED INTO THE BUILT BUNDLE by Vite.
 * Anyone who can load this page can read this key out of the JavaScript. That
 * is not a flaw in this file, it is a property of shipping a secret to a
 * browser: a single-page app has nowhere to hide one.
 *
 * So this is a DEVELOPMENT SHARED SECRET for a localhost tool, not client
 * authentication. It is adequate here because the whole system is local: the
 * API binds to 127.0.0.1 by default and CORS admits only localhost origins. It
 * would NOT be adequate if this were deployed, where a real design needs either
 * a server-side session the browser never sees the secret for, or per-user
 * tokens issued after a login.
 *
 * Recorded here rather than left implicit, because the failure mode is someone
 * later reading "the API is authenticated" and believing the browser half of it
 * is too. It is not. C40's entry in 04_FINDINGS_LEDGER.md is the place that
 * reasoning belongs if this ever ships.
 */

export const API = 'http://localhost:8000'

export const API_KEY_HEADER = 'X-API-Key'

// Read once. Vite replaces this expression at build time.
export const API_KEY = import.meta.env?.VITE_GEOWATCH_API_KEY || ''

/** True when no key is configured — the app will 401 and should say why. */
export function isKeyMissing() {
  return !API_KEY
}

/** Headers for an authenticated request. Empty when no key is configured. */
export function authHeaders(extra = {}) {
  return API_KEY ? { [API_KEY_HEADER]: API_KEY, ...extra } : { ...extra }
}

/**
 * `fetch`, with credentials attached.
 *
 * Every call in this app goes through here rather than calling fetch directly,
 * so a newly added request is authenticated by default instead of by someone
 * remembering. That is the same argument item 70 used for putting the server
 * check in middleware rather than on each endpoint: coverage should be a
 * property of the path, not of anyone's memory.
 */
export function apiFetch(path, options = {}) {
  const url = path.startsWith('http') ? path : `${API}${path}`
  return fetch(url, { ...options, headers: authHeaders(options.headers || {}) })
}

/**
 * Fetch an image from the authenticated API and return an object URL.
 *
 * WHY THIS EXISTS. Leaflet's <ImageOverlay> takes a URL and lets the browser
 * load it as an ordinary image request — and an <img> load CANNOT carry a
 * custom header. Since item 70 the /runs mount requires one, so the landcover
 * overlay would simply fail to appear, quietly, with a 401 visible only in the
 * network tab.
 *
 * The alternatives were worse. Accepting the key as a query parameter would put
 * the secret into URLs, browser history and server logs. Exempting the static
 * mount from auth would reopen exactly the hole item 70 closed — /runs serves
 * data/pipeline_runs/, which is the same data C34 would have disclosed.
 *
 * So the bytes are fetched with the header and handed to Leaflet as a blob URL.
 * The caller must revoke it; `useAuthedImage` below does.
 */
export async function fetchImageObjectUrl(path) {
  const res = await apiFetch(path)
  if (!res.ok) throw new Error(`image fetch failed: ${res.status}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}
