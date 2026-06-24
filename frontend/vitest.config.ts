import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Pure helpers run in plain Node; no jsdom needed.
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
