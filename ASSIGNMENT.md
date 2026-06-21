# Take-Home Assignment: Medical Billing Extraction Platform

**Role:** Full-Stack + AI Engineer (2–3 YOE)
**Time allowed:** up to 1 week from receipt (most candidates spend 4–6 focused days; see milestones)
**Submission:** Git repository (zipped) + completed [`docs/design.md`](docs/design.md) + an `AGENTS.md` at the repo root

Operational instructions (Docker, smoke tests, repo layout) are in **[README.md](README.md)**.

---

## Background

Medical billing records arrive as PDFs. Hospitals, clinics, pharmacies, and billing
departments produce them in a wide variety of formats: structured tables, scanned
documents, multi-provider bundles, pharmacy ledgers with embedded software screenshots.
They are rarely clean.

In litigation and insurance dispute contexts, extracting structured billing data from
these documents is a prerequisite for every downstream analysis. The output is consumed by
attorneys and paralegals who need accurate financial summaries tied to exact source
citations. A silent error (wrong amount, wrong provider, a missed adjustment) has real
consequences.

This is a multi-user product. Different attorneys and paralegals log in, upload their own
documents, and must see only their own jobs and results. That isolation is a hard
data-security boundary, and it has to hold at the database layer even when the application
code has a bug.

Your task is to build a full-stack platform: an authenticated web application where a
logged-in user uploads medical billing PDFs, the system processes them asynchronously
through an extraction agent, and the user sees structured results scoped strictly to their
own account.

Read [`docs/domain.md`](docs/domain.md) and [`docs/schema.md`](docs/schema.md) before
writing extraction code. The domain has specific rules about what to extract, what to leave
blank, and when to flag for review.

---

## Build to your own judgment

> The starter code is scaffolding, not a finished design. Restructure it, replace it, throw
> parts away, do whatever serves the product you think should exist. We care much more about
> how you think, both technically and as a product thinker, than about whether you stayed
> inside the lines we drew. If you see a better data model, a better flow, a better UX, or a
> sharper way to surface uncertainty to the attorney who relies on it, build that and tell
> us why in the design doc.
>
> A few things are firm, because they are the point of the exercise: per-user isolation
> enforced by RLS in the database (M1/M2), Better Auth and Next.js for the web layer, the
> whole stack coming up via `docker compose up`, and the [API contract](#api-contract)
> staying intact. Everything else is yours to shape. Treat the gaps and rough edges as room
> to exercise judgment rather than a spec to satisfy literally.

---

## What You Are Building

A full-stack system that comes up with a single `docker compose up`. It has four parts:

- A **Next.js web frontend** where a user signs up, signs in, uploads PDFs, and views their
  own jobs and extracted results. This is the primary client a user touches.
- **Better Auth** for session management, with auth issuance living in the Next.js app.
  Email/password is fine; add another method if you want.
- A **Python/FastAPI API and async worker** (the existing stack) that accepts uploads,
  manages the job lifecycle, runs the extraction agent, and persists results. Compose runs
  two worker instances by default, so your claiming logic has to be safe under concurrent
  access.
- **Postgres with Row-Level Security**, storing users, jobs, and extraction results.
  Per-user isolation is enforced by RLS policies in the database, not only by
  `WHERE user_id = ...` clauses in application code.

PDFs live on a shared volume mounted into the API and worker containers.

> **You choose the topology**: who owns the session, how the Python API learns the identity
> of the caller, and how the background worker establishes the correct database identity
> when it writes a result. There is no single right answer, but pick one deliberately and
> document and defend it in `docs/design.md`. A muddy or unstated topology is the most
> common way this assignment goes wrong.

---

## Milestones

The assignment is structured as vertical slices. Each milestone is thin but end-to-end,
running from the frontend through auth and the backend down to the database. Complete them
in order. A smaller system that fully works through M2 beats a sprawling one that works
nowhere.

### M1 — Authentication + isolation spine (REQUIRED CORE)

A user can sign up and sign in through the Next.js app (Better Auth). Once signed in, they
land on a protected page that reads user-scoped data from Postgres with RLS enabled. An
unauthenticated request gets nothing. The whole stack, frontend through Postgres, comes up
on `docker compose up`.

This milestone proves you understand the auth-to-backend-to-RLS chain end to end, and it is
the heart of the assignment. RLS faked with application-layer filtering does not meet it
(see *The Isolation Guarantee* below).

### M2 — Extraction behind auth (REQUIRED CORE)

A signed-in user uploads a PDF from the frontend, and a job is created owned by that user.
The worker picks it up safely under two concurrent workers, runs the extraction agent, and
writes the result. The user sees the job and its result in the UI, and only the owner can
read it, enforced by RLS.

The interesting sub-problem: the background worker runs outside any HTTP request and has no
session. Under whose database identity does it write the result, and how do you keep that
safe? Solve this in code, not just in prose.

### M3 — Reliability backend (STRETCH — graded extra)

Harden the job queue: bounded retries with backoff on transient failures, crash recovery
for jobs stuck in `processing`, content-based result caching with a bypass flag, and a live
`/jobs/active` view. Full requirements are in *Job Lifecycle & Reliability* below. Do as
much as time allows, and document what you did and did not get to.

### M4 — Frontend experience (STRETCH — working-knowledge bar)

A usable dashboard that lists jobs with status, shows a completed extraction, and surfaces
flagged or uncertain records clearly. We are checking for working knowledge of frontend,
not design polish. Clean, legible, and functional beats elaborate. (See *Frontend
Expectations*.)

---

## The Backend Lever: auth, backend, RLS

This is one of our two primary axes (the other is your AI and agent design), and the one we
drill hardest on the debrief. Read this section carefully.

### The Isolation Guarantee

Per-user isolation must be enforced by Postgres Row-Level Security, rather than by trusting
application code to always add the right filter. The test we apply is blunt:

> Signed in as user A, ask for user B's job by its exact ID, both against your API and
> against the database directly as the role your app connects with. You must get nothing. If
> a forgotten or wrong `WHERE` clause anywhere in the stack would leak B's data, you have
> not met the bar.

Concretely: the application connects to Postgres as a role that is subject to RLS (not the
table owner, not a `BYPASSRLS` superuser), RLS policies are defined on every user-owned
table, and the current user's identity is propagated into the database session so the
policies can act on it.

### State and defend your topology

In `docs/design.md`, walk through, at the code level:

- Where the session is created and validated, and how the Python API learns which
  authenticated user a request belongs to (a shared session token, a verified JWT, a shared
  session table, something else).
- How the user's identity reaches the database session so RLS policies can use it, for
  example a `SET LOCAL` of a setting the policy reads via `current_setting(...)`. Cover how
  that interacts with connection pooling: what happens to a session-scoped setting under a
  transaction-pooled connection? Get this wrong and isolation leaks silently.
- How the background worker, which has no request and no session, establishes the correct
  identity before writing a result for a given job.

### What you build now vs. what we explore live

For this submission, user-level isolation is the requirement. You do not need to build
multi-tenancy or sharing. On the debrief call we will ask you to extend your own design,
live, in your editor:

- How would you move from user-level to tenant-level isolation (an org with many users)?
- How would you then allow cross-tenant sharing of a specific document, at the RLS level,
  without weakening the default-deny boundary?
- How would you turn the single-queue worker into a multi-worker, workflow-based system
  across several machines or regions, and how would the user/tenant identity travel to a
  detached worker there?

If you let a tool write your RLS without understanding it, these questions will surface that
within a few minutes, which is intentional. We expect you to use AI. What we are checking is
whether you understand what it produced well enough to change it.

---

## API Contract

Your Python API must expose these endpoints. Do not rename or remove them. All `/jobs`
routes operate in the authenticated caller's context and return only that caller's data,
enforced by RLS. `/health` is public.

```
POST   /jobs
       Body: multipart/form-data with a PDF file
       Auth: required. The created job is owned by the authenticated user.
       Optional: a flag (header or query parameter, your choice of name and mechanism)
                 to bypass result caching for this upload.

       If the uploaded file's content matches a previously completed extraction
       OWNED BY THE SAME USER, the API may return a new job record immediately in
       completed status, reusing the cached result rather than reprocessing. The
       file name is irrelevant to this comparison; only file content matters. How you
       detect content equivalence, where you store the fingerprint, and how caching
       interacts with per-user isolation are your design decisions; document them.

       When caching is bypassed, always create a fresh job and run full extraction.

       Returns: same job envelope as GET /jobs/{job_id} (see docs/schema.md); metrics
       fields start as JSON null until the worker finishes (or are populated
       immediately on a cache hit).

GET    /jobs
       Returns the authenticated user's jobs with their current status.
       Supports optional query param: ?status=pending|processing|completed|failed

GET    /jobs/active
       Returns the authenticated user's jobs currently being processed, as a list.
       Empty list if none. Must always reflect live state; do not cache it.

GET    /jobs/{job_id}
       Returns full job detail (including extraction result if completed) for a job
       the caller owns. A job owned by another user must be indistinguishable from a
       job that does not exist.

DELETE /jobs/{job_id}
       Cancels a pending job the caller owns before a worker picks it up.
       Must return 409 if the job is already processing or completed.

GET    /health
       Public. Returns: { "status": "ok", "db": "ok" }
       Checks live database connectivity on every call.
```

**Job metrics (required on M2+).** Each job persists and returns these three fields on every
response that includes a job payload. Use JSON `null` for fields not yet known; for `failed`
jobs, populate what you can.

| Field | What to capture |
|---|---|
| `token_usage` | LLM token counts, broken out into at least `input`, `output`, and `total`. |
| `cost_usd` | Estimated API spend in USD for that job, based on documented pricing assumptions. |
| `processing_duration_seconds` | Wall-clock time from when the worker starts the job through its terminal state. |

We no longer enforce hard cost or latency targets (see *Extraction Quality* below), but we
still want these measured and surfaced. They are a window into how you think about the
agent.

---

## Job Lifecycle & Reliability (M3)

```
pending → processing → completed
                    ↘ failed
pending → cancelled
```

A job that transitions to `processing` must never silently go back to `pending`. If the
worker crashes mid-job, the system has to recover it. Think about how, and document when
recovery triggers.

**Concurrency.** Two workers run by default. Walk through, in the design doc, the exact
mechanism that guarantees two workers never claim the same job, and what would break if you
removed it.

**Retries.** Transient failures (timeouts, rate limits, intermittent API errors) should not
flip a job straight to `failed`. Retry up to a bounded number of times; you choose *n*,
backoff, and what counts as retryable (document it). Once retries are exhausted, end in
`failed` with error detail explaining what was tried.

**Caching.** Content-based result caching with a bypass flag, scoped correctly to the
isolation model so that a cache hit never crosses the user boundary. Document the
fingerprinting approach and its failure modes.

These are stretch relative to M1/M2, but they are real backend signal and a strong
submission gets through most of them.

---

## Extraction Quality (secondary signal)

Extraction still matters. A platform that isolates users perfectly but extracts garbage is
not useful. But it is no longer the dominant axis, and there are no hard cost or latency
targets this round. Build the best extraction you reasonably can within the timeframe, and
be honest in the design doc about where it falls short.

We will still run your system against a held-out set of documents you have not seen, scored
field-level against ground truth, but it counts as one input among several rather than the
single deciding score.

### Field weights (`BillingRecord`)

| Field | Weight |
|---|---|
| `treatment_date` | High |
| `cpt_codes` | High |
| `total_charges` | High |
| `ins_paid` | High |
| `adjustment` | High |
| `payments` | High |
| `balance` | High |
| `provider` | Medium |
| `page` | Medium |
| `insurers` | Medium |
| `third_parties` | Medium |
| `description` | Low |

High weight covers dates, procedure codes, and every amount column. Medium covers identity
and citation fields. Low covers short text that may be phrased differently while still
correct.

### Flagging rubric (unchanged, and still important)

When part of an episode is unreliable, that has to be visible in one of two ways: as correct
values in `records`, or as an honest `flagged` row whose `fields` (and `row`, when it
applies) identify what was uncertain. A confident but wrong `records` row is the failure
mode to avoid.

Flagged uncertain records are not penalized. A record marked uncertain and skipped scores
better than a confident wrong value. The opposite failure mode counts too: flagging almost
everything reads as avoiding extraction rather than exercising judgment. Most rows on a
typical document should land in `records` with defensible values, with `flagged` reserved
for genuine ambiguity.

### Do the homework

A strong extraction starts with a careful read of [`docs/domain.md`](docs/domain.md) and a
manual pass over every provided sample PDF next to its ground-truth file. If you cannot
label the samples correctly with the schema in front of you, a model will not do it reliably
either. The LLM amplifies a specification you already understand.

---

## Frontend Expectations

The bar is working knowledge of frontend, not design mastery. We want to see a clean,
legible, functional UI that lets a user sign in, upload, and read results.

- A functional, isolation-correct UI beats an elaborate one. A pretty dashboard that leaks
  another user's data fails the test that matters here.
- Taste is a small bonus rather than a requirement. A screen that looks like an untouched
  default template is a minor note; thoughtful, non-generic UI is a minor plus.
- Feel free to use AI design tooling (for example Claude's `design` or `impeccable.style`
  skills) to help. Using it well is in the spirit of the role.

We will not reject a strong backend submission over imperfect styling.

---

## Constraints

**Required stack choices.** Next.js (frontend), Better Auth (authentication), the provided
Python/FastAPI worker stack (extraction backend), and Postgres with RLS for isolation.
Beyond these, choose libraries deliberately and justify them briefly in the design doc.

**No high-level LLM orchestration frameworks.** LangChain, LlamaIndex, CrewAI, AutoGen, and
similar are out. The OpenAI Agents SDK is encouraged for the tool-calling loop, and calling
model APIs directly is also fine. State management, handoffs, and orchestration (what
persists across steps, how control passes, what each stage receives) must be your own code
and your own design, rather than delegated to a framework that hides those choices.

**Understand what the model sees on every turn.** Be able to describe what enters the agent
context window at each step: system instructions, tools, messages, retrieval, and why.

**Docker Compose is required.** The submitted repository has to come up and be usable via
`docker compose up`: frontend, auth, API, worker, Postgres. For evaluation we run the stack
exactly this way and exercise it through the UI and the HTTP API. If it does not start
cleanly, the affected milestones score zero regardless of code quality.

**Version control is required.** The starter ships as a git repository. Commit your work
incrementally as you build, in small coherent commits with honest messages, and submit with
the `.git/` history intact (no squashing to a single commit, no re-init). We read the commit
history as part of understanding how you work, and it is the cleanest signal that the system
grew from your own iteration. A repo that arrives as one giant "final" commit is a red flag.

**AI usage is expected.** The point is not that you avoid AI; it is that the system reflects
your own understanding. If you cannot explain a design decision at the code level on the
debrief call, it should not be in your submission.

---

## How We Evaluate

Backend depth and AI are the two primary axes, weighted most heavily. The rest follow,
roughly in order of weight:

1. **Backend depth (auth, backend, RLS) — primary.** Is isolation truly DB-enforced? Is the
   topology coherent and defensible? Does the worker handle identity correctly?
2. **AI: agent and tool design, and extraction — primary.** What tools you gave the agent and
   why; how it navigates an unseen document, handles tables that split across pages, and
   signals uncertainty; and the field-level accuracy and flagging it produces on the held-out
   set. The accuracy number is one input among several, but the quality and judgment of your
   agent and tool design is weighted high.
3. **Code quality and maintainability.** Clean separation of API, service, and data-access
   layers; explicit state with no global mutable objects; meaningful errors; tests for the
   core logic and at least one end-to-end lifecycle test that includes an unhappy path; and
   a useful root `AGENTS.md` (see below).
4. **Full-stack runnability.** Clone, `docker compose up`, sign up, upload, see your result,
   seamlessly and with no guesswork.
5. **Frontend.** Working knowledge, per above.
6. **Design document.** Hand-written, precise, defensible.

### The debrief is part of the evaluation

You will walk us through your repository live, in your editor. Expect to explain why the
system works the way it does and to make changes to it on the spot. The submission earns the
call, and the call is where we tell apart someone who understands the system from someone who
pasted what a tool produced. Know your codebase well enough to defend and extend any part of
it.

### `AGENTS.md` (required)

Include a root `AGENTS.md` documenting how an AI coding agent should work in your repo:
project layout, how to run and test, conventions, and the workflow you actually used to
build and ship fast. We read it as evidence of how you operate in an AI-native codebase.

### Paxel report

Share a **[Paxel](https://paxel.ycombinator.com/)** report for this project. This is how we
understand the way you used AI to build, in place of asking you to write it up yourself. Run
Paxel over your sessions for this project and paste the report URL into `docs/design.md`
(there is a field for it). It runs locally and shares only a derived profile of your working
style.

---

## Provided Starter Repo

Approximate layout (see **README.md** for an up-to-date tree):

```
README.md                   # how to run + smoke-test the whole stack
ASSIGNMENT.md               # this specification
docker-compose.yml          # whole stack: Postgres, API, worker (+ your web service)
.env.example                # required environment variables
docs/
  domain.md                 # medical billing domain reference — read this first
  schema.md                 # output schema and field definitions
  design.md                 # template for your design document
backend/                    # Python API + worker (provided, stubbed)
  app/                      # FastAPI, services, DAOs, AI pipeline (stubbed where noted)
  alembic/                  # migrations — DB owned by Alembic
  scripts/migrate.sh        # runs migrations before the API process
  Dockerfile                # uv sync-based image (Python 3.12 + .venv)
  main.py / worker.py       # entrypoints
frontend/                   # YOU BUILD THIS — Next.js + Better Auth (placeholder README)
data/                       # sample PDFs + ground truth (when shipped; git-ignored)
```

The `frontend/` directory is a placeholder. The Next.js frontend and Better Auth
integration are yours to add there. Wire a `web` service into the repo-root
`docker-compose.yml` (a commented skeleton is provided) so the whole stack still comes up
with one command.

Sample PDFs and ground truth may ship under `data/sample/` and `data/ground_truth/`.

### On the boilerplate

`docker compose up` brings up Postgres, migrates via the API container entrypoint, starts
Uvicorn, and starts the worker once the API is healthy. A minimal `echo` agent under
`backend/app/ai/` demonstrates prompts, tools, and `Runner.run` as a pattern, not the
solution. Service and DAO layers include `NotImplementedError` stubs for job lifecycle,
extraction persistence, and worker claiming. Everything beyond that baseline is yours.

---

## Deliverables

Resubmit this repository as your finished assignment:

- Full-stack implementation: Next.js and Better Auth frontend, Python API and worker,
  Postgres with RLS, meeting M1 and M2 plus as much of M3/M4 as time allowed.
- Tests: core extraction logic plus at least one end-to-end lifecycle test with an unhappy
  path.
- Filled-in **`docs/design.md`** (hand-written), including the topology and RLS sections
  above and an honest accuracy/failure analysis.
- Root **`AGENTS.md`**.
- Alembic migrations for any schema you add, including RLS policies.
- **`docker-compose.yml`**, **`Dockerfile`**(s), and **`.env.example`** that run cleanly
  together.
- A **`README.md`** that gets a reviewer from clone to `docker compose up` to signed-in and
  uploading, with no guesswork.
- The repository with its `.git/` history, showing incremental commits across your work
  rather than a single squashed commit.

The bar is simple: run **`docker compose up`**, then sign up, upload a PDF, and see an
isolated result, with no guesswork.
