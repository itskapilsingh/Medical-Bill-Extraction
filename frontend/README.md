# Frontend — your Next.js app

**This directory is intentionally empty. Build your web frontend here.**

Per [`../ASSIGNMENT.md`](../ASSIGNMENT.md), the platform's UI is a Next.js app with Better
Auth for sign up, sign in, and sessions. A signed-in user uploads medical billing PDFs and
views their own jobs and extracted results, scoped strictly to their account by the
database's Row-Level Security policies.

What we expect to find here when you submit:

- A Next.js application (App Router or Pages Router, your choice; justify it briefly in the
  design doc).
- Better Auth wired in, with auth tables migrated into Postgres.
- Screens to sign up, sign in, upload a PDF, and list and view jobs and their results.
- A `Dockerfile` for this service, wired into the repo-root `docker-compose.yml` so the
  whole stack still comes up with a single `docker compose up`. Serve on port `3000`.

Relevant environment variables are in the repo-root `.env.example`: `BETTER_AUTH_SECRET`,
`BETTER_AUTH_URL`, `NEXT_PUBLIC_API_BASE_URL`, and `DATABASE_URL`.

The bar for the frontend is working knowledge, not design mastery; see the *Frontend
Expectations* section of the assignment. Feel free to use AI design tooling (for example
Claude's `design` or `impeccable.style` skills) to help.
