// TODO-368: one Flask base URL + JSON fetch helpers, instead of 30+ copies of
// `const BASE = window.api.flaskBase` and hand-rolled fetch().then(r => r.json()).
// Like the code they replace, these do NOT throw on non-2xx — routes return JSON
// error bodies that callers inspect.

export const BASE = window.api.flaskBase

/** GET `${BASE}${path}` and parse the JSON body. */
export function getJson<T = any>(path: string, init?: RequestInit): Promise<T> {
  return fetch(`${BASE}${path}`, init).then(r => r.json())
}

/** Send `body` (JSON-encoded, if given) to `${BASE}${path}` and parse the JSON reply. */
export function postJson<T = any>(
  path: string,
  body?: unknown,
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'POST',
): Promise<T> {
  const init: RequestInit = body === undefined
    ? { method }
    : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  return fetch(`${BASE}${path}`, init).then(r => r.json())
}
