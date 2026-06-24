import { headers } from "next/headers";
import { NextRequest } from "next/server";

import { auth } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Inside Docker the API is reachable at http://api:8000; locally, override via env.
const API_BASE = process.env.API_INTERNAL_URL ?? "http://api:8000";

// Reject oversized bodies before buffering them (the API enforces the real cap).
const MAX_BODY_BYTES = 26 * 1024 * 1024; // ~25 MB + multipart overhead

/**
 * Backend-for-frontend proxy.
 *
 * The browser only ever talks to this same-origin route, so the httpOnly Better
 * Auth session cookie rides along (it would NOT cross-origin to :8000 under
 * SameSite=Lax). We validate the session here, then forward the request to the
 * FastAPI API with the raw session token as a Bearer credential. The API
 * re-validates that token against the shared session table — neither service
 * blindly trusts the other.
 */
async function proxy(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return Response.json({ error: "unauthenticated" }, { status: 401 });
  }

  const { path } = await ctx.params;
  const target = `${API_BASE}/${path.join("/")}${req.nextUrl.search}`;

  const forwardHeaders: Record<string, string> = {
    authorization: `Bearer ${session.session.token}`,
    accept: req.headers.get("accept") ?? "application/json",
  };
  const contentType = req.headers.get("content-type");
  if (contentType) forwardHeaders["content-type"] = contentType;

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers: forwardHeaders,
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    const declared = Number(req.headers.get("content-length") ?? "0");
    if (declared > MAX_BODY_BYTES) {
      return Response.json({ message: "Upload too large" }, { status: 413 });
    }
    init.body = await req.arrayBuffer();
    init.duplex = "half";
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    // API container down / starting / network blip — return a clean JSON error
    // the client can parse, not Next's opaque 500 HTML page.
    return Response.json({ message: "Backend API is unavailable" }, { status: 502 });
  }

  const responseHeaders = new Headers();
  const upstreamType = upstream.headers.get("content-type");
  if (upstreamType) responseHeaders.set("content-type", upstreamType);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
};
