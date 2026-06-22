"""The isolation guarantee, tested where it has to hold: in the database, as the
exact role the application connects with.

The bar from ASSIGNMENT.md: signed in as user A, ask for user B's job by its
exact id — you must get nothing. These tests do that with no application-layer
WHERE clause at all, so they prove RLS (not app code) is the enforcer.
"""

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _set_identity(conn, user_id):
    if user_id is not None:
        await conn.execute(
            text("SELECT set_config('app.user_id', :u, true)"), {"u": user_id}
        )


async def _insert_job_as_admin(admin_engine, owner_id, job_id):
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, status) "
                "VALUES (:id, :owner, 'doc.pdf', '/app/pdfs/doc.pdf', 'pending')"
            ),
            {"id": job_id, "owner": owner_id},
        )


async def test_app_role_is_subject_to_rls(app_engine):
    """The connecting role must not be superuser or BYPASSRLS — otherwise RLS is
    decorative."""
    async with app_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            )
        ).first()
    assert row.rolsuper is False
    assert row.rolbypassrls is False


async def test_user_a_cannot_read_user_b_job_by_id(app_engine, admin_engine, two_users):
    alice, bob = two_users
    job_id = f"job-{uuid.uuid4().hex}"
    await _insert_job_as_admin(admin_engine, bob, job_id)

    # As Alice: Bob's job by its exact id is invisible, and absent from a full scan.
    async with app_engine.connect() as conn:
        async with conn.begin():
            await _set_identity(conn, alice)
            by_id = (
                await conn.execute(text("SELECT id FROM jobs WHERE id = :id"), {"id": job_id})
            ).first()
            assert by_id is None
            all_ids = [
                r.id for r in (await conn.execute(text("SELECT id FROM jobs"))).fetchall()
            ]
            assert job_id not in all_ids

    # As Bob: the same job is visible.
    async with app_engine.connect() as conn:
        async with conn.begin():
            await _set_identity(conn, bob)
            by_id = (
                await conn.execute(text("SELECT id FROM jobs WHERE id = :id"), {"id": job_id})
            ).first()
            assert by_id is not None


async def test_no_identity_is_default_deny(app_engine, admin_engine, two_users):
    _, bob = two_users
    job_id = f"job-{uuid.uuid4().hex}"
    await _insert_job_as_admin(admin_engine, bob, job_id)

    # No app.user_id set at all: the policy's USING clause is NULL -> deny.
    async with app_engine.connect() as conn:
        async with conn.begin():
            rows = (await conn.execute(text("SELECT id FROM jobs"))).fetchall()
            assert rows == []


async def test_with_check_blocks_inserting_for_another_user(app_engine, two_users):
    alice, bob = two_users
    async with app_engine.connect() as conn:
        async with conn.begin():
            await _set_identity(conn, alice)
            # Alice tries to create a job owned by Bob — WITH CHECK must reject it.
            with pytest.raises(Exception):
                await conn.execute(
                    text(
                        "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, status) "
                        "VALUES (:id, :owner, 'x.pdf', '/p', 'pending')"
                    ),
                    {"id": f"job-{uuid.uuid4().hex}", "owner": bob},
                )


async def test_user_can_insert_and_read_own_job(app_engine, two_users):
    alice, _ = two_users
    job_id = f"job-{uuid.uuid4().hex}"
    async with app_engine.connect() as conn:
        async with conn.begin():
            await _set_identity(conn, alice)
            await conn.execute(
                text(
                    "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, status) "
                    "VALUES (:id, :owner, 'x.pdf', '/p', 'pending')"
                ),
                {"id": job_id, "owner": alice},
            )
            found = (
                await conn.execute(text("SELECT owner_id FROM jobs WHERE id = :id"), {"id": job_id})
            ).first()
            assert found is not None
            assert found.owner_id == alice
