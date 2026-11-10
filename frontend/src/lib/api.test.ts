import { describe, expect, it, vi } from "vitest";

import { callsTo, errorResponse, jsonResponse, session, stubFetch } from "../test/fakeServer";
import { api, ApiError, onSessionExpired, refreshSession, setAccessToken } from "./api";

const ME = "/api/v1/users/me";
const REFRESH = "/api/v1/auth/refresh";

function authHeader(init: RequestInit | undefined): string | null {
  return new Headers(init?.headers).get("Authorization");
}

describe("api", () => {
  it("attaches the access token and returns JSON", async () => {
    setAccessToken("abc");
    const fetchMock = stubFetch(() => jsonResponse(200, { ok: true }));

    await expect(api(ME.replace("/api/v1", ""))).resolves.toEqual({ ok: true });

    expect(authHeader(fetchMock.mock.calls[0]?.[1])).toBe("Bearer abc");
  });

  it("returns undefined for an empty 204 response", async () => {
    stubFetch(() => new Response(null, { status: 204 }));
    await expect(api("/auth/logout", "POST")).resolves.toBeUndefined();
  });

  it("converts the error format into an ApiError with field errors", async () => {
    stubFetch(() =>
      errorResponse(422, "validation_error", "Invalid", [{ field: "email", message: "Bad email" }]),
    );

    const error = await api("/auth/register", "POST", {}).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "validation_error",
      requestId: "req-1",
      fieldErrors: { email: "Bad email" },
    });
  });

  it("reports network failure as a readable error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api("/users/me")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("handles a non-JSON error response", async () => {
    stubFetch(() => new Response("<html>Bad gateway</html>", { status: 502 }));
    await expect(api("/users/me")).rejects.toMatchObject({
      status: 502,
      code: "unexpected_response",
    });
  });

  it("refreshes once and retries after a 401", async () => {
    setAccessToken("expired");
    const fetchMock = stubFetch((url, init) => {
      if (url === REFRESH) return jsonResponse(200, session("fresh"));
      return authHeader(init) === "Bearer fresh"
        ? jsonResponse(200, { ok: true })
        : errorResponse(401, "not_authenticated", "No");
    });

    await expect(api("/users/me")).resolves.toEqual({ ok: true });

    expect(callsTo(fetchMock, REFRESH)).toHaveLength(1);
    expect(callsTo(fetchMock, ME)).toHaveLength(2);
  });

  it("shares a single refresh between concurrent 401s", async () => {
    setAccessToken("expired");
    const fetchMock = stubFetch(async (url, init) => {
      if (url === REFRESH) {
        await new Promise((resolve) => setTimeout(resolve, 5));
        return jsonResponse(200, session("fresh"));
      }
      return authHeader(init) === "Bearer fresh"
        ? jsonResponse(200, { url })
        : errorResponse(401, "not_authenticated", "No");
    });

    await Promise.all([api("/users/me"), api("/users/me"), api("/users/me")]);

    expect(callsTo(fetchMock, REFRESH)).toHaveLength(1);
  });

  it("signals an expired session when refresh fails", async () => {
    const expired = vi.fn();
    onSessionExpired(expired);
    stubFetch(() => errorResponse(401, "not_authenticated", "No"));

    await expect(api("/users/me")).rejects.toMatchObject({ status: 401 });

    expect(expired).toHaveBeenCalledOnce();
    onSessionExpired(null);
  });

  it("does not try to refresh after a failed login", async () => {
    const fetchMock = stubFetch(() => errorResponse(401, "invalid_credentials", "Incorrect"));

    await expect(api("/auth/login", "POST", {})).rejects.toMatchObject({
      code: "invalid_credentials",
    });

    expect(callsTo(fetchMock, REFRESH)).toHaveLength(0);
  });

  it("allows another refresh after the previous one finished", async () => {
    const fetchMock = stubFetch(() => jsonResponse(200, session()));

    await refreshSession();
    await refreshSession();

    expect(callsTo(fetchMock, REFRESH)).toHaveLength(2);
  });
});
