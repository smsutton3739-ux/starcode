#!/usr/bin/env python3
"""Create or promote an administrator.

Password registration is disabled by default (`ALLOW_PASSWORD_REGISTRATION`), because
there is no reset flow and an unrecoverable credential is worse than none. That leaves
no way to obtain the first admin account through the API, which is what this script is
for: an operator with shell access to the deployment, running it once.

    python3 scripts/create_admin.py --email you@example.com

The password is read from the terminal without echoing it, or from `STARCODE_ADMIN_PASSWORD`
for unattended provisioning. It is never taken from a command-line argument, because
argv is visible to every process on the host and lands in shell history.

Re-running it against an existing address promotes that account and, with
`--reset-password`, sets a new password — which is also the intended recovery path for a
locked-out operator.

Run it from `backend/`, with the same environment the API uses, so it talks to the same
database.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

# Python puts the *script's* directory on the path, not the working directory, so `app`
# is not importable without this. Prepended so `python3 scripts/create_admin.py` works
# from `backend/` without an editable install or a PYTHONPATH incantation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402 - after the path bootstrap above

from app.core.security import hash_password, validate_password_strength  # noqa: E402
from app.db.models.user import Role, User, UserSetting  # noqa: E402
from app.db.session import session_scope  # noqa: E402

PASSWORD_ENV = "STARCODE_ADMIN_PASSWORD"  # noqa: S105 - the name of a variable, not a secret


def read_password(*, confirm: bool) -> str:
    """From the environment for unattended runs, otherwise from the terminal."""
    from_env = os.environ.get(PASSWORD_ENV)
    if from_env:
        return from_env

    if not sys.stdin.isatty():
        raise SystemExit(
            f"No terminal to prompt on. Set {PASSWORD_ENV} for unattended provisioning."
        )

    password = getpass.getpass("Password (at least 12 characters): ")
    if confirm and password != getpass.getpass("Again: "):
        raise SystemExit("The two entries did not match.")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default=None, help="Display name for a new account.")
    parser.add_argument(
        "--role",
        default=Role.ADMIN.value,
        choices=[r.value for r in Role],
        help="Defaults to admin. Lower roles are accepted so this can also fix a mistake.",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Set a new password on an account that already exists.",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    role = Role(args.role)

    with session_scope() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

        if user is not None and not args.reset_password:
            # Promotion only. Not prompting for a password here is deliberate: changing
            # someone's credential should never be a side effect of changing their role.
            was = user.role
            user.role = role
            user.is_active = True
            print(
                f"{email}: role {was.value} → {role.value}"
                if was != role
                else f"{email}: already {role.value}"
            )
            return 0

        password = read_password(confirm=user is None)
        problems = validate_password_strength(password)
        if problems:
            raise SystemExit(" ".join(problems))

        if user is None:
            user = User(
                email=email,
                display_name=args.name,
                hashed_password=hash_password(password),
                role=role,
                is_active=True,
                # Set by an operator who owns the deployment, not by an unverified
                # visitor, so there is no address to confirm.
                email_verified=True,
            )
            user.settings = UserSetting()
            db.add(user)
            print(f"{email}: created with role {role.value}")
        else:
            user.hashed_password = hash_password(password)
            user.role = role
            user.is_active = True
            print(f"{email}: password reset, role {role.value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
