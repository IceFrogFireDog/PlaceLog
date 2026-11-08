export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fieldErrors: Record<string, string> = {},
    /** 응답 본문 전체 (예: 409 DUPLICATE_PLACE의 existing_place) */
    public body: Record<string, unknown> | null = null,
  ) {
    super(message);
  }
}

/** 목록·지도 요청의 404: 그 기능이 아직 없는 백엔드(1차)이거나 대상이 없음 → 빈 결과로 보여 준다 */
export const isNotFound = (e: unknown) => e instanceof ApiError && e.status === 404;

let csrfToken: string | null = null;
export const setCsrfToken = (t: string | null) => { csrfToken = t; };

// 세션이 바뀌었을 수 있는 응답(401, CSRF 실패)을 받으면 AuthProvider가 다시 확인하도록 알린다.
const staleListeners = new Set<() => void>();
export function onAuthStale(fn: () => void): () => void {
  staleListeners.add(fn);
  return () => { staleListeners.delete(fn); };
}

interface Options {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
  form?: FormData;
  query?: Record<string, string | number | undefined | null>;
  signal?: AbortSignal;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  if (opts.form) body = opts.form;
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let url = API_BASE + path;
  if (opts.query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.query)) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }

  let res: Response;
  try {
    res = await fetch(url, { method, headers, body, credentials: "same-origin", signal: opts.signal, cache: "no-store" });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "NETWORK_ERROR", "서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const stale = res.status === 401 || (res.status === 403 && data?.code === "CSRF_FAILED");
    if (stale && !path.startsWith("/auth/me") && !path.startsWith("/auth/login")) staleListeners.forEach((fn) => fn());
    throw new ApiError(res.status, data?.code ?? "HTTP_ERROR", data?.message ?? "요청을 처리하지 못했습니다.", data?.field_errors ?? {}, data && typeof data === "object" ? data : null);
  }
  return data as T;
}

export const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "알 수 없는 오류가 발생했습니다.");
