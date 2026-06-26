# Security & PHI Handling

Medical billing PDFs are **Protected Health Information (PHI)**. This document
states what the application enforces in code and what an operator must provide at
deployment before pointing it at real patient data. It is deliberately explicit
about the boundary: the code closes the application-layer gaps; the items under
[Deployment requirements](#deployment-requirements-before-real-phi) are
infrastructure controls the code cannot grant itself.

## Threat model

- **Tenant isolation** is the primary guarantee: one user must never read,
  infer, or act on another user's jobs or extracted records.
- **Inputs are untrusted**: PDFs are uploaded by users and parsed by the worker;
  a hostile or malformed file must not exhaust or hang the service, and its text
  must not be able to redirect the extraction agent.
- **PHI exposure is minimized**: the raw document lives on disk only as long as it
  takes to extract from it, and only the structured result is retained.

## What the application enforces

### Isolation (defense in depth)
- **Row-Level Security** on `jobs`, keyed off `current_setting('app.user_id')`.
  The API and worker connect as a non-owner, non-`BYPASSRLS` role, so a missing
  `WHERE` clause cannot leak another tenant's rows — the database filters them.
- The worker processes each job under the **job owner's** identity
  (`acting_as(owner_id)`), so result writes are RLS-scoped exactly as if the owner
  wrote them. The one deliberate cross-tenant surface — claiming the next pending
  job — is a `SECURITY DEFINER` function that hands back a single row.
- The browser only ever talks to a same-origin **BFF proxy**; the session token is
  re-validated by the API against the shared session table. Neither service blindly
  trusts the other.
- Better Auth writes through a dedicated `billing_auth` database role
  (`AUTH_DATABASE_URL`) that has DML only on the auth tables. It is not the schema
  owner and has no `jobs` privileges, so the web tier is not a bypass around RLS.

### Authentication
- Better Auth with server-enforced password minimum length, bounded session
  lifetime with rotation, and rate-limited auth endpoints.
- Failed authentications are logged (`auth_failed` with reason, path, client IP)
  for an audit trail.
- CSRF/Origin trust is restricted to the web origin only.

### Abuse / DoS resistance
- Per-IP request rate limiting, with a stricter budget for uploads. The client IP
  is resolved spoof-resistantly: `X-Forwarded-For` is honored only when the peer is
  a configured `TRUSTED_PROXIES` entry, and then only the address contributed by our
  own proxy hops (read right-to-left) is believed — never a client-prepended value —
  otherwise the real TCP peer is used. So a client can't rotate the header to dodge
  the limit, with or without a proxy in front. The limiter's state map is swept each
  window so idle keys can't accumulate without bound.
- Per-**user** rate limiting on `POST /jobs`, keyed on the authenticated user id
  (`RATE_LIMIT_USER_UPLOAD_MAX_REQUESTS`). Each accepted upload triggers a paid LLM
  extraction against a small worker pool, so this is the real guard against
  unbounded consumption (OWASP API4:2023 / LLM10, CWE-770): a single account can't
  drive runaway extraction spend or starve other tenants' jobs by bursting uploads,
  and — unlike the per-IP layer — the budget follows the account across IP rotation
  and shared NAT. Over-budget requests get `429` with `Retry-After` *before* any PDF
  is persisted or any extraction is queued. The per-IP and per-user layers share one
  in-process sliding-window primitive.
- Upload size cap enforced by **streaming** the body (the request is rejected
  before it is fully buffered in memory), at both the BFF and the API.
- Duplicate uploads are fingerprinted before durable storage when possible. Cache
  hits and in-flight duplicates do not persist a second raw PDF, and race-created
  duplicate files are deleted immediately.
- PDF page-count cap, a wall-clock timeout on PDF parsing, and a timeout on the
  model call — a hostile or huge document cannot pin a worker. Parsing runs off
  the event loop so one bad file cannot stall the worker's other duties.

### Transport & content hardening
- Security headers on both services: strict CSP, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store` on API responses, and HSTS.

### PHI minimization & retention
- The source PDF is deleted from the shared volume the moment a job reaches a
  terminal state (`DELETE_PDF_AFTER_PROCESSING`, default on).
- A periodic worker sweep removes any PDFs left on the volume older than
  `RETENTION_DAYS` (orphans from a crash, or runs with deletion disabled).
- The worker drains gracefully on `SIGTERM`/`SIGINT`: it stops claiming new work,
  lets the in-flight job finish, and exits — so a deploy/restart never strands a
  job mid-run.

### Prompt-injection posture
- Document text is untrusted. The extraction agent is instructed to treat page
  content strictly as data to extract from, never as instructions, and it returns
  a fixed structured schema rather than free-form actions — there is no tool the
  agent can be talked into misusing against another tenant.

## Deployment requirements (before real PHI)

These are **operator responsibilities**. The application is not cleared to process
real patient data until they are in place.

1. **Business Associate Agreement (BAA) with every PHI subprocessor.** This stack
   sends document text to the OpenAI API for extraction. Under HIPAA you must have
   a signed BAA with OpenAI (and use an API tier the BAA covers), or replace the
   model with a self-hosted/BAA-covered alternative. **Do not send real PHI to a
   model endpoint that is not under a BAA.**
2. **Encryption at rest.** Enable encryption for the Postgres data volume and the
   PDF volume (e.g. an encrypted EBS/disk or a managed Postgres with encryption
   on). The application stores extracted records in the clear in the database by
   design; the disk must be encrypted underneath it.
3. **TLS everywhere.** Terminate TLS in front of the web service and require HTTPS
   (the HSTS header assumes it). Use TLS for the Postgres connection. Never expose
   the API container's port `8000` publicly — only the BFF is meant to be reachable.
4. **Secrets management.** Generate a unique `BETTER_AUTH_SECRET`
   (`openssl rand -hex 32`) and strong, unique database passwords; inject them from
   a secrets manager, not from a committed `.env`. The defaults in `.env.example`
   are for local development only. Use separate admin, API (`billing_app`), and
   auth (`billing_auth`) database credentials.
5. **Distributed rate limiting.** The in-process limiter protects a single replica.
   Behind a load balancer with multiple API replicas, move it to a shared store
   (e.g. Redis) or enforce limits at the ingress.
6. **Backups & access logging.** Encrypted, access-controlled backups with a tested
   restore path, and retention of the structured audit logs this app emits.

## Reporting

This is a take-home project, not a production service. For a real deployment,
route security reports to a monitored channel and document the response process
here.

## Submission preflight

Before packaging or sharing the repository, run:

```bash
python scripts/preflight.py
```

The check fails if local-only artifacts are present, including `.env`, runtime
PDFs, local logs, build outputs, virtualenvs, or an unfinished design/Paxel entry.
Package from git (`git archive`) or a clean checkout rather than zipping the
working directory.

For convenience, `python scripts/create_submission.py` creates a source zip from
tracked and safe untracked files while excluding ignored runtime artifacts.
