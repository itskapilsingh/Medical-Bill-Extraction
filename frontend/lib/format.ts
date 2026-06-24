// Small pure formatting helpers shared across the UI. Kept dependency-free and
// side-effect-free so they're trivially unit-testable (see format.test.ts).

/** Human-readable byte size, e.g. 2_048 -> "2 KB", 5_400_000 -> "5.2 MB". */
export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Up-to-two-letter initials for an avatar, e.g. "Ada Lovelace" -> "AL". */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** USD currency, or an em dash for null/undefined. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** Last path segment of a stored PDF path, e.g. "/app/pdfs/u/abc.pdf" -> "abc.pdf". */
export function fileName(path: string): string {
  return path.split("/").pop() || path;
}
