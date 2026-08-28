from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import fields, replace
from datetime import UTC, datetime
from html.parser import HTMLParser
import inspect
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import player_wiki.character_update_preview_routes as route_module
import player_wiki.db as db_module
import pytest
from werkzeug.exceptions import Forbidden

from player_wiki.character_models import CharacterDefinition
from player_wiki.character_update_planner import (
    Diagnostic,
    DiagnosticCode,
    OperationKind,
    OperationStatus,
    PlanStatus,
    PlannedOperation,
    SemanticCategory,
    StateImpact,
    StateReconciliation,
)
from player_wiki.character_update_apply import (
    CharacterUpdateApplyClassification,
    CharacterUpdateApplyResult,
    CharacterUpdateReviewClaims,
    CharacterUpdateReviewIssue,
    CharacterUpdateTokenCodec,
)
from player_wiki.systems_models import SystemsEntryRecord


ENDPOINT = "character_update_preview_view"
ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/update-preview"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _ChoiceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_operation_select = False
        self.first_value = ""
        self.values = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "select" and attributes.get("name") == "operation_0_choice":
            self.in_operation_select = True
        elif tag == "option" and self.in_operation_select:
            value = attributes.get("value", "")
            if value:
                self.values.append(value)
                if not self.first_value:
                    self.first_value = value

    def handle_endtag(self, tag):
        if tag == "select" and self.in_operation_select:
            self.in_operation_select = False


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _dependencies(app):
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    return freevars["dependencies"].cell_contents


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    current = freevars["dependencies"].cell_contents
    monkeypatch.setattr(
        freevars["dependencies"],
        "cell_contents",
        replace(current, **replacements),
    )


def _definition(**overrides) -> CharacterDefinition:
    payload = {
        "campaign_slug": "linden-pass",
        "character_slug": "arden-march",
        "name": "Arden March",
        "status": "active",
        "system": "DND-5E",
        "profile": {"level": 5},
        "stats": {
            "max_hp": 30,
            "armor_class": 15,
            "ability_scores": {
                key: {"score": 10, "modifier": 0, "save_bonus": 0}
                for key in ("str", "dex", "con", "int", "wis", "cha")
            },
        },
        "skills": [],
        "proficiencies": {
            "armor": [],
            "weapons": [],
            "tools": [],
            "languages": [],
            "tool_expertise": [],
        },
        "attacks": [],
        "features": [],
        "spellcasting": {},
        "equipment_catalog": [],
        "reference_notes": {},
        "resource_templates": [],
        "source": {"source_type": "native_character_builder"},
    }
    payload.update(deepcopy(overrides))
    return CharacterDefinition.from_dict(payload)


def _state(**overrides):
    payload = {
        "status": "active",
        "vitals": {
            "current_hp": 28,
            "temp_hp": 0,
            "death_saves": {"successes": 0, "failures": 0},
        },
        "hit_dice": {"pools": []},
        "resources": [],
        "inventory": [],
        "currency": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0, "other": []},
        "spell_slots": [],
        "attunement": {"max_attuned_items": 3, "attuned_item_refs": []},
        "notes": {"player_notes_markdown": "", "session_notes": []},
    }
    payload.update(deepcopy(overrides))
    return payload


def _page(
    page_ref="mechanics/harbor-blessing",
    *,
    title="Harbor Blessing",
    section="Mechanics",
    option=None,
    body="A private source body that must never render: C:\\operator\\vault\\definition.yaml",
):
    return SimpleNamespace(
        campaign_slug="linden-pass",
        page_ref=page_ref,
        relative_path=f"content/{page_ref}.md",
        metadata={
            "character_option": deepcopy(
                option
                if option is not None
                else {
                    "kind": "feature" if section == "Mechanics" else "item",
                    "name": title,
                    "description": "A bounded visible summary.",
                }
            )
        },
        body_markdown=body,
        page=SimpleNamespace(
            title=title,
            summary="A bounded source summary.",
            section=section,
            subsection="",
        ),
        updated_at="2026-08-28T00:00:00Z",
    )


def _entry(
    entry_key="item|phb|iron-lantern",
    *,
    title="Iron Lantern",
    metadata=None,
) -> SystemsEntryRecord:
    now = datetime(2026, 8, 28, tzinfo=UTC)
    return SystemsEntryRecord(
        id=1,
        library_slug="dnd-5e",
        source_id="PHB",
        entry_key=entry_key,
        entry_type="item",
        slug=entry_key.rsplit("|", 1)[-1],
        title=title,
        source_page="",
        source_path="C:\\private\\systems\\source.json",
        search_text=title,
        player_safe_default=True,
        dm_heavy=False,
        metadata=dict(metadata or {}),
        body={"private": "must not render"},
        rendered_html="<p>must not render</p>",
        created_at=now,
        updated_at=now,
    )


def _fixture_replacements(
    events,
    *,
    definition=None,
    state=None,
    pages=None,
    entries=None,
):
    definition = definition or _definition()
    state = state or _state()
    campaign = SimpleNamespace(
        slug="linden-pass",
        title="Linden Pass",
        system="DND-5E",
    )
    record = SimpleNamespace(
        definition=definition,
        state_record=SimpleNamespace(state=state, revision=7),
    )
    pages = [_page()] if pages is None else list(pages)
    entries = [] if entries is None else list(entries)
    service = object()

    def event(name, result):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    return {
        "load_character_context": event("load", (campaign, record)),
        "can_manage_campaign_session": event("manager", True),
        "get_authenticated_user": event(
            "authenticated", SimpleNamespace(is_admin=False)
        ),
        "get_current_auth_source": event("auth_source", "session"),
        "is_dnd_5e_system": event("dnd", True),
        "get_systems_service": event("systems", service),
        "list_builder_campaign_page_records": event("pages", pages),
        "list_enabled_systems_items": event("entries", entries),
        "can_access_campaign_systems_entry": event("entry_access", True),
        "systems_item_is_approved": event("entry_approved", True),
        "prepare_native_derivation_foundation": event(
            "native_foundation", object()
        ),
        "normalize_definition_with_prepared_native_foundation": (
            lambda candidate, _foundation: events.append(("normalize",))
            or candidate
        ),
        "merge_state_with_definition": (
            lambda _candidate, current_state: events.append(("merge",))
            or deepcopy(current_state)
        ),
    }


def _first_choice(html: str) -> str:
    parser = _ChoiceParser()
    parser.feed(html)
    assert parser.first_value
    return parser.first_value


def _all_choices(html: str) -> list[str]:
    parser = _ChoiceParser()
    parser.feed(html)
    return parser.values


def _review_form(choice: str, *, intent="review", quantity="1"):
    return {
        "intent": intent,
        "operation_count": "1",
        "operation_0_choice": choice,
        "operation_0_quantity": quantity,
    }


def test_transport_registers_one_guarded_get_post_route_without_write_dependencies():
    dependency_names = {
        field.name
        for field in fields(route_module.CharacterUpdatePreviewRouteDependencies)
    }
    assert not dependency_names.intersection(
        {
            "character_publication_coordinator",
            "character_state_service",
            "audit_store",
            "token_store",
            "write_yaml",
        }
    )

    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_update_preview_routes.py").read_text(
            encoding="utf-8"
        )
    )
    registrations = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    registration = registrations[0]
    keywords = {keyword.arg: keyword.value for keyword in registration.keywords}
    assert isinstance(keywords["endpoint"], ast.Constant)
    assert keywords["endpoint"].value == ENDPOINT
    assert isinstance(keywords["methods"], (ast.Tuple, ast.List))
    assert [item.value for item in keywords["methods"].elts] == ["GET", "POST"]
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "campaign_scope_access_required"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "characters"
        for node in ast.walk(keywords["view_func"])
    )


def test_transport_owns_manager_and_view_as_admission_dependencies_only():
    dependency_names = [
        field.name
        for field in fields(route_module.CharacterUpdatePreviewRouteDependencies)
    ]
    assert "can_manage_campaign_session" in dependency_names
    assert "get_authenticated_user" in dependency_names
    assert "get_current_auth_source" in dependency_names
    assert "has_session_mode_access" not in dependency_names


def test_route_identity_methods_and_neighbor_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/campaigns/<campaign_slug>/characters/<character_slug>/update-preview"
    )
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert endpoints.index("character_retraining_view") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_read_view")
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


def test_manager_admission_precedes_character_and_source_work(
    app, monkeypatch
):
    events = []
    replacements = _fixture_replacements(events)
    replacements["can_manage_campaign_session"] = (
        lambda *_args: events.append(("manager",)) or False
    )
    _install_dependencies(app, monkeypatch, **replacements)

    with app.test_request_context(ROUTE_PATH):
        with pytest.raises(Forbidden):
            _handler(app)("linden-pass", "arden-march")

    assert events == [("authenticated", (), {}), ("auth_source", (), {}), ("manager",)]


def test_dm_and_admin_are_admitted_but_players_and_observers_are_denied(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    for user_key in ("dm", "admin"):
        sign_in(users[user_key]["email"], users[user_key]["password"])
        response = client.get(ROUTE_PATH)
        assert response.status_code == 200
        assert "Preview an update for Arden March" in response.get_data(as_text=True)

    for user_key in ("owner", "party", "observer", "outsider"):
        sign_in(users[user_key]["email"], users[user_key]["password"])
        response = client.get(ROUTE_PATH)
        assert response.status_code in {403, 404}

    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.get(
        "/campaigns/linden-pass/characters/arden-march/edit"
    ).status_code == 200


def test_view_as_admin_gets_visible_preview_only_surface_and_global_post_denial(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session["view_as_user_id"] = users["owner"]["id"]

    response = client.get(ROUTE_PATH)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Preview-only View As mode" in html
    assert 'value="review"' not in html
    assert client.post(ROUTE_PATH, data={"intent": "cancel"}).status_code == 403


def test_read_link_is_manager_only_and_dnd_only(client, sign_in, users):
    character_url = "/campaigns/linden-pass/characters/arden-march"
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_html = client.get(character_url).get_data(as_text=True)
    assert f'href="{ROUTE_PATH}"' in dm_html
    assert "Preview update" in dm_html

    sign_in(users["owner"]["email"], users["owner"]["password"])
    player_html = client.get(character_url).get_data(as_text=True)
    assert f'href="{ROUTE_PATH}"' not in player_html
    assert "Preview update" not in player_html


def test_cancel_redirects_before_character_or_source_preparation(
    app, client, sign_in, users, monkeypatch
):
    events = []
    replacements = _fixture_replacements(events)
    replacements["load_character_context"] = lambda *_args: pytest.fail(
        "cancel loaded the character"
    )
    replacements["prepare_character_update_adapters"] = lambda **_kwargs: pytest.fail(
        "cancel prepared adapters"
    )
    replacements["prepare_native_derivation_foundation"] = (
        lambda *_args, **_kwargs: pytest.fail(
            "cancel prepared native derivation"
        )
    )
    replacements["plan_character_update"] = lambda *_args, **_kwargs: pytest.fail(
        "cancel called the planner"
    )
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.post(
        ROUTE_PATH,
        data={
            "intent": "cancel",
            "operation_count": "1",
            "operation_0_choice": "",
            "operation_0_quantity": "1",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march"
    )


def test_get_and_back_never_prepare_or_plan_while_review_calls_each_once(
    app, client, sign_in, users, monkeypatch
):
    events = []
    replacements = _fixture_replacements(events)
    current = _dependencies(app)

    def prepare(**kwargs):
        events.append(("prepare",))
        return current.prepare_character_update_adapters(**kwargs)

    def plan(*args, **kwargs):
        events.append(("plan",))
        return current.plan_character_update(*args, **kwargs)

    replacements["prepare_character_update_adapters"] = prepare
    replacements["plan_character_update"] = plan
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    get_response = client.get(ROUTE_PATH)
    choice = _first_choice(get_response.get_data(as_text=True))
    assert not any(event[0] in {"prepare", "plan"} for event in events)
    assert not any(event[0] == "native_foundation" for event in events)

    back_response = client.post(
        ROUTE_PATH,
        data=_review_form(choice, intent="back"),
    )
    assert back_response.status_code == 200
    assert choice in back_response.get_data(as_text=True)
    assert not any(event[0] in {"prepare", "plan"} for event in events)
    assert not any(event[0] == "native_foundation" for event in events)

    review_response = client.post(ROUTE_PATH, data=_review_form(choice))
    assert review_response.status_code == 200
    assert [event[0] for event in events].count("prepare") == 1
    assert [event[0] for event in events].count("plan") == 1
    assert [event[0] for event in events].count("native_foundation") == 1


def test_valid_review_orders_validation_sources_native_foundation_adapters_and_planner_once(
    app, client, sign_in, users, monkeypatch
):
    events = []
    replacements = _fixture_replacements(events)
    current = _dependencies(app)
    original_parse = route_module._parse_form
    original_source = route_module._build_source_foundation

    def parse(*args, **kwargs):
        events.append(("parse",))
        return original_parse(*args, **kwargs)

    def source(*args, **kwargs):
        events.append(("source",))
        return original_source(*args, **kwargs)

    def prepare_adapters(**kwargs):
        events.append(("adapter",))
        return current.prepare_character_update_adapters(**kwargs)

    def plan(*args, **kwargs):
        events.append(("plan",))
        return current.plan_character_update(*args, **kwargs)

    monkeypatch.setattr(route_module, "_parse_form", parse)
    monkeypatch.setattr(route_module, "_build_source_foundation", source)
    replacements["prepare_character_update_adapters"] = prepare_adapters
    replacements["plan_character_update"] = plan
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    choice = _first_choice(client.get(ROUTE_PATH).get_data(as_text=True))
    events.clear()
    response = client.post(ROUTE_PATH, data=_review_form(choice))

    assert response.status_code == 200
    ordered = [
        event[0]
        for event in events
        if event[0]
        in {
            "parse",
            "source",
            "native_foundation",
            "adapter",
            "plan",
            "normalize",
            "merge",
        }
    ]
    assert ordered == [
        "parse",
        "source",
        "native_foundation",
        "adapter",
        "plan",
        "normalize",
        "merge",
    ]


def test_validation_is_bounded_retains_safe_values_and_focuses_first_error(
    app, client, sign_in, users, monkeypatch
):
    events = []
    _install_dependencies(
        app,
        monkeypatch,
        **_fixture_replacements(events),
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])
    choice = _first_choice(client.get(ROUTE_PATH).get_data(as_text=True))

    invalid = client.post(
        ROUTE_PATH,
        data=_review_form(choice, quantity="abc"),
    )
    html = invalid.get_data(as_text=True)
    assert invalid.status_code == 400
    assert 'href="#operation-0-quantity"' in html
    assert 'id="operation-0-quantity"' in html
    assert 'value="abc"' in html
    assert 'aria-invalid="true"' in html
    assert "autofocus" in html
    assert not any(event[0] == "prepare" for event in events)
    assert not any(event[0] == "native_foundation" for event in events)

    private_payload = "C:\\private\\definition.yaml"
    unsafe_retention = client.post(
        ROUTE_PATH,
        data={
            "intent": "review",
            "operation_count": private_payload,
            "operation_0_choice": choice,
            "operation_0_quantity": "f" * 64,
        },
    )
    assert unsafe_retention.status_code == 400
    assert private_payload not in unsafe_retention.get_data(as_text=True)
    assert "f" * 64 not in unsafe_retention.get_data(as_text=True)

    too_many = client.post(
        ROUTE_PATH,
        data={
            "intent": "review",
            "operation_count": "129",
            "operation_0_choice": choice,
            "operation_0_quantity": "1",
        },
    )
    assert too_many.status_code == 400
    assert "Choose between 1 and 128 operation rows" in too_many.get_data(
        as_text=True
    )


def test_unknown_or_replacement_fields_are_rejected_without_reflection(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    private_payload = "C:\\private\\character\\definition.yaml"
    response = client.post(
        ROUTE_PATH,
        data={
            "intent": "review",
            "operation_count": "1",
            "operation_0_choice": "",
            "operation_0_quantity": "1",
            "definition": private_payload,
            "state": '{"vitals": {}}',
            "digest": "f" * 64,
        },
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert private_payload not in html
    assert '"vitals"' not in html
    assert "f" * 64 not in html


def test_source_choices_exclude_choice_bearing_hidden_and_unapproved_rows(
    app, client, sign_in, users, monkeypatch
):
    events = []
    allowed_page = _page()
    choice_page = _page(
        "mechanics/choice-boon",
        title="Choice Boon",
        option={
            "kind": "feature",
            "additional_spells": {"choose": ["One", "Two"]},
        },
    )
    allowed_entry = _entry()
    hidden_entry = _entry("item|phb|hidden-item", title="Hidden Item")
    draft_entry = _entry("item|phb|draft-item", title="Draft Item")
    replacements = _fixture_replacements(
        events,
        pages=[allowed_page, choice_page],
        entries=[allowed_entry, hidden_entry, draft_entry],
    )
    replacements["can_access_campaign_systems_entry"] = (
        lambda _campaign_slug, entry_slug: entry_slug != "hidden-item"
    )
    replacements["systems_item_is_approved"] = (
        lambda entry: entry.slug != "draft-item"
    )
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    html = client.get(ROUTE_PATH).get_data(as_text=True)
    assert "Harbor Blessing" in html
    assert "Iron Lantern" in html
    assert "Choice Boon" not in html
    assert "Hidden Item" not in html
    assert "Draft Item" not in html


@pytest.mark.parametrize(
    ("exact_sources", "expected_relink"),
    ((("phb",), True), (("phb", "dmg"), False)),
)
def test_safe_relink_choice_requires_one_exact_case_sensitive_source_match(
    app, client, sign_in, users, monkeypatch, exact_sources, expected_relink
):
    equipment = {
        "id": "legacy-lantern",
        "name": "Legacy Lantern",
        "default_quantity": 1,
        "source_kind": "manual_edit",
        "campaign_option": None,
    }
    inventory = {
        "id": "legacy-lantern",
        "catalog_ref": "legacy-lantern",
        "name": "Legacy Lantern",
        "quantity": 1,
    }
    events = []
    replacements = _fixture_replacements(
        events,
        definition=_definition(equipment_catalog=[equipment]),
        state=_state(inventory=[inventory]),
        entries=[
            *[
                _entry(
                    f"item|{source}|legacy-lantern",
                    title="Legacy Lantern",
                )
                for source in exact_sources
            ],
            _entry("item|phb|case-mismatch", title="legacy lantern"),
        ],
    )
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    html = client.get(ROUTE_PATH).get_data(as_text=True)
    assert "Approved Systems items" in html
    assert ("Safe equipment relinks" in html) is expected_relink


def test_review_projects_ready_operations_and_all_six_categories_without_leaks(
    app, client, sign_in, users, monkeypatch
):
    events = []
    replacements = _fixture_replacements(events)
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    choice = _first_choice(client.get(ROUTE_PATH).get_data(as_text=True))

    response = client.post(ROUTE_PATH, data=_review_form(choice))
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Ready for a later apply workflow" in html
    assert "Grant campaign feature or boon" in html
    for label in (
        "Features",
        "Equipment/inventory",
        "Spells",
        "Attacks",
        "Armor Class",
        "Resources",
    ):
        assert f"<h3>{label}</h3>" in html
    for forbidden in (
        "definition.yaml",
        "source.json",
        "C:\\private",
        '"private"',
        "candidate_definition",
        "derived_character",
        "digest",
    ):
        assert forbidden not in html
    assert 'name="apply"' not in html
    assert ">Apply<" not in html
    assert 'value="review"' not in html


def test_ready_review_issues_one_actor_bound_token_and_renders_no_javascript_apply_form(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    events = []
    replacements = _fixture_replacements(events)
    replacements["get_authenticated_user"] = lambda: SimpleNamespace(
        id=users["dm"]["id"],
        is_admin=False,
    )

    class Engine:
        def issue_review(self, recompute, *, actor_user_id):
            events.append(("issue", recompute, actor_user_id))
            return CharacterUpdateReviewIssue(
                "cu1.canonical-body.canonical-signature",
                None,
            )

    replacements["character_update_apply_engine"] = Engine()
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    choice = _first_choice(client.get(ROUTE_PATH).get_data(as_text=True))
    events.clear()

    response = client.post(ROUTE_PATH, data=_review_form(choice))
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    issue_events = [event for event in events if event[0] == "issue"]
    assert len(issue_events) == 1
    assert issue_events[0][2] == users["dm"]["id"]
    assert 'name="review_token" value="cu1.canonical-body.canonical-signature"' in html
    assert '<button type="submit" name="intent" value="apply">' in html
    assert "A private source body" not in html


def test_preview_numeric_envelopes_for_one_and_128_operations(
    app,
    users,
    monkeypatch,
    record_property,
):
    codec = CharacterUpdateTokenCodec("performance-secret", now=lambda: 1_788_000_000)
    issue_errors = []

    class Engine:
        def issue_review(self, recompute, *, actor_user_id):
            claims = CharacterUpdateReviewClaims(
                actor_user_id=actor_user_id,
                campaign_slug="linden-pass",
                character_slug="arden-march",
                operations=recompute.operations,
                definition_digest="a" * 64,
                import_digest="b" * 64,
                state_revision=7,
                state_digest="c" * 64,
                state_updated_at="2026-08-28T00:00:00Z",
                state_updated_by_user_id=actor_user_id,
                source_digest=recompute.source_digest,
                policy_digest=recompute.policy_digest,
                native_digest=recompute.native_digest,
                planner_version=int(recompute.plan.version),
                state_impact=str(recompute.plan.state_impact.value),
                candidate_digest=str(recompute.plan.digest),
                semantic_digest="d" * 64,
                issued_at=1_788_000_000,
            )
            try:
                return CharacterUpdateReviewIssue(codec.issue(claims), None)
            except Exception as exc:
                issue_errors.append(exc)
                raise

    query_count = 0
    original_record_query = db_module._record_db_query

    def counted_query(duration_ms, *, is_write=False):
        nonlocal query_count
        query_count += 1
        return original_record_query(duration_ms, is_write=is_write)

    monkeypatch.setattr(db_module, "_record_db_query", counted_query)
    campaign_reads = 0
    original_path_open = Path.open

    def counted_path_open(path, mode="r", *args, **kwargs):
        nonlocal campaign_reads
        try:
            within_campaigns = Path(app.config["CAMPAIGNS_DIR"]).resolve() in path.resolve().parents
        except OSError:
            within_campaigns = False
        if within_campaigns and "r" in mode:
            campaign_reads += 1
        return original_path_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted_path_open)
    materializations = 0

    def install(pages):
        replacements = _fixture_replacements([], pages=pages)
        replacements["get_authenticated_user"] = lambda: SimpleNamespace(
            id=users["dm"]["id"],
            is_admin=False,
        )
        replacements["character_update_apply_engine"] = Engine()
        _install_dependencies(app, monkeypatch, **replacements)

    def invoke(method="GET", data=None):
        nonlocal query_count, campaign_reads, materializations
        with app.test_request_context(ROUTE_PATH, method=method, data=data):
            query_count = campaign_reads = materializations = 0
            started = perf_counter()
            response = app.make_response(_handler(app)("linden-pass", "arden-march"))
            elapsed_ms = (perf_counter() - started) * 1000
            return response, elapsed_ms, query_count, campaign_reads, materializations

    install([_page()])
    invoke()
    (
        one_get,
        one_get_ms,
        one_get_queries,
        one_get_reads,
        one_get_materializations,
    ) = invoke()
    one_choice = _first_choice(one_get.get_data(as_text=True))

    (
        one_review,
        one_review_ms,
        one_review_queries,
        one_review_reads,
        one_review_materializations,
    ) = invoke("POST", _review_form(one_choice))

    pages = [
        _page(
            f"mechanics/performance-{index}",
            title=f"Performance Grant {index}",
        )
        for index in range(128)
    ]
    install(pages)
    invoke()
    (
        batch_get,
        batch_get_ms,
        batch_get_queries,
        batch_get_reads,
        batch_get_materializations,
    ) = invoke()
    choices = _all_choices(batch_get.get_data(as_text=True))
    assert len(choices) == 128

    batch_form = {"intent": "review", "operation_count": "128"}
    for index, choice in enumerate(choices):
        batch_form[f"operation_{index}_choice"] = choice
        batch_form[f"operation_{index}_quantity"] = "1"
    (
        batch_review,
        batch_review_ms,
        batch_review_queries,
        batch_review_reads,
        batch_review_materializations,
    ) = invoke("POST", batch_form)

    assert one_get.status_code == one_review.status_code == 200, issue_errors
    assert batch_get.status_code == batch_review.status_code == 200
    assert one_get_queries <= 23
    assert one_review_queries <= 29
    assert batch_get_queries <= 23
    assert batch_review_queries <= 29
    assert max(one_get_reads, one_review_reads, batch_get_reads, batch_review_reads) <= 3
    assert (
        one_get_materializations,
        one_review_materializations,
        batch_get_materializations,
        batch_review_materializations,
    ) == (0, 0, 0, 0)
    assert len(one_get.data) <= 64 * 1024
    assert len(one_review.data) <= 64 * 1024
    assert len(batch_get.data) <= 64 * 1024
    assert len(batch_review.data) <= 640 * 1024
    assert one_get_ms <= 100
    assert one_review_ms <= 250
    assert batch_get_ms <= 100
    assert batch_review_ms <= 1500
    for name, value in {
        "one_get_ms": one_get_ms,
        "one_get_queries": one_get_queries,
        "one_get_reads": one_get_reads,
        "one_review_ms": one_review_ms,
        "one_review_queries": one_review_queries,
        "one_review_reads": one_review_reads,
        "batch_get_ms": batch_get_ms,
        "batch_get_queries": batch_get_queries,
        "batch_get_reads": batch_get_reads,
        "batch_review_ms": batch_review_ms,
        "batch_review_queries": batch_review_queries,
        "batch_review_reads": batch_review_reads,
        "one_get_bytes": len(one_get.data),
        "one_review_bytes": len(one_review.data),
        "batch_get_bytes": len(batch_get.data),
        "batch_review_bytes": len(batch_review.data),
    }.items():
        record_property(name, value)


@pytest.mark.parametrize(
    ("status", "diagnostics", "expected"),
    (
        (PlanStatus.NO_OP, (), "No changes needed"),
        (
            PlanStatus.BLOCKED,
            (Diagnostic(DiagnosticCode.IDENTITY_COLLISION, "private field.path"),),
            "Blocked — inspect the diagnostics",
        ),
    ),
)
def test_review_renders_no_op_and_blocked_states_with_sanitized_diagnostics(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    status,
    diagnostics,
    expected,
):
    events = []
    replacements = _fixture_replacements(events)

    class Prepared:
        snapshot = object()
        operations = (object(),)

        @staticmethod
        def planner_kwargs():
            return {}

    replacements["prepare_character_update_adapters"] = lambda **_kwargs: Prepared()
    replacements["plan_character_update"] = lambda *_args, **_kwargs: SimpleNamespace(
        status=status,
        operations=(
            PlannedOperation(
                "hidden-operation-id",
                OperationKind.CAMPAIGN_FEATURE_GRANT,
                1,
                (),
                (
                    OperationStatus.ALREADY_SATISFIED
                    if status is PlanStatus.NO_OP
                    else OperationStatus.BLOCKED
                ),
            ),
        ),
        state_impact=StateImpact.PRESERVE_EXACT,
        reconciliation=StateReconciliation(),
        semantic_diff=(),
        diagnostics=diagnostics,
    )
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    choice = _first_choice(client.get(ROUTE_PATH).get_data(as_text=True))

    response = client.post(ROUTE_PATH, data=_review_form(choice))
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert expected in html
    assert "hidden-operation-id" not in html
    assert "private field.path" not in html
    if status is PlanStatus.BLOCKED:
        assert "conflicts with an existing character entry" in html


def test_unexpected_preparation_or_planner_fault_is_sanitized_with_inspection_guidance(
    app, client, sign_in, users, monkeypatch
):
    events = []
    replacements = _fixture_replacements(events)
    replacements["prepare_character_update_adapters"] = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("C:\\private\\definition.yaml field.path")
    )
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    choice = _first_choice(client.get(ROUTE_PATH).get_data(as_text=True))

    response = client.post(ROUTE_PATH, data=_review_form(choice))
    html = response.get_data(as_text=True)
    assert response.status_code == 409
    assert "Preview needs inspection" in html
    assert "Refresh the character" in html
    assert "C:\\private" not in html
    assert "field.path" not in html


def test_unsupported_character_redirects_before_source_or_planner_work(
    app, monkeypatch
):
    events = []
    definition = _definition(system="Xianxia")
    replacements = _fixture_replacements(events, definition=definition)
    replacements["is_dnd_5e_system"] = lambda *_args: False
    replacements["redirect_unsupported_native_character_tools"] = (
        lambda *args, **kwargs: ("unsupported", 302)
    )
    replacements["list_builder_campaign_page_records"] = lambda *_args: pytest.fail(
        "unsupported target loaded sources"
    )
    _install_dependencies(app, monkeypatch, **replacements)

    with app.test_request_context(ROUTE_PATH):
        response = _handler(app)("linden-pass", "arden-march")

    assert response == ("unsupported", 302)


def test_get_validation_back_and_review_leave_character_bytes_and_revision_unchanged(
    app, client, sign_in, users, get_character, monkeypatch
):
    before_record = get_character("arden-march")
    before = (
        deepcopy(before_record.definition.to_dict()),
        deepcopy(before_record.state_record.state),
        before_record.state_record.revision,
    )
    coordinator = app.extensions["character_publication_coordinator"]
    monkeypatch.setattr(
        coordinator,
        "update",
        lambda *_args, **_kwargs: pytest.fail("preview attempted publication"),
    )
    events = []
    _install_dependencies(app, monkeypatch, **_fixture_replacements(events))
    sign_in(users["dm"]["email"], users["dm"]["password"])
    get_response = client.get(ROUTE_PATH)
    choice = _first_choice(get_response.get_data(as_text=True))
    assert client.post(
        ROUTE_PATH,
        data=_review_form(choice, quantity="bad"),
    ).status_code == 400
    assert client.post(
        ROUTE_PATH,
        data=_review_form(choice, intent="back"),
    ).status_code == 200
    assert client.post(ROUTE_PATH, data=_review_form(choice)).status_code == 200

    after_record = get_character("arden-march")
    after = (
        deepcopy(after_record.definition.to_dict()),
        deepcopy(after_record.state_record.state),
        after_record.state_record.revision,
    )
    assert after == before


def test_apply_transport_accepts_only_token_form_and_delegates_once_after_manager_auth(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    events = []
    replacements = _fixture_replacements(events)
    campaign, record = replacements["load_character_context"]()
    events.clear()
    replacements["get_authenticated_user"] = lambda: SimpleNamespace(
        id=users["dm"]["id"],
        is_admin=False,
    )
    replacements["load_character_apply_context"] = lambda *_args: (
        campaign,
        record,
    )

    class Engine:
        def apply(self, token, **kwargs):
            events.append(("apply", token, kwargs))
            return CharacterUpdateApplyResult(
                CharacterUpdateApplyClassification.CONFIRMED_APPLIED,
                "a" * 64,
            )

    replacements["character_update_apply_engine"] = Engine()
    _install_dependencies(app, monkeypatch, **replacements)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.post(
        ROUTE_PATH,
        data={
            "_csrf_token": "test",
            "intent": "apply",
            "review_token": "cu1.body.signature",
        },
    )

    assert response.status_code == 200
    assert 'data-update-outcome="confirmed_applied"' in response.get_data(as_text=True)
    apply_events = [event for event in events if event[0] == "apply"]
    assert len(apply_events) == 1
    assert apply_events[0][1] == "cu1.body.signature"
    assert apply_events[0][2]["actor_user_id"] == users["dm"]["id"]

    events.clear()
    rejected = client.post(
        ROUTE_PATH,
        data={
            "_csrf_token": "test",
            "intent": "apply",
            "review_token": "cu1.body.signature",
            "operation_0_choice": "forbidden",
        },
    )
    assert rejected.status_code == 400
    assert not [event for event in events if event[0] == "apply"]
