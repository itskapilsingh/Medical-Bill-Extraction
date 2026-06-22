import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

// Mounts every Better Auth endpoint (sign-up, sign-in, sign-out, get-session, …)
// under /api/auth/*. This is the only place sessions are issued.
export const { GET, POST } = toNextJsHandler(auth.handler);
