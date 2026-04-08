from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import yaml
from datetime import datetime, timezone

import player_wiki.app as app_module
import pytest
from player_wiki.auth_store import AuthStore
from player_wiki.systems_models import SystemsEntryRecord


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


def _write_campaign_config(app, mutator) -> None:
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_character_definition(app, character_slug: str, mutator) -> None:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_character_state(app, character_slug: str, mutator) -> None:
    with app.app_context():
        repository = app.extensions["character_repository"]
        store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", character_slug)
        assert record is not None
        payload = deepcopy(record.state_record.state)
        mutator(payload)
        store.replace_state(
            record.definition,
            payload,
            expected_revision=record.state_record.revision,
        )


def _read_character_definition(app, character_slug: str) -> dict:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    return yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}


def _character_state_revision(app, character_slug: str) -> int:
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", character_slug)
        assert record is not None
        return int(record.state_record.revision)


def _seed_systems_item_entry(
    app,
    *,
    slug: str = "phb-item-rope",
    title: str = "Rope",
    metadata: dict[str, object] | None = None,
):
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["item"],
            entries=[
                {
                    "entry_key": f"dnd-5e|item|phb|{slug}",
                    "entry_type": "item",
                    "slug": slug,
                    "title": title,
                    "source_page": "150",
                    "source_path": "data/items-base.json",
                    "search_text": f"{title.lower()} rope gear",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "weight": 10,
                        **dict(metadata or {}),
                    },
                    "body": {},
                    "rendered_html": f"<p>{title}.</p>",
                }
            ],
        )
        entry = app.extensions["systems_service"].get_entry_by_slug_for_campaign("linden-pass", slug)
        assert entry is not None
        return entry


def _seed_systems_spell_entries(app, entries: list[dict[str, object]]) -> dict[str, SystemsEntryRecord]:
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        source_titles = {
            "PHB": "Player's Handbook",
            "TCE": "Tasha's Cauldron of Everything",
            "XGE": "Xanathar's Guide to Everything",
        }
        for source_id in sorted({str(entry.get("source_id") or "PHB").strip().upper() for entry in entries}):
            if not source_id:
                continue
            systems_store.upsert_source(
                "DND-5E",
                source_id,
                title=source_titles.get(source_id, source_id),
                license_class="srd_cc",
                public_visibility_allowed=True,
                requires_unofficial_notice=False,
            )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": f"dnd-5e|spell|phb|{str(entry['slug'])}",
                    "entry_type": "spell",
                    "slug": str(entry["slug"]),
                    "title": str(entry["title"]),
                    "source_page": str(entry.get("source_page") or "200"),
                    "source_path": f"data/spells/spells-{str(entry.get('source_id') or 'PHB').strip().lower()}.json",
                    "search_text": str(entry.get("search_text") or f"{entry['title']} spell"),
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "level": int(entry.get("level") or 0),
                        "class_lists": dict(entry.get("class_lists") or {"PHB": []}),
                        "casting_time": list(entry.get("casting_time") or [{"number": 1, "unit": "action"}]),
                        "range": dict(entry.get("range") or {"type": "point", "distance": {"type": "feet", "amount": 60}}),
                        "duration": list(entry.get("duration") or [{"type": "timed", "duration": {"type": "round", "amount": 1}}]),
                        "components": dict(entry.get("components") or {"v": True}),
                    },
                    "body": {},
                    "rendered_html": f"<p>{entry['title']}.</p>",
                }
                for entry in entries
                if str(entry.get("source_id") or "PHB").strip().upper() == "PHB"
            ],
        )
        for source_id in sorted({str(entry.get("source_id") or "PHB").strip().upper() for entry in entries if str(entry.get("source_id") or "PHB").strip().upper() != "PHB"}):
            systems_store.replace_entries_for_source(
                "DND-5E",
                source_id,
                entry_types=["spell"],
                entries=[
                    {
                        "entry_key": f"dnd-5e|spell|{source_id.lower()}|{str(entry['slug'])}",
                        "entry_type": "spell",
                        "slug": str(entry["slug"]),
                        "title": str(entry["title"]),
                        "source_page": str(entry.get("source_page") or "200"),
                        "source_path": f"data/spells/spells-{source_id.lower()}.json",
                        "search_text": str(entry.get("search_text") or f"{entry['title']} spell"),
                        "player_safe_default": True,
                        "dm_heavy": False,
                        "metadata": {
                            "level": int(entry.get("level") or 0),
                            "class_lists": dict(entry.get("class_lists") or {"PHB": []}),
                            "casting_time": list(entry.get("casting_time") or [{"number": 1, "unit": "action"}]),
                            "range": dict(entry.get("range") or {"type": "point", "distance": {"type": "feet", "amount": 60}}),
                            "duration": list(entry.get("duration") or [{"type": "timed", "duration": {"type": "round", "amount": 1}}]),
                            "components": dict(entry.get("components") or {"v": True}),
                        },
                        "body": {},
                        "rendered_html": f"<p>{entry['title']}.</p>",
                    }
                    for entry in entries
                    if str(entry.get("source_id") or "PHB").strip().upper() == source_id
                ],
            )
        systems_service = app.extensions["systems_service"]
        return {
            str(entry["slug"]): systems_service.get_entry_by_slug_for_campaign("linden-pass", str(entry["slug"]))
            for entry in entries
        }


def _systems_ref(entry: SystemsEntryRecord) -> dict[str, str]:
    return {
        "entry_key": str(entry.entry_key or "").strip(),
        "entry_type": str(entry.entry_type or "").strip(),
        "title": str(entry.title or "").strip(),
        "slug": str(entry.slug or "").strip(),
        "source_id": str(entry.source_id or "").strip(),
    }


def _spell_payload(
    entry: SystemsEntryRecord,
    *,
    source: str,
    mark: str = "",
    is_always_prepared: bool = False,
    is_bonus_known: bool = False,
) -> dict[str, object]:
    metadata = dict(entry.metadata or {})
    return {
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
    assert "Enter session mode" in sheet_html
    assert "Alignment:" in sheet_html
    assert "Chaotic Good" in sheet_html
    assert "Campaign:" in sheet_html
    assert "Context" not in sheet_html
    assert "Back to character roster" not in sheet_html
    assert "Open campaign wiki" not in sheet_html


def test_non_5e_roster_hides_native_character_builder_affordances(app, client, sign_in, users):
    _write_campaign_config(app, lambda payload: payload.__setitem__("system", "Pathfinder 2E"))

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Create character" not in html
    assert "/campaigns/linden-pass/characters/new" not in html
    assert "PHB level 1 character" not in html
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
    assert "Enter session mode" in html
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
    assert "Active session" in html
    assert "Back to read mode" in html
    assert "Edit character" not in html


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


@pytest.mark.parametrize("route_suffix", ["edit", "level-up", "progression-repair"])
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
    assert "Active session" in html
    assert "Save vitals" in html
    assert "Back to read mode" in html
    assert "?mode=session&amp;page=quick" in html
    assert "?mode=session&amp;page=personal" in html
    assert "Save personal details" not in html


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
    assert "At a glance" not in html
    assert "Inventory and currency" not in html
    assert "Keep an eye on the harbor." not in html
    assert "mode=session&amp;page=features" in html


def test_spellcasting_subpage_is_only_shown_for_casters_and_holds_spell_list(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    caster_quick = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")
    caster_spellcasting = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    noncaster_quick = client.get("/campaigns/linden-pass/characters/tobin-slate?mode=read&page=quick")

    assert caster_quick.status_code == 200
    caster_quick_html = caster_quick.get_data(as_text=True)
    assert "?page=spellcasting" in caster_quick_html
    assert "Sorcerer" in caster_quick_html
    assert "Spell slots" in caster_quick_html
    assert "Message" not in caster_quick_html

    assert caster_spellcasting.status_code == 200
    caster_spellcasting_html = caster_spellcasting.get_data(as_text=True)
    assert "Spellcasting" in caster_spellcasting_html
    assert "Message" in caster_spellcasting_html
    assert "1 action" in caster_spellcasting_html
    assert "120 feet" in caster_spellcasting_html
    assert "1 round" in caster_spellcasting_html
    assert "V, S, M" in caster_spellcasting_html

    assert noncaster_quick.status_code == 200
    noncaster_quick_html = noncaster_quick.get_data(as_text=True)
    assert "?page=spellcasting" not in noncaster_quick_html


def test_spellcasting_subpage_can_search_add_and_remove_known_spells(app, client, sign_in, users):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-message", "title": "Message", "level": 0, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-shield", "title": "Shield", "level": 1, "class_lists": {"PHB": ["Sorcerer"]}},
            {"slug": "phb-spell-find-familiar", "title": "Find Familiar", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Sorcerer 5"
        profile["classes"] = [{"class_name": "Sorcerer", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
            ],
            "spells": [
                _spell_payload(spell_entries["phb-spell-message"], source="Sorcerer"),
                _spell_payload(spell_entries["phb-spell-magic-missile"], source="Sorcerer"),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Known spells" in page_html
    assert "Add known spell" in page_html

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=spell&q=find"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload == {
        "results": [],
        "message": "No eligible class spells matched that search.",
    }

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "spell",
            "selected_value": "phb-spell-shield",
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    updated_spells = list((updated_definition.get("spellcasting") or {}).get("spells") or [])
    shield_spell = next(spell for spell in updated_spells if spell.get("name") == "Shield")
    assert shield_spell["mark"] == "Known"

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-shield",
        },
        follow_redirects=False,
    )
    assert remove_response.status_code == 302

    final_definition = _read_character_definition(app, "arden-march")
    final_spell_names = [str(spell.get("name") or "") for spell in list((final_definition.get("spellcasting") or {}).get("spells") or [])]
    assert "Shield" not in final_spell_names


def test_spellcasting_search_uses_enabled_systems_sources_only(app, client, sign_in, users):
    def _disable_tce(payload: dict) -> None:
        systems_sources = list(payload.get("systems_sources") or [])
        for index, source in enumerate(systems_sources):
            source_payload = dict(source or {})
            if str(source_payload.get("source_id") or "").strip().upper() != "TCE":
                continue
            source_payload["enabled"] = False
            systems_sources[index] = source_payload
        payload["systems_sources"] = systems_sources

    _write_campaign_config(app, _disable_tce)
    _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-shield", "title": "Shield", "level": 1, "class_lists": {"PHB": ["Sorcerer"]}, "source_id": "PHB"},
            {"slug": "tce-spell-tashascausticbrew", "title": "Tasha's Caustic Brew", "level": 1, "class_lists": {"TCE": ["Sorcerer"]}, "source_id": "TCE"},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Sorcerer 5"
        profile["classes"] = [{"class_name": "Sorcerer", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
            ],
            "spells": [],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    hidden_source_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=spell&q=tasha"
    )
    assert hidden_source_response.status_code == 200
    assert hidden_source_response.get_json() == {
        "results": [],
        "message": "No eligible class spells matched that search.",
    }

    visible_source_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=spell&q=shield"
    )
    assert visible_source_response.status_code == 200
    visible_payload = visible_source_response.get_json()
    assert visible_payload["message"] == "Found 1 matching spells."
    assert visible_payload["results"] == [
        {
            "entry_slug": "phb-spell-shield",
            "title": "Shield",
            "level_label": "1st-level",
            "source_id": "PHB",
            "select_label": "Shield - 1st-level - PHB",
        }
    ]


def test_spellcasting_subpage_can_prepare_spells_and_protect_always_prepared_entries(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-guidance", "title": "Guidance", "level": 0, "class_lists": {"PHB": ["Cleric"]}},
            {"slug": "phb-spell-cure-wounds", "title": "Cure Wounds", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
            {"slug": "phb-spell-bless", "title": "Bless", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Cleric 5"
        profile["classes"] = [{"class_name": "Cleric", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Cleric",
            "spellcasting_ability": "Wisdom",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "spells": [
                _spell_payload(spell_entries["phb-spell-guidance"], source="Cleric"),
                _spell_payload(spell_entries["phb-spell-cure-wounds"], source="Cleric"),
                _spell_payload(spell_entries["phb-spell-bless"], source="Cleric (Always Prepared)", mark="P"),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Prepared spells" in page_html
    assert "Prepare spell" in page_html
    assert "Always prepared" in page_html

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "spell",
            "selected_value": "phb-spell-detect-magic",
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    updated_spells = list((updated_definition.get("spellcasting") or {}).get("spells") or [])
    detect_magic = next(spell for spell in updated_spells if spell.get("name") == "Detect Magic")
    assert detect_magic["mark"] == "Prepared"

    protected_remove = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-bless",
        },
        follow_redirects=True,
    )
    assert protected_remove.status_code == 200
    protected_html = protected_remove.get_data(as_text=True)
    assert "cannot be removed here" in protected_html

    protected_definition = _read_character_definition(app, "arden-march")
    protected_spell_names = [str(spell.get("name") or "") for spell in list((protected_definition.get("spellcasting") or {}).get("spells") or [])]
    assert "Bless" in protected_spell_names

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-detect-magic",
        },
        follow_redirects=False,
    )
    assert remove_response.status_code == 302

    final_definition = _read_character_definition(app, "arden-march")
    final_spell_names = [str(spell.get("name") or "") for spell in list((final_definition.get("spellcasting") or {}).get("spells") or [])]
    assert "Detect Magic" not in final_spell_names


def test_spellcasting_subpage_can_manage_wizard_spellbooks_and_prepare_spells(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-message", "title": "Message", "level": 0, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-shield", "title": "Shield", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Wizard 5"
        profile["classes"] = [{"class_name": "Wizard", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Wizard",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "spells": [
                _spell_payload(spell_entries["phb-spell-message"], source="Wizard", mark="O"),
                _spell_payload(spell_entries["phb-spell-magic-missile"], source="Wizard", mark="O"),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Wizard spellbook" in page_html
    assert "Add spellbook spell" in page_html

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "spellbook",
            "selected_value": "phb-spell-shield",
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    updated_spells = list((updated_definition.get("spellcasting") or {}).get("spells") or [])
    magic_missile = next(spell for spell in updated_spells if spell.get("name") == "Magic Missile")
    shield_spell = next(spell for spell in updated_spells if spell.get("name") == "Shield")
    assert magic_missile["mark"] == "Prepared + Spellbook"
    assert shield_spell["mark"] == "Spellbook"

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/update",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": "phb-spell-shield",
            "prepared_value": "1",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302

    final_definition = _read_character_definition(app, "arden-march")
    final_spells = list((final_definition.get("spellcasting") or {}).get("spells") or [])
    final_shield = next(spell for spell in final_spells if spell.get("name") == "Shield")
    assert final_shield["mark"] == "Prepared + Spellbook"


def test_dm_controls_subpage_shows_management_controls(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Controls" in html
    assert "?page=controls" in html
    assert "Player controls" in html
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


def test_equipment_manager_is_visible_to_editable_users_and_hidden_from_read_only_players(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    sign_in(users["owner"]["email"], users["owner"]["password"])
    owner_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    owner_html = owner_response.get_data(as_text=True)

    assert owner_response.status_code == 200
    assert "Add Systems item" in owner_html
    assert "Add campaign item" in owner_html
    assert "Add custom item" in owner_html
    assert "Supplemental equipment" in owner_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    read_only_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    read_only_html = read_only_response.get_data(as_text=True)

    assert read_only_response.status_code == 200
    assert "Add Systems item" not in read_only_html
    assert "Add campaign item" not in read_only_html
    assert "Add custom item" not in read_only_html
    assert "Supplemental equipment" not in read_only_html


def test_equipment_manager_campaign_item_picker_only_lists_item_pages(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Stormglass Compass - Items" in html
    assert "Operations Brief - Notes" not in html
    assert "Captain Lyra Vale - NPCs" not in html


def test_equipment_subpage_is_separate_from_inventory_manager(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Attuned items" in html
    assert "Equipped items" in html
    assert "Save equipment state" in html
    assert "Add Systems item" not in html
    assert "Supplemental equipment" not in html
    assert "Inventory and currency" not in html


def test_equipment_subpage_can_update_equipped_and_attuned_state(app, client, sign_in, users):
    entry = _seed_systems_item_entry(
        app,
        slug="phb-item-stormglass-compass",
        title="Stormglass Compass",
        metadata={"weight": 1, "attunement": "requires attunement"},
    )

    def _mutate_definition(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        equipment_catalog[4] = {
            **dict(equipment_catalog[4]),
            "name": "Stormglass Compass",
            "weight": "1 lb.",
            "systems_ref": _systems_ref(entry),
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        inventory[4] = {
            **dict(inventory[4]),
            "name": "Stormglass Compass",
            "weight": "1 lb.",
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["inventory"] = inventory
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": []}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")
    assert page_response.status_code == 200
    assert "Requires attunement" in page_response.get_data(as_text=True)

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/backpack-5/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
            "is_attuned": "1",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302
    assert update_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march?page=equipment#character-equipment-state"
    )

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "backpack-5"
        )
        state_item = next(
            item
            for item in list(record.state_record.state.get("inventory") or [])
            if str(item.get("catalog_ref") or item.get("id") or "") == "backpack-5"
        )
        assert definition_item["is_equipped"] is True
        assert definition_item["is_attuned"] is True
        assert state_item["is_equipped"] is True
        assert state_item["is_attuned"] is True
        assert record.state_record.state["attunement"]["attuned_item_refs"] == ["backpack-5"]


def test_imported_character_equipment_controls_can_search_and_add_systems_items_without_resetting_other_quantities(
    app, client, sign_in, users
):
    entry = _seed_systems_item_entry(app)

    _write_character_state(
        app,
        "selene-brook",
        lambda payload: payload.__setitem__(
            "inventory",
            [
                {
                    **dict(item),
                    "quantity": 11 if str(item.get("catalog_ref") or item.get("id") or "") == "arrows-2" else item.get("quantity"),
                }
                for item in list(payload.get("inventory") or [])
            ],
        ),
    )

    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/selene-brook/equipment/systems-items/search?q=rope",
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["results"]
    assert search_payload["results"][0]["entry_slug"] == entry.slug
    assert search_payload["results"][0]["title"] == "Rope"

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "selene-brook")
        assert record is not None
        revision = record.state_record.revision

    add_response = client.post(
        "/campaigns/linden-pass/characters/selene-brook/equipment/add-systems",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "entry_slug": entry.slug,
            "quantity": "2",
            "notes": "Emergency climbing bundle.",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302
    assert add_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/selene-brook?page=inventory#character-inventory-manager"
    )

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "selene-brook")
        assert record is not None
        supplemental = [
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        ]
        assert len(supplemental) == 1
        added_item = supplemental[0]
        assert added_item["name"] == "Rope"
        assert added_item["default_quantity"] == 2
        assert added_item["notes"] == "Emergency climbing bundle."
        assert added_item["systems_ref"]["slug"] == entry.slug

        inventory_by_ref = {
            str(item.get("catalog_ref") or item.get("id") or ""): dict(item)
            for item in list(record.state_record.state.get("inventory") or [])
        }
        assert inventory_by_ref[added_item["id"]]["quantity"] == 2
        assert inventory_by_ref["arrows-2"]["quantity"] == 11

    landing = client.get(add_response.headers["Location"])
    html = landing.get_data(as_text=True)
    assert "Rope" in html
    assert "Emergency climbing bundle." in html
    assert "Remove item" in html


def test_native_character_equipment_controls_can_add_campaign_items_from_item_pages(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _write_character_definition(
        app,
        "arden-march",
        lambda payload: payload.__setitem__(
            "source",
            {"source_type": "native_character_builder", "source_path": "builder://arden-march"},
        ),
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/add-campaign-item",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "page_ref": "items/stormglass-compass",
            "quantity": "1",
            "weight": "",
            "notes": "Issued from the brass vault.",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        manual_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        )
        assert manual_item["name"] == "Stormglass Compass"
        assert manual_item["page_ref"] == "items/stormglass-compass"
        assert manual_item["notes"] == "Issued from the brass vault."
        revision = record.state_record.revision

    update_response = client.post(
        f"/campaigns/linden-pass/characters/arden-march/equipment/{manual_item['id']}/update",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "name": "",
            "quantity": "2",
            "weight": "1 lb.",
            "page_ref": "items/stormglass-compass",
            "notes": "Retuned to the harbor beacons.",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        manual_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        )
        assert manual_item["name"] == "Stormglass Compass"
        assert manual_item["default_quantity"] == 2
        assert manual_item["weight"] == "1 lb."
        assert manual_item["page_ref"] == "items/stormglass-compass"
        assert manual_item["notes"] == "Retuned to the harbor beacons."


def test_native_character_equipment_controls_can_add_update_and_remove_manual_items(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _write_character_definition(
        app,
        "arden-march",
        lambda payload: payload.__setitem__(
            "source",
            {"source_type": "native_character_builder", "source_path": "builder://arden-march"},
        ),
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/add-manual",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "name": "Harbor Pass",
            "quantity": "1",
            "weight": "",
            "notes": "Issued by the harbor office.",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        manual_items = [
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        ]
        assert len(manual_items) == 1
        manual_item = manual_items[0]
        assert not manual_item.get("page_ref")

        revision = record.state_record.revision

    update_response = client.post(
        f"/campaigns/linden-pass/characters/arden-march/equipment/{manual_item['id']}/update",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
            "name": "Harbor Pass",
            "quantity": "3",
            "weight": "",
            "notes": "Stamped for repeat entry.",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        manual_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        )
        assert manual_item["default_quantity"] == 3
        assert manual_item["notes"] == "Stamped for repeat entry."
        revision = record.state_record.revision

    remove_response = client.post(
        f"/campaigns/linden-pass/characters/arden-march/equipment/{manual_item['id']}/remove",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "inventory",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        assert [
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("source_kind") or "").strip() == "manual_edit"
        ] == []


def test_character_personal_portrait_can_be_uploaded_replaced_rendered_and_removed(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    upload_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/personal/portrait",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "personal",
            "portrait_alt": "Arden leaning over the harbor rail.",
            "portrait_caption": "Used on the personal page.",
            "portrait_file": (BytesIO(TEST_PNG_BYTES), "arden-portrait.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert upload_response.status_code == 302

    portrait_png = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "assets"
        / "characters"
        / "arden-march"
        / "portrait.png"
    )
    assert portrait_png.exists()

    read_personal = client.get("/campaigns/linden-pass/characters/arden-march?page=personal")
    read_html = read_personal.get_data(as_text=True)
    assert read_personal.status_code == 200
    assert "/campaigns/linden-pass/characters/arden-march/portrait" in read_html
    assert "Arden leaning over the harbor rail." in read_html
    assert "Remove portrait" in read_html

    session_personal = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=personal")
    session_html = session_personal.get_data(as_text=True)
    assert session_personal.status_code == 200
    assert "/campaigns/linden-pass/characters/arden-march/portrait" in session_html
    assert "Remove portrait" not in session_html
    assert "Save portrait" not in session_html

    portrait_response = client.get("/campaigns/linden-pass/characters/arden-march/portrait")
    assert portrait_response.status_code == 200
    assert portrait_response.mimetype == "image/png"
    assert portrait_response.data == TEST_PNG_BYTES

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    read_only_personal = client.get("/campaigns/linden-pass/characters/arden-march?page=personal")
    read_only_html = read_only_personal.get_data(as_text=True)
    assert read_only_personal.status_code == 200
    assert "/campaigns/linden-pass/characters/arden-march/portrait" in read_only_html
    assert "Save portrait" not in read_only_html
    assert "Remove portrait" not in read_only_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    replace_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/personal/portrait",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "personal",
            "portrait_alt": "Arden in a second portrait.",
            "portrait_caption": "Updated portrait caption.",
            "portrait_file": (BytesIO(TEST_JPG_BYTES), "arden-portrait.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert replace_response.status_code == 302
    portrait_jpg = portrait_png.with_suffix(".jpg")
    assert portrait_jpg.exists()
    assert not portrait_png.exists()

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        revision = record.state_record.revision

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/personal/portrait/remove",
        data={
            "expected_revision": revision,
            "mode": "read",
            "page": "personal",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302
    assert not portrait_jpg.exists()

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        profile = dict(record.definition.profile or {})
        assert profile.get("portrait_asset_ref") in (None, "")


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
    assert "Save personal details" in personal_html
    assert 'name="physical_description_markdown"' in personal_html
    assert 'name="background_markdown"' in personal_html
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
    assert "Save personal details" in html
    assert "Save note" not in html
    assert "At a glance" not in html


def test_editable_users_default_to_read_mode(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" not in html
    assert "Enter session mode" in html
    assert "Back to read mode" not in html


def test_session_active_widget_stays_on_quick_reference_only(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")
    features_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=features")

    assert quick_response.status_code == 200
    quick_html = quick_response.get_data(as_text=True)
    assert "Active session" in quick_html
    assert "Save vitals" in quick_html

    assert features_response.status_code == 200
    features_html = features_response.get_data(as_text=True)
    assert "Active session" not in features_html
    assert "Save vitals" not in features_html


def test_quick_reference_hides_item_backed_attacks_when_the_linked_item_is_not_equipped(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        attacks = list(payload.get("attacks") or [])
        if len(attacks) >= 2:
            attacks[0]["equipment_refs"] = ["light-crossbow-1"]
            attacks[1]["equipment_refs"] = ["quarterstaff-2"]
        payload["attacks"] = attacks

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for item in inventory:
            item_ref = str(item.get("catalog_ref") or item.get("id") or "").strip()
            if item_ref == "light-crossbow-1":
                item["is_equipped"] = False
            elif item_ref == "quarterstaff-2":
                item["is_equipped"] = True
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 1
    assert "Quarterstaff" in html
    assert "Hidden until equipped: Crossbow, Light." in html


def test_quick_reference_can_fall_back_to_legacy_attack_name_matching_for_equipment_state(
    app, client, sign_in, users
):
    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for item in inventory:
            item_ref = str(item.get("catalog_ref") or item.get("id") or "").strip()
            if item_ref == "light-crossbow-1":
                item["is_equipped"] = False
            elif item_ref == "quarterstaff-2":
                item["is_equipped"] = True
        payload["inventory"] = inventory

    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 1
    assert "Quarterstaff" in html
    assert "Hidden until equipped: Crossbow, Light." in html


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
    equipment_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=equipment")

    assert quick_response.status_code == 200
    assert spellcasting_response.status_code == 200
    assert features_response.status_code == 200
    assert equipment_response.status_code == 200

    quick_html = quick_response.get_data(as_text=True)
    spellcasting_html = spellcasting_response.get_data(as_text=True)
    features_html = features_response.get_data(as_text=True)
    equipment_html = equipment_response.get_data(as_text=True)

    assert '/campaigns/linden-pass/systems/entries/phb-class-sorcerer' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-subclass-wild-magic' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-race-human' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-background-noble' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-item-crossbow-light' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-spell-message' not in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-spell-message' in spellcasting_html
    assert '/campaigns/linden-pass/systems/entries/phb-classfeature-spellcasting' in features_html
    assert '/campaigns/linden-pass/systems/entries/phb-item-backpack' in equipment_html
    assert 'View source entry' not in quick_html
    assert 'View source entry' not in spellcasting_html
    assert 'View source entry' not in features_html
    assert 'View source entry' not in equipment_html


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
    equipment_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=equipment")

    assert quick_response.status_code == 200
    assert equipment_response.status_code == 200

    quick_html = quick_response.get_data(as_text=True)
    equipment_html = equipment_response.get_data(as_text=True)

    assert '/campaigns/linden-pass/pages/items/consecrated-huran-blade' in quick_html
    assert '/campaigns/linden-pass/pages/items/consecrated-huran-blade' in equipment_html
    assert '>Consecrated Huran Blade</a>' in quick_html
    assert '>Consecrated Huran Blade</a>' in equipment_html


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


def test_session_currency_editor_renders_plain_fields_without_adjuster_buttons(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=inventory")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="cp"' in html
    assert 'name="sp"' in html
    assert 'name="ep"' in html
    assert 'name="gp"' in html
    assert 'name="pp"' in html
    assert 'value="cp:-1"' not in html
    assert 'value="gp:1"' not in html


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

