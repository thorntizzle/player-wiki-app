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
    for filename in (
        "app.py",
        "character_controls_routes.py",
        "character_routes.py",
        "combat_routes.py",
        "dm_content_routes.py",
        "session_routes.py",
        "systems_routes.py",
    ):
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
        "app.py": 28,
        "api.py": 66,
        "admin.py": 14,
        "auth.py": 9,
        "character_api_routes.py": 0,
        "character_advanced_editor_api_routes.py": 0,
        "character_level_up_api_routes.py": 0,
        "character_progression_repair_api_routes.py": 0,
        "character_cultivation_api_routes.py": 0,
        "character_retraining_api_routes.py": 0,
        "character_controls_assignment_api_routes.py": 0,
        "character_controls_delete_api_routes.py": 0,
        "character_controls_delete_routes.py": 0,
        "character_equipment_definition_routes.py": 0,
        "character_equipment_state_routes.py": 0,
        "character_feature_state_routes.py": 0,
        "character_equipment_remove_routes.py": 0,
        "character_xianxia_dao_use_request_routes.py": 0,
        "character_xianxia_dao_use_record_routes.py": 0,
        "character_session_vitals_routes.py": 0,
        "character_session_resource_routes.py": 0,
        "character_session_spell_slots_routes.py": 0,
        "character_session_item_action_routes.py": 0,
        "character_session_inventory_routes.py": 0,
        "character_session_xianxia_inventory_routes.py": 0,
        "character_session_currency_routes.py": 0,
        "character_session_notes_routes.py": 0,
        "character_session_personal_routes.py": 0,
        "character_session_rest_routes.py": 0,
        "character_equipment_search_routes.py": 0,
        "character_spell_mutation_routes.py": 0,
        "character_spell_search_routes.py": 0,
        "character_controls_routes.py": 0,
        "character_create_routes.py": 0,
        "character_edit_routes.py": 0,
        "character_level_up_routes.py": 0,
        "character_xianxia_cultivation_routes.py": 0,
        "character_progression_repair_routes.py": 0,
        "character_retraining_routes.py": 0,
        "character_create_context_api_routes.py": 0,
        "character_create_submit_api_routes.py": 0,
        "character_xianxia_manual_import_api_routes.py": 0,
        "character_xianxia_manual_import_routes.py": 0,
        "character_inventory_api_routes.py": 0,
        "character_xianxia_inventory_add_api_routes.py": 0,
        "character_xianxia_inventory_item_update_api_routes.py": 0,
        "character_item_action_api_routes.py": 0,
        "character_list_api_routes.py": 0,
        "character_portrait_mutation_api_routes.py": 0,
        "character_rest_preview_api_routes.py": 0,
        "character_resource_api_routes.py": 0,
        "character_sheet_edit_api_routes.py": 0,
        "character_spell_slots_api_routes.py": 0,
        "character_vitals_api_routes.py": 0,
        "character_portrait_mutation_routes.py": 0,
        "character_routes.py": 0,
        "combat_api_routes.py": 0,
        "combat_routes.py": 0,
        "publishing_routes.py": 0,
        "dm_content_routes.py": 0,
        "session_routes.py": 0,
        "session_api_routes.py": 0,
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
        "combat_routes.py",
        "dm_content_routes.py",
        "publishing_routes.py",
        "session_routes.py",
        "systems_routes.py",
    }
    assert {name for name, text in source_text.items() if "add_url_rule" in text} == {
        "combat_api_routes.py",
        "character_advanced_editor_api_routes.py",
        "character_level_up_api_routes.py",
        "character_progression_repair_api_routes.py",
        "character_cultivation_api_routes.py",
        "character_retraining_api_routes.py",
        "character_api_routes.py",
        "character_controls_assignment_api_routes.py",
        "character_controls_delete_api_routes.py",
        "character_controls_delete_routes.py",
        "character_equipment_definition_routes.py",
        "character_equipment_state_routes.py",
        "character_feature_state_routes.py",
        "character_equipment_remove_routes.py",
        "character_xianxia_dao_use_request_routes.py",
        "character_xianxia_dao_use_record_routes.py",
        "character_session_vitals_routes.py",
        "character_session_xianxia_active_state_routes.py",
        "character_session_resource_routes.py",
        "character_session_spell_slots_routes.py",
        "character_session_item_action_routes.py",
        "character_session_inventory_routes.py",
        "character_session_xianxia_inventory_routes.py",
        "character_session_currency_routes.py",
        "character_session_notes_routes.py",
        "character_session_personal_routes.py",
        "character_session_rest_routes.py",
        "character_equipment_search_routes.py",
        "character_spell_mutation_routes.py",
        "character_spell_search_routes.py",
        "character_controls_routes.py",
        "character_create_routes.py",
        "character_edit_routes.py",
        "character_level_up_routes.py",
        "character_xianxia_cultivation_routes.py",
        "character_progression_repair_routes.py",
        "character_retraining_routes.py",
        "character_create_context_api_routes.py",
        "character_create_submit_api_routes.py",
        "character_xianxia_manual_import_api_routes.py",
        "character_xianxia_manual_import_routes.py",
            "character_inventory_api_routes.py",
            "character_xianxia_inventory_add_api_routes.py",
            "character_xianxia_inventory_item_update_api_routes.py",
            "character_item_action_api_routes.py",
        "character_list_api_routes.py",
        "character_portrait_mutation_api_routes.py",
        "character_rest_preview_api_routes.py",
        "character_resource_api_routes.py",
        "character_sheet_edit_api_routes.py",
        "character_spell_slots_api_routes.py",
        "character_vitals_api_routes.py",
        "character_portrait_mutation_routes.py",
        "character_routes.py",
        "combat_routes.py",
        "dm_content_routes.py",
        "publishing_routes.py",
        "session_routes.py",
        "session_api_routes.py",
        "systems_api_routes.py",
        "systems_routes.py",
    }


def test_character_edit_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_edit_view"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/edit"
    )
    assert explicit_methods(matches[0]) == ["GET", "POST"]
    assert set(matches[0].methods) == {"GET", "HEAD", "POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_edit_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_edit_routes.py", "register_character_edit_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_retraining_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_retraining_view"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/retraining"
    )
    assert explicit_methods(matches[0]) == ["GET", "POST"]
    assert set(matches[0].methods) == {"GET", "HEAD", "POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_retraining_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_retraining_routes.py", "register_character_retraining_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_level_up_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_level_up_view"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/level-up"
    )
    assert explicit_methods(matches[0]) == ["GET", "POST"]
    assert set(matches[0].methods) == {"GET", "HEAD", "POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_level_up_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_level_up_routes.py", "register_character_level_up_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_progression_repair_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_progression_repair_view"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair"
    )
    assert explicit_methods(matches[0]) == ["GET", "POST"]
    assert set(matches[0].methods) == {"GET", "HEAD", "POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_progression_repair_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_progression_repair_routes.py",
        "register_character_progression_repair_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_xianxia_cultivation_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_xianxia_cultivation_view"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/cultivation"
    )
    assert explicit_methods(matches[0]) == ["GET", "POST"]
    assert set(matches[0].methods) == {"GET", "HEAD", "POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_xianxia_cultivation_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_xianxia_cultivation_routes.py",
        "register_character_xianxia_cultivation_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_api_character_level_up_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "api.character_level_up_read": ("GET",),
        "api.character_level_up_submit": ("POST",),
    }
    rules = discover_rules()
    for endpoint, methods in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == (
            "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up"
        )
        assert explicit_methods(matches[0]) == list(methods)

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name in {"character_level_up_read", "character_level_up_submit"}
        for node in ast.walk(api_tree)
    )
    handlers = {
        endpoint.removeprefix("api."): module_function(
            "character_level_up_api_routes.py", endpoint.removeprefix("api.")
        )
        for endpoint in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_level_up_api_routes.py",
        "register_character_level_up_api_routes",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_api_character_progression_repair_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "api.character_progression_repair_read": ("GET",),
        "api.character_progression_repair_submit": ("POST",),
    }
    rules = discover_rules()
    for endpoint, methods in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == (
            "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair"
        )
        assert explicit_methods(matches[0]) == list(methods)

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name
        in {
            "character_progression_repair_read",
            "character_progression_repair_submit",
        }
        for node in ast.walk(api_tree)
    )
    handlers = {
        endpoint.removeprefix("api."): module_function(
            "character_progression_repair_api_routes.py",
            endpoint.removeprefix("api."),
        )
        for endpoint in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_progression_repair_api_routes.py",
        "register_character_progression_repair_api_routes",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_api_character_cultivation_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "api.character_cultivation_read": ("GET",),
        "api.character_cultivation_action": ("POST",),
    }
    rules = discover_rules()
    for endpoint, methods in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == (
            "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/cultivation"
        )
        assert explicit_methods(matches[0]) == list(methods)

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name in {"character_cultivation_read", "character_cultivation_action"}
        for node in ast.walk(api_tree)
    )
    handlers = {
        endpoint.removeprefix("api."): module_function(
            "character_cultivation_api_routes.py", endpoint.removeprefix("api.")
        )
        for endpoint in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_cultivation_api_routes.py",
        "register_character_cultivation_api_routes",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_character_portrait_mutation_routes_keep_contract_and_module_ownership() -> None:
    expected_posts = {
        "character_personal_portrait":
            "/campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait",
        "character_personal_portrait_remove":
            "/campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait/remove",
    }
    rules = discover_rules()

    for endpoint, path in expected_posts.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["POST"]
        assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected_posts
        for node in ast.walk(app_tree)
    )
    handlers = {
        endpoint: module_function("character_portrait_mutation_routes.py", endpoint)
        for endpoint in expected_posts
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_portrait_mutation_routes.py",
        "register_character_portrait_mutation_routes",
    )
    assert {
        node.name for node in registrar.body if isinstance(node, ast.FunctionDef)
    } == set(expected_posts)
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_character_create_context_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_create_context"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == f"api.{endpoint}"]
    assert len(matches) == 1
    assert matches[0].rule == "/api/v1/campaigns/<campaign_slug>/characters/create"
    assert explicit_methods(matches[0]) == ["GET"]
    assert set(matches[0].methods) == {"GET", "HEAD", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(api_tree)
    )

    handler = module_function("character_create_context_api_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_create_context_api_routes.py",
        "register_character_create_context_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_create_submit_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_create_submit"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == f"api.{endpoint}"]
    assert len(matches) == 1
    assert matches[0].rule == "/api/v1/campaigns/<campaign_slug>/characters/create"
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(api_tree)
    )

    handler = module_function("character_create_submit_api_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_create_submit_api_routes.py",
        "register_character_create_submit_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_advanced_editor_api_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "character_advanced_editor_read": "GET",
        "character_advanced_editor_update": "PUT",
    }
    path = "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor"
    rules = discover_rules()

    for endpoint, method in expected.items():
        matches = [rule for rule in rules if rule.endpoint == f"api.{endpoint}"]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        expected_methods = {method, "OPTIONS"}
        if method == "GET":
            expected_methods.add("HEAD")
        assert set(matches[0].methods) == expected_methods

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected
        for node in ast.walk(api_tree)
    )
    handlers = {
        name: module_function("character_advanced_editor_api_routes.py", name)
        for name in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_advanced_editor_api_routes.py",
        "register_character_advanced_editor_api_routes",
    )
    assert {
        node.name for node in registrar.body if isinstance(node, ast.FunctionDef)
    } == set(expected)
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_character_retraining_api_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "character_retraining_read": "GET",
        "character_retraining_submit": "POST",
    }
    path = "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining"
    rules = discover_rules()

    for endpoint, method in expected.items():
        matches = [rule for rule in rules if rule.endpoint == f"api.{endpoint}"]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        expected_methods = {method, "OPTIONS"}
        if method == "GET":
            expected_methods.add("HEAD")
        assert set(matches[0].methods) == expected_methods

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected
        for node in ast.walk(api_tree)
    )
    handlers = {
        name: module_function("character_retraining_api_routes.py", name)
        for name in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_retraining_api_routes.py",
        "register_character_retraining_api_routes",
    )
    assert {
        node.name for node in registrar.body if isinstance(node, ast.FunctionDef)
    } == set(expected)
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_character_xianxia_manual_import_api_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "character_xianxia_manual_import_context": "GET",
        "character_xianxia_manual_import_submit": "POST",
    }
    rules = discover_rules()
    path = "/api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual"

    for endpoint, method in expected.items():
        matches = [rule for rule in rules if rule.endpoint == f"api.{endpoint}"]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        expected_methods = {method, "OPTIONS"}
        if method == "GET":
            expected_methods.add("HEAD")
        assert set(matches[0].methods) == expected_methods

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected
        for node in ast.walk(api_tree)
    )
    handlers = {
        endpoint: module_function(
            "character_xianxia_manual_import_api_routes.py", endpoint
        )
        for endpoint in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_xianxia_manual_import_api_routes.py",
        "register_character_xianxia_manual_import_api_routes",
    )
    assert {
        node.name for node in registrar.body if isinstance(node, ast.FunctionDef)
    } == set(expected)
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_character_xianxia_manual_import_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_import_xianxia_manual_view"
    path = "/campaigns/<campaign_slug>/characters/import/xianxia-manual"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == path
    assert explicit_methods(matches[0]) == ["GET", "POST"]
    assert set(matches[0].methods) == {"GET", "HEAD", "POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function(
        "character_xianxia_manual_import_routes.py", endpoint
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_xianxia_manual_import_routes.py",
        "register_character_xianxia_manual_import_route",
    )
    assert {
        node.name for node in registrar.body if isinstance(node, ast.FunctionDef)
    } == {endpoint}
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_create_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_create_view"
    path = "/campaigns/<campaign_slug>/characters/new"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == path
    assert explicit_methods(matches[0]) == ["GET", "POST"]
    assert set(matches[0].methods) == {"GET", "HEAD", "POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_create_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_create_routes.py", "register_character_create_route"
    )
    assert {
        node.name for node in registrar.body if isinstance(node, ast.FunctionDef)
    } == {endpoint}
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_portrait_mutation_api_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "api.character_portrait_upsert": (
            "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait",
            "PUT",
        ),
        "api.character_portrait_delete": (
            "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/portrait",
            "DELETE",
        ),
    }
    rules = discover_rules()

    for endpoint, (path, method) in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        assert set(matches[0].methods) == {method, "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler_names = {endpoint.removeprefix("api.") for endpoint in expected}
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in handler_names
        for node in ast.walk(api_tree)
    )
    handlers = {
        name: module_function("character_portrait_mutation_api_routes.py", name)
        for name in handler_names
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_portrait_mutation_api_routes.py",
        "register_character_portrait_mutation_api_routes",
    )
    assert {
        node.name for node in registrar.body if isinstance(node, ast.FunctionDef)
    } == handler_names
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_character_rest_preview_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_rest_preview"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "rest-preview/<rest_type>"
    )
    assert explicit_methods(matches[0]) == ["GET"]
    assert set(matches[0].methods) == {"GET", "HEAD", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_rest_preview"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_rest_preview_api_routes.py", "character_rest_preview"
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_rest_preview_api_routes.py",
        "register_character_rest_preview_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_sheet_edit_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_sheet_edit_update"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit"
    )
    assert explicit_methods(matches[0]) == ["PATCH"]
    assert set(matches[0].methods) == {"PATCH", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_sheet_edit_update"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_sheet_edit_api_routes.py", "character_sheet_edit_update"
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_sheet_edit_api_routes.py",
        "register_character_sheet_edit_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_vitals_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_vitals_update"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals"
    )
    assert explicit_methods(matches[0]) == ["PATCH"]
    assert set(matches[0].methods) == {"PATCH", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_vitals_update"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_vitals_api_routes.py", "character_vitals_update"
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_vitals_api_routes.py", "register_character_vitals_api_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_resource_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_resource_update"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>"
    )
    assert explicit_methods(matches[0]) == ["PATCH"]
    assert set(matches[0].methods) == {"PATCH", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_resource_update"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_resource_api_routes.py", "character_resource_update"
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_resource_api_routes.py", "register_character_resource_api_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_spell_slots_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_spell_slots_update"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/spell-slots/<int:level>"
    )
    assert explicit_methods(matches[0]) == ["PATCH"]
    assert set(matches[0].methods) == {"PATCH", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_spell_slots_update"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_spell_slots_api_routes.py", "character_spell_slots_update"
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_spell_slots_api_routes.py",
        "register_character_spell_slots_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_item_action_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_item_action_use"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/item-actions/<action_id>/use"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_item_action_use"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_item_action_api_routes.py", "character_item_action_use"
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_item_action_api_routes.py",
        "register_character_item_action_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_inventory_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_inventory_update"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/inventory/<item_id>"
    )
    assert explicit_methods(matches[0]) == ["PATCH"]
    assert set(matches[0].methods) == {"PATCH", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_inventory_update"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_inventory_api_routes.py", "character_inventory_update"
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_inventory_api_routes.py",
        "register_character_inventory_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_xianxia_inventory_add_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_xianxia_inventory_add"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/xianxia-inventory"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_inventory_add"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_xianxia_inventory_add_api_routes.py",
        "character_xianxia_inventory_add",
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_xianxia_inventory_add_api_routes.py",
        "register_character_xianxia_inventory_add_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_xianxia_inventory_item_update_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.character_xianxia_inventory_item_update"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/xianxia-inventory/<item_id>"
    )
    assert explicit_methods(matches[0]) == ["PATCH"]
    assert set(matches[0].methods) == {"PATCH", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "character_xianxia_inventory_item_update"
        for node in ast.walk(api_tree)
    )
    handler = module_function(
        "character_xianxia_inventory_item_update_api_routes.py",
        "character_xianxia_inventory_item_update",
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_xianxia_inventory_item_update_api_routes.py",
        "register_character_xianxia_inventory_item_update_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_controls_assignment_routes_keep_contract_and_module_ownership() -> None:
    expected_posts = {
        "character_controls_assignment":
            "/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment",
        "character_controls_assignment_remove":
            "/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment/remove",
    }
    rules = discover_rules()

    for endpoint, path in expected_posts.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["POST"]
        assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected_posts
        for node in ast.walk(app_tree)
    )

    handlers = {
        endpoint: module_function("character_controls_routes.py", endpoint)
        for endpoint in expected_posts
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())

    registrar = module_function(
        "character_controls_routes.py",
        "register_character_controls_assignment_routes",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_character_controls_delete_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_controls_delete"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/controls/delete"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_controls_delete_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_controls_delete_routes.py",
        "register_character_controls_delete_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_equipment_search_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_equipment_systems_item_search"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "equipment/systems-items/search"
    )
    assert explicit_methods(matches[0]) == ["GET"]
    assert set(matches[0].methods) == {"GET", "HEAD", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_equipment_search_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_equipment_search_routes.py",
        "register_character_equipment_search_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_equipment_definition_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "character_equipment_add_systems": "equipment/add-systems",
        "character_equipment_add_manual": "equipment/add-manual",
        "character_equipment_add_campaign_item": "equipment/add-campaign-item",
        "character_equipment_update": "equipment/<item_id>/update",
    }
    rules = discover_rules()
    for endpoint, suffix in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == (
            "/campaigns/<campaign_slug>/characters/<character_slug>/" + suffix
        )
        assert explicit_methods(matches[0]) == ["POST"]
        assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected
        for node in ast.walk(app_tree)
    )

    handlers = {
        endpoint: module_function("character_equipment_definition_routes.py", endpoint)
        for endpoint in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_equipment_definition_routes.py",
        "register_character_equipment_definition_routes",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 4


def test_character_equipment_state_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_equipment_state_update"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "equipment/<item_id>/state"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_equipment_state_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_equipment_state_routes.py",
        "register_character_equipment_state_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_feature_state_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_feature_state_update"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "feature-states/<feature_key>"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_feature_state_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_feature_state_routes.py",
        "register_character_feature_state_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_equipment_remove_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_equipment_remove"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "equipment/<item_id>/remove"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_equipment_remove_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_equipment_remove_routes.py",
        "register_character_equipment_remove_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_xianxia_dao_request_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_xianxia_dao_immolating_use_request"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "xianxia/dao-immolating-use-requests"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_xianxia_dao_use_request_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_xianxia_dao_use_request_routes.py",
        "register_character_xianxia_dao_use_request_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_xianxia_dao_record_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_xianxia_dao_immolating_use_record"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "xianxia/dao-immolating-use-records"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_xianxia_dao_use_record_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_xianxia_dao_use_record_routes.py",
        "register_character_xianxia_dao_use_record_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_vitals_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_vitals"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_session_vitals_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_session_vitals_routes.py",
        "register_character_session_vitals_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_xianxia_active_state_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_xianxia_active_state"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/xianxia-active-state"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function(
        "character_session_xianxia_active_state_routes.py", endpoint
    )
    assert handler.decorator_list == []
    registrar = module_function(
        "character_session_xianxia_active_state_routes.py",
        "register_character_session_xianxia_active_state_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_resource_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_resource"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/resources/<resource_id>"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_session_resource_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_session_resource_routes.py",
        "register_character_session_resource_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_spell_slots_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_spell_slots"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/spell-slots/<int:level>"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_session_spell_slots_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_session_spell_slots_routes.py",
        "register_character_session_spell_slots_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_item_action_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_item_action_use"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/item-actions/<action_id>/use"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_session_item_action_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_session_item_action_routes.py",
        "register_character_session_item_action_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_inventory_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_inventory"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/inventory/<item_id>"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_session_inventory_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_session_inventory_routes.py",
        "register_character_session_inventory_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_xianxia_inventory_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "character_session_xianxia_inventory_add": (
            "/campaigns/<campaign_slug>/characters/<character_slug>/"
            "session/xianxia-inventory/add"
        ),
        "character_session_xianxia_inventory_update": (
            "/campaigns/<campaign_slug>/characters/<character_slug>/"
            "session/xianxia-inventory/<item_id>/update"
        ),
        "character_session_xianxia_inventory_remove": (
            "/campaigns/<campaign_slug>/characters/<character_slug>/"
            "session/xianxia-inventory/<item_id>/remove"
        ),
        "character_session_xianxia_inventory_equipped": (
            "/campaigns/<campaign_slug>/characters/<character_slug>/"
            "session/xianxia-inventory/<item_id>/equipped"
        ),
    }
    rules = discover_rules()
    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))

    for endpoint, path in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["POST"]
        assert set(matches[0].methods) == {"POST", "OPTIONS"}
        assert not any(
            isinstance(node, ast.FunctionDef) and node.name == endpoint
            for node in ast.walk(app_tree)
        )
        handler = module_function(
            "character_session_xianxia_inventory_routes.py",
            endpoint,
        )
        assert handler.decorator_list == []

    registrar = module_function(
        "character_session_xianxia_inventory_routes.py",
        "register_character_session_xianxia_inventory_routes",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 4


def test_character_session_currency_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_currency"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/currency"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_session_currency_routes.py", endpoint)
    assert handler.decorator_list == []

    registrar = module_function(
        "character_session_currency_routes.py",
        "register_character_session_currency_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_notes_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_notes"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/notes"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_session_notes_routes.py", endpoint)
    assert handler.decorator_list == []

    registrar = module_function(
        "character_session_notes_routes.py",
        "register_character_session_notes_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_personal_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_personal"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/personal"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_session_personal_routes.py", endpoint)
    assert handler.decorator_list == []

    registrar = module_function(
        "character_session_personal_routes.py",
        "register_character_session_personal_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_session_rest_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_session_rest"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>"
    )
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )
    handler = module_function("character_session_rest_routes.py", endpoint)
    assert handler.decorator_list == []

    registrar = module_function(
        "character_session_rest_routes.py",
        "register_character_session_rest_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_spell_search_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_spell_search"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "spellcasting/spells/search"
    )
    assert explicit_methods(matches[0]) == ["GET"]
    assert set(matches[0].methods) == {"GET", "HEAD", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(app_tree)
    )

    handler = module_function("character_spell_search_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_spell_search_routes.py",
        "register_character_spell_search_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_character_spell_mutation_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "character_spell_add": "add",
        "character_spell_update": "update",
        "character_spell_remove": "remove",
    }
    rules = discover_rules()
    for endpoint, suffix in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == (
            "/campaigns/<campaign_slug>/characters/<character_slug>/"
            f"spellcasting/{suffix}"
        )
        assert explicit_methods(matches[0]) == ["POST"]
        assert set(matches[0].methods) == {"POST", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected
        for node in ast.walk(app_tree)
    )

    handlers = {
        endpoint: module_function("character_spell_mutation_routes.py", endpoint)
        for endpoint in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())
    registrar = module_function(
        "character_spell_mutation_routes.py",
        "register_character_spell_mutation_routes",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 3


def test_character_controls_assignment_api_routes_keep_module_ownership() -> None:
    expected = {
        "character_controls_assignment_update": "POST",
        "character_controls_assignment_delete": "DELETE",
    }
    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in expected
        for node in ast.walk(api_tree)
    )

    handlers = {
        endpoint: module_function(
            "character_controls_assignment_api_routes.py", endpoint
        )
        for endpoint in expected
    }
    assert all(handler.decorator_list == [] for handler in handlers.values())

    registrar = module_function(
        "character_controls_assignment_api_routes.py",
        "register_character_controls_assignment_api_routes",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_character_controls_delete_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "character_controls_delete"
    rules = discover_rules()
    matches = [rule for rule in rules if rule.endpoint == f"api.{endpoint}"]
    assert len(matches) == 1
    assert matches[0].rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/controls"
    )
    assert explicit_methods(matches[0]) == ["DELETE"]
    assert set(matches[0].methods) == {"DELETE", "OPTIONS"}

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == endpoint
        for node in ast.walk(api_tree)
    )

    handler = module_function("character_controls_delete_api_routes.py", endpoint)
    assert handler.decorator_list == []
    registrar = module_function(
        "character_controls_delete_api_routes.py",
        "register_character_controls_delete_api_route",
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1


def test_session_routes_keep_legacy_contract_and_module_ownership() -> None:
    expected_gets = {
        "campaign_session_view": "/campaigns/<campaign_slug>/session",
        "campaign_session_dm_view": "/campaigns/<campaign_slug>/session/dm",
        "campaign_session_live_state": "/campaigns/<campaign_slug>/session/live-state",
        "campaign_session_search_article_sources":
            "/campaigns/<campaign_slug>/session/article-sources/search",
        "campaign_session_wiki_lookup_search":
            "/campaigns/<campaign_slug>/session/wiki-lookup/search",
        "campaign_session_wiki_lookup_preview":
            "/campaigns/<campaign_slug>/session/wiki-lookup/preview",
        "campaign_session_convert_article_view":
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>/convert",
        "campaign_session_log_view":
            "/campaigns/<campaign_slug>/session/logs/<int:session_id>",
        "campaign_session_article_image":
            "/campaigns/<campaign_slug>/session-article-images/<int:article_id>",
    }
    expected_posts = {
        "campaign_session_post_message":
            "/campaigns/<campaign_slug>/session/messages",
        "campaign_session_start": "/campaigns/<campaign_slug>/session/start",
        "campaign_session_close": "/campaigns/<campaign_slug>/session/close",
        "campaign_session_log_delete":
            "/campaigns/<campaign_slug>/session/logs/<int:session_id>/delete",
        "campaign_session_create_article":
            "/campaigns/<campaign_slug>/session/articles",
        "campaign_session_update_article":
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>",
        "campaign_session_convert_article_submit":
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>/convert",
        "campaign_session_reveal_article":
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>/reveal",
        "campaign_session_delete_article":
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>/delete",
        "campaign_session_clear_revealed_articles":
            "/campaigns/<campaign_slug>/session/articles/clear-revealed",
    }
    rules = discover_rules()

    for endpoint, path in expected_gets.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["GET"]
        assert set(matches[0].methods) >= {"GET", "HEAD", "OPTIONS"}

    for endpoint, path in expected_posts.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["POST"]
        assert set(matches[0].methods) == {"POST", "OPTIONS"}

    assert not any(rule.endpoint.startswith("session.") for rule in rules)
    assert len([rule for rule in rules if rule.endpoint in expected_gets]) == 9
    assert len([rule for rule in rules if rule.endpoint in expected_posts]) == 10

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name in {*expected_gets, *expected_posts}
        for node in ast.walk(app_tree)
    )
    for handler_name in {*expected_gets, *expected_posts}:
        function = module_function("session_routes.py", handler_name)
        assert len(function.decorator_list) == 1
        assert call_name(function.decorator_list[0]) == "campaign_scope_access_required"
        assert len(function.decorator_list[0].args) == 1
        assert isinstance(function.decorator_list[0].args[0], ast.Constant)
        assert function.decorator_list[0].args[0].value == "session"


def test_combat_extracted_routes_keep_legacy_contract_and_module_ownership() -> None:
    expected_gets = {
        "campaign_combat_view": "/campaigns/<campaign_slug>/combat",
        "campaign_combat_live_state": "/campaigns/<campaign_slug>/combat/live-state",
        "campaign_combat_dm_view": "/campaigns/<campaign_slug>/combat/dm",
        "campaign_combat_dm_live_state": "/campaigns/<campaign_slug>/combat/dm/live-state",
        "campaign_combat_status_view": "/campaigns/<campaign_slug>/combat/status",
        "campaign_combat_status_live_state":
            "/campaigns/<campaign_slug>/combat/status/live-state",
    }
    expected_posts = {
        "campaign_combat_advance_turn": "/campaigns/<campaign_slug>/combat/advance-turn",
        "campaign_combat_set_current_turn":
            "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/set-current",
        "campaign_combat_update_turn_value":
            "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/turn",
        "campaign_combat_update_player_detail_visibility":
            "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/player-detail-visibility",
        "campaign_combat_add_player":
            "/campaigns/<campaign_slug>/combat/player-combatants",
        "campaign_combat_add_npc":
            "/campaigns/<campaign_slug>/combat/npc-combatants",
        "campaign_combat_add_condition":
            "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/conditions",
        "campaign_combat_delete_condition":
            "/campaigns/<campaign_slug>/combat/conditions/<int:condition_id>/delete",
        "campaign_combat_update_condition":
            "/campaigns/<campaign_slug>/combat/conditions/<int:condition_id>",
        "campaign_combat_clear": "/campaigns/<campaign_slug>/combat/clear",
        "campaign_combat_delete_combatant":
            "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/delete",
    }
    rules = discover_rules()

    for endpoint, path in expected_gets.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["GET"]
        assert set(matches[0].methods) >= {"GET", "HEAD", "OPTIONS"}

    for endpoint, path in expected_posts.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["POST"]
        assert set(matches[0].methods) == {"POST", "OPTIONS"}

    assert not any(rule.endpoint.startswith("combat.") for rule in rules)
    assert len(
        [
            rule
            for rule in rules
            if rule.endpoint in {*expected_gets, *expected_posts}
        ]
    ) == 17

    combat_browser_entries = [
        entry
        for entry in cached_manifest()["entries"]
        if entry["surface"] == "browser" and entry["owning_domain"] == "combat"
    ]
    assert len(combat_browser_entries) == 29
    assert sum(entry["method"] == "GET" for entry in combat_browser_entries) == 9
    assert sum(entry["method"] == "POST" for entry in combat_browser_entries) == 20

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name in {*expected_gets, *expected_posts}
        for node in ast.walk(app_tree)
    )
    update_resources = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "campaign_combat_update_resources"
    )
    visibility_registration = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_update_player_detail_visibility_route"
    )
    condition_registration = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_condition_routes"
    )
    assert (
        update_resources.end_lineno
        < visibility_registration.lineno
        < condition_registration.lineno
    )
    systems_search = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "campaign_combat_search_systems_monsters"
    )
    basic_seeding_registration = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_basic_seeding_routes"
    )
    statblock_add = next(
        node
        for node in ast.walk(app_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "campaign_combat_add_statblock_npc"
    )
    assert (
        systems_search.end_lineno
        < basic_seeding_registration.lineno
        < statblock_add.lineno
    )
    for handler_name in {*expected_gets, *expected_posts}:
        function = module_function("combat_routes.py", handler_name)
        assert len(function.decorator_list) == 1
        assert call_name(function.decorator_list[0]) == "campaign_scope_access_required"
        assert len(function.decorator_list[0].args) == 1
        assert isinstance(function.decorator_list[0].args[0], ast.Constant)
        assert function.decorator_list[0].args[0].value == "combat"

    registration_function = module_function(
        "combat_routes.py",
        "_register_legacy_endpoints",
    )
    registration_assignments = {
        target.id: statement.value
        for statement in registration_function.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    registrations = registration_assignments["registrations"]
    assert isinstance(registrations, ast.Tuple)
    assert len(registrations.elts) == 6
    assert [
        (registration.elts[1].value, registration.elts[0].value)
        for registration in registrations.elts
        if isinstance(registration, ast.Tuple)
        and isinstance(registration.elts[0], ast.Constant)
        and isinstance(registration.elts[1], ast.Constant)
    ] == list(expected_gets.items())
    status_live_function = module_function(
        "combat_routes.py",
        "campaign_combat_status_live_state",
    )
    assert isinstance(status_live_function.body[0], ast.If)
    assert call_name(status_live_function.body[0].test.operand) == "can_manage_campaign_combat"
    add_url_rule_calls = [
        node
        for node in ast.walk(registration_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(add_url_rule_calls) == 1
    methods = next(
        keyword.value
        for keyword in add_url_rule_calls[0].keywords
        if keyword.arg == "methods"
    )
    assert isinstance(methods, ast.Tuple)
    assert [element.value for element in methods.elts] == ["GET"]

    post_registrars = {
        "campaign_combat_advance_turn": "register_combat_advance_turn_route",
        "campaign_combat_clear": "register_combat_clear_route",
        "campaign_combat_set_current_turn": "register_combat_set_current_turn_route",
        "campaign_combat_update_turn_value": "register_combat_update_turn_value_route",
        "campaign_combat_update_player_detail_visibility":
            "register_combat_update_player_detail_visibility_route",
        "campaign_combat_delete_combatant": "register_combat_delete_combatant_route",
    }
    for endpoint, registrar_name in post_registrars.items():
        registrar = module_function("combat_routes.py", registrar_name)
        add_url_rule_calls = [
            node
            for node in ast.walk(registrar)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_url_rule"
        ]
        assert len(add_url_rule_calls) == 1
        registration = add_url_rule_calls[0]
        assert len(registration.args) == 1
        assert isinstance(registration.args[0], ast.Constant)
        assert registration.args[0].value == expected_posts[endpoint]
        keyword_values = {
            keyword.arg: keyword.value
            for keyword in registration.keywords
        }
        assert isinstance(keyword_values["endpoint"], ast.Constant)
        assert keyword_values["endpoint"].value == endpoint
        assert isinstance(keyword_values["view_func"], ast.Name)
        assert keyword_values["view_func"].id == endpoint
        assert isinstance(keyword_values["methods"], ast.Tuple)
        assert [element.value for element in keyword_values["methods"].elts] == ["POST"]

    basic_seeding_registrar = module_function(
        "combat_routes.py",
        "register_combat_basic_seeding_routes",
    )
    basic_seeding_assignments = {
        target.id: statement.value
        for statement in basic_seeding_registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    basic_seeding_registrations = basic_seeding_assignments["registrations"]
    assert isinstance(basic_seeding_registrations, ast.Tuple)
    assert len(basic_seeding_registrations.elts) == 2
    assert [
        (registration.elts[1].value, registration.elts[0].value)
        for registration in basic_seeding_registrations.elts
        if isinstance(registration, ast.Tuple)
        and isinstance(registration.elts[0], ast.Constant)
        and isinstance(registration.elts[1], ast.Constant)
    ] == [
        (
            "campaign_combat_add_player",
            expected_posts["campaign_combat_add_player"],
        ),
        (
            "campaign_combat_add_npc",
            expected_posts["campaign_combat_add_npc"],
        ),
    ]
    basic_seeding_add_url_rule_calls = [
        node
        for node in ast.walk(basic_seeding_registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(basic_seeding_add_url_rule_calls) == 1
    basic_seeding_methods = next(
        keyword.value
        for keyword in basic_seeding_add_url_rule_calls[0].keywords
        if keyword.arg == "methods"
    )
    assert isinstance(basic_seeding_methods, ast.Tuple)
    assert [element.value for element in basic_seeding_methods.elts] == ["POST"]

    condition_registrar = module_function(
        "combat_routes.py",
        "register_combat_condition_routes",
    )
    condition_assignments = {
        target.id: statement.value
        for statement in condition_registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    condition_registrations = condition_assignments["registrations"]
    assert isinstance(condition_registrations, ast.Tuple)
    assert len(condition_registrations.elts) == 3
    assert [
        (registration.elts[1].value, registration.elts[0].value)
        for registration in condition_registrations.elts
        if isinstance(registration, ast.Tuple)
        and isinstance(registration.elts[0], ast.Constant)
        and isinstance(registration.elts[1], ast.Constant)
    ] == [
        (
            "campaign_combat_add_condition",
            expected_posts["campaign_combat_add_condition"],
        ),
        (
            "campaign_combat_delete_condition",
            expected_posts["campaign_combat_delete_condition"],
        ),
        (
            "campaign_combat_update_condition",
            expected_posts["campaign_combat_update_condition"],
        ),
    ]
    condition_add_url_rule_calls = [
        node
        for node in ast.walk(condition_registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(condition_add_url_rule_calls) == 1
    condition_methods = next(
        keyword.value
        for keyword in condition_add_url_rule_calls[0].keywords
        if keyword.arg == "methods"
    )
    assert isinstance(condition_methods, ast.Tuple)
    assert [element.value for element in condition_methods.elts] == ["POST"]


def test_combat_api_read_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "api.combat_state": "/api/v1/campaigns/<campaign_slug>/combat",
        "api.combat_live_state":
            "/api/v1/campaigns/<campaign_slug>/combat/live-state",
    }
    rules = discover_rules()
    for endpoint, path in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == ["GET"]
        assert set(matches[0].methods) >= {"GET", "HEAD", "OPTIONS"}

        entry = manifest_entry(endpoint, "GET")
        assert entry["surface"] == "api"
        assert entry["owning_domain"] == "combat"
        assert entry["flask_supplied_methods"] == ["HEAD", "OPTIONS"]

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler_names = {endpoint.removeprefix("api.") for endpoint in expected}
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in handler_names
        for node in ast.walk(api_tree)
    )

    registrar_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_api_read_routes"
    )
    condition_delete = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "dm_content_condition_delete"
    )
    systems_search = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_search_systems_monsters"
    )
    assert condition_delete.end_lineno < registrar_call.lineno < systems_search.lineno

    combat_api_tree = ast.parse(
        (source_root / "combat_api_routes.py").read_text(encoding="utf-8")
    )
    handlers = {
        node.name: node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.FunctionDef) and node.name in handler_names
    }
    assert set(handlers) == handler_names
    assert all(function.decorator_list == [] for function in handlers.values())

    registrar = module_function(
        "combat_api_routes.py",
        "register_combat_api_read_routes",
    )
    assignments = {
        target.id: statement.value
        for statement in registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    for view_name, handler_name in (
        ("combat_state_view", "combat_state"),
        ("combat_live_state_view", "combat_live_state"),
    ):
        wrapper = assignments[view_name]
        assert call_name(wrapper) == "combat_scope_access_required"
        assert len(wrapper.args) == 1
        assert isinstance(wrapper.args[0], ast.Name)
        assert wrapper.args[0].id == handler_name

    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2
    registrations_by_endpoint = {
        next(
            keyword.value.value
            for keyword in registration.keywords
            if keyword.arg == "endpoint"
            and isinstance(keyword.value, ast.Constant)
        ): registration
        for registration in registrations
    }
    assert set(registrations_by_endpoint) == handler_names
    for endpoint, path in expected.items():
        handler_name = endpoint.removeprefix("api.")
        registration = registrations_by_endpoint[handler_name]
        assert len(registration.args) == 1
        assert isinstance(registration.args[0], ast.Constant)
        assert registration.args[0].value == path.removeprefix("/api/v1")
        keyword_values = {
            keyword.arg: keyword.value
            for keyword in registration.keywords
        }
        assert isinstance(keyword_values["view_func"], ast.Name)
        assert keyword_values["view_func"].id == f"{handler_name}_view"
        assert isinstance(keyword_values["methods"], ast.Tuple)
        assert [
            element.value for element in keyword_values["methods"].elts
        ] == ["GET"]


def test_combat_condition_api_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "api.combat_condition_create": (
            "/api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/conditions",
            "POST",
        ),
        "api.combat_condition_delete": (
            "/api/v1/campaigns/<campaign_slug>/combat/conditions/<int:condition_id>",
            "DELETE",
        ),
    }
    rules = discover_rules()
    for endpoint, (path, method) in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        assert set(matches[0].methods) >= {method, "OPTIONS"}
        assert "HEAD" not in matches[0].methods

        entry = manifest_entry(endpoint, method)
        assert entry["surface"] == "api"
        assert entry["owning_domain"] == "combat"
        assert entry["flask_supplied_methods"] == ["OPTIONS"]
        assert entry["authentication_policy"] == "api_identity_required"
        assert entry["view_as_policy"] == "campaign_mutations_blocked"

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler_names = {endpoint.removeprefix("api.") for endpoint in expected}
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in handler_names
        for node in ast.walk(api_tree)
    )

    registrar_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_condition_api_routes"
    )
    generic_resources = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_resources_update"
    )
    npc_resources_registrar = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_npc_resources_update_api_route"
    )
    combatant_delete_registrar = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_combatant_delete_api_route"
    )
    character_list_registrar = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_character_list_api_route"
    )
    assert (
        generic_resources.end_lineno
        < npc_resources_registrar.lineno
        < registrar_call.lineno
        < combatant_delete_registrar.lineno
        < character_list_registrar.lineno
    )

    combat_api_tree = ast.parse(
        (source_root / "combat_api_routes.py").read_text(encoding="utf-8")
    )
    handlers = {
        node.name: node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.FunctionDef) and node.name in handler_names
    }
    assert set(handlers) == handler_names
    assert all(function.decorator_list == [] for function in handlers.values())

    registrar = module_function(
        "combat_api_routes.py",
        "register_combat_condition_api_routes",
    )
    assignments = {
        target.id: statement.value
        for statement in registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    for view_name, handler_name in (
        ("combat_condition_create_view", "combat_condition_create"),
        ("combat_condition_delete_view", "combat_condition_delete"),
    ):
        outer = assignments[view_name]
        assert call_name(outer) == "combat_scope_access_required"
        assert len(outer.args) == 1
        inner = outer.args[0]
        assert call_name(inner) == "login_required"
        assert len(inner.args) == 1
        assert isinstance(inner.args[0], ast.Name)
        assert inner.args[0].id == handler_name

    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2
    registrations_by_endpoint = {
        next(
            keyword.value.value
            for keyword in registration.keywords
            if keyword.arg == "endpoint"
            and isinstance(keyword.value, ast.Constant)
        ): registration
        for registration in registrations
    }
    assert set(registrations_by_endpoint) == handler_names
    for endpoint, (path, method) in expected.items():
        handler_name = endpoint.removeprefix("api.")
        registration = registrations_by_endpoint[handler_name]
        assert len(registration.args) == 1
        assert isinstance(registration.args[0], ast.Constant)
        assert registration.args[0].value == path.removeprefix("/api/v1")
        keyword_values = {
            keyword.arg: keyword.value
            for keyword in registration.keywords
        }
        assert isinstance(keyword_values["view_func"], ast.Name)
        assert keyword_values["view_func"].id == f"{handler_name}_view"
        assert isinstance(keyword_values["methods"], ast.Tuple)
        assert [
            element.value for element in keyword_values["methods"].elts
        ] == [method]

    all_module_registrations = [
        node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(all_module_registrations) == 11

    combat_entries = [
        entry
        for entry in cached_manifest()["entries"]
        if entry["owning_domain"] == "combat"
    ]
    assert sum(entry["endpoint"].startswith("api.") for entry in combat_entries) == 17
    assert sum(not entry["endpoint"].startswith("api.") for entry in combat_entries) == 29


def test_combat_custom_npc_create_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.combat_add_npc"
    path = "/api/v1/campaigns/<campaign_slug>/combat/npc-combatants"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == path
    assert explicit_methods(matches[0]) == ["POST"]
    assert set(matches[0].methods) == {"POST", "OPTIONS"}

    entry = manifest_entry(endpoint, "POST")
    assert entry["surface"] == "api"
    assert entry["owning_domain"] == "combat"
    assert entry["flask_supplied_methods"] == ["OPTIONS"]
    assert entry["authentication_policy"] == "api_identity_required"
    assert entry["view_as_policy"] == "campaign_mutations_blocked"

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "combat_add_npc"
        for node in ast.walk(api_tree)
    )

    player_create = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_add_player"
    )
    registrar_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_custom_npc_create_api_route"
    )
    statblock_create = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_add_statblock_npc"
    )
    assert player_create.end_lineno < registrar_call.lineno < statblock_create.lineno

    combat_api_tree = ast.parse(
        (source_root / "combat_api_routes.py").read_text(encoding="utf-8")
    )
    handler = next(
        node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "combat_add_npc"
    )
    assert handler.decorator_list == []

    registrar = module_function(
        "combat_api_routes.py",
        "register_combat_custom_npc_create_api_route",
    )
    assignments = {
        target.id: statement.value
        for statement in registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    outer = assignments["combat_add_npc_view"]
    assert call_name(outer) == "combat_scope_access_required"
    assert len(outer.args) == 1
    inner = outer.args[0]
    assert call_name(inner) == "login_required"
    assert len(inner.args) == 1
    assert isinstance(inner.args[0], ast.Name)
    assert inner.args[0].id == "combat_add_npc"

    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    registration = registrations[0]
    assert len(registration.args) == 1
    assert isinstance(registration.args[0], ast.Constant)
    assert registration.args[0].value == path.removeprefix("/api/v1")
    keyword_values = {
        keyword.arg: keyword.value
        for keyword in registration.keywords
    }
    assert isinstance(keyword_values["endpoint"], ast.Constant)
    assert keyword_values["endpoint"].value == "combat_add_npc"
    assert isinstance(keyword_values["view_func"], ast.Name)
    assert keyword_values["view_func"].id == "combat_add_npc_view"
    assert isinstance(keyword_values["methods"], ast.Tuple)
    assert [element.value for element in keyword_values["methods"].elts] == [
        "POST"
    ]

    all_module_registrations = [
        node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(all_module_registrations) == 11

    combat_entries = [
        manifest_entry
        for manifest_entry in cached_manifest()["entries"]
        if manifest_entry["owning_domain"] == "combat"
    ]
    assert sum(
        manifest_entry["endpoint"].startswith("api.")
        for manifest_entry in combat_entries
    ) == 17
    assert sum(
        not manifest_entry["endpoint"].startswith("api.")
        for manifest_entry in combat_entries
    ) == 29


def test_combat_turn_control_api_routes_keep_contract_and_module_ownership() -> None:
    route_specs = (
        (
            "api.combat_advance_turn",
            "/api/v1/campaigns/<campaign_slug>/combat/advance-turn",
            "POST",
            "combat_advance_turn",
        ),
        (
            "api.combat_clear",
            "/api/v1/campaigns/<campaign_slug>/combat/clear",
            "POST",
            "combat_clear",
        ),
        (
            "api.combat_set_current",
            "/api/v1/campaigns/<campaign_slug>/combat/combatants/"
            "<int:combatant_id>/set-current",
            "POST",
            "combat_set_current",
        ),
        (
            "api.combat_turn_update",
            "/api/v1/campaigns/<campaign_slug>/combat/combatants/"
            "<int:combatant_id>/turn",
            "PATCH",
            "combat_turn_update",
        ),
    )

    rules = discover_rules()
    for endpoint, path, method, _handler_name in route_specs:
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        assert set(matches[0].methods) == {method, "OPTIONS"}
        entry = manifest_entry(endpoint, method)
        assert entry["surface"] == "api"
        assert entry["owning_domain"] == "combat"
        assert entry["flask_supplied_methods"] == ["OPTIONS"]
        assert entry["authentication_policy"] == "api_identity_required"
        assert entry["view_as_policy"] == "campaign_mutations_blocked"

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name in {spec[3] for spec in route_specs}
        for node in ast.walk(api_tree)
    )
    systems_seed = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_add_systems_monster"
    )
    registrar_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_turn_control_api_routes"
    )
    generic_vitals = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_vitals_update"
    )
    assert systems_seed.end_lineno < registrar_call.lineno < generic_vitals.lineno

    combat_api_tree = ast.parse(
        (source_root / "combat_api_routes.py").read_text(encoding="utf-8")
    )
    registrar = module_function(
        "combat_api_routes.py",
        "register_combat_turn_control_api_routes",
    )
    handlers = {
        node.name: node
        for node in ast.walk(registrar)
        if isinstance(node, ast.FunctionDef)
        and node is not registrar
    }
    assert set(handlers) == {spec[3] for spec in route_specs}
    assert all(handler.decorator_list == [] for handler in handlers.values())

    assignments = {
        target.id: statement.value
        for statement in registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    for _endpoint, _path, _method, handler_name in route_specs:
        outer = assignments[f"{handler_name}_view"]
        assert call_name(outer) == "combat_scope_access_required"
        assert len(outer.args) == 1
        inner = outer.args[0]
        assert call_name(inner) == "login_required"
        assert len(inner.args) == 1
        assert isinstance(inner.args[0], ast.Name)
        assert inner.args[0].id == handler_name

    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 4
    for registration, (_endpoint, path, method, handler_name) in zip(
        registrations,
        route_specs,
        strict=True,
    ):
        assert registration.args[0].value == path.removeprefix("/api/v1")
        keyword_values = {keyword.arg: keyword.value for keyword in registration.keywords}
        assert keyword_values["endpoint"].value == handler_name
        assert keyword_values["view_func"].id == f"{handler_name}_view"
        assert [element.value for element in keyword_values["methods"].elts] == [method]

    all_module_registrations = [
        node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(all_module_registrations) == 11

    combat_entries = [
        entry
        for entry in cached_manifest()["entries"]
        if entry["owning_domain"] == "combat"
    ]
    assert sum(entry["endpoint"].startswith("api.") for entry in combat_entries) == 17
    assert sum(not entry["endpoint"].startswith("api.") for entry in combat_entries) == 29


def test_combat_npc_resources_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.combat_npc_resources_update"
    path = (
        "/api/v1/campaigns/<campaign_slug>/combat/combatants/"
        "<int:combatant_id>/npc-resources"
    )
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == path
    assert explicit_methods(matches[0]) == ["PATCH"]
    assert set(matches[0].methods) == {"PATCH", "OPTIONS"}

    entry = manifest_entry(endpoint, "PATCH")
    assert entry["surface"] == "api"
    assert entry["owning_domain"] == "combat"
    assert entry["flask_supplied_methods"] == ["OPTIONS"]
    assert entry["authentication_policy"] == "api_identity_required"
    assert entry["view_as_policy"] == "campaign_mutations_blocked"

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "combat_npc_resources_update"
        for node in ast.walk(api_tree)
    )

    generic_resources = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_resources_update"
    )
    registrar_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_npc_resources_update_api_route"
    )
    condition_registrar = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_condition_api_routes"
    )
    assert (
        generic_resources.end_lineno
        < registrar_call.lineno
        < condition_registrar.lineno
    )

    combat_api_tree = ast.parse(
        (source_root / "combat_api_routes.py").read_text(encoding="utf-8")
    )
    handler = next(
        node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_npc_resources_update"
    )
    assert handler.decorator_list == []

    registrar = module_function(
        "combat_api_routes.py",
        "register_combat_npc_resources_update_api_route",
    )
    assignments = {
        target.id: statement.value
        for statement in registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    outer = assignments["combat_npc_resources_update_view"]
    assert call_name(outer) == "combat_scope_access_required"
    assert len(outer.args) == 1
    inner = outer.args[0]
    assert call_name(inner) == "login_required"
    assert len(inner.args) == 1
    assert isinstance(inner.args[0], ast.Name)
    assert inner.args[0].id == "combat_npc_resources_update"

    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    registration = registrations[0]
    assert len(registration.args) == 1
    assert isinstance(registration.args[0], ast.Constant)
    assert registration.args[0].value == path.removeprefix("/api/v1")
    keyword_values = {
        keyword.arg: keyword.value
        for keyword in registration.keywords
    }
    assert isinstance(keyword_values["endpoint"], ast.Constant)
    assert keyword_values["endpoint"].value == "combat_npc_resources_update"
    assert isinstance(keyword_values["view_func"], ast.Name)
    assert keyword_values["view_func"].id == "combat_npc_resources_update_view"
    assert isinstance(keyword_values["methods"], ast.Tuple)
    assert [element.value for element in keyword_values["methods"].elts] == [
        "PATCH"
    ]

    all_module_registrations = [
        node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(all_module_registrations) == 11

    combat_entries = [
        manifest_entry
        for manifest_entry in cached_manifest()["entries"]
        if manifest_entry["owning_domain"] == "combat"
    ]
    assert sum(
        manifest_entry["endpoint"].startswith("api.")
        for manifest_entry in combat_entries
    ) == 17
    assert sum(
        not manifest_entry["endpoint"].startswith("api.")
        for manifest_entry in combat_entries
    ) == 29


def test_combat_combatant_delete_api_route_keeps_contract_and_module_ownership() -> None:
    endpoint = "api.combat_combatant_delete"
    path = "/api/v1/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>"
    matches = [rule for rule in discover_rules() if rule.endpoint == endpoint]
    assert len(matches) == 1
    assert matches[0].rule == path
    assert explicit_methods(matches[0]) == ["DELETE"]
    assert set(matches[0].methods) == {"DELETE", "OPTIONS"}

    entry = manifest_entry(endpoint, "DELETE")
    assert entry["surface"] == "api"
    assert entry["owning_domain"] == "combat"
    assert entry["flask_supplied_methods"] == ["OPTIONS"]
    assert entry["authentication_policy"] == "api_identity_required"
    assert entry["view_as_policy"] == "campaign_mutations_blocked"

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name == "combat_combatant_delete"
        for node in ast.walk(api_tree)
    )

    condition_registrar = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_condition_api_routes"
    )
    delete_registrar = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_combat_combatant_delete_api_route"
    )
    character_list_registrar = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "register_character_list_api_route"
    )
    assert condition_registrar.lineno < delete_registrar.lineno < character_list_registrar.lineno

    combat_api_tree = ast.parse(
        (source_root / "combat_api_routes.py").read_text(encoding="utf-8")
    )
    handler = next(
        node
        for node in ast.walk(combat_api_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "combat_combatant_delete"
    )
    assert handler.decorator_list == []

    registrar = module_function(
        "combat_api_routes.py",
        "register_combat_combatant_delete_api_route",
    )
    assignments = {
        target.id: statement.value
        for statement in registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    outer = assignments["combat_combatant_delete_view"]
    assert call_name(outer) == "combat_scope_access_required"
    assert len(outer.args) == 1
    inner = outer.args[0]
    assert call_name(inner) == "login_required"
    assert len(inner.args) == 1
    assert isinstance(inner.args[0], ast.Name)
    assert inner.args[0].id == "combat_combatant_delete"

    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    registration = registrations[0]
    assert len(registration.args) == 1
    assert isinstance(registration.args[0], ast.Constant)
    assert registration.args[0].value == path.removeprefix("/api/v1")
    keyword_values = {
        keyword.arg: keyword.value
        for keyword in registration.keywords
    }
    assert isinstance(keyword_values["endpoint"], ast.Constant)
    assert keyword_values["endpoint"].value == "combat_combatant_delete"
    assert isinstance(keyword_values["view_func"], ast.Name)
    assert keyword_values["view_func"].id == "combat_combatant_delete_view"
    assert isinstance(keyword_values["methods"], ast.Tuple)
    assert [element.value for element in keyword_values["methods"].elts] == [
        "DELETE"
    ]


def test_session_api_routes_keep_contract_and_module_ownership() -> None:
    expected = {
        "api.session_state": (
            "/api/v1/campaigns/<campaign_slug>/session",
            "GET",
        ),
        "api.session_article_image": (
            "/api/v1/campaigns/<campaign_slug>/session/articles/<int:article_id>/image",
            "GET",
        ),
        "api.session_article_create": (
            "/api/v1/campaigns/<campaign_slug>/session/articles",
            "POST",
        ),
        "api.session_article_update": (
            "/api/v1/campaigns/<campaign_slug>/session/articles/<int:article_id>",
            "PUT",
        ),
        "api.session_article_reveal": (
            "/api/v1/campaigns/<campaign_slug>/session/articles/<int:article_id>/reveal",
            "POST",
        ),
        "api.session_article_delete": (
            "/api/v1/campaigns/<campaign_slug>/session/articles/<int:article_id>",
            "DELETE",
        ),
        "api.session_revealed_articles_clear": (
            "/api/v1/campaigns/<campaign_slug>/session/articles/revealed",
            "DELETE",
        ),
        "api.session_article_source_search": (
            "/api/v1/campaigns/<campaign_slug>/session/article-sources/search",
            "GET",
        ),
        "api.session_log_detail": (
            "/api/v1/campaigns/<campaign_slug>/session/logs/<int:session_id>",
            "GET",
        ),
        "api.session_start": (
            "/api/v1/campaigns/<campaign_slug>/session/start",
            "POST",
        ),
        "api.session_close": (
            "/api/v1/campaigns/<campaign_slug>/session/close",
            "POST",
        ),
        "api.session_log_delete": (
            "/api/v1/campaigns/<campaign_slug>/session/logs/<int:session_id>",
            "DELETE",
        ),
        "api.session_message_create": (
            "/api/v1/campaigns/<campaign_slug>/session/messages",
            "POST",
        ),
    }
    rules = discover_rules()
    for endpoint, (path, method) in expected.items():
        matches = [rule for rule in rules if rule.endpoint == endpoint]
        assert len(matches) == 1
        assert matches[0].rule == path
        assert explicit_methods(matches[0]) == [method]
        if method == "GET":
            assert set(matches[0].methods) >= {"GET", "HEAD", "OPTIONS"}
        else:
            assert set(matches[0].methods) >= {method, "OPTIONS"}
            assert "HEAD" not in matches[0].methods

        entry = manifest_entry(endpoint, method)
        assert entry["owning_domain"] == "live-session"
        assert entry["flask_supplied_methods"] == (
            ["HEAD", "OPTIONS"] if method == "GET" else ["OPTIONS"]
        )

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler_names = {endpoint.removeprefix("api.") for endpoint in expected}
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in handler_names
        for node in ast.walk(api_tree)
    )

    session_api_tree = ast.parse(
        (source_root / "session_api_routes.py").read_text(encoding="utf-8")
    )
    handlers = {
        node.name: node
        for node in ast.walk(session_api_tree)
        if isinstance(node, ast.FunctionDef) and node.name in handler_names
    }
    assert set(handlers) == handler_names
    assert all(function.decorator_list == [] for function in handlers.values())

    registrations = [
        node
        for node in ast.walk(session_api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 13
    assert {
        keyword.value.value
        for registration in registrations
        for keyword in registration.keywords
        if keyword.arg == "endpoint" and isinstance(keyword.value, ast.Constant)
    } == handler_names

    registrations_by_function = (
        module_function("session_api_routes.py", "register_session_api_read_routes"),
        module_function(
            "session_api_routes.py",
            "register_session_article_authoring_routes",
        ),
        module_function(
            "session_api_routes.py",
            "register_session_article_lifecycle_routes",
        ),
    )
    assignments = {
        target.id: statement.value
        for registration in registrations_by_function
        for statement in registration.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    for view_name, handler_name in (
        ("session_state_view", "session_state"),
        ("session_article_image_view", "session_article_image"),
    ):
        outer = assignments[view_name]
        assert call_name(outer) == "session_scope_access_required"
        assert len(outer.args) == 1
        assert isinstance(outer.args[0], ast.Name)
        assert outer.args[0].id == handler_name

    for view_name, handler_name in (
        ("session_article_source_search_view", "session_article_source_search"),
        ("session_log_detail_view", "session_log_detail"),
        ("session_start_view", "session_start"),
        ("session_close_view", "session_close"),
        ("session_log_delete_view", "session_log_delete"),
        ("session_message_create_view", "session_message_create"),
        ("session_article_create_view", "session_article_create"),
        ("session_article_update_view", "session_article_update"),
        ("session_article_reveal_view", "session_article_reveal"),
        ("session_article_delete_view", "session_article_delete"),
        (
            "session_revealed_articles_clear_view",
            "session_revealed_articles_clear",
        ),
    ):
        outer = assignments[view_name]
        assert call_name(outer) == "session_scope_access_required"
        assert len(outer.args) == 1
        inner = outer.args[0]
        assert call_name(inner) == "login_required"
        assert len(inner.args) == 1
        assert isinstance(inner.args[0], ast.Name)
        assert inner.args[0].id == handler_name

    contract = contract_app()
    adapter = contract.url_map.bind("localhost")
    shared_log_path = "/api/v1/campaigns/linden-pass/session/logs/7"
    assert adapter.match(shared_log_path, method="GET")[0] == "api.session_log_detail"
    assert adapter.match(shared_log_path, method="HEAD")[0] == "api.session_log_detail"
    assert adapter.match(shared_log_path, method="DELETE")[0] == "api.session_log_delete"
    assert adapter.match(shared_log_path, method="OPTIONS")[0] == "api.session_log_detail"

    shared_article_path = "/api/v1/campaigns/linden-pass/session/articles/7"
    assert adapter.match(shared_article_path, method="PUT")[0] == "api.session_article_update"
    assert adapter.match(shared_article_path, method="DELETE")[0] == "api.session_article_delete"
    assert adapter.match(shared_article_path, method="OPTIONS")[0] == "api.session_article_update"

    message_entry = manifest_entry("api.session_message_create", "POST")
    assert message_entry["access_policy"] == "session_participant_api"
    assert message_entry["authentication_policy"] == "api_identity_required"
    assert message_entry["object_relationship_requirement"] == "active_session_participant"
    assert message_entry["view_as_policy"] == "campaign_mutations_blocked"

    assert sum(rule.endpoint.startswith("api.") for rule in rules) == 136
    live_session_entries = [
        entry
        for entry in cached_manifest()["entries"]
        if entry["owning_domain"] == "live-session"
    ]
    assert len(live_session_entries) == 32
    assert sum(entry["endpoint"].startswith("api.") for entry in live_session_entries) == 13
    assert sum(not entry["endpoint"].startswith("api.") for entry in live_session_entries) == 19


def test_systems_api_routes_keep_sixteen_api_rules_and_implicit_methods() -> None:
    expected = {
        "api.systems_import_run_list": {
            "/api/v1/systems/import-runs",
        },
        "api.systems_import_run_detail": {
            "/api/v1/systems/import-runs/<int:import_run_id>",
        },
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
    assert len(extracted_rules) == 8
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
    assert api_decorators == 66

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
    assert len(explicit_registrations) == 16
    systems_handlers = {
        node.name
        for node in ast.walk(systems_api_tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("systems_")
    }
    assert len(systems_handlers) == 15
    assert {
        "systems_import_dnd5e",
        "systems_import_run_list",
        "systems_import_run_detail",
    } <= systems_handlers

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
        "api.systems_item_mechanics_import": (
            "/api/v1/campaigns/<campaign_slug>/systems/item-mechanics/import",
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

    ingest_matches = [
        rule for rule in rules if rule.endpoint == "api.systems_import_dnd5e"
    ]
    assert len(ingest_matches) == 1
    assert ingest_matches[0].rule == "/api/v1/systems/imports/dnd5e"
    assert explicit_methods(ingest_matches[0]) == ["POST"]
    assert set(ingest_matches[0].methods) >= {"POST", "OPTIONS"}
    assert "HEAD" not in ingest_matches[0].methods

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


def test_systems_import_run_api_routes_keep_admin_read_contract_and_source_ownership() -> None:
    for endpoint in (
        "api.systems_import_run_list",
        "api.systems_import_run_detail",
    ):
        entry = manifest_entry(endpoint, "GET")
        assert entry["access_policy"] == "admin_api"
        assert entry["owning_domain"] == "systems"
        assert entry["authentication_policy"] == "api_identity_required"
        assert entry["view_as_policy"] == "real_actor_only"
        assert entry["flask_supplied_methods"] == ["HEAD", "OPTIONS"]

        function = module_function(
            "systems_api_routes.py",
            endpoint.removeprefix("api."),
        )
        assert function.decorator_list == []

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name in {"systems_import_run_list", "systems_import_run_detail"}
        for node in ast.walk(api_tree)
    )

    registration = module_function(
        "systems_api_routes.py",
        "register_systems_api_read_routes",
    )
    assignments = {
        target.id: statement.value
        for statement in registration.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    for view_name, handler_name in (
        ("systems_import_run_list_view", "systems_import_run_list"),
        ("systems_import_run_detail_view", "systems_import_run_detail"),
    ):
        outer = assignments[view_name]
        assert call_name(outer) == "login_required"
        assert len(outer.args) == 1
        inner = outer.args[0]
        assert call_name(inner) == "admin_required"
        assert len(inner.args) == 1
        assert isinstance(inner.args[0], ast.Name)
        assert inner.args[0].id == handler_name


def test_systems_dnd5e_ingest_api_route_keeps_admin_contract_and_source_ownership() -> None:
    entry = manifest_entry("api.systems_import_dnd5e", "POST")
    assert entry["access_policy"] == "admin_api"
    assert entry["owning_domain"] == "systems"
    assert entry["authentication_policy"] == "api_identity_required"
    assert entry["system_restriction"] == "dnd5e_only"
    assert entry["view_as_policy"] == "real_actor_only"
    assert entry["flask_supplied_methods"] == ["OPTIONS"]

    function = module_function("systems_api_routes.py", "systems_import_dnd5e")
    assert function.decorator_list == []

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "systems_import_dnd5e"
        for node in ast.walk(api_tree)
    )

    registration = module_function(
        "systems_api_routes.py",
        "register_systems_api_routes",
    )
    assignments = {
        target.id: statement.value
        for statement in registration.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    outer = assignments["systems_import_dnd5e_view"]
    assert call_name(outer) == "login_required"
    assert len(outer.args) == 1
    inner = outer.args[0]
    assert call_name(inner) == "admin_required"
    assert len(inner.args) == 1
    assert isinstance(inner.args[0], ast.Name)
    assert inner.args[0].id == "systems_import_dnd5e"


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
        "systems_item_mechanics_import",
    }
    for endpoint in extracted_api_endpoints:
        function = module_function("systems_api_routes.py", endpoint)
        assert function.decorator_list == []

    extracted_registration = module_function(
        "systems_api_routes.py",
        "register_systems_api_routes",
    )
    assert sum(
        call_name(node) == "systems_management_required"
        for node in ast.walk(extracted_registration)
    ) == 7
    assert sum(
        call_name(node) == "login_required"
        for node in ast.walk(extracted_registration)
    ) == 8

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
