"""Local administrative CLI for user provisioning and legacy profile claims."""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
import uuid
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from app.auth.exceptions import AuthError
from app.auth.service import AuthService
from app.database.session import SessionLocal
from app.profile.exceptions import ProfileEngineError

logger = logging.getLogger(__name__)


def _prompt_password() -> str:
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise AuthError("passwords do not match")
    return password


def _prompt_claim_confirmation(profile_id: uuid.UUID, email: str) -> bool:
    answer = input(f"Assign legacy profile {profile_id} to {email}? [y/N]: ")
    return answer.strip().casefold() in {"y", "yes"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="VagaNexo local administration CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_user_parser = subparsers.add_parser(
        "create-user",
        help="Create a new user account (prompts interactively for password)",
    )
    create_user_parser.add_argument("--email", required=True, help="User email address")
    create_user_parser.add_argument(
        "--inactive",
        action="store_true",
        help="Provision the user as inactive",
    )
    create_user_parser.add_argument(
        "--verify-email",
        action="store_true",
        help="Mark the provisioned user's email address as verified",
    )

    claim_parser = subparsers.add_parser(
        "claim-profile",
        help="Assign an unowned legacy candidate profile to an existing user",
    )
    claim_parser.add_argument("--profile-id", required=True, help="Legacy profile UUID")
    claim_parser.add_argument("--email", required=True, help="Target user email address")

    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    session: Session | None = None,
    password_prompt: Callable[[], str] = _prompt_password,
    confirm_prompt: Callable[[uuid.UUID, str], bool] = _prompt_claim_confirmation,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    owns_session = session is None
    db = session if session is not None else SessionLocal()
    try:
        auth_service = AuthService(db)
        if args.command == "create-user":
            password = password_prompt()
            user = auth_service.create_user(
                email=args.email,
                password=password,
                is_active=not args.inactive,
                verify_email=args.verify_email,
            )
            print(f"Created user {user.id} ({user.email}) active={user.is_active}")
            return 0

        if args.command == "claim-profile":
            try:
                profile_id = uuid.UUID(args.profile_id)
            except ValueError:
                print("Error: --profile-id must be a valid UUID", file=sys.stderr)
                return 2
            if not confirm_prompt(profile_id, args.email):
                print("Aborted.")
                return 1
            profile = auth_service.claim_profile(profile_id=profile_id, email=args.email)
            print(f"Assigned profile {profile.id} to user {profile.user_id}")
            return 0

        return 2
    except (AuthError, ProfileEngineError) as exc:
        print(f"Error: {exc.detail}", file=sys.stderr)
        return 1
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    raise SystemExit(run_cli())
