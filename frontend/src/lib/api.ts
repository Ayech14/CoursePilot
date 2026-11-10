/**
 * The only module that talks to the backend.
 *
 * The access token lives in this module's memory rather than in localStorage, so a script
 * injected into the page cannot read a stored credential. The long-lived refresh token is in an
 * HttpOnly cookie that JavaScript cannot see at all. A page reload loses the access token, and
 * the app gets a new one by calling `refreshSession` on startup.
 */

export interface User {
  id: string;
  email: string;
  display_name: string;
  timezone: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

interface ErrorDetail {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: Record<string, string>;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: unknown = null,
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.fieldErrors = Array.isArray(details)
      ? Object.fromEntries((details as ErrorDetail[]).map((d) => [d.field, d.message]))
      : {};
  }
}

const BASE_URL = "/api/v1";

let accessToken: string | null = null;
let sessionExpiredListener: (() => void) | null = null;
let pendingRefresh: Promise<AuthResponse | null> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function onSessionExpired(listener: (() => void) | null): void {
  sessionExpiredListener = listener;
}

async function send(path: string, method: string, body: unknown): Promise<Response> {
  const headers = new Headers();
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  try {
    return await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection.");
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const { error } = await response.json();
    return new ApiError(response.status, error.code, error.message, error.details, error.request_id);
  } catch {
    return new ApiError(response.status, "unexpected_response", "The server returned an error.");
  }
}

/**
 * Get a new access token using the refresh cookie. Resolves to null when there is no valid session.
 *
 * Concurrent callers share one request. Refresh tokens are single use, so several parallel
 * refreshes triggered by a burst of 401s would otherwise look like token theft to the server.
 */
export function refreshSession(): Promise<AuthResponse | null> {
  pendingRefresh ??= (async () => {
    try {
      const response = await send("/auth/refresh", "POST", undefined);
      if (!response.ok) {
        setAccessToken(null);
        return null;
      }
      const session = (await response.json()) as AuthResponse;
      setAccessToken(session.access_token);
      return session;
    } finally {
      pendingRefresh = null;
    }
  })();
  return pendingRefresh;
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let response = await send(path, method, body);

  if (response.status === 401 && !path.startsWith("/auth/")) {
    const session = await refreshSession();
    if (session === null) {
      sessionExpiredListener?.();
      throw await toApiError(response);
    }
    response = await send(path, method, body);
  }

  if (!response.ok) throw await toApiError(response);
  return (response.status === 204 ? undefined : await response.json()) as T;
}
