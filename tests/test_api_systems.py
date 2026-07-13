from __future__ import annotations

from urllib.parse import quote

import pytest

from tests.helpers.api_test_helpers import *
from tests.helpers.api_test_helpers import (
    _advanced_editor_values,
    _build_systems_import_archive,
    _build_unsafe_systems_import_archive,
    _configure_xianxia_campaign,
    _find_tracker_combatant,
    _import_systems_goblin,
    _seed_systems_item_entry,
    _seed_systems_spell_entry,
    _systems_ref,
    _valid_xianxia_create_data,
    _valid_xianxia_manual_import_data,
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
    _write_json,
)
from player_wiki.systems_ingest import SystemsArchiveLimits
from player_wiki.systems_importer import Dnd5eImportResult
from player_wiki.systems_service import SystemsPolicyValidationError
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.systems_import_helpers import _build_malformed_utf8_systems_import_archive


def _systems_api_mutation_dependencies(app, endpoint: str):
    pending = [app.view_functions[endpoint]]
    seen: set[int] = set()
    while pending:
        candidate = pending.pop()
        if id(candidate) in seen:
            continue
        seen.add(id(candidate))
        closure = getattr(candidate, "__closure__", None) or ()
        for cell in closure:
            value = cell.cell_contents
            if hasattr(value, "serialize_custom_systems_entry") and hasattr(
                value,
                "build_dm_content_systems_payload",
            ):
                return value
            if callable(value):
                pending.append(value)
    raise AssertionError(f"Unable to locate mutation dependencies for {endpoint}.")


def _write_published_api_item_page(app, page_ref: str, *, title: str) -> None:
    item_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "content"
        / f"{page_ref}.md"
    )
    item_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.write_text(
        "\n".join(
            [
                "---",
                f"title: {title}",
                "section: Items",
                "page_type: item",
                "source_ref: API item-mechanics transport characterization",
                "published: true",
                "---",
                "",
                "*Weapon (longsword), uncommon (requires attunement)*",
                "",
                "You gain a +1 bonus to attack and damage rolls with this weapon.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with app.app_context():
        app.extensions["repository_store"].refresh()


def _seed_api_policy_override_entry(
    app,
    *,
    entry_key: str = "dnd-5e|rule|API-POLICY|folder/policy-entry",
) -> str:
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        source_id = "API-POLICY"
        store.upsert_source(
            library_slug,
            source_id,
            title="API Policy Characterization",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="players",
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": entry_key,
                    "entry_type": "rule",
                    "slug": "api-policy-entry",
                    "title": "API Policy Entry",
                    "search_text": "api policy entry",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {},
                    "rendered_html": "<p>API policy entry.</p>",
                }
            ],
            entry_types=["rule"],
        )
    return entry_key


def test_api_systems_entry_admin_read_contract_includes_disabled_sources_and_nested_denials(
    client,
    app,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        slugs: dict[str, str] = {}
        for label, source_enabled, entry_enabled in (
            ("source_disabled", False, True),
            ("entry_disabled", True, False),
        ):
            source_id = f"API-{label.upper()}"
            entry_slug = f"api-admin-read-{label.replace('_', '-')}"
            entry_key = f"dnd-5e|spell|{source_id.lower()}|{entry_slug}"
            store.upsert_source(
                library_slug,
                source_id,
                title=f"API Admin Read {label}",
                license_class="open_license",
                public_visibility_allowed=True,
                requires_unofficial_notice=False,
            )
            store.upsert_campaign_enabled_source(
                "linden-pass",
                library_slug=library_slug,
                source_id=source_id,
                is_enabled=source_enabled,
                default_visibility="players",
            )
            store.replace_entries_for_source(
                library_slug,
                source_id,
                entries=[
                    {
                        "entry_key": entry_key,
                        "entry_type": "spell",
                        "slug": entry_slug,
                        "title": f"API Admin Read {label}",
                        "search_text": f"api admin read {label}",
                        "player_safe_default": True,
                        "metadata": {},
                        "body": {},
                        "rendered_html": f"<p>API Admin Read {label}.</p>",
                    }
                ],
                entry_types=["spell"],
            )
            if not entry_enabled:
                store.upsert_campaign_entry_override(
                    "linden-pass",
                    library_slug=library_slug,
                    entry_key=entry_key,
                    visibility_override=None,
                    is_enabled_override=False,
                )
            slugs[label] = entry_slug

        custom_entry = service.create_custom_campaign_entry(
            "linden-pass",
            title="Archived API Admin Read Custom Entry",
            entry_type="rule",
            slug_leaf="archived-api-admin-read",
            visibility="players",
            body_markdown="Archived API custom entry body.",
            actor_user_id=users["admin"]["id"],
            can_set_private=True,
        )
        service.archive_custom_campaign_entry(
            "linden-pass",
            custom_entry.slug,
            actor_user_id=users["admin"]["id"],
        )
        slugs["archived_custom"] = custom_entry.slug

    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-entry-read")
    player_token = issue_api_token(app, users["party"]["email"], label="player-entry-read")
    entry_url = lambda slug: f"/api/v1/campaigns/linden-pass/systems/entries/{slug}"

    for entry_slug in slugs.values():
        admin_response = client.get(entry_url(entry_slug), headers=api_headers(admin_token))
        assert admin_response.status_code == 200
        assert admin_response.get_json()["entry"]["slug"] == entry_slug

        player_response = client.get(entry_url(entry_slug), headers=api_headers(player_token))
        assert player_response.status_code == 403
        assert player_response.get_json()["error"]["code"] == "forbidden"

        anonymous_response = client.get(entry_url(entry_slug))
        assert anonymous_response.status_code == 401
        assert anonymous_response.get_json()["error"]["code"] == "auth_required"

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    for entry_slug in slugs.values():
        view_as_response = client.get(entry_url(entry_slug))
        assert view_as_response.status_code == 403
        assert view_as_response.get_json()["error"]["code"] == "forbidden"

    assert client.get(
        entry_url("missing-admin-read-entry"),
        headers=api_headers(admin_token),
    ).status_code == 404
    assert client.get(
        "/api/v1/campaigns/missing-campaign/systems/entries/missing",
        headers=api_headers(admin_token),
    ).status_code == 404


def test_api_systems_endpoints_follow_source_visibility_and_allow_dm_policy_updates(client, app, users, tmp_path):
    goblin_entry_key, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-systems-api")

    dm_index = client.get("/api/v1/campaigns/linden-pass/systems", headers=api_headers(dm_token))
    assert dm_index.status_code == 200
    dm_index_payload = dm_index.get_json()
    dm_sources = {item["source_id"] for item in dm_index_payload["sources"]}
    assert "MM" in dm_sources
    assert "has_rules_reference_search" in dm_index_payload
    assert "source_scoped_rules_reference_sources" in dm_index_payload

    dm_search = client.get(
        "/api/v1/campaigns/linden-pass/systems?q=goblin",
        headers=api_headers(dm_token),
    )
    assert dm_search.status_code == 200
    dm_search_payload = dm_search.get_json()
    assert dm_search_payload["query"] == "goblin"
    assert dm_search_payload["search_results"]
    assert dm_search_payload["search_results"][0]["entry_key"] == goblin_entry_key
    assert dm_search_payload["reference_query"] == ""

    player_index = client.get("/api/v1/campaigns/linden-pass/systems", headers=api_headers(player_token))
    assert player_index.status_code == 200
    player_sources = {item["source_id"] for item in player_index.get_json()["sources"]}
    assert "MM" not in player_sources

    blocked_source = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM",
        headers=api_headers(player_token),
    )
    assert blocked_source.status_code == 403

    source_detail = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM",
        headers=api_headers(dm_token),
    )
    assert source_detail.status_code == 200
    source_payload = source_detail.get_json()
    assert source_payload["source"]["source_id"] == "MM"
    assert source_payload["entry_count"] == 1
    assert source_payload["browsable_entry_count"] == 1
    assert source_payload["entry_groups"][0]["entry_type"] == "monster"
    assert source_payload["book_entries"] == []
    assert source_payload["reference_query"] == ""
    assert "has_rules_reference_search" in source_payload

    source_category = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster",
        headers=api_headers(dm_token),
    )
    assert source_category.status_code == 200
    category_payload = source_category.get_json()
    assert category_payload["entry_groups"][0]["entry_type"] == "monster"
    assert category_payload["entry_groups"][0]["entry_type_label"] == "Monsters"
    assert category_payload["entry_groups"][0]["count"] == 1
    category_entries = category_payload["entries"]
    assert len(category_entries) == 1
    assert category_entries[0]["entry_key"] == goblin_entry_key
    assert category_entries[0]["title"] == "Goblin"

    entry_detail = client.get(
        f"/api/v1/campaigns/linden-pass/systems/entries/{goblin_slug}",
        headers=api_headers(dm_token),
    )
    assert entry_detail.status_code == 200
    entry_payload = entry_detail.get_json()
    assert entry_payload["entry"]["title"] == "Goblin"
    assert entry_payload["entry"]["entry_type"] == "monster"
    assert "rendered_html" in entry_payload["entry"]
    assert entry_payload["links"]["flask_entry_url"].endswith(f"/systems/entries/{goblin_slug}")
    assert "dm-content/systems" in entry_payload["links"]["dm_content_systems_url"]

    update_sources = client.put(
        "/api/v1/campaigns/linden-pass/systems/sources",
        headers=api_headers(dm_token),
        json={
            "updates": [
                {
                    "source_id": "XGE",
                    "is_enabled": True,
                    "default_visibility": "dm",
                }
            ]
        },
    )
    assert update_sources.status_code == 200
    xge_state = next(
        item for item in update_sources.get_json()["sources"] if item["source_id"] == "XGE"
    )
    assert xge_state["default_visibility"] == "dm"

    with app.app_context():
        state = app.extensions["systems_service"].get_campaign_source_state("linden-pass", "XGE")
        assert state is not None
        assert state.default_visibility == "dm"

        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("source_id") == "XGE" for event in events)


def test_api_systems_read_routes_preserve_index_alias_head_and_options_contracts(
    client,
    app,
    users,
    tmp_path,
):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-read-methods")
    headers = api_headers(dm_token)
    paths = (
        "/api/v1/campaigns/linden-pass/systems",
        "/api/v1/campaigns/linden-pass/systems/search",
        "/api/v1/campaigns/linden-pass/systems/sources",
        "/api/v1/campaigns/linden-pass/systems/sources/MM",
        "/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster",
        f"/api/v1/campaigns/linden-pass/systems/entries/{goblin_slug}",
    )

    for path in paths:
        get_response = client.get(path, headers=headers)
        head_response = client.head(path, headers=headers)
        options_response = client.options(path, headers=headers)

        assert get_response.status_code == 200
        assert head_response.status_code == get_response.status_code
        assert head_response.get_data() == b""
        assert options_response.status_code == 200
        assert {"GET", "HEAD", "OPTIONS"} <= set(
            options_response.headers["Allow"].split(", ")
        )

    source_list_options = client.options(
        "/api/v1/campaigns/linden-pass/systems/sources",
        headers=headers,
    )
    assert {"GET", "HEAD", "OPTIONS", "PUT"} <= set(
        source_list_options.headers["Allow"].split(", ")
    )

    query_string = {"q": "goblin", "reference_q": "rules"}
    index_payload = client.get(
        "/api/v1/campaigns/linden-pass/systems",
        query_string=query_string,
        headers=headers,
    ).get_json()
    search_payload = client.get(
        "/api/v1/campaigns/linden-pass/systems/search",
        query_string=query_string,
        headers=headers,
    ).get_json()
    assert search_payload == index_payload


def test_api_systems_source_list_projects_all_states_to_manager_and_only_accessible_enabled_states_to_player(
    client,
    app,
    users,
):
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        source_settings = (
            ("READ-PLAYERS", True, "players"),
            ("READ-DISABLED", False, "players"),
            ("READ-DM", True, "dm"),
        )
        for source_id, is_enabled, visibility in source_settings:
            store.upsert_source(
                library_slug,
                source_id,
                title=f"Source List {source_id}",
                license_class="open_license",
                public_visibility_allowed=True,
                requires_unofficial_notice=False,
            )
            store.upsert_campaign_enabled_source(
                "linden-pass",
                library_slug=library_slug,
                source_id=source_id,
                is_enabled=is_enabled,
                default_visibility=visibility,
            )
        configured_source_ids = {
            state.source.source_id
            for state in service.list_campaign_source_states("linden-pass")
        }

    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-source-list-dm")
    player_token = issue_api_token(
        app,
        users["party"]["email"],
        label="systems-source-list-player",
    )
    source_list_url = "/api/v1/campaigns/linden-pass/systems/sources"

    manager_payload = client.get(
        source_list_url,
        headers=api_headers(dm_token),
    ).get_json()
    manager_sources = manager_payload["sources"]
    assert {source["source_id"] for source in manager_sources} == configured_source_ids
    assert manager_payload["permissions"]["can_manage_systems"] is True
    assert all(source["permissions"]["can_manage"] is True for source in manager_sources)

    player_payload = client.get(
        source_list_url,
        headers=api_headers(player_token),
    ).get_json()
    player_sources = player_payload["sources"]
    player_source_ids = {source["source_id"] for source in player_sources}
    assert "READ-PLAYERS" in player_source_ids
    assert "READ-DISABLED" not in player_source_ids
    assert "READ-DM" not in player_source_ids
    assert player_payload["permissions"]["can_manage_systems"] is False
    assert all(source["is_enabled"] is True for source in player_sources)
    assert all(source["permissions"] == {"can_access": True, "can_manage": False} for source in player_sources)


def test_api_systems_policy_mutations_preserve_auth_json_view_as_and_csrf_order(
    client,
    app,
    users,
    sign_in,
    set_campaign_visibility,
):
    source_url = "/api/v1/campaigns/linden-pass/systems/sources"
    missing_campaign_url = "/api/v1/campaigns/missing-campaign/systems/sources"

    assert client.put(missing_campaign_url, json={}).status_code == 404

    anonymous = client.put(source_url, json={})
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    for actor in ("party", "outsider"):
        token = issue_api_token(
            app,
            users[actor]["email"],
            label=f"systems-policy-{actor}",
        )
        denied = client.put(source_url, headers=api_headers(token), json={})
        assert denied.status_code == 403
        assert denied.get_json()["error"]["code"] == "forbidden"

    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-policy-dm")
    non_object = client.put(source_url, headers=api_headers(dm_token), json=[])
    assert non_object.status_code == 400
    assert non_object.get_json()["error"] == {
        "code": "validation_error",
        "message": "Request body must be a JSON object.",
    }
    malformed = client.put(
        source_url,
        headers={**api_headers(dm_token), "Content-Type": "application/json"},
        data="{",
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"] == {
        "code": "validation_error",
        "message": "Request body must be a JSON object.",
    }

    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    view_as_denied = client.put(source_url, json={})
    assert view_as_denied.status_code == 403
    assert view_as_denied.get_json()["error"]["code"] == "view_as_read_only"

    app.config["CSRF_ENABLED"] = False
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    csrf_denied = client.put(source_url, json={})
    assert csrf_denied.status_code == 400
    assert csrf_denied.get_json()["error"]["code"] == "csrf_failed"

    bearer_allowed = app.test_client().put(
        source_url,
        headers=api_headers(dm_token),
        json={},
    )
    assert bearer_allowed.status_code == 200

    set_campaign_visibility("linden-pass", systems="private")
    scope_denied = app.test_client().put(
        source_url,
        headers=api_headers(dm_token),
        json={},
    )
    assert scope_denied.status_code == 403
    assert scope_denied.get_json()["error"]["code"] == "forbidden"
    admin_token = issue_api_token(
        app,
        users["admin"]["email"],
        label="systems-policy-admin",
    )
    assert app.test_client().put(
        source_url,
        headers=api_headers(admin_token),
        json={},
    ).status_code == 200


def test_api_systems_source_update_preserves_truthiness_private_nochange_and_duplicate_order(
    client,
    app,
    users,
):
    source_url = "/api/v1/campaigns/linden-pass/systems/sources"
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-source-contract")
    dm_headers = api_headers(dm_token)

    no_body = client.put(source_url, headers=dm_headers)
    assert no_body.status_code == 200
    with app.app_context():
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        service = app.extensions["systems_service"]
        xge_before = service.get_campaign_source_state("linden-pass", "XGE")
        assert xge_before is not None
        initial_visibility = xge_before.default_visibility
        changed_visibility = "dm" if initial_visibility != "dm" else "players"

    private_denied = client.put(
        source_url,
        headers=dm_headers,
        json={
            "updates": [
                {
                    "source_id": "XGE",
                    "is_enabled": True,
                    "default_visibility": "private",
                }
            ]
        },
    )
    assert private_denied.status_code == 400
    assert private_denied.get_json()["error"]["message"] == (
        "Private visibility is reserved for app admins."
    )

    duplicate_update = client.put(
        source_url,
        headers=dm_headers,
        json={
            "updates": [
                {
                    "source_id": "XGE",
                    "is_enabled": xge_before.is_enabled,
                    "default_visibility": changed_visibility,
                },
                {
                    "source_id": "XGE",
                    "is_enabled": xge_before.is_enabled,
                    "default_visibility": initial_visibility,
                },
            ]
        },
    )
    assert duplicate_update.status_code == 200
    with app.app_context():
        state = app.extensions["systems_service"].get_campaign_source_state(
            "linden-pass",
            "XGE",
        )
        assert state is not None
        assert state.default_visibility == changed_visibility
        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        assert [event.metadata["source_id"] for event in events] == ["XGE"]

        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            "API-PROPRIETARY",
            title="API Proprietary Source",
            license_class="proprietary_private",
            public_visibility_allowed=False,
            requires_unofficial_notice=True,
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id="API-PROPRIETARY",
            is_enabled=False,
            default_visibility="dm",
        )

    proprietary_update = {
        "updates": [
            {
                "source_id": "API-PROPRIETARY",
                "is_enabled": "false",
                "default_visibility": "dm",
            }
        ]
    }
    acknowledgement_required = client.put(
        source_url,
        headers=dm_headers,
        json=proprietary_update,
    )
    assert acknowledgement_required.status_code == 400
    assert "Acknowledge the proprietary-source notice" in (
        acknowledgement_required.get_json()["error"]["message"]
    )

    truthy_strings = client.put(
        source_url,
        headers=dm_headers,
        json={**proprietary_update, "acknowledge_proprietary": "false"},
    )
    assert truthy_strings.status_code == 200
    with app.app_context():
        state = app.extensions["systems_service"].get_campaign_source_state(
            "linden-pass",
            "API-PROPRIETARY",
        )
        assert state is not None and state.is_enabled is True

    admin_token = issue_api_token(
        app,
        users["admin"]["email"],
        label="systems-source-private-admin",
    )
    admin_private = client.put(
        source_url,
        headers=api_headers(admin_token),
        json={
            "updates": [
                {
                    "source_id": "XGE",
                    "is_enabled": xge_before.is_enabled,
                    "default_visibility": "private",
                }
            ]
        },
    )
    assert admin_private.status_code == 200
    with app.app_context():
        state = app.extensions["systems_service"].get_campaign_source_state(
            "linden-pass",
            "XGE",
        )
        assert state is not None and state.default_visibility == "private"


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("1", True),
        ("true", True),
        ("YES", True),
        (" on ", True),
        ("0", False),
        ("false", False),
        ("NO", False),
        (" off ", False),
    ],
)
def test_api_systems_override_update_preserves_path_and_bool_coercion(
    client,
    app,
    users,
    raw_value,
    expected,
):
    entry_key = _seed_api_policy_override_entry(app)
    override_url = (
        "/api/v1/campaigns/linden-pass/systems/overrides/"
        f"{quote(entry_key, safe='/')}"
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-override-coerce")
    response = client.put(
        override_url,
        headers=api_headers(dm_token),
        json={"is_enabled_override": raw_value},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["override"]["entry_key"] == entry_key
    assert payload["override"]["is_enabled_override"] is expected
    if expected:
        assert payload["entry"]["entry_key"] == entry_key
    else:
        assert payload["entry"] is None


def test_api_systems_override_update_preserves_inherit_repeat_validation_and_private_rules(
    client,
    app,
    users,
):
    entry_key = _seed_api_policy_override_entry(app)
    override_url = (
        "/api/v1/campaigns/linden-pass/systems/overrides/"
        f"{quote(entry_key, safe='/')}"
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-override-contract")
    dm_headers = api_headers(dm_token)

    for _ in range(2):
        inherited = client.put(override_url, headers=dm_headers)
        assert inherited.status_code == 200
        assert inherited.get_json()["override"]["visibility_override"] is None
        assert inherited.get_json()["override"]["is_enabled_override"] is None

    invalid_bool = client.put(
        override_url,
        headers=dm_headers,
        json={"is_enabled_override": "disabled"},
    )
    assert invalid_bool.status_code == 400
    assert invalid_bool.get_json()["error"]["message"] == (
        "is_enabled_override must be true or false."
    )

    normalized = client.put(
        override_url,
        headers=dm_headers,
        json={"visibility_override": "  dm  ", "is_enabled_override": None},
    )
    assert normalized.status_code == 200
    assert normalized.get_json()["override"] == {
        "entry_key": entry_key,
        "visibility_override": "dm",
        "is_enabled_override": None,
        "updated_at": normalized.get_json()["override"]["updated_at"],
        "updated_by_user_id": users["dm"]["id"],
    }

    private_denied = client.put(
        override_url,
        headers=dm_headers,
        json={"visibility_override": "private"},
    )
    assert private_denied.status_code == 400
    assert private_denied.get_json()["error"]["message"] == (
        "Private visibility is reserved for app admins."
    )

    admin_token = issue_api_token(
        app,
        users["admin"]["email"],
        label="systems-override-private-admin",
    )
    admin_private = client.put(
        override_url,
        headers=api_headers(admin_token),
        json={"visibility_override": "private"},
    )
    assert admin_private.status_code == 200
    assert admin_private.get_json()["override"]["visibility_override"] == "private"

    with app.app_context():
        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_entry_override_updated",
            campaign_slug="linden-pass",
        )
        assert len(events) == 4


def test_api_systems_source_update_preserves_write_and_partial_audit_failures(
    client,
    app,
    users,
    monkeypatch,
):
    source_url = "/api/v1/campaigns/linden-pass/systems/sources"
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-source-faults")
    headers = api_headers(dm_token)
    with app.app_context():
        service = app.extensions["systems_service"]
        original_update = service.update_campaign_sources

        def fail_update(*args, **kwargs):
            raise RuntimeError("source update unavailable")

        monkeypatch.setattr(service, "update_campaign_sources", fail_update)
        with pytest.raises(RuntimeError, match="source update unavailable"):
            client.put(source_url, headers=headers, json={"updates": []})
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        monkeypatch.setattr(service, "update_campaign_sources", original_update)

        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        for source_id in ("XGE", "TCE"):
            store.upsert_campaign_enabled_source(
                "linden-pass",
                library_slug=library_slug,
                source_id=source_id,
                is_enabled=True,
                default_visibility="players",
            )

        auth_store = app.extensions["auth_store"]
        original_audit = auth_store.write_audit_event
        attempted_source_ids = []

        def fail_second_audit(*args, **kwargs):
            attempted_source_ids.append(kwargs["metadata"]["source_id"])
            if len(attempted_source_ids) == 2:
                raise RuntimeError("source audit unavailable")
            return original_audit(*args, **kwargs)

        monkeypatch.setattr(auth_store, "write_audit_event", fail_second_audit)
        with pytest.raises(RuntimeError, match="source audit unavailable"):
            client.put(
                source_url,
                headers=headers,
                json={
                    "updates": [
                        {
                            "source_id": source_id,
                            "is_enabled": True,
                            "default_visibility": "dm",
                        }
                        for source_id in ("XGE", "TCE")
                    ]
                },
            )

        assert attempted_source_ids == ["XGE", "TCE"]
        for source_id in ("XGE", "TCE"):
            state = service.get_campaign_source_state("linden-pass", source_id)
            assert state is not None and state.default_visibility == "dm"
        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        assert [event.metadata["source_id"] for event in events] == ["XGE"]


def test_api_systems_override_update_preserves_write_and_audit_failure_boundaries(
    client,
    app,
    users,
    monkeypatch,
):
    entry_key = _seed_api_policy_override_entry(app)
    override_url = (
        "/api/v1/campaigns/linden-pass/systems/overrides/"
        f"{quote(entry_key, safe='/')}"
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-override-faults")
    headers = api_headers(dm_token)

    with app.app_context():
        store = app.extensions["systems_store"]
        original_write = store.upsert_campaign_entry_override

        def fail_write(*args, **kwargs):
            raise RuntimeError("override write unavailable")

        monkeypatch.setattr(store, "upsert_campaign_entry_override", fail_write)
        with pytest.raises(RuntimeError, match="override write unavailable"):
            client.put(
                override_url,
                headers=headers,
                json={"visibility_override": "dm"},
            )
        assert store.get_campaign_entry_override("linden-pass", entry_key) is None
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_entry_override_updated",
            campaign_slug="linden-pass",
        )
        monkeypatch.setattr(store, "upsert_campaign_entry_override", original_write)

        auth_store = app.extensions["auth_store"]

        def fail_audit(*args, **kwargs):
            raise RuntimeError("override audit unavailable")

        monkeypatch.setattr(auth_store, "write_audit_event", fail_audit)
        with pytest.raises(RuntimeError, match="override audit unavailable"):
            client.put(
                override_url,
                headers=headers,
                json={"visibility_override": "dm"},
            )

        override = store.get_campaign_entry_override("linden-pass", entry_key)
        assert override is not None and override.visibility_override == "dm"
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_entry_override_updated",
            campaign_slug="linden-pass",
        )


def test_api_dm_content_systems_endpoint_returns_management_payload_and_denies_unauthorized_users(
    client,
    app,
    users,
    tmp_path,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-content-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-systems-content-api")
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-content-api")

    # Seed one import run so import history appears in the management payload.
    archive_bytes = _build_systems_import_archive(tmp_path)
    import_response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "mm-import.zip",
                "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
            },
        },
    )
    assert import_response.status_code == 200
    import_payload = import_response.get_json()
    assert import_payload["ok"] is True
    import_run_ids = [entry["id"] for entry in import_payload["import_runs"]]

    systems_response = client.get(
        "/api/v1/campaigns/linden-pass/dm-content/systems",
        headers=api_headers(dm_token),
    )
    assert systems_response.status_code == 200
    systems_payload = systems_response.get_json()

    assert isinstance(systems_payload["source_rows"], list)
    assert systems_payload["source_rows"]
    assert any(row["source_id"] == "MM" for row in systems_payload["source_rows"])
    assert systems_payload["custom_entry_type_choices"]
    assert len(systems_payload["custom_entry_visibility_choices"]) == 3
    visibility_values = {item["value"] for item in systems_payload["custom_entry_visibility_choices"]}
    assert {"public", "players", "dm"} <= visibility_values
    assert systems_payload["links"]["flask_systems_lane_url"]
    assert systems_payload["links"]["flask_systems_control_url"]

    import_rows = systems_payload["import_run_rows"]
    assert import_rows
    assert set(import_run_ids).issubset({run["id"] for run in import_rows})
    assert all("source_path" not in run for run in import_rows)
    assert any(item["value"] == "spell" for item in systems_payload["custom_entry_type_choices"])

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/dm-content/systems",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"


def test_api_dm_content_systems_custom_entry_lifecycle_returns_refreshed_system_payload(
    client,
    app,
    users,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-custom-entries-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/systems/custom-entries",
        headers=api_headers(dm_token),
        json={
            "title": "API Spark",
            "entry_type": "spell",
            "slug_leaf": "api-systems-spark",
            "provenance": "API test",
            "visibility": "players",
            "search_metadata": "api systems spark",
            "body_markdown": "## Effect\nA small burst of controlled lightning.",
        },
    )
    assert create_response.status_code == 200
    create_payload = create_response.get_json()
    created_entry = create_payload["entry"]
    assert created_entry["title"] == "API Spark"
    assert created_entry["entry_type"] == "spell"
    assert not created_entry["is_archived"]
    assert "systems" in create_payload
    create_systems_payload = create_payload["systems"]
    create_rows = create_systems_payload["custom_entry_source_rows"]
    assert create_rows
    create_source_row = next(
        row for row in create_rows if row["source_id"] == created_entry["source_id"]
    )
    assert any(entry["slug"] == created_entry["slug"] for entry in create_source_row["entries"])

    update_payload = {
        "title": "API Spark Revised",
        "entry_type": "feat",
        "provenance": "API test revised",
        "visibility": "dm",
        "search_metadata": "api systems spark revised",
        "body_markdown": "## Effect\nA revised burst of controlled lightning.",
    }
    update_response = client.put(
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{created_entry['slug']}",
        headers=api_headers(dm_token),
        json=update_payload,
    )
    assert update_response.status_code == 200
    updated_entry = update_response.get_json()["entry"]
    assert updated_entry["title"] == update_payload["title"]
    assert updated_entry["entry_type"] == update_payload["entry_type"]
    assert "systems" in update_response.get_json()
    updated_systems_payload = update_response.get_json()["systems"]
    updated_source_row = next(
        row for row in updated_systems_payload["custom_entry_source_rows"] if row["source_id"] == created_entry["source_id"]
    )
    assert any(entry["slug"] == created_entry["slug"] for entry in updated_source_row["entries"])

    archive_response = client.post(
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{created_entry['slug']}/archive",
        headers=api_headers(dm_token),
    )
    assert archive_response.status_code == 200
    archived_entry = archive_response.get_json()["entry"]
    assert archived_entry["is_archived"] is True
    assert "systems" in archive_response.get_json()
    archived_systems_payload = archive_response.get_json()["systems"]
    archived_source_row = next(
        row for row in archived_systems_payload["custom_entry_source_rows"] if row["source_id"] == created_entry["source_id"]
    )
    archived_row_entry = next(
        entry for entry in archived_source_row["entries"] if entry["slug"] == created_entry["slug"]
    )
    assert archived_row_entry["is_archived"] is True

    restore_response = client.post(
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{created_entry['slug']}/restore",
        headers=api_headers(dm_token),
    )
    assert restore_response.status_code == 200
    restored_entry = restore_response.get_json()["entry"]
    assert restored_entry["is_archived"] is False
    assert "systems" in restore_response.get_json()
    restored_systems_payload = restore_response.get_json()["systems"]
    restored_source_row = next(
        row for row in restored_systems_payload["custom_entry_source_rows"] if row["source_id"] == created_entry["source_id"]
    )
    restored_row_entry = next(
        entry for entry in restored_source_row["entries"] if entry["slug"] == created_entry["slug"]
    )
    assert restored_row_entry["is_archived"] is False


def test_api_systems_custom_entry_mutations_preserve_auth_view_as_csrf_and_json_contract(
    client,
    app,
    users,
    sign_in,
):
    routes = (
        ("POST", "/api/v1/campaigns/linden-pass/systems/custom-entries"),
        (
            "PUT",
            "/api/v1/campaigns/linden-pass/systems/custom-entries/missing-entry",
        ),
        (
            "POST",
            "/api/v1/campaigns/linden-pass/systems/custom-entries/missing-entry/archive",
        ),
        (
            "POST",
            "/api/v1/campaigns/linden-pass/systems/custom-entries/missing-entry/restore",
        ),
    )

    for method, path in routes:
        missing_campaign = client.open(
            path.replace("linden-pass", "missing-campaign"),
            method=method,
            json={},
        )
        assert missing_campaign.status_code == 404

        anonymous = client.open(path, method=method, json={})
        assert anonymous.status_code == 401
        assert anonymous.get_json()["error"]["code"] == "auth_required"

    for actor in ("party", "outsider"):
        token = issue_api_token(
            app,
            users[actor]["email"],
            label=f"systems-custom-entry-{actor}",
        )
        for method, path in routes:
            denied = client.open(
                path,
                method=method,
                headers=api_headers(token),
                json={},
            )
            assert denied.status_code == 403
            assert denied.get_json()["error"]["code"] == "forbidden"

    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    for method, path in routes:
        view_as_denied = client.open(path, method=method, json={})
        assert view_as_denied.status_code == 403
        assert view_as_denied.get_json()["error"]["code"] == "view_as_read_only"

    app.config["CSRF_ENABLED"] = False
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    for method, path in routes:
        csrf_denied = client.open(path, method=method, json={})
        assert csrf_denied.status_code == 400
        assert csrf_denied.get_json()["error"]["code"] == "csrf_failed"

    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-custom-entry-json")
    bearer_results = [
        app.test_client().open(
            path,
            method=method,
            headers=api_headers(dm_token),
            json={},
        )
        for method, path in routes
    ]
    assert [response.status_code for response in bearer_results] == [400, 400, 400, 400]
    assert [response.get_json()["error"]["code"] for response in bearer_results] == [
        "invalid_json",
        "invalid_json",
        "validation_error",
        "validation_error",
    ]

    for method, path in routes[:2]:
        non_object = app.test_client().open(
            path,
            method=method,
            headers=api_headers(dm_token),
            json=[],
        )
        malformed = app.test_client().open(
            path,
            method=method,
            headers={**api_headers(dm_token), "Content-Type": "application/json"},
            data="{",
        )
        for response in (non_object, malformed):
            assert response.status_code == 400
            assert response.get_json()["error"] == {
                "code": "invalid_json",
                "message": "Request body must be a JSON object.",
            }


def test_api_systems_custom_entry_fields_lifecycle_and_sqlite_only_contract(
    client,
    app,
    users,
    monkeypatch,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-custom-fields")
    dm_headers = api_headers(dm_token)
    campaigns_root = Path(app.config["TEST_CAMPAIGNS_DIR"])
    campaign_files_before = {
        path.relative_to(campaigns_root): path.read_bytes()
        for path in campaigns_root.rglob("*")
        if path.is_file()
    }

    def reject_repository_refresh():
        raise AssertionError("custom Systems API mutations must not refresh the repository")

    monkeypatch.setattr(
        app.extensions["repository_store"],
        "refresh",
        reject_repository_refresh,
    )

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/systems/custom-entries",
        headers=dm_headers,
        json={
            "title": "API Contract Blade",
            "entry_type": "item",
            "slug_leaf": "api-contract-blade",
            "provenance": 17,
            "search_metadata": ["contract", "blade"],
            "body_markdown": "A **bright** blade.\n\n<script>alert('no')</script>",
            "mechanics_review_status": "approved",
            "item_mechanics": {"rarity": "rare"},
        },
    )
    assert create_response.status_code == 200
    create_payload = create_response.get_json()
    entry = create_payload["entry"]
    assert create_payload["ok"] is True
    assert set(create_payload) == {"ok", "entry", "systems"}
    assert entry["slug"] == "custom-linden-pass-api-contract-blade"
    assert entry["visibility"] == "players"
    assert entry["provenance"] == "17"
    assert entry["search_metadata"] == "['contract', 'blade']"
    assert entry["item_mechanics"]["review_status"] == "approved"
    assert "rarity" in entry["item_mechanics"]["modeled_fields"]
    assert "<script" not in entry["body_markdown"]
    assert "<script" not in entry["rendered_html"]

    duplicate = client.post(
        "/api/v1/campaigns/linden-pass/systems/custom-entries",
        headers=dm_headers,
        json={
            "title": "Duplicate",
            "entry_type": "rule",
            "slug_leaf": "api-contract-blade",
            "body_markdown": "Duplicate body.",
        },
    )
    assert duplicate.status_code == 400
    assert duplicate.get_json()["error"]["code"] == "invalid_json"

    dm_private = client.post(
        "/api/v1/campaigns/linden-pass/systems/custom-entries",
        headers=dm_headers,
        json={
            "title": "DM Private Attempt",
            "entry_type": "rule",
            "slug_leaf": "dm-private-attempt",
            "visibility": "private",
            "body_markdown": "Private body.",
        },
    )
    assert dm_private.status_code == 400
    assert dm_private.get_json()["error"]["code"] == "invalid_json"

    admin_token = issue_api_token(
        app,
        users["admin"]["email"],
        label="systems-custom-private-admin",
    )
    admin_private = client.post(
        "/api/v1/campaigns/linden-pass/systems/custom-entries",
        headers=api_headers(admin_token),
        json={
            "title": "Admin Private Entry",
            "entry_type": "rule",
            "slug_leaf": "admin-private-entry",
            "visibility": "private",
            "body_markdown": "Private body.",
        },
    )
    assert admin_private.status_code == 200
    assert admin_private.get_json()["entry"]["visibility"] == "private"

    update_response = client.put(
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{entry['slug']}",
        headers=dm_headers,
        json={
            "title": "API Contract Blade Revised",
            "entry_type": "item",
            "slug_leaf": "ignored-new-slug",
            "visibility": "dm",
            "body_markdown": "Revised body.",
            "item_mechanics_review_status": "manual_review",
            "mechanics_review_status": "approved",
            "item_mechanics": ["not", "an", "object"],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.get_json()["entry"]
    assert updated["slug"] == entry["slug"]
    assert updated["entry_key"] == entry["entry_key"]
    assert updated["title"] == "API Contract Blade Revised"
    assert updated["item_mechanics"]["review_status"] == "manual_review"
    assert "rarity" not in updated["item_mechanics"]["modeled_fields"]

    archive_url = (
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{entry['slug']}/archive"
    )
    service = app.extensions["systems_service"]
    original_get_entry = service.get_custom_campaign_entry_by_slug
    refetch_calls = 0

    def omit_archive_refetch(*args, **kwargs):
        nonlocal refetch_calls
        refetch_calls += 1
        return original_get_entry(*args, **kwargs) if refetch_calls == 1 else None

    monkeypatch.setattr(service, "get_custom_campaign_entry_by_slug", omit_archive_refetch)
    for index, (body, content_type) in enumerate(
        (("{", "application/json"), ("[]", "application/json"))
    ):
        archived = client.post(
            archive_url,
            headers={**dm_headers, "Content-Type": content_type},
            data=body,
        )
        assert archived.status_code == 200
        assert archived.get_json()["entry"]["is_archived"] is True
        if index == 0:
            assert refetch_calls == 2
            monkeypatch.setattr(
                service,
                "get_custom_campaign_entry_by_slug",
                original_get_entry,
            )

    restore_url = (
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{entry['slug']}/restore"
    )
    refetch_calls = 0

    def omit_restore_refetch(*args, **kwargs):
        nonlocal refetch_calls
        refetch_calls += 1
        return original_get_entry(*args, **kwargs) if refetch_calls == 1 else None

    monkeypatch.setattr(service, "get_custom_campaign_entry_by_slug", omit_restore_refetch)
    for index, (body, content_type) in enumerate(
        (("{", "application/json"), ("[]", "application/json"))
    ):
        restored = client.post(
            restore_url,
            headers={**dm_headers, "Content-Type": content_type},
            data=body,
        )
        assert restored.status_code == 200
        assert restored.get_json()["entry"]["is_archived"] is False
        if index == 0:
            assert refetch_calls == 2
            monkeypatch.setattr(
                service,
                "get_custom_campaign_entry_by_slug",
                original_get_entry,
            )

    missing_update = client.put(
        "/api/v1/campaigns/linden-pass/systems/custom-entries/missing-entry",
        headers=dm_headers,
        json={
            "title": "Missing",
            "entry_type": "rule",
            "body_markdown": "Missing body.",
        },
    )
    assert missing_update.status_code == 400
    assert missing_update.get_json()["error"]["code"] == "invalid_json"
    for suffix in ("archive", "restore"):
        missing = client.post(
            f"/api/v1/campaigns/linden-pass/systems/custom-entries/missing-entry/{suffix}",
            headers=dm_headers,
        )
        assert missing.status_code == 400
        assert missing.get_json()["error"]["code"] == "validation_error"

    with app.app_context():
        event_counts = {
            event_type: len(
                AuthStore().list_recent_audit_events(
                    event_type=event_type,
                    campaign_slug="linden-pass",
                )
            )
            for event_type in (
                "campaign_systems_custom_entry_created",
                "campaign_systems_custom_entry_updated",
                "campaign_systems_custom_entry_archived",
                "campaign_systems_custom_entry_restored",
            )
        }
    assert event_counts == {
        "campaign_systems_custom_entry_created": 2,
        "campaign_systems_custom_entry_updated": 1,
        "campaign_systems_custom_entry_archived": 2,
        "campaign_systems_custom_entry_restored": 2,
    }
    assert {
        path.relative_to(campaigns_root): path.read_bytes()
        for path in campaigns_root.rglob("*")
        if path.is_file()
    } == campaign_files_before


def test_api_systems_custom_entry_invalid_create_preserves_scaffold_partial_failure(
    client,
    app,
    users,
):
    source_id = "CUSTOM-LINDEN-PASS"
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-custom-scaffold")

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        assert store.get_source(library_slug, source_id) is None

    response = client.post(
        "/api/v1/campaigns/linden-pass/systems/custom-entries",
        headers=api_headers(dm_token),
        json={"title": "", "entry_type": "rule", "body_markdown": "Body."},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_json"

    with app.app_context():
        source = store.get_source(library_slug, source_id)
        enabled = store.get_campaign_enabled_source("linden-pass", source_id)
        policy = store.get_campaign_policy("linden-pass")
        assert source is not None
        assert enabled is not None and enabled.is_enabled is True
        assert policy is not None
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_custom_entry_created",
            campaign_slug="linden-pass",
        )


def test_api_systems_custom_entry_preserves_service_audit_response_and_cache_failure_windows(
    client,
    app,
    users,
    monkeypatch,
):
    create_url = "/api/v1/campaigns/linden-pass/systems/custom-entries"
    dm_token = issue_api_token(app, users["dm"]["email"], label="systems-custom-faults")
    headers = api_headers(dm_token)
    with app.app_context():
        service = app.extensions["systems_service"]
        auth_store = app.extensions["auth_store"]
        original_create = service.create_custom_campaign_entry

        def fail_service(*args, **kwargs):
            raise RuntimeError("custom entry service unavailable")

        monkeypatch.setattr(service, "create_custom_campaign_entry", fail_service)
        with pytest.raises(RuntimeError, match="custom entry service unavailable"):
            client.post(
                create_url,
                headers=headers,
                json={
                    "title": "Service Failure",
                    "entry_type": "rule",
                    "slug_leaf": "service-failure",
                    "body_markdown": "Body.",
                },
            )
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_custom_entry_created",
            campaign_slug="linden-pass",
        )
        monkeypatch.setattr(service, "create_custom_campaign_entry", original_create)

        original_audit = auth_store.write_audit_event

        def fail_audit(*args, **kwargs):
            raise RuntimeError("custom entry audit unavailable")

        monkeypatch.setattr(auth_store, "write_audit_event", fail_audit)
        with pytest.raises(RuntimeError, match="custom entry audit unavailable"):
            client.post(
                create_url,
                headers=headers,
                json={
                    "title": "Audit Failure",
                    "entry_type": "rule",
                    "slug_leaf": "audit-failure",
                    "body_markdown": "Body.",
                },
            )
        assert service.get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-audit-failure",
        ) is not None
        monkeypatch.setattr(auth_store, "write_audit_event", original_audit)

        audit_attempts: list[str] = []

        def record_audit(*args, **kwargs):
            audit_attempts.append(kwargs["metadata"]["entry_slug"])
            return original_audit(*args, **kwargs)

        monkeypatch.setattr(auth_store, "write_audit_event", record_audit)
        dependencies = _systems_api_mutation_dependencies(
            app,
            "api.systems_custom_entry_create",
        )
        original_full_payload = dependencies.build_dm_content_systems_payload

        def fail_full_payload(*args, **kwargs):
            raise RuntimeError("custom entry payload unavailable")

        object.__setattr__(
            dependencies,
            "build_dm_content_systems_payload",
            fail_full_payload,
        )
        with pytest.raises(RuntimeError, match="custom entry payload unavailable"):
            client.post(
                create_url,
                headers=headers,
                json={
                    "title": "Payload Failure",
                    "entry_type": "rule",
                    "slug_leaf": "payload-failure",
                    "body_markdown": "Body.",
                },
            )
        object.__setattr__(
            dependencies,
            "build_dm_content_systems_payload",
            original_full_payload,
        )
        assert service.get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-payload-failure",
        ) is not None
        assert audit_attempts == [
            "custom-linden-pass-payload-failure"
        ]

        store = app.extensions["systems_store"]
        original_serializer = dependencies.serialize_custom_systems_entry

        def fail_serializer(*args, **kwargs):
            raise RuntimeError("custom entry serializer unavailable")

        object.__setattr__(
            dependencies,
            "serialize_custom_systems_entry",
            fail_serializer,
        )
        with pytest.raises(RuntimeError, match="custom entry serializer unavailable"):
            client.post(
                create_url,
                headers=headers,
                json={
                    "title": "Serializer Failure",
                    "entry_type": "rule",
                    "slug_leaf": "serializer-failure",
                    "body_markdown": "Body.",
                },
            )
        serializer_entry = store.get_entry_by_slug(
            service.get_campaign_library_slug("linden-pass"),
            "custom-linden-pass-serializer-failure",
        )
        assert serializer_entry is not None
        assert audit_attempts == [
            "custom-linden-pass-payload-failure",
            "custom-linden-pass-serializer-failure",
        ]
        object.__setattr__(
            dependencies,
            "serialize_custom_systems_entry",
            original_serializer,
        )
        monkeypatch.setattr(auth_store, "write_audit_event", original_audit)

        seeded = original_create(
            "linden-pass",
            title="Cache Failure",
            entry_type="rule",
            slug_leaf="cache-failure",
            body_markdown="Body.",
            actor_user_id=users["dm"]["id"],
            can_set_private=False,
        )

        def fail_cache_clear():
            raise RuntimeError("systems cache unavailable")

        monkeypatch.setattr(
            "player_wiki.systems_service._systems_service_cache_clear",
            fail_cache_clear,
        )
        with pytest.raises(RuntimeError, match="systems cache unavailable"):
            client.post(
                f"{create_url}/{seeded.slug}/archive",
                headers=headers,
            )
        override = service.store.get_campaign_entry_override(
            "linden-pass",
            seeded.entry_key,
        )
        assert override is not None and override.is_enabled_override is False
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_custom_entry_archived",
            campaign_slug="linden-pass",
        )


def test_api_systems_imports_campaign_item_page_as_reviewed_mechanics_entry(
    client,
    app,
    users,
):
    item_path = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "content" / "items" / "api-consecrated-huran-blade.md"
    item_path.write_text(
        "\n".join(
            [
                "---",
                "title: API Consecrated Huran Blade",
                "section: Items",
                "page_type: item",
                "source_ref: API test item page",
                "published: true",
                "---",
                "",
                "*Weapon (longsword), uncommon (requires attunement)*",
                "",
                "You gain a +1 bonus to attack and damage rolls made with this magic weapon.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-item-mechanics-api")

    systems_response = client.get(
        "/api/v1/campaigns/linden-pass/dm-content/systems",
        headers=api_headers(dm_token),
    )
    assert systems_response.status_code == 200
    systems_payload = systems_response.get_json()
    item_page_row = next(
        row
        for row in systems_payload["campaign_item_page_rows"]
        if row["page_ref"] == "items/api-consecrated-huran-blade"
    )
    assert item_page_row["has_structured_item"] is False

    import_response = client.post(
        "/api/v1/campaigns/linden-pass/systems/item-mechanics/import",
        headers=api_headers(dm_token),
        json={
            "page_ref": "items/api-consecrated-huran-blade",
            "visibility": "players",
            "item_mechanics_review_status": "approved",
        },
    )
    assert import_response.status_code == 200
    payload = import_response.get_json()
    entry = payload["entry"]
    assert entry["entry_type"] == "item"
    assert entry["linked_published_page_ref"] == "items/api-consecrated-huran-blade"
    assert entry["item_mechanics"]["review_status"] == "approved"
    assert entry["item_mechanics"]["support_state"] == "modeled"
    assert "base_item" in entry["item_mechanics"]["modeled_fields"]
    assert "bonus_weapon" in entry["item_mechanics"]["modeled_fields"]

    refreshed_row = next(
        row
        for row in payload["systems"]["campaign_item_page_rows"]
        if row["page_ref"] == "items/api-consecrated-huran-blade"
    )
    assert refreshed_row["has_structured_item"] is True
    assert refreshed_row["entry_slug"] == entry["slug"]
    assert refreshed_row["item_mechanics"]["review_status"] == "approved"


def test_api_item_mechanics_import_preserves_auth_view_as_csrf_json_and_options_contract(
    client,
    app,
    users,
    sign_in,
    set_campaign_visibility,
):
    item_url = "/api/v1/campaigns/linden-pass/systems/item-mechanics/import"
    missing_campaign_url = item_url.replace("linden-pass", "missing-campaign")

    options_response = client.open(item_url, method="OPTIONS")
    assert options_response.status_code == 200
    assert {
        method.strip() for method in options_response.headers["Allow"].split(",")
    } == {"POST", "OPTIONS"}

    assert client.post(missing_campaign_url, json={}).status_code == 404
    anonymous = client.post(item_url, json={})
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    for actor in ("party", "outsider"):
        token = issue_api_token(
            app,
            users[actor]["email"],
            label=f"item-mechanics-{actor}",
        )
        denied = client.post(
            item_url,
            headers=api_headers(token),
            json={},
        )
        assert denied.status_code == 403
        assert denied.get_json()["error"]["code"] == "forbidden"

    dm_token = issue_api_token(app, users["dm"]["email"], label="item-mechanics-dm")
    for response in (
        client.post(item_url, headers=api_headers(dm_token), json=[]),
        client.post(
            item_url,
            headers={**api_headers(dm_token), "Content-Type": "application/json"},
            data="{",
        ),
    ):
        assert response.status_code == 400
        assert response.get_json()["error"] == {
            "code": "invalid_json",
            "message": "Request body must be a JSON object.",
        }

    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    view_as_denied = client.post(item_url, json={})
    assert view_as_denied.status_code == 403
    assert view_as_denied.get_json()["error"]["code"] == "view_as_read_only"

    app.config["CSRF_ENABLED"] = False
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    csrf_denied = client.post(item_url, json={})
    assert csrf_denied.status_code == 400
    assert csrf_denied.get_json()["error"]["code"] == "csrf_failed"

    bearer_validation = app.test_client().post(
        item_url,
        headers=api_headers(dm_token),
        json={},
    )
    assert bearer_validation.status_code == 400
    assert bearer_validation.get_json()["error"]["code"] == "invalid_json"

    set_campaign_visibility("linden-pass", systems="private")
    scope_denied = app.test_client().post(
        item_url,
        headers=api_headers(dm_token),
        json={},
    )
    assert scope_denied.status_code == 403
    assert scope_denied.get_json()["error"]["code"] == "forbidden"

    admin_token = issue_api_token(
        app,
        users["admin"]["email"],
        label="item-mechanics-admin",
    )
    admin_validation = app.test_client().post(
        item_url,
        headers=api_headers(admin_token),
        json={},
    )
    assert admin_validation.status_code == 400
    assert admin_validation.get_json()["error"]["code"] == "invalid_json"


def test_api_item_mechanics_import_preserves_alias_coercion_private_and_audit_metadata(
    client,
    app,
    users,
    monkeypatch,
):
    page_ref = "items/api-item-mechanics-alias-contract"
    _write_published_api_item_page(
        app,
        page_ref,
        title="API Item Mechanics Alias Contract",
    )
    item_url = "/api/v1/campaigns/linden-pass/systems/item-mechanics/import"
    admin_token = issue_api_token(
        app,
        users["admin"]["email"],
        label="item-mechanics-alias-admin",
    )

    with app.app_context():
        service = app.extensions["systems_service"]
        original_upsert = service.upsert_campaign_item_mechanics_entry_from_page
        captured: dict[str, object] = {}

        def capture_upsert(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return original_upsert(*args, **kwargs)

        monkeypatch.setattr(
            service,
            "upsert_campaign_item_mechanics_entry_from_page",
            capture_upsert,
        )
        response = client.post(
            item_url,
            headers=api_headers(admin_token),
            json={
                "page_ref": page_ref,
                "visibility": "private",
                "mechanics_review_status": "manual_review",
                "item_mechanics": ["ignored non-object mechanics"],
            },
        )
        assert response.status_code == 200
        entry_payload = response.get_json()["entry"]

        assert captured["args"] == ("linden-pass", page_ref)
        assert captured["kwargs"] == {
            "visibility": "private",
            "item_mechanics_review_status": "manual_review",
            "item_mechanics": None,
            "actor_user_id": users["admin"]["id"],
            "can_set_private": True,
        }
        entry = service.get_campaign_item_entry_by_page_ref(
            "linden-pass",
            page_ref,
        )
        assert entry is not None
        assert entry_payload["slug"] == entry.slug
        assert entry.metadata["campaign_item_mechanics_review_status"] == "manual_review"

        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_item_mechanics_imported",
            campaign_slug="linden-pass",
        )
        assert len(events) == 1
        assert events[0].actor_user_id == users["admin"]["id"]
        assert events[0].metadata == {
            "entry_key": entry.entry_key,
            "entry_slug": entry.slug,
            "entry_type": "item",
            "page_ref": page_ref,
            "source": "api",
        }


def test_api_item_mechanics_import_preserves_audit_and_response_failure_windows(
    client,
    app,
    users,
    monkeypatch,
):
    audit_page_ref = "items/api-item-mechanics-audit-failure"
    serializer_page_ref = "items/api-item-mechanics-serializer-failure"
    payload_page_ref = "items/api-item-mechanics-payload-failure"
    _write_published_api_item_page(
        app,
        audit_page_ref,
        title="API Item Mechanics Audit Failure",
    )
    _write_published_api_item_page(
        app,
        serializer_page_ref,
        title="API Item Mechanics Serializer Failure",
    )
    _write_published_api_item_page(
        app,
        payload_page_ref,
        title="API Item Mechanics Payload Failure",
    )
    item_url = "/api/v1/campaigns/linden-pass/systems/item-mechanics/import"
    dm_token = issue_api_token(
        app,
        users["dm"]["email"],
        label="item-mechanics-failure-windows",
    )
    headers = api_headers(dm_token)

    with app.app_context():
        service = app.extensions["systems_service"]
        auth_store = app.extensions["auth_store"]
        original_audit = auth_store.write_audit_event

        def fail_audit(*args, **kwargs):
            raise RuntimeError("item mechanics audit unavailable")

        monkeypatch.setattr(auth_store, "write_audit_event", fail_audit)
        with pytest.raises(RuntimeError, match="item mechanics audit unavailable"):
            client.post(
                item_url,
                headers=headers,
                json={"page_ref": audit_page_ref},
            )
        assert service.get_campaign_item_entry_by_page_ref(
            "linden-pass",
            audit_page_ref,
        ) is not None
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_item_mechanics_imported",
            campaign_slug="linden-pass",
        )

        monkeypatch.setattr(auth_store, "write_audit_event", original_audit)
        dependencies = _systems_api_mutation_dependencies(
            app,
            "api.systems_item_mechanics_import",
        )
        original_serializer = dependencies.serialize_custom_systems_entry
        original_full_payload = dependencies.build_dm_content_systems_payload

        def fail_serializer(*args, **kwargs):
            raise RuntimeError("item mechanics serializer unavailable")

        object.__setattr__(
            dependencies,
            "serialize_custom_systems_entry",
            fail_serializer,
        )
        try:
            with pytest.raises(RuntimeError, match="item mechanics serializer unavailable"):
                client.post(
                    item_url,
                    headers=headers,
                    json={"page_ref": serializer_page_ref},
                )
        finally:
            object.__setattr__(
                dependencies,
                "serialize_custom_systems_entry",
                original_serializer,
            )

        serializer_entry = service.get_campaign_item_entry_by_page_ref(
            "linden-pass",
            serializer_page_ref,
        )
        assert serializer_entry is not None
        serializer_events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_item_mechanics_imported",
            campaign_slug="linden-pass",
        )
        assert len(serializer_events) == 1
        assert serializer_events[0].metadata["entry_key"] == serializer_entry.entry_key
        assert serializer_events[0].metadata["page_ref"] == serializer_page_ref

        def fail_full_payload(*args, **kwargs):
            raise RuntimeError("item mechanics payload unavailable")

        object.__setattr__(
            dependencies,
            "build_dm_content_systems_payload",
            fail_full_payload,
        )
        try:
            with pytest.raises(RuntimeError, match="item mechanics payload unavailable"):
                client.post(
                    item_url,
                    headers=headers,
                    json={"page_ref": payload_page_ref},
                )
        finally:
            object.__setattr__(
                dependencies,
                "build_dm_content_systems_payload",
                original_full_payload,
            )

        entry = service.get_campaign_item_entry_by_page_ref(
            "linden-pass",
            payload_page_ref,
        )
        assert entry is not None
        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_item_mechanics_imported",
            campaign_slug="linden-pass",
        )
        assert len(events) == 2
        payload_event = next(
            event
            for event in events
            if event.metadata["page_ref"] == payload_page_ref
        )
        assert payload_event.metadata["entry_key"] == entry.entry_key
        assert payload_event.metadata["source"] == "api"


def test_api_campaign_item_mechanics_import_preserves_item_use_actions(
    client,
    app,
    users,
):
    item_path = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "content" / "items" / "api-innovators-bolt.md"
    item_path.write_text(
        "\n".join(
            [
                "---",
                "title: API Innovator's Bolt",
                "section: Items",
                "page_type: item",
                "source_ref: API test item page",
                "published: true",
                "---",
                "",
                "*Weapon (pistol), very rare (requires attunement by an artificer)*",
                "",
                "A spell-slot-loaded firearm.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-innovators-bolt-api")

    import_response = client.post(
        "/api/v1/campaigns/linden-pass/systems/item-mechanics/import",
        headers=api_headers(dm_token),
        json={
            "page_ref": "items/api-innovators-bolt",
            "visibility": "players",
            "item_mechanics_review_status": "approved",
            "item_mechanics": approved_innovators_bolt_item_mechanics(),
        },
    )

    assert import_response.status_code == 200
    entry = import_response.get_json()["entry"]
    assert entry["item_mechanics"]["review_status"] == "approved"
    assert "item_use_actions" in entry["item_mechanics"]["modeled_fields"]

    with app.app_context():
        library_slug = app.extensions["systems_service"].get_campaign_library_slug("linden-pass")
        stored_entry = app.extensions["systems_store"].get_entry_by_slug(library_slug, entry["slug"])
    assert stored_entry is not None
    actions = stored_entry.metadata["item_use_actions"]
    assert actions[0]["id"] == "innovators-bolt-enchanted-bullet"
    choices = actions[0]["choices"]
    assert [choice["id"] for choice in choices] == ["incendiary", "booming", "smoke"]
    assert choices[0]["damage_scaling"] == {"per_slot_level": "1d6 fire"}
    assert choices[1]["save"]["ability"] == "con"
    assert choices[2]["damage_scaling"] == {"per_slot_level": "1d6 bludgeoning"}
    assert all("table-managed" in choice["summary"] for choice in choices)
    assert all("condition" not in choice for choice in choices)
    assert all("target_effect" not in choice for choice in choices)
    assert all("area" not in choice for choice in choices)


def test_campaign_item_mechanics_rejects_nonpublished_item_pages_before_systems_writes(
    client,
    app,
    users,
):
    content_root = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "content"
    unpublished_ref = "items/unpublished-mechanics-source"
    non_item_ref = "npcs/not-an-item-mechanics-source"
    (content_root / f"{unpublished_ref}.md").parent.mkdir(parents=True, exist_ok=True)
    (content_root / f"{unpublished_ref}.md").write_text(
        "\n".join(
            [
                "---",
                "title: Unpublished Mechanics Source",
                "section: Items",
                "page_type: item",
                "source_ref: Unpublished test item",
                "published: false",
                "---",
                "",
                "This item is not published.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (content_root / f"{non_item_ref}.md").parent.mkdir(parents=True, exist_ok=True)
    (content_root / f"{non_item_ref}.md").write_text(
        "\n".join(
            [
                "---",
                "title: Not An Item Mechanics Source",
                "section: NPCs",
                "page_type: npc",
                "source_ref: Non-item test page",
                "published: true",
                "---",
                "",
                "This published page is not an item.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    expected_message = (
        "Choose a valid published item page before importing item mechanics."
    )
    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        source_id = service.get_campaign_custom_source_id("linden-pass")

        def systems_state():
            source = store.get_source(library_slug, source_id)
            return (
                source,
                store.get_campaign_policy("linden-pass"),
                store.get_campaign_enabled_source("linden-pass", source_id),
                tuple(
                    store.list_entries_for_source(
                        library_slug,
                        source_id,
                        limit=None,
                    )
                )
                if source is not None
                else (),
                tuple(store.list_campaign_entry_overrides("linden-pass", library_slug)),
                tuple(
                    AuthStore().list_recent_audit_events(
                        event_type="campaign_systems_item_mechanics_imported",
                        campaign_slug="linden-pass",
                    )
                ),
            )

        before = systems_state()
        listed_refs = {
            str(row["page_ref"])
            for row in service.list_campaign_item_page_rows("linden-pass")
        }
        assert unpublished_ref not in listed_refs
        assert non_item_ref not in listed_refs
        for page_ref in ("items/missing-mechanics-source", non_item_ref, unpublished_ref):
            with pytest.raises(
                SystemsPolicyValidationError,
                match="Choose a valid published item page before importing item mechanics",
            ) as exc_info:
                service.upsert_campaign_item_mechanics_entry_from_page(
                    "linden-pass",
                    page_ref,
                    actor_user_id=users["dm"]["id"],
                    can_set_private=False,
                )
            assert str(exc_info.value) == expected_message
        assert systems_state() == before

    dm_token = issue_api_token(
        app,
        users["dm"]["email"],
        label="unpublished-item-mechanics-policy",
    )
    for page_ref in ("items/missing-mechanics-source", non_item_ref, unpublished_ref):
        response = client.post(
            "/api/v1/campaigns/linden-pass/systems/item-mechanics/import",
            headers=api_headers(dm_token),
            json={"page_ref": page_ref},
        )
        assert response.status_code == 400
        assert response.get_json()["error"] == {
            "code": "invalid_json",
            "message": expected_message,
        }

    with app.app_context():
        assert systems_state() == before


def test_unpublishing_item_page_preserves_existing_linked_systems_mechanics(
    client,
    app,
    users,
):
    page_ref = "items/published-then-unpublished-mechanics"
    page_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "content"
        / f"{page_ref}.md"
    )

    def write_page(*, published: bool) -> None:
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            "\n".join(
                [
                    "---",
                    "title: Published Then Unpublished Mechanics",
                    "section: Items",
                    "page_type: item",
                    "source_ref: Publication-state test item",
                    f"published: {'true' if published else 'false'}",
                    "---",
                    "",
                    "*Weapon (longsword), rare*",
                    "",
                    "You gain a +1 bonus to attack and damage rolls with this weapon.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    expected_message = (
        "Choose a valid published item page before importing item mechanics."
    )
    write_page(published=True)
    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        auth_store = app.extensions["auth_store"]
        entry = service.upsert_campaign_item_mechanics_entry_from_page(
            "linden-pass",
            page_ref,
            visibility="players",
            item_mechanics_review_status="approved",
            actor_user_id=users["dm"]["id"],
            can_set_private=False,
        )
        auth_store.write_audit_event(
            event_type="campaign_systems_item_mechanics_imported",
            actor_user_id=users["dm"]["id"],
            campaign_slug="linden-pass",
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "entry_type": entry.entry_type,
                "page_ref": page_ref,
                "source": "test",
            },
        )
        library_slug = service.get_campaign_library_slug("linden-pass")
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        audits = tuple(
            auth_store.list_recent_audit_events(
                event_type="campaign_systems_item_mechanics_imported",
                campaign_slug="linden-pass",
            )
        )
        assert override is not None
        assert entry.metadata["campaign_item_mechanics_review_status"] == "approved"

    write_page(published=False)
    with app.app_context():
        app.extensions["repository_store"].refresh()
        assert page_ref not in {
            str(row["page_ref"])
            for row in service.list_campaign_item_page_rows("linden-pass")
        }
        linked_entry = service.get_campaign_item_entry_by_page_ref(
            "linden-pass",
            page_ref,
        )
        assert linked_entry == entry
        with pytest.raises(SystemsPolicyValidationError) as exc_info:
            service.upsert_campaign_item_mechanics_entry_from_page(
                "linden-pass",
                page_ref,
                actor_user_id=users["dm"]["id"],
                can_set_private=False,
            )
        assert str(exc_info.value) == expected_message
        with pytest.raises(SystemsPolicyValidationError) as exc_info:
            service.update_custom_campaign_entry(
                "linden-pass",
                entry.slug,
                title=entry.title,
                entry_type="item",
                visibility="players",
                body_markdown=str(entry.body.get("markdown") or ""),
                source_page_ref=page_ref,
                actor_user_id=users["dm"]["id"],
                can_set_private=False,
            )
        assert str(exc_info.value) == (
            "Choose a valid published item page before saving item mechanics."
        )

    dm_token = issue_api_token(
        app,
        users["dm"]["email"],
        label="unpublished-linked-item-mechanics",
    )
    response = client.post(
        "/api/v1/campaigns/linden-pass/systems/item-mechanics/import",
        headers=api_headers(dm_token),
        json={"page_ref": page_ref},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "invalid_json",
        "message": expected_message,
    }

    with app.app_context():
        assert store.get_entry(library_slug, entry.entry_key) == entry
        assert store.get_campaign_entry_override("linden-pass", entry.entry_key) == override
        assert service.get_campaign_item_entry_by_page_ref("linden-pass", page_ref) == entry
        assert tuple(
            auth_store.list_recent_audit_events(
                event_type="campaign_systems_item_mechanics_imported",
                campaign_slug="linden-pass",
            )
        ) == audits


def test_api_systems_import_endpoints_require_admin_and_record_runs(client, app, users, tmp_path):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-api")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-import-api")
    with app.app_context():
        audits_before = AuthStore().list_recent_audit_events(limit=1000)
    archive_bytes = _build_systems_import_archive(tmp_path)
    import_payload = {
        "source_ids": ["MM"],
        "entry_types": ["monster"],
        "archive": {
            "filename": "mm-import.zip",
            "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
        },
    }

    blocked_response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(dm_token),
        json=import_payload,
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    import_response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json=import_payload,
    )
    assert import_response.status_code == 200
    import_payload = import_response.get_json()
    assert import_payload["ok"] is True

    import_result = import_payload["import_results"][0]
    assert import_result["source_id"] == "MM"
    assert import_result["import_version"] == "mm-import"
    assert import_result["imported_count"] == 1
    assert import_result["imported_by_type"] == {"monster": 1}
    assert import_result["source_files"] == ["data/bestiary/bestiary-mm.json"]

    import_run = import_payload["import_runs"][0]
    assert import_run["status"] == "completed"
    assert import_run["source_id"] == "MM"
    assert import_run["import_version"] == "mm-import"
    assert import_run["source_path"] == "api-upload:mm-import.zip"
    assert import_run["started_by_user_id"] == users["admin"]["id"]
    assert import_run["summary"]["entry_types"] == ["monster"]
    assert import_run["summary"]["imported_count"] == 1
    assert import_run["summary"]["source_files"] == ["data/bestiary/bestiary-mm.json"]

    blocked_runs = client.get("/api/v1/systems/import-runs", headers=api_headers(dm_token))
    assert blocked_runs.status_code == 403
    assert blocked_runs.get_json()["error"]["code"] == "forbidden"

    list_response = client.get("/api/v1/systems/import-runs?source_id=MM", headers=api_headers(admin_token))
    assert list_response.status_code == 200
    listed_run = list_response.get_json()["import_runs"][0]
    assert listed_run["id"] == import_run["id"]
    assert listed_run["summary"]["imported_count"] == 1

    detail_response = client.get(
        f"/api/v1/systems/import-runs/{import_run['id']}",
        headers=api_headers(admin_token),
    )
    assert detail_response.status_code == 200
    assert detail_response.get_json()["import_run"]["id"] == import_run["id"]

    dm_source = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster",
        headers=api_headers(dm_token),
    )
    assert dm_source.status_code == 200
    imported_entries = dm_source.get_json()["entries"]
    assert len(imported_entries) == 1
    assert imported_entries[0]["title"] == "Goblin"
    with app.app_context():
        assert AuthStore().list_recent_audit_events(limit=1000) == audits_before


def test_api_systems_dnd5e_import_preserves_auth_view_as_csrf_and_methods(
    client,
    app,
    sign_in,
    users,
):
    url = "/api/v1/systems/imports/dnd5e"
    admin_token = issue_api_token(app, users["admin"]["email"], label="ingest-auth-admin")
    dm_token = issue_api_token(app, users["dm"]["email"], label="ingest-auth-dm")
    player_token = issue_api_token(
        app,
        users["party"]["email"],
        label="ingest-auth-player",
    )

    options_response = client.open(url, method="OPTIONS")
    assert options_response.status_code == 200
    assert set(options_response.headers["Allow"].split(", ")) == {
        "POST",
        "OPTIONS",
    }
    head_response = client.head(url, headers=api_headers(admin_token))
    assert head_response.status_code == 405
    assert head_response.data == b""

    anonymous = client.post(url, json={})
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"
    for token in (dm_token, player_token):
        denied = client.post(url, headers=api_headers(token), json={})
        assert denied.status_code == 403
        assert denied.get_json()["error"]["code"] == "forbidden"

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    view_as_admin = client.post(url, json={})
    assert view_as_admin.status_code == 400
    assert view_as_admin.get_json()["error"] == {
        "code": "validation_error",
        "message": "source_ids must be an array of source IDs.",
    }

    app.config["CSRF_ENABLED"] = True
    session_csrf_denied = client.post(url, json={})
    assert session_csrf_denied.status_code == 400
    assert session_csrf_denied.get_json()["error"]["code"] == "csrf_failed"
    bearer_bypass = client.post(url, headers=api_headers(admin_token), json={})
    assert bearer_bypass.status_code == 400
    assert bearer_bypass.get_json()["error"]["code"] == "validation_error"


def test_api_systems_dnd5e_import_preserves_request_coercion_defaults_and_cleanup(
    client,
    app,
    users,
    tmp_path,
):
    url = "/api/v1/systems/imports/dnd5e"
    admin_token = issue_api_token(app, users["admin"]["email"], label="ingest-coercion")
    headers = api_headers(admin_token)
    archive_base64 = base64.b64encode(_build_systems_import_archive(tmp_path)).decode(
        "ascii"
    )
    dependencies = _systems_api_mutation_dependencies(
        app,
        "api.systems_import_dnd5e",
    )
    original_build_importer = dependencies.build_importer
    calls: list[dict[str, object]] = []
    extracted_roots: list[Path] = []

    class CapturingImporter:
        def __init__(self, data_root):
            extracted_roots.append(Path(data_root))

        def import_sources(self, source_ids, **kwargs):
            calls.append({"source_ids": source_ids, **kwargs})
            return [
                Dnd5eImportResult(
                    source_id=source_ids[0],
                    import_run_id=900000 + len(calls),
                    import_version=str(kwargs["import_version"]),
                    imported_count=0,
                    imported_by_type={},
                    source_files=[],
                )
            ]

    object.__setattr__(
        dependencies,
        "build_importer",
        lambda data_root: CapturingImporter(data_root),
    )
    with app.app_context():
        audits_before = AuthStore().list_recent_audit_events(limit=1000)

    defaulted = client.post(
        url,
        headers=headers,
        json={
            "source_ids": [None, " mm ", "MM", "", 42],
            "entry_types": [None, " MONSTER ", "monster", ""],
            "archive": {
                "filename": "  Archive.Name.ZIP ",
                "data_base64": archive_base64,
            },
            "ignored": "field",
        },
    )
    assert defaulted.status_code == 200
    assert calls[-1] == {
        "source_ids": ["MM", "MM", "42"],
        "entry_types": ["monster", "monster"],
        "started_by_user_id": users["admin"]["id"],
        "import_version": "Archive.Name",
        "source_path_label": "api-upload:Archive.Name.ZIP",
    }
    assert defaulted.get_json()["import_runs"] == []

    overridden = client.post(
        url,
        headers=headers,
        json={
            "source_ids": [" mm "],
            "archive": {
                "filename": "mm.zip",
                "data_base64": archive_base64,
            },
            "import_version": " custom-version ",
            "source_path_label": " custom-source ",
        },
    )
    assert overridden.status_code == 200
    assert calls[-1] == {
        "source_ids": ["MM"],
        "entry_types": None,
        "started_by_user_id": users["admin"]["id"],
        "import_version": "custom-version",
        "source_path_label": "custom-source",
    }

    invalid_types = client.post(
        url,
        headers=headers,
        json={"source_ids": ["MM"], "entry_types": ["z", " A ", "z"]},
    )
    assert invalid_types.status_code == 400
    assert invalid_types.get_json()["error"] == {
        "code": "validation_error",
        "message": "Unsupported entry_types: a, z",
    }

    for body, content_type, message in (
        (None, None, "source_ids must be an array of source IDs."),
        ("[]", "application/json", "Request body must be a JSON object."),
        ("{", "application/json", "Request body must be a JSON object."),
        ("{}", "text/plain", "Request body must be a JSON object."),
    ):
        response = client.post(
            url,
            headers=headers,
            data=body,
            content_type=content_type,
        )
        assert response.status_code == 400
        assert response.get_json()["error"] == {
            "code": "validation_error",
            "message": message,
        }

    object.__setattr__(dependencies, "build_importer", original_build_importer)
    assert extracted_roots
    assert all(not path.exists() for path in extracted_roots)
    with app.app_context():
        assert AuthStore().list_recent_audit_events(limit=1000) == audits_before


@pytest.mark.parametrize(
    ("failure_point", "expected_message", "expected_status", "entries_are_durable"),
    (
        ("create", "create import run unavailable", None, False),
        ("replace", "replace entries unavailable", "failed", False),
        ("complete", "complete import run unavailable", "failed", True),
        ("fail", "fail import run unavailable", "started", False),
    ),
)
def test_api_systems_dnd5e_import_preserves_importer_failure_windows(
    client,
    app,
    users,
    tmp_path,
    monkeypatch,
    failure_point,
    expected_message,
    expected_status,
    entries_are_durable,
):
    url = "/api/v1/systems/imports/dnd5e"
    admin_token = issue_api_token(app, users["admin"]["email"], label=f"ingest-{failure_point}")
    archive_base64 = base64.b64encode(_build_systems_import_archive(tmp_path)).decode(
        "ascii"
    )
    with app.app_context():
        store = app.extensions["systems_store"]
        app.extensions["systems_service"].ensure_builtin_library_seeded("DND-5E")
        audits_before = AuthStore().list_recent_audit_events(limit=1000)

        if failure_point == "create":
            def fail_create(*args, **kwargs):
                raise RuntimeError(expected_message)

            monkeypatch.setattr(store, "create_import_run", fail_create)
        elif failure_point == "replace":
            def fail_replace(*args, **kwargs):
                raise RuntimeError(expected_message)

            monkeypatch.setattr(store, "replace_entries_for_source", fail_replace)
        elif failure_point == "complete":
            def fail_complete(*args, **kwargs):
                raise RuntimeError(expected_message)

            monkeypatch.setattr(store, "complete_import_run", fail_complete)
        else:
            def fail_replace(*args, **kwargs):
                raise RuntimeError("original replacement failure")

            def fail_status(*args, **kwargs):
                raise RuntimeError(expected_message)

            monkeypatch.setattr(store, "replace_entries_for_source", fail_replace)
            monkeypatch.setattr(store, "fail_import_run", fail_status)

        with pytest.raises(RuntimeError, match=expected_message):
            client.post(
                url,
                headers=api_headers(admin_token),
                json={
                    "source_ids": ["MM"],
                    "entry_types": ["monster"],
                    "archive": {
                        "filename": "mm.zip",
                        "data_base64": archive_base64,
                    },
                },
            )

        runs = store.list_import_runs(library_slug="DND-5E")
        if expected_status is None:
            assert runs == []
        else:
            assert len(runs) == 1
            assert runs[0].status == expected_status
        entries = store.list_entries(
            "DND-5E",
            source_ids=["MM"],
            entry_type="monster",
        )
        assert bool(entries) is entries_are_durable
        assert AuthStore().list_recent_audit_events(limit=1000) == audits_before


def test_api_systems_dnd5e_import_preserves_later_source_partial_failure(
    client,
    app,
    users,
    tmp_path,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="ingest-partial")
    archive_base64 = base64.b64encode(_build_systems_import_archive(tmp_path)).decode(
        "ascii"
    )
    with app.app_context():
        audits_before = AuthStore().list_recent_audit_events(limit=1000)

    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM", "NOT-A-SOURCE"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "mm.zip",
                "data_base64": archive_base64,
            },
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "Unsupported DND 5E source ID: NOT-A-SOURCE",
    }
    with app.app_context():
        store = app.extensions["systems_store"]
        runs = store.list_import_runs(library_slug="DND-5E")
        assert len(runs) == 1 and runs[0].status == "completed"
        assert store.list_entries(
            "DND-5E",
            source_ids=["MM"],
            entry_type="monster",
        )
        assert AuthStore().list_recent_audit_events(limit=1000) == audits_before


@pytest.mark.parametrize(
    "failure_field",
    (
        "get_import_run",
        "serialize_systems_import_result",
        "serialize_systems_import_run",
    ),
)
def test_api_systems_dnd5e_import_preserves_post_commit_response_failures(
    client,
    app,
    users,
    tmp_path,
    failure_field,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label=f"ingest-{failure_field}")
    archive_base64 = base64.b64encode(_build_systems_import_archive(tmp_path)).decode(
        "ascii"
    )
    dependencies = _systems_api_mutation_dependencies(
        app,
        "api.systems_import_dnd5e",
    )
    original = getattr(dependencies, failure_field)

    def fail_response(*args, **kwargs):
        raise RuntimeError(f"{failure_field} unavailable")

    object.__setattr__(dependencies, failure_field, fail_response)
    with app.app_context():
        audits_before = AuthStore().list_recent_audit_events(limit=1000)
        with pytest.raises(RuntimeError, match=f"{failure_field} unavailable"):
            client.post(
                "/api/v1/systems/imports/dnd5e",
                headers=api_headers(admin_token),
                json={
                    "source_ids": ["MM"],
                    "entry_types": ["monster"],
                    "archive": {
                        "filename": "mm.zip",
                        "data_base64": archive_base64,
                    },
                },
            )
        runs = app.extensions["systems_store"].list_import_runs(
            library_slug="DND-5E"
        )
        assert len(runs) == 1 and runs[0].status == "completed"
        assert AuthStore().list_recent_audit_events(limit=1000) == audits_before
    object.__setattr__(dependencies, failure_field, original)


def test_api_systems_import_run_reads_preserve_auth_methods_404s_and_no_audit(
    client,
    app,
    sign_in,
    users,
):
    with app.app_context():
        import_run = app.extensions["systems_store"].create_import_run(
            library_slug="DND-5E",
            source_id="MM",
            source_path="characterization:mm.zip",
            started_by_user_id=users["admin"]["id"],
        )

    admin_token = issue_api_token(app, users["admin"]["email"], label="import-run-admin")
    dm_token = issue_api_token(app, users["dm"]["email"], label="import-run-dm")
    player_token = issue_api_token(
        app,
        users["party"]["email"],
        label="import-run-player",
    )
    list_url = "/api/v1/systems/import-runs"
    detail_url = f"{list_url}/{import_run.id}"

    with app.app_context():
        audits_before = AuthStore().list_recent_audit_events(limit=1000)

    for url in (list_url, detail_url):
        options_response = client.open(url, method="OPTIONS")
        assert options_response.status_code == 200
        assert set(options_response.headers["Allow"].split(", ")) == {
            "GET",
            "HEAD",
            "OPTIONS",
        }

        anonymous_response = client.get(url)
        assert anonymous_response.status_code == 401
        assert anonymous_response.get_json()["error"]["code"] == "auth_required"

        anonymous_head = client.head(url)
        assert anonymous_head.status_code == 401
        assert anonymous_head.data == b""

        for token in (dm_token, player_token):
            denied = client.get(url, headers=api_headers(token))
            assert denied.status_code == 403
            assert denied.get_json()["error"]["code"] == "forbidden"

        authorized = client.get(url, headers=api_headers(admin_token))
        assert authorized.status_code == 200

        authorized_head = client.head(url, headers=api_headers(admin_token))
        assert authorized_head.status_code == 200
        assert authorized_head.data == b""

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    for url in (list_url, detail_url):
        response = client.get(url)
        assert response.status_code == 200

    noninteger = client.get(f"{list_url}/not-an-integer", headers=api_headers(admin_token))
    assert noninteger.status_code == 404
    assert not noninteger.is_json

    missing = client.get(f"{list_url}/{import_run.id + 1000}", headers=api_headers(admin_token))
    assert missing.status_code == 404
    assert not missing.is_json

    with app.app_context():
        assert AuthStore().list_recent_audit_events(limit=1000) == audits_before


def test_api_systems_import_run_list_preserves_query_and_serializer_contract(
    client,
    app,
    users,
    monkeypatch,
):
    with app.app_context():
        store = app.extensions["systems_store"]
        older = store.create_import_run(
            library_slug="dNd-5e",
            source_id="MM",
            import_version="older-version",
            source_path="raw/path/older.zip",
            summary={"full": {"nested": ["summary", "payload"]}},
            started_by_user_id=users["admin"]["id"],
        )
        store.complete_import_run(
            older.id,
            summary={"full": {"nested": ["summary", "payload"]}},
        )
        newer = store.create_import_run(
            library_slug="dNd-5e",
            source_id="MM",
            import_version="newer-version",
            source_path="raw/path/newer.zip",
            summary={"newer": True},
            started_by_user_id=users["admin"]["id"],
        )
        original_list_import_runs = store.list_import_runs

    calls: list[dict[str, object]] = []

    def capture_list_import_runs(**kwargs):
        calls.append(kwargs)
        return original_list_import_runs(**kwargs)

    monkeypatch.setattr(store, "list_import_runs", capture_list_import_runs)
    admin_token = issue_api_token(app, users["admin"]["email"], label="import-run-query")
    headers = api_headers(admin_token)
    list_url = "/api/v1/systems/import-runs"

    default_response = client.get(list_url, headers=headers)
    assert default_response.status_code == 200
    assert calls[-1] == {"library_slug": None, "source_id": None, "limit": 20}
    import_runs = default_response.get_json()["import_runs"]
    assert [entry["id"] for entry in import_runs[:2]] == [newer.id, older.id]
    serialized_older = next(entry for entry in import_runs if entry["id"] == older.id)
    assert serialized_older == {
        "id": older.id,
        "library_slug": "dNd-5e",
        "source_id": "MM",
        "status": "completed",
        "import_version": "older-version",
        "source_path": "raw/path/older.zip",
        "summary": {"full": {"nested": ["summary", "payload"]}},
        "started_at": serialized_older["started_at"],
        "completed_at": serialized_older["completed_at"],
        "started_by_user_id": users["admin"]["id"],
    }
    assert serialized_older["started_at"]
    assert serialized_older["completed_at"]

    expected_error = {
        "ok": False,
        "error": {
            "code": "validation_error",
            "message": "limit must be an integer.",
        },
    }
    for raw_limit in ("", "not-an-integer"):
        response = client.get(list_url, query_string={"limit": raw_limit}, headers=headers)
        assert response.status_code == 400
        assert response.get_json() == expected_error

    for raw_limit in (0, -4):
        response = client.get(list_url, query_string={"limit": raw_limit}, headers=headers)
        assert response.status_code == 200
        assert calls[-1]["limit"] == raw_limit
        assert len(response.get_json()["import_runs"]) == 1

    response = client.get(
        list_url,
        query_string={
            "limit": 999999,
            "library_slug": " dNd-5e ",
            "source_id": " mm ",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert calls[-1] == {
        "library_slug": "dNd-5e",
        "source_id": "MM",
        "limit": 999999,
    }
    assert [entry["id"] for entry in response.get_json()["import_runs"]] == [
        newer.id,
        older.id,
    ]


def test_api_systems_import_endpoint_rejects_unsafe_archives(client, app, users, tmp_path):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-unsafe-api")
    archive_bytes = _build_unsafe_systems_import_archive(tmp_path)

    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "unsafe-systems-import.zip",
                "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
            },
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]["code"] == "validation_error"
    assert "parent-relative paths" in payload["error"]["message"]
    assert "unsafe-systems-import.zip" not in payload["error"]["message"]
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


def test_api_systems_import_prebounds_base64_before_decoder_and_database_mutation(
    client,
    app,
    users,
    monkeypatch,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-bound-api")
    app.config["SYSTEMS_ARCHIVE_LIMITS"] = SystemsArchiveLimits(
        max_raw_bytes=3
    )
    decoder_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal decoder_called
        decoder_called = True
        raise AssertionError("oversized base64 must be rejected before decoding")

    monkeypatch.setattr("player_wiki.input_limits.base64.b64decode", fail_if_called)
    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "oversized.zip",
                "data_base64": "AAAAAA==",
            },
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    assert decoder_called is False
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


@pytest.mark.parametrize("data_base64", ["Y Q==", "YQ=", "YQ===", "not-base64!"])
def test_api_systems_import_rejects_non_strict_base64_without_mutation(
    client,
    app,
    users,
    data_base64,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-base64-api")
    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {"filename": "invalid.zip", "data_base64": data_base64},
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


def test_api_systems_import_rejects_noncanonical_base64_without_mutation(
    client,
    app,
    users,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-canonical-api")
    for data_base64 in ("Zh==", "Zm9="):
        response = client.post(
            "/api/v1/systems/imports/dnd5e",
            headers=api_headers(admin_token),
            json={
                "source_ids": ["MM"],
                "entry_types": ["monster"],
                "archive": {"filename": "noncanonical.zip", "data_base64": data_base64},
            },
        )

        assert response.status_code == 400
        payload = response.get_json()
        assert payload["error"]["code"] == "validation_error"
        assert payload["error"]["message"] == (
            "archive data_base64 must be valid base64 and stay at or under 64 MiB."
        )
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


def test_api_systems_import_rejects_malformed_utf8_without_leak_mutation_or_residue(
    client,
    app,
    users,
    tmp_path,
    monkeypatch,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-malformed-api")
    temp_root = tmp_path / "systems-temp"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))
    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "ATTACKER-SENTINEL.zip",
                "data_base64": base64.b64encode(
                    _build_malformed_utf8_systems_import_archive()
                ).decode("ascii"),
            },
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == {
        "code": "validation_error",
        "message": "Import archive must be a valid supported ZIP file.",
    }
    response_text = response.get_data(as_text=True)
    assert "ATTACKER-SENTINEL" not in response_text
    assert "codec" not in response_text
    assert "position" not in response_text
    with app.app_context():
        store = app.extensions["systems_store"]
        assert store.list_import_runs(library_slug="DND-5E") == []
        assert store.list_entries_for_source("DND-5E", "MM", entry_type="monster", limit=None) == []
    assert not temp_root.exists() or list(temp_root.iterdir()) == []


def test_api_systems_import_accepts_archive_at_exact_raw_limit(client, app, users):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-exact-api")
    archive_bytes = _build_systems_import_archive(wrapper="source-export")
    app.config["SYSTEMS_ARCHIVE_LIMITS"] = SystemsArchiveLimits(
        max_raw_bytes=len(archive_bytes)
    )
    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "exact.zip",
                "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
