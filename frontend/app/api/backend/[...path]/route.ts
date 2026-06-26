import { headers } from "next/headers";
import { NextRequest } from "next/server";

import { auth } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function requireEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value.replace(/\/+$/, "");
}

const API_BASE = requireEnv("API_INTERNAL_URL");

// Reject oversized bodies before buffering them (the API enforces the real cap).
const MAX_BODY_BYTES = 26 * 1024 * 1024; // ~25 MB + multipart overhead

async function readLimitedBody(req: NextRequest): Promise<ArrayBuffer | Response | undefined> {
  const declared = Number(req.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {
    return Response.json({ message: "Upload too large" }, { status: 413 });
  }
  if (!req.body) {
    return undefined;
  }

  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BODY_BYTES) {
      await reader.cancel();
      return Response.json({ message: "Upload too large" }, { status: 413 });
    }
    chunks.push(value);
  }

  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body.buffer;
}

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
    const body = await readLimitedBody(req);
    if (body instanceof Response) return body;
    init.body = body;
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
  // Pass through Retry-After so the client can tell the user when to retry (429).
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) responseHeaders.set("retry-after", retryAfter);

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
