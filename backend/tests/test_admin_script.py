"""The operator escape hatch.

`scripts/create_admin.py` is the only way to obtain an administrator once password
registration is disabled, which is the default. If it breaks, a fresh deployment has no
route to its own admin panel, so it is tested like a feature rather than a convenience.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.models import Role, User

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "create_admin.py"


def load_script():
    """Imported by path because `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("create_admin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run(monkeypatch):
    module = load_script()

    def invoke(*args: str, password: str | None = None) -> int:
        monkeypatch.setattr(sys, "argv", ["create_admin.py", *args])
        if password is None:
            monkeypatch.delenv(module.PASSWORD_ENV, raising=False)
        else:
            monkeypatch.setenv(module.PASSWORD_ENV, password)
        return module.main()

    return invoke


@pytest.fixture
def address() -> str:
    return f"operator-{os.urandom(4).hex()}@starcode-test.org"


def fetch(db: Session, email: str) -> User | None:
    db.expire_all()
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def test_creates_an_admin_that_can_actually_sign_in(run, db, client, address):
    assert run("--email", address, "--name", "Owner", password="a-properly-long-passphrase") == 0

    user = fetch(db, address)
    assert user is not None
    assert user.role is Role.ADMIN
    assert user.is_active
    # An address the operator set on their own deployment has nothing to confirm.
    assert user.email_verified

    response = client.post(
        "/api/v1/auth/login",
        json={"email": address, "password": "a-properly-long-passphrase"},
    )
    assert response.status_code == 200, response.text

    token = response.json()["access_token"]
    admin_view = client.get("/api/v1/admin/system", headers={"Authorization": f"Bearer {token}"})
    assert admin_view.status_code == 200


def test_registration_stays_disabled_for_everyone_else(run, client, address):
    """Creating an admin out of band must not open the front door."""
    assert run("--email", address, password="a-properly-long-passphrase") == 0

    refused = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"someone-else-{os.urandom(3).hex()}@starcode-test.org",
            "password": "a-properly-long-passphrase",
        },
    )
    assert refused.status_code == 403


def test_email_is_normalised_so_a_second_run_does_not_duplicate(run, db, address):
    assert run("--email", address.upper(), password="a-properly-long-passphrase") == 0
    assert fetch(db, address) is not None

    assert run("--email", address, "--role", "moderator") == 0
    matches = db.execute(select(User).where(User.email == address)).scalars().all()
    assert len(matches) == 1


def test_a_rerun_changes_the_role_without_touching_the_password(run, db, address):
    assert run("--email", address, password="a-properly-long-passphrase") == 0
    original = fetch(db, address).hashed_password

    # No password supplied and no terminal to prompt on: this must still succeed, because
    # changing someone's role should never be a reason to change their credential.
    assert run("--email", address, "--role", "moderator") == 0

    user = fetch(db, address)
    assert user.role is Role.MODERATOR
    assert user.hashed_password == original


def test_reset_password_is_the_recovery_path_for_a_locked_out_operator(run, db, address):
    assert run("--email", address, password="the-original-passphrase") == 0

    assert run("--email", address, "--reset-password", password="a-replacement-passphrase") == 0

    user = fetch(db, address)
    assert verify_password("a-replacement-passphrase", user.hashed_password)
    assert not verify_password("the-original-passphrase", user.hashed_password)
    assert user.role is Role.ADMIN


def test_a_weak_password_is_refused_rather_than_stored(run, db, address):
    with pytest.raises(SystemExit):
        run("--email", address, password="short")
    assert fetch(db, address) is None


def test_it_refuses_to_guess_when_there_is_no_password_and_no_terminal(
    run, db, address, monkeypatch
):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit):
        run("--email", address)
    assert fetch(db, address) is None
