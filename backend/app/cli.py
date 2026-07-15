"""Small management CLI for the backend.

Usage (inside the backend container / venv):

    python -m app.cli ensure-admin
    python -m app.cli create-admin --email a@b.com --password secret123 --name "Jane"

``ensure-admin`` is idempotent — it creates the bootstrap admin from environment
settings only if that email does not already exist. It is run automatically by
the backend container on startup.
"""

import argparse
import asyncio
import secrets
import sys

from app.config import settings
from app.db.models.constants import UserRole
from app.db.session import AsyncSessionLocal
from app.services import users as user_service


async def _ensure_admin(email: str, password: str, name: str) -> int:
    async with AsyncSessionLocal() as db:
        existing = await user_service.get_by_email(db, email)
        if existing is not None:
            print(f"[cli] admin '{email}' already exists (id={existing.id}); nothing to do")
            return 0
        user = await user_service.create_user(
            db,
            email=email,
            password=password,
            full_name=name,
            role=UserRole.admin.value,
        )
        print(f"[cli] created admin '{user.email}' (id={user.id})")
        return 0


def _generate_secret() -> int:
    print(secrets.token_hex(32))
    return 0


def _prod_check() -> int:
    """Report insecure configuration for a production deployment."""
    problems = settings.insecure_production_defaults()
    if not problems:
        print("[cli] production configuration looks good ✓")
        return 0
    print("[cli] insecure configuration for production:")
    for p in problems:
        print(f"  - {p}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ensure-admin", help="Create the bootstrap admin if it does not exist")

    create = sub.add_parser("create-admin", help="Create an admin with explicit values")
    create.add_argument("--email", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--name", default="Administrator")

    sub.add_parser("generate-secret", help="Print a strong random SECRET_KEY (hex)")
    sub.add_parser("prod-check", help="Fail if the config has insecure production defaults")

    args = parser.parse_args(argv)

    if args.command == "ensure-admin":
        return asyncio.run(
            _ensure_admin(
                settings.bootstrap_admin_email,
                settings.bootstrap_admin_password,
                settings.bootstrap_admin_name,
            )
        )
    if args.command == "create-admin":
        return asyncio.run(_ensure_admin(args.email, args.password, args.name))
    if args.command == "generate-secret":
        return _generate_secret()
    if args.command == "prod-check":
        return _prod_check()
    return 1


if __name__ == "__main__":
    sys.exit(main())
