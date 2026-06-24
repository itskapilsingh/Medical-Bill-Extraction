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

### Authentication
- Better Auth with server-enforced password minimum length, bounded session
  lifetime with rotation, and rate-limited auth endpoints.
- Failed authentications are logged (`auth_failed` with reason, path, client IP)
  for an audit trail.
- CSRF/Origin trust is restricted to the web origin only.

### Abuse / DoS resistance
- Per-IP request rate limiting, with a stricter budget for uploads. The client IP
  is resolved spoof-resistantly: `X-Forwarded-For` is trusted only when the peer is
  a configured `TRUSTED_PROXIES` entry, otherwise the real TCP peer is used, so a
  direct client can't rotate the header to dodge the limit. The limiter's state map
  is swept each window so idle keys can't accumulate without bound.
- Upload size cap enforced by **streaming** the body (the request is rejected
  before it is fully buffered in memory), at both the BFF and the API.
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
   are for local development only.
5. **Distributed rate limiting.** The in-process limiter protects a single replica.
   Behind a load balancer with multiple API replicas, move it to a shared store
   (e.g. Redis) or enforce limits at the ingress.
6. **Backups & access logging.** Encrypted, access-controlled backups with a tested
   restore path, and retention of the structured audit logs this app emits.

## Reporting

This is a take-home project, not a production service. For a real deployment,
route security reports to a monitored channel and document the response process
here.
