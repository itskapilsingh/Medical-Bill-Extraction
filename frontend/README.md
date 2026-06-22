# Frontend — Next.js + Better Auth

The web client. Next.js (App Router) with Better Auth for email/password sign-up, sign-in,
and sessions. A signed-in user uploads billing PDFs and reviews their own extracted records;
isolation is enforced by the database's RLS, not the UI.

## How it fits together

- **Auth** (`lib/auth.ts`, `app/api/auth/[...all]`): Better Auth owns sessions and writes the
  `user`/`session`/`account`/`verification` tables over the admin `DATABASE_URL`. The session
  cookie is httpOnly and stays on this origin.
- **BFF proxy** (`app/api/backend/[...path]`): the browser only ever calls this same-origin
  route. It validates the Better Auth session, then forwards the request to the FastAPI API
  with the raw session token as `Authorization: Bearer …`. This sidesteps the SameSite=Lax
  problem (the cookie would not cross-origin to the API on :8000) and keeps a clean trust
  boundary — the API re-validates the token against the shared `session` table itself.
- **Pages**: `app/login` (sign in / create account), `app/dashboard` (protected; upload +
  job list with polling + result/flag display).

## Run

Part of the stack — `docker compose up` from the repo root serves it on
http://localhost:3000. Standalone:

```bash
npm install
npm run dev      # or: npm run build && npm start
```

Env (from the repo-root `.env`): `DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`,
`API_INTERNAL_URL` (point at `http://localhost:8000` when running outside Docker),
`TRUSTED_ORIGINS`.

## Stack notes

- **App Router** for server components (session checks happen server-side before render) and
  colocated route handlers (the auth handler and BFF proxy are just routes).
- **Tailwind v4** with a small set of primitives in `app/globals.css` — clean and legible
  over elaborate, per the brief.
- **Standalone output** (`next.config.mjs`) so the Docker runtime image is small.
