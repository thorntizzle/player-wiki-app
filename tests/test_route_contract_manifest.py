from __future__ import annotations

import ast
import json
from functools import lru_cache
from pathlib import Path

import pytest

from player_wiki.route_contracts import (
    ACTOR_ACCESS_STATES,
    ACTOR_DIMENSIONS,
    API_DOC_PATH,
    CAMPAIGN_SCOPES,
    DENIAL_MODES,
    MANIFEST_PATH,
    OBJECT_RELATIONSHIP_REQUIREMENTS,
    OWNING_DOMAINS,
    POLICY_PATH,
    SYSTEM_RESTRICTIONS,
    VISIBILITY_STATES,
    build_manifest,
    discover_rules,
    explicit_methods,
    load_policy_document,
    manifest_bytes,
    normalize_route_converters,
    parse_api_core_endpoints,
    registered_api_endpoints,
    validate_policy_document,
)


pytestmark = pytest.mark.contract


@lru_cache(maxsize=1)
def cached_manifest() -> dict[str, object]:
    return build_manifest()


def manifest_entry(endpoint: str, method: str) -> dict[str, object]:
    matches = [
        entry
        for entry in cached_manifest()["entries"]
        if entry["endpoint"] == endpoint and entry["method"] == method
    ]
    assert len(matches) == 1
    return matches[0]


def test_every_url_map_endpoint_has_exactly_one_current_policy() -> None:
    rules = discover_rules()
    policies = load_policy_document()

    validate_policy_document(policies, rules)
    assert set(policies["endpoints"]) == {rule.endpoint for rule in rules}


def test_url_map_has_no_duplicate_method_path_registration() -> None:
    rules = discover_rules()
    identities = [
        (method, rule.rule)
        for rule in rules
        for method in explicit_methods(rule)
    ]

    assert len(identities) == len(set(identities))
    assert len(rules) == 299
    assert sum(rule.endpoint != "static" for rule in rules) == 298
    assert len(identities) == 308
    assert sum(len(explicit_methods(rule)) > 1 for rule in rules) == 9


def test_route_registration_sources_match_the_checked_inventory() -> None:
    expected = {
        "app.py": 136,
        "api.py": 136,
        "admin.py": 14,
        "auth.py": 9,
        "publishing_routes.py": 0,
    }
    actual: dict[str, int] = {}
    for filename in expected:
        path = Path(__file__).resolve().parents[1] / "player_wiki" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
        actual[filename] = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in {"route", "get", "post", "put", "patch", "delete"}
        )

    assert actual == expected
    source_text = {
        path.name: path.read_text(encoding="utf-8")
        for path in (Path(__file__).resolve().parents[1] / "player_wiki").glob("*.py")
    }
    assert {name for name, text in source_text.items() if "Blueprint(" in text} == {
        "api.py",
        "publishing_routes.py",
    }
    assert {name for name, text in source_text.items() if "add_url_rule" in text} == {
        "publishing_routes.py"
    }


def test_publishing_get_routes_keep_one_legacy_rule_and_implicit_methods() -> None:
    expected = {
        "campaign_asset": "/campaigns/<campaign_slug>/assets/<path:asset_path>",
        "section_view": "/campaigns/<campaign_slug>/sections/<section_slug>",
        "page_view": "/campaigns/<campaign_slug>/pages/<path:page_slug>",
    }
    rules = discover_rules()

    for endpoint, path in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["GET"]
        assert set(matches[0].methods) >= {"GET", "HEAD", "OPTIONS"}

    assert not any(rule.endpoint.startswith("publishing.") for rule in rules)


def test_committed_manifest_is_generated_byte_for_byte() -> None:
    assert MANIFEST_PATH.read_bytes() == manifest_bytes()


def test_manifest_expands_complete_ordered_enums_and_actor_matrices() -> None:
    manifest = build_manifest()

    assert manifest["actor_dimensions"] == list(ACTOR_DIMENSIONS)
    assert manifest["actor_access_states"] == list(ACTOR_ACCESS_STATES)
    assert manifest["visibility_states"] == list(VISIBILITY_STATES)
    assert manifest["owning_domains"] == list(OWNING_DOMAINS)
    assert manifest["campaign_scopes"] == list(CAMPAIGN_SCOPES)
    assert manifest["object_relationship_requirements"] == list(OBJECT_RELATIONSHIP_REQUIREMENTS)
    assert manifest["system_restrictions"] == list(SYSTEM_RESTRICTIONS)
    assert manifest["denial_modes"] == list(DENIAL_MODES)
    assert manifest["entries"] == sorted(
        manifest["entries"],
        key=lambda item: (item["route"], item["method"], item["endpoint"]),
    )
    for entry in manifest["entries"]:
        assert list(entry["actor_access"]) == list(ACTOR_DIMENSIONS)
        assert set(entry["actor_access"].values()) <= set(ACTOR_ACCESS_STATES)


def test_every_campaign_route_has_scope_and_visibility_or_explicit_none_rationale() -> None:
    for entry in build_manifest()["entries"]:
        if "<campaign_slug>" not in entry["route"]:
            continue
        if entry["campaign_scope"] != "none" and entry["visibility_policy"] != "none":
            continue
        assert entry["campaign_scope"] == "none"
        assert entry["visibility_policy"] == "management_not_player_visibility"
        assert entry["rationale"].strip()


def test_api_core_endpoint_list_exactly_matches_registered_api_routes() -> None:
    documented = parse_api_core_endpoints(API_DOC_PATH.read_text(encoding="utf-8"))
    registered = registered_api_endpoints()

    assert documented == registered, {
        "missing_from_docs": sorted(registered - documented),
        "stale_in_docs": sorted(documented - registered),
    }


def test_combat_status_routes_are_dm_admin_management_reads() -> None:
    for endpoint in ("campaign_combat_status_view", "campaign_combat_status_live_state"):
        entry = manifest_entry(endpoint, "GET")
        assert entry["access_policy"] == "campaign_manage_browser"
        assert entry["access_mode"] == "read"
        assert entry["authentication_policy"] == "browser_session_required"
        assert entry["actor_access"]["assigned_player"] == "deny"
        assert entry["actor_access"]["campaign_dm"] == "allow"
        assert entry["denial_mode"] == "browser_sign_in_or_forbidden_or_not_found"
        assert entry["system_restriction"] == "combat_capable_system"


def test_systems_monster_combat_routes_require_manager_and_systems_access() -> None:
    expected = {
        ("campaign_combat_search_systems_monsters", "GET"): ("combat_systems_manager_browser", "read"),
        ("campaign_combat_add_systems_monster", "POST"): ("combat_systems_manager_browser", "mutation"),
        ("api.combat_search_systems_monsters", "GET"): ("combat_systems_manager_api", "read"),
        ("api.combat_add_systems_monster", "POST"): ("combat_systems_manager_api", "mutation"),
    }
    for (endpoint, method), (profile, access_mode) in expected.items():
        entry = manifest_entry(endpoint, method)
        assert entry["access_policy"] == profile
        assert entry["access_mode"] == access_mode
        assert entry["owning_domain"] == "combat"
        assert entry["campaign_scope"] == "none"
        assert entry["visibility_policy"] == "management_not_player_visibility"
        assert entry["object_relationship_requirement"] == "campaign_combat_manager_with_systems_scope"
        assert entry["system_restriction"] == "combat_capable_system_with_systems_scope"
        assert entry["actor_access"]["assigned_player"] == "deny"
        assert entry["actor_access"]["campaign_dm"] == "conditional"
        if endpoint.startswith("api."):
            assert entry["authentication_policy"] == "api_identity_required"
            assert entry["denial_mode"] == "api_401_or_403_or_404"
        else:
            assert entry["authentication_policy"] == "browser_session_required"
            assert entry["denial_mode"] == "browser_sign_in_or_forbidden_or_not_found"


def test_cultivation_is_manager_only_and_retraining_allows_the_assigned_owner() -> None:
    cultivation_entries = (
        manifest_entry("character_xianxia_cultivation_view", "GET"),
        manifest_entry("character_xianxia_cultivation_view", "POST"),
        manifest_entry("api.character_cultivation_read", "GET"),
        manifest_entry("api.character_cultivation_action", "POST"),
    )
    for entry in cultivation_entries:
        assert entry["access_policy"] in {"cultivation_manager_browser", "cultivation_manager_api"}
        assert entry["actor_access"]["assigned_player"] == "deny"
        assert entry["actor_access"]["campaign_dm"] == "conditional"
        assert entry["campaign_scope"] == "characters"
        assert entry["object_relationship_requirement"] == "campaign_session_manager_with_characters_scope"
        assert entry["system_restriction"] == "xianxia_only"

    retraining_entries = (
        manifest_entry("character_retraining_view", "GET"),
        manifest_entry("character_retraining_view", "POST"),
        manifest_entry("api.character_retraining_read", "GET"),
        manifest_entry("api.character_retraining_submit", "POST"),
    )
    for entry in retraining_entries:
        assert entry["access_policy"] in {
            "character_scope_owner_or_manager_browser",
            "character_scope_owner_or_manager_api",
        }
        assert entry["actor_access"]["assigned_player"] == "conditional"
        assert entry["campaign_scope"] == "characters"
        assert entry["visibility_policy"] == "campaign_scope"
        assert entry["object_relationship_requirement"] == "assigned_character_or_campaign_manager"
        assert entry["system_restriction"] == "dnd5e_only"


def test_full_browser_character_reads_do_not_use_assignment_override() -> None:
    for endpoint in ("character_roster_view", "character_read_view", "character_portrait_asset"):
        entry = manifest_entry(endpoint, "GET")
        assert entry["access_policy"] == "character_read_browser"
        assert entry["campaign_scope"] == "characters"
        assert entry["visibility_policy"] == "campaign_scope"
        assert entry["object_relationship_requirement"] == "visible_character_in_characters_scope"


def test_session_character_uses_session_scope_and_assignment_filtered_records() -> None:
    entry = manifest_entry("campaign_session_character_view", "GET")
    assert entry["access_policy"] == "session_character_read_browser"
    assert entry["authentication_policy"] == "optional_identity"
    assert entry["campaign_scope"] == "session"
    assert entry["visibility_policy"] == "campaign_scope"
    assert entry["object_relationship_requirement"] == "session_character_assignment_or_manager_filtered_roster"
    assert entry["actor_access"]["assigned_player"] == "conditional"
    assert entry["actor_access"]["campaign_dm"] == "conditional"


def test_browser_advanced_editor_is_dnd5e_native_tools_gated() -> None:
    for method in ("GET", "POST"):
        entry = manifest_entry("character_edit_view", method)
        assert entry["access_policy"] == "character_scope_owner_or_manager_browser"
        assert entry["campaign_scope"] == "characters"
        assert entry["visibility_policy"] == "campaign_scope"
        assert entry["system_restriction"] == "dnd5e_only"


def test_session_live_state_records_the_dm_query_mode_gate() -> None:
    entry = manifest_entry("campaign_session_live_state", "GET")
    assert entry["access_policy"] == "session_live_state_browser"
    assert entry["campaign_scope"] == "session"
    assert entry["object_relationship_requirement"] == "session_scope_with_dm_query_manager_gate"
    assert entry["denial_mode"] == "browser_sign_in_or_forbidden_or_not_found"
    assert "view=dm" in entry["rationale"]
    assert "DM/admin" in entry["rationale"]
    assert "403" in entry["rationale"]


def test_contract_json_is_canonical_lf_utf8_with_trailing_newline() -> None:
    for path in (POLICY_PATH, MANIFEST_PATH):
        raw = path.read_bytes()
        assert raw.endswith(b"\n")
        assert b"\r" not in raw
        assert json.loads(raw.decode("utf-8"))["schema_version"] == 1

    attributes = (Path(__file__).resolve().parents[1] / ".gitattributes").read_text(encoding="utf-8")
    assert "docs/contracts/*.json text eol=lf" in attributes.splitlines()
