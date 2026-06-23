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
