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

export const session = (token = "token-1") => ({
  access_token: token,
  token_type: "bearer",
  expires_in: 900,
  user: ADA,
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
