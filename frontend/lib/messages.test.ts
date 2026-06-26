import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import { rateLimitMessage, uploadErrorMessage } from "@/lib/messages";

describe("rateLimitMessage", () => {
  it("names the wait time when known, pluralizing correctly", () => {
    expect(rateLimitMessage(1)).toContain("1 second.");
    expect(rateLimitMessage(30)).toContain("30 seconds.");
  });

  it("rounds fractional seconds up", () => {
    expect(rateLimitMessage(2.1)).toContain("3 seconds.");
  });

  it("falls back to generic copy when the wait is unknown or zero", () => {
    const generic = "Please wait a moment and try again.";
    expect(rateLimitMessage()).toContain(generic);
    expect(rateLimitMessage(0)).toContain(generic);
  });
});

describe("uploadErrorMessage", () => {
  it("uses the rate-limit copy (with retry time) for a 429", () => {
    const err = new ApiError("Rate limit exceeded. Please retry later.", 429, 12);
    expect(uploadErrorMessage(err)).toContain("Try again in 12 seconds.");
  });

  it("passes through the server message for other API errors", () => {
    const err = new ApiError("Upload exceeds the maximum allowed size", 413);
    expect(uploadErrorMessage(err)).toBe("Upload exceeds the maximum allowed size");
  });

  it("has a sane fallback for non-Error throws", () => {
    expect(uploadErrorMessage("boom")).toBe("Upload failed. Please try again.");
  });
});
