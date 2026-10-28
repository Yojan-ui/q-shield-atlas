// One fetch wrapper for the whole app: timeout, one retry for idempotent GETs (network error / 5xx / timeout),
// CSRF double-submit header on writes, JSON error envelope -> ApiError, failures reported once via onError.
export class ApiError extends Error {
  constructor(status, code, message, fields = null) {
    super(message);
    this.status = status; this.code = code; this.fields = fields;
  }
}

export function readCookie(cookieString, name) {
  for (const part of (cookieString || "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return "";
}

export function createApi({ fetchImpl, cookie = () => "", onError = () => {}, sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  timeoutMs = 10000 } = {}) {
  async function once(path, opts) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), opts.timeout ?? timeoutMs);
    const onAbort = () => ctl.abort();
    if (opts.signal) opts.signal.addEventListener("abort", onAbort, { once: true });
    try {
      const headers = { Accept: "application/json", ...(opts.headers || {}) };
      let body = opts.body;
      if (body !== undefined && !(typeof Blob !== "undefined" && body instanceof Blob) && !(body instanceof ArrayBuffer)) {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(body);
      }
      if (opts.method !== "GET") headers["X-CSRF-Token"] = readCookie(cookie(), "atlas_csrf");
      const res = await fetchImpl(path, { method: opts.method, headers, body, credentials: "same-origin", signal: ctl.signal, cache: "no-store" });
      if (opts.raw && res.ok) return res;
      const text = await res.text();
      let data = null;
      try { data = text ? JSON.parse(text) : null; } catch { data = null; }
      if (!res.ok) {
        const e = (data && data.error) || {};
        throw new ApiError(res.status, e.code || `http_${res.status}`, e.message || `request failed (HTTP ${res.status})`, e.fields || null);
      }
      return data;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (opts.signal && opts.signal.aborted) throw new ApiError(0, "aborted", "request cancelled");
      if (err && err.name === "AbortError") throw new ApiError(0, "timeout", "the server did not answer in time");
      throw new ApiError(0, "network", "cannot reach the Atlas server");
    } finally {
      clearTimeout(timer);
      if (opts.signal) opts.signal.removeEventListener("abort", onAbort);
    }
  }

  async function request(path, opts = {}) {
    const o = { method: "GET", retry: undefined, quiet: false, ...opts };
    const retries = o.retry ?? (o.method === "GET" ? 1 : 0);
    for (let attempt = 0; ; attempt++) {
      try {
        return await once(path, o);
      } catch (err) {
        const transient = err.status === 0 && err.code !== "aborted" || err.status >= 500;
        if (transient && attempt < retries) { await sleep(300 * (attempt + 1)); continue; }
        if (!o.quiet && err.code !== "aborted") onError(err, path);
        throw err;
      }
    }
  }

  return {
    get: (p, o) => request(p, { ...o, method: "GET" }),
    post: (p, body, o) => request(p, { ...o, method: "POST", body: body ?? {} }),
    put: (p, body, o) => request(p, { ...o, method: "PUT", body }),
    del: (p, o) => request(p, { ...o, method: "DELETE" }),
    request,
  };
}
