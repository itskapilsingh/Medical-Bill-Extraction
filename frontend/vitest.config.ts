import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Mirror the tsconfig "@/*" -> project-root path alias so tests can import the
// same way app code does (e.g. "@/lib/api").
const root = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: { "@": root },
  },
  test: {
    // Pure helpers + route handlers run in plain Node; no jsdom needed.
    environment: "node",
    include: ["lib/**/*.test.ts", "app/**/*.test.ts"],
  },
});
