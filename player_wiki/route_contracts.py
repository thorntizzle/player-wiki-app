from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from flask import Flask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "docs" / "contracts" / "route-access-policies.json"
MANIFEST_PATH = PROJECT_ROOT / "docs" / "contracts" / "route-api-role-visibility-manifest.json"
API_DOC_PATH = PROJECT_ROOT / "docs" / "api-v1.md"

ACTOR_DIMENSIONS = (
    "anonymous",
    "authenticated_outsider",
    "observer",
    "unassigned_player",
    "assigned_player",
    "campaign_dm",
    "app_admin",
)
ACTOR_ACCESS_STATES = ("allow", "conditional", "deny")
VISIBILITY_STATES = ("public", "players", "dm", "private")
SURFACES = ("browser", "api", "framework")
ACCESS_MODES = ("read", "mutation")
OWNING_DOMAINS = (
    "admin",
    "app-shell",
    "auth",
    "characters",
    "combat",
    "dm-content",
    "framework",
    "live-session",
    "publishing",
    "systems",
)
CAMPAIGN_SCOPES = ("none", "campaign", "wiki", "systems", "session", "combat", "dm_content", "characters")
AUTHENTICATION_POLICIES = (
    "public",
    "optional_identity",
    "browser_session_required",
    "api_identity_required",
    "token_capability",
)
VISIBILITY_POLICIES = (
    "none",
    "campaign_scope",
    "systems_source",
    "systems_entry",
    "character_scope_with_assignment_override",
    "management_not_player_visibility",
    "object_visibility",
    "token_capability",
)
VIEW_AS_POLICIES = (
    "not_applicable",
    "real_actor_only",
    "campaign_safe_reads_use_effective_actor",
    "campaign_mutations_blocked",
)
DENIAL_MODES = (
    "none",
    "browser_sign_in_redirect",
    "browser_sign_in_or_not_found",
    "browser_sign_in_or_forbidden",
    "browser_sign_in_or_forbidden_or_not_found",
    "browser_forbidden_or_not_found",
    "api_401_or_403",
    "api_401_or_403_or_404",
    "not_found",
)
OBJECT_RELATIONSHIP_REQUIREMENTS = (
    "none",
    "valid_invite_or_reset_token",
    "active_account_self",
    "real_app_admin",
    "app_admin",
    "visible_campaign_collection",
    "existing_campaign",
    "existing_campaign_asset",
    "visible_published_object",
    "enabled_systems_source",
    "enabled_systems_entry",
    "enabled_systems_entry_or_real_app_admin",
    "visible_session_object",
    "visible_combat_projection",
    "campaign_manager",
    "app_admin_or_opted_in_campaign_dm",
    "visible_character_or_assignment",
    "assigned_character_or_campaign_manager",
    "campaign_character_manager",
    "app_admin_character_assignment",
    "active_session_participant",
    "selected_player_combatant_assignment",
    "permission_filtered_management_projection",
    "campaign_combat_manager_with_systems_scope",
    "visible_character_in_characters_scope",
    "session_character_assignment_or_manager_filtered_roster",
    "session_scope_with_dm_query_manager_gate",
    "campaign_session_manager_with_characters_scope",
)
SYSTEM_RESTRICTIONS = (
    "none",
    "campaign_character_authoring_capability",
    "dnd5e_only",
    "xianxia_only",
    "combat_capable_system",
    "combat_capable_system_with_systems_scope",
    "enabled_systems_source",
    "enabled_systems_entry",
    "enabled_systems_entry_or_real_app_admin",
)

_CONVERTER_RE = re.compile(r"<(?:(?P<converter>[^:<>]+):)?(?P<name>[^<>]+)>")
_CORE_ENDPOINT_RE = re.compile(r"^- `(?P<method>[A-Z]+) (?P<route>/api/v1/[^`]+)`$")


class RouteContractError(ValueError):
    """Raised when checked route-contract inputs drift or are incomplete."""


def load_policy_document(path: Path = POLICY_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise RouteContractError("Route policy document must be a JSON object.")
    return document


def contract_app() -> Flask:
    """Build an app against tracked sample data, never operator campaign data."""

    from player_wiki.config import Config
    from tests.sample_data import build_test_campaigns_dir

    temporary_directory = tempfile.TemporaryDirectory(prefix="cpw-route-contract-")
    campaigns_dir = build_test_campaigns_dir(Path(temporary_directory.name))
    original_campaigns_dir = Config.CAMPAIGNS_DIR
    try:
        Config.CAMPAIGNS_DIR = campaigns_dir
        from player_wiki.app import create_app

        app = create_app()
    finally:
        Config.CAMPAIGNS_DIR = original_campaigns_dir
    # Keep the sample directory alive for any lazy URL-map inspection.
    app.extensions["route_contract_tempdir"] = temporary_directory
    return app


def explicit_methods(rule: Any) -> list[str]:
    return sorted(set(rule.methods) - {"HEAD", "OPTIONS"})


def flask_supplied_methods(rule: Any) -> list[str]:
    return [method for method in ("HEAD", "OPTIONS") if method in rule.methods]


def route_converters(route: str) -> dict[str, str]:
    return {
        match.group("name"): match.group("converter") or "string"
        for match in _CONVERTER_RE.finditer(route)
    }


def normalize_route_converters(route: str) -> str:
    return _CONVERTER_RE.sub(lambda match: f"<{match.group('name')}>", route)


def discover_rules(app: Flask | None = None) -> list[Any]:
    contract = app or contract_app()
    return sorted(
        contract.url_map.iter_rules(),
        key=lambda rule: (rule.rule, explicit_methods(rule), rule.endpoint),
    )


def _expanded_actor_access(profile: dict[str, Any]) -> dict[str, str]:
    allowed = set(profile.get("allow", []))
    conditional = set(profile.get("conditional", []))
    unknown = (allowed | conditional) - set(ACTOR_DIMENSIONS)
    overlap = allowed & conditional
    if unknown:
        raise RouteContractError(f"Unknown actor dimensions: {sorted(unknown)}")
    if overlap:
        raise RouteContractError(f"Actor dimensions cannot be both allowed and conditional: {sorted(overlap)}")
    return {
        actor: "allow" if actor in allowed else "conditional" if actor in conditional else "deny"
        for actor in ACTOR_DIMENSIONS
    }


def validate_policy_document(document: dict[str, Any], rules: list[Any]) -> None:
    if document.get("schema_version") != 1:
        raise RouteContractError("Route policy schema_version must be 1.")
    if document.get("actor_dimensions") != list(ACTOR_DIMENSIONS):
        raise RouteContractError("actor_dimensions must match the schema-ordered actor enum.")
    if document.get("visibility_states") != list(VISIBILITY_STATES):
        raise RouteContractError("visibility_states must match the schema-ordered visibility enum.")

    profiles = document.get("profiles")
    endpoints = document.get("endpoints")
    if not isinstance(profiles, dict) or not isinstance(endpoints, dict):
        raise RouteContractError("Route policies require object-valued profiles and endpoints.")

    discovered_endpoints = {rule.endpoint for rule in rules}
    policy_endpoints = set(endpoints)
    missing = sorted(discovered_endpoints - policy_endpoints)
    stale = sorted(policy_endpoints - discovered_endpoints)
    if missing or stale:
        raise RouteContractError(f"Endpoint policy drift; missing={missing}, stale={stale}")

    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            raise RouteContractError(f"Profile {profile_name!r} must be an object.")
        _expanded_actor_access(profile)
        enum_checks = (
            ("authentication_policy", AUTHENTICATION_POLICIES),
            ("campaign_scope", CAMPAIGN_SCOPES),
            ("visibility_policy", VISIBILITY_POLICIES),
            ("object_relationship_requirement", OBJECT_RELATIONSHIP_REQUIREMENTS),
            ("view_as_policy", VIEW_AS_POLICIES),
            ("denial_mode", DENIAL_MODES),
        )
        for field, enum_values in enum_checks:
            if profile.get(field) not in enum_values:
                raise RouteContractError(f"Profile {profile_name!r} has invalid {field}.")
        if profile["visibility_policy"] != "none" and not str(profile.get("rationale", "")).strip():
            raise RouteContractError(f"Dynamic profile {profile_name!r} needs a rationale.")

    for endpoint, record in endpoints.items():
        if not isinstance(record, dict):
            raise RouteContractError(f"Endpoint policy {endpoint!r} must be an object.")
        if record.get("profile") not in profiles:
            raise RouteContractError(f"Endpoint {endpoint!r} references an unknown profile.")
        if record.get("owning_domain") not in OWNING_DOMAINS:
            raise RouteContractError(f"Endpoint {endpoint!r} needs owning_domain.")
        profile = profiles[record["profile"]]
        endpoint_enum_checks = (
            ("campaign_scope", record.get("campaign_scope", profile["campaign_scope"]), CAMPAIGN_SCOPES),
            (
                "visibility_policy",
                record.get("visibility_policy", profile["visibility_policy"]),
                VISIBILITY_POLICIES,
            ),
            (
                "object_relationship_requirement",
                record.get(
                    "object_relationship_requirement",
                    profile["object_relationship_requirement"],
                ),
                OBJECT_RELATIONSHIP_REQUIREMENTS,
            ),
        )
        for field, value, enum_values in endpoint_enum_checks:
            if value not in enum_values:
                raise RouteContractError(f"Endpoint {endpoint!r} has an invalid {field}.")
        if record.get("system_restriction", "none") not in SYSTEM_RESTRICTIONS:
            raise RouteContractError(f"Endpoint {endpoint!r} has an invalid system restriction.")


def build_manifest(document: dict[str, Any] | None = None, app: Flask | None = None) -> dict[str, Any]:
    policies = document or load_policy_document()
    rules = discover_rules(app)
    validate_policy_document(policies, rules)
    profiles = policies["profiles"]
    endpoint_policies = policies["endpoints"]

    entries: list[dict[str, Any]] = []
    seen_method_routes: set[tuple[str, str]] = set()
    for rule in rules:
        record = endpoint_policies[rule.endpoint]
        profile = profiles[record["profile"]]
        for method in explicit_methods(rule):
            identity = (method, rule.rule)
            if identity in seen_method_routes:
                raise RouteContractError(f"Duplicate method/path registration: {method} {rule.rule}")
            seen_method_routes.add(identity)
            is_mutation = method not in {"GET"}
            entry = {
                "endpoint": rule.endpoint,
                "route": rule.rule,
                "normalized_route": normalize_route_converters(rule.rule),
                "converters": route_converters(rule.rule),
                "method": method,
                "flask_supplied_methods": flask_supplied_methods(rule),
                "surface": "framework" if rule.endpoint == "static" else "api" if rule.rule.startswith("/api/") else "browser",
                "owning_domain": record["owning_domain"],
                "access_mode": "mutation" if is_mutation else "read",
                "authentication_policy": profile["authentication_policy"],
                "access_policy": record["profile"],
                "actor_access": _expanded_actor_access(profile),
                "campaign_scope": record.get("campaign_scope", profile.get("campaign_scope", "none")),
                "visibility_policy": record.get("visibility_policy", profile["visibility_policy"]),
                "object_relationship_requirement": record.get(
                    "object_relationship_requirement",
                    profile.get("object_relationship_requirement", "none"),
                ),
                "system_restriction": record.get("system_restriction", "none"),
                "view_as_policy": (
                    "campaign_mutations_blocked"
                    if is_mutation
                    and (
                        rule.rule.startswith("/campaigns/")
                        or rule.rule.startswith("/api/v1/campaigns/")
                    )
                    else profile["view_as_policy"]
                ),
                "denial_mode": profile["denial_mode"],
                "rationale": record.get("rationale", profile.get("rationale", "")),
            }
            entries.append(entry)

    entries.sort(key=lambda item: (item["route"], item["method"], item["endpoint"]))
    return {
        "schema_version": 1,
        "actor_dimensions": list(ACTOR_DIMENSIONS),
        "actor_access_states": list(ACTOR_ACCESS_STATES),
        "visibility_states": list(VISIBILITY_STATES),
        "surfaces": list(SURFACES),
        "access_modes": list(ACCESS_MODES),
        "owning_domains": list(OWNING_DOMAINS),
        "authentication_policies": list(AUTHENTICATION_POLICIES),
        "campaign_scopes": list(CAMPAIGN_SCOPES),
        "visibility_policies": list(VISIBILITY_POLICIES),
        "object_relationship_requirements": list(OBJECT_RELATIONSHIP_REQUIREMENTS),
        "system_restrictions": list(SYSTEM_RESTRICTIONS),
        "view_as_policies": list(VIEW_AS_POLICIES),
        "denial_modes": list(DENIAL_MODES),
        "flask_supplied_method_contract": ["HEAD for GET routes", "OPTIONS for all routes"],
        "entries": entries,
    }


def manifest_bytes(document: dict[str, Any] | None = None, app: Flask | None = None) -> bytes:
    payload = json.dumps(build_manifest(document, app), indent=2, ensure_ascii=False)
    return (payload + "\n").encode("utf-8")


def parse_api_core_endpoints(markdown: str) -> set[tuple[str, str]]:
    in_core = False
    endpoints: set[tuple[str, str]] = set()
    for line in markdown.splitlines():
        if line == "## Core Endpoints":
            in_core = True
            continue
        if in_core and line.startswith("## "):
            break
        if not in_core:
            continue
        match = _CORE_ENDPOINT_RE.match(line)
        if match:
            endpoints.add((match.group("method"), normalize_route_converters(match.group("route"))))
    return endpoints


def registered_api_endpoints(app: Flask | None = None) -> set[tuple[str, str]]:
    return {
        (method, normalize_route_converters(rule.rule))
        for rule in discover_rules(app)
        if rule.rule.startswith("/api/v1/")
        for method in explicit_methods(rule)
    }
