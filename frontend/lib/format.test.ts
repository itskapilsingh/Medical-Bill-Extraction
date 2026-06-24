import { describe, expect, it } from "vitest";

import { fileName, formatBytes, initials, money } from "./format";

describe("formatBytes", () => {
  it("uses bytes under 1 KiB", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
  });
  it("rounds KB without decimals", () => {
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(1536)).toBe("2 KB"); // 1.5 KiB rounds to 2
  });
  it("uses one decimal for MB", () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatBytes(2_600_000)).toBe("2.5 MB");
  });
});

describe("initials", () => {
  it("takes first + last initial", () => {
    expect(initials("Ada Lovelace")).toBe("AL");
    expect(initials("  grace  brewster  hopper ")).toBe("GH");
  });
  it("takes up to two letters from a single name", () => {
    expect(initials("Cher")).toBe("CH");
  });
  it("falls back to ? when empty", () => {
    expect(initials("")).toBe("?");
    expect(initials("   ")).toBe("?");
  });
});

describe("money", () => {
  it("formats USD", () => {
    expect(money(1850)).toBe("$1,850.00");
    expect(money(0)).toBe("$0.00");
  });
  it("renders an em dash for null/undefined", () => {
    expect(money(null)).toBe("—");
    expect(money(undefined)).toBe("—");
  });
});

describe("fileName", () => {
  it("returns the last path segment", () => {
    expect(fileName("/app/pdfs/user-1/abc.pdf")).toBe("abc.pdf");
  });
  it("returns the input when there is no slash", () => {
    expect(fileName("invoice.pdf")).toBe("invoice.pdf");
  });
});
