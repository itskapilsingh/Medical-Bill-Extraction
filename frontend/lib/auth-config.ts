// Pure resolution of the Better Auth configuration from environment variables.
//
// Kept free of side effects (no Pool, no betterAuth()) so the production
// guardrails below — which decide whether a misconfiguration is fatal — can be
// unit-tested directly against a plain env object. lib/auth.ts calls this once at
// import and wires the result into betterAuth().

export interface AuthEnv {
  /** Connection string for the auth-only database role. */
  databaseUrl: string;
  /** Better Auth signing secret. */
  secret: string;
  /** Public base URL Better Auth issues cookies/links against. */
  baseURL: string;
  /** Origins permitted to call the auth endpoints. */
  trustedOrigins: string[];
}

/**
 * Resolve and validate the auth configuration from `env`.
 *
 * Throws (fail-fast) when runtime or build configuration is missing a required
 * value, or when a production runtime would reuse the admin DATABASE_URL for
 * auth. Local development may point AUTH_DATABASE_URL at DATABASE_URL only when
 * NODE_ENV is not production.
 */
export function resolveAuthEnv(env: NodeJS.ProcessEnv): AuthEnv {
  const isProduction = env.NODE_ENV === "production";

  const databaseUrl =
    env.AUTH_DATABASE_URL ??
    (isProduction ? undefined : env.DATABASE_URL);

  if (!databaseUrl) {
    throw new Error("AUTH_DATABASE_URL is required for the Better Auth database pool");
  }
  if (
    isProduction &&
    env.DATABASE_URL &&
    databaseUrl === env.DATABASE_URL
  ) {
    throw new Error("AUTH_DATABASE_URL must not use the admin DATABASE_URL in production");
  }

  const secret = env.BETTER_AUTH_SECRET;
  if (!secret) {
    throw new Error("BETTER_AUTH_SECRET is required");
  }

  const baseURL = env.BETTER_AUTH_URL;
  if (!baseURL) {
    throw new Error("BETTER_AUTH_URL is required");
  }

  if (!env.TRUSTED_ORIGINS) {
    throw new Error("TRUSTED_ORIGINS is required");
  }
  const trustedOrigins = env.TRUSTED_ORIGINS
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);
  if (trustedOrigins.length === 0) {
    throw new Error("TRUSTED_ORIGINS must include at least one origin");
  }

  return { databaseUrl, secret, baseURL, trustedOrigins };
}
