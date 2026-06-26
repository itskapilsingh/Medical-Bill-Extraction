import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

// getSession is configured per test. vi.hoisted keeps it defined before the
// hoisted vi.mock factory runs.
const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }));
vi.mock("@/lib/auth", () => ({ auth: { api: { getSession } } }));
// The route awaits headers(); it doesn't matter what they are for these tests.
vi.mock("next/headers", () => ({ headers: async () => new Headers() }));

const API_BASE = "http://test-api";

// Load the route after the upstream URL env is set (the route reads it once at
// module load). Mocks above are hoisted, so they apply to this dynamic import.
let route: typeof import("./route");
beforeAll(async () => {
  process.env.API_INTERNAL_URL = API_BASE;
  route = await import("./route");
});

const fetchMock = vi.fn();

beforeEach(() => {
  getSession.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function makeReq(opts: {
  method?: string;
  url?: string;
  headers?: Record<string, string>;
} = {}): NextRequest {
  const url = opts.url ?? "http://localhost/api/backend/jobs?status=completed";
  return {
    method: opts.method ?? "GET",
    headers: new Headers(opts.headers ?? {}),
    nextUrl: new URL(url),
    body: null,
  } as unknown as NextRequest;
}

const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });

describe("BFF proxy route", () => {
  it("returns 401 and never calls upstream when there is no session", async () => {
    getSession.mockResolvedValue(null);

    const res = await route.GET(makeReq(), ctx(["jobs"]));

    expect(res.status).toBe(401);
    await expect(res.json()).resolves.toEqual({ error: "unauthenticated" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards an authenticated GET with a Bearer token and preserves the query", async () => {
    getSession.mockResolvedValue({ session: { token: "tok123" } });
    fetchMock.mockResolvedValue(
      new Response('{"ok":true}', {
        status: 200,
        headers: { "content-type": "application/json", "retry-after": "5" },
      }),
    );

    const res = await route.GET(
      makeReq({ url: "http://localhost/api/backend/jobs?status=completed" }),
      ctx(["jobs"]),
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [target, init] = fetchMock.mock.calls[0];
    expect(target).toBe(`${API_BASE}/jobs?status=completed`);
    expect((init.headers as Record<string, string>).authorization).toBe("Bearer tok123");
    expect(res.status).toBe(200);
    // Selected upstream headers are passed back to the client.
    expect(res.headers.get("content-type")).toBe("application/json");
    expect(res.headers.get("retry-after")).toBe("5");
    await expect(res.json()).resolves.toEqual({ ok: true });
  });

  it("maps an upstream connection failure to a clean 502", async () => {
    getSession.mockResolvedValue({ session: { token: "tok123" } });
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));

    const res = await route.GET(makeReq(), ctx(["jobs"]));

    expect(res.status).toBe(502);
    await expect(res.json()).resolves.toEqual({ message: "Backend API is unavailable" });
  });

  it("rejects an over-large upload with 413 before contacting upstream", async () => {
    getSession.mockResolvedValue({ session: { token: "tok123" } });

    const res = await route.POST(
      makeReq({
        method: "POST",
        headers: { "content-length": String(27 * 1024 * 1024) },
      }),
      ctx(["jobs"]),
    );

    expect(res.status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
