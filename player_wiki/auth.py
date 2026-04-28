from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import wraps
from urllib.parse import urljoin, urlsplit

from flask import Flask, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .auth_store import (
    ApiTokenRecord,
    AuthStore,
    CampaignMembership,
    DEFAULT_SESSION_CHAT_ORDER,
    UserAccount,
    UserPreferences,
    is_valid_session_chat_order,
    normalize_session_chat_order,
    utcnow,
)
from .campaign_visibility import (
    CAMPAIGN_VISIBILITY_SCOPES,
    DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE,
    VISIBILITY_DM,
    VISIBILITY_LABELS,
    VISIBILITY_ORDER,
    VISIBILITY_PLAYERS,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    build_default_campaign_visibility_by_scope,
    is_valid_visibility_scope,
    most_private_visibility,
)
from .models import Campaign
from .repository import Repository
from .repository_store import RepositoryStore
from .themes import ThemePreset, get_theme_preset, is_valid_theme_key, list_theme_presets, normalize_theme_key

AUTH_SESSION_KEY = "auth_session_token"
SESSION_CHAT_ORDER_LABELS = {
    "newest_first": "Newest first",
    "oldest_first": "Oldest first",
}
SESSION_CHAT_ORDER_CHOICES = [
    {
        "value": "newest_first",
        "label": "Newest first",
        "description": "Show new messages and revealed articles above older entries in the live Session chat window.",
    },
    {
        "value": "oldest_first",
        "label": "Oldest first",
        "description": "Keep the live Session chat window in chronological order from top to bottom.",
    },
]


@dataclass(slots=True)
class CampaignAccessEntry:
    campaign: Campaign
    role: str


def register_auth(app: Flask) -> None:
    def load_authenticated_user(
        user: UserAccount,
        *,
        auth_source: str,
        memberships: list[CampaignMembership],
        session_record=None,
        api_token_record: ApiTokenRecord | None = None,
    ) -> None:
        preferences = get_auth_store().get_user_preferences(user.id)
        g.current_user = user
        g.current_memberships = memberships
        g.current_session_record = session_record
        g.current_api_token_record = api_token_record
        g.current_auth_source = auth_source
        g.current_user_preferences = preferences
        g.current_theme = get_theme_preset(preferences.theme_key)

    def extract_api_bearer_token() -> str | None:
        raw_header = request.headers.get("Authorization", "").strip()
        if not raw_header:
            return None
        scheme, _, credentials = raw_header.partition(" ")
        if scheme.lower() != "bearer":
            return None
        token = credentials.strip()
        return token or None

    def render_account_settings_page(*, status_code: int = 200):
        rendered = render_template(
            "account_settings.html",
            theme_presets=list_theme_presets(),
            selected_theme_key=get_current_theme().key,
            session_chat_order_choices=SESSION_CHAT_ORDER_CHOICES,
            selected_session_chat_order=get_current_user_preferences().session_chat_order,
        )
        if status_code == 200:
            return rendered
        return rendered, status_code

    @app.before_request
    def load_request_identity() -> None:
        g.current_user = None
        g.current_memberships = []
        g.current_session_record = None
        g.current_api_token_record = None
        g.current_auth_source = "anonymous"
        g.campaign_visibility_cache = {}
        g.current_user_preferences = UserPreferences(
            user_id=0,
            theme_key=get_theme_preset(None).key,
            session_chat_order=DEFAULT_SESSION_CHAT_ORDER,
            updated_at=utcnow(),
        )
        g.current_theme = get_theme_preset(None)

        store = get_auth_store()
        raw_api_token = extract_api_bearer_token()
        if raw_api_token is not None:
            api_token_record = store.get_active_api_token(raw_api_token)
            if api_token_record is None:
                return

            user = store.get_user_by_id(api_token_record.user_id)
            if user is None or not user.is_active:
                store.revoke_api_token(api_token_record.id)
                return

            memberships = store.list_memberships_for_user(user.id, statuses=("active",))
            load_authenticated_user(
                user,
                auth_source="api_token",
                memberships=memberships,
                api_token_record=api_token_record,
            )

            touch_after_seconds = current_app.config["SESSION_TOUCH_INTERVAL_SECONDS"]
            if (utcnow() - api_token_record.last_used_at).total_seconds() >= touch_after_seconds:
                store.touch_api_token(api_token_record.id)
            return

        raw_token = session.get(AUTH_SESSION_KEY)
        if not raw_token:
            return

        session_record = store.get_active_session(raw_token)
        if session_record is None:
            session.pop(AUTH_SESSION_KEY, None)
            return

        user = store.get_user_by_id(session_record.user_id)
        if user is None or not user.is_active:
            store.revoke_session(session_record.id)
            session.pop(AUTH_SESSION_KEY, None)
            return

        memberships = store.list_memberships_for_user(user.id, statuses=("active",))
        load_authenticated_user(
            user,
            auth_source="browser_session",
            memberships=memberships,
            session_record=session_record,
        )

        touch_after_seconds = current_app.config["SESSION_TOUCH_INTERVAL_SECONDS"]
        if (utcnow() - session_record.last_seen_at).total_seconds() >= touch_after_seconds:
            store.touch_session(session_record.id)

    @app.context_processor
    def inject_auth_context() -> dict[str, object]:
        return {
            "current_user": get_current_user(),
            "current_user_preferences": get_current_user_preferences(),
            "current_theme": get_current_theme(),
            "has_campaign_access": can_access_campaign,
            "campaign_role_for_current_user": get_campaign_role,
            "can_manage_campaign_session": can_manage_campaign_session,
            "can_manage_campaign_combat": can_manage_campaign_combat,
            "can_manage_campaign_dm_content": can_manage_campaign_dm_content,
            "can_manage_campaign_systems": can_manage_campaign_systems,
            "can_edit_shared_systems_entries": can_edit_shared_systems_entries,
            "can_manage_campaign_content": can_manage_campaign_content,
            "can_post_campaign_session_messages": can_post_campaign_session_messages,
            "can_access_campaign_scope": can_access_campaign_scope,
            "campaign_visibility_for_scope": get_campaign_scope_visibility,
            "effective_campaign_visibility_for_scope": get_effective_campaign_visibility,
            "campaign_visibility_label": lambda value: VISIBILITY_LABELS.get(value, value.title()),
            "can_manage_campaign_visibility": can_manage_campaign_visibility,
        }

    @app.get("/sign-in")
    def sign_in() -> str:
        if get_current_user() is not None:
            return redirect(url_for("home"))

        next_url = request.args.get("next", "").strip()
        return render_template("sign_in.html", next_url=next_url)

    @app.post("/sign-in")
    def sign_in_submit() -> str:
        if get_current_user() is not None:
            return redirect(url_for("home"))

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "").strip()

        store = get_auth_store()
        user = store.get_user_by_email(email)
        if (
            user is None
            or not user.is_active
            or not user.password_hash
            or not check_password_hash(user.password_hash, password)
        ):
            flash("Sign-in failed. Check your email and password.", "error")
            return render_template("sign_in.html", email=email, next_url=next_url), 400

        raw_token, _ = store.create_session(
            user.id,
            expires_in=timedelta(hours=current_app.config["SESSION_TTL_HOURS"]),
            user_agent=request.user_agent.string or None,
            ip_address=request.remote_addr,
        )
        begin_browser_session(raw_token)
        flash(f"Signed in as {user.display_name}.", "success")
        return redirect(resolve_next_url(next_url))

    @app.post("/sign-out")
    @login_required
    def sign_out() -> str:
        session_record = get_current_session_record()
        if session_record is not None:
            get_auth_store().revoke_session(session_record.id)

        session.clear()
        flash("Signed out.", "success")
        return redirect(url_for("sign_in"))

    @app.get("/account")
    @login_required
    def account_settings_view():
        return render_account_settings_page()

    @app.post("/account/theme")
    @login_required
    def account_theme_update():
        user = get_current_user()
        if user is None:
            abort(401)

        requested_theme_key = request.form.get("theme_key", "")
        if not is_valid_theme_key(requested_theme_key):
            flash("Choose a valid theme preset.", "error")
            return render_account_settings_page(status_code=400)

        selected_theme = get_theme_preset(normalize_theme_key(requested_theme_key))
        store = get_auth_store()
        current_theme_key = store.get_user_preferences(user.id).theme_key
        if current_theme_key == selected_theme.key:
            flash(f"Theme already set to {selected_theme.label}.", "success")
            return redirect(url_for("account_settings_view"))

        store.set_user_theme_key(user.id, selected_theme.key)
        g.current_theme = selected_theme
        flash(f"Theme updated to {selected_theme.label}.", "success")
        return redirect(url_for("account_settings_view"))

    @app.post("/account/session-chat-order")
    @login_required
    def account_session_chat_order_update():
        user = get_current_user()
        if user is None:
            abort(401)

        requested_order = request.form.get("session_chat_order", "")
        if not is_valid_session_chat_order(requested_order):
            flash("Choose a valid live session chat order.", "error")
            return render_account_settings_page(status_code=400)

        normalized_order = normalize_session_chat_order(requested_order)
        current_preferences = get_auth_store().get_user_preferences(user.id)
        if current_preferences.session_chat_order == normalized_order:
            flash(
                f"Live session chat order already set to {SESSION_CHAT_ORDER_LABELS[normalized_order]}.",
                "success",
            )
            return redirect(url_for("account_settings_view"))

        updated_preferences = get_auth_store().set_user_session_chat_order(user.id, normalized_order)
        g.current_user_preferences = updated_preferences
        flash(
            f"Live session chat order updated to {SESSION_CHAT_ORDER_LABELS[normalized_order]}.",
            "success",
        )
        return redirect(url_for("account_settings_view"))

    @app.route("/invite/<token>", methods=["GET", "POST"])
    def invite_setup(token: str) -> str | tuple[str, int]:
        resolved = get_auth_store().get_valid_invite(token)
        if resolved is None:
            return render_template(
                "invite_setup.html",
                mode="invite",
                token_valid=False,
                page_title="Set your password",
            ), 400

        invite_record, user = resolved
        if user.status != "invited":
            return render_template(
                "invite_setup.html",
                mode="invite",
                token_valid=False,
                page_title="Set your password",
            ), 400

        if request.method == "POST":
            display_name = request.form.get("display_name", user.display_name).strip()
            password = request.form.get("password", "")
            password_confirmation = request.form.get("password_confirmation", "")
            errors = validate_password_inputs(password, password_confirmation)
            if not display_name:
                errors.append("Display name is required.")

            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template(
                    "invite_setup.html",
                    mode="invite",
                    token_valid=True,
                    page_title="Set your password",
                    display_name=display_name,
                    user=user,
                ), 400

            password_hash = generate_password_hash(password)
            store = get_auth_store()
            store.activate_user(user.id, display_name=display_name, password_hash=password_hash)
            store.consume_invite(invite_record.id)
            store.revoke_all_user_sessions(user.id)
            store.revoke_all_user_api_tokens(user.id)
            store.write_audit_event(
                event_type="user_activated",
                actor_user_id=user.id,
                target_user_id=user.id,
                metadata={"via": "invite"},
            )
            raw_token, _ = store.create_session(
                user.id,
                expires_in=timedelta(hours=current_app.config["SESSION_TTL_HOURS"]),
                user_agent=request.user_agent.string or None,
                ip_address=request.remote_addr,
            )
            begin_browser_session(raw_token)
            flash("Account setup complete.", "success")
            return redirect(url_for("home"))

        return render_template(
            "invite_setup.html",
            mode="invite",
            token_valid=True,
            page_title="Set your password",
            display_name=user.display_name,
            user=user,
        )

    @app.route("/reset/<token>", methods=["GET", "POST"])
    def password_reset(token: str) -> str | tuple[str, int]:
        resolved = get_auth_store().get_valid_password_reset(token)
        if resolved is None:
            return render_template(
                "invite_setup.html",
                mode="reset",
                token_valid=False,
                page_title="Reset your password",
            ), 400

        reset_record, user = resolved
        if request.method == "POST":
            password = request.form.get("password", "")
            password_confirmation = request.form.get("password_confirmation", "")
            errors = validate_password_inputs(password, password_confirmation)
            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template(
                    "invite_setup.html",
                    mode="reset",
                    token_valid=True,
                    page_title="Reset your password",
                    user=user,
                ), 400

            store = get_auth_store()
            store.set_password(user.id, generate_password_hash(password))
            store.consume_password_reset(reset_record.id)
            store.revoke_all_user_sessions(user.id)
            store.revoke_all_user_api_tokens(user.id)
            store.write_audit_event(
                event_type="password_reset_completed",
                actor_user_id=user.id,
                target_user_id=user.id,
                metadata={"via": "reset_token"},
            )
            raw_token, _ = store.create_session(
                user.id,
                expires_in=timedelta(hours=current_app.config["SESSION_TTL_HOURS"]),
                user_agent=request.user_agent.string or None,
                ip_address=request.remote_addr,
            )
            begin_browser_session(raw_token)
            flash("Password updated.", "success")
            return redirect(url_for("home"))

        return render_template(
            "invite_setup.html",
            mode="reset",
            token_valid=True,
            page_title="Reset your password",
            user=user,
        )

    @app.get("/campaigns")
    def campaign_picker() -> str:
        user = get_current_user()
        if user is None:
            entries = get_public_campaign_entries()
        else:
            entries = get_accessible_campaign_entries()
        return render_template("campaign_picker.html", campaign_entries=entries)


def get_auth_store() -> AuthStore:
    return current_app.extensions["auth_store"]


def get_repository_store() -> RepositoryStore:
    return current_app.extensions["repository_store"]


def get_repository() -> Repository:
    return get_repository_store().get()


def get_systems_service():
    return current_app.extensions["systems_service"]


def get_current_user() -> UserAccount | None:
    user = getattr(g, "current_user", None)
    return user if isinstance(user, UserAccount) else None


def get_current_memberships() -> list[CampaignMembership]:
    memberships = getattr(g, "current_memberships", [])
    return memberships if isinstance(memberships, list) else []


def get_current_session_record():
    return getattr(g, "current_session_record", None)


def get_current_auth_source() -> str:
    value = getattr(g, "current_auth_source", "anonymous")
    return value if isinstance(value, str) else "anonymous"


def get_current_theme() -> ThemePreset:
    theme = getattr(g, "current_theme", None)
    return theme if isinstance(theme, ThemePreset) else get_theme_preset(None)


def get_current_user_preferences() -> UserPreferences:
    preferences = getattr(g, "current_user_preferences", None)
    if isinstance(preferences, UserPreferences):
        return preferences
    return UserPreferences(
        user_id=0,
        theme_key=get_theme_preset(None).key,
        session_chat_order=DEFAULT_SESSION_CHAT_ORDER,
        updated_at=utcnow(),
    )


def get_campaign_visibility_settings(campaign_slug: str) -> dict[str, str]:
    cache = getattr(g, "campaign_visibility_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        g.campaign_visibility_cache = cache

    if campaign_slug in cache:
        return dict(cache[campaign_slug])

    settings = get_campaign_default_visibility_settings(campaign_slug)
    for setting in get_auth_store().list_campaign_visibility_settings(campaign_slug):
        if setting.scope in CAMPAIGN_VISIBILITY_SCOPES:
            settings[setting.scope] = setting.visibility

    cache[campaign_slug] = dict(settings)
    return settings


def get_campaign_default_visibility_settings(campaign_slug: str) -> dict[str, str]:
    campaign = get_repository().get_campaign(campaign_slug)
    system_code = campaign.system if campaign is not None else ""
    return build_default_campaign_visibility_by_scope(system_code)


def get_campaign_default_scope_visibility(campaign_slug: str, scope: str) -> str:
    normalized_scope = scope.strip().lower()
    if not is_valid_visibility_scope(normalized_scope):
        return VISIBILITY_PRIVATE
    return get_campaign_default_visibility_settings(campaign_slug).get(
        normalized_scope,
        DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE[normalized_scope],
    )


def clear_campaign_visibility_cache(campaign_slug: str | None = None) -> None:
    cache = getattr(g, "campaign_visibility_cache", None)
    if not isinstance(cache, dict):
        return
    if campaign_slug is None:
        cache.clear()
        return
    cache.pop(campaign_slug, None)


def get_campaign_scope_visibility(campaign_slug: str, scope: str) -> str:
    normalized_scope = scope.strip().lower()
    if not is_valid_visibility_scope(normalized_scope):
        return VISIBILITY_PRIVATE
    return get_campaign_visibility_settings(campaign_slug).get(
        normalized_scope,
        get_campaign_default_scope_visibility(campaign_slug, normalized_scope),
    )


def get_effective_campaign_visibility(campaign_slug: str, scope: str) -> str:
    normalized_scope = scope.strip().lower()
    if not is_valid_visibility_scope(normalized_scope):
        return VISIBILITY_PRIVATE

    campaign_visibility = get_campaign_scope_visibility(campaign_slug, "campaign")
    if normalized_scope == "campaign":
        return campaign_visibility
    return most_private_visibility(
        campaign_visibility,
        get_campaign_scope_visibility(campaign_slug, normalized_scope),
    )


def role_satisfies_visibility(role: str | None, visibility: str) -> bool:
    if visibility == VISIBILITY_PUBLIC:
        return True
    if visibility == VISIBILITY_PLAYERS:
        return role in {"player", "dm"}
    if visibility == VISIBILITY_DM:
        return role == "dm"
    return False


def get_accessible_campaign_entries(repository: Repository | None = None) -> list[CampaignAccessEntry]:
    user = get_current_user()
    if user is None:
        return []

    repository = repository or get_repository()
    if user.is_admin:
        entries = [CampaignAccessEntry(campaign=campaign, role="admin") for campaign in repository.campaigns.values()]
        return sorted(entries, key=lambda entry: entry.campaign.title.lower())

    entries: list[CampaignAccessEntry] = []
    for campaign in repository.campaigns.values():
        if not can_access_campaign_scope(campaign.slug, "campaign"):
            continue
        entries.append(CampaignAccessEntry(campaign=campaign, role=get_campaign_role(campaign.slug) or "public"))

    return sorted(entries, key=lambda entry: entry.campaign.title.lower())


def get_public_campaign_entries(repository: Repository | None = None) -> list[CampaignAccessEntry]:
    repository = repository or get_repository()
    entries = [
        CampaignAccessEntry(campaign=campaign, role="public")
        for campaign in repository.campaigns.values()
        if get_effective_campaign_visibility(campaign.slug, "campaign") == VISIBILITY_PUBLIC
    ]
    return sorted(entries, key=lambda entry: entry.campaign.title.lower())


def can_view_campaign(campaign_slug: str) -> bool:
    return can_access_campaign_scope(campaign_slug, "campaign")


def has_campaign_membership_access(campaign_slug: str) -> bool:
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return get_repository().get_campaign(campaign_slug) is not None
    return any(
        membership.campaign_slug == campaign_slug and membership.status == "active"
        for membership in get_current_memberships()
    )


def can_access_campaign(campaign_slug: str) -> bool:
    return can_access_campaign_scope(campaign_slug, "campaign")


def can_access_campaign_scope(campaign_slug: str, scope: str) -> bool:
    if get_repository().get_campaign(campaign_slug) is None:
        return False

    user = get_current_user()
    if user is not None and user.is_admin:
        return True

    effective_visibility = get_effective_campaign_visibility(campaign_slug, scope)
    if effective_visibility == VISIBILITY_PUBLIC:
        return True
    return role_satisfies_visibility(get_campaign_role(campaign_slug), effective_visibility)


def get_campaign_role(campaign_slug: str) -> str | None:
    user = get_current_user()
    if user is None:
        return None
    if user.is_admin:
        return "admin"
    membership = next(
        (item for item in get_current_memberships() if item.campaign_slug == campaign_slug and item.status == "active"),
        None,
    )
    return membership.role if membership else None


def can_edit_character(campaign_slug: str, character_slug: str) -> bool:
    if not can_access_campaign_scope(campaign_slug, "characters"):
        return False
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return True

    role = get_campaign_role(campaign_slug)
    if role == "dm":
        return True
    if role != "player":
        return False

    assignment = get_auth_store().get_character_assignment(campaign_slug, character_slug)
    return assignment is not None and assignment.user_id == user.id


def has_session_mode_access(campaign_slug: str, character_slug: str) -> bool:
    return can_edit_character(campaign_slug, character_slug)


def can_manage_campaign_session(campaign_slug: str) -> bool:
    if not can_access_campaign_scope(campaign_slug, "session"):
        return False
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return True
    return get_campaign_role(campaign_slug) == "dm"


def can_manage_campaign_combat(campaign_slug: str) -> bool:
    if not can_access_campaign_scope(campaign_slug, "combat"):
        return False
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return True
    return get_campaign_role(campaign_slug) == "dm"


def can_manage_campaign_dm_content(campaign_slug: str) -> bool:
    if not can_access_campaign_scope(campaign_slug, "dm_content"):
        return False
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return True
    return get_campaign_role(campaign_slug) == "dm"


def can_manage_campaign_systems(campaign_slug: str) -> bool:
    if not can_access_campaign_scope(campaign_slug, "systems"):
        return False
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return True
    return get_campaign_role(campaign_slug) == "dm"


def can_edit_shared_systems_entries(campaign_slug: str) -> bool:
    user = get_current_user()
    if user is None:
        return False
    if get_repository().get_campaign(campaign_slug) is None:
        return False
    if user.is_admin:
        return True
    if get_campaign_role(campaign_slug) != "dm":
        return False
    if not can_manage_campaign_systems(campaign_slug):
        return False
    policy = get_systems_service().get_campaign_policy(campaign_slug)
    return bool(policy and policy.allow_dm_shared_core_entry_edits)


def can_manage_campaign_content(campaign_slug: str) -> bool:
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return get_repository().get_campaign(campaign_slug) is not None
    return get_campaign_role(campaign_slug) == "dm" and can_access_campaign_scope(campaign_slug, "campaign")


def get_effective_campaign_systems_source_visibility(campaign_slug: str, source_id: str) -> str:
    service = get_systems_service()
    source_state = service.get_campaign_source_state(campaign_slug, source_id)
    if source_state is None or not source_state.is_enabled:
        return VISIBILITY_PRIVATE
    return most_private_visibility(
        get_effective_campaign_visibility(campaign_slug, "systems"),
        source_state.default_visibility,
    )


def can_access_campaign_systems_source(campaign_slug: str, source_id: str) -> bool:
    if get_repository().get_campaign(campaign_slug) is None:
        return False
    user = get_current_user()
    if user is not None and user.is_admin:
        return True
    effective_visibility = get_effective_campaign_systems_source_visibility(campaign_slug, source_id)
    if effective_visibility == VISIBILITY_PUBLIC:
        return True
    return role_satisfies_visibility(get_campaign_role(campaign_slug), effective_visibility)


def get_effective_campaign_systems_entry_visibility(campaign_slug: str, entry_slug: str) -> str:
    service = get_systems_service()
    entry = service.get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
    if entry is None:
        return VISIBILITY_PRIVATE
    if not service.is_entry_enabled_for_campaign(campaign_slug, entry):
        return VISIBILITY_PRIVATE
    override = service.store.get_campaign_entry_override(campaign_slug, entry.entry_key)
    source_state = service.get_campaign_source_state(campaign_slug, entry.source_id)
    if source_state is None or not source_state.is_enabled:
        return VISIBILITY_PRIVATE
    entry_visibility = (
        override.visibility_override
        if override is not None and override.visibility_override
        else service.get_default_entry_visibility_for_campaign(campaign_slug, entry)
    )
    entry_visibility = service.clamp_visibility_for_source(source_state.source, entry_visibility)
    return most_private_visibility(
        get_effective_campaign_visibility(campaign_slug, "systems"),
        entry_visibility,
    )


def can_access_campaign_systems_entry(campaign_slug: str, entry_slug: str) -> bool:
    if get_repository().get_campaign(campaign_slug) is None:
        return False
    user = get_current_user()
    if user is not None and user.is_admin:
        return True
    effective_visibility = get_effective_campaign_systems_entry_visibility(campaign_slug, entry_slug)
    if effective_visibility == VISIBILITY_PUBLIC:
        return True
    return role_satisfies_visibility(get_campaign_role(campaign_slug), effective_visibility)


def can_post_campaign_session_messages(campaign_slug: str) -> bool:
    if not can_access_campaign_scope(campaign_slug, "session"):
        return False
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return True
    return get_campaign_role(campaign_slug) in {"dm", "player"}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            return redirect(url_for("sign_in", next=request.full_path if request.query_string else request.path))
        return view(*args, **kwargs)

    return wrapped


def can_manage_campaign_visibility(campaign_slug: str) -> bool:
    user = get_current_user()
    if user is None:
        return False
    if user.is_admin:
        return get_repository().get_campaign(campaign_slug) is not None
    return get_campaign_role(campaign_slug) == "dm" and can_access_campaign_scope(campaign_slug, "campaign")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user is None or not user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def campaign_access_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        campaign_slug = kwargs.get("campaign_slug")
        if not isinstance(campaign_slug, str) or not has_campaign_membership_access(campaign_slug):
            abort(404)
        return view(*args, **kwargs)

    return wrapped


def campaign_scope_access_required(scope: str):
    normalized_scope = scope.strip().lower()
    if not is_valid_visibility_scope(normalized_scope):
        raise ValueError(f"Unsupported campaign visibility scope: {scope}")

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            campaign_slug = kwargs.get("campaign_slug")
            if not isinstance(campaign_slug, str) or get_repository().get_campaign(campaign_slug) is None:
                abort(404)

            if can_access_campaign_scope(campaign_slug, normalized_scope):
                return view(*args, **kwargs)

            if get_current_user() is None and get_effective_campaign_visibility(campaign_slug, normalized_scope) != VISIBILITY_PUBLIC:
                return redirect(url_for("sign_in", next=request.full_path if request.query_string else request.path))

            abort(404)

        return wrapped

    return decorator


def public_campaign_access_required(view):
    return campaign_scope_access_required("wiki")(view)


def campaign_systems_source_access_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        campaign_slug = kwargs.get("campaign_slug")
        source_id = kwargs.get("source_id")
        if not isinstance(campaign_slug, str) or not isinstance(source_id, str):
            abort(404)
        if can_access_campaign_systems_source(campaign_slug, source_id):
            return view(*args, **kwargs)
        if get_current_user() is None and get_effective_campaign_systems_source_visibility(campaign_slug, source_id) != VISIBILITY_PUBLIC:
            return redirect(url_for("sign_in", next=request.full_path if request.query_string else request.path))
        abort(404)

    return wrapped


def campaign_systems_entry_access_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        campaign_slug = kwargs.get("campaign_slug")
        entry_slug = kwargs.get("entry_slug")
        if not isinstance(campaign_slug, str) or not isinstance(entry_slug, str):
            abort(404)
        if can_access_campaign_systems_entry(campaign_slug, entry_slug):
            return view(*args, **kwargs)
        if get_current_user() is None and get_effective_campaign_systems_entry_visibility(campaign_slug, entry_slug) != VISIBILITY_PUBLIC:
            return redirect(url_for("sign_in", next=request.full_path if request.query_string else request.path))
        abort(404)

    return wrapped


def begin_browser_session(raw_token: str) -> None:
    session.clear()
    session.permanent = True
    session[AUTH_SESSION_KEY] = raw_token


def validate_password_inputs(password: str, password_confirmation: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if password != password_confirmation:
        errors.append("Password confirmation does not match.")
    return errors


def is_safe_next_url(target: str) -> bool:
    if not target:
        return False

    base_url = request.host_url
    reference = urlsplit(base_url)
    candidate = urlsplit(urljoin(base_url, target))
    return candidate.scheme in {"http", "https"} and candidate.netloc == reference.netloc


def resolve_next_url(next_url: str) -> str:
    if is_safe_next_url(next_url):
        return next_url
    return url_for("home")
