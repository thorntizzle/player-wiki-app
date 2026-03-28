from __future__ import annotations

import argparse
import getpass
from datetime import timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from player_wiki import create_app
from player_wiki.auth import validate_password_inputs
from player_wiki.auth_store import AuthStore, UserAccount, utcnow
from player_wiki.db import init_database
from player_wiki.systems_importer import Dnd5eSystemsImporter, SUPPORTED_ENTRY_TYPES

DEFAULT_DND5E_EXPORT_ROOT = Path.home() / "Documents" / "dnd5e-source-export"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local auth and campaign access for Campaign Player Wiki.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create or update the local SQLite auth schema.")

    create_admin = subparsers.add_parser("create-admin", help="Create the first active admin user.")
    create_admin.add_argument("email")
    create_admin.add_argument("display_name")
    create_admin.add_argument("--password")

    ensure_admin = subparsers.add_parser(
        "ensure-admin",
        help="Create an active admin user if it does not already exist.",
    )
    ensure_admin.add_argument("email")
    ensure_admin.add_argument("display_name")
    ensure_admin.add_argument("--password")

    invite_user = subparsers.add_parser("invite-user", help="Create an invited user and print an invite URL.")
    invite_user.add_argument("email")
    invite_user.add_argument("display_name")
    invite_user.add_argument("--admin", action="store_true", help="Grant app-wide admin access.")
    invite_user.add_argument("--actor-email")

    set_membership = subparsers.add_parser("set-membership", help="Create or update a campaign membership.")
    set_membership.add_argument("email")
    set_membership.add_argument("campaign_slug")
    set_membership.add_argument("role", choices=("dm", "player", "observer"))
    set_membership.add_argument("--status", default="active", choices=("active", "invited", "removed"))
    set_membership.add_argument("--actor-email")

    assign_character = subparsers.add_parser("assign-character", help="Assign a character owner inside a campaign.")
    assign_character.add_argument("email")
    assign_character.add_argument("campaign_slug")
    assign_character.add_argument("character_slug")
    assign_character.add_argument("--actor-email")

    disable_user = subparsers.add_parser("disable-user", help="Disable a user and revoke active sessions.")
    disable_user.add_argument("email")
    disable_user.add_argument("--actor-email")

    reset_user = subparsers.add_parser("issue-password-reset", help="Issue an admin-managed password reset URL.")
    reset_user.add_argument("email")
    reset_user.add_argument("--actor-email")

    issue_api_token = subparsers.add_parser("issue-api-token", help="Issue a bearer token for the JSON API.")
    issue_api_token.add_argument("email")
    issue_api_token.add_argument("label")
    issue_api_token.add_argument("--expires-in-days", type=int, default=365)
    issue_api_token.add_argument("--actor-email")

    list_api_tokens = subparsers.add_parser("list-api-tokens", help="List API tokens for a user.")
    list_api_tokens.add_argument("email")

    revoke_api_token = subparsers.add_parser("revoke-api-token", help="Revoke an API token by id.")
    revoke_api_token.add_argument("token_id", type=int)
    revoke_api_token.add_argument("--actor-email")

    import_systems = subparsers.add_parser(
        "import-dnd5e-source",
        help="Import DND 5E mechanics entries from a local source export into the shared systems library.",
    )
    import_systems.add_argument("source_ids", nargs="+", help="One or more source IDs, such as PHB MM XGE.")
    import_systems.add_argument(
        "--data-root",
        default=str(DEFAULT_DND5E_EXPORT_ROOT),
        help="Path to the local DND 5E source export root.",
    )
    import_systems.add_argument(
        "--entry-types",
        nargs="+",
        choices=sorted(SUPPORTED_ENTRY_TYPES),
        help="Optional subset of mechanics entry types to import.",
    )
    import_systems.add_argument("--actor-email")

    return parser


def prompt_for_password() -> str:
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    errors = validate_password_inputs(password, confirmation)
    if errors:
        raise SystemExit("\n".join(errors))
    return password


def require_user(store: AuthStore, email: str) -> UserAccount:
    user = store.get_user_by_email(email)
    if user is None:
        raise SystemExit(f"User not found: {email}")
    return user


def resolve_actor_id(store: AuthStore, actor_email: str | None) -> int | None:
    if not actor_email:
        return None

    actor = store.get_user_by_email(actor_email)
    if actor is None:
        raise SystemExit(f"Actor user not found: {actor_email}")
    return actor.id


def ensure_campaign_exists(app, campaign_slug: str) -> None:
    repository = app.extensions["repository_store"].get()
    if repository.get_campaign(campaign_slug) is None:
        raise SystemExit(f"Unknown campaign slug: {campaign_slug}")


def build_local_url(app, path: str) -> str:
    return f"{app.config['BASE_URL'].rstrip('/')}{path}"


def format_optional_timestamp(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC") if value is not None else "-"


def format_api_token_status(token) -> str:
    if token.revoked_at is not None:
        return "revoked"
    if token.expires_at is not None and token.expires_at <= utcnow():
        return "expired"
    return "active"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    app = create_app()

    with app.app_context():
        store: AuthStore = app.extensions["auth_store"]

        if args.command == "init-db":
            init_database()
            print(f"Initialized auth database at {app.config['DB_PATH']}")
            return

        init_database()

        if args.command == "create-admin":
            if store.get_user_by_email(args.email) is not None:
                raise SystemExit(f"User already exists: {args.email}")

            password = args.password or prompt_for_password()
            user = store.create_user(
                args.email,
                args.display_name,
                is_admin=True,
                status="active",
                password_hash=generate_password_hash(password),
            )
            store.write_audit_event(
                event_type="user_created",
                target_user_id=user.id,
                metadata={"is_admin": True, "source": "manage.py"},
            )
            print(f"Created admin user {user.email}")
            return

        if args.command == "ensure-admin":
            existing = store.get_user_by_email(args.email)
            if existing is not None:
                if not existing.is_admin:
                    raise SystemExit(f"User exists but is not an admin: {existing.email}")
                print(f"Admin user already exists: {existing.email}")
                return

            password = args.password or prompt_for_password()
            user = store.create_user(
                args.email,
                args.display_name,
                is_admin=True,
                status="active",
                password_hash=generate_password_hash(password),
            )
            store.write_audit_event(
                event_type="user_created",
                target_user_id=user.id,
                metadata={"is_admin": True, "source": "manage.py"},
            )
            print(f"Created admin user {user.email}")
            return

        if args.command == "invite-user":
            if store.get_user_by_email(args.email) is not None:
                raise SystemExit(f"User already exists: {args.email}")

            actor_user_id = resolve_actor_id(store, args.actor_email)
            user = store.create_user(
                args.email,
                args.display_name,
                is_admin=bool(args.admin),
                status="invited",
            )
            invite_token = store.issue_invite_token(
                user.id,
                expires_in=timedelta(hours=app.config["INVITE_TTL_HOURS"]),
                created_by_user_id=actor_user_id,
            )
            store.write_audit_event(
                event_type="user_created",
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                metadata={"is_admin": bool(args.admin), "source": "manage.py"},
            )
            store.write_audit_event(
                event_type="user_invited",
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                metadata={"source": "manage.py"},
            )
            print(f"Created invited user {user.email}")
            print(build_local_url(app, f"/invite/{invite_token}"))
            return

        if args.command == "set-membership":
            ensure_campaign_exists(app, args.campaign_slug)
            actor_user_id = resolve_actor_id(store, args.actor_email)
            user = require_user(store, args.email)
            previous = store.get_membership(user.id, args.campaign_slug, statuses=None)
            membership = store.upsert_membership(
                user.id,
                args.campaign_slug,
                role=args.role,
                status=args.status,
            )
            if previous is None or previous.status == "removed":
                event_type = "membership_created"
            elif membership.status == "removed":
                event_type = "membership_removed"
            else:
                event_type = "membership_role_changed"
            store.write_audit_event(
                event_type=event_type,
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                campaign_slug=args.campaign_slug,
                metadata={
                    "role": membership.role,
                    "status": membership.status,
                    "source": "manage.py",
                },
            )
            print(
                f"Membership updated for {user.email}: {membership.campaign_slug} -> {membership.role} ({membership.status})"
            )
            return

        if args.command == "assign-character":
            ensure_campaign_exists(app, args.campaign_slug)
            actor_user_id = resolve_actor_id(store, args.actor_email)
            user = require_user(store, args.email)
            previous = store.get_character_assignment(args.campaign_slug, args.character_slug)
            assignment = store.upsert_character_assignment(
                user.id,
                args.campaign_slug,
                args.character_slug,
            )
            store.write_audit_event(
                event_type="character_assignment_created",
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                campaign_slug=args.campaign_slug,
                character_slug=args.character_slug,
                metadata={
                    "previous_user_id": previous.user_id if previous is not None else None,
                    "assignment_type": assignment.assignment_type,
                    "source": "manage.py",
                },
            )
            print(
                f"Character assignment updated for {user.email}: {assignment.campaign_slug}/{assignment.character_slug}"
            )
            return

        if args.command == "disable-user":
            actor_user_id = resolve_actor_id(store, args.actor_email)
            user = require_user(store, args.email)
            store.disable_user(user.id)
            store.revoke_all_user_sessions(user.id)
            store.revoke_all_user_api_tokens(user.id)
            store.write_audit_event(
                event_type="user_disabled",
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                metadata={"source": "manage.py"},
            )
            print(f"Disabled user {user.email}")
            return

        if args.command == "issue-password-reset":
            actor_user_id = resolve_actor_id(store, args.actor_email)
            user = require_user(store, args.email)
            if not user.is_active:
                raise SystemExit(f"User is not active: {user.email}")

            reset_token = store.issue_password_reset_token(
                user.id,
                expires_in=timedelta(hours=app.config["RESET_TTL_HOURS"]),
                created_by_user_id=actor_user_id,
            )
            store.write_audit_event(
                event_type="password_reset_issued",
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                metadata={"source": "manage.py"},
            )
            print(f"Issued password reset for {user.email}")
            print(build_local_url(app, f"/reset/{reset_token}"))
            return

        if args.command == "issue-api-token":
            actor_user_id = resolve_actor_id(store, args.actor_email)
            user = require_user(store, args.email)
            if not user.is_active:
                raise SystemExit(f"User is not active: {user.email}")
            if args.expires_in_days <= 0:
                raise SystemExit("--expires-in-days must be greater than 0.")

            raw_token, token_record = store.create_api_token(
                user.id,
                label=args.label,
                expires_in=timedelta(days=args.expires_in_days),
                created_by_user_id=actor_user_id,
            )
            store.write_audit_event(
                event_type="api_token_issued",
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                metadata={
                    "label": token_record.label,
                    "token_id": token_record.id,
                    "source": "manage.py",
                },
            )
            print(f"Issued API token {token_record.id} for {user.email} ({token_record.label})")
            print(f"Expires: {format_optional_timestamp(token_record.expires_at)}")
            print(raw_token)
            return

        if args.command == "list-api-tokens":
            user = require_user(store, args.email)
            tokens = store.list_api_tokens_for_user(user.id)
            if not tokens:
                print(f"No API tokens found for {user.email}")
                return

            print(f"API tokens for {user.email}")
            for token in tokens:
                print(
                    f"[{token.id}] {token.label} | {format_api_token_status(token)} | "
                    f"created {format_optional_timestamp(token.created_at)} | "
                    f"last used {format_optional_timestamp(token.last_used_at)} | "
                    f"expires {format_optional_timestamp(token.expires_at)}"
                )
            return

        if args.command == "revoke-api-token":
            actor_user_id = resolve_actor_id(store, args.actor_email)
            token = store.get_api_token_by_id(args.token_id)
            if token is None:
                raise SystemExit(f"API token not found: {args.token_id}")

            store.revoke_api_token(token.id)
            store.write_audit_event(
                event_type="api_token_revoked",
                actor_user_id=actor_user_id,
                target_user_id=token.user_id,
                metadata={
                    "label": token.label,
                    "token_id": token.id,
                    "source": "manage.py",
                },
            )
            print(f"Revoked API token {token.id} ({token.label})")
            return

        if args.command == "import-dnd5e-source":
            actor_user_id = resolve_actor_id(store, args.actor_email)
            importer = Dnd5eSystemsImporter(
                store=app.extensions["systems_store"],
                systems_service=app.extensions["systems_service"],
                data_root=Path(args.data_root),
            )
            results = importer.import_sources(
                list(args.source_ids),
                entry_types=list(args.entry_types) if args.entry_types else None,
                started_by_user_id=actor_user_id,
            )
            for result in results:
                print(
                    f"Imported {result.source_id}: {result.imported_count} entries "
                    f"across {len(result.imported_by_type)} entry types."
                )
                for entry_type, count in sorted(result.imported_by_type.items()):
                    print(f"  {entry_type}: {count}")
            return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
