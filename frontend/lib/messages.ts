// User-facing message helpers. Pure and side-effect-free so they're trivially
// unit-testable (see messages.test.ts).

import { ApiError } from "@/lib/api";

/** Friendly copy for a 429, telling the user when to retry if we know. */
export function rateLimitMessage(retryAfterSeconds?: number): string {
  if (retryAfterSeconds && retryAfterSeconds > 0) {
    const s = Math.ceil(retryAfterSeconds);
    return `You're uploading too quickly. Try again in ${s} second${s === 1 ? "" : "s"}.`;
  }
  return "You're uploading too quickly. Please wait a moment and try again.";
}

/** Map any thrown error from an upload into a single human-readable line. */
export function uploadErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 429) {
    return rateLimitMessage(err.retryAfter);
  }
  if (err instanceof Error && err.message) return err.message;
  return "Upload failed. Please try again.";
}
