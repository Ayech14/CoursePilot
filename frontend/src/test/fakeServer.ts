import { vi } from "vitest";

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function errorResponse(status: number, code: string, message: string, details: unknown = null) {
  return jsonResponse(status, { error: { code, message, details, request_id: "req-1" } });
}

export const ADA = {
  id: "1",
  email: "ada@example.com",
  display_name: "Ada",
  timezone: "America/Toronto",
  created_at: "2026-11-01T00:00:00Z",
};

export const session = (token = "token-1", user = ADA) => ({
  access_token: token,
  token_type: "bearer",
  expires_in: 900,
  user,
});

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

/** Replace global fetch. The handler receives the path, e.g. "/api/v1/users/me". */
export function stubFetch(handler: Handler) {
  const mock = vi.fn((url: string, init: RequestInit) => Promise.resolve(handler(url, init)));
  vi.stubGlobal("fetch", mock);
  return mock;
}

export function callsTo(mock: ReturnType<typeof stubFetch>, path: string) {
  return mock.mock.calls.filter(([url]) => url === path);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RouteHandler = (body: any, url: string) => Response;

/** Stub the API by "METHOD /path". The session refresh succeeds unless a route overrides it. */
export function stubApi(routes: Record<string, RouteHandler>) {
  return stubFetch((url, init) => {
    const key = `${init.method ?? "GET"} ${url.replace("/api/v1", "").split("?")[0]}`;
    if (key === "POST /auth/refresh" && !routes[key]) return jsonResponse(200, session());
    const handler = routes[key];
    if (!handler) return errorResponse(404, "not_found", `No stub for ${key}`);
    return handler(init.body ? JSON.parse(init.body as string) : undefined, url);
  });
}

/** Parsed JSON bodies of every call to one "METHOD /path". */
export function bodiesSent(mock: ReturnType<typeof stubFetch>, route: string) {
  const [method, path] = route.split(" ");
  return mock.mock.calls
    .filter(([url, init]) => (init.method ?? "GET") === method && url.split("?")[0] === `/api/v1${path}`)
    .map(([, init]) => JSON.parse(init.body as string));
}
