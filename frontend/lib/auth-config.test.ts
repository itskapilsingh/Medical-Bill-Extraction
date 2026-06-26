import { describe, expect, it } from "vitest";

import { resolveAuthEnv } from "@/lib/auth-config";

// Build a clean env object for each case (vitest's process.env is shared, so we
// pass an explicit object instead of mutating globals).
function env(overrides: Record<string, string | undefined> = {}): NodeJS.ProcessEnv {
  return overrides as NodeJS.ProcessEnv;
}

describe("resolveAuthEnv", () => {
  it("allows DATABASE_URL for local auth only outside production", () => {
    const cfg = resolveAuthEnv(
      env({
        NODE_ENV: "development",
        DATABASE_URL: "postgres://dev/app",
        BETTER_AUTH_SECRET: "dev-secret",
        BETTER_AUTH_URL: "http://localhost:3000",
        TRUSTED_ORIGINS: "http://localhost:3000",
      }),
    );
    expect(cfg.databaseUrl).toBe("postgres://dev/app");
    expect(cfg.secret).toBe("dev-secret");
    expect(cfg.baseURL).toBe("http://localhost:3000");
    expect(cfg.trustedOrigins).toEqual(["http://localhost:3000"]);
  });

  it("uses the explicit auth values when provided", () => {
    const cfg = resolveAuthEnv(
      env({
        NODE_ENV: "production",
        AUTH_DATABASE_URL: "postgres://auth_role/auth",
        DATABASE_URL: "postgres://admin/app",
        BETTER_AUTH_SECRET: "a-real-secret",
        BETTER_AUTH_URL: "https://app.example.com",
        TRUSTED_ORIGINS: "https://app.example.com, https://admin.example.com",
      }),
    );
    expect(cfg.databaseUrl).toBe("postgres://auth_role/auth");
    expect(cfg.secret).toBe("a-real-secret");
    expect(cfg.baseURL).toBe("https://app.example.com");
    expect(cfg.trustedOrigins).toEqual([
      "https://app.example.com",
      "https://admin.example.com",
    ]);
  });

  it("requires a database URL in production", () => {
    expect(() => resolveAuthEnv(env({ NODE_ENV: "production" }))).toThrow(
      /AUTH_DATABASE_URL is required/,
    );
  });

  it("rejects reusing the admin DATABASE_URL for auth in production", () => {
    expect(() =>
      resolveAuthEnv(
        env({
          NODE_ENV: "production",
          AUTH_DATABASE_URL: "postgres://shared/db",
          DATABASE_URL: "postgres://shared/db",
          BETTER_AUTH_SECRET: "s",
          BETTER_AUTH_URL: "https://x",
          TRUSTED_ORIGINS: "https://x",
        }),
      ),
    ).toThrow(/must not use the admin DATABASE_URL/);
  });

  it("requires a secret in production", () => {
    expect(() =>
      resolveAuthEnv(
        env({
          NODE_ENV: "production",
          AUTH_DATABASE_URL: "postgres://auth/db",
          BETTER_AUTH_URL: "https://x",
          TRUSTED_ORIGINS: "https://x",
        }),
      ),
    ).toThrow(/BETTER_AUTH_SECRET is required/);
  });

  it("requires a base URL in production", () => {
    expect(() =>
      resolveAuthEnv(
        env({
          NODE_ENV: "production",
          AUTH_DATABASE_URL: "postgres://auth/db",
          BETTER_AUTH_SECRET: "s",
          TRUSTED_ORIGINS: "https://x",
        }),
      ),
    ).toThrow(/BETTER_AUTH_URL is required/);
  });

  it("requires trusted origins", () => {
    expect(() =>
      resolveAuthEnv(
        env({
          NODE_ENV: "production",
          AUTH_DATABASE_URL: "postgres://auth/db",
          BETTER_AUTH_SECRET: "s",
          BETTER_AUTH_URL: "https://x",
        }),
      ),
    ).toThrow(/TRUSTED_ORIGINS is required/);
  });

  it("does not create production-build placeholders", () => {
    expect(() =>
      resolveAuthEnv(
        env({ NODE_ENV: "production", NEXT_PHASE: "phase-production-build" }),
      ),
    ).toThrow(/AUTH_DATABASE_URL is required/);
  });
});
