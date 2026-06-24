import { betterAuth } from "better-auth";
import { Pool } from "pg";

// A single shared pool per process. Cached on globalThis so Next's dev HMR does
// not open a new pool on every reload.
const globalForPool = globalThis as unknown as { __authPool?: Pool };

const pool =
  globalForPool.__authPool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    max: 5,
  });

if (process.env.NODE_ENV !== "production") {
  globalForPool.__authPool = pool;
}

const trustedOrigins = (process.env.TRUSTED_ORIGINS ?? "http://localhost:3000")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

/**
 * Better Auth owns session creation and validation. It writes the user/session/
 * account/verification tables (created by Alembic) over the admin DATABASE_URL.
 * The FastAPI API reads the same `session` table to validate tokens it is
 * handed — the "shared session table" topology.
 *
 * BETTER_AUTH_SECRET and BETTER_AUTH_URL are read from the environment.
 */
export const auth = betterAuth({
  database: pool,
  emailAndPassword: {
    enabled: true,
    minPasswordLength: 8, // server-enforced (client minLength is advisory only)
    maxPasswordLength: 128,
    // No email server in this stack; verification is off (Better Auth default).
    requireEmailVerification: false,
  },
  session: {
    expiresIn: 60 * 60 * 24 * 7, // 7 days
    updateAge: 60 * 60 * 24, // refresh/rotate the session after a day of use
  },
  // Brute-force / abuse protection on the auth endpoints.
  rateLimit: {
    enabled: true,
    window: 60,
    max: 30,
  },
  trustedOrigins,
});
