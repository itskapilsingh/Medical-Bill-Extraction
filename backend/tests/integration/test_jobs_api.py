"""End-to-end job lifecycle through the real HTTP stack: auth dependency →
service → DAO → Postgres with RLS. Covers the happy path and several unhappy
paths (no auth, bad token, cross-user access, double-cancel conflict).

Runs the FastAPI app in-process via httpx's ASGI transport, driving the same
auth path a real request takes: a Bearer session token validated against the
shared session table.
"""

import os
import tempfile
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

# Point uploads at a writable temp dir before the app reads settings.
os.environ["PDF_MOUNT_PATH"] = tempfile.mkdtemp(prefix="pdfs-test-")

pytestmark = pytest.mark.asyncio

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest_asyncio.fixture
async def sessions(admin_engine, two_users):
    """Seed a valid session token for each user; cascades away with the users."""
    alice, bob = two_users
    tok_a = f"tok-{uuid.uuid4().hex}"
    tok_b = f"tok-{uuid.uuid4().hex}"
    async with admin_engine.begin() as conn:
        for uid, tok in ((alice, tok_a), (bob, tok_b)):
            await conn.execute(
                text(
                    'INSERT INTO "session" (id, "expiresAt", token, "userId") '
                    "VALUES (:id, now() + interval '1 day', :tok, :uid)"
                ),
                {"id": f"sess-{uuid.uuid4().hex}", "tok": tok, "uid": uid},
            )
    return {"alice_token": tok_a, "bob_token": tok_b}


async def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


def _load_app():
    from app.config.settings import get_settings

    get_settings.cache_clear()
    from app.api.main import app

    return app


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_unauthenticated_requests_are_rejected(sessions):
    app = _load_app()
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            assert (await client.get("/jobs")).status_code == 401
            assert (
                await client.get("/jobs", headers=_auth("not-a-real-token"))
            ).status_code == 401


async def test_full_job_lifecycle(sessions):
    app = _load_app()
    headers = _auth(sessions["alice_token"])
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            # Create
            created = await client.post(
                "/jobs",
                headers=headers,
                files={"file": ("bill.pdf", PDF_BYTES, "application/pdf")},
            )
            assert created.status_code == 201, created.text
            job = created.json()
            job_id = job["job_id"]
            assert job["status"] == "pending"
            assert job["token_usage"] is None  # not processed yet

            # List + active
            listed = (await client.get("/jobs", headers=headers)).json()
            assert any(j["job_id"] == job_id for j in listed)

            # Get one
            got = await client.get(f"/jobs/{job_id}", headers=headers)
            assert got.status_code == 200
            assert got.json()["job_id"] == job_id

            # Cancel (pending -> cancelled)
            cancelled = await client.delete(f"/jobs/{job_id}", headers=headers)
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"

            # Cancel again -> 409 (no longer pending)
            again = await client.delete(f"/jobs/{job_id}", headers=headers)
            assert again.status_code == 409


async def test_one_user_cannot_see_anothers_job(sessions):
    app = _load_app()
    alice = _auth(sessions["alice_token"])
    bob = _auth(sessions["bob_token"])
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            created = await client.post(
                "/jobs",
                headers=alice,
                files={"file": ("bill.pdf", PDF_BYTES, "application/pdf")},
            )
            job_id = created.json()["job_id"]

            # Bob asks for Alice's job by exact id -> 404, indistinguishable from
            # a job that doesn't exist.
            assert (await client.get(f"/jobs/{job_id}", headers=bob)).status_code == 404
            # And it never shows up in Bob's list.
            bob_jobs = (await client.get("/jobs", headers=bob)).json()
            assert all(j["job_id"] != job_id for j in bob_jobs)


async def test_summary_aggregates_server_side_and_is_rls_scoped(
    sessions, admin_engine, two_users
):
    """GET /jobs/summary aggregates ALL of the caller's jobs in SQL, and never
    counts another tenant's rows (the fix for the client-side truncation bug)."""
    import json

    alice, bob = two_users

    def rec(charges, balance):
        return {
            "total_charges": charges, "ins_paid": 0, "adjustment": 0,
            "payments": 0, "balance": balance,
        }

    alice_completed = [
        {"records": [rec(100, 10), rec(200, 20)], "flagged": [{"row": 0, "reason": "x"}]},
        {"records": [rec(50, 5)], "flagged": []},
    ]
    bob_completed = {"records": [rec(999, 999)], "flagged": []}

    async with admin_engine.begin() as conn:
        for result in alice_completed:
            await conn.execute(
                text(
                    "INSERT INTO jobs (owner_id, pdf_filename, pdf_path, status, result) "
                    "VALUES (:o,'a.pdf','/p/a.pdf','completed', CAST(:r AS jsonb))"
                ),
                {"o": alice, "r": json.dumps(result)},
            )
        await conn.execute(
            text(
                "INSERT INTO jobs (owner_id, pdf_filename, pdf_path, status) "
                "VALUES (:o,'p.pdf','/p/p.pdf','pending')"
            ),
            {"o": alice},
        )
        # Bob's completed job with big numbers must NOT leak into Alice's summary.
        await conn.execute(
            text(
                "INSERT INTO jobs (owner_id, pdf_filename, pdf_path, status, result) "
                "VALUES (:o,'b.pdf','/p/b.pdf','completed', CAST(:r AS jsonb))"
            ),
            {"o": bob, "r": json.dumps(bob_completed)},
        )

    app = _load_app()
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            s = (
                await client.get("/jobs/summary", headers=_auth(sessions["alice_token"]))
            ).json()

    assert s["total"] == 3
    assert s["completed"] == 2
    assert s["pending"] == 1
    assert s["records_count"] == 3            # 2 + 1
    assert s["flagged_count"] == 1
    assert s["total_charges"] == 350.0        # 100 + 200 + 50 (Bob's 999 excluded)
    assert s["balance"] == 35.0               # 10 + 20 + 5


async def test_summary_tolerates_malformed_financial_values(
    sessions, two_users, admin_engine
):
    """A completed job whose LLM result holds non-numeric money values must not
    500 the summary: each unparseable value degrades to 0, the rest still sum
    (the guarded ::numeric cast — TEST-004)."""
    import json

    alice, _ = two_users
    result = {
        "records": [
            {"total_charges": 100, "ins_paid": 0, "adjustment": 0, "payments": 0, "balance": 10},
            # garbage string, would raise on a raw ::numeric cast
            {"total_charges": "N/A", "ins_paid": 0, "adjustment": 0, "payments": 0, "balance": "oops"},
            # "NaN"/"Infinity"-style tokens must also be treated as 0, not poison the SUM
            {"total_charges": "NaN", "ins_paid": 0, "adjustment": 0, "payments": 0, "balance": 0},
            {"total_charges": 50, "ins_paid": 0, "adjustment": 0, "payments": 0, "balance": 5},
        ],
        "flagged": [],
    }
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO jobs (owner_id, pdf_filename, pdf_path, status, result) "
                "VALUES (:o,'a.pdf','/p/a.pdf','completed', CAST(:r AS jsonb))"
            ),
            {"o": alice, "r": json.dumps(result)},
        )

    app = _load_app()
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            resp = await client.get(
                "/jobs/summary", headers=_auth(sessions["alice_token"])
            )

    assert resp.status_code == 200, resp.text
    s = resp.json()
    assert s["records_count"] == 4        # every row is still counted
    assert s["total_charges"] == 150.0    # 100 + 50; "N/A" and "NaN" -> 0
    assert s["balance"] == 15.0           # 10 + 5; "oops" -> 0


async def test_list_keyset_pagination_is_stable(sessions, two_users, admin_engine):
    """The before_created_at/before_id keyset cursor returns strictly older rows
    and is immune to a new job arriving at the head between pages (REL-004): no
    row is skipped or duplicated across the walk."""
    alice, _ = two_users
    headers = _auth(sessions["alice_token"])

    # Seed 5 jobs with distinct, strictly-decreasing created_at so newest-first
    # ordering is deterministic. ids[0] is the newest.
    ids = [f"job-{i}-{uuid.uuid4().hex}" for i in range(5)]
    async with admin_engine.begin() as conn:
        for i, jid in enumerate(ids):
            await conn.execute(
                text(
                    "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, status, "
                    "created_at) VALUES (:id, :o, 'x.pdf', '/p/x.pdf', 'pending', "
                    "now() - make_interval(secs => :s))"
                ),
                {"id": jid, "o": alice, "s": i},
            )

    app = _load_app()
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            page1 = (await client.get("/jobs?limit=2", headers=headers)).json()
            assert [j["job_id"] for j in page1] == ids[0:2]

            last = page1[-1]
            page2 = (
                await client.get(
                    "/jobs",
                    headers=headers,
                    params={
                        "limit": 2,
                        "before_created_at": last["created_at"],
                        "before_id": last["job_id"],
                    },
                )
            ).json()
            assert [j["job_id"] for j in page2] == ids[2:4]

            # A brand-new job lands at the head between pages.
            newest = f"job-new-{uuid.uuid4().hex}"
            async with admin_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, "
                        "status, created_at) VALUES (:id, :o, 'x.pdf', '/p/x.pdf', "
                        "'pending', now())"
                    ),
                    {"id": newest, "o": alice},
                )

            # The next page, cursored off page2's last row, is unaffected by the
            # head insert: it yields exactly the remaining old row.
            last2 = page2[-1]
            page3 = (
                await client.get(
                    "/jobs",
                    headers=headers,
                    params={
                        "limit": 2,
                        "before_created_at": last2["created_at"],
                        "before_id": last2["job_id"],
                    },
                )
            ).json()
            assert [j["job_id"] for j in page3] == ids[4:5]

            # The walked pages cover exactly the original five, in order — the
            # newcomer never caused a skip or a duplicate.
            assert [j["job_id"] for j in page1 + page2 + page3] == ids

            # A half-specified cursor is a client error, not a silent full scan.
            bad = await client.get(
                "/jobs", headers=headers, params={"before_id": ids[0]}
            )
            assert bad.status_code == 400


async def test_non_pdf_upload_is_rejected(sessions):
    app = _load_app()
    headers = _auth(sessions["alice_token"])
    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            resp = await client.post(
                "/jobs",
                headers=headers,
                files={"file": ("notes.pdf", b"just text, no PDF header", "application/pdf")},
            )
            assert resp.status_code == 400


async def test_per_user_upload_rate_limit_returns_429(sessions, monkeypatch):
    """A burst of uploads past the per-user budget is rejected with 429.

    Drives the whole stack — IP middleware, auth, the per-user guard, the
    exception handler — and asserts the budget is per authenticated user (Bob is
    unaffected when Alice is throttled) and the 429 carries Retry-After. The low
    budget is injected via the env var the lifespan reads when it builds the
    limiter; ``_load_app`` clears the settings cache so the override takes effect.
    """
    monkeypatch.setenv("RATE_LIMIT_USER_UPLOAD_MAX_REQUESTS", "3")
    app = _load_app()
    alice = _auth(sessions["alice_token"])
    bob = _auth(sessions["bob_token"])
    upload = {"file": ("bill.pdf", PDF_BYTES, "application/pdf")}

    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            codes = [
                (await client.post("/jobs", headers=alice, files=upload)).status_code
                for _ in range(4)
            ]
            assert codes == [201, 201, 201, 429]

            # The throttled response carries Retry-After and the error envelope.
            blocked = await client.post("/jobs", headers=alice, files=upload)
            assert blocked.status_code == 429
            assert int(blocked.headers["retry-after"]) >= 1
            body = blocked.json()
            assert body["success"] is False
            assert body["http_status"] == 429
            assert body["error"]["retry_after_seconds"] == int(blocked.headers["retry-after"])

            # The budget is per-user: Bob is untouched by Alice exhausting hers.
            bob_resp = await client.post("/jobs", headers=bob, files=upload)
            assert bob_resp.status_code == 201, bob_resp.text


async def test_active_view_and_status_filter(sessions, two_users, admin_engine):
    """GET /jobs/active returns only processing jobs; ?status filters the list."""
    app = _load_app()
    alice, _ = two_users
    headers = _auth(sessions["alice_token"])

    # Seed a processing job for alice (a worker would have claimed it).
    processing_id = f"job-{uuid.uuid4().hex}"
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, status, "
                "started_at) VALUES (:id, :o, 'p.pdf', '/p', 'processing', now())"
            ),
            {"id": processing_id, "o": alice},
        )

    async with app.router.lifespan_context(app):
        async with await _client(app) as client:
            # Create a pending job too.
            await client.post(
                "/jobs",
                headers=headers,
                files={"file": ("bill.pdf", PDF_BYTES, "application/pdf")},
            )

            active = (await client.get("/jobs/active", headers=headers)).json()
            assert any(j["job_id"] == processing_id for j in active)
            assert all(j["status"] == "processing" for j in active)

            pending = (await client.get("/jobs?status=pending", headers=headers)).json()
            assert len(pending) >= 1
            assert all(j["status"] == "pending" for j in pending)

            completed = (await client.get("/jobs?status=completed", headers=headers)).json()
            assert completed == []
