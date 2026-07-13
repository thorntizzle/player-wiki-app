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
    contract_app,
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


def app_function(name: str) -> ast.FunctionDef:
    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    matches = []
    for filename in ("app.py", "dm_content_routes.py", "systems_routes.py"):
        tree = ast.parse((source_root / filename).read_text(encoding="utf-8"))
        matches.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
    assert len(matches) == 1
    return matches[0]


def module_function(filename: str, name: str) -> ast.FunctionDef:
    path = Path(__file__).resolve().parents[1] / "player_wiki" / filename
    tree = ast.parse(path.read_text(encoding="utf-8"))
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1
    return matches[0]


def call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


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
        "app.py": 108,
        "api.py": 124,
        "admin.py": 14,
        "auth.py": 9,
        "publishing_routes.py": 0,
        "dm_content_routes.py": 0,
        "systems_routes.py": 0,
        "systems_api_routes.py": 0,
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
        "dm_content_routes.py",
        "publishing_routes.py",
        "systems_routes.py",
    }
    assert {name for name, text in source_text.items() if "add_url_rule" in text} == {
        "dm_content_routes.py",
        "publishing_routes.py",
        "systems_api_routes.py",
        "systems_routes.py",
    }


def test_systems_api_routes_keep_twelve_api_rules_and_implicit_methods() -> None:
    expected = {
        "api.systems_index": {
            "/api/v1/campaigns/<campaign_slug>/systems",
            "/api/v1/campaigns/<campaign_slug>/systems/search",
        },
        "api.systems_source_list": {
            "/api/v1/campaigns/<campaign_slug>/systems/sources",
        },
        "api.systems_source_detail": {
            "/api/v1/campaigns/<campaign_slug>/systems/sources/<source_id>",
        },
        "api.systems_source_category_detail": {
            "/api/v1/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>",
        },
        "api.systems_entry_detail": {
            "/api/v1/campaigns/<campaign_slug>/systems/entries/<entry_slug>",
        },
    }
    rules = discover_rules()

    for endpoint, paths in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert {rule.rule for rule in matches} == paths
        assert all(explicit_methods(rule) == ["GET"] for rule in matches)
        assert all(set(rule.methods) >= {"GET", "HEAD", "OPTIONS"} for rule in matches)

    extracted_rules = [rule for rule in rules if rule.endpoint in expected]
    assert len(extracted_rules) == 6
    assert sum(rule.endpoint.startswith("api.") for rule in rules) == 136

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    api_decorators = sum(
        1
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in {"route", "get", "post", "put", "patch", "delete"}
    )
    assert api_decorators == 124

    systems_api_tree = ast.parse(
        (source_root / "systems_api_routes.py").read_text(encoding="utf-8")
    )
    explicit_registrations = [
        node
        for node in ast.walk(systems_api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(explicit_registrations) == 12

    mutation_rules = {
        "api.systems_source_update": (
            "/api/v1/campaigns/<campaign_slug>/systems/sources",
            "PUT",
        ),
        "api.systems_entry_override_update": (
            "/api/v1/campaigns/<campaign_slug>/systems/overrides/<path:entry_key>",
            "PUT",
        ),
        "api.systems_custom_entry_create": (
            "/api/v1/campaigns/<campaign_slug>/systems/custom-entries",
            "POST",
        ),
        "api.systems_custom_entry_update": (
            "/api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>",
            "PUT",
        ),
        "api.systems_custom_entry_archive": (
            "/api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/archive",
            "POST",
        ),
        "api.systems_custom_entry_restore": (
            "/api/v1/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/restore",
            "POST",
        ),
    }
    for endpoint, (path, method) in mutation_rules.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        assert set(matches[0].methods) >= {method, "OPTIONS"}
        assert "HEAD" not in matches[0].methods

    contract = contract_app()
    shared_source_path = "/api/v1/campaigns/<campaign_slug>/systems/sources"
    shared_source_rules = [
        rule for rule in contract.url_map.iter_rules() if rule.rule == shared_source_path
    ]
    assert [rule.endpoint for rule in shared_source_rules] == [
        "api.systems_source_update",
        "api.systems_source_list",
    ]
    adapter = contract.url_map.bind("localhost")
    matched_endpoint, _ = adapter.match(
        "/api/v1/campaigns/linden-pass/systems/sources",
        method="OPTIONS",
    )
    assert matched_endpoint == "api.systems_source_update"


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


def test_systems_read_routes_keep_one_bare_rule_and_implicit_methods() -> None:
    expected = {
        "campaign_systems_index": "/campaigns/<campaign_slug>/systems",
        "campaign_systems_search": "/campaigns/<campaign_slug>/systems/search",
        "campaign_systems_source_detail":
            "/campaigns/<campaign_slug>/systems/sources/<source_id>",
        "campaign_systems_source_type_detail":
            "/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>",
        "campaign_systems_entry_detail":
            "/campaigns/<campaign_slug>/systems/entries/<entry_slug>",
    }
    rules = discover_rules()

    for endpoint, path in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["GET"]
        assert set(matches[0].methods) >= {"GET", "HEAD", "OPTIONS"}

    assert not any(rule.endpoint.startswith("systems.") for rule in rules)


def test_systems_management_routes_keep_one_bare_rule_and_implicit_options() -> None:
    expected = {
        "campaign_systems_control_panel_update_sources": (
            "/campaigns/<campaign_slug>/systems/control-panel/sources",
            "POST",
        ),
        "campaign_systems_control_panel_update_override": (
            "/campaigns/<campaign_slug>/systems/control-panel/overrides",
            "POST",
        ),
        "campaign_systems_control_panel_update_shared_core_permission": (
            "/campaigns/<campaign_slug>/systems/control-panel/shared-core-permission",
            "POST",
        ),
        "campaign_systems_control_panel_import_dnd5e": (
            "/campaigns/<campaign_slug>/systems/control-panel/imports/dnd5e",
            "POST",
        ),
        "campaign_systems_control_panel_edit_shared_entry": (
            "/campaigns/<campaign_slug>/systems/control-panel/shared-entries/<entry_slug>/edit",
            "GET",
        ),
        "campaign_systems_control_panel_update_shared_entry": (
            "/campaigns/<campaign_slug>/systems/control-panel/shared-entries/<entry_slug>",
            "POST",
        ),
        "campaign_systems_control_panel_create_custom_entry": (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries",
            "POST",
        ),
        "campaign_systems_control_panel_edit_custom_entry": (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/edit",
            "GET",
        ),
        "campaign_systems_control_panel_update_custom_entry": (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>",
            "POST",
        ),
        "campaign_systems_control_panel_archive_custom_entry": (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/archive",
            "POST",
        ),
        "campaign_systems_control_panel_restore_custom_entry": (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/restore",
            "POST",
        ),
    }
    rules = discover_rules()

    for endpoint, (path, method) in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        assert "OPTIONS" in matches[0].methods
        if method == "GET":
            assert "HEAD" in matches[0].methods
        else:
            assert "HEAD" not in matches[0].methods

    extracted_endpoints = set(expected) | {
        "campaign_systems_index",
        "campaign_systems_search",
        "campaign_systems_source_detail",
        "campaign_systems_source_type_detail",
        "campaign_systems_entry_detail",
    }
    assert sum(rule.endpoint in extracted_endpoints for rule in rules) == 16
    assert not any(rule.endpoint.startswith("systems.") for rule in rules)


def test_dm_content_mutation_routes_keep_one_bare_rule_and_implicit_options() -> None:
    expected = {
        "campaign_dm_content_upload_statblock":
            "/campaigns/<campaign_slug>/dm-content/statblocks",
        "campaign_dm_content_update_statblock":
            "/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>",
        "campaign_dm_content_delete_statblock":
            "/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>/delete",
        "campaign_dm_content_add_condition_definition":
            "/campaigns/<campaign_slug>/dm-content/conditions",
        "campaign_dm_content_update_condition_definition":
            "/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>",
        "campaign_dm_content_delete_condition_definition":
            "/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>/delete",
    }
    rules = discover_rules()

    for endpoint, path in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["POST"]
        assert "OPTIONS" in matches[0].methods

    assert not any(rule.endpoint.startswith("dm_content.") for rule in rules)


def test_publishing_mutation_routes_keep_one_legacy_rule_and_implicit_methods() -> None:
    expected = {
        "campaign_dm_content_edit_player_wiki_page": (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/edit",
            ["GET"],
        ),
        "campaign_dm_content_new_player_wiki_page_from_session_article": (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/session-articles/<int:article_id>/new",
            ["GET"],
        ),
        "campaign_dm_content_create_player_wiki_page": (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages",
            ["POST"],
        ),
        "campaign_dm_content_update_player_wiki_page": (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>",
            ["POST"],
        ),
        "campaign_dm_content_unpublish_player_wiki_page": (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/unpublish",
            ["POST"],
        ),
        "campaign_dm_content_delete_player_wiki_page": (
            "/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/delete",
            ["POST"],
        ),
    }
    rules = discover_rules()

    for endpoint, (path, methods) in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == methods
        assert "OPTIONS" in matches[0].methods
        if methods == ["GET"]:
            assert "HEAD" in matches[0].methods

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


def test_dm_content_mutations_record_scope_and_statblock_upload_system_gate() -> None:
    mutation_endpoints = {
        "campaign_dm_content_upload_statblock",
        "campaign_dm_content_update_statblock",
        "campaign_dm_content_delete_statblock",
        "campaign_dm_content_add_condition_definition",
        "campaign_dm_content_update_condition_definition",
        "campaign_dm_content_delete_condition_definition",
    }
    for endpoint in mutation_endpoints:
        entry = manifest_entry(endpoint, "POST")
        assert entry["access_policy"] == "campaign_manage_browser"
        assert entry["campaign_scope"] == "dm_content"
        assert entry["visibility_policy"] == "campaign_scope"
        assert entry["object_relationship_requirement"] == "campaign_manager"
        assert "effective DM Content-scope access" in entry["rationale"]

    upload_entry = manifest_entry("campaign_dm_content_upload_statblock", "POST")
    assert upload_entry["system_restriction"] == "dnd5e_only"
    for endpoint in mutation_endpoints - {"campaign_dm_content_upload_statblock"}:
        assert manifest_entry(endpoint, "POST")["system_restriction"] == "none"


def test_dm_content_mutation_metadata_matches_runtime_scope_and_system_gates() -> None:
    mutation_endpoints = {
        "campaign_dm_content_upload_statblock",
        "campaign_dm_content_update_statblock",
        "campaign_dm_content_delete_statblock",
        "campaign_dm_content_add_condition_definition",
        "campaign_dm_content_update_condition_definition",
        "campaign_dm_content_delete_condition_definition",
    }
    for endpoint in mutation_endpoints:
        function = app_function(endpoint)
        scope_decorators = [
            decorator
            for decorator in function.decorator_list
            if call_name(decorator) == "campaign_scope_access_required"
        ]
        assert len(scope_decorators) == 1
        assert len(scope_decorators[0].args) == 1
        assert isinstance(scope_decorators[0].args[0], ast.Constant)
        assert scope_decorators[0].args[0].value == "dm_content"

        manager_checks = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and call_name(node.test.operand) == "can_manage_campaign_dm_content"
        ]
        assert len(manager_checks) == 1
        assert any(
            call_name(node) == "abort"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == 403
            for node in ast.walk(manager_checks[0])
        )

    runtime_system_gates = {
        endpoint: sum(
            call_name(node) == "supports_dnd5e_statblock_upload"
            for node in ast.walk(app_function(endpoint))
        )
        for endpoint in mutation_endpoints
    }
    assert runtime_system_gates == {
        endpoint: int(endpoint == "campaign_dm_content_upload_statblock")
        for endpoint in mutation_endpoints
    }


def test_dm_content_read_policy_records_unfiltered_statblock_and_condition_disclosure() -> None:
    for endpoint in ("campaign_dm_content_view", "campaign_dm_content_subpage_view"):
        entry = manifest_entry(endpoint, "GET")
        assert entry["access_policy"] == "dm_content_read_browser"
        assert entry["campaign_scope"] == "dm_content"
        assert entry["visibility_policy"] == "campaign_scope"
        assert "statblock bodies" in entry["rationale"]
        assert "custom-condition names, descriptions, and counts" in entry["rationale"]
        assert "do not filter those records" in entry["rationale"]
        assert "Systems-manager authority" in entry["rationale"]


def test_dm_content_read_metadata_matches_runtime_record_and_controls_projection() -> None:
    function = app_function("build_campaign_dm_content_page_context")
    direct_assignments = {
        target.id: statement.value
        for statement in function.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        for target in statement.targets
    }
    assert call_name(direct_assignments["statblocks"]) == "list_statblocks"
    assert call_name(direct_assignments["custom_conditions"]) == "list_condition_definitions"

    systems_gates = [
        statement
        for statement in function.body
        if isinstance(statement, ast.If)
        and isinstance(statement.test, ast.Name)
        and statement.test.id == "can_manage_systems"
    ]
    assert len(systems_gates) == 1
    systems_gate_call_names = {
        name
        for node in ast.walk(systems_gates[0])
        if (name := call_name(node)) is not None
    }
    assert "build_campaign_systems_control_context" in systems_gate_call_names
    assert "list_campaign_source_states" in systems_gate_call_names
    assert "list_statblocks" not in systems_gate_call_names
    assert "list_condition_definitions" not in systems_gate_call_names

    returns = [statement for statement in function.body if isinstance(statement, ast.Return)]
    assert len(returns) == 1
    assert isinstance(returns[0].value, ast.Dict)
    returned_names = {
        key.value: value.id
        for key, value in zip(returns[0].value.keys, returns[0].value.values, strict=True)
        if isinstance(key, ast.Constant)
        and isinstance(key.value, str)
        and isinstance(value, ast.Name)
    }
    assert returned_names["dm_statblocks"] == "statblocks"
    assert returned_names["custom_condition_definitions"] == "custom_conditions"
    assert any(
        key is None
        and isinstance(value, ast.Name)
        and value.id == "systems_management_context"
        for key, value in zip(returns[0].value.keys, returns[0].value.values, strict=True)
    )


def test_systems_management_policies_record_scope_and_admin_boundaries() -> None:
    browser_endpoints = {
        "campaign_systems_control_panel_view": "GET",
        "campaign_systems_control_panel_update_sources": "POST",
        "campaign_systems_control_panel_update_override": "POST",
        "campaign_systems_control_panel_create_custom_entry": "POST",
        "campaign_systems_control_panel_edit_custom_entry": "GET",
        "campaign_systems_control_panel_update_custom_entry": "POST",
        "campaign_systems_control_panel_archive_custom_entry": "POST",
        "campaign_systems_control_panel_restore_custom_entry": "POST",
    }
    for endpoint, method in browser_endpoints.items():
        entry = manifest_entry(endpoint, method)
        assert entry["access_policy"] == "systems_manage_browser"
        assert entry["campaign_scope"] == "systems"
        assert entry["visibility_policy"] == "campaign_scope"
        assert entry["actor_access"]["campaign_dm"] == "conditional"
        assert entry["actor_access"]["app_admin"] == "allow"
        assert "effective Systems-scope access" in entry["rationale"]

    api_endpoints = {
        "api.systems_source_update": "PUT",
        "api.systems_entry_override_update": "PUT",
        "api.systems_custom_entry_create": "POST",
        "api.systems_custom_entry_update": "PUT",
        "api.systems_custom_entry_archive": "POST",
        "api.systems_custom_entry_restore": "POST",
        "api.systems_item_mechanics_import": "POST",
    }
    for endpoint, method in api_endpoints.items():
        entry = manifest_entry(endpoint, method)
        assert entry["access_policy"] == "systems_manage_api"
        assert entry["campaign_scope"] == "systems"
        assert entry["visibility_policy"] == "campaign_scope"
        assert entry["actor_access"]["campaign_dm"] == "conditional"
        assert entry["actor_access"]["app_admin"] == "allow"
        assert "effective Systems-scope access" in entry["rationale"]

    permission_entry = manifest_entry(
        "campaign_systems_control_panel_update_shared_core_permission",
        "POST",
    )
    assert permission_entry["access_policy"] == "campaign_admin_browser"
    assert permission_entry["actor_access"]["campaign_dm"] == "deny"
    assert permission_entry["actor_access"]["app_admin"] == "allow"
    assert permission_entry["object_relationship_requirement"] == "existing_campaign"
    assert permission_entry["denial_mode"] == "browser_sign_in_or_forbidden_or_not_found"

    for endpoint, method in (
        ("campaign_systems_control_panel_edit_shared_entry", "GET"),
        ("campaign_systems_control_panel_update_shared_entry", "POST"),
    ):
        entry = manifest_entry(endpoint, method)
        assert entry["access_policy"] == "systems_shared_editor_browser"
        assert entry["campaign_scope"] == "systems"
        assert entry["actor_access"]["campaign_dm"] == "conditional"
        assert "early app-admin branch intentionally bypasses" in entry["rationale"]
        assert "campaign DM requires effective Systems-scope access" in entry["rationale"]

    dm_content_entry = manifest_entry("api.dm_content_systems_state", "GET")
    assert dm_content_entry["access_policy"] == "dm_content_systems_manage_api"
    assert dm_content_entry["campaign_scope"] == "dm_content"
    assert dm_content_entry["visibility_policy"] == "campaign_scope"
    assert dm_content_entry["actor_access"]["campaign_dm"] == "conditional"
    assert "effective DM Content-scope admission" in dm_content_entry["rationale"]
    assert "effective Systems-scope access" in dm_content_entry["rationale"]
    assert "one scalar campaign_scope field" in dm_content_entry["rationale"]


def test_systems_entry_detail_policies_match_split_browser_and_api_admin_access() -> None:
    admin_or_enabled_entry = "enabled_systems_entry_or_real_app_admin"
    browser_entry = manifest_entry("campaign_systems_entry_detail", "GET")
    api_entry = manifest_entry("api.systems_entry_detail", "GET")

    assert browser_entry["access_policy"] == "systems_entry_read_browser"
    assert browser_entry["object_relationship_requirement"] == admin_or_enabled_entry
    assert browser_entry["system_restriction"] == "enabled_systems_source"
    assert browser_entry["denial_mode"] == "browser_sign_in_or_not_found"
    assert "The source must be enabled" in browser_entry["rationale"]

    assert api_entry["access_policy"] == "systems_entry_read_api"
    assert api_entry["object_relationship_requirement"] == admin_or_enabled_entry
    assert api_entry["system_restriction"] == admin_or_enabled_entry
    assert api_entry["denial_mode"] == "api_401_or_403_or_404"
    assert "even through a disabled source" in api_entry["rationale"]

    for entry in (browser_entry, api_entry):
        assert entry["actor_access"]["app_admin"] == "allow"
        assert entry["view_as_policy"] == "campaign_safe_reads_use_effective_actor"
        assert "View As replaces the effective actor" in entry["rationale"]

    assert {
        entry["endpoint"]
        for entry in build_manifest()["entries"]
        if admin_or_enabled_entry
        in {
            entry["object_relationship_requirement"],
            entry["system_restriction"],
        }
    } == {"campaign_systems_entry_detail", "api.systems_entry_detail"}

    access_helper = module_function("auth.py", "can_access_campaign_systems_entry")
    current_user_assignments = [
        statement
        for statement in access_helper.body
        if isinstance(statement, ast.Assign)
        and call_name(statement.value) == "get_current_user"
    ]
    admin_bypasses = [
        statement
        for statement in access_helper.body
        if isinstance(statement, ast.If)
        and any(
            isinstance(node, ast.Attribute) and node.attr == "is_admin"
            for node in ast.walk(statement.test)
        )
        and any(
            isinstance(node, ast.Return)
            and isinstance(node.value, ast.Constant)
            and node.value.value is True
            for node in ast.walk(statement)
        )
    ]
    assert len(current_user_assignments) == 1
    assert len(admin_bypasses) == 1
    assert current_user_assignments[0].lineno < admin_bypasses[0].lineno

    browser_guard = module_function("auth.py", "campaign_systems_entry_access_required")
    api_guard = module_function("api.py", "api_campaign_systems_entry_access_required")
    for guard in (browser_guard, api_guard):
        assert sum(
            call_name(node) == "can_access_campaign_systems_entry"
            for node in ast.walk(guard)
        ) == 1

    browser_context = app_function("build_campaign_systems_entry_context")
    source_state_aborts = [
        statement
        for statement in browser_context.body
        if isinstance(statement, ast.If)
        and any(
            isinstance(node, ast.Attribute) and node.attr == "is_enabled"
            for node in ast.walk(statement.test)
        )
        and any(
            call_name(node) == "abort"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == 404
            for node in ast.walk(statement)
        )
    ]
    assert len(source_state_aborts) == 1

    api_endpoint = module_function("systems_api_routes.py", "systems_entry_detail")
    assert sum(
        call_name(node) == "get_entry_by_slug_for_campaign"
        for node in ast.walk(api_endpoint)
    ) == 1


def test_dnd5e_browser_import_policy_matches_campaign_admin_runtime(
    client,
    sign_in,
    users,
) -> None:
    endpoint = "campaign_systems_control_panel_import_dnd5e"
    entry = manifest_entry(endpoint, "POST")
    assert entry["access_policy"] == "campaign_admin_browser"
    assert entry["owning_domain"] == "systems"
    assert entry["system_restriction"] == "dnd5e_only"
    assert entry["object_relationship_requirement"] == "existing_campaign"
    assert entry["actor_access"]["campaign_dm"] == "deny"
    assert entry["actor_access"]["app_admin"] == "allow"
    assert entry["denial_mode"] == "browser_sign_in_or_forbidden_or_not_found"

    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == "/campaigns/<campaign_slug>/systems/control-panel/imports/dnd5e"
    assert explicit_methods(matches[0]) == ["POST"]
    assert "OPTIONS" in matches[0].methods
    assert not any(rule.endpoint.startswith("systems.") for rule in discover_rules())

    function = app_function(endpoint)
    assert any(
        isinstance(decorator, ast.Name) and decorator.id == "login_required"
        for decorator in function.decorator_list
    )
    campaign_loads = [
        node
        for node in ast.walk(function)
        if call_name(node) == "load_campaign"
    ]
    systems_manager_checks = [
        node
        for node in ast.walk(function)
        if call_name(node) == "can_manage_campaign_systems"
    ]
    current_user_calls = [
        node
        for node in ast.walk(function)
        if call_name(node) == "get_current_user"
    ]
    admin_denials = [
        node
        for node in function.body
        if isinstance(node, ast.If)
        and any(
            isinstance(child, ast.Attribute) and child.attr == "is_admin"
            for child in ast.walk(node.test)
        )
    ]
    dnd5e_restrictions = [
        node
        for node in ast.walk(function)
        if call_name(node) == "supports_dnd5e_systems_import"
    ]
    assert len(campaign_loads) == 1
    assert len(systems_manager_checks) == 1
    assert len(current_user_calls) == 1
    assert len(admin_denials) == 1
    assert len(dnd5e_restrictions) == 1
    assert (
        campaign_loads[0].lineno
        < systems_manager_checks[0].lineno
        < current_user_calls[0].lineno
        < admin_denials[0].lineno
        < dnd5e_restrictions[0].lineno
    )

    sign_in(users["admin"]["email"], users["admin"]["password"])
    missing = client.post(
        "/campaigns/missing-campaign/systems/control-panel/imports/dnd5e",
        follow_redirects=False,
    )
    assert missing.status_code == 404


def test_systems_management_policy_metadata_matches_runtime_authority_checks() -> None:
    browser_endpoints = {
        "campaign_systems_control_panel_view",
        "campaign_systems_control_panel_update_sources",
        "campaign_systems_control_panel_update_override",
        "campaign_systems_control_panel_create_custom_entry",
        "campaign_systems_control_panel_edit_custom_entry",
        "campaign_systems_control_panel_update_custom_entry",
        "campaign_systems_control_panel_archive_custom_entry",
        "campaign_systems_control_panel_restore_custom_entry",
    }
    for endpoint in browser_endpoints:
        function = app_function(endpoint)
        assert sum(
            call_name(node) == "can_manage_campaign_systems"
            for node in ast.walk(function)
        ) == 1

    extracted_api_endpoints = {
        "systems_source_update",
        "systems_entry_override_update",
        "systems_custom_entry_create",
        "systems_custom_entry_update",
        "systems_custom_entry_archive",
        "systems_custom_entry_restore",
    }
    for endpoint in extracted_api_endpoints:
        function = module_function("systems_api_routes.py", endpoint)
        assert function.decorator_list == []

    api_endpoints = {"systems_item_mechanics_import"}
    for endpoint in api_endpoints:
        function = module_function("api.py", endpoint)
        assert any(
            isinstance(decorator, ast.Name)
            and decorator.id == "api_campaign_systems_management_required"
            for decorator in function.decorator_list
        )

    extracted_registration = module_function(
        "systems_api_routes.py",
        "register_systems_api_routes",
    )
    assert sum(
        call_name(node) == "systems_management_required"
        for node in ast.walk(extracted_registration)
    ) == 6
    assert sum(
        call_name(node) == "login_required"
        for node in ast.walk(extracted_registration)
    ) == 6

    api_manager = module_function("api.py", "api_campaign_systems_management_required")
    assert sum(
        call_name(node) == "can_manage_campaign_systems"
        for node in ast.walk(api_manager)
    ) == 1

    systems_manager = module_function("auth.py", "can_manage_campaign_systems")
    scope_calls = [
        node
        for node in ast.walk(systems_manager)
        if call_name(node) == "can_access_campaign_scope"
    ]
    assert len(scope_calls) == 1
    assert len(scope_calls[0].args) == 2
    assert isinstance(scope_calls[0].args[1], ast.Constant)
    assert scope_calls[0].args[1].value == "systems"
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "is_admin"
        for node in ast.walk(systems_manager)
    )
    assert any(
        call_name(node) == "get_campaign_role"
        for node in ast.walk(systems_manager)
    )

    shared_permission = module_function(
        "systems_routes.py",
        "campaign_systems_control_panel_update_shared_core_permission",
    )
    campaign_loads = [
        node
        for node in ast.walk(shared_permission)
        if call_name(node) == "load_campaign"
    ]
    admin_denials = [
        node
        for node in shared_permission.body
        if isinstance(node, ast.If)
        and any(
            isinstance(child, ast.Attribute) and child.attr == "is_admin"
            for child in ast.walk(node.test)
        )
    ]
    assert len(campaign_loads) == 1
    assert len(admin_denials) == 1
    assert campaign_loads[0].lineno < admin_denials[0].lineno
    assert any(
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Attribute)
        and node.operand.attr == "is_admin"
        for node in ast.walk(admin_denials[0].test)
    )

    for endpoint in (
        "campaign_systems_control_panel_edit_shared_entry",
        "campaign_systems_control_panel_update_shared_entry",
    ):
        assert sum(
            call_name(node) == "can_edit_shared_systems_entries"
            for node in ast.walk(module_function("systems_routes.py", endpoint))
        ) == 1
    shared_editor = module_function("auth.py", "can_edit_shared_systems_entries")
    shared_editor_calls = {
        name
        for node in ast.walk(shared_editor)
        if (name := call_name(node)) is not None
    }
    assert "can_manage_campaign_systems" in shared_editor_calls
    assert "get_campaign_role" in shared_editor_calls
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "is_admin"
        for node in ast.walk(shared_editor)
    )
    assert any(
        isinstance(node, ast.Attribute)
        and node.attr == "allow_dm_shared_core_entry_edits"
        for node in ast.walk(shared_editor)
    )
    admin_bypass = [
        node
        for node in shared_editor.body
        if isinstance(node, ast.If)
        and any(
            isinstance(child, ast.Attribute) and child.attr == "is_admin"
            for child in ast.walk(node.test)
        )
    ]
    systems_scope_gate = [
        node
        for node in shared_editor.body
        if isinstance(node, ast.If)
        and any(
            call_name(child) == "can_manage_campaign_systems"
            for child in ast.walk(node.test)
        )
    ]
    assert len(admin_bypass) == 1
    assert len(systems_scope_gate) == 1
    assert admin_bypass[0].lineno < systems_scope_gate[0].lineno
    assert any(
        isinstance(statement, ast.Return)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is True
        for statement in admin_bypass[0].body
    )

    dm_content_function = module_function("api.py", "dm_content_systems_state")
    scope_decorators = [
        decorator
        for decorator in dm_content_function.decorator_list
        if call_name(decorator) == "api_campaign_scope_access_required"
    ]
    assert len(scope_decorators) == 1
    assert isinstance(scope_decorators[0].args[0], ast.Constant)
    assert scope_decorators[0].args[0].value == "dm_content"
    payload_builder = module_function("api.py", "build_dm_content_systems_payload")
    systems_manager_gates = [
        node
        for node in ast.walk(payload_builder)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and call_name(node.test.operand) == "can_manage_campaign_systems"
    ]
    assert len(systems_manager_gates) == 1


def test_contract_json_is_canonical_lf_utf8_with_trailing_newline() -> None:
    for path in (POLICY_PATH, MANIFEST_PATH):
        raw = path.read_bytes()
        assert raw.endswith(b"\n")
        assert b"\r" not in raw
        assert json.loads(raw.decode("utf-8"))["schema_version"] == 1

    attributes = (Path(__file__).resolve().parents[1] / ".gitattributes").read_text(encoding="utf-8")
    assert "docs/contracts/*.json text eol=lf" in attributes.splitlines()
