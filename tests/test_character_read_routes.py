from __future__ import annotations

from tests.helpers.character_state_helpers import (
    _character_state_revision,
    _read_character_definition,
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
)
from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
)
from tests.helpers.systems_seed_helpers import (
    _seed_systems_item_entry,
    _seed_systems_spell_entries,
    _systems_ref,
)
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import re
import yaml
from datetime import datetime, timezone

import player_wiki.app as app_module
import player_wiki.character_builder as character_builder_module
import pytest
from player_wiki.auth_store import AuthStore
from player_wiki.character_builder import normalize_definition_to_native_model
from player_wiki.character_models import CharacterDefinition
from player_wiki.system_policy import (
    DND_5E_SYSTEM_CODE,
    XIANXIA_SYSTEM_CODE,
    XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
    XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE,
)
from player_wiki.systems_models import SystemsEntryRecord
from player_wiki.systems_service import XIANXIA_HOMEBREW_SOURCE_ID


TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\x8f\x9b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
TEST_JPG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00"
    + (b"\x08" * 64)
    + b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\x00\xff\xd9"
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _character_read_shell_script_text() -> str:
    return (PROJECT_ROOT / "player_wiki" / "static" / "character-read-shell.js").read_text(encoding="utf-8")


def _assert_event_contains(event: dict, expected: dict) -> None:
    assert {key: event.get(key) for key in expected} == expected


def _read_shell_target_subpages(html: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(r'data-character-read-target-subpage="([^"]+)"', html)
    ]


def _seed_systems_entry(
    app,
    *,
    source_id: str,
    entry_type: str,
    slug: str,
    title: str,
    rendered_html: str = "",
    metadata: dict[str, object] | None = None,
) -> SystemsEntryRecord:
    normalized_source_id = source_id.strip().upper()
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        source_titles = {
            "DMG": "Dungeon Master's Guide",
            "PHB": "Player's Handbook",
            "TCE": "Tasha's Cauldron of Everything",
            "XGE": "Xanathar's Guide to Everything",
        }
        systems_store.upsert_source(
            "DND-5E",
            normalized_source_id,
            title=source_titles.get(normalized_source_id, normalized_source_id),
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        existing_entries = [
            {
                "entry_key": record.entry_key,
                "entry_type": record.entry_type,
                "slug": record.slug,
                "title": record.title,
                "source_page": record.source_page,
                "source_path": record.source_path,
                "search_text": record.search_text,
                "player_safe_default": record.player_safe_default,
                "dm_heavy": record.dm_heavy,
                "metadata": dict(record.metadata or {}),
                "body": dict(record.body or {}),
                "rendered_html": record.rendered_html,
            }
            for record in systems_store.list_entries_for_source(
                "DND-5E",
                normalized_source_id,
                entry_type=entry_type,
            )
            if str(record.slug or "").strip() != slug
        ]
        systems_store.replace_entries_for_source(
            "DND-5E",
            normalized_source_id,
            entry_types=[entry_type],
            entries=existing_entries
            + [
                {
                    "entry_key": f"dnd-5e|{entry_type}|{normalized_source_id.lower()}|{slug}",
                    "entry_type": entry_type,
                    "slug": slug,
                    "title": title,
                    "source_page": "1",
                    "source_path": f"test/{entry_type}.json",
                    "search_text": f"{title} {entry_type}",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": dict(metadata or {}),
                    "body": {},
                    "rendered_html": rendered_html or f"<p>{title}.</p>",
                }
            ],
        )
        entry = app.extensions["systems_service"].get_entry_by_slug_for_campaign("linden-pass", slug)
        assert entry is not None
        return entry


def _spell_payload(
    entry: SystemsEntryRecord,
    *,
    source: str,
    mark: str = "",
    is_always_prepared: bool = False,
    is_bonus_known: bool = False,
    **extra: object,
) -> dict[str, object]:
    metadata = dict(entry.metadata or {})
    payload = {
        "name": str(entry.title or "").strip(),
        "casting_time": "1 action",
        "range": "60 feet" if int(metadata.get("level") or 0) > 0 else "Self",
        "duration": "Instantaneous" if int(metadata.get("level") or 0) > 0 else "1 round",
        "components": "V",
        "save_or_hit": "",
        "source": source,
        "reference": f"p. {entry.source_page or '200'}",
        "mark": mark,
        "is_always_prepared": is_always_prepared,
        "is_bonus_known": is_bonus_known,
        "systems_ref": _systems_ref(entry),
    }
    payload.update(dict(extra or {}))
    return payload


def test_dm_can_open_character_roster_and_read_sheet(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    sheet = client.get("/campaigns/linden-pass/characters/selene-brook")

    assert roster.status_code == 200
    roster_html = roster.get_data(as_text=True)
    assert "Selene Brook" in roster_html
    assert "Arden March" in roster_html
    assert "Tobin Slate" in roster_html
    assert "Back to wiki" not in roster_html

    assert sheet.status_code == 200
    sheet_html = sheet.get_data(as_text=True)
    assert "At a glance" in sheet_html
    assert "Active session" not in sheet_html
    assert "Advanced Editor" in sheet_html
    assert "Open sheet edit view" not in sheet_html
    assert "Enter session mode" not in sheet_html
    assert "Alignment:" in sheet_html
    assert "Chaotic Good" in sheet_html
    assert "Campaign:" not in sheet_html
    assert 'class="site-header__campaign"' in sheet_html
    assert "Context" not in sheet_html
    assert "Back to character roster" not in sheet_html
    assert "Open campaign wiki" not in sheet_html


def test_read_sheet_shows_carrying_capacity_stats(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["size"] = "Large"
        payload["profile"] = profile

        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["str"] = {"score": 16, "modifier": 3, "save_bonus": 3}
        stats["ability_scores"] = ability_scores
        payload["stats"] = stats

        features = list(payload.get("features") or [])
        features.append(
            {
                "id": "powerful-build-1",
                "name": "Powerful Build",
                "category": "species_trait",
                "activation_type": "passive",
            }
        )
        payload["features"] = features

        normalized = normalize_definition_to_native_model(CharacterDefinition.from_dict(payload))
        payload.clear()
        payload.update(normalized.to_dict())

    _write_character_definition(app, "selene-brook", _mutate)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    sheet = client.get("/campaigns/linden-pass/characters/selene-brook")

    assert sheet.status_code == 200
    sheet_html = sheet.get_data(as_text=True)
    assert "Carrying Capacity" in sheet_html
    assert "960 lb." in sheet_html
    assert "Push / Drag / Lift" in sheet_html
    assert "1920 lb." in sheet_html


def test_read_sheet_shows_tool_expertise_under_tools(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        proficiencies = dict(payload.get("proficiencies") or {})
        proficiencies["tools"] = ["Navigator's Tools", "Thieves' Tools"]
        proficiencies["tool_expertise"] = ["Thieves' Tools"]
        payload["proficiencies"] = proficiencies

    _write_character_definition(app, "selene-brook", _mutate)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    sheet = client.get("/campaigns/linden-pass/characters/selene-brook")

    assert sheet.status_code == 200
    sheet_html = sheet.get_data(as_text=True)
    assert "Tools" in sheet_html
    assert "Navigator&#39;s Tools, Thieves&#39; Tools (Expertise)" in sheet_html


def test_roster_and_read_sheet_derive_multiclass_summary_from_class_rows(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Fighter 3"
        profile["classes"] = [
            {
                "class_name": "Fighter",
                "subclass_name": "",
                "level": 3,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|fighter",
                    "entry_type": "class",
                    "title": "Fighter",
                    "slug": "phb-class-fighter",
                    "source_id": "PHB",
                },
            },
            {
                "class_name": "Wizard",
                "subclass_name": "",
                "level": 2,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|wizard",
                    "entry_type": "class",
                    "title": "Wizard",
                    "slug": "phb-class-wizard",
                    "source_id": "PHB",
                },
            },
        ]
        payload["profile"] = profile

    _write_character_definition(app, "tobin-slate", _mutate)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    sheet = client.get("/campaigns/linden-pass/characters/tobin-slate?mode=read")

    assert roster.status_code == 200
    assert "Fighter 3 / Wizard 2" in roster.get_data(as_text=True)
    assert sheet.status_code == 200
    assert "Fighter 3 / Wizard 2" in sheet.get_data(as_text=True)


def test_non_5e_roster_hides_native_character_builder_affordances(app, client, sign_in, users):
    _write_campaign_config(app, lambda payload: payload.__setitem__("system", "Pathfinder 2E"))

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Create character" not in html
    assert "/campaigns/linden-pass/characters/new" not in html
    assert "PHB level 1 character" not in html
    assert "Open a player sheet for read mode, use inline state controls when authorized, and use Advanced Editor for larger sheet changes." in html
    assert "Native character creation and progression stay hidden here" in html


def test_non_5e_read_sheet_hides_native_authoring_affordances_and_skips_readiness(
    app, client, sign_in, users, monkeypatch
):
    _write_campaign_config(app, lambda payload: payload.__setitem__("system", "Pathfinder 2E"))

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("native level-up readiness should stay disabled for non-5E character sheets")

    monkeypatch.setattr(app_module, "native_level_up_readiness", _fail_if_called)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Open sheet edit view" not in html
    assert "Sheet edit view" not in html
    assert "Advanced Editor" not in html
    assert "Active session" not in html
    assert "Enter session mode" not in html
    assert "Edit character" not in html
    assert "Level up" not in html
    assert "Prepare for level-up" not in html


def test_non_5e_session_mode_still_works_for_owner_player(
    app, client, sign_in, users, set_campaign_visibility
):
    _write_campaign_config(app, lambda payload: payload.__setitem__("system", "Pathfinder 2E"))
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" not in html
    assert "Sheet edit view" not in html
    assert "Open sheet edit view" not in html
    assert "Save pending changes" not in html
    assert "Back to character sheet" not in html
    assert "Back to read mode" not in html
    assert "?mode=session&amp;page=quick" in html
    assert "Edit character" not in html


def test_native_normalizer_respects_supplied_empty_catalogs(app):
    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None

        item_catalog = character_builder_module._effective_item_catalog_for_definition(
            record.definition,
            item_catalog={},
            systems_service=app.extensions["systems_service"],
        )
        spell_catalog = character_builder_module._effective_spell_catalog_for_definition(
            record.definition,
            spell_catalog={},
            systems_service=app.extensions["systems_service"],
        )

    assert item_catalog == {}
    assert spell_catalog == {}


def test_non_5e_builder_route_redirects_to_roster_with_error(app, client, sign_in, users):
    _write_campaign_config(app, lambda payload: payload.__setitem__("system", "Pathfinder 2E"))

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/new", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters")

    landing = client.get(response.headers["Location"])
    html = landing.get_data(as_text=True)
    assert app_module.NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE in html
    assert "Create character" not in html


@pytest.mark.parametrize("route_suffix", ["edit", "level-up", "progression-repair", "retraining"])
def test_non_5e_native_character_routes_redirect_to_sheet_with_error(
    app, client, sign_in, users, route_suffix: str
):
    _write_campaign_config(app, lambda payload: payload.__setitem__("system", "Pathfinder 2E"))

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get(
        f"/campaigns/linden-pass/characters/arden-march/{route_suffix}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    landing = client.get(response.headers["Location"])
    html = landing.get_data(as_text=True)
    assert app_module.NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE in html
    assert "Arden March" in html


def test_character_read_sheet_links_species_and_background_to_campaign_pages_when_present(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["species"] = "Sea-Blessed"
        profile["species_ref"] = None
        profile["species_page_ref"] = "species/sea-blessed"
        profile["background"] = "Harbor Initiate"
        profile["background_ref"] = None
        profile["background_page_ref"] = "backgrounds/harbor-initiate"
        payload["profile"] = profile

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/campaigns/linden-pass/pages/species/sea-blessed" in html
    assert "/campaigns/linden-pass/pages/backgrounds/harbor-initiate" in html
    assert "Sea-Blessed" in html
    assert "Harbor Initiate" in html


def test_player_cannot_open_character_roster_or_sheet_when_characters_are_dm_only(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    sheet = client.get("/campaigns/linden-pass/characters/arden-march")

    assert roster.status_code == 404
    assert sheet.status_code == 404


def test_owner_player_can_open_session_mode_when_character_visibility_allows_players(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Advanced Editor" in html
    assert "Active session" not in html
    assert "Save pending changes" not in html
    assert "Save vitals" not in html
    assert 'data-character-sheet-edit-form="vitals"' in html
    assert 'class="glance-card glance-card--vitals"' in html
    assert 'name="mode" value="read"' in html
    assert "Back to character sheet" not in html
    assert "Back to read mode" not in html
    assert "?mode=session&amp;page=quick" in html
    assert "?mode=session&amp;page=personal" in html
    assert "Open sheet edit view" not in html


def test_unassigned_player_falls_back_to_read_mode_when_character_visibility_allows_players(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" not in html
    assert "Save vitals" not in html
    assert "Enter session mode" not in html


def test_observer_cannot_read_character_when_characters_are_dm_only(client, sign_in, users):
    sign_in(users["observer"]["email"], users["observer"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session")

    assert response.status_code == 404


def test_character_sheet_subpages_show_requested_sections(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        reference_notes = dict(payload.get("reference_notes") or {})
        reference_notes["additional_notes_markdown"] = "Keep an eye on the harbor."
        payload["reference_notes"] = reference_notes

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Quick Reference" in html
    assert "Spellcasting" in html
    assert "Features" in html
    assert "Equipment" in html
    assert "Inventory" in html
    assert "Personal" in html
    assert "Notes" in html
    assert "?page=quick" in html
    assert "?page=spellcasting" in html
    assert "?page=features" in html
    assert "?page=equipment" in html
    assert "?page=inventory" in html
    assert "?page=personal" in html
    assert "?page=notes" in html
    assert "Features and traits" in html
    assert '<section class="feature-group">' in html
    assert '<article class="feature-row">' in html
    assert "feature-row__header" in html
    assert "At a glance" not in html
    assert "Inventory and currency" not in html
    assert "Keep an eye on the harbor." not in html
    assert "mode=session&amp;page=features" not in html


def test_character_read_sheet_exposes_character_shell_data_hooks(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'data-character-read-shell-root' in html
    assert 'data-character-read-shell-panel' in html
    assert 'data-character-read-shell-page="quick"' in html
    assert 'data-character-read-shell-mode="read"' in html
    assert 'data-character-read-shell-loading' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'data-character-read-shell-loading-message' in html
    assert 'data-character-read-subpage-link' in html
    assert 'data-character-read-target-subpage="quick"' in html
    assert 'data-character-read-target-subpage="features"' in html
    assert '/static/character-read-shell.js?v=' in html


def test_character_read_subpage_nav_links_keep_fallback_hrefs(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read")
    read_html = read_response.get_data(as_text=True)
    assert read_response.status_code == 200
    assert 'href="/campaigns/linden-pass/characters/arden-march?page=quick"' in read_html
    assert 'href="/campaigns/linden-pass/characters/arden-march?page=inventory"' in read_html
    assert 'href="/campaigns/linden-pass/characters/arden-march?page=features"' in read_html
    assert 'href="/campaigns/linden-pass/characters/arden-march?page=spellcasting"' in read_html
    assert 'href="/campaigns/linden-pass/characters/arden-march?mode=session&amp;page=quick"' not in read_html

    session_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=features")
    session_html = session_response.get_data(as_text=True)
    assert session_response.status_code == 200
    assert 'href="/campaigns/linden-pass/characters/arden-march?mode=session&amp;page=quick"' in session_html
    assert 'href="/campaigns/linden-pass/characters/arden-march?mode=session&amp;page=features"' in session_html
    assert 'href="/campaigns/linden-pass/characters/arden-march?mode=session&amp;page=inventory"' in session_html


def test_character_read_shell_scripts_are_embedded_for_progressive_enhancement(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert '/static/character-read-shell.js?v=' in html
    assert "data-character-read-subpage-link" in html
    character_script = _character_read_shell_script_text()
    assert "window.__playerWikiCharacterReadShell" in character_script
    assert "history.pushState" in character_script
    assert "new FormData(form, submitter)" in character_script
    assert "addEventListener(\"popstate\"" in character_script
    assert "loadPanelFromResponseText" in character_script
    assert "replaceFlashStack" in character_script
    assert "event.button !== 0" in character_script
    assert "event.preventDefault();" in character_script
    assert "\"X-Requested-With\": \"XMLHttpRequest\"" in character_script
    assert "\"Accept\": \"text/html\"" in character_script
    assert 'shellRoot.setAttribute("aria-busy", "true")' in character_script
    assert 'shellRoot.removeAttribute("aria-busy")' in character_script
    assert "cancelActiveSubpageRequest();" in character_script
    assert 'link.removeAttribute("data-character-read-pending")' in character_script
    assert "if (response.status === 503)" in character_script
    assert "if (initialPanelState.mode !== \"read\")" in character_script


def _install_character_render_builder_spy(app, monkeypatch, builder_name, calls):
    render_character_page = app.extensions[
        "character_read_route_dependencies"
    ].render_character_page
    closure_index = render_character_page.__code__.co_freevars.index(builder_name)
    closure_cell = render_character_page.__closure__[closure_index]
    original_builder = closure_cell.cell_contents

    def spy(*args, **kwargs):
        calls.append(builder_name)
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(closure_cell, "cell_contents", spy)


@pytest.mark.parametrize(
    ("page", "expected_builders"),
    (
        ("quick", []),
        ("spellcasting", ["build_character_spell_manager_context"]),
        (
            "equipment",
            ["build_character_item_catalog", "build_character_equipment_state_context"],
        ),
        (
            "inventory",
            ["build_character_item_catalog", "build_character_inventory_manager_context"],
        ),
        ("controls", ["build_character_controls_context"]),
    ),
)
def test_character_read_selected_dnd_section_builds_exact_manager_matrix_and_one_page_scan(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    page,
    expected_builders,
):
    page_store = app.extensions["campaign_page_store"]
    original_list_page_records = page_store.list_page_records
    page_scan_calls = []

    def list_page_records(*args, **kwargs):
        page_scan_calls.append((args, kwargs))
        return original_list_page_records(*args, **kwargs)

    monkeypatch.setattr(page_store, "list_page_records", list_page_records)
    calls = []
    for builder_name in (
        "build_character_item_catalog",
        "build_character_spell_manager_context",
        "build_character_inventory_manager_context",
        "build_character_equipment_state_context",
        "build_character_controls_context",
    ):
        _install_character_render_builder_spy(app, monkeypatch, builder_name, calls)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get(
        f"/campaigns/linden-pass/characters/arden-march?mode=read&page={page}",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    assert calls == expected_builders
    assert len(page_scan_calls) == 1
    assert page_scan_calls[0][1].get("include_body") is True


@pytest.mark.parametrize("page", ("quick", "equipment", "inventory"))
def test_character_read_xianxia_sections_skip_dnd_manager_builders(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    page,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    created = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Section Matrix Crane"),
        follow_redirects=False,
    )
    assert created.status_code == 302

    calls = []
    for builder_name in (
        "build_character_item_catalog",
        "build_character_spell_manager_context",
        "build_character_inventory_manager_context",
        "build_character_equipment_state_context",
    ):
        _install_character_render_builder_spy(app, monkeypatch, builder_name, calls)

    response = client.get(
        f"/campaigns/linden-pass/characters/section-matrix-crane?page={page}"
    )

    assert response.status_code == 200
    assert calls == []


def test_dnd_read_view_exposes_expected_character_read_shell_subpages_when_manageable(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "data-character-read-shell-root" in html
    target_subpages = _read_shell_target_subpages(html)
    assert target_subpages == [
        "quick",
        "spellcasting",
        "features",
        "equipment",
        "inventory",
        "personal",
        "portrait",
        "notes",
        "controls",
    ]
    assert 'data-character-read-target-subpage="quick"' in html
    assert 'data-character-read-target-subpage="spellcasting"' in html
    assert "Quick Reference" in html
    assert "Spellcasting" in html
    assert "Features" in html
    assert "Equipment" in html
    assert "Inventory" in html
    assert "Personal" in html
    assert "Portrait" in html
    assert "Notes" in html
    assert "Controls" in html
    assert 'href="/campaigns/linden-pass/characters/arden-march?page=quick"' in html
    assert 'href="/campaigns/linden-pass/characters/arden-march?page=spellcasting"' in html


def test_sheet_edit_view_session_combat_links_remain_outside_shell_navigation(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=inventory")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Open Character Help" not in html
    assert 'href="/campaigns/linden-pass/help#characters"' not in html
    assert '/campaigns/linden-pass/session/character?character=arden-march&amp;page=inventory' not in html
    assert '>Open Session Character<' not in html
    assert '/campaigns/linden-pass/combat?combatant=' not in html
    assert '>Open Combat<' not in html
    assert "?mode=session&amp;page=inventory" in html
    assert "Character-page sheet edit" not in html
    assert "Combat-context editing" not in html
    nav_start = html.find('<nav class="character-subpage-nav"')
    nav_end = html.find("</nav>", nav_start)
    nav_segment = html[nav_start:nav_end] if nav_start != -1 and nav_end != -1 else ""
    assert "/campaigns/linden-pass/session/character?character=arden-march&amp;page=inventory" not in nav_segment
    assert "/campaigns/linden-pass/combat?combatant=" not in nav_segment


def test_dm_controls_subpage_shows_management_controls(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Controls" in html
    assert "?page=controls" in html
    assert "Player controls" in html
    assert "Character management controls for campaign staff." in html
    assert "Current owner" in html
    assert "Owner Player" in html
    assert "Delete character" in html
    assert "Assignment controls" not in html
    assert "At a glance" not in html


def test_owner_player_controls_subpage_holds_future_player_controls_without_admin_tools(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Controls" in html
    assert "Player controls" in html
    assert "?page=controls" in html
    assert "Player-controls workspace for Arden March." in html
    assert "Delete character" not in html
    assert "Assignment controls" not in html
    assert "Owner Player" in html
    assert "At a glance" not in html


def test_read_only_player_controls_request_falls_back_to_quick_reference(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "At a glance" in html
    assert "Delete character" not in html
    assert "Assignment controls" not in html
    assert "?page=controls" not in html
    assert 'data-character-read-shell-page="quick"' in html
    assert 'data-character-read-shell-mode="read"' in html
    assert 'data-character-read-target-subpage="controls"' not in html


def test_character_sheet_invalid_subpage_defaults_to_quick_reference(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=not-a-real-page")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "At a glance" in html
    assert "Abilities and skills" in html
    assert "Features and traits" not in html
    assert "Inventory and currency" not in html
    assert "No notes yet." not in html
    assert 'data-character-read-shell-page="quick"' in html
    assert 'data-character-read-shell-mode="read"' in html


def test_admin_can_reassign_and_clear_owner_from_character_controls(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    assign_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/controls/assignment",
        data={"user_id": users["party"]["id"]},
        follow_redirects=False,
    )

    assert assign_response.status_code == 302
    assert assign_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march?page=controls")

    with app.app_context():
        store = AuthStore()
        assignment = store.get_character_assignment("linden-pass", "arden-march")
        assert assignment is not None
        assert assignment.user_id == users["party"]["id"]

    assigned_page = client.get(assign_response.headers["Location"])
    assigned_html = assigned_page.get_data(as_text=True)
    assert "Party Player" in assigned_html
    assert "Save assignment" in assigned_html

    clear_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/controls/assignment/remove",
        data={},
        follow_redirects=False,
    )

    assert clear_response.status_code == 302
    assert clear_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march?page=controls")

    with app.app_context():
        store = AuthStore()
        assert store.get_character_assignment("linden-pass", "arden-march") is None


def test_dm_can_delete_character_from_controls(app, client, sign_in, users):
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    portrait_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "assets"
        / "characters"
        / "arden-march"
        / "portrait.png"
    )
    assert definition_path.exists()
    portrait_path.parent.mkdir(parents=True, exist_ok=True)
    portrait_path.write_bytes(TEST_PNG_BYTES)
    _write_character_definition(
        app,
        "arden-march",
        lambda payload: payload.setdefault("profile", {}).update(
            {
                "portrait_asset_ref": "characters/arden-march/portrait.png",
                "portrait_alt": "Arden portrait",
                "portrait_caption": "Shown on the personal page.",
            }
        ),
    )

    sign_in(users["dm"]["email"], users["dm"]["password"])

    invalid_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/controls/delete",
        data={"confirm_character_slug": "not-arden-march"},
        follow_redirects=False,
    )

    assert invalid_response.status_code == 302
    assert invalid_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march?page=controls")
    assert definition_path.exists()

    delete_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/controls/delete",
        data={"confirm_character_slug": "arden-march"},
        follow_redirects=False,
    )

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"].endswith("/campaigns/linden-pass/characters")

    with app.app_context():
        store = AuthStore()
        state_store = app.extensions["character_state_store"]
        assert store.get_character_assignment("linden-pass", "arden-march") is None
        assert state_store.get_state("linden-pass", "arden-march") is None

    assert not definition_path.exists()
    assert not portrait_path.exists()
    assert not portrait_path.parent.exists()


def test_character_sheet_personal_and_notes_subpages_render_markdown_fields_and_hide_legacy_action_sections(
    app, client, sign_in, users
):
    def _mutate_definition(payload: dict) -> None:
        reference_notes = dict(payload.get("reference_notes") or {})
        reference_notes["additional_notes_markdown"] = "Keep an eye on the harbor."
        reference_notes["custom_sections"] = [
            {"title": "Actions: Bonus Actions", "body_markdown": "Second Wind"}
        ]
        payload["reference_notes"] = reference_notes

    def _mutate_state(payload: dict) -> None:
        notes = dict(payload.get("notes") or {})
        notes["player_notes_markdown"] = "Remember the **dock code**."
        notes["physical_description_markdown"] = "Tall, scarred, and always in dark leathers."
        notes["background_markdown"] = "Raised along the harbor and quick to vanish into crowds."
        payload["notes"] = notes

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    personal_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=personal")
    notes_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=notes")

    assert personal_response.status_code == 200
    personal_html = personal_response.get_data(as_text=True)
    assert "Personal" in personal_html
    assert "Physical Description" in personal_html
    assert "Tall, scarred, and always in dark leathers." in personal_html
    assert "Background" in personal_html
    assert "Raised along the harbor and quick to vanish into crowds." in personal_html
    assert "Save personal details" not in personal_html
    assert 'name="physical_description_markdown"' not in personal_html
    assert 'name="background_markdown"' not in personal_html
    assert "No personal details yet." not in personal_html

    assert notes_response.status_code == 200
    notes_html = notes_response.get_data(as_text=True)
    assert "Notes" in notes_html
    assert "Remember the" in notes_html
    assert "dock code" in notes_html
    assert "Keep an eye on the harbor." in notes_html
    assert "Save note" in notes_html
    assert 'name="player_notes_markdown"' in notes_html
    assert "Actions: Bonus Actions" not in notes_html
    assert "Second Wind" not in notes_html
    assert "No notes yet." not in notes_html


def test_read_mode_note_save_stays_in_read_mode(client, sign_in, users, get_character, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/notes",
        data={
            "expected_revision": record.state_record.revision,
            "mode": "read",
            "page": "notes",
            "player_notes_markdown": "Read mode note save.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march?page=notes#session-notes")
    assert "mode=session" not in response.headers["Location"]


def test_read_mode_note_save_stale_revision_refreshes_read_shell_view(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    get_character,
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None
    stale_revision = record.state_record.revision

    _write_character_state(
        app,
        "arden-march",
        lambda state: (
            state.__setitem__("notes", {
                **dict(state.get("notes") or {}),
                "player_notes_markdown": "Concurrent read-mode edit from elsewhere.",
            })
        ),
    )

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/notes",
        data={
            "expected_revision": stale_revision,
            "mode": "read",
            "page": "notes",
            "player_notes_markdown": "Read mode note save.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 409
    html = response.get_data(as_text=True)
    assert "This sheet changed in another session." in html
    assert 'data-character-read-shell-mode="read"' in html
    assert 'data-character-read-shell-page="notes"' in html
    assert "Read mode note save." in html


def test_session_mode_uses_same_subpage_ui_as_read_mode(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=personal")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" not in html
    assert "?mode=session&amp;page=quick" in html
    assert "?mode=session&amp;page=spellcasting" in html
    assert "?mode=session&amp;page=equipment" in html
    assert "?mode=session&amp;page=inventory" in html
    assert "?mode=session&amp;page=personal" in html
    assert "?mode=session&amp;page=notes" in html
    assert "Save pending changes" not in html
    assert "Save note" not in html
    assert "At a glance" not in html
    assert "Advanced Editor" in html


def test_editable_users_default_to_read_mode(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" not in html
    assert "Open sheet edit view" not in html
    assert "Advanced Editor" in html
    assert "Enter session mode" not in html
    assert "Back to character sheet" not in html


def test_character_compatibility_url_shows_inline_state_without_active_session_chrome(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")
    features_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=features")

    assert quick_response.status_code == 200
    quick_html = quick_response.get_data(as_text=True)
    assert "Active session" not in quick_html
    assert "Short rest" not in quick_html
    assert "Long rest" not in quick_html
    assert "Save pending changes" not in quick_html
    assert "Save note" not in quick_html
    assert "Save vitals" not in quick_html
    assert 'data-character-sheet-edit-form="vitals"' in quick_html
    assert 'data-character-sheet-edit-form="resource"' in quick_html
    assert 'name="mode" value="read"' in quick_html
    assert 'class="glance-card glance-card--vitals"' in quick_html
    assert 'id="session-vitals"' in quick_html

    assert features_response.status_code == 200
    features_html = features_response.get_data(as_text=True)
    assert "Active session" not in features_html
    assert "Save pending changes" not in features_html
    assert 'data-character-sheet-edit-form="vitals"' not in features_html


def test_dnd_character_normal_page_shows_inline_state_controls_for_assigned_player(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?page=quick")
    spell_response = client.get("/campaigns/linden-pass/characters/arden-march?page=spellcasting")
    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    personal_response = client.get("/campaigns/linden-pass/characters/arden-march?page=personal")
    portrait_response = client.get("/campaigns/linden-pass/characters/arden-march?page=portrait")
    notes_response = client.get("/campaigns/linden-pass/characters/arden-march?page=notes")
    controls_response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert quick_response.status_code == 200
    quick_html = quick_response.get_data(as_text=True)
    assert 'data-character-sheet-edit-form="vitals"' in quick_html
    assert 'data-character-sheet-edit-form="resource"' in quick_html
    assert "Save vitals" not in quick_html
    assert "Current state" not in quick_html
    assert 'data-character-subpage-nav-card' in quick_html
    assert 'class="glance-card glance-card--vitals"' in quick_html
    assert 'class="session-vitals-form session-vitals-form--inline session-vitals-form--inline-current"' in quick_html
    assert 'class="session-vitals-form session-vitals-form--inline session-vitals-form--inline-temp"' in quick_html
    assert 'name="current_hp"' in quick_html
    assert 'name="temp_hp"' in quick_html
    assert 'id="session-vitals"' in quick_html
    assert 'resource-grid resource-grid--editable' in quick_html
    assert 'resource-grid resource-grid--editable resource-grid--compact' in quick_html
    assert "glance-grid--quick-row-1" in quick_html
    assert "glance-grid--quick-row-2" in quick_html
    assert "glance-grid--quick-row-3" in quick_html
    assert "glance-grid--quick-row-4" in quick_html
    assert 'ability-grid ability-grid--skills' in quick_html
    assert "ability-skill-list" in quick_html
    assert "skill-grid" not in quick_html
    assert "Active session" not in quick_html
    assert "Short rest" not in quick_html
    assert "Long rest" not in quick_html
    assert "Save pending changes" not in quick_html
    assert 'name="mode" value="read"' in quick_html

    assert spell_response.status_code == 200
    spell_html = spell_response.get_data(as_text=True)
    assert 'data-character-sheet-edit-form="spell-slot"' in spell_html
    assert 'class="spell-slot-editor-list spell-slot-editor-list--compact"' in spell_html
    assert "<h3>Spell slots</h3>" not in spell_html
    assert '<h3 class="visually-hidden spell-slot-pool-title">Spell slots</h3>' in spell_html
    assert "Restore 1" not in spell_html
    assert "Use 1" not in spell_html
    assert 'data-character-autosubmit' in spell_html
    assert "Save pending changes" not in spell_html
    assert 'name="mode" value="read"' in spell_html

    assert inventory_response.status_code == 200
    inventory_html = inventory_response.get_data(as_text=True)
    assert 'data-character-sheet-edit-form="inventory"' in inventory_html
    assert 'data-character-sheet-edit-form="currency"' in inventory_html
    assert 'name="cp"' in inventory_html
    assert 'class="currency-grid"' in inventory_html
    assert inventory_html.count('class="currency-grid"') == 1
    assert 'name="delta" value="cp:-1"' not in inventory_html
    assert 'name="delta" value="gp:1"' not in inventory_html
    assert 'data-character-autosubmit' in inventory_html
    assert "Save currency" not in inventory_html
    assert "Inventory and currency" in inventory_html
    assert "Save pending changes" not in inventory_html
    assert 'name="mode" value="read"' in inventory_html

    assert personal_response.status_code == 200
    personal_html = personal_response.get_data(as_text=True)
    assert "Personal" in personal_html
    assert "Save portrait" not in personal_html
    assert "Save personal details" not in personal_html
    assert 'name="physical_description_markdown"' not in personal_html
    assert 'name="background_markdown"' not in personal_html
    assert "Open sheet edit view" not in personal_html
    assert "Sheet edit view" not in personal_html

    assert portrait_response.status_code == 200
    portrait_html = portrait_response.get_data(as_text=True)
    assert "Portrait" in portrait_html
    assert "Save portrait" in portrait_html
    assert 'name="page" value="portrait"' in portrait_html

    assert notes_response.status_code == 200
    notes_html = notes_response.get_data(as_text=True)
    assert 'data-character-sheet-edit-form="notes"' in notes_html
    assert "Save note" in notes_html
    assert "Save pending changes" not in notes_html
    assert 'name="mode" value="read"' in notes_html

    assert controls_response.status_code == 200
    controls_html = controls_response.get_data(as_text=True)
    assert "Player-controls workspace for Arden March." in controls_html
    assert "Assignment controls" not in controls_html
    assert "Delete character" not in controls_html


def test_dnd_character_normal_page_hides_inline_state_controls_for_read_only_users(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["party"]["email"], users["party"]["password"])

    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?page=quick")
    spell_response = client.get("/campaigns/linden-pass/characters/arden-march?page=spellcasting")
    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    personal_response = client.get("/campaigns/linden-pass/characters/arden-march?page=personal")
    portrait_response = client.get("/campaigns/linden-pass/characters/arden-march?page=portrait")
    notes_response = client.get("/campaigns/linden-pass/characters/arden-march?page=notes")
    controls_response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert quick_response.status_code == 200
    quick_html = quick_response.get_data(as_text=True)
    assert "At a glance" in quick_html
    assert 'data-character-sheet-edit-form="vitals"' not in quick_html
    assert 'data-character-sheet-edit-form="resource"' not in quick_html
    assert "Save vitals" not in quick_html
    assert "glance-grid--quick-row-1" in quick_html
    assert "ability-skill-list" in quick_html

    assert spell_response.status_code == 200
    spell_html = spell_response.get_data(as_text=True)
    assert "Spellcasting" in spell_html
    assert 'data-character-sheet-edit-form="spell-slot"' not in spell_html

    assert inventory_response.status_code == 200
    inventory_html = inventory_response.get_data(as_text=True)
    assert "Inventory and currency" in inventory_html
    assert 'data-character-sheet-edit-form="inventory"' not in inventory_html
    assert 'data-character-sheet-edit-form="currency"' not in inventory_html
    assert "Save currency" not in inventory_html

    assert personal_response.status_code == 200
    personal_html = personal_response.get_data(as_text=True)
    assert "Personal" in personal_html
    assert "Save portrait" not in personal_html
    assert "Save personal details" not in personal_html
    assert 'name="physical_description_markdown"' not in personal_html
    assert 'name="background_markdown"' not in personal_html

    assert portrait_response.status_code == 200
    portrait_html = portrait_response.get_data(as_text=True)
    assert "Portrait" in portrait_html
    assert "Save portrait" not in portrait_html

    assert notes_response.status_code == 200
    notes_html = notes_response.get_data(as_text=True)
    assert "Notes" in notes_html
    assert 'data-character-sheet-edit-form="notes"' not in notes_html
    assert "Save note" not in notes_html

    assert controls_response.status_code == 200
    controls_html = controls_response.get_data(as_text=True)
    assert "At a glance" in controls_html
    assert "Controls" not in controls_html
    assert 'data-character-read-target-subpage="controls"' not in controls_html

    client.post("/sign-out", follow_redirects=False)
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["observer"]["email"], users["observer"]["password"])
    observer_response = client.get("/campaigns/linden-pass/characters/arden-march?page=quick")

    assert observer_response.status_code == 200
    observer_html = observer_response.get_data(as_text=True)
    assert 'data-character-sheet-edit-form="vitals"' not in observer_html
    assert 'data-character-sheet-edit-form="resource"' not in observer_html
    assert "Save vitals" not in observer_html


@pytest.mark.parametrize("user_key", ["dm", "admin"])
def test_dnd_character_normal_page_preserves_advanced_and_management_controls_for_staff(
    client, sign_in, users, set_campaign_visibility, user_key
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users[user_key]["email"], users[user_key]["password"])

    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?page=quick")
    controls_response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")
    personal_response = client.get("/campaigns/linden-pass/characters/arden-march?page=personal")
    portrait_response = client.get("/campaigns/linden-pass/characters/arden-march?page=portrait")
    edit_response = client.get("/campaigns/linden-pass/characters/arden-march/edit")

    assert quick_response.status_code == 200
    quick_html = quick_response.get_data(as_text=True)
    assert "Advanced Editor" in quick_html
    assert "character-header__actions" in quick_html
    assert "Open sheet edit view" not in quick_html
    assert "Sheet edit view" not in quick_html
    assert 'data-character-sheet-edit-form="vitals"' in quick_html
    assert 'data-character-sheet-edit-form="resource"' in quick_html

    assert controls_response.status_code == 200
    controls_html = controls_response.get_data(as_text=True)
    assert "Controls" in controls_html
    assert "Delete character" in controls_html
    assert "Open sheet edit view" not in controls_html
    if user_key == "admin":
        assert "Assignment controls" in controls_html
        assert "Save assignment" in controls_html
    else:
        assert "Assignment controls" not in controls_html

    assert personal_response.status_code == 200
    personal_html = personal_response.get_data(as_text=True)
    assert "Save portrait" not in personal_html
    assert "Save personal details" not in personal_html
    assert 'name="physical_description_markdown"' not in personal_html
    assert 'name="background_markdown"' not in personal_html

    assert portrait_response.status_code == 200
    portrait_html = portrait_response.get_data(as_text=True)
    assert "Save portrait" in portrait_html
    assert 'name="page" value="portrait"' in portrait_html

    assert edit_response.status_code == 200
    edit_html = edit_response.get_data(as_text=True)
    assert "Character editor" in edit_html
    assert "Advanced campaign-time adjustments and durable reference text" in edit_html
    assert 'name="physical_description_markdown"' in edit_html
    assert 'name="background_markdown"' in edit_html


def test_character_view_no_longer_uses_sheet_edit_lane_label(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Sheet edit view" not in html
    assert "Open sheet edit view" not in html
    assert 'href="/campaigns/linden-pass/help#characters"' not in html
    assert "Open Character Help" not in html


def test_sheet_edit_view_links_to_session_character_and_combat_when_both_are_live(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=inventory")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Open Character Help" not in html
    assert 'href="/campaigns/linden-pass/help#characters"' not in html
    assert "/campaigns/linden-pass/session/character?character=arden-march&amp;page=inventory" not in html
    assert ">Open Session Character<" not in html
    assert '/campaigns/linden-pass/combat?combatant=' not in html
    assert ">Open Combat<" not in html
    assert "Character-page sheet edit" not in html
    assert "Combat-context editing" not in html


def test_help_copy_distinguishes_inline_state_edits_from_advanced_editor(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/help")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Who can use inline state edits" in html
    assert "Current HP, temp HP, tracked resources, and spell slot usage" in html
    assert "Compatibility note" in html
    assert "?mode=session" in html
    assert "`?mode=session` is a compatibility alias for the standard Character page." in html
    assert "Assigned player owners can use inline Character-page state edits for their own characters." in html
    assert "DMs can use the same inline state edits on managed characters." in html
    assert "Owner assignment stays admin-only on Controls" in html
    assert "Observers and unassigned players stay on the standard Character page without inline state-edit affordances." in html
    assert "Advanced Editor" in html
    assert "These edits save immediately per form and stay on the Character page rather than opening a separate edit mode." in html
    assert "Sheet edit view" not in html


def test_character_copy_no_longer_mentions_batch_sheet_edit_drafts(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Cancel pending changes" not in html
    assert "Unsaved edits stay local until save/cancel." not in html
    assert "pending draft was restored locally for review" not in html
    assert "Compare the refreshed sheet and save again when ready." not in html
    assert "beforeunload" not in html
    assert "Pending changes. Save or cancel before you leave." not in html
    assert "Save pending changes" not in html
    assert "data-character-sheet-save-bar" not in html
    assert "data-character-sheet-save-action" not in html
    assert "data-character-sheet-cancel-action" not in html
    assert "data-character-sheet-reset-pending" not in html
    assert "data-character-sheet-immediate-action" not in html
    assert "characterSheetEditEndpoint" not in html


def test_character_sheet_renders_systems_links_when_present(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        classes = list(profile.get("classes") or [])
        if classes:
            first_class = dict(classes[0] or {})
            first_class["systems_ref"] = {
                "entry_type": "class",
                "slug": "phb-class-sorcerer",
                "title": "Sorcerer",
                "source_id": "PHB",
            }
            first_class["subclass_ref"] = {
                "entry_type": "subclass",
                "slug": "phb-subclass-wild-magic",
                "title": "Wild Magic",
                "source_id": "PHB",
            }
            classes[0] = first_class
        profile["classes"] = classes
        profile["class_ref"] = {
            "entry_type": "class",
            "slug": "phb-class-sorcerer",
            "title": "Sorcerer",
            "source_id": "PHB",
        }
        profile["subclass_ref"] = {
            "entry_type": "subclass",
            "slug": "phb-subclass-wild-magic",
            "title": "Wild Magic",
            "source_id": "PHB",
        }
        profile["species_ref"] = {
            "entry_type": "race",
            "slug": "phb-race-human",
            "title": "Human",
            "source_id": "PHB",
        }
        profile["background_ref"] = {
            "entry_type": "background",
            "slug": "phb-background-noble",
            "title": "Noble",
            "source_id": "PHB",
        }
        payload["profile"] = profile

        features = list(payload.get("features") or [])
        if features:
            features[2]["systems_ref"] = {
                "entry_type": "classfeature",
                "slug": "phb-classfeature-spellcasting",
                "title": "Spellcasting",
                "source_id": "PHB",
            }
        payload["features"] = features

        attacks = list(payload.get("attacks") or [])
        if attacks:
            attacks[0]["systems_ref"] = {
                "entry_type": "item",
                "slug": "phb-item-crossbow-light",
                "title": "Crossbow, Light",
                "source_id": "PHB",
            }
        payload["attacks"] = attacks

        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        if spells:
            spells[0]["systems_ref"] = {
                "entry_type": "spell",
                "slug": "phb-spell-message",
                "title": "Message",
                "source_id": "PHB",
            }
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        if len(equipment_catalog) > 4:
            equipment_catalog[4]["systems_ref"] = {
                "entry_type": "item",
                "slug": "phb-item-backpack",
                "title": "Backpack",
                "source_id": "PHB",
            }
        payload["equipment_catalog"] = equipment_catalog

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")
    spellcasting_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    features_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")
    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=inventory")

    assert quick_response.status_code == 200
    assert spellcasting_response.status_code == 200
    assert features_response.status_code == 200
    assert inventory_response.status_code == 200

    quick_html = quick_response.get_data(as_text=True)
    spellcasting_html = spellcasting_response.get_data(as_text=True)
    features_html = features_response.get_data(as_text=True)
    inventory_html = inventory_response.get_data(as_text=True)

    assert '/campaigns/linden-pass/systems/entries/phb-class-sorcerer' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-subclass-wild-magic' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-race-human' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-background-noble' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-item-crossbow-light' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-spell-message' not in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-spell-message' in spellcasting_html
    assert '/campaigns/linden-pass/systems/entries/phb-classfeature-spellcasting' in features_html
    assert '/campaigns/linden-pass/systems/entries/phb-item-backpack' in inventory_html
    assert 'View source entry' not in quick_html
    assert 'View source entry' not in spellcasting_html
    assert 'View source entry' not in features_html
    assert 'View source entry' not in inventory_html


def test_character_sheet_collapses_linked_spell_and_item_descriptions(
    app, client, sign_in, users, monkeypatch
):
    def _mutate(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        if spells:
            spells[0] = {
                **dict(spells[0]),
                "systems_ref": {
                    "entry_type": "spell",
                    "slug": "phb-spell-message",
                    "title": "Message",
                    "source_id": "PHB",
                },
            }
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        if len(equipment_catalog) > 4:
            equipment_catalog[4] = {
                **dict(equipment_catalog[4]),
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "phb-item-backpack",
                    "title": "Backpack",
                    "source_id": "PHB",
                },
            }
        payload["equipment_catalog"] = equipment_catalog

    _write_character_definition(app, "arden-march", _mutate)

    fake_spell = SystemsEntryRecord(
        id=991,
        library_slug="DND-5E",
        source_id="PHB",
        entry_key="dnd-5e|spell|phb|message",
        entry_type="spell",
        slug="phb-spell-message",
        title="Message",
        source_page="",
        source_path="",
        search_text="message",
        player_safe_default=True,
        dm_heavy=False,
        metadata={},
        body={"entries": ["Character spell detail body from Systems."]},
        rendered_html="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    fake_item = SystemsEntryRecord(
        id=992,
        library_slug="DND-5E",
        source_id="PHB",
        entry_key="dnd-5e|item|phb|backpack",
        entry_type="item",
        slug="phb-item-backpack",
        title="Dagger",
        source_page="",
        source_path="",
        search_text="dagger",
        player_safe_default=True,
        dm_heavy=False,
        metadata={"weight": 1},
        body={"entries": ["Character item detail body from Systems."]},
        rendered_html="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    systems_service = app.extensions["systems_service"]
    original_get_entry = systems_service.get_entry_by_slug_for_campaign

    def _fake_get_entry(campaign_slug: str, entry_slug: str):
        if campaign_slug == "linden-pass" and entry_slug == "phb-spell-message":
            return fake_spell
        if campaign_slug == "linden-pass" and entry_slug == "phb-item-backpack":
            return fake_item
        return original_get_entry(campaign_slug, entry_slug)

    monkeypatch.setattr(systems_service, "get_entry_by_slug_for_campaign", _fake_get_entry)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    spellcasting_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=inventory")

    assert spellcasting_response.status_code == 200
    assert inventory_response.status_code == 200

    spellcasting_html = spellcasting_response.get_data(as_text=True)
    inventory_html = inventory_response.get_data(as_text=True)

    assert "Spell details" in spellcasting_html
    assert "Character spell detail body from Systems." in spellcasting_html
    assert "Item details" in inventory_html
    assert 'class="ghost-button item-detail-button"' in inventory_html
    assert 'aria-controls="item-detail-dialog-' in inventory_html
    assert 'class="spell-detail-dialog item-detail-dialog"' in inventory_html
    assert "data-character-spell-modal" in inventory_html
    assert "data-presentation-dialog" in inventory_html
    assert '<details class="item-description-detail">' not in inventory_html
    assert "Item properties" in inventory_html
    assert "1d4 piercing" in inventory_html
    assert "Finesse, Light, Thrown" in inventory_html
    assert "Character item detail body from Systems." in inventory_html
    assert 'class="meta-badge">x' not in inventory_html
    assert re.search(r'class="meta-badge">[^<]*\blb\.?', inventory_html) is None


def test_character_sheet_renders_campaign_page_links_when_present(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        attacks = list(payload.get("attacks") or [])
        if attacks:
            attacks[0]["name"] = "Consecrated Huran Blade"
            attacks[0]["systems_ref"] = None
            attacks[0]["page_ref"] = {
                "slug": "items/consecrated-huran-blade",
                "title": "Consecrated Huran Blade",
            }
        payload["attacks"] = attacks

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        if equipment_catalog:
            equipment_catalog[0]["name"] = "Consecrated Huran Blade"
            equipment_catalog[0]["systems_ref"] = None
            equipment_catalog[0]["page_ref"] = {
                "slug": "items/consecrated-huran-blade",
                "title": "Consecrated Huran Blade",
            }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        if inventory:
            inventory[0] = {
                **dict(inventory[0]),
                "name": "Consecrated Huran Blade",
            }
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")
    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=inventory")

    assert quick_response.status_code == 200
    assert inventory_response.status_code == 200

    quick_html = quick_response.get_data(as_text=True)
    inventory_html = inventory_response.get_data(as_text=True)

    assert '/campaigns/linden-pass/pages/items/consecrated-huran-blade' in quick_html
    assert '/campaigns/linden-pass/pages/items/consecrated-huran-blade' in inventory_html
    assert '>Consecrated Huran Blade</a>' in quick_html
    assert '>Consecrated Huran Blade</a>' in inventory_html


def test_character_sheet_shows_systems_feature_text_inline_and_hides_source_metadata(
    app, client, sign_in, users, monkeypatch
):
    def _mutate(payload: dict) -> None:
        features = list(payload.get("features") or [])
        if not features:
            return
        features[0] = {
            "name": "Spellcasting",
            "category": "class_feature",
            "source": "Unique Source 77",
            "description_markdown": "",
            "activation_type": "bonus_action",
            "tracker_ref": None,
            "systems_ref": {
                "entry_type": "classfeature",
                "slug": "phb-classfeature-spellcasting",
                "title": "Spellcasting",
                "source_id": "PHB",
            },
        }
        payload["features"] = features

    _write_character_definition(app, "arden-march", _mutate)

    fake_entry = SystemsEntryRecord(
        id=999,
        library_slug="DND-5E",
        source_id="PHB",
        entry_key="dnd-5e|classfeature|phb|spellcasting",
        entry_type="classfeature",
        slug="phb-classfeature-spellcasting",
        title="Spellcasting",
        source_page="",
        source_path="",
        search_text="spellcasting",
        player_safe_default=True,
        dm_heavy=False,
        metadata={},
        body={"entries": ["You can cast spells using your force of personality as your spellcasting focus."]},
        rendered_html="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    systems_service = app.extensions["systems_service"]
    original_get_entry = systems_service.get_entry_by_slug_for_campaign

    def _fake_get_entry(campaign_slug: str, entry_slug: str):
        if campaign_slug == "linden-pass" and entry_slug == "phb-classfeature-spellcasting":
            return fake_entry
        return original_get_entry(campaign_slug, entry_slug)

    monkeypatch.setattr(systems_service, "get_entry_by_slug_for_campaign", _fake_get_entry)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '>Spellcasting</a>' in html
    assert '/campaigns/linden-pass/systems/entries/phb-classfeature-spellcasting' in html
    assert 'You can cast spells using your force of personality as your spellcasting focus.' in html
    assert 'Unique Source 77' not in html
    assert 'View source entry' not in html


def test_character_sheet_shows_campaign_page_feature_text_inline(app, client, sign_in, users):
    mechanics_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "content" / "mechanics"
    mechanics_dir.mkdir(parents=True, exist_ok=True)
    (mechanics_dir / "wild-magic-modification.md").write_text(
        "---\n"
        "title: Wild Magic Modification\n"
        "section: Mechanics\n"
        "type: mechanic\n"
        "---\n\n"
        "You gain a number of Wild Die equal to half your level. A Wild Die is a d6.\n",
        encoding="utf-8",
    )
    with app.app_context():
        app.extensions["repository_store"].refresh()

    def _mutate(payload: dict) -> None:
        payload["features"] = [
            {
                "id": "wild-magic-mod",
                "name": "Wild Magic Mod",
                "category": "feat",
                "description_markdown": "",
                "activation_type": "passive",
                "tracker_ref": "wild-die",
                "page_ref": {
                    "slug": "mechanics/wild-magic-modification",
                    "title": "Wild Magic Modification",
                },
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert ">Wild Magic Mod</a>" in html
    assert "/campaigns/linden-pass/pages/mechanics/wild-magic-modification" in html
    assert "A Wild Die is a d6." in html


def test_temporal_awareness_adds_intelligence_modifier_to_initiative(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        stats = dict(payload.get("stats") or {})
        stats["initiative_bonus"] = 1
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["dex"] = {"score": 13, "modifier": 1, "save_bonus": 1}
        ability_scores["int"] = {"score": 20, "modifier": 5, "save_bonus": 8}
        ability_scores["dexterity"] = {"score": 13, "modifier": 1, "save_bonus": 1}
        ability_scores["intelligence"] = {"score": 20, "modifier": 5, "save_bonus": 8}
        stats["ability_scores"] = ability_scores
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "temporal-awareness",
                "name": "Temporal Awareness",
                "category": "class_feature",
                "description_markdown": "You can add your Intelligence modifier to your initiative rolls.",
                "activation_type": "passive",
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Initiative" in html
    assert "<strong>+6</strong>" in html


def test_character_sheet_nests_armorer_armor_model_components(app, client, sign_in, users):
    def _mutate_definition(payload: dict) -> None:
        payload["features"] = [
            {
                "id": "arcane-armor-1",
                "name": "Arcane Armor",
                "category": "class_feature",
                "description_markdown": "You turn worn armor into Arcane Armor.",
                "activation_type": "action",
            },
            {
                "id": "armor-model-2",
                "name": "Armor Model",
                "category": "class_feature",
                "description_markdown": "Choose Guardian or Infiltrator.",
                "activation_type": "passive",
            },
            {
                "id": "guardian-3",
                "name": "Guardian",
                "category": "class_feature",
                "description_markdown": "You design your armor to be in the front line of conflict.",
                "activation_type": "passive",
            },
            {
                "id": "guardian-thunder-4",
                "name": "Guardian Armor: Thunder Gauntlets",
                "category": "class_feature",
                "description_markdown": "Each gauntlet deals 1d8 thunder damage.",
                "activation_type": "action",
            },
            {
                "id": "guardian-field-5",
                "name": "Guardian Armor: Defensive Field",
                "category": "class_feature",
                "description_markdown": "You gain temporary hit points.",
                "activation_type": "bonus_action",
                "tracker_ref": "guardian-armor-defensive-field",
            },
            {
                "id": "guardian-thunder-str-6",
                "name": "Guardian Armor: Thunder Gauntlets (STR)",
                "category": "class_feature",
                "description_markdown": "",
                "activation_type": "action",
            },
            {
                "id": "flash-of-genius-7",
                "name": "Flash of Genius",
                "category": "class_feature",
                "description_markdown": "Add your Intelligence modifier to an ability check or saving throw.",
                "activation_type": "reaction",
            },
        ]

    def _mutate_state(payload: dict) -> None:
        resources = [
            dict(resource or {})
            for resource in list(payload.get("resources") or [])
            if str((resource or {}).get("id") or "") != "guardian-armor-defensive-field"
        ]
        resources.append(
            {
                "id": "guardian-armor-defensive-field",
                "label": "Defensive Field",
                "current": 3,
                "max": 3,
                "reset_on": "long_rest",
            }
        )
        payload["resources"] = resources

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    def _assert_armorer_components(html: str) -> None:
        assert re.search(r"<h4>\s*Arcane Armor\s*</h4>", html)
        assert re.search(r"<h4>\s*Flash of Genius\s*</h4>", html)
        for child_name in (
            "Armor Model",
            "Guardian",
            "Guardian Armor: Thunder Gauntlets",
            "Guardian Armor: Defensive Field",
        ):
            assert not re.search(rf"<h4>\s*{re.escape(child_name)}\s*</h4>", html)
            assert re.search(rf"<h5>\s*{re.escape(child_name)}\s*</h5>", html)
        assert "feature-row__components" in html
        assert "Each gauntlet deals 1d8 thunder damage." in html
        assert "Bonus Action | Defensive Field: 3 / 3 (Long Rest)" in html
        assert "Guardian Armor: Thunder Gauntlets (STR)" not in html

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")
    session_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=features")

    assert read_response.status_code == 200
    assert session_response.status_code == 200
    _assert_armorer_components(read_response.get_data(as_text=True))
    _assert_armorer_components(session_response.get_data(as_text=True))


def test_character_sheet_nests_artificer_infusion_rows_under_artificer_infusions(app, client, sign_in, users):
    _seed_systems_entry(
        app,
        source_id="TCE",
        entry_type="classfeature",
        slug="tce-classfeature-infuseitem-artificer-tce-2",
        title="Infuse Item",
        rendered_html="<p>Infuse Item source text should stay in Systems.</p>",
    )
    _seed_systems_entry(
        app,
        source_id="TCE",
        entry_type="optionalfeature",
        slug="tce-optionalfeature-replicatemagicitem",
        title="Replicate Magic Item",
        rendered_html="<p>Replicate Magic Item source text should stay in Systems.</p>",
    )
    _seed_systems_entry(
        app,
        source_id="DMG",
        entry_type="item",
        slug="dmg-item-gogglesofnight",
        title="Goggles of Night",
        rendered_html="<p>Goggles of Night source text should stay in Systems.</p>",
    )

    def _mutate_definition(payload: dict) -> None:
        payload["features"] = [
            {
                "id": "artificer-infusions-8",
                "name": "Artificer Infusions",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": "You have invented numerous magical  infusions.",
                "activation_type": "passive",
            },
            {
                "id": "artificer-enhanced-defense-9",
                "name": "Enhanced Defense",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": "Grant +1 to AC to one item.",
                "activation_type": "passive",
                "native_edit_parent_feature_id": "artificer-infusions-8",
            },
            {
                "id": "artificer-homunculus-servant-10",
                "name": "Homunculus Servant",
                "category": "class_feature",
                "source": "TCoE 13",
                "description_markdown": "You can summon a tiny guardian construct.",
                "activation_type": "action",
                "native_edit_parent_feature_id": "artificer-infusions-8",
            },
            {
                "id": "artificer-replicate-magic-item-goggles-11",
                "name": "Replicate Magic Item (Goggles of Night)",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": (
                    "Turn two objects into magic goggles. "
                    "This is the long body text you want to hide in the nested card."
                ),
                "activation_type": "bonus_action",
            },
            {
                "id": "artificer-repeating-shot-12",
                "name": "Repeating Shot",
                "category": "class_feature",
                "source": "TCoE 13",
                "description_markdown": "Your firearm shots can be repeated after short rests.",
                "activation_type": "special",
            },
            {
                "id": "artificer-boots-winding-path-13",
                "name": "Boots of the Winding Path",
                "category": "class_feature",
                "source": "TCoE 13",
                "description_markdown": "You can move more quickly while infused.",
                "activation_type": "passive",
            },
            {
                "id": "artificer-armor-magical-strength-14",
                "name": "Armor of Magical Strength",
                "category": "class_feature",
                "source": "TCoE 13",
                "description_markdown": "Choose a melee weapon and gain strength bonus.",
                "activation_type": "passive",
                "native_edit_parent_feature_id": "artificer-infusions-8",
            },
            {
                "id": "artificer-custom-choice-15",
                "name": "Custom Infusion Choice",
                "category": "class_feature",
                "source": "Campaign",
                "description_markdown": "A non-catalog child choice should still nest by parent id.",
                "activation_type": "passive",
                "native_edit_parent_feature_id": "artificer-infusions-8",
            },
            {
                "id": "artificer-feature-16",
                "name": "Other Feature",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": "Should stay top level.",
                "activation_type": "passive",
            },
        ]

    _write_character_definition(app, "arden-march", _mutate_definition)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    def _assert_artificer_infusion_components(html: str) -> None:
        assert re.search(
            r'<h4>\s*<a href="/campaigns/linden-pass/systems/entries/tce-classfeature-infuseitem-artificer-tce-2">\s*Artificer Infusions\s*</a>\s*</h4>',
            html,
        )
        assert re.search(r"<h4>\s*Other Feature\s*</h4>", html)

        def assert_component_heading(label: str) -> None:
            assert re.search(
                rf"<h5>\s*(?:<a [^>]+>)?\s*{re.escape(label)}\s*(?:</a>)?\s*</h5>",
                html,
            )

        for child_name in (
            "Enhanced Defense",
            "Homunculus Servant",
            "Replicate Magic Item (Goggles of Night)",
            "Repeating Shot",
            "Boots of the Winding Path",
            "Armor of Magical Strength",
            "Custom Infusion Choice",
        ):
            assert not re.search(rf"<h4>\s*{re.escape(child_name)}\s*</h4>", html)
            assert_component_heading(child_name)
        assert html.count("Replicate Magic Item (Goggles of Night)") == 1
        assert re.search(
            r'<h5>\s*<a href="/campaigns/linden-pass/systems/entries/dmg-item-gogglesofnight">\s*Goggles of Night\s*</a>\s*</h5>',
            html,
        )
        assert "/campaigns/linden-pass/systems/entries/tce-optionalfeature-replicatemagicitem" in html
        assert "This is the long body text you want to hide in the nested card." not in html
        assert "Replicate Magic Item source text should stay in Systems." not in html
        assert "Goggles of Night source text should stay in Systems." not in html
        assert "feature-row__components" in html

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")
    session_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=features")

    assert read_response.status_code == 200
    assert session_response.status_code == 200
    _assert_artificer_infusion_components(read_response.get_data(as_text=True))
    _assert_artificer_infusion_components(session_response.get_data(as_text=True))


def test_character_sheet_hides_generated_artificer_infusion_summary_lines(app, client, sign_in, users):
    _seed_systems_entry(
        app,
        source_id="TCE",
        entry_type="classfeature",
        slug="tce-classfeature-infuseitem-artificer-tce-2",
        title="Infuse Item",
        rendered_html="<p>Infuse Item source text should stay in Systems.</p>",
    )

    def _mutate_definition(payload: dict) -> None:
        payload["features"] = [
            {
                "id": "artificer-infusions-8",
                "name": "Artificer Infusions",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": (
                    "Known infusions at artificer level 6: Enhanced Defense - Homunculus Servant - "
                    "Replicate Magic Item (Goggles of Night) - Repeating Shot.\n\n"
                    "Replicate Magic Item selection: Goggles of Night.\n\n"
                    "This remaining note is not generated summary prose."
                ),
                "activation_type": "passive",
            }
        ]

    _write_character_definition(app, "arden-march", _mutate_definition)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "/campaigns/linden-pass/systems/entries/tce-classfeature-infuseitem-artificer-tce-2" in html
    assert "Known infusions at artificer level 6" not in html
    assert "Replicate Magic Item selection: Goggles of Night" not in html
    assert "This remaining note is not generated summary prose." in html
    assert "Infuse Item source text should stay in Systems." not in html


def test_arcane_armor_state_gates_guardian_attacks_on_character_sheet(app, client, sign_in, users):
    def _mutate_definition(payload: dict) -> None:
        payload["attacks"] = [
            {
                "id": "guardian-armor-thunder-gauntlets-1",
                "name": "Guardian Armor: Thunder Gauntlets",
                "category": "weapon",
                "attack_bonus": 8,
                "damage": "1d8+5 Thunder",
                "notes": "",
            }
        ]
        payload["features"] = [
            {
                "id": "arcane-armor-1",
                "name": "Arcane Armor",
                "category": "class_feature",
                "description_markdown": "You turn worn armor into Arcane Armor.",
                "activation_type": "action",
            },
            {
                "id": "armor-model-2",
                "name": "Armor Model",
                "category": "class_feature",
                "description_markdown": "Choose Guardian or Infiltrator.",
                "activation_type": "passive",
            },
            {
                "id": "guardian-3",
                "name": "Guardian",
                "category": "class_feature",
                "description_markdown": "You design your armor to be in the front line of conflict.",
                "activation_type": "passive",
            },
            {
                "id": "guardian-thunder-4",
                "name": "Guardian Armor: Thunder Gauntlets",
                "category": "class_feature",
                "description_markdown": "Each gauntlet deals 1d8 thunder damage.",
                "activation_type": "action",
            },
            {
                "id": "guardian-field-5",
                "name": "Guardian Armor: Defensive Field",
                "category": "class_feature",
                "description_markdown": "You gain temporary hit points.",
                "activation_type": "bonus_action",
                "tracker_ref": "guardian-armor-defensive-field",
            },
        ]
        for item in list(payload.get("equipment_catalog") or []):
            item["is_equipped"] = False
            item.pop("weapon_wield_mode", None)

    def _mutate_state(payload: dict) -> None:
        payload.pop("feature_states", None)
        for item in list(payload.get("inventory") or []):
            item["is_equipped"] = False
            item.pop("weapon_wield_mode", None)

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert campaign is not None
        assert record is not None
        disabled_character = app_module.present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )
        assert disabled_character["arcane_armor_state"]["enabled"] is False
        assert "Guardian Armor: Thunder Gauntlets" not in {
            attack["name"] for attack in disabled_character["attacks"]
        }
        assert "Guardian Armor: Thunder Gauntlets" in {
            attack["name"] for attack in disabled_character["hidden_attacks"]
        }

    equipment_page = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")
    assert equipment_page.status_code == 200
    equipment_html = equipment_page.get_data(as_text=True)
    assert "Arcane Armor enabled" in equipment_html
    assert "Save Arcane Armor" not in equipment_html
    assert 'data-character-autosubmit' in equipment_html

    enable_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/feature-states/arcane_armor",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert enable_response.status_code == 302

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert campaign is not None
        assert record is not None
        assert record.state_record.state["feature_states"]["arcane_armor"]["enabled"] is True
        enabled_character = app_module.present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )
        assert "Guardian Armor: Thunder Gauntlets" in {
            attack["name"] for attack in enabled_character["attacks"]
        }

    def _occupy_hands(payload: dict) -> None:
        feature_states = dict(payload.get("feature_states") or {})
        feature_states["arcane_armor"] = {"enabled": True}
        payload["feature_states"] = feature_states
        for item in list(payload.get("inventory") or []):
            item_ref = str(item.get("catalog_ref") or item.get("id") or "").strip()
            if item_ref == "quarterstaff-2":
                item["is_equipped"] = True
                item["weapon_wield_mode"] = "main-hand"

    _write_character_state(app, "arden-march", _occupy_hands)

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert campaign is not None
        assert record is not None
        occupied_character = app_module.present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )
        assert occupied_character["arcane_armor_state"]["enabled"] is True
        assert occupied_character["arcane_armor_state"]["hands_free"] is False
        assert "Guardian Armor: Thunder Gauntlets" not in {
            attack["name"] for attack in occupied_character["attacks"]
        }
        assert "Guardian Armor: Thunder Gauntlets" in {
            attack["name"] for attack in occupied_character["hidden_attacks"]
        }


def test_character_sheet_hides_redundant_choice_placeholder_features(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        features = list(payload.get("features") or [])
        features.extend(
            [
                {
                    "name": "Hit Points",
                    "category": "class_feature",
                    "source": "PHB 71",
                    "description_markdown": "Your hit points increase by 1d10 plus your Constitution modifier at fighter level 1.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Proficiencies",
                    "category": "class_feature",
                    "source": "PHB 71",
                    "description_markdown": "You gain proficiency with all armor, shields, simple weapons, and martial weapons.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Languages",
                    "category": "species_trait",
                    "source": "BR 31",
                    "description_markdown": "You can speak, read, and write Common and one extra language.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Ability Score Increase",
                    "category": "species_trait",
                    "source": "BR 31",
                    "description_markdown": "Two different ability scores of your choice increase by 1.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Skills",
                    "category": "species_trait",
                    "source": "BR 31",
                    "description_markdown": "You gain proficiency in one skill of your choice.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Feat",
                    "category": "species_trait",
                    "source": "BR 31",
                    "description_markdown": "You gain one feat of your choice.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Ability Score Improvement",
                    "category": "class_feature",
                    "source": "PHB 72",
                    "description_markdown": "Increase one ability score by 2 or two ability scores by 1.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Fighting Style",
                    "category": "class_feature",
                    "source": "PHB 72",
                    "description_markdown": "You adopt a fighting style specialty.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Psi Warrior",
                    "category": "class_feature",
                    "source": "TCE 42",
                    "description_markdown": "Feature progression: Level 3 through Level 18 subclass features.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Sentinel",
                    "category": "feat",
                    "source": "PHB 169",
                    "description_markdown": "Creatures provoke opportunity attacks from you even if they take the Disengage action.",
                    "activation_type": "reaction",
                    "tracker_ref": None,
                },
            ]
        )
        payload["features"] = features

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Your hit points increase by 1d10 plus your Constitution modifier at fighter level 1." not in html
    assert "You gain proficiency with all armor, shields, simple weapons, and martial weapons." not in html
    assert "You can speak, read, and write Common and one extra language." not in html
    assert "Two different ability scores of your choice increase by 1." not in html
    assert "You gain proficiency in one skill of your choice." not in html
    assert "You gain one feat of your choice." not in html
    assert "Increase one ability score by 2 or two ability scores by 1." not in html
    assert "You adopt a fighting style specialty." not in html
    assert "Feature progression: Level 3 through Level 18 subclass features." not in html
    assert "Creatures provoke opportunity attacks from you even if they take the Disengage action." in html


def test_character_sheet_renders_long_form_imported_ability_keys(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        stats = dict(payload.get("stats") or {})
        stats["ability_scores"] = {
            "strength": {"score": 17, "modifier": 3, "save_bonus": 6},
            "dexterity": {"score": 13, "modifier": 1, "save_bonus": 1},
            "constitution": {"score": 16, "modifier": 3, "save_bonus": 3},
            "intelligence": {"score": 8, "modifier": -1, "save_bonus": -1},
            "wisdom": {"score": 12, "modifier": 1, "save_bonus": 1},
            "charisma": {"score": 19, "modifier": 4, "save_bonus": 7},
        }
        payload["stats"] = stats

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<h3>17</h3>" in html
    assert "<p>Strength</p>" in html
    assert "Modifier +3 | Save +6" in html
    assert "<h3>19</h3>" in html
    assert "<p>Charisma</p>" in html
    assert "Modifier +4 | Save +7" in html


def test_character_sheet_renders_recalculated_structured_save_bonus_values(app, client, sign_in, users):
    sorcerer = SystemsEntryRecord(
        id=1,
        library_slug="DND-5E",
        source_id="PHB",
        entry_key="dnd-5e|class|phb|phb-class-sorcerer",
        entry_type="class",
        slug="phb-class-sorcerer",
        title="Sorcerer",
        source_page="",
        source_path="",
        search_text="sorcerer",
        player_safe_default=True,
        dm_heavy=False,
        metadata={"proficiency": ["con", "cha"]},
        body={},
        rendered_html="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    def _mutate(payload: dict) -> None:
        definition = CharacterDefinition.from_dict(payload)
        definition.features = list(definition.features or []) + [
            {
                "id": "steadfast-aura-1",
                "name": "Steadfast Aura",
                "category": "custom_feature",
                "campaign_option": {
                    "modeled_effects": [
                        "save-bonus:all:2",
                        "save-bonus:abilities:wis,cha:1",
                    ]
                },
            }
        ]
        normalized = normalize_definition_to_native_model(definition, resolved_class=sorcerer)
        payload.clear()
        payload.update(normalized.to_dict())

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<p>Wisdom</p>" in html
    assert re.search(r"Modifier\s+\+1\s*\|\s*Save\s+\+7", html)
    assert "<p>Charisma</p>" in html
    assert re.search(r"Modifier\s+\+4\s*\|\s*Save\s+\+10", html)

