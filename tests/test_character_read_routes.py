from __future__ import annotations

from copy import deepcopy
from io import BytesIO
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
            for record in systems_store.list_entries_for_source("DND-5E", "PHB", entry_type="item")
            if str(record.slug or "").strip() != slug
        ]
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["item"],
            entries=existing_entries
            + [
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
                        "ritual": bool(entry.get("ritual")),
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
                            "ritual": bool(entry.get("ritual")),
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
    assert "Open sheet edit view" in sheet_html
    assert "Enter session mode" not in sheet_html
    assert "Alignment:" in sheet_html
    assert "Chaotic Good" in sheet_html
    assert "Campaign:" in sheet_html
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
    assert "open the sheet edit view when you have edit access" in html
    assert "Native character creation and progression stay hidden here" in html


def test_xianxia_roster_uses_system_policy_to_show_xianxia_create_without_dnd_affordances(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Create character" in html
    assert "/campaigns/linden-pass/characters/new" in html
    assert "Xianxia character creator" in html
    assert "PHB level 1 character" not in html
    assert "Native character creation and progression stay hidden here" not in html


def test_dnd5e_character_routes_keep_native_affordances_with_xianxia_policy_present(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "DND-5E"
        payload["systems_library"] = "DND-5E"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    builder = client.get("/campaigns/linden-pass/characters/new")
    sheet = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert roster.status_code == 200
    roster_html = roster.get_data(as_text=True)
    assert "Create character" in roster_html
    assert "/campaigns/linden-pass/characters/new" in roster_html
    assert "PHB level 1 character" in roster_html
    assert "Native character creation and progression stay hidden here" not in roster_html

    assert builder.status_code == 200
    builder_html = builder.get_data(as_text=True)
    assert "Native Level 1 Builder" in builder_html
    assert XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE not in builder_html

    assert sheet.status_code == 200
    sheet_html = sheet.get_data(as_text=True)
    assert "Edit character" in sheet_html
    assert "/campaigns/linden-pass/characters/arden-march/edit" in sheet_html
    assert "Open sheet edit view" in sheet_html
    assert "?page=spellcasting" in sheet_html
    assert app_module.NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE not in sheet_html


def test_xianxia_native_character_create_route_uses_xianxia_context_and_submit_path(
    app, client, sign_in, users, get_character
):
    def _attribute_data() -> dict[str, str]:
        return {
            "attribute_str": "1",
            "attribute_dex": "1",
            "attribute_con": "1",
            "attribute_int": "1",
            "attribute_wis": "1",
            "attribute_cha": "1",
        }

    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    assert roster.status_code == 200
    roster_html = roster.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/new" in roster_html
    assert "Create character" in roster_html
    assert "PHB level 1 character" not in roster_html
    assert "imported PDF" not in roster_html

    create_response = client.get("/campaigns/linden-pass/characters/new")
    assert create_response.status_code == 200
    create_html = create_response.get_data(as_text=True)
    assert "Xianxia Character" in create_html
    assert "Starting Defaults" in create_html
    for attribute_label in (
        "Strength",
        "Dexterity",
        "Constitution",
        "Intelligence",
        "Wisdom",
        "Charisma",
    ):
        assert attribute_label in create_html
    assert "Native Level 1 Builder" not in create_html
    assert "Spell Preview" not in create_html
    assert XIANXIA_NATIVE_CHARACTER_CREATE_UNSUPPORTED_MESSAGE not in create_html

    missing_name = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "", "character_slug": ""},
        follow_redirects=False,
    )
    assert missing_name.status_code == 400
    assert "Character name is required." in missing_name.get_data(as_text=True)

    missing_attributes = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "Attribute Gap", "character_slug": ""},
        follow_redirects=False,
    )
    assert missing_attributes.status_code == 400
    assert (
        "Missing Xianxia attributes: Strength, Dexterity, Constitution, "
        "Intelligence, Wisdom, and Charisma."
    ) in missing_attributes.get_data(as_text=True)

    invalid_attributes = _attribute_data()
    invalid_attributes["attribute_dex"] = "quick"
    invalid_attribute_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "Attribute Typo", "character_slug": "", **invalid_attributes},
        follow_redirects=False,
    )
    assert invalid_attribute_response.status_code == 400
    assert "Dexterity must be a whole number." in invalid_attribute_response.get_data(as_text=True)

    submit_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={"name": "Lotus Wake", "character_slug": "", **_attribute_data()},
        follow_redirects=False,
    )
    assert submit_response.status_code == 302
    assert submit_response.headers["Location"].endswith("/campaigns/linden-pass/characters/lotus-wake")

    definition_payload = _read_character_definition(app, "lotus-wake")
    assert definition_payload["system"] == XIANXIA_SYSTEM_CODE
    assert definition_payload["source"]["source_type"] == "xianxia_character_builder"
    assert definition_payload["spellcasting"] == {}
    assert definition_payload["xianxia"]["realm"] == "Mortal"
    assert definition_payload["xianxia"]["honor"] == "Honorable"
    assert definition_payload["xianxia"]["reputation"] == "Unknown"
    assert definition_payload["xianxia"]["attributes"] == {
        "str": 1,
        "dex": 1,
        "con": 1,
        "int": 1,
        "wis": 1,
        "cha": 1,
    }
    assert definition_payload["xianxia"]["durability"] == {
        "hp_max": 10,
        "stance_max": 10,
        "manual_armor_bonus": 0,
        "defense": 10,
    }
    assert definition_payload["xianxia"]["yin_yang"] == {"yin_max": 1, "yang_max": 1}
    assert definition_payload["xianxia"]["dao"] == {"max": 3}
    assert definition_payload["xianxia"]["insight"] == {"available": 0, "spent": 0}
    assert definition_payload["xianxia"]["martial_arts"] == []
    assert definition_payload["xianxia"]["generic_techniques"] == []

    import_payload = yaml.safe_load(
        (
            app.config["TEST_CAMPAIGNS_DIR"]
            / "linden-pass"
            / "characters"
            / "lotus-wake"
            / "import.yaml"
        ).read_text(encoding="utf-8")
    )
    assert import_payload["source_path"] == "builder://xianxia-create"

    record = get_character("lotus-wake")
    assert record is not None
    assert record.definition.system == XIANXIA_SYSTEM_CODE
    state = record.state_record.state
    assert state["vitals"] == {"current_hp": 10, "temp_hp": 0}
    assert state["spell_slots"] == []
    assert state["resources"] == []
    assert state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 0,
        "current_stance": 10,
        "temp_stance": 0,
    }
    assert state["xianxia"]["energies"] == {
        "jing": {"current": 0},
        "qi": {"current": 0},
        "shen": {"current": 0},
    }
    assert state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 1}
    assert state["xianxia"]["dao"] == {"current": 0}

    expected_messages = {
        "edit": app_module.NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE,
        "level-up": XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
        "progression-repair": XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
        "retraining": XIANXIA_CHARACTER_ADVANCEMENT_UNSUPPORTED_MESSAGE,
    }
    for route_suffix, expected_message in expected_messages.items():
        for method_name in ("get", "post"):
            response = getattr(client, method_name)(
                f"/campaigns/linden-pass/characters/arden-march/{route_suffix}",
                follow_redirects=False,
            )
            assert response.status_code == 302
            assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")
            route_landing = client.get(response.headers["Location"])
            assert expected_message in route_landing.get_data(as_text=True)

    landing = client.get("/campaigns/linden-pass/characters/arden-march")
    html = landing.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/arden-march/edit" not in html
    assert "/campaigns/linden-pass/characters/arden-march/level-up" not in html
    assert "/campaigns/linden-pass/characters/arden-march/progression-repair" not in html
    assert "/campaigns/linden-pass/characters/arden-march/retraining" not in html
    assert "Edit character" not in html
    assert "Level up" not in html
    assert "Prepare for level-up" not in html


def test_xianxia_hides_dnd_spellcasting_read_and_session_affordances(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    session_response = client.get("/campaigns/linden-pass/session/character?character=arden-march&page=spells")

    assert read_response.status_code == 200
    read_html = read_response.get_data(as_text=True)
    assert "At a glance" in read_html
    assert "?page=spellcasting" not in read_html
    assert "/spellcasting/" not in read_html
    assert "Spell slots" not in read_html
    assert "Message" not in read_html

    assert session_response.status_code == 200
    session_html = session_response.get_data(as_text=True)
    assert "Overview" in session_html
    assert "Spell slots" not in session_html
    assert "page=spells" not in session_html
    assert "/spellcasting/" not in session_html


def test_xianxia_read_sheet_keeps_shared_controls_without_dnd_authoring(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["admin"]["email"], users["admin"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Controls" in html
    assert "Assignment controls" in html
    assert "Delete character" in html
    assert "Edit character" not in html
    assert "Level up" not in html
    assert "Prepare for level-up" not in html
    assert "?page=spellcasting" not in html


def test_xianxia_character_sheet_renders_and_links_xianxia_systems_entries(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
            }
        ]

    _write_campaign_config(app, _mutate_campaign)

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        service.ensure_builtin_library_seeded(DND_5E_SYSTEM_CODE)
        store.upsert_source(
            DND_5E_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            title="DND Impostor Xianxia Source",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.replace_entries_for_source(
            DND_5E_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            entry_types=["martial_art"],
            entries=[
                {
                    "entry_key": "dnd-5e|martial_art|xianxia-homebrew|heavenly-palm",
                    "entry_type": "martial_art",
                    "slug": "heavenly-palm",
                    "title": "DND Heavenly Palm",
                    "search_text": "heavenly palm dnd impostor",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"facet": "martial_art"},
                    "body": {},
                    "rendered_html": "<p>DND impostor palm body must not render.</p>",
                }
            ],
        )
        store.replace_entries_for_source(
            XIANXIA_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            entry_types=["martial_art", "rule"],
            entries=[
                {
                    "entry_key": "xianxia|martial_art|xianxia-homebrew|heavenly-palm",
                    "entry_type": "martial_art",
                    "slug": "heavenly-palm",
                    "title": "Heavenly Palm",
                    "search_text": "heavenly palm xianxia martial art",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"facet": "martial_art"},
                    "body": {},
                    "rendered_html": "<p>Xianxia palm body renders on the character sheet.</p>",
                },
                {
                    "entry_key": "xianxia|rule|xianxia-homebrew|dao-breathing",
                    "entry_type": "rule",
                    "slug": "dao-breathing",
                    "title": "Dao Breathing",
                    "search_text": "dao breathing xianxia rule",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"rule_key": "dao_breathing"},
                    "body": {},
                    "rendered_html": "<p>Dao Breathing rule text renders on the character sheet.</p>",
                },
            ],
        )
        heavenly_palm = service.get_entry_by_slug_for_campaign("linden-pass", "heavenly-palm")
        dao_breathing = service.get_entry_by_slug_for_campaign("linden-pass", "dao-breathing")
        assert heavenly_palm is not None
        assert heavenly_palm.library_slug == XIANXIA_SYSTEM_CODE
        assert dao_breathing is not None
        assert dao_breathing.library_slug == XIANXIA_SYSTEM_CODE

    def _mutate_character(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["classes"] = [
            {
                "row_id": "xianxia-row-1",
                "class_name": "Mortal Cultivator",
                "level": 0,
            }
        ]
        profile["class_level_text"] = "Mortal Cultivator"
        profile["class_ref"] = {}
        profile["subclass_ref"] = {}
        profile["species"] = ""
        profile["species_ref"] = {}
        profile["background"] = ""
        profile["background_ref"] = {}
        payload["profile"] = profile
        payload["spellcasting"] = {}
        payload["features"] = [
            {
                "id": "xianxia-martial-art-heavenly-palm",
                "name": "Heavenly Palm",
                "category": "custom_feature",
                "systems_ref": _systems_ref(heavenly_palm),
            },
            {
                "id": "xianxia-rule-dao-breathing",
                "name": "Dao Breathing",
                "category": "custom_feature",
                "systems_ref": _systems_ref(dao_breathing),
            },
        ]

    _write_character_definition(app, "arden-march", _mutate_character)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    sheet_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")
    entry_response = client.get("/campaigns/linden-pass/systems/entries/heavenly-palm")

    assert sheet_response.status_code == 200
    assert entry_response.status_code == 200
    html = sheet_response.get_data(as_text=True)
    entry_html = entry_response.get_data(as_text=True)

    assert 'href="/campaigns/linden-pass/systems/entries/heavenly-palm"' in html
    assert 'href="/campaigns/linden-pass/systems/entries/dao-breathing"' in html
    assert "Xianxia palm body renders on the character sheet." in html
    assert "Dao Breathing rule text renders on the character sheet." in html
    assert "DND Heavenly Palm" not in html
    assert "DND impostor palm body must not render." not in html
    assert "Heavenly Palm" in entry_html
    assert "Xianxia palm body renders on the character sheet." in entry_html
    assert "DND impostor palm body must not render." not in entry_html


def test_xianxia_generic_techniques_and_basic_actions_browse_search_and_link_from_sheet(
    app, client, sign_in, users
):
    def _mutate_campaign(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
            }
        ]

    _write_campaign_config(app, _mutate_campaign)

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        qi_blast = service.get_entry_by_slug_for_campaign("linden-pass", "qi-blast")
        throat_jab = service.get_entry_by_slug_for_campaign("linden-pass", "throat-jab")

        assert qi_blast is not None
        assert qi_blast.library_slug == XIANXIA_SYSTEM_CODE
        assert qi_blast.entry_type == "generic_technique"
        assert throat_jab is not None
        assert throat_jab.library_slug == XIANXIA_SYSTEM_CODE
        assert throat_jab.entry_type == "basic_action"

    def _mutate_character(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["classes"] = [
            {
                "row_id": "xianxia-row-1",
                "class_name": "Mortal Cultivator",
                "level": 0,
            }
        ]
        profile["class_level_text"] = "Mortal Cultivator"
        profile["class_ref"] = {}
        profile["subclass_ref"] = {}
        profile["species"] = ""
        profile["species_ref"] = {}
        profile["background"] = ""
        profile["background_ref"] = {}
        payload["profile"] = profile
        payload["spellcasting"] = {}
        payload["features"] = [
            {
                "id": "xianxia-generic-technique-qi-blast",
                "name": "Qi Blast",
                "category": "custom_feature",
                "systems_ref": _systems_ref(qi_blast),
            },
            {
                "id": "xianxia-basic-action-throat-jab",
                "name": "Throat Jab",
                "category": "custom_feature",
                "systems_ref": _systems_ref(throat_jab),
            },
        ]

    _write_character_definition(app, "arden-march", _mutate_character)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_response = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}"
    )
    generic_category_response = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/generic_technique"
    )
    basic_action_category_response = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/basic_action"
    )
    generic_search_response = client.get("/campaigns/linden-pass/systems/search?q=Qi+Blast")
    basic_action_search_response = client.get("/campaigns/linden-pass/systems/search?q=Throat+Jab")
    sheet_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=features")

    assert source_response.status_code == 200
    source_html = source_response.get_data(as_text=True)
    assert "Xianxia Homebrew" in source_html
    assert "Generic Techniques" in source_html
    assert "Basic Actions" in source_html
    assert (
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/generic_technique"
        in source_html
    )
    assert (
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/basic_action"
        in source_html
    )

    assert generic_category_response.status_code == 200
    generic_category_html = generic_category_response.get_data(as_text=True)
    assert "Xianxia Homebrew: Generic Techniques" in generic_category_html
    assert "Qi Blast" in generic_category_html
    assert "/campaigns/linden-pass/systems/entries/qi-blast" in generic_category_html

    assert basic_action_category_response.status_code == 200
    basic_action_category_html = basic_action_category_response.get_data(as_text=True)
    assert "Xianxia Homebrew: Basic Actions" in basic_action_category_html
    assert "Throat Jab" in basic_action_category_html
    assert "/campaigns/linden-pass/systems/entries/throat-jab" in basic_action_category_html

    assert generic_search_response.status_code == 200
    generic_search_html = generic_search_response.get_data(as_text=True)
    assert "Qi Blast" in generic_search_html
    assert "/campaigns/linden-pass/systems/entries/qi-blast" in generic_search_html

    assert basic_action_search_response.status_code == 200
    basic_action_search_html = basic_action_search_response.get_data(as_text=True)
    assert "Throat Jab" in basic_action_search_html
    assert "/campaigns/linden-pass/systems/entries/throat-jab" in basic_action_search_html

    assert sheet_response.status_code == 200
    sheet_html = sheet_response.get_data(as_text=True)
    assert 'href="/campaigns/linden-pass/systems/entries/qi-blast"' in sheet_html
    assert 'href="/campaigns/linden-pass/systems/entries/throat-jab"' in sheet_html
    assert "Spend a point of Qi" in sheet_html
    assert "Insight Cost" in sheet_html
    assert "Basic Action Details" in sheet_html
    assert "1 Round" in sheet_html
    assert "?page=spellcasting" not in sheet_html


def test_xianxia_blocks_dnd_spellcasting_management_routes(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?q=message"
    )
    assert search_response.status_code == 404
    assert search_response.get_json()["message"] == app_module.DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE

    spell_add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        follow_redirects=False,
    )
    assert spell_add_response.status_code == 302
    assert spell_add_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    spell_update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/update",
        follow_redirects=False,
    )
    assert spell_update_response.status_code == 302
    assert spell_update_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    spell_remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        follow_redirects=False,
    )
    assert spell_remove_response.status_code == 302
    assert spell_remove_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    slot_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/spell-slots/1",
        follow_redirects=False,
    )
    assert slot_response.status_code == 302
    assert slot_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march")

    landing = client.get(spell_add_response.headers["Location"])
    assert app_module.DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE in landing.get_data(as_text=True)


def test_dnd5e_spellcasting_and_session_slots_remain_enabled_with_xianxia_policy_present(
    app, client, sign_in, users, get_character
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "DND-5E"
        payload["systems_library"] = "DND-5E"

    _write_campaign_config(app, _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?q=message"
    )

    assert search_response.status_code == 200
    assert (
        search_response.get_json()["message"]
        != app_module.DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE
    )

    record = get_character("arden-march")
    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/spell-slots/2",
        data={"expected_revision": record.state_record.revision, "used": 1},
        follow_redirects=False,
    )

    assert response.status_code == 302
    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 1


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
    assert "Open sheet edit view" in html
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
    assert "Active session" in html
    assert "Sheet edit view" in html
    assert "Back to character sheet" in html
    assert "Back to read mode" not in html
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
    assert "Active session" in html
    assert "Save pending changes" in html
    assert "Save vitals" not in html
    assert "Back to character sheet" in html
    assert "Back to read mode" not in html
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


def test_spellcasting_subpage_shows_supported_feat_spell_rows_as_read_only_sections(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-mage-hand", "title": "Mage Hand", "level": 0, "class_lists": {"TCE": ["Artificer"], "PHB": ["Wizard"]}},
            {"slug": "phb-spell-cure-wounds", "title": "Cure Wounds", "level": 1, "class_lists": {"TCE": ["Artificer"], "PHB": ["Cleric", "Druid"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Fighter 5"
        profile["classes"] = [{"class_name": "Fighter", "level": 5}]
        payload["profile"] = profile
        source_row_id = "feat-spell-source:artificer-initiate:species-feat-1"
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "class_rows": [],
            "source_rows": [
                {
                    "source_row_id": source_row_id,
                    "source_row_kind": "feat",
                    "title": "Artificer Initiate",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 12,
                    "spell_attack_bonus": 4,
                }
            ],
            "spells": [
                _spell_payload(
                    spell_entries["phb-spell-mage-hand"],
                    source="PHB",
                    mark="Cantrip",
                    is_bonus_known=True,
                    spell_source_row_id=source_row_id,
                    spell_source_row_kind="feat",
                    spell_source_row_title="Artificer Initiate",
                    spell_source_ability_key="int",
                    grant_source_label="Artificer Initiate",
                ),
                _spell_payload(
                    spell_entries["phb-spell-cure-wounds"],
                    source="PHB",
                    is_bonus_known=True,
                    spell_source_row_id=source_row_id,
                    spell_source_row_kind="feat",
                    spell_source_row_title="Artificer Initiate",
                    spell_source_ability_key="int",
                    grant_source_label="Artificer Initiate",
                    spell_access_type="free_cast",
                    spell_access_uses=1,
                    spell_access_reset_on="long_rest",
                ),
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Artificer Initiate" in html
    assert "Feat spells" in html
    assert "Intelligence spellcasting" in html
    assert "Save DC 12" in html
    assert "Attack +4" in html
    assert "Feature granted" in html
    assert "1 / Long Rest" in html
    assert "Feat-granted spells stay read-only here in this slice." in html
    assert "Prepare spell" not in html
    assert "Add spellbook spell" not in html
    assert "Remove cantrip" not in html


def test_spellcasting_subpage_can_manage_ritual_caster_ritual_book(app, client, sign_in, users):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-find-familiar", "title": "Find Familiar", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-alarm", "title": "Alarm", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    source_row_id = "feat-spell-source:phb-feat-ritual-caster:species-feat-1"

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Fighter 5"
        profile["classes"] = [{"class_name": "Fighter", "level": 5}]
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["int"] = {"score": 14, "modifier": 2, "save_bonus": 2}
        stats["ability_scores"] = ability_scores
        stats["proficiency_bonus"] = 3
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "ritual-caster-1",
                "name": "Ritual Caster",
                "category": "feat",
                "source": "PHB",
                "description_markdown": "",
                "activation_type": "passive",
                "systems_ref": {
                    "entry_key": "dnd-5e|feat|phb|ritual-caster",
                    "entry_type": "feat",
                    "title": "Ritual Caster",
                    "slug": "phb-feat-ritual-caster",
                    "source_id": "PHB",
                },
                "spell_manager": {
                    "source_row_id": source_row_id,
                    "source_row_kind": "feat",
                    "title": "Ritual Caster (Wizard)",
                    "mode": "ritual_book",
                    "spell_list_class_name": "Wizard",
                    "spellcasting_ability": "Intelligence",
                    "spellcasting_ability_key": "int",
                    "max_spell_level_formula": "ritual_caster_half_level_rounded_up",
                },
            }
        ]
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "class_rows": [],
            "source_rows": [],
            "spells": [],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Ritual Caster (Wizard)" in page_html
    assert "Ritual book" in page_html
    assert "Add ritual spell" in page_html
    assert "No spells recorded yet for this class row." in page_html

    search_response = client.get(
        f"/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=ritual_book&q=detect&target_class_row_id={source_row_id}"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching ritual spells."
    assert [result["entry_slug"] for result in search_payload["results"]] == ["phb-spell-detect-magic"]

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "ritual_book",
            "selected_value": "phb-spell-detect-magic",
            "target_class_row_id": source_row_id,
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    spells_by_name = {spell["name"]: spell for spell in updated_definition["spellcasting"]["spells"]}
    assert spells_by_name["Detect Magic"]["mark"] == "Ritual Book"
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"]["spell_source_row_id"] == source_row_id

    updated_page = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    updated_html = updated_page.get_data(as_text=True)
    assert "Detect Magic" in updated_html
    assert "Ritual Book" in updated_html
    assert "Remove from ritual book" in updated_html

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": f"feat:{source_row_id}::phb-spell-detect-magic",
            "target_class_row_id": source_row_id,
        },
        follow_redirects=False,
    )
    assert remove_response.status_code == 302

    removed_definition = _read_character_definition(app, "arden-march")
    assert removed_definition["spellcasting"]["spells"] == []
    removed_page = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    removed_html = removed_page.get_data(as_text=True)
    assert "Ritual Caster (Wizard)" in removed_html
    assert "Add ritual spell" in removed_html
    assert "No spells recorded yet for this class row." in removed_html


def test_spellcasting_subpage_can_manage_campaign_feature_ritual_book(app, client, sign_in, users):
    _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-alarm", "title": "Alarm", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-find-familiar", "title": "Find Familiar", "level": 1, "class_lists": {"PHB": ["Wizard"]}, "ritual": True},
            {"slug": "phb-spell-magic-missile", "title": "Magic Missile", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    source_row_id = "feature-spell-source:mechanics-harbor-ritual-book:mechanics-harbor-ritual-book"

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Fighter 5"
        profile["classes"] = [{"class_name": "Fighter", "level": 5}]
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["int"] = {"score": 14, "modifier": 2, "save_bonus": 2}
        stats["ability_scores"] = ability_scores
        stats["proficiency_bonus"] = 3
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "harbor-ritual-book-1",
                "name": "Harbor Ritual Book",
                "category": "custom_feature",
                "source": "Campaign",
                "description_markdown": "",
                "activation_type": "special",
                "page_ref": "mechanics/harbor-ritual-book",
                "spell_manager": {
                    "source_row_id": source_row_id,
                    "source_row_kind": "feature",
                    "title": "Harbor Ritual Book",
                    "mode": "ritual_book",
                    "spell_list_class_name": "Wizard",
                    "spellcasting_ability": "Intelligence",
                    "spellcasting_ability_key": "int",
                    "max_spell_level_formula": "ritual_caster_half_level_rounded_up",
                },
            }
        ]
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "class_rows": [],
            "source_rows": [],
            "spells": [],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Harbor Ritual Book" in page_html
    assert "Ritual book" in page_html
    assert "Add ritual spell" in page_html

    search_response = client.get(
        f"/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search?kind=ritual_book&q=alarm&target_class_row_id={source_row_id}"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching ritual spells."
    assert [result["entry_slug"] for result in search_payload["results"]] == ["phb-spell-alarm"]

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "ritual_book",
            "selected_value": "phb-spell-alarm",
            "target_class_row_id": source_row_id,
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    spells_by_name = {spell["name"]: spell for spell in updated_definition["spellcasting"]["spells"]}
    assert spells_by_name["Alarm"]["mark"] == "Ritual Book"
    assert spells_by_name["Alarm"]["spell_source_row_id"] == source_row_id

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/remove",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "spell_key": f"feature:{source_row_id}::phb-spell-alarm",
            "target_class_row_id": source_row_id,
        },
        follow_redirects=False,
    )
    assert remove_response.status_code == 302

    removed_definition = _read_character_definition(app, "arden-march")
    assert removed_definition["spellcasting"]["spells"] == []


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

    session_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=spellcasting")
    assert session_response.status_code == 200
    assert "Always prepared" in session_response.get_data(as_text=True)

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
    bless = next(spell for spell in updated_spells if spell.get("name") == "Bless")
    assert detect_magic["mark"] == "Prepared"
    assert bless["is_always_prepared"] is True

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


def test_spellcasting_subpage_groups_multiclass_rows_and_allows_same_spell_on_another_row(
    app, client, sign_in, users
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
            entry_types=["class"],
            entries=[
                {
                    "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                    "entry_type": "class",
                    "slug": "phb-class-wizard",
                    "title": "Wizard",
                    "source_page": "100",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "wizard class",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "hit_die": {"faces": 6},
                        "spellcasting_ability": "int",
                        "caster_progression": "full",
                        "spells_known_progression_fixed": [6],
                    },
                    "body": {},
                    "rendered_html": "<p>Wizard.</p>",
                },
                {
                    "entry_key": "dnd-5e|class|phb|phb-class-cleric",
                    "entry_type": "class",
                    "slug": "phb-class-cleric",
                    "title": "Cleric",
                    "source_page": "101",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "cleric class",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "hit_die": {"faces": 8},
                        "spellcasting_ability": "wis",
                        "caster_progression": "full",
                        "prepared_spells": "level + wis",
                    },
                    "body": {},
                    "rendered_html": "<p>Cleric.</p>",
                },
            ],
        )
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard", "Cleric"]}},
            {"slug": "phb-spell-bless", "title": "Bless", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Wizard 3 / Cleric 3"
        profile["classes"] = [
            {
                "row_id": "class-row-1",
                "class_name": "Wizard",
                "level": 3,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                    "entry_type": "class",
                    "title": "Wizard",
                    "slug": "phb-class-wizard",
                    "source_id": "PHB",
                },
            },
            {
                "row_id": "class-row-2",
                "class_name": "Cleric",
                "level": 3,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|phb-class-cleric",
                    "entry_type": "class",
                    "title": "Cleric",
                    "slug": "phb-class-cleric",
                    "source_id": "PHB",
                },
            },
        ]
        payload["profile"] = profile
        payload["source"] = {
            "source_path": "builder://native-multiclass",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Builder",
            "imported_at": "2026-04-08T00:00:00Z",
            "parse_warnings": [],
        }
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 3},
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Wizard",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                        "entry_type": "class",
                        "title": "Wizard",
                        "slug": "phb-class-wizard",
                        "source_id": "PHB",
                    },
                    "level": 3,
                    "caster_progression": "full",
                    "spell_mode": "wizard",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 14,
                    "spell_attack_bonus": 6,
                },
                {
                    "class_row_id": "class-row-2",
                    "class_name": "Cleric",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-cleric",
                        "entry_type": "class",
                        "title": "Cleric",
                        "slug": "phb-class-cleric",
                        "source_id": "PHB",
                    },
                    "level": 3,
                    "caster_progression": "full",
                    "spell_mode": "prepared",
                    "spellcasting_ability": "Wisdom",
                    "spell_save_dc": 13,
                    "spell_attack_bonus": 5,
                },
            ],
            "spells": [
                {
                    **_spell_payload(spell_entries["phb-spell-detect-magic"], source="Wizard", mark="O"),
                    "class_row_id": "class-row-1",
                },
                {
                    **_spell_payload(spell_entries["phb-spell-bless"], source="Cleric", mark="P"),
                    "class_row_id": "class-row-2",
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Multiclass Spellcasting" in page_html
    assert "Shared spell slots" in page_html
    assert "Wizard 3" in page_html
    assert "Cleric 3" in page_html

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search"
        "?kind=spell&q=detect&target_class_row_id=class-row-2"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching spells."
    assert [result["entry_slug"] for result in search_payload["results"]] == ["phb-spell-detect-magic"]

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/add",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "read",
            "page": "spellcasting",
            "kind": "spell",
            "selected_value": "phb-spell-detect-magic",
            "target_class_row_id": "class-row-2",
        },
        follow_redirects=False,
    )
    assert add_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    detect_magic_rows = [
        str(spell.get("class_row_id") or "").strip()
        for spell in list((updated_definition.get("spellcasting") or {}).get("spells") or [])
        if str(spell.get("name") or "").strip() == "Detect Magic"
    ]
    assert detect_magic_rows == ["class-row-1", "class-row-2"]


def test_spell_management_search_uses_wizard_list_for_arcane_trickster_rows(app, client, sign_in, users):
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
            entry_types=["class"],
            entries=[
                {
                    "entry_key": "dnd-5e|class|phb|phb-class-rogue",
                    "entry_type": "class",
                    "slug": "phb-class-rogue",
                    "title": "Rogue",
                    "source_page": "101",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "rogue class",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "hit_die": {"faces": 8},
                        "subclass_title": "Roguish Archetype",
                    },
                    "body": {},
                    "rendered_html": "<p>Rogue.</p>",
                },
            ],
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["subclass"],
            entries=[
                {
                    "entry_key": "dnd-5e|subclass|phb|phb-subclass-arcane-trickster",
                    "entry_type": "subclass",
                    "slug": "phb-subclass-arcane-trickster",
                    "title": "Arcane Trickster",
                    "source_page": "98",
                    "source_path": "data/class/class-phb.json",
                    "search_text": "arcane trickster rogue subclass",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "class_name": "Rogue",
                        "class_source": "PHB",
                    },
                    "body": {},
                    "rendered_html": "<p>Arcane Trickster.</p>",
                },
            ],
        )
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-bless", "title": "Bless", "level": 1, "class_lists": {"PHB": ["Cleric"]}},
            {"slug": "phb-spell-mage-hand", "title": "Mage Hand", "level": 0, "class_lists": {"PHB": ["Wizard"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Rogue 3"
        profile["class_ref"] = {
            "entry_key": "dnd-5e|class|phb|phb-class-rogue",
            "entry_type": "class",
            "title": "Rogue",
            "slug": "phb-class-rogue",
            "source_id": "PHB",
        }
        profile["subclass_ref"] = {
            "entry_key": "dnd-5e|subclass|phb|phb-subclass-arcane-trickster",
            "entry_type": "subclass",
            "title": "Arcane Trickster",
            "slug": "phb-subclass-arcane-trickster",
            "source_id": "PHB",
        }
        profile["classes"] = [
            {
                "row_id": "class-row-1",
                "class_name": "Rogue",
                "subclass_name": "Arcane Trickster",
                "level": 3,
                "systems_ref": dict(profile["class_ref"]),
                "subclass_ref": dict(profile["subclass_ref"]),
            }
        ]
        payload["profile"] = profile
        payload["source"] = {
            "source_path": "builder://native-arcane-trickster",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Builder",
            "imported_at": "2026-04-09T00:00:00Z",
            "parse_warnings": [],
        }
        payload["spellcasting"] = {
            "spellcasting_class": "Rogue",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 13,
            "spell_attack_bonus": 5,
            "slot_progression": [
                {"level": 1, "max_slots": 2},
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Rogue",
                    "spell_list_class_name": "Wizard",
                    "class_ref": dict(profile["class_ref"]),
                    "level": 3,
                    "caster_progression": "1/3",
                    "spell_mode": "known",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 13,
                    "spell_attack_bonus": 5,
                }
            ],
            "spells": [
                {
                    **_spell_payload(spell_entries["phb-spell-mage-hand"], source="Rogue", mark="Cantrip"),
                    "class_row_id": "class-row-1",
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    search_response = client.get(
        "/campaigns/linden-pass/characters/arden-march/spellcasting/spells/search"
        "?kind=spell&q=detect&target_class_row_id=class-row-1"
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching spells."
    assert [result["entry_slug"] for result in search_payload["results"]] == ["phb-spell-detect-magic"]


def test_spellcasting_subpage_shows_and_updates_separate_slot_pools_for_wizard_warlock_multiclass(
    app, client, sign_in, users
):
    spell_entries = _seed_systems_spell_entries(
        app,
        [
            {"slug": "phb-spell-detect-magic", "title": "Detect Magic", "level": 1, "class_lists": {"PHB": ["Wizard"]}},
            {"slug": "phb-spell-hex", "title": "Hex", "level": 1, "class_lists": {"PHB": ["Warlock"]}},
        ],
    )

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Wizard 3 / Warlock 2"
        profile["classes"] = [
            {
                "row_id": "class-row-1",
                "class_name": "Wizard",
                "level": 3,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                    "entry_type": "class",
                    "title": "Wizard",
                    "slug": "phb-class-wizard",
                    "source_id": "PHB",
                },
            },
            {
                "row_id": "class-row-2",
                "class_name": "Warlock",
                "level": 2,
                "systems_ref": {
                    "entry_key": "dnd-5e|class|phb|phb-class-warlock",
                    "entry_type": "class",
                    "title": "Warlock",
                    "slug": "phb-class-warlock",
                    "source_id": "PHB",
                },
            },
        ]
        payload["profile"] = profile
        payload["source"] = {
            "source_path": "builder://native-multiclass",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Builder",
            "imported_at": "2026-04-09T00:00:00Z",
            "parse_warnings": [],
        }
        payload["spellcasting"] = {
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "slot_lanes": [
                {
                    "id": "class-row-1-slots",
                    "title": "Wizard spell slots",
                    "shared": False,
                    "row_ids": ["class-row-1"],
                    "slot_progression": [
                        {"level": 1, "max_slots": 4},
                        {"level": 2, "max_slots": 2},
                    ],
                },
                {
                    "id": "class-row-2-slots",
                    "title": "Warlock Pact Magic slots",
                    "shared": False,
                    "row_ids": ["class-row-2"],
                    "slot_progression": [
                        {"level": 1, "max_slots": 2},
                    ],
                },
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Wizard",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-wizard",
                        "entry_type": "class",
                        "title": "Wizard",
                        "slug": "phb-class-wizard",
                        "source_id": "PHB",
                    },
                    "level": 3,
                    "caster_progression": "full",
                    "spell_mode": "wizard",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 14,
                    "spell_attack_bonus": 6,
                    "slot_lane_id": "class-row-1-slots",
                },
                {
                    "class_row_id": "class-row-2",
                    "class_name": "Warlock",
                    "class_ref": {
                        "entry_key": "dnd-5e|class|phb|phb-class-warlock",
                        "entry_type": "class",
                        "title": "Warlock",
                        "slug": "phb-class-warlock",
                        "source_id": "PHB",
                    },
                    "level": 2,
                    "caster_progression": "pact",
                    "spell_mode": "known",
                    "spellcasting_ability": "Charisma",
                    "spell_save_dc": 13,
                    "spell_attack_bonus": 5,
                    "slot_lane_id": "class-row-2-slots",
                },
            ],
            "spells": [
                {
                    **_spell_payload(spell_entries["phb-spell-detect-magic"], source="Wizard", mark="O"),
                    "class_row_id": "class-row-1",
                },
                {
                    **_spell_payload(spell_entries["phb-spell-hex"], source="Warlock", mark="Known"),
                    "class_row_id": "class-row-2",
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    page_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Spell slot pools are shown below" in page_html
    assert "Wizard spell slots" in page_html
    assert "Warlock Pact Magic slots" in page_html

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/spell-slots/1",
        data={
            "expected_revision": str(_character_state_revision(app, "arden-march")),
            "mode": "session",
            "page": "spellcasting",
            "slot_lane_id": "class-row-2-slots",
            "used": "1",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302

    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", "arden-march")
        assert record is not None
        wizard_slot = next(
            slot
            for slot in list(record.state_record.state.get("spell_slots") or [])
            if str(slot.get("slot_lane_id") or "") == "class-row-1-slots"
            and int(slot.get("level") or 0) == 1
        )
        warlock_slot = next(
            slot
            for slot in list(record.state_record.state.get("spell_slots") or [])
            if str(slot.get("slot_lane_id") or "") == "class-row-2-slots"
            and int(slot.get("level") or 0) == 1
        )
        assert wizard_slot["used"] == 0
        assert warlock_slot["used"] == 1


def test_dm_controls_subpage_shows_management_controls(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=controls")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Controls" in html
    assert "?page=controls" in html
    assert "Player controls" in html
    assert "main character sheet edit view" in html
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
    assert "main character sheet edit view" in html
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


def test_inventory_subpage_shows_direct_remove_controls_only_to_editable_users(
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
            "name": "Dock Ledger",
            "quantity": "1",
            "weight": "",
            "notes": "Tracked on the inventory page.",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    owner_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    owner_html = owner_response.get_data(as_text=True)

    assert owner_response.status_code == 200
    assert "Dock Ledger" in owner_html
    assert "Remove from inventory" in owner_html
    assert "Tracked inventory rows can be removed directly here." in owner_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    read_only_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    read_only_html = read_only_response.get_data(as_text=True)

    assert read_only_response.status_code == 200
    assert "Dock Ledger" in read_only_html
    assert "Remove from inventory" not in read_only_html
    assert "Tracked inventory rows can be removed directly here." not in read_only_html


def test_imported_inventory_rows_can_be_removed_from_inventory_page(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    inventory_html = inventory_response.get_data(as_text=True)

    assert inventory_response.status_code == 200
    assert "Backpack" in inventory_html
    assert "Remove from inventory" in inventory_html

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/backpack-5/remove",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "inventory",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    updated_definition = _read_character_definition(app, "arden-march")
    assert "Backpack" not in {str(item.get("name") or "") for item in list(updated_definition.get("equipment_catalog") or [])}

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        inventory_names = {
            str(item.get("name") or "")
            for item in list((record.state_record.state or {}).get("inventory") or [])
        }
        assert "Backpack" not in inventory_names


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


def test_equipment_subpage_filters_inventory_only_rows_and_only_shows_attunement_for_required_magic_items(
    app, client, sign_in, users
):
    boots_entry = _seed_systems_item_entry(
        app,
        slug="phb-item-boots-of-elvenkind",
        title="Boots of Elvenkind",
        metadata={"weight": 1, "rarity": "uncommon"},
    )
    compass_entry = _seed_systems_item_entry(
        app,
        slug="phb-item-stormglass-compass",
        title="Stormglass Compass",
        metadata={"weight": 1, "rarity": "rare", "attunement": "requires attunement"},
    )

    def _mutate_definition(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        equipment_catalog[2] = {
            **dict(equipment_catalog[2]),
            "name": "Boots of Elvenkind",
            "weight": "1 lb.",
            "systems_ref": _systems_ref(boots_entry),
            "is_equipped": False,
            "is_attuned": False,
        }
        equipment_catalog[4] = {
            **dict(equipment_catalog[4]),
            "name": "Stormglass Compass",
            "weight": "1 lb.",
            "systems_ref": _systems_ref(compass_entry),
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        inventory[2] = {
            **dict(inventory[2]),
            "name": "Boots of Elvenkind",
            "weight": "1 lb.",
            "is_equipped": False,
            "is_attuned": False,
        }
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
    html = page_response.get_data(as_text=True)
    assert "Light Crossbow" in html
    assert "Quarterstaff" in html
    assert "Boots of Elvenkind" in html
    assert "Stormglass Compass" in html
    assert "Courier Satchel" not in html
    assert "Crossbow Bolts" not in html
    assert "Chalk" not in html
    assert html.count("Save equipment state") == 4
    assert html.count('name="weapon_wield_mode"') == 2
    assert html.count('name="is_equipped"') == 2
    assert html.count('name="is_attuned"') == 1
    assert "Main Hand" in html
    assert "Off Hand" in html
    assert "Two-Handed" in html
    assert "Use attunement only when the item's rules call for it." not in html


def test_equipment_state_update_rejects_inventory_only_rows(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

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
        assert definition_item.get("is_equipped") is not True
        assert definition_item.get("is_attuned") is not True
        assert state_item.get("is_equipped") is not True
        assert state_item.get("is_attuned") is not True
        assert record.state_record.state["attunement"]["attuned_item_refs"] == []


def test_equipment_state_update_preserves_three_item_attunement_limit_for_qualifying_items(
    app, client, sign_in, users
):
    item_ids = ["light-crossbow-1", "quarterstaff-2", "satchel-3", "crossbow-bolts-4"]
    entries = [
        _seed_systems_item_entry(
            app,
            slug=f"phb-item-attuned-relic-{index}",
            title=f"Attuned Relic {index}",
            metadata={"weight": 1, "rarity": "rare", "attunement": "requires attunement"},
        )
        for index in range(1, 5)
    ]

    def _mutate_definition(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, entry in enumerate(entries):
            equipment_catalog[index] = {
                **dict(equipment_catalog[index]),
                "name": f"Attuned Relic {index + 1}",
                "weight": "1 lb.",
                "systems_ref": _systems_ref(entry),
                "is_equipped": index < 3,
                "is_attuned": index < 3,
            }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index in range(4):
            inventory[index] = {
                **dict(inventory[index]),
                "name": f"Attuned Relic {index + 1}",
                "weight": "1 lb.",
                "is_equipped": index < 3,
                "is_attuned": index < 3,
            }
        payload["inventory"] = inventory
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": item_ids[:3]}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/crossbow-bolts-4/state",
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

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "crossbow-bolts-4"
        )
        state_item = next(
            item
            for item in list(record.state_record.state.get("inventory") or [])
            if str(item.get("catalog_ref") or item.get("id") or "") == "crossbow-bolts-4"
        )
        assert definition_item["is_equipped"] is False
        assert definition_item["is_attuned"] is False
        assert state_item["is_equipped"] is False
        assert state_item["is_attuned"] is False
        assert record.state_record.state["attunement"]["attuned_item_refs"] == item_ids[:3]


def test_equipment_state_update_persists_weapon_wield_mode_for_weapon_rows(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    update_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/quarterstaff-2/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "weapon_wield_mode": "two-handed",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "quarterstaff-2"
        )
        state_item = next(
            item
            for item in list(record.state_record.state.get("inventory") or [])
            if str(item.get("catalog_ref") or item.get("id") or "") == "quarterstaff-2"
        )
        assert definition_item["weapon_wield_mode"] == "two-handed"
        assert definition_item["is_equipped"] is True
        assert state_item["weapon_wield_mode"] == "two-handed"
        assert state_item["is_equipped"] is True


def test_native_equipment_state_update_recalculates_attunement_gated_magic_weapon_attacks(
    app, client, sign_in, users
):
    entry = _seed_systems_item_entry(
        app,
        slug="phb-item-plus-one-light-crossbow",
        title="+1 Light Crossbow",
        metadata={"weight": 5, "base_item": "Light Crossbow|PHB", "attunement": "requires attunement"},
    )

    def _mutate_definition(payload: dict) -> None:
        source = dict(payload.get("source") or {})
        source["source_type"] = "native_character_builder"
        source["source_path"] = "builder://arden-march"
        source["imported_from"] = "In-app Native Level 5 Builder"
        payload["source"] = source

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        equipment_catalog[0] = {
            **dict(equipment_catalog[0]),
            "name": "+1 Light Crossbow",
            "weight": "5 lb.",
            "systems_ref": _systems_ref(entry),
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        inventory[0] = {
            **dict(inventory[0]),
            "name": "+1 Light Crossbow",
            "weight": "5 lb.",
            "is_equipped": False,
            "is_attuned": False,
        }
        payload["inventory"] = inventory
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": []}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    equip_only_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/light-crossbow-1/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
        },
        follow_redirects=False,
    )

    assert equip_only_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        attacks_by_name = {
            attack["name"]: attack
            for attack in list(record.definition.attacks or [])
        }
        assert attacks_by_name["+1 Light Crossbow"]["attack_bonus"] == 5
        assert attacks_by_name["+1 Light Crossbow"]["damage"] == "1d8+2 piercing"

    fully_active_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/light-crossbow-1/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
            "is_attuned": "1",
        },
        follow_redirects=False,
    )

    assert fully_active_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        attacks_by_name = {
            attack["name"]: attack
            for attack in list(record.definition.attacks or [])
        }
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "light-crossbow-1"
        )
        assert attacks_by_name["+1 Light Crossbow"]["attack_bonus"] == 6
        assert attacks_by_name["+1 Light Crossbow"]["damage"] == "1d8+3 piercing"
        assert definition_item["is_equipped"] is True
        assert definition_item["is_attuned"] is True
        assert record.state_record.state["attunement"]["attuned_item_refs"] == ["light-crossbow-1"]


def test_native_equipment_state_update_recalculates_medium_armor_master_armor_class(
    app, client, sign_in, users
):
    def _mutate_definition(payload: dict) -> None:
        payload["source"] = {
            "source_type": "native_character_builder",
            "source_path": "builder://arden-march",
            "imported_from": "In-app Native Level 5 Builder",
        }
        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
        stats["ability_scores"] = ability_scores
        stats["armor_class"] = 13
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "medium-armor-master-1",
                "name": "Medium Armor Master",
                "category": "feat",
                "source": "PHB",
                "description_markdown": "",
                "activation_type": "passive",
                "tracker_ref": None,
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "phb-feat-medium-armor-master",
                    "title": "Medium Armor Master",
                    "source_id": "PHB",
                },
            }
        ]
        payload["equipment_catalog"] = [
            {
                "id": "scale-mail-1",
                "name": "Scale Mail",
                "default_quantity": 1,
                "weight": "45 lb.",
                "notes": "",
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "phb-item-scale-mail",
                    "title": "Scale Mail",
                    "source_id": "PHB",
                },
                "is_equipped": False,
                "is_attuned": False,
            }
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "id": "scale-mail-1",
                "catalog_ref": "scale-mail-1",
                "name": "Scale Mail",
                "quantity": 1,
                "weight": "45 lb.",
                "notes": "",
                "is_equipped": False,
                "is_attuned": False,
                "tags": [],
            }
        ]
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": []}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])

    equip_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/scale-mail-1/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
            "is_equipped": "1",
        },
        follow_redirects=False,
    )

    assert equip_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "scale-mail-1"
        )
        assert record.definition.stats["armor_class"] == 17
        assert definition_item["is_equipped"] is True

    unequip_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/equipment/scale-mail-1/state",
        data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read",
            "page": "equipment",
        },
        follow_redirects=False,
    )

    assert unequip_response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        definition_item = next(
            item
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "") == "scale-mail-1"
        )
        assert record.definition.stats["armor_class"] == 13
        assert definition_item["is_equipped"] is False


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
    assert "Remove from inventory" in html
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


def test_non_equipment_character_save_persists_recovered_equipment_links(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _seed_systems_item_entry(
        app,
        slug="phb-item-chain-mail",
        title="Chain Mail",
        metadata={"type": "HA", "ac": 16},
    )

    def _mutate_definition(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "chain-mail-1",
                "name": "Chain Mail",
                "default_quantity": 1,
                "weight": "55 lb.",
                "notes": "",
                "is_equipped": True,
                "systems_ref": None,
                "page_ref": None,
            }
        ]

    _write_character_definition(app, "arden-march", _mutate_definition)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    revision = _character_state_revision(app, "arden-march")

    response = client.post(
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

    assert response.status_code == 302

    definition = _read_character_definition(app, "arden-march")
    equipment_item = dict(definition["equipment_catalog"][0] or {})
    assert equipment_item["systems_ref"]["slug"] == "phb-item-chain-mail"
    assert equipment_item["systems_ref"]["title"] == "Chain Mail"
    assert equipment_item["systems_ref"]["entry_type"] == "item"
    assert equipment_item["systems_ref"]["source_id"] == "PHB"


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
    assert "Save pending changes" in html
    assert "Save personal details" not in html
    assert "Save note" not in html
    assert "At a glance" not in html


def test_editable_users_default_to_read_mode(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" not in html
    assert "Open sheet edit view" in html
    assert "Enter session mode" not in html
    assert "Back to character sheet" not in html


def test_session_active_widget_stays_on_quick_reference_only(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")
    features_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=features")

    assert quick_response.status_code == 200
    quick_html = quick_response.get_data(as_text=True)
    assert "Active session" in quick_html
    assert "Save pending changes" in quick_html
    assert "Save vitals" not in quick_html

    assert features_response.status_code == 200
    features_html = features_response.get_data(as_text=True)
    assert "Active session" not in features_html
    assert "Save pending changes" not in features_html


def test_sheet_edit_view_makes_first_pass_bounded_scope_explicit(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Keep first-pass Character-page edits here." in html
    assert "Help page for the full sheet-edit scope" in html
    assert "Character versus Session Character versus Combat boundary" in html
    assert 'href="/campaigns/linden-pass/help#characters"' in html
    assert "Open Character Help" in html
    assert "Sheet edit scope" not in html
    assert "Character-page sheet edit" not in html
    assert "Compatibility note" not in html
    assert "Player self-editing" not in html
    assert "Session-enabled editing" not in html
    assert "Combat-context editing" not in html


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
    assert "Open Character Help" in html
    assert 'href="/campaigns/linden-pass/help#characters"' in html
    assert '/campaigns/linden-pass/session/character?character=arden-march&amp;page=inventory' in html
    assert ">Open Session Character<" in html
    assert '/campaigns/linden-pass/combat?combatant=' in html
    assert ">Open Combat<" in html
    assert "Character-page sheet edit" not in html
    assert "Combat-context editing" not in html


def test_sheet_edit_view_explains_player_dm_and_admin_authority(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/help")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Who can use sheet edit view" in html
    assert "Current HP, temp HP, tracked resources, and spell slot usage" in html
    assert "Compatibility note" in html
    assert "Older Character-page links that still use ?mode=session" in html
    assert "Assigned player owners can use this same sheet edit view for their own characters" in html
    assert "DMs can open the same sheet edit view for characters they manage" in html
    assert "Owner assignment stays admin-only on Controls" in html
    assert "Observers and unassigned players stay on the standard character sheet" in html


def test_sheet_edit_view_exposes_cancel_and_unsaved_change_warning_copy(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Cancel pending changes" in html
    assert "stay local until you save or cancel them" in html
    assert "the browser will warn you" in html
    assert "Session Character, Combat, or another tab changes the sheet first" in html
    assert "The latest sheet was reloaded" in html
    assert "pending draft was restored locally for review" in html
    assert "Compare the refreshed sheet and save again when ready." in html
    assert "Session Character, Combat, or another tab may have changed nearby fields first" in html
    assert "nothing was auto-merged" in html
    assert "beforeunload" in html
    assert "Pending changes on this page. Save or cancel before you leave." in html


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

    assert html.count('class="attack-card"') == 2
    assert "Quarterstaff" in html
    assert "Hidden until equipped:" in html
    assert "Light Crossbow" in html


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

    assert html.count('class="attack-card"') == 2
    assert "Quarterstaff" in html
    assert "Hidden until equipped:" in html
    assert "Light Crossbow" in html


def test_quick_reference_uses_explicit_weapon_wield_mode_for_versatile_attack_rows(app, client, sign_in, users):
    def _set_quarterstaff_mode(payload: dict, mode: str) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for item in equipment_catalog:
            if str(item.get("id") or "").strip() == "quarterstaff-2":
                item["is_equipped"] = True
                if mode:
                    item["weapon_wield_mode"] = mode
                else:
                    item.pop("weapon_wield_mode", None)
        payload["equipment_catalog"] = equipment_catalog

    def _set_quarterstaff_state(payload: dict, mode: str) -> None:
        inventory = list(payload.get("inventory") or [])
        for item in inventory:
            if str(item.get("catalog_ref") or item.get("id") or "").strip() == "quarterstaff-2":
                item["is_equipped"] = True
                if mode:
                    item["weapon_wield_mode"] = mode
                else:
                    item.pop("weapon_wield_mode", None)
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", lambda payload: _set_quarterstaff_mode(payload, "main-hand"))
    _write_character_state(app, "arden-march", lambda payload: _set_quarterstaff_state(payload, "main-hand"))

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert campaign is not None
        assert record is not None
        main_hand_character = app_module.present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )
        assert "Quarterstaff (two-handed)" not in {attack["name"] for attack in main_hand_character["attacks"]}
        assert "Quarterstaff (two-handed)" in {attack["name"] for attack in main_hand_character["hidden_attacks"]}

    _write_character_definition(app, "arden-march", lambda payload: _set_quarterstaff_mode(payload, "two-handed"))
    _write_character_state(app, "arden-march", lambda payload: _set_quarterstaff_state(payload, "two-handed"))

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert campaign is not None
        assert record is not None
        two_handed_character = app_module.present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )
        assert "Quarterstaff (two-handed)" in {attack["name"] for attack in two_handed_character["attacks"]}


def test_quick_reference_tolerates_legacy_string_page_refs_when_linking_attacks_to_equipment(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "manual-item-staff-of-the-crescent-moon",
                "name": "Staff of the Crescent Moon",
                "default_quantity": 1,
                "weight": "4 lb.",
                "notes": "",
                "page_ref": "items/staff-of-the-crescent-moon",
            }
        ]
        payload["attacks"] = [
            {
                "id": "staff-of-the-crescent-moon",
                "name": "Staff of the Crescent Moon",
                "category": "weapon",
                "attack_bonus": 7,
                "damage": "1d6+4 bludgeoning",
                "damage_type": "bludgeoning",
                "notes": "A crescent-tipped staff used in close quarters.",
                "page_ref": "actions/staff-of-the-crescent-moon",
            }
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "catalog_ref": "manual-item-staff-of-the-crescent-moon",
                "name": "Staff of the Crescent Moon",
                "quantity": 1,
                "is_equipped": True,
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 1
    assert "Staff of the Crescent Moon" in html


def test_quick_reference_renders_shield_master_helper_row_without_placeholder_math(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "shield-1",
                "name": "Shield",
                "default_quantity": 1,
                "weight": "6 lb.",
                "notes": "",
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "phb-item-shield",
                    "title": "Shield",
                    "source_id": "PHB",
                },
            }
        ]
        payload["attacks"] = [
            {
                "id": "shield-shove-1",
                "name": "Shield Shove",
                "category": "special action",
                "attack_bonus": None,
                "damage": "",
                "damage_type": "",
                "notes": "Bonus action after taking the Attack action; Shield Master shove within 5 feet.",
                "mode_key": "feat:phb-feat-shield-master:shove",
                "equipment_refs": ["shield-1"],
            }
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "id": "shield-1",
                "catalog_ref": "shield-1",
                "name": "Shield",
                "quantity": 1,
                "weight": "6 lb.",
                "notes": "",
                "is_equipped": True,
                "is_attuned": False,
                "tags": [],
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 1
    assert "Shield Shove" in html
    assert "Special Action" in html
    assert "Bonus action after taking the Attack action; Shield Master shove within 5 feet." in html
    assert "to hit" not in html
    assert "<strong>--</strong>" not in html


def test_quick_reference_renders_grappler_helper_row_without_placeholder_math(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["attacks"] = [
            {
                "id": "pin-grappled-creature-1",
                "name": "Pin Grappled Creature",
                "category": "special action",
                "attack_bonus": None,
                "damage": "",
                "damage_type": "",
                "notes": "Action while grappling a creature; make another grapple check to pin both you and the target until the grapple ends.",
                "mode_key": "feat:phb-feat-grappler:pin",
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 1
    assert "Pin Grappled Creature" in html
    assert "Special Action" in html
    assert "Action while grappling a creature; make another grapple check to pin both you and the target until the grapple ends." in html
    assert "to hit" not in html
    assert "<strong>--</strong>" not in html


def test_quick_reference_renders_mounted_combatant_note_on_melee_attack_card(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["attacks"] = [
            {
                "id": "handaxe-1",
                "name": "Handaxe",
                "category": "melee weapon",
                "attack_bonus": 5,
                "damage": "1d6+3 slashing",
                "damage_type": "Slashing",
                "notes": "Mounted Combatant (while mounted, advantage against unmounted creatures smaller than your mount).",
            },
            {
                "id": "handaxe-thrown-2",
                "name": "Handaxe (thrown)",
                "category": "ranged weapon",
                "attack_bonus": 5,
                "damage": "1d6+3 slashing",
                "damage_type": "Slashing",
                "notes": "range 20/60.",
            },
        ]

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Handaxe" in html
    assert "Mounted Combatant (while mounted, advantage against unmounted creatures smaller than your mount)." in html
    assert "Handaxe (thrown)" in html
    assert "range 20/60." in html


def test_quick_reference_hides_shield_master_helper_row_until_shield_is_equipped(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "shield-1",
                "name": "Shield",
                "default_quantity": 1,
                "weight": "6 lb.",
                "notes": "",
                "systems_ref": {
                    "entry_type": "item",
                    "slug": "phb-item-shield",
                    "title": "Shield",
                    "source_id": "PHB",
                },
            }
        ]
        payload["attacks"] = [
            {
                "id": "shield-shove-1",
                "name": "Shield Shove",
                "category": "special action",
                "attack_bonus": None,
                "damage": "",
                "damage_type": "",
                "notes": "Bonus action after taking the Attack action; Shield Master shove within 5 feet.",
                "mode_key": "feat:phb-feat-shield-master:shove",
                "equipment_refs": ["shield-1"],
            }
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "id": "shield-1",
                "catalog_ref": "shield-1",
                "name": "Shield",
                "quantity": 1,
                "weight": "6 lb.",
                "notes": "",
                "is_equipped": False,
                "is_attuned": False,
                "tags": [],
            }
        ]

    _write_character_definition(app, "arden-march", _mutate)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert html.count('class="attack-card"') == 0
    assert "Hidden until equipped:" in html
    assert "Shield Shove" in html
    assert "Bonus action after taking the Attack action; Shield Master shove within 5 feet." not in html


def test_quick_reference_renders_shared_defensive_rules_section(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        stats = dict(payload.get("stats") or {})
        stats["defensive_state"] = {
            "armor_state": {
                "wearing_shield": True,
                "shield_bonus": 2,
                "equipped_armor_categories": ["heavy"],
                "stealth_disadvantage": True,
                "stealth_disadvantage_suppressed": False,
            },
            "rules": [
                {
                    "title": "Heavy Armor Master",
                    "active": True,
                    "condition": "Applies only while wearing heavy armor.",
                    "effects": [
                        {
                            "kind": "damage_mitigation",
                            "label": "Mitigation",
                            "summary": "Reduce nonmagical bludgeoning, piercing, and slashing damage from weapons by 3.",
                        }
                    ],
                },
                {
                    "title": "Shield Master",
                    "active": True,
                    "condition": "Applies only while a shield is equipped and you are not incapacitated.",
                    "effects": [
                        {
                            "kind": "saving_throw",
                            "label": "Dex saves",
                            "summary": "Add +2 to Dexterity saves against spells or other harmful effects that target only you.",
                        },
                        {
                            "kind": "reaction",
                            "label": "Reaction",
                            "summary": "If an effect lets you make a Dexterity save for half damage, you can use your reaction to take no damage on a success.",
                        },
                    ],
                },
            ],
        }
        payload["stats"] = stats

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Defensive rules" in html
    assert "Heavy Armor Master" in html
    assert "Mitigation:</strong> Reduce nonmagical bludgeoning, piercing, and slashing damage from weapons by 3." in html
    assert "Shield Master" in html
    assert "Dex saves:</strong> Add +2 to Dexterity saves against spells or other harmful effects that target only you." in html
    assert "Reaction:</strong> If an effect lets you make a Dexterity save for half damage, you can use your reaction to take no damage on a success." in html
    assert html.count(">Active<") >= 2


def test_quick_reference_renders_combat_reminders_and_mage_slayer_defense(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        payload["attacks"] = [
            {
                "id": "mace-1",
                "name": "Mace",
                "category": "melee weapon",
                "attack_bonus": 5,
                "damage": "1d6+3 bludgeoning",
                "damage_type": "Bludgeoning",
                "notes": "",
            },
            {
                "id": "rapier-1",
                "name": "Rapier",
                "category": "melee weapon",
                "attack_bonus": 5,
                "damage": "1d8+3 piercing",
                "damage_type": "Piercing",
                "notes": "",
            },
        ]
        stats = dict(payload.get("stats") or {})
        stats["attack_reminder_state"] = {
            "rules": [
                {
                    "title": "Mage Slayer",
                    "condition": "Use these reminders when a creature within 5 feet of you casts a spell or is concentrating on one.",
                    "attack_scope": {
                        "label": "Melee weapon attacks",
                        "categories": ["melee weapon"],
                    },
                    "effects": [
                        {
                            "kind": "reaction",
                            "label": "Spellcasting trigger",
                            "summary": "When a creature within 5 feet of you casts a spell, you can use your reaction to make a melee weapon attack against it.",
                        }
                    ],
                },
                {
                    "title": "Crusher",
                    "condition": "Use these reminders only when a visible attack deals bludgeoning damage.",
                    "attack_scope": {
                        "label": "Bludgeoning attacks",
                        "damage_types": ["Bludgeoning"],
                    },
                    "effects": [
                        {
                            "kind": "forced_movement",
                            "label": "Once per turn on hit",
                            "summary": "When you hit a creature with bludgeoning damage, you can move it 5 feet to an unoccupied space if it is no more than one size larger than you.",
                        }
                    ],
                },
                {
                    "title": "Piercer",
                    "condition": "Use these reminders only when a visible attack deals piercing damage.",
                    "attack_scope": {
                        "label": "Piercing attacks",
                        "damage_types": ["Piercing"],
                    },
                    "effects": [
                        {
                            "kind": "damage_reroll",
                            "label": "Once per turn on hit",
                            "summary": "You can reroll one of the attack's damage dice.",
                        }
                    ],
                },
            ]
        }
        stats["defensive_state"] = {
            "armor_state": {},
            "rules": [
                {
                    "title": "Mage Slayer",
                    "active": True,
                    "condition": "Applies against spells cast by creatures within 5 feet of you.",
                    "effects": [
                        {
                            "kind": "saving_throw",
                            "label": "Spell saves",
                            "summary": "You have advantage on saving throws against spells cast by creatures within 5 feet of you.",
                        }
                    ],
                }
            ],
        }
        payload["stats"] = stats

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=read&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Combat reminders" in html
    assert "Mage Slayer" in html
    assert "Spellcasting trigger:</strong> When a creature within 5 feet of you casts a spell, you can use your reaction to make a melee weapon attack against it." in html
    assert "Crusher" in html
    assert "Eligible attacks: Mace" in html
    assert "Piercer" in html
    assert "Eligible attacks: Rapier" in html
    assert "Linked attacks" in html
    assert "Defensive rules" in html
    assert "Spell saves:</strong> You have advantage on saving throws against spells cast by creatures within 5 feet of you." in html


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


def test_character_sheet_recovers_missing_equipment_links_for_inventory_and_equipment_rows(
    app, client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    _seed_systems_item_entry(
        app,
        slug="phb-item-chain-mail",
        title="Chain Mail",
        metadata={"type": "HA", "ac": 16},
    )
    _seed_systems_item_entry(
        app,
        slug="phb-item-stormglass-compass",
        title="Stormglass Compass",
        metadata={"weight": 1, "rarity": "rare"},
    )

    def _mutate_definition(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "chain-mail-1",
                "name": "Chain Mail",
                "default_quantity": 1,
                "weight": "55 lb.",
                "notes": "",
                "is_equipped": True,
                "systems_ref": None,
            },
            {
                "id": "stormglass-compass-2",
                "name": "Stormglass Compass",
                "default_quantity": 1,
                "weight": "1 lb.",
                "notes": "",
                "page_ref": None,
                "systems_ref": None,
            },
        ]

    def _mutate_state(payload: dict) -> None:
        payload["inventory"] = [
            {
                "id": "chain-mail-1",
                "catalog_ref": "chain-mail-1",
                "name": "Chain Mail",
                "quantity": 1,
                "weight": "55 lb.",
                "is_equipped": True,
                "is_attuned": False,
                "charges_current": None,
                "charges_max": None,
                "notes": "",
                "tags": [],
            },
            {
                "id": "stormglass-compass-2",
                "catalog_ref": "stormglass-compass-2",
                "name": "Stormglass Compass",
                "quantity": 1,
                "weight": "1 lb.",
                "is_equipped": False,
                "is_attuned": False,
                "charges_current": None,
                "charges_max": None,
                "notes": "",
                "tags": [],
            },
        ]

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    inventory_response = client.get("/campaigns/linden-pass/characters/arden-march?page=inventory")
    equipment_response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")

    assert inventory_response.status_code == 200
    assert equipment_response.status_code == 200

    inventory_html = inventory_response.get_data(as_text=True)
    equipment_html = equipment_response.get_data(as_text=True)

    assert '/campaigns/linden-pass/systems/entries/phb-item-stormglass-compass' in inventory_html
    assert '/campaigns/linden-pass/systems/entries/phb-item-chain-mail' in equipment_html


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
    assert "Modifier +1 | Save +4" in html
    assert "<p>Charisma</p>" in html
    assert "Modifier +4 | Save +10" in html

