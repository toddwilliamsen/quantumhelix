/**
 * Shared API helpers — auth header, JSON parse, consistent errors.
 */

export function getToken() {
  return localStorage.getItem('quantum_token');
}

export function getRole() {
  return localStorage.getItem('quantum_role');
}

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

/**
 * fetch wrapper that attaches Bearer auth and parses JSON when present.
 * @param {string} path
 * @param {RequestInit & { token?: string, json?: any }} [opts]
 */
export async function apiFetch(path, opts = {}) {
  const { token = getToken(), json, headers: extraHeaders, ...rest } = opts;
  const headers = new Headers(extraHeaders || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let body = rest.body;
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(json);
  }
  const res = await fetch(path, { ...rest, headers, body });
  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const data = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    const msg = (data && (data.message || data.error)) || `Request failed (${res.status})`;
    throw new ApiError(msg, res.status, data);
  }
  return data !== null ? data : res;
}

/** Debounce a function; returns a cancellable wrapper. */
export function debounce(fn, waitMs = 300) {
  let timer;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), waitMs);
  };
  wrapped.cancel = () => clearTimeout(timer);
  return wrapped;
}
