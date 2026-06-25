from __future__ import annotations

import base64
from copy import deepcopy
import json
from datetime import timedelta
from pathlib import Path
import zipfile

import yaml

import player_wiki.api as api_module
from player_wiki.auth_store import AuthStore
from player_wiki.character_models import CharacterDefinition
from player_wiki.systems_importer import Dnd5eSystemsImporter
from player_wiki.systems_service import XIANXIA_HOMEBREW_SOURCE_ID
from player_wiki.xianxia_character_model import (
    XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION,
    XIANXIA_DEFINITION_FIELD_KEYS,
)


TINY_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def embedded_png_payload(
    filename: str = "session-article.png",
    *,
    alt_text: str | None = None,
    caption: str | None = None,
) -> dict[str, str | None]:
    payload: dict[str, str | None] = {
        "filename": filename,
        "media_type": "image/png",
        "data_base64": TINY_PNG_BASE64,
    }
    if alt_text is not None:
        payload["alt_text"] = alt_text
    if caption is not None:
        payload["caption"] = caption
    return payload


def api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def issue_api_token(app, user_email: str, *, label: str = "test-token") -> str:
    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_email(user_email)
        assert user is not None
        raw_token, _ = store.create_api_token(
            user.id,
            label=label,
            expires_in=timedelta(days=365),
        )
        return raw_token


def test_api_admin_view_as_uses_target_permissions_and_blocks_campaign_writes(client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    me_response = client.get("/api/v1/me")
    assert me_response.status_code == 200
    me_payload = me_response.get_json()
    assert me_payload["user"]["email"] == users["admin"]["email"]
    assert me_payload["view_as"]["can_view_as"] is True
    assert me_payload["view_as"]["active_user"] is None
    choice_emails = {choice["email"] for choice in me_payload["view_as"]["user_choices"]}
    assert users["party"]["email"] in choice_emails

    set_response = client.post(
        "/api/v1/me/view-as",
        json={"user_id": users["party"]["id"]},
    )
    assert set_response.status_code == 200
    set_payload = set_response.get_json()
    assert set_payload["view_as"]["active_user"]["email"] == users["party"]["email"]

    me_after = client.get("/api/v1/me")
    assert me_after.status_code == 200
    me_after_payload = me_after.get_json()
    assert me_after_payload["user"]["email"] == users["admin"]["email"]
    assert me_after_payload["view_as"]["active_user"]["email"] == users["party"]["email"]

    campaign_response = client.get("/api/v1/campaigns/linden-pass")
    assert campaign_response.status_code == 200
    campaign_payload = campaign_response.get_json()
    assert campaign_payload["role"] == "player"
    assert campaign_payload["permissions"]["can_manage_dm_content"] is False
    assert campaign_payload["visibility"]["dm_content"]["can_access"] is False

    blocked_dm_content = client.get("/api/v1/campaigns/linden-pass/dm-content")
    assert blocked_dm_content.status_code == 403

    blocked_write = client.post("/api/v1/campaigns/linden-pass/session/start")
    assert blocked_write.status_code == 403
    assert blocked_write.get_json()["error"]["code"] == "view_as_read_only"

    clear_response = client.delete("/api/v1/me/view-as")
    assert clear_response.status_code == 200
    assert clear_response.get_json()["view_as"]["active_user"] is None

    admin_dm_content = client.get("/api/v1/campaigns/linden-pass/dm-content")
    assert admin_dm_content.status_code == 200

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    forbidden_set = client.post(
        "/api/v1/me/view-as",
        json={"user_id": users["admin"]["id"]},
    )
    assert forbidden_set.status_code == 403

    player_me = client.get("/api/v1/me")
    assert player_me.status_code == 200
    assert player_me.get_json()["view_as"]["can_view_as"] is False


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def _advanced_editor_values(editor_context: dict) -> dict[str, str]:
    values: dict[str, str] = {}
    for group_name in ("proficiency_fields", "reference_fields", "stat_adjustment_fields"):
        for field in editor_context.get(group_name, []):
            field_name = str(field.get("name") or "").strip()
            if field_name:
                values[field_name] = str(field.get("value") or "")

    for row in editor_context.get("recoverable_penalty_rows", []):
        row_index = int(row.get("index") or 0)
        if row_index <= 0:
            continue
        values[f"recoverable_penalty_id_{row_index}"] = str(row.get("id") or "")
        values[f"recoverable_penalty_source_{row_index}"] = str(row.get("source") or "")
        values[f"recoverable_penalty_target_{row_index}"] = str(row.get("target") or "")
        values[f"recoverable_penalty_amount_{row_index}"] = str(row.get("amount") or "")
        values[f"recoverable_penalty_notes_{row_index}"] = str(row.get("notes") or "")

    for row in editor_context.get("feature_rows", []):
        row_index = int(row.get("index") or 0)
        if row_index <= 0:
            continue
        values[f"custom_feature_id_{row_index}"] = str(row.get("id") or "")
        values[f"custom_feature_name_{row_index}"] = str(row.get("name") or "")
        values[f"custom_feature_page_ref_{row_index}"] = str(row.get("page_ref") or "")
        values[f"custom_feature_activation_type_{row_index}"] = str(row.get("activation_type") or "")
        values[f"custom_feature_description_{row_index}"] = str(row.get("description_markdown") or "")
        values[f"custom_feature_resource_max_{row_index}"] = str(row.get("resource_max") or "")
        values[f"custom_feature_resource_reset_on_{row_index}"] = str(row.get("resource_reset_on") or "")
        for field in row.get("choice_fields", []):
            field_name = str(field.get("name") or "").strip()
            if field_name:
                values[field_name] = str(field.get("selected") or "")

    for row in editor_context.get("equipment_rows", []):
        row_index = int(row.get("index") or 0)
        if row_index <= 0:
            continue
        values[f"manual_item_id_{row_index}"] = str(row.get("id") or "")
        values[f"manual_item_name_{row_index}"] = str(row.get("name") or "")
        values[f"manual_item_page_ref_{row_index}"] = str(row.get("page_ref") or "")
        values[f"manual_item_quantity_{row_index}"] = str(row.get("quantity") or "")
        values[f"manual_item_weight_{row_index}"] = str(row.get("weight") or "")
        values[f"manual_item_notes_{row_index}"] = str(row.get("notes") or "")

    return values


def _write_campaign_config(app, mutator) -> None:
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with app.app_context():
        app.extensions["repository_store"].refresh()


def _configure_xianxia_campaign(app) -> None:
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    _write_campaign_config(app, _mutate)


def _valid_xianxia_create_data(name: str, *, slug: str = "") -> dict[str, str]:
    return {
        "name": name,
        "character_slug": slug,
        "attribute_str": "3",
        "attribute_dex": "0",
        "attribute_con": "3",
        "attribute_int": "0",
        "attribute_wis": "0",
        "attribute_cha": "0",
        "effort_basic": "3",
        "effort_weapon": "1",
        "effort_guns_explosive": "0",
        "effort_magic": "1",
        "effort_ultimate": "0",
        "energy_jing": "1",
        "energy_qi": "1",
        "energy_shen": "1",
        "trained_skill_1": "Fishing",
        "trained_skill_2": "Calligraphy",
        "trained_skill_3": "Tea Ceremony",
        "martial_art_1_slug": "demons-fist",
        "martial_art_1_rank": "initiate",
        "martial_art_2_slug": "heavenly-palm",
        "martial_art_2_rank": "initiate",
        "martial_art_3_slug": "taoist-blade",
        "martial_art_3_rank": "initiate",
    }


def _valid_xianxia_manual_import_data(name: str = "Imported Lotus", *, slug: str = "imported-lotus") -> dict[str, str]:
    return {
        "name": name,
        "character_slug": slug,
        "realm": "Immortal",
        "honor": "Majestic",
        "reputation": "Saffron court witness",
        "attribute_str": "9",
        "attribute_dex": "8",
        "attribute_con": "7",
        "attribute_int": "6",
        "attribute_wis": "5",
        "attribute_cha": "4",
        "effort_basic": "3",
        "effort_weapon": "4",
        "effort_guns_explosive": "5",
        "effort_magic": "6",
        "effort_ultimate": "7",
        "hp_max": "19",
        "stance_max": "17",
        "manual_armor_bonus": "4",
        "insight_available": "12",
        "insight_spent": "8",
        "energy_jing_max": "5",
        "energy_qi_max": "6",
        "energy_shen_max": "7",
        "yin_max": "9",
        "yang_max": "10",
        "dao_max": "3",
        "coin": "12",
        "supply": "3",
        "spirit_stones": "2",
        "trained_skills_text": "Tea Ceremony\nQi Sense | Raised by a wandering hermit\nSky Calling\nBlade Focus",
        "martial_art_1_slug": "heavenly-palm",
        "martial_art_1_rank": "Novice",
        "martial_art_1_teacher": "Elder Qing",
        "martial_art_1_breakthrough": "Cloud breakthrough",
        "martial_art_1_notes": "Linked branch",
        "martial_art_2_name": "Unlisted Fist",
        "martial_art_2_rank": "Apprentice",
        "martial_art_2_teacher": "Wandering monk",
        "martial_art_2_breakthrough": "Wind step",
        "martial_art_2_notes": "Manual record",
        "inventory_text": "Spirit rice | 3 | consumable, treasure | Emergency cache\nTravel cloak | 1 | tool | Weathered",
        "additional_notes_markdown": "Imported from the table sheet.",
        "player_notes_markdown": "Keep an eye on the spirit rice.",
    }


def _seed_systems_item_entry(
    app,
    *,
    slug: str = "phb-item-rope",
    title: str = "Rope",
    metadata: dict[str, object] | None = None,
    rendered_html: str | None = None,
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
                    "search_text": title.lower(),
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"weight": 1, **dict(metadata or {})},
                    "body": {},
                    "rendered_html": rendered_html if rendered_html is not None else f"<p>{title}.</p>",
                }
            ],
        )
        entry = app.extensions["systems_service"].get_entry_by_slug_for_campaign("linden-pass", slug)
        assert entry is not None
        return entry


def _seed_systems_spell_entry(
    app,
    *,
    slug: str = "phb-spell-api-detail",
    title: str = "API Detail Spell",
    metadata: dict[str, object] | None = None,
    rendered_html: str | None = None,
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
            for record in systems_store.list_entries_for_source("DND-5E", "PHB", entry_type="spell")
            if str(record.slug or "").strip() != slug
        ]
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=existing_entries
            + [
                {
                    "entry_key": f"dnd-5e|spell|phb|{slug}",
                    "entry_type": "spell",
                    "slug": slug,
                    "title": title,
                    "source_page": "220",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": title.lower(),
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"level": 1, "school": "evocation", **dict(metadata or {})},
                    "body": {},
                    "rendered_html": rendered_html if rendered_html is not None else f"<p>{title} spell detail.</p>",
                }
            ],
        )
        entry = app.extensions["systems_service"].get_entry_by_slug_for_campaign("linden-pass", slug)
        assert entry is not None
        return entry


def _systems_ref(entry) -> dict[str, str]:
    return {
        "entry_key": str(entry.entry_key or "").strip(),
        "entry_type": str(entry.entry_type or "").strip(),
        "title": str(entry.title or "").strip(),
        "slug": str(entry.slug or "").strip(),
        "source_id": str(entry.source_id or "").strip(),
    }


def _import_systems_goblin(app, tmp_path) -> tuple[str, str]:
    data_root = tmp_path / "api-systems-dnd5e-source"
    _write_json(
        data_root / "data/bestiary/bestiary-mm.json",
        {
            "monster": [
                {
                    "name": "Goblin",
                    "source": "MM",
                    "page": 166,
                    "size": ["S"],
                    "type": {"type": "humanoid", "tags": ["goblinoid"]},
                    "alignment": ["N", "E"],
                    "ac": [{"ac": 15, "from": ["leather armor", "shield"]}],
                    "hp": {"average": 7, "formula": "2d6"},
                    "speed": {"walk": 30},
                    "str": 8,
                    "dex": 14,
                    "con": 10,
                    "int": 10,
                    "wis": 8,
                    "cha": 8,
                    "action": [
                        {
                            "name": "Scimitar",
                            "entries": [
                                "{@atk mw} {@hit 4} to hit, reach 5 ft., one target. {@h}5 ({@damage 1d6 + 2}) slashing damage."
                            ],
                        }
                    ],
                }
            ]
        },
    )
    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MM", entry_types=["monster"])
        entry = next(
            item
            for item in app.extensions["systems_service"].list_monster_entries_for_campaign("linden-pass")
            if item.title == "Goblin"
        )
        return entry.entry_key, entry.slug


def _find_tracker_combatant(payload: dict[str, object], *, name: str | None = None, character_slug: str | None = None):
    for combatant in payload["tracker"]["combatants"]:
        if name is not None and combatant["name"] == name:
            return combatant
        if character_slug is not None and combatant["character_slug"] == character_slug:
            return combatant
    return None


def _build_systems_import_archive(tmp_path) -> bytes:
    data_root = tmp_path / "systems-import-archive"
    _write_json(
        data_root / "data/bestiary/bestiary-mm.json",
        {
            "monster": [
                {
                    "name": "Goblin",
                    "source": "MM",
                    "page": 166,
                    "size": ["S"],
                    "type": {"type": "humanoid", "tags": ["goblinoid"]},
                    "alignment": ["N", "E"],
                    "ac": [{"ac": 15, "from": ["leather armor", "shield"]}],
                    "hp": {"average": 7, "formula": "2d6"},
                    "speed": {"walk": 30},
                    "str": 8,
                    "dex": 14,
                    "con": 10,
                    "int": 10,
                    "wis": 8,
                    "cha": 8,
                    "action": [
                        {
                            "name": "Scimitar",
                            "entries": [
                                "{@atk mw} {@hit 4} to hit, reach 5 ft., one target. {@h}5 ({@damage 1d6 + 2}) slashing damage."
                            ],
                        }
                    ],
                }
            ]
        },
    )
    archive_path = tmp_path / "mm-import.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in data_root.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(data_root).as_posix())
    return archive_path.read_bytes()


def _build_unsafe_systems_import_archive(tmp_path) -> bytes:
    archive_path = tmp_path / "unsafe-systems-import.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../data/bestiary/bestiary-mm.json", "{}")
    return archive_path.read_bytes()


def test_api_me_and_campaigns_use_bearer_token_auth(client, app, users):
    token = issue_api_token(app, users["dm"]["email"], label="dm-api")

    me_response = client.get("/api/v1/me", headers=api_headers(token))

    assert me_response.status_code == 200
    me_payload = me_response.get_json()
    assert me_payload["ok"] is True
    assert me_payload["auth_source"] == "api_token"
    assert me_payload["user"]["email"] == users["dm"]["email"]
    assert me_payload["preferences"]["theme_key"] is not None
    assert me_payload["preferences"]["session_chat_order"] is not None
    assert me_payload["preferences"]["frontend_mode"] == "gen2"

    campaigns_response = client.get("/api/v1/campaigns", headers=api_headers(token))

    assert campaigns_response.status_code == 200
    campaigns_payload = campaigns_response.get_json()
    assert campaigns_payload["campaigns"][0]["campaign"]["slug"] == "linden-pass"
    assert campaigns_payload["campaigns"][0]["role"] == "dm"

    with app.app_context():
        store = AuthStore()
        token_record = store.get_active_api_token(token)
        assert token_record is not None
        store.revoke_api_token(token_record.id)

    revoked_response = client.get("/api/v1/me", headers=api_headers(token))

    assert revoked_response.status_code == 401
    assert revoked_response.get_json()["error"]["code"] == "auth_required"


def test_api_account_settings_reads_and_updates_user_preferences(client, app, users):
    token = issue_api_token(app, users["party"]["email"], label="account-settings-api")

    settings_response = client.get("/api/v1/me/settings", headers=api_headers(token))

    assert settings_response.status_code == 200
    settings_payload = settings_response.get_json()
    assert settings_payload["ok"] is True
    assert settings_payload["user"]["email"] == users["party"]["email"]
    assert settings_payload["preferences"] == {
        "theme_key": "parchment",
        "session_chat_order": "newest_first",
        "frontend_mode": "gen2",
    }
    assert [theme["key"] for theme in settings_payload["theme_presets"]] == [
        "parchment",
        "moonlit",
        "verdant",
        "ember",
    ]
    assert [choice["value"] for choice in settings_payload["session_chat_order_choices"]] == [
        "newest_first",
        "oldest_first",
    ]
    assert "frontend_mode_choices" not in settings_payload

    update_response = client.patch(
        "/api/v1/me/settings",
        headers=api_headers(token),
        json={"theme_key": "moonlit", "session_chat_order": "oldest_first"},
    )

    assert update_response.status_code == 200
    update_payload = update_response.get_json()
    assert update_payload["preferences"] == {
        "theme_key": "moonlit",
        "session_chat_order": "oldest_first",
        "frontend_mode": "gen2",
    }

    me_response = client.get("/api/v1/me", headers=api_headers(token))
    assert me_response.status_code == 200
    assert me_response.get_json()["preferences"] == update_payload["preferences"]

    with app.app_context():
        preferences = AuthStore().get_user_preferences(users["party"]["id"])
        assert preferences.theme_key == "moonlit"
        assert preferences.session_chat_order == "oldest_first"
        assert preferences.frontend_mode == "gen2"


def test_api_account_settings_rejects_invalid_preferences(client, app, users):
    token = issue_api_token(app, users["party"]["email"], label="account-settings-invalid-api")

    invalid_theme_response = client.patch(
        "/api/v1/me/settings",
        headers=api_headers(token),
        json={"theme_key": "bad-theme", "session_chat_order": "oldest_first"},
    )
    assert invalid_theme_response.status_code == 400
    assert invalid_theme_response.get_json()["error"]["code"] == "validation_error"
    assert invalid_theme_response.get_json()["error"]["message"] == "Choose a valid theme preset."

    invalid_order_response = client.patch(
        "/api/v1/me/settings",
        headers=api_headers(token),
        json={"theme_key": "moonlit", "session_chat_order": "sideways"},
    )
    assert invalid_order_response.status_code == 400
    assert invalid_order_response.get_json()["error"]["code"] == "validation_error"
    assert invalid_order_response.get_json()["error"]["message"] == "Choose a valid live session chat order."

    invalid_frontend_response = client.patch(
        "/api/v1/me/settings",
        headers=api_headers(token),
        json={"frontend_mode": "gen2"},
    )
    assert invalid_frontend_response.status_code == 400
    assert invalid_frontend_response.get_json()["error"]["code"] == "validation_error"
    assert (
        invalid_frontend_response.get_json()["error"]["message"]
        == "Preferred frontend selection is no longer available."
    )

    empty_response = client.patch("/api/v1/me/settings", headers=api_headers(token), json={})
    assert empty_response.status_code == 400
    assert empty_response.get_json()["error"]["message"] == "No account settings were provided."

    with app.app_context():
        preferences = AuthStore().get_user_preferences(users["party"]["id"])
        assert preferences.theme_key == "parchment"
        assert preferences.session_chat_order == "newest_first"
        assert preferences.frontend_mode == "gen2"


def test_api_admin_user_management_context_actions_and_permissions(client, app, users):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-gen2-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="admin-gen2-blocked-api")

    anonymous = client.get("/api/v1/admin")
    blocked = client.get("/api/v1/admin", headers=api_headers(owner_token))
    dashboard = client.get("/api/v1/admin", headers=api_headers(admin_token))

    assert anonymous.status_code == 401
    assert blocked.status_code == 403
    assert dashboard.status_code == 200
    dashboard_payload = dashboard.get_json()
    assert dashboard_payload["ok"] is True
    assert dashboard_payload["links"]["gen2_admin_url"] == "/app-next/admin"
    assert any(user["email"] == users["owner"]["email"] for user in dashboard_payload["user_cards"])
    assert any(choice["value"] == "user_invited" for choice in dashboard_payload["audit_event_type_choices"])

    invite_response = client.post(
        "/api/v1/admin/users/invite",
        headers=api_headers(admin_token),
        json={
            "email": "gen2-admin-api@example.com",
            "display_name": "Gen2 Admin API",
            "user_type": "standard",
        },
    )
    assert invite_response.status_code == 201
    invite_payload = invite_response.get_json()
    assert invite_payload["managed_user"]["email"] == "gen2-admin-api@example.com"
    assert "/invite/" in invite_payload["invite_url"]
    assert "/invite/" in invite_payload["message"]
    created_user_id = invite_payload["managed_user"]["id"]

    detail_response = client.get(f"/api/v1/admin/users/{created_user_id}", headers=api_headers(admin_token))
    detail_payload = detail_response.get_json()
    assert detail_response.status_code == 200
    assert detail_payload["managed_user"]["status"] == "invited"
    assert detail_payload["links"]["gen2_user_url"] == f"/app-next/admin/users/{created_user_id}"

    membership_response = client.post(
        f"/api/v1/admin/users/{created_user_id}/membership",
        headers=api_headers(admin_token),
        json={
            "campaign_slug": "linden-pass",
            "role": "player",
            "status": "active",
        },
    )
    assert membership_response.status_code == 200
    membership_payload = membership_response.get_json()
    assert any(
        membership["campaign_slug"] == "linden-pass"
        and membership["role"] == "player"
        and membership["status"] == "active"
        for membership in membership_payload["memberships"]
    )

    assignment_response = client.post(
        f"/api/v1/admin/users/{created_user_id}/assignment",
        headers=api_headers(admin_token),
        json={"character_ref": "linden-pass::selene-brook"},
    )
    assert assignment_response.status_code == 200
    assignment_payload = assignment_response.get_json()
    assert any(
        assignment["campaign_slug"] == "linden-pass"
        and assignment["character_slug"] == "selene-brook"
        and assignment["character_label"] == "Selene Brook"
        for assignment in assignment_payload["assignments"]
    )
    assert assignment_payload["message"] == (
        "Assigned Selene Brook in Echoes of the Alloy Coast to gen2-admin-api@example.com."
    )

    filtered_detail = client.get(
        f"/api/v1/admin/users/{created_user_id}?audit_q=selene-brook",
        headers=api_headers(admin_token),
    )
    filtered_payload = filtered_detail.get_json()
    assert filtered_detail.status_code == 200
    assert any(event["event_type"] == "character_assignment_created" for event in filtered_payload["recent_audit_events"])
    assert all("/invite/" not in event.get("details", "") for event in filtered_payload["recent_audit_events"])

    invite_again = client.post(
        f"/api/v1/admin/users/{created_user_id}/invite",
        headers=api_headers(admin_token),
    )
    assert invite_again.status_code == 200
    assert "/invite/" in invite_again.get_json()["invite_url"]

    reset_response = client.post(
        f"/api/v1/admin/users/{users['owner']['id']}/password-reset",
        headers=api_headers(admin_token),
    )
    assert reset_response.status_code == 200
    assert "/reset/" in reset_response.get_json()["reset_url"]

    disable_response = client.post(
        f"/api/v1/admin/users/{users['owner']['id']}/disable",
        headers=api_headers(admin_token),
    )
    assert disable_response.status_code == 200
    assert disable_response.get_json()["managed_user"]["status"] == "disabled"

    enable_response = client.post(
        f"/api/v1/admin/users/{users['owner']['id']}/enable",
        headers=api_headers(admin_token),
    )
    assert enable_response.status_code == 200
    assert enable_response.get_json()["managed_user"]["status"] == "active"

    delete_without_confirmation = client.delete(
        f"/api/v1/admin/users/{created_user_id}",
        headers=api_headers(admin_token),
        json={"confirm_email": ""},
    )
    assert delete_without_confirmation.status_code == 400

    delete_response = client.delete(
        f"/api/v1/admin/users/{created_user_id}",
        headers=api_headers(admin_token),
        json={"confirm_email": "gen2-admin-api@example.com"},
    )
    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["deleted_user"]["email"] == "gen2-admin-api@example.com"
    assert all(user["email"] != "gen2-admin-api@example.com" for user in delete_payload["user_cards"])

    with app.app_context():
        store = AuthStore()
        assert store.get_user_by_id(created_user_id) is None
        assert store.get_character_assignment("linden-pass", "selene-brook") is None


def test_api_campaign_help_returns_surface_guidance_for_viewer_access(client, app, users):
    player_token = issue_api_token(app, users["party"]["email"], label="campaign-help-player-api")

    response = client.get("/api/v1/campaigns/linden-pass/help", headers=api_headers(player_token))
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["campaign"]["slug"] == "linden-pass"
    assert payload["viewer_role_label"] == "Player"
    assert payload["campaign_system_label"] == "DND-5E"
    assert payload["links"]["flask_help_url"] == "/campaigns/linden-pass/help"
    assert payload["links"]["gen2_help_url"] == "/app-next/campaigns/linden-pass/help"

    surface_labels = [surface["label"] for surface in payload["surfaces"]]
    assert "Campaign Home" in surface_labels
    assert "Systems" in surface_labels
    assert "Session" in surface_labels
    assert "Combat" in surface_labels
    assert "DM Content" not in surface_labels
    assert "Control" not in surface_labels
    assert payload["available_surface_labels"] == surface_labels
    assert any("polling instead of websockets" in item for item in payload["cross_cutting_limits"])

    dm_token = issue_api_token(app, users["dm"]["email"], label="campaign-help-dm-api")
    dm_response = client.get("/api/v1/campaigns/linden-pass/help", headers=api_headers(dm_token))
    assert dm_response.status_code == 200
    dm_payload = dm_response.get_json()
    dm_surface_labels = [surface["label"] for surface in dm_payload["surfaces"]]
    assert "DM Content" in dm_surface_labels
    assert "Characters" in dm_surface_labels
    assert "Control" in dm_surface_labels
    dm_content = next(surface for surface in dm_payload["surfaces"] if surface["label"] == "DM Content")
    assert "Browser and API boundary" in [card["title"] for card in dm_content["guidance_cards"]]


def test_api_campaign_control_visibility_requires_manager_and_updates_scopes(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="campaign-control-dm-api")
    player_token = issue_api_token(app, users["party"]["email"], label="campaign-control-player-api")

    blocked_response = client.get("/api/v1/campaigns/linden-pass/control", headers=api_headers(player_token))
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    control_response = client.get("/api/v1/campaigns/linden-pass/control", headers=api_headers(dm_token))
    assert control_response.status_code == 200
    payload = control_response.get_json()
    assert payload["ok"] is True
    assert payload["campaign"]["slug"] == "linden-pass"
    assert payload["links"]["flask_control_url"] == "/campaigns/linden-pass/control-panel"
    assert payload["links"]["gen2_control_url"] == "/app-next/campaigns/linden-pass/control"
    rows_by_scope = {row["scope"]: row for row in payload["visibility_rows"]}
    assert rows_by_scope["campaign"]["selected_visibility"] == "public"
    assert rows_by_scope["characters"]["effective_visibility"] == "dm"
    assert payload["can_set_private_visibility"] is False

    private_response = client.patch(
        "/api/v1/campaigns/linden-pass/control/visibility",
        headers=api_headers(dm_token),
        json={"visibility": {"campaign": "private"}},
    )
    assert private_response.status_code == 400
    assert private_response.get_json()["error"]["message"] == "Private visibility is reserved for app admins."

    update_response = client.patch(
        "/api/v1/campaigns/linden-pass/control/visibility",
        headers=api_headers(dm_token),
        json={"visibility": {"campaign": "players", "wiki": "dm", "session": "players"}},
    )
    assert update_response.status_code == 200
    updated = update_response.get_json()
    assert set(updated["changed_scopes"]) == {"Campaign", "Player Wiki"}
    updated_rows = {row["scope"]: row for row in updated["visibility_rows"]}
    assert updated_rows["campaign"]["selected_visibility"] == "players"
    assert updated_rows["wiki"]["selected_visibility"] == "dm"
    assert updated_rows["session"]["effective_visibility"] == "players"
    assert "Updated visibility for" in updated["message"]

    with app.app_context():
        store = AuthStore()
        campaign_setting = store.get_campaign_visibility_setting("linden-pass", "campaign")
        wiki_setting = store.get_campaign_visibility_setting("linden-pass", "wiki")
        assert campaign_setting is not None
        assert campaign_setting.visibility == "players"
        assert wiki_setting is not None
        assert wiki_setting.visibility == "dm"


def test_api_player_wiki_read_endpoints_follow_visible_campaign_pages(client, app, users):
    player_token = issue_api_token(app, users["party"]["email"], label="player-wiki-api")
    note_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "notes"
        / "operations-brief.md"
    )
    note_path.write_text(
        (
            note_path.read_text(encoding="utf-8")
            + "\nLegacy route check: [Captain Lyra Vale](/campaigns/linden-pass/pages/npcs/captain-lyra-vale).\n"
            + "Already Gen2 check: [Harbor Row](/app-next/campaigns/linden-pass/pages/locations/harbor-row).\n"
        ),
        encoding="utf-8",
    )
    bestiary_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "content" / "bestiary"
    bestiary_dir.mkdir(parents=True, exist_ok=True)
    (bestiary_dir / "clockwork-eel.md").write_text(
        "\n".join(
            [
                "---",
                "title: Clockwork Eel",
                "section: Bestiary",
                "type: monster",
                "reveal_after_session: 2",
                "summary: A hostile construct encountered by the party.",
                "---",
                "",
                "The party documented this enemy after the harbor job.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with app.app_context():
        app.extensions["repository_store"].refresh()

    home_response = client.get("/api/v1/campaigns/linden-pass/wiki", headers=api_headers(player_token))
    assert home_response.status_code == 200
    home_payload = home_response.get_json()
    assert home_payload["ok"] is True
    assert home_payload["frontend_mode"] == "gen2"
    assert home_payload["can_view_wiki"] is True
    assert home_payload["overview_page"] is None
    assert home_payload["latest_session_summary"] is not None
    assert home_payload["latest_session_summary"]["title"] == "Session 2 - The Brass Vault"
    assert home_payload["latest_session_summary"]["route_slug"] == "sessions/session-2-the-brass-vault"
    assert home_payload["latest_session_summary"]["page_type"] == "session"
    assert all(section["section_name"] != "Overview" for section in home_payload["grouped_sections"])
    assert all(section["section_name"] != "Overview" for section in home_payload["section_navigation"])
    locations_group = next(section for section in home_payload["grouped_sections"] if section["section_name"] == "Locations")
    assert locations_group["href"] == "/app-next/campaigns/linden-pass/sections/locations"
    locations_nav_item = next(section for section in home_payload["section_navigation"] if section["section_name"] == "Locations")
    assert locations_nav_item == {
        "section_name": "Locations",
        "section_slug": "locations",
        "href": "/app-next/campaigns/linden-pass/sections/locations",
        "page_count": locations_group["page_count"],
    }
    bestiary_group = next(section for section in home_payload["grouped_sections"] if section["section_name"] == "Bestiary")
    assert bestiary_group["href"] == "/app-next/campaigns/linden-pass/sections/bestiary"
    bestiary_nav_item = next(section for section in home_payload["section_navigation"] if section["section_name"] == "Bestiary")
    assert bestiary_nav_item == {
        "section_name": "Bestiary",
        "section_slug": "bestiary",
        "href": "/app-next/campaigns/linden-pass/sections/bestiary",
        "page_count": 1,
    }

    search_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki?q=capt",
        headers=api_headers(player_token),
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["query"] == "capt"
    assert search_payload["overview_page"] is None
    assert search_payload["latest_session_summary"] is None
    assert search_payload["result_count"] >= 1
    search_pages = [
        page
        for section in search_payload["grouped_sections"]
        for page in section["pages"]
    ]
    captain = next(page for page in search_pages if page["page_ref"] == "npcs/captain-lyra-vale")
    assert captain["href"] == "/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale"
    assert "source_ref" not in captain
    assert "aliases" not in captain
    assert any(section["section_name"] == "Locations" for section in search_payload["section_navigation"])

    section_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/sections/locations",
        headers=api_headers(player_token),
    )
    assert section_response.status_code == 200
    section_payload = section_response.get_json()
    assert section_payload["section_name"] == "Locations"
    assert section_payload["frontend_mode"] == "gen2"
    assert section_payload["show_subsections"] is True
    assert section_payload["top_level_pages"][0]["title"] == "Port Meridian"
    assert section_payload["top_level_pages"][0]["href"].startswith("/app-next/campaigns/linden-pass/pages/")
    subsection_names = [group["subsection_name"] for group in section_payload["subsection_groups"]]
    assert "Civic and Institutional Sites" in subsection_names
    assert "Venues and Residences" in subsection_names
    assert any(section["section_slug"] == "locations" for section in section_payload["section_navigation"])
    bestiary_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/sections/bestiary",
        headers=api_headers(player_token),
    )
    assert bestiary_response.status_code == 200
    bestiary_payload = bestiary_response.get_json()
    assert bestiary_payload["section_name"] == "Bestiary"
    assert bestiary_payload["pages"][0]["title"] == "Clockwork Eel"
    assert bestiary_payload["pages"][0]["display_type"] == "monster"

    page_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale",
        headers=api_headers(player_token),
    )
    assert page_response.status_code == 200
    page_payload = page_response.get_json()
    assert page_payload["page"]["title"] == "Captain Lyra Vale"
    assert page_payload["page"]["image"]["url"] == "/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png"
    assert page_payload["page"]["image"]["caption"] == "Harbor watch captain and trusted ally of the crew."
    assert "Captain Lyra Vale coordinates inspections" in page_payload["page"]["body_html"]
    assert page_payload["links"]["flask_page_url"] == "/campaigns/linden-pass/pages/npcs/captain-lyra-vale"
    assert page_payload["links"]["campaign_url"] == "/app-next/campaigns/linden-pass"
    assert page_payload["links"]["section_url"] == "/app-next/campaigns/linden-pass/sections/npcs"
    assert page_payload["links"]["gen2_campaign_url"] == "/app-next/campaigns/linden-pass"
    assert any(section["section_slug"] == "npcs" for section in page_payload["section_navigation"])

    note_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/notes/operations-brief",
        headers=api_headers(player_token),
    )
    assert note_response.status_code == 200
    note_body = note_response.get_json()["page"]["body_html"]
    assert 'href="/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale"' in note_body
    assert 'href="/app-next/campaigns/linden-pass/pages/locations/harbor-row"' in note_body
    assert "/app-next/app-next/" not in note_body
    assert 'href="/campaigns/linden-pass/pages/' not in note_body

    overview_section_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/sections/overview",
        headers=api_headers(player_token),
    )
    assert overview_section_response.status_code == 404
    overview_page_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/index",
        headers=api_headers(player_token),
    )
    assert overview_page_response.status_code == 404

    with app.app_context():
        AuthStore().set_user_frontend_mode(users["party"]["id"], "flask")

    legacy_home_response = client.get("/api/v1/campaigns/linden-pass/wiki", headers=api_headers(player_token))
    assert legacy_home_response.status_code == 200
    legacy_home_payload = legacy_home_response.get_json()
    assert legacy_home_payload["frontend_mode"] == "gen2"
    assert legacy_home_payload["overview_page"] is None
    assert legacy_home_payload["latest_session_summary"] is not None
    assert legacy_home_payload["latest_session_summary"]["title"] == "Session 2 - The Brass Vault"
    assert legacy_home_payload["latest_session_summary"]["route_slug"] == "sessions/session-2-the-brass-vault"
    assert all(section["section_name"] != "Overview" for section in legacy_home_payload["grouped_sections"])
    assert all(section["section_name"] != "Overview" for section in legacy_home_payload["section_navigation"])
    legacy_locations_group = next(section for section in legacy_home_payload["grouped_sections"] if section["section_name"] == "Locations")
    assert legacy_locations_group["href"] == "/app-next/campaigns/linden-pass/sections/locations"
    legacy_locations_nav_item = next(
        section for section in legacy_home_payload["section_navigation"] if section["section_name"] == "Locations"
    )
    assert legacy_locations_nav_item["href"] == "/app-next/campaigns/linden-pass/sections/locations"

    legacy_search_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki?q=capt",
        headers=api_headers(player_token),
    )
    assert legacy_search_response.status_code == 200
    legacy_search_pages = [
        page
        for section in legacy_search_response.get_json()["grouped_sections"]
        for page in section["pages"]
    ]
    legacy_captain = next(page for page in legacy_search_pages if page["page_ref"] == "npcs/captain-lyra-vale")
    assert legacy_captain["href"] == "/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale"

    legacy_page_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale",
        headers=api_headers(player_token),
    )
    assert legacy_page_response.status_code == 200
    legacy_page_payload = legacy_page_response.get_json()
    assert legacy_page_payload["links"]["campaign_url"] == "/app-next/campaigns/linden-pass"
    assert legacy_page_payload["links"]["section_url"] == "/app-next/campaigns/linden-pass/sections/npcs"
    assert legacy_page_payload["links"]["flask_page_url"] == "/campaigns/linden-pass/pages/npcs/captain-lyra-vale"


def test_api_player_wiki_home_reports_restricted_wiki_scope(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", wiki="dm")
    player_token = issue_api_token(app, users["party"]["email"], label="restricted-player-wiki-api")

    home_response = client.get("/api/v1/campaigns/linden-pass/wiki", headers=api_headers(player_token))
    assert home_response.status_code == 200
    home_payload = home_response.get_json()
    assert home_payload["can_view_wiki"] is False
    assert home_payload["grouped_sections"] == []
    assert home_payload["section_navigation"] == []
    assert "requires DM access" in home_payload["message"]

    page_response = client.get(
        "/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale",
        headers=api_headers(player_token),
    )
    assert page_response.status_code == 403
    assert page_response.get_json()["error"]["code"] == "forbidden"


def test_campaign_home_renders_latest_session_summary_card(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'aria-label="Latest session summary"' in html
    assert "Latest session summary" in html
    assert "Session 2 - The Brass Vault" in html
    assert 'href="/campaigns/linden-pass/pages/sessions/session-2-the-brass-vault"' in html
    assert "Session 3 - Stormglass Heist" not in html

    search_response = client.get("/campaigns/linden-pass?q=capt")
    assert search_response.status_code == 200
    assert 'aria-label="Latest session summary"' not in search_response.get_data(as_text=True)


def test_api_player_wiki_home_selects_latest_published_session_summary_deterministically(
    client,
    app,
    users,
):
    sessions_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "content" / "sessions"
    for stem, summary in (
        ("session-2-alpha-incident", "Session 2 - Alpha Incident"),
        ("session-2-zeta-chronicle", "Session 2 - Zeta Chronicle"),
    ):
        (sessions_dir / f"{stem}.md").write_text(
            "\n".join(
                [
                    "---",
                    "title: " + summary,
                    "section: Sessions",
                    "type: session",
                    "reveal_after_session: 2",
                    "summary: " + summary,
                    "---",
                    "",
                    "Added as a deterministic test fixture for campaign-home session selection.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    with app.app_context():
        app.extensions["repository_store"].refresh()

    dm_token = issue_api_token(app, users["dm"]["email"], label="session-summary-deterministic-api")
    home_response = client.get("/api/v1/campaigns/linden-pass/wiki", headers=api_headers(dm_token))
    assert home_response.status_code == 200
    home_payload = home_response.get_json()
    assert home_payload["latest_session_summary"] is not None
    assert home_payload["latest_session_summary"]["title"] == "Session 2 - Zeta Chronicle"


def test_api_session_endpoints_follow_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-session-api")

    start_response = client.post("/api/v1/campaigns/linden-pass/session/start", headers=api_headers(dm_token))

    assert start_response.status_code == 200
    assert start_response.get_json()["session"]["is_active"] is True

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Sealed Orders",
            "body_markdown": "Deliver the crate to the eastern gate before moonrise.",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Sealed Orders"
    assert article_payload["links"] == {
        "source_url": "",
        "published_page_url": "",
        "player_wiki_editor_url": "/campaigns/linden-pass/dm-content/player-wiki/session-articles/1/new",
        "convert_url": "/campaigns/linden-pass/session/articles/1/convert",
    }
    assert article_payload["source"] == {
        "title": "",
        "label": "",
        "action_label": "",
        "missing_message": "",
    }
    assert article_payload["converted_page"] is None

    dm_session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))

    assert dm_session_response.status_code == 200
    dm_session_payload = dm_session_response.get_json()
    assert dm_session_payload["show_session_dm_passive_scores"] is True
    assert isinstance(dm_session_payload["session_dm_passive_scores"], list)
    assert len(dm_session_payload["staged_articles"]) == 1
    assert dm_session_payload["staged_articles"][0]["title"] == "Sealed Orders"

    post_message_response = client.post(
        "/api/v1/campaigns/linden-pass/session/messages",
        headers=api_headers(player_token),
        json={"body": "We should check the contract before we sign anything."},
    )

    assert post_message_response.status_code == 200
    assert post_message_response.get_json()["message"]["author_display_name"] == "Party Player"

    player_before_reveal = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(player_token))

    assert player_before_reveal.status_code == 200
    player_before_payload = player_before_reveal.get_json()
    assert player_before_payload["show_session_dm_passive_scores"] is False
    assert "session_dm_passive_scores" not in player_before_payload
    assert "staged_articles" not in player_before_payload
    assert all(message["article"] is None for message in player_before_payload["messages"])

    reveal_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles/1/reveal",
        headers=api_headers(dm_token),
    )

    assert reveal_response.status_code == 200
    assert reveal_response.get_json()["article"]["is_revealed"] is True

    player_after_reveal = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(player_token))

    assert player_after_reveal.status_code == 200
    player_after_payload = player_after_reveal.get_json()
    reveal_messages = [message for message in player_after_payload["messages"] if message["article"] is not None]
    assert len(reveal_messages) == 1
    assert reveal_messages[0]["article"]["title"] == "Sealed Orders"


def test_api_session_articles_allow_image_only_manual_staging(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-image-only-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Signal Sketch",
            "body_markdown": "",
            "image": embedded_png_payload(
                "signal-sketch.png",
                alt_text="A sketched signal flag.",
                caption="Shown as the only article content.",
            ),
        },
    )

    assert create_response.status_code == 200
    article_payload = create_response.get_json()["article"]
    assert article_payload["title"] == "Signal Sketch"
    assert article_payload["body_markdown"] == ""
    assert article_payload["image"]["filename"] == "signal-sketch.png"
    assert article_payload["image"]["alt_text"] == "A sketched signal flag."
    assert article_payload["image"]["caption"] == "Shown as the only article content."

    session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
    assert session_response.status_code == 200
    staged_payload = session_response.get_json()["staged_articles"]
    assert any(article["title"] == "Signal Sketch" and article["body_markdown"] == "" for article in staged_payload)


def test_api_session_articles_still_reject_title_only_manual_staging(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-empty-article-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Empty Draft",
            "body_markdown": "",
        },
    )

    assert create_response.status_code == 400
    payload = create_response.get_json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Session articles need body text or an image before they can be saved."


def test_api_session_article_blank_update_requires_existing_or_valid_image(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-image-update-api")

    text_create = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Text Draft",
            "body_markdown": "This text should survive a failed image replacement.",
        },
    )
    assert text_create.status_code == 200
    text_article_id = text_create.get_json()["article"]["id"]

    failed_update = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{text_article_id}",
        headers=api_headers(dm_token),
        json={
            "title": "Text Draft",
            "body_markdown": "",
            "image": {
                "filename": "not-an-image.txt",
                "media_type": "text/plain",
                "data_base64": TINY_PNG_BASE64,
            },
        },
    )
    assert failed_update.status_code == 400

    session_after_failure = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
    text_article = next(
        article
        for article in session_after_failure.get_json()["staged_articles"]
        if article["id"] == text_article_id
    )
    assert text_article["body_markdown"] == "This text should survive a failed image replacement."
    assert text_article["image"] is None

    image_create = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Image Draft",
            "body_markdown": "This body can be cleared because the article has an image.",
            "image": embedded_png_payload("image-draft.png"),
        },
    )
    assert image_create.status_code == 200
    image_article_id = image_create.get_json()["article"]["id"]

    blank_update = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{image_article_id}",
        headers=api_headers(dm_token),
        json={
            "title": "Image Draft",
            "body_markdown": "",
            "image_alt_text": "Updated image-only draft.",
            "image_caption": "Body intentionally blank.",
        },
    )
    assert blank_update.status_code == 200
    updated_article = blank_update.get_json()["article"]
    assert updated_article["body_markdown"] == ""
    assert updated_article["image"]["alt_text"] == "Updated image-only draft."
    assert updated_article["image"]["caption"] == "Body intentionally blank."


def test_api_session_messages_support_private_audience_scope(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-audience-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-audience-api")
    party_token = issue_api_token(app, users["party"]["email"], label="party-session-audience-api")

    start_response = client.post("/api/v1/campaigns/linden-pass/session/start", headers=api_headers(dm_token))
    assert start_response.status_code == 200
    assert start_response.get_json()["session"]["id"] == 1

    global_body = "Council update for everyone."
    dm_only_body = "DM-only response notes."
    owner_only_body = "Owner should get this note."
    party_private_body = "Party-to-DM check-in."

    assert (
        client.post(
            "/api/v1/campaigns/linden-pass/session/messages",
            headers=api_headers(dm_token),
            json={
                "body": global_body,
            },
        ).status_code
        == 200
    )

    assert (
        client.post(
            "/api/v1/campaigns/linden-pass/session/messages",
            headers=api_headers(dm_token),
            json={
                "body": dm_only_body,
                "recipient_scope": "dm_only",
            },
        ).status_code
        == 200
    )

    owner_create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/messages",
        headers=api_headers(dm_token),
        json={
            "body": owner_only_body,
            "recipient_scope": "player",
            "recipient_user_id": users["owner"]["id"],
        },
    )
    assert owner_create_response.status_code == 200
    assert owner_create_response.get_json()["message"]["recipient_label"] == "Owner Player"

    assert (
        client.post(
            "/api/v1/campaigns/linden-pass/session/messages",
            headers=api_headers(party_token),
            json={
                "body": party_private_body,
                "recipient_scope": "dm_only",
            },
        ).status_code
        == 200
    )

    party_payload = client.get(
        "/api/v1/campaigns/linden-pass/session",
        headers=api_headers(party_token),
    ).get_json()
    party_messages = [entry["body_text"] for entry in party_payload["messages"]]
    assert global_body in party_messages
    assert dm_only_body not in party_messages
    assert owner_only_body not in party_messages
    assert party_private_body in party_messages

    owner_payload = client.get(
        "/api/v1/campaigns/linden-pass/session",
        headers=api_headers(owner_token),
    ).get_json()
    recipient_choices = owner_payload.get("session_message_recipient_player_choices")
    assert isinstance(recipient_choices, list)
    recipient_ids = {int(choice["user_id"]) for choice in recipient_choices}
    assert users["owner"]["id"] in recipient_ids
    assert users["party"]["id"] in recipient_ids
    assert all("label" in choice for choice in recipient_choices)
    recipient_labels = {int(choice["user_id"]): choice["label"] for choice in recipient_choices}
    assert recipient_labels[users["owner"]["id"]] == "Arden March (Owner Player)"
    assert recipient_labels[users["party"]["id"]] == "Party Player"
    assert all("@" not in choice["label"] for choice in recipient_choices)

    owner_messages = {entry["body_text"]: entry for entry in owner_payload["messages"]}
    assert owner_messages[global_body]["recipient_scope"] == "global"
    assert owner_messages[owner_only_body]["recipient_scope"] == "player"
    assert owner_messages[owner_only_body]["recipient_label"] == "Owner Player"
    assert party_private_body not in owner_messages

    dm_payload = client.get(
        "/api/v1/campaigns/linden-pass/session",
        headers=api_headers(dm_token),
    ).get_json()
    dm_messages = {entry["body_text"]: entry for entry in dm_payload["messages"]}
    assert dm_messages[global_body]["recipient_scope"] == "global"
    assert dm_messages[dm_only_body]["recipient_scope"] == "dm_only"
    assert dm_messages[dm_only_body]["recipient_label"] == "DM"
    assert dm_messages[owner_only_body]["recipient_label"] == "Owner Player"

    close_response = client.post(
        "/api/v1/campaigns/linden-pass/session/close",
        headers=api_headers(dm_token),
    )
    assert close_response.status_code == 200

    log_id = int(close_response.get_json()["session"]["id"])
    log_payload = client.get(
        f"/api/v1/campaigns/linden-pass/session/logs/{log_id}",
        headers=api_headers(dm_token),
    ).get_json()
    assert log_payload["ok"] is True
    log_messages = {entry["body_text"]: entry for entry in log_payload["messages"]}
    assert set(log_messages.keys()) >= {
        global_body,
        dm_only_body,
        owner_only_body,
        party_private_body,
    }
    assert log_messages[dm_only_body]["recipient_scope"] == "dm_only"
    assert log_messages[owner_only_body]["recipient_scope"] == "player"
    assert log_messages[owner_only_body]["recipient_label"] == "Owner Player"


def test_active_player_choices_use_campaign_membership_list(app, users, monkeypatch):
    from player_wiki.player_choices import build_active_player_choices

    with app.app_context():
        store = app.extensions["auth_store"]

        def fail_get_membership(*args, **kwargs):
            raise AssertionError("player choices should use the campaign membership list")

        monkeypatch.setattr(store, "get_membership", fail_get_membership)

        choices = build_active_player_choices(
            store,
            "linden-pass",
            current_user_id=users["owner"]["id"],
            include_current=True,
        )

    choices_by_id = {int(choice["user_id"]): choice for choice in choices}
    assert set(choices_by_id) == {users["owner"]["id"], users["party"]["id"]}
    assert choices_by_id[users["owner"]["id"]]["label"] == "Owner Player (owner@example.com)"
    assert choices_by_id[users["owner"]["id"]]["is_current"] is True
    assert choices_by_id[users["party"]["id"]]["is_current"] is False


def test_api_session_state_includes_revision_and_view_token(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-metadata-api")

    response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["ok"] is True
    assert isinstance(payload["session_revision"], int)
    assert payload["session_revision"] >= 0
    assert isinstance(payload["session_view_token"], str)
    assert len(payload["session_view_token"]) == 12


def test_api_session_state_short_circuits_with_matching_live_tokens(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-unchanged-api")

    initial_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
    assert initial_response.status_code == 200
    initial_payload = initial_response.get_json()
    assert initial_payload["ok"] is True

    unchanged_response = client.get(
        "/api/v1/campaigns/linden-pass/session",
        headers={
            **api_headers(dm_token),
            "X-Live-Revision": str(initial_payload["session_revision"]),
            "X-Live-View-Token": initial_payload["session_view_token"],
        },
    )
    assert unchanged_response.status_code == 200
    unchanged_payload = unchanged_response.get_json()

    assert unchanged_payload["ok"] is True
    assert unchanged_payload["changed"] is False
    assert unchanged_payload["session_revision"] == initial_payload["session_revision"]
    assert unchanged_payload["session_view_token"] == initial_payload["session_view_token"]
    assert set(unchanged_payload.keys()) == {"ok", "changed", "session_revision", "session_view_token"}


def test_api_can_pull_visible_wiki_page_into_session_store(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-wiki-api")

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "wiki",
            "source_ref": "npcs/captain-lyra-vale",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Captain Lyra Vale"
    assert article_payload["body_format"] == "markdown"
    assert article_payload["source_kind"] == "page"
    assert article_payload["source_ref"] == "npcs/captain-lyra-vale"
    assert article_payload["source_page_ref"] == "npcs/captain-lyra-vale"
    assert article_payload["links"]["source_url"] == "/campaigns/linden-pass/pages/npcs/captain-lyra-vale"
    assert article_payload["links"]["player_wiki_editor_url"] == ""
    assert article_payload["links"]["convert_url"] == ""
    assert article_payload["source"] == {
        "title": "Captain Lyra Vale",
        "label": "published wiki page",
        "action_label": "View published page",
        "missing_message": "The original published wiki page is not currently visible in the player wiki.",
    }
    assert article_payload["image"] is not None
    assert article_payload["image"]["filename"] == "captain-lyra-vale.png"
    assert article_payload["image"]["alt_text"] == "Portrait of Captain Lyra Vale."
    assert article_payload["image"]["caption"] == "Harbor watch captain and trusted ally of the crew."


def test_api_session_article_payload_reports_converted_page_links(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-converted-links-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Courier Seal",
            "body_markdown": "A seal shown during the session.",
        },
    )

    assert create_response.status_code == 200
    article_id = create_response.get_json()["article"]["id"]

    create_page_response = client.put(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-courier-seal",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "API Courier Seal",
                "section": "Notes",
                "type": "note",
                "summary": "A session article converted into a durable player wiki page.",
                "published": True,
                "reveal_after_session": 0,
                "source_ref": f"session-article:linden-pass:{article_id}",
            },
            "body_markdown": "The courier seal is now a published reference.",
        },
    )

    assert create_page_response.status_code == 200

    session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))

    assert session_response.status_code == 200
    staged_articles = session_response.get_json()["staged_articles"]
    article_payload = next(article for article in staged_articles if article["id"] == article_id)
    assert article_payload["converted_page"] == {
        "title": "API Courier Seal",
        "is_visible": True,
        "reveal_after_session": 0,
    }
    assert article_payload["links"]["published_page_url"] == "/campaigns/linden-pass/pages/notes/api-courier-seal"
    assert article_payload["links"]["player_wiki_editor_url"] == ""
    assert article_payload["links"]["convert_url"] == ""


def test_api_session_article_source_search_returns_wiki_pages_and_systems_entries(client, app, users, tmp_path):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-source-search-api")

    wiki_search = client.get(
        "/api/v1/campaigns/linden-pass/session/article-sources/search?q=capt",
        headers=api_headers(dm_token),
    )
    assert wiki_search.status_code == 200
    wiki_payload = wiki_search.get_json()
    assert wiki_payload["results"]
    captain_result = next(
        result for result in wiki_payload["results"] if result["source_ref"] == "npcs/captain-lyra-vale"
    )
    assert captain_result["source_kind"] == "page"
    assert captain_result["kind_label"] == "Wiki"
    assert captain_result["select_label"] == "Captain Lyra Vale - Wiki - NPCs"

    systems_search = client.get(
        "/api/v1/campaigns/linden-pass/session/article-sources/search?q=gob",
        headers=api_headers(dm_token),
    )
    assert systems_search.status_code == 200
    systems_payload = systems_search.get_json()
    assert systems_payload["results"]
    assert systems_payload["results"][0]["source_kind"] == "systems"
    assert systems_payload["results"][0]["source_ref"] == f"systems:{goblin_slug}"
    assert systems_payload["results"][0]["title"] == "Goblin"
    assert systems_payload["results"][0]["subtitle"] == "Monsters - MM"
    assert systems_payload["results"][0]["kind_label"] == "Systems"
    assert systems_payload["results"][0]["select_label"] == "Goblin - Systems - Monsters - MM"


def test_api_can_pull_visible_systems_entry_into_session_store(client, app, users, tmp_path):
    _, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-systems-api")

    create_article_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "wiki",
            "source_ref": f"systems:{goblin_slug}",
        },
    )

    assert create_article_response.status_code == 200
    article_payload = create_article_response.get_json()["article"]
    assert article_payload["title"] == "Goblin"
    assert article_payload["body_format"] == "html"
    assert article_payload["source_kind"] == "systems"
    assert article_payload["source_ref"] == goblin_slug
    assert article_payload["source_page_ref"] == f"systems:{goblin_slug}"
    assert "Scimitar" in article_payload["body_markdown"]
    assert article_payload["image"] is None


def test_api_can_update_and_clear_session_articles(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-session-article-update-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-session-article-update-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={
            "mode": "manual",
            "title": "Initial Orders",
            "body_markdown": "Meet at the north gate.",
        },
    )

    assert create_response.status_code == 200
    article_id = create_response.get_json()["article"]["id"]

    forbidden_update = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}",
        headers=api_headers(player_token),
        json={
            "title": "Player Rewrite",
            "body_markdown": "This should not save.",
        },
    )

    assert forbidden_update.status_code == 403

    update_response = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}",
        headers=api_headers(dm_token),
        json={
            "title": "Updated Orders",
            "body_markdown": "Meet at the south gate.",
        },
    )

    assert update_response.status_code == 200
    updated_payload = update_response.get_json()["article"]
    assert updated_payload["title"] == "Updated Orders"
    assert updated_payload["body_markdown"] == "Meet at the south gate."

    start_response = client.post("/api/v1/campaigns/linden-pass/session/start", headers=api_headers(dm_token))

    assert start_response.status_code == 200

    reveal_response = client.post(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}/reveal",
        headers=api_headers(dm_token),
    )

    assert reveal_response.status_code == 200
    assert reveal_response.get_json()["article"]["is_revealed"] is True

    revealed_update = client.put(
        f"/api/v1/campaigns/linden-pass/session/articles/{article_id}",
        headers=api_headers(dm_token),
        json={
            "title": "Late Rewrite",
            "body_markdown": "This should not save either.",
        },
    )

    assert revealed_update.status_code == 400
    assert revealed_update.get_json()["error"]["code"] == "validation_error"

    forbidden_clear = client.delete(
        "/api/v1/campaigns/linden-pass/session/articles/revealed",
        headers=api_headers(player_token),
    )

    assert forbidden_clear.status_code == 403

    clear_response = client.delete(
        "/api/v1/campaigns/linden-pass/session/articles/revealed",
        headers=api_headers(dm_token),
    )

    assert clear_response.status_code == 200
    clear_payload = clear_response.get_json()
    assert clear_payload["deleted_article_ids"] == [article_id]
    assert clear_payload["deleted_articles"][0]["title"] == "Updated Orders"

    dm_session_response = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))

    assert dm_session_response.status_code == 200
    assert dm_session_response.get_json()["revealed_articles"] == []


def test_api_dm_content_endpoints_require_dm_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-dm-content-api")

    initial_dm_content_response = client.get("/api/v1/campaigns/linden-pass/dm-content", headers=api_headers(dm_token))
    assert initial_dm_content_response.status_code == 200
    initial_dm_content_payload = initial_dm_content_response.get_json()
    initial_statblock_count = len(initial_dm_content_payload["statblocks"])
    initial_condition_count = len(initial_dm_content_payload["conditions"])
    initial_counts = initial_dm_content_payload.get("subpage_counts", {})
    initial_staged_count = initial_counts.get("staged_articles")
    if initial_staged_count is None:
        session_status = client.get("/api/v1/campaigns/linden-pass/session", headers=api_headers(dm_token))
        assert session_status.status_code == 200
        initial_staged_count = len(session_status.get_json()["staged_articles"])
    initial_player_wiki_count = initial_counts.get("player_wiki")
    if initial_player_wiki_count is None:
        initial_pages_response = client.get("/api/v1/campaigns/linden-pass/content/pages", headers=api_headers(dm_token))
        assert initial_pages_response.status_code == 200
        initial_player_wiki_count = len(initial_pages_response.get_json()["pages"])
    initial_systems_count = initial_counts.get("systems")
    if initial_systems_count is None:
        systems_payload = client.get(
            "/api/v1/campaigns/linden-pass/dm-content/systems",
            headers=api_headers(dm_token),
        )
        assert systems_payload.status_code == 200
        initial_systems_count = int(systems_payload.get_json().get("source_count") or 0)

    statblock_response = client.post(
        "/api/v1/campaigns/linden-pass/dm-content/statblocks",
        headers=api_headers(dm_token),
        json={
            "filename": "dock-runner.md",
            "subsection": "Malverine Minions",
            "markdown_text": (
                "# Dock Runner\n\n"
                "Armor Class 13\n"
                "Hit Points 22\n"
                "Speed 30 ft.\n\n"
                "DEX 14 (+2)\n"
            ),
        },
    )

    assert statblock_response.status_code == 200
    statblock_payload = statblock_response.get_json()["statblock"]
    assert statblock_payload["title"] == "Dock Runner"
    assert statblock_payload["subsection"] == "Malverine Minions"
    assert statblock_payload["parser_feedback"]["summary"] == (
        "Parsed combat fields: AC 13, HP 22, Speed 30 ft. (30 ft. movement), Init +2."
    )

    update_statblock_response = client.put(
        f"/api/v1/campaigns/linden-pass/dm-content/statblocks/{statblock_payload['id']}",
        headers=api_headers(dm_token),
        json={
            "subsection": "Dock Crew",
            "markdown_text": (
                "# Dock Runner Captain\n\n"
                "Armor Class 15\n"
                "Hit Points 36\n"
                "Speed 35 ft.\n\n"
                "DEX 16 (+3)\n"
            ),
        },
    )

    assert update_statblock_response.status_code == 200
    updated_statblock_payload = update_statblock_response.get_json()["statblock"]
    assert updated_statblock_payload["title"] == "Dock Runner Captain"
    assert updated_statblock_payload["subsection"] == "Dock Crew"
    assert updated_statblock_payload["max_hp"] == 36
    assert updated_statblock_payload["movement_total"] == 35
    assert updated_statblock_payload["initiative_bonus"] == 3
    assert updated_statblock_payload["parser_feedback"]["summary"] == (
        "Parsed combat fields: AC 15, HP 36, Speed 35 ft. (35 ft. movement), Init +3."
    )

    blocked_update_response = client.put(
        f"/api/v1/campaigns/linden-pass/dm-content/statblocks/{statblock_payload['id']}",
        headers=api_headers(player_token),
        json={"subsection": "Blocked"},
    )

    assert blocked_update_response.status_code == 403

    condition_response = client.post(
        "/api/v1/campaigns/linden-pass/dm-content/conditions",
        headers=api_headers(dm_token),
        json={
            "name": "Off Balance",
            "description_markdown": "The target has disadvantage on its next attack roll.",
        },
    )

    assert condition_response.status_code == 200
    condition_payload = condition_response.get_json()["condition"]
    assert condition_payload["name"] == "Off Balance"

    condition_update_response = client.put(
        f"/api/v1/campaigns/linden-pass/dm-content/conditions/{condition_payload['id']}",
        headers=api_headers(dm_token),
        json={
            "name": "Off Balance Revised",
            "description_markdown": "The target has disadvantage on its next Dexterity check.",
        },
    )

    assert condition_update_response.status_code == 200
    updated_condition_payload = condition_update_response.get_json()["condition"]
    assert updated_condition_payload["name"] == "Off Balance Revised"
    assert (
        updated_condition_payload["description_markdown"]
        == "The target has disadvantage on its next Dexterity check."
    )

    blocked_condition_update_response = client.put(
        f"/api/v1/campaigns/linden-pass/dm-content/conditions/{condition_payload['id']}",
        headers=api_headers(player_token),
        json={"name": "Blocked"},
    )

    assert blocked_condition_update_response.status_code == 403

    create_staged_response = client.post(
        "/api/v1/campaigns/linden-pass/session/articles",
        headers=api_headers(dm_token),
        json={"mode": "manual", "title": "DM Content Count Prep", "body_markdown": "A staged article for count coverage."},
    )
    assert create_staged_response.status_code == 200
    create_staged_payload = create_staged_response.get_json()
    assert create_staged_payload["article"]["title"] == "DM Content Count Prep"

    page_ref = "notes/dm-content-api-counts"
    create_page_response = client.put(
        f"/api/v1/campaigns/linden-pass/content/pages/{page_ref}",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "DM Content API Count Page",
                "section": "Notes",
                "type": "note",
                "summary": "A temporary page used to cover subpage count parity in tests.",
                "published": True,
                "reveal_after_session": 0,
            },
            "body_markdown": "API coverage for DM Content lane counts.",
        },
    )
    assert create_page_response.status_code == 200

    dm_content_response = client.get("/api/v1/campaigns/linden-pass/dm-content", headers=api_headers(dm_token))

    assert dm_content_response.status_code == 200
    dm_content_payload = dm_content_response.get_json()
    assert "subpage_counts" in dm_content_payload
    assert len(dm_content_payload["statblocks"]) == initial_statblock_count + 1
    assert len(dm_content_payload["conditions"]) == initial_condition_count + 1
    assert dm_content_payload["subpage_counts"]["statblocks"] == initial_statblock_count + 1
    assert dm_content_payload["subpage_counts"]["conditions"] == initial_condition_count + 1
    assert dm_content_payload["subpage_counts"]["player_wiki"] == initial_player_wiki_count + 1
    assert dm_content_payload["subpage_counts"]["staged_articles"] == initial_staged_count + 1
    assert dm_content_payload["subpage_counts"]["systems"] == initial_systems_count
    assert any(statblock["subsection"] == "Dock Crew" for statblock in dm_content_payload["statblocks"])
    assert any(condition["name"] == "Off Balance Revised" for condition in dm_content_payload["conditions"])

    blocked_response = client.get("/api/v1/campaigns/linden-pass/dm-content", headers=api_headers(player_token))

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"


def test_api_character_endpoints_allow_assigned_owner_updates(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-api")
    other_player_token = issue_api_token(app, users["party"]["email"], label="other-character-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    starting_revision = character_payload["state_record"]["revision"]

    notes_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "player_notes_markdown": "Remember to bring the ash-yard contract to the council.",
        },
    )

    assert notes_response.status_code == 200
    updated_character = notes_response.get_json()["character"]
    assert updated_character["state_record"]["revision"] == starting_revision + 1
    assert (
        updated_character["state_record"]["state"]["notes"]["player_notes_markdown"]
        == "Remember to bring the ash-yard contract to the council."
    )

    clear_notes_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
        headers=api_headers(owner_token),
        json={
            "expected_revision": updated_character["state_record"]["revision"],
            "player_notes_markdown": "",
        },
    )

    assert clear_notes_response.status_code == 200
    cleared_character = clear_notes_response.get_json()["character"]
    assert cleared_character["state_record"]["revision"] == updated_character["state_record"]["revision"] + 1
    assert cleared_character["state_record"]["state"]["notes"]["player_notes_markdown"] == ""

    personal_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/personal",
        headers=api_headers(owner_token),
        json={
            "expected_revision": cleared_character["state_record"]["revision"],
            "physical_description_markdown": "Broad-shouldered and steady-eyed.",
            "background_markdown": "Spent years running messages along the harbor roads.",
        },
    )

    assert personal_response.status_code == 200
    personal_character = personal_response.get_json()["character"]
    assert personal_character["state_record"]["state"]["notes"]["physical_description_markdown"] == (
        "Broad-shouldered and steady-eyed."
    )
    assert personal_character["state_record"]["state"]["notes"]["background_markdown"] == (
        "Spent years running messages along the harbor roads."
    )

    stale_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "player_notes_markdown": "This revision should conflict.",
        },
    )

    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"

    blocked_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/notes",
        headers=api_headers(other_player_token),
        json={
            "expected_revision": starting_revision + 1,
            "player_notes_markdown": "Another player should not be able to edit this sheet.",
        },
    )

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"
    assert blocked_response.get_json()["error"]["message"] == "You do not have permission to update this character from this view."


def test_api_character_sheet_edit_batch_updates_state_backed_sections_in_one_revision(
    client, app, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-sheet-edit-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    starting_revision = character_payload["state_record"]["revision"]
    second_level_slot = next(
        item
        for item in character_payload["state_record"]["state"]["spell_slots"]
        if int(item.get("level") or 0) == 2
    )

    batch_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/sheet-edit",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "vitals": {
                "current_hp": 35,
                "temp_hp": 4,
            },
            "resources": [
                {
                    "id": "sorcery-points",
                    "current": 3,
                }
            ],
            "spell_slots": [
                {
                    "level": 2,
                    "slot_lane_id": second_level_slot.get("slot_lane_id", ""),
                    "used": 2,
                }
            ],
            "inventory": [
                {
                    "id": "crossbow-bolts-4",
                    "quantity": 18,
                }
            ],
            "currency": {
                "sp": 7,
                "gp": 125,
            },
            "notes": {
                "player_notes_markdown": "Batch note test",
            },
            "personal": {
                "physical_description_markdown": "Lean and weathered.",
                "background_markdown": "Raised around the salt docks.",
            },
        },
    )

    assert batch_response.status_code == 200
    updated_character = batch_response.get_json()["character"]
    updated_state = updated_character["state_record"]["state"]
    assert updated_character["state_record"]["revision"] == starting_revision + 1
    assert updated_state["vitals"]["current_hp"] == 35
    assert updated_state["vitals"]["temp_hp"] == 4
    assert {item["id"]: item for item in updated_state["resources"]}["sorcery-points"]["current"] == 3
    assert next(
        item
        for item in updated_state["spell_slots"]
        if int(item.get("level") or 0) == 2
        and str(item.get("slot_lane_id") or "") == str(second_level_slot.get("slot_lane_id") or "")
    )["used"] == 2
    assert {item["id"]: item for item in updated_state["inventory"]}["crossbow-bolts-4"]["quantity"] == 18
    assert updated_state["currency"]["gp"] == 125
    assert updated_state["currency"]["sp"] == 7
    assert updated_state["notes"]["player_notes_markdown"] == "Batch note test"
    assert updated_state["notes"]["physical_description_markdown"] == "Lean and weathered."
    assert updated_state["notes"]["background_markdown"] == "Raised around the salt docks."

    stale_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/sheet-edit",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "notes": {
                "player_notes_markdown": "This stale batch should conflict.",
            },
        },
    )

    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"
    assert stale_response.get_json()["error"]["message"] == (
        "This sheet changed before your batch save finished. Refresh and review the latest sheet before saving "
        "again. Session Character, Combat, or another tab may have changed nearby fields first; nothing was "
        "auto-merged."
    )


def test_api_character_sheet_edit_batch_rejects_delta_actions(
    client, app, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-sheet-edit-delta-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    starting_revision = character_payload["state_record"]["revision"]

    delta_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/sheet-edit",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "resources": [
                {
                    "id": "sorcery-points",
                    "delta": -1,
                }
            ],
        },
    )

    assert delta_response.status_code == 400
    assert delta_response.get_json()["error"]["code"] == "validation_error"
    assert "absolute current values" in delta_response.get_json()["error"]["message"]

    unchanged_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert unchanged_response.status_code == 200
    unchanged_state = unchanged_response.get_json()["character"]["state_record"]["state"]
    assert {item["id"]: item for item in unchanged_state["resources"]}["sorcery-points"]["current"] == (
        {item["id"]: item for item in character_payload["state_record"]["state"]["resources"]}["sorcery-points"]["current"]
    )


def test_api_character_session_endpoints_cover_dnd_state_controls(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-state-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    starting_revision = character_payload["state_record"]["revision"]
    second_level_slot = next(
        item
        for item in character_payload["state_record"]["state"]["spell_slots"]
        if int(item.get("level") or 0) == 2
    )

    resource_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/resources/sorcery-points",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "current": 1,
        },
    )

    assert resource_response.status_code == 200
    resource_character = resource_response.get_json()["character"]
    assert resource_character["state_record"]["revision"] == starting_revision + 1
    resource_state = resource_character["state_record"]["state"]
    assert {item["id"]: item for item in resource_state["resources"]}["sorcery-points"]["current"] == 1

    stale_resource_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/resources/sorcery-points",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "current": 2,
        },
    )

    assert stale_resource_response.status_code == 409
    assert stale_resource_response.get_json()["error"]["code"] == "state_conflict"

    spell_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/spell-slots/2",
        headers=api_headers(owner_token),
        json={
            "expected_revision": resource_character["state_record"]["revision"],
            "slot_lane_id": second_level_slot.get("slot_lane_id", ""),
            "used": 1,
        },
    )

    assert spell_response.status_code == 200
    spell_character = spell_response.get_json()["character"]
    spell_state = spell_character["state_record"]["state"]
    assert next(
        item
        for item in spell_state["spell_slots"]
        if int(item.get("level") or 0) == 2
        and str(item.get("slot_lane_id") or "") == str(second_level_slot.get("slot_lane_id") or "")
    )["used"] == 1

    inventory_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/inventory/crossbow-bolts-4",
        headers=api_headers(owner_token),
        json={
            "expected_revision": spell_character["state_record"]["revision"],
            "quantity": 17,
        },
    )

    assert inventory_response.status_code == 200
    inventory_character = inventory_response.get_json()["character"]
    inventory_state = inventory_character["state_record"]["state"]
    assert {item["id"]: item for item in inventory_state["inventory"]}["crossbow-bolts-4"]["quantity"] == 17

    currency_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/currency",
        headers=api_headers(owner_token),
        json={
            "expected_revision": inventory_character["state_record"]["revision"],
            "sp": 8,
            "gp": 12,
        },
    )

    assert currency_response.status_code == 200
    currency_character = currency_response.get_json()["character"]
    currency_state = currency_character["state_record"]["state"]
    assert currency_state["currency"]["sp"] == 8
    assert currency_state["currency"]["gp"] == 12

    preview_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/rest-preview/long",
        headers=api_headers(owner_token),
    )

    assert preview_response.status_code == 200
    preview_payload = preview_response.get_json()["preview"]
    assert preview_payload["rest_type"] == "long"
    assert preview_payload["label"] == "Long Rest"
    assert preview_payload["changes"]
    assert isinstance(preview_payload["adjustments"]["current_hp"], int)
    hit_dice_pools = preview_payload["adjustments"]["hit_dice"]["pools"]
    assert hit_dice_pools
    adjusted_hit_die_faces = str(hit_dice_pools[0]["faces"])

    rest_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/rest/long",
        headers=api_headers(owner_token),
        json={
            "expected_revision": currency_character["state_record"]["revision"],
            "current_hp": 7,
            "hit_dice_current": {adjusted_hit_die_faces: 0},
        },
    )

    assert rest_response.status_code == 200
    rested_character = rest_response.get_json()["character"]
    rested_state = rested_character["state_record"]["state"]
    assert rested_state["vitals"]["current_hp"] == 7
    assert next(
        pool
        for pool in rested_state["hit_dice"]["pools"]
        if str(pool["faces"]) == adjusted_hit_die_faces
    )["current"] == 0
    rested_sorcery = {item["id"]: item for item in rested_state["resources"]}["sorcery-points"]
    assert rested_sorcery["current"] == rested_sorcery["max"]
    assert next(
        item
        for item in rested_state["spell_slots"]
        if int(item.get("level") or 0) == 2
        and str(item.get("slot_lane_id") or "") == str(second_level_slot.get("slot_lane_id") or "")
    )["used"] == 0


def test_api_character_session_endpoints_cover_xianxia_state_controls(
    client,
    app,
    users,
    sign_in,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("API Session Crane"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/api-session-crane"
    )

    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-session-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/api-session-crane",
        headers=api_headers(dm_token),
    )

    assert character_response.status_code == 200
    character_payload = character_response.get_json()["character"]
    assert character_payload["presented_xianxia"]["system_label"] == "Xianxia"
    assert character_payload["presented_xianxia"]["resources"]["durability"][0]["label"] == "HP"
    starting_revision = character_payload["state_record"]["revision"]

    vitals_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/api-session-crane/session/vitals",
        headers=api_headers(dm_token),
        json={
            "expected_revision": starting_revision,
            "current_hp": 7,
            "temp_hp": 2,
            "current_stance": 8,
            "temp_stance": 1,
            "current_jing": 0,
            "current_qi": 1,
            "current_shen": 1,
            "current_yin": 0,
            "current_yang": 1,
            "current_dao": 2,
        },
    )

    assert vitals_response.status_code == 200
    vitals_character = vitals_response.get_json()["character"]
    vitals_state = vitals_character["state_record"]["state"]
    assert vitals_state["vitals"] == {"current_hp": 7, "temp_hp": 2}
    assert vitals_state["xianxia"]["vitals"] == {
        "current_hp": 7,
        "temp_hp": 2,
        "current_stance": 8,
        "temp_stance": 1,
    }
    assert vitals_state["xianxia"]["energies"] == {
        "jing": {"current": 0},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert vitals_state["xianxia"]["yin_yang"] == {
        "yin_current": 0,
        "yang_current": 1,
    }
    assert vitals_state["xianxia"]["dao"] == {"current": 2}
    assert vitals_character["presented_xianxia"]["resources"]["dao"]["current"] == 2

    active_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-active-state",
        headers=api_headers(dm_token),
        json={
            "expected_revision": vitals_character["state_record"]["revision"],
            "active_stance_name": "Stone Root",
            "active_aura_name": "Azure Bell",
        },
    )

    assert active_response.status_code == 200
    active_character = active_response.get_json()["character"]
    active_state = active_character["state_record"]["state"]["xianxia"]
    assert active_state["active_stance"] == {"name": "Stone Root"}
    assert active_state["active_aura"] == {"name": "Azure Bell"}
    assert active_character["presented_xianxia"]["active_state"]["stance"]["name"] == "Stone Root"

    add_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-inventory",
        headers=api_headers(dm_token),
        json={
            "expected_revision": active_character["state_record"]["revision"],
            "item": {
                "name": "Spirit Fan",
                "quantity": 2,
                "item_nature": "Relic",
                "item_type": "Artifact",
                "notes": "Painted with cloud sigils.",
                "tags": ["focus"],
                "equippable": True,
                "is_equipped": False,
            },
        },
    )

    assert add_response.status_code == 200
    add_character = add_response.get_json()["character"]
    added_item = next(
        item
        for item in add_character["presented_xianxia"]["inventory"]["quantities"]
        if item["name"] == "Spirit Fan"
    )
    assert added_item["quantity"] == 2
    assert added_item["item_type"] == "Artifact"

    quantity_response = client.patch(
        f"/api/v1/campaigns/linden-pass/characters/api-session-crane/session/inventory/{added_item['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_revision": add_character["state_record"]["revision"],
            "quantity": 3,
        },
    )

    assert quantity_response.status_code == 200
    quantity_character = quantity_response.get_json()["character"]
    quantity_item = next(
        item
        for item in quantity_character["presented_xianxia"]["inventory"]["quantities"]
        if item["id"] == added_item["id"]
    )
    assert quantity_item["quantity"] == 3

    update_response = client.patch(
        f"/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-inventory/{added_item['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_revision": quantity_character["state_record"]["revision"],
            "item": {
                "id": added_item["id"],
                "name": "Spirit Fan",
                "quantity": 4,
                "item_nature": "Relic",
                "item_type": "Artifact",
                "notes": "Painted with storm sigils.",
                "tags": ["focus", "storm"],
                "equippable": True,
                "is_equipped": False,
            },
        },
    )

    assert update_response.status_code == 200
    update_character = update_response.get_json()["character"]
    updated_item = next(
        item
        for item in update_character["presented_xianxia"]["inventory"]["quantities"]
        if item["id"] == added_item["id"]
    )
    assert updated_item["quantity"] == 4
    assert updated_item["notes"] == "Painted with storm sigils."
    assert updated_item["tags"] == ["focus", "storm"]

    equip_response = client.patch(
        f"/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-inventory/{added_item['id']}/equipped",
        headers=api_headers(dm_token),
        json={
            "expected_revision": update_character["state_record"]["revision"],
            "is_equipped": True,
        },
    )

    assert equip_response.status_code == 200
    equip_character = equip_response.get_json()["character"]
    equipped_item = next(
        item
        for item in equip_character["presented_xianxia"]["equipment"]["equipped_items"]
        if item["id"] == added_item["id"]
    )
    assert equipped_item["is_equipped"] is True

    remove_response = client.delete(
        f"/api/v1/campaigns/linden-pass/characters/api-session-crane/session/xianxia-inventory/{added_item['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_revision": equip_character["state_record"]["revision"],
        },
    )

    assert remove_response.status_code == 200
    remove_character = remove_response.get_json()["character"]
    assert all(
        item["id"] != added_item["id"]
        for item in remove_character["presented_xianxia"]["inventory"]["quantities"]
    )


def test_api_character_session_endpoints_cover_xianxia_dao_immolating_actions(
    client,
    app,
    users,
    sign_in,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("API Dao Crane"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    def _prepare_definition(payload: dict) -> None:
        xianxia = payload.setdefault("xianxia", {})
        xianxia["insight"] = {"available": 12, "spent": 0}
        dao_immolating = xianxia.setdefault("dao_immolating_techniques", {})
        dao_immolating["prepared"] = [
            {
                "name": "Ashen Bell",
                "notes": "Stored for a prepared request.",
            }
        ]
        dao_immolating["use_history"] = [
            {
                "name": "River-Cleaving Spark",
                "approval_status": "approved",
                "approval_notes": "Approved for this duel.",
            }
        ]

    _write_character_definition(app, "api-dao-crane", _prepare_definition)

    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-dao-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/api-dao-crane",
        headers=api_headers(dm_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]
    assert character["permissions"]["can_record_xianxia_dao_immolating_use"] is True
    approval_group = next(
        group
        for group in character["presented_xianxia"]["approval"]["status_groups"]
        if group["key"] == "dao_immolating_use_records"
    )
    assert approval_group["records"][0]["use_record_index"] == 0
    assert approval_group["records"][0]["status_label"] == "Approved"
    assert approval_group["records"][0]["insight_cost"] == 10

    player_token = issue_api_token(app, users["party"]["email"], label="player-xianxia-dao-api")
    forbidden_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/api-dao-crane/session/xianxia-dao-immolating-use-records",
        headers=api_headers(player_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "use_record_index": 0,
        },
    )

    assert forbidden_response.status_code == 403

    request_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/api-dao-crane/session/xianxia-dao-immolating-use-requests",
        headers=api_headers(dm_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "prepared_record_index": 0,
            "notes": "Player called on the prepared bell.",
        },
    )

    assert request_response.status_code == 200
    request_character = request_response.get_json()["character"]
    request_history = request_character["definition"]["xianxia"]["dao_immolating_techniques"][
        "use_history"
    ]
    assert request_history[-1]["name"] == "Ashen Bell"
    assert request_history[-1]["request_type"] == "dao_immolating_use"
    assert request_history[-1]["request_source"] == "prepared_record"
    assert request_history[-1]["approval_status"] == "pending"
    assert request_history[-1]["prepared_record_index"] == 0
    request_group = next(
        group
        for group in request_character["presented_xianxia"]["approval"]["status_groups"]
        if group["key"] == "dao_immolating_use_records"
    )
    assert [record["status_label"] for record in request_group["records"]] == [
        "Approved",
        "Pending",
    ]

    record_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/api-dao-crane/session/xianxia-dao-immolating-use-records",
        headers=api_headers(dm_token),
        json={
            "expected_revision": request_character["state_record"]["revision"],
            "use_record_index": 0,
            "notes": "Spent during the bridge duel.",
        },
    )

    assert record_response.status_code == 200
    record_character = record_response.get_json()["character"]
    xianxia_definition = record_character["definition"]["xianxia"]
    recorded_use = xianxia_definition["dao_immolating_techniques"]["use_history"][0]
    assert recorded_use["used"] is True
    assert recorded_use["one_use_status"] == "used"
    assert recorded_use["insight_spent"] == 10
    assert recorded_use["use_notes"] == "Spent during the bridge duel."
    assert xianxia_definition["insight"] == {"available": 2, "spent": 10}
    assert xianxia_definition["advancement_history"][-1]["action"] == "dao_immolating_technique_used"
    record_group = next(
        group
        for group in record_character["presented_xianxia"]["approval"]["status_groups"]
        if group["key"] == "dao_immolating_use_records"
    )
    assert record_group["records"][0]["used"] is True
    assert record_group["records"][0]["use_notes"] == "Spent during the bridge duel."


def test_api_character_session_equipment_state_endpoint_updates_wield_mode_and_rejects_invalid_rows(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-equipment-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]
    equipment_state = character["equipment_state"]
    assert equipment_state["rows"]
    quarterstaff = {item["id"]: item for item in equipment_state["rows"]}["quarterstaff-2"]
    assert quarterstaff["supports_weapon_wield_mode"] is True
    assert {"value": "two-handed", "label": "Two-Handed"} in quarterstaff["weapon_wield_options"]

    wield_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/equipment/quarterstaff-2",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "weapon_wield_mode": "two-handed",
        },
    )

    assert wield_response.status_code == 200
    wielded_character = wield_response.get_json()["character"]
    wielded_inventory = {
        item["catalog_ref"] if item.get("catalog_ref") else item["id"]: item
        for item in wielded_character["state_record"]["state"]["inventory"]
    }
    assert wielded_inventory["quarterstaff-2"]["is_equipped"] is True
    assert wielded_inventory["quarterstaff-2"]["weapon_wield_mode"] == "two-handed"
    wielded_equipment = {item["id"]: item for item in wielded_character["equipment_state"]["rows"]}
    assert wielded_equipment["quarterstaff-2"]["weapon_wield_mode"] == "two-handed"
    assert wielded_equipment["quarterstaff-2"]["equipped_label"] == "Two-Handed"

    stale_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/equipment/quarterstaff-2",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "weapon_wield_mode": "",
        },
    )

    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"

    invalid_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/equipment/backpack-5",
        headers=api_headers(owner_token),
        json={
            "expected_revision": wielded_character["state_record"]["revision"],
            "is_equipped": True,
        },
    )

    assert invalid_response.status_code == 400
    assert invalid_response.get_json()["error"]["code"] == "validation_error"
    assert "does not support equipment state" in invalid_response.get_json()["error"]["message"]


def test_api_character_artificer_infusions_apply_enhanced_defense_and_note_only_effects(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    def _mutate_definition(payload: dict) -> None:
        payload["source"] = {
            "source_type": "native_character_builder",
            "source_path": "builder://arden-march",
            "imported_from": "In-app Native Level 6 Builder",
        }
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Artificer 6"
        profile["classes"] = [
            {
                "row_id": "class-row-1",
                "class_name": "Artificer",
                "subclass_name": "Armorer",
                "level": 6,
            }
        ]
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        ability_scores = dict(stats.get("ability_scores") or {})
        ability_scores["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
        stats["ability_scores"] = ability_scores
        stats["armor_class"] = 16
        payload["stats"] = stats
        payload["features"] = [
            {
                "id": "artificer-infusions-1",
                "name": "Artificer Infusions",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": "You have invented numerous magical infusions.",
                "activation_type": "passive",
            },
            {
                "id": "enhanced-defense-1",
                "name": "Enhanced Defense",
                "category": "class_feature",
                "source": "TCoE 12",
                "description_markdown": "A creature gains a +1 bonus to Armor Class while wearing the infused item.",
                "activation_type": "passive",
                "native_edit_parent_feature_id": "artificer-infusions-1",
            },
            {
                "id": "homunculus-servant-1",
                "name": "Homunculus Servant",
                "category": "class_feature",
                "source": "TCoE 13",
                "description_markdown": "You learn intricate methods for creating a special homunculus.",
                "activation_type": "passive",
                "native_edit_parent_feature_id": "artificer-infusions-1",
            },
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
                "is_equipped": True,
                "is_attuned": False,
            },
            {
                "id": "backpack-1",
                "name": "Backpack",
                "default_quantity": 1,
                "weight": "5 lb.",
                "notes": "",
                "tags": [],
                "is_equipped": False,
                "is_attuned": False,
            },
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
                "is_equipped": True,
                "is_attuned": False,
                "tags": [],
            },
            {
                "id": "backpack-1",
                "catalog_ref": "backpack-1",
                "name": "Backpack",
                "quantity": 1,
                "weight": "5 lb.",
                "notes": "",
                "is_equipped": False,
                "is_attuned": False,
                "tags": [],
            },
        ]
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": []}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-artificer-infusions-api")

    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]
    infusions_state = character["equipment_state"]["artificer_infusions_state"]
    known_by_key = {entry["infusion_key"]: entry for entry in infusions_state["known"]}
    assert infusions_state["available"] is True
    assert infusions_state["artificer_level"] == 6
    assert infusions_state["known_capacity"] == 6
    assert infusions_state["active_capacity"] == 3
    assert "enhanced-defense" in known_by_key
    assert "homunculus-servant" in known_by_key
    assert known_by_key["enhanced-defense"]["target_options"] == [
        {"value": "scale-mail-1", "label": "Scale Mail"}
    ]
    assert any(option["value"] == "backpack-1" for option in known_by_key["homunculus-servant"]["target_options"])

    patch_response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/artificer-infusions",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "active": [
                {"infusion_key": "enhanced-defense", "target_item_ref": "scale-mail-1"},
                {"infusion_key": "homunculus-servant", "target_item_ref": "backpack-1"},
            ],
        },
    )

    assert patch_response.status_code == 200
    updated_character = patch_response.get_json()["character"]
    updated_inventory = {
        item["catalog_ref"] if item.get("catalog_ref") else item["id"]: item
        for item in updated_character["state_record"]["state"]["inventory"]
    }
    assert updated_inventory["scale-mail-1"]["active_infusions"][0]["infusion_key"] == "enhanced-defense"
    assert updated_inventory["backpack-1"]["active_infusions"][0]["infusion_key"] == "homunculus-servant"
    assert updated_character["definition"]["stats"]["armor_class"] == 17
    overview_by_label = {stat["label"]: stat["value"] for stat in updated_character["overview_stats"]}
    assert overview_by_label["Armor Class"] == "17"
    defensive_rules = updated_character["definition"]["stats"]["defensive_state"]["rules"]
    assert any(rule["title"] == "Enhanced Defense" and rule["active"] is True for rule in defensive_rules)

    updated_infusions = updated_character["equipment_state"]["artificer_infusions_state"]
    active_by_key = {entry["infusion_key"]: entry for entry in updated_infusions["active"]}
    assert active_by_key["enhanced-defense"]["automation_status"] == "automated"
    assert active_by_key["homunculus-servant"]["automation_status"] == "note_only"
    assert active_by_key["homunculus-servant"]["effect_summary"] == (
        "Active note only; this infusion does not have automated effects yet."
    )


def test_api_character_detail_exposes_linked_item_and_spell_details(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    item_entry = _seed_systems_item_entry(
        app,
        slug="phb-item-api-linked-quarterstaff",
        title="Quarterstaff",
        metadata={"weapon_category": "simple", "weapon_type": "M", "damage": "1d6", "properties": ["V"]},
        rendered_html="<p>API linked quarterstaff detail.</p>",
    )
    spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-api-linked-detail",
        title="API Detail Spell",
        metadata={"level": 1, "school": "evocation"},
        rendered_html="<p>API linked spell detail.</p>",
    )

    def _mutate_definition(payload: dict) -> None:
        linked_item = False
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, item in enumerate(equipment_catalog):
            item_payload = dict(item or {})
            if str(item_payload.get("id") or "").strip() != "quarterstaff-2":
                continue
            equipment_catalog[index] = {
                **item_payload,
                "name": "Quarterstaff",
                "systems_ref": _systems_ref(item_entry),
            }
            linked_item = True
        assert linked_item
        payload["equipment_catalog"] = equipment_catalog

        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        assert spells
        spells[0] = {
            **dict(spells[0] or {}),
            "name": "API Detail Spell",
            "systems_ref": _systems_ref(spell_entry),
            "casting_time": "1 action",
            "range": "60 feet",
            "duration": "Instantaneous",
            "components": "V, S",
            "save_or_hit": "Dex save",
        }
        spellcasting["spells"] = spells
        spellcasting["spells"][0]["at_higher_levels"] = "At higher levels, the spell deals +1d8 healing per spell slot above 1st."
        payload["spellcasting"] = spellcasting

    _write_character_definition(app, "arden-march", _mutate_definition)
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-linked-details-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert response.status_code == 200
    character = response.get_json()["character"]
    quarterstaff = {item["id"]: item for item in character["equipment_state"]["rows"]}["quarterstaff-2"]
    assert quarterstaff["href"].endswith("/systems/entries/phb-item-api-linked-quarterstaff")
    assert "API linked quarterstaff detail" in quarterstaff["description_html"]

    inventory_quarterstaff = {
        item["item_ref"]: item for item in character["presented_inventory"]
    }["quarterstaff-2"]
    assert inventory_quarterstaff["href"].endswith("/systems/entries/phb-item-api-linked-quarterstaff")
    assert "API linked quarterstaff detail" in inventory_quarterstaff["description_html"]

    def _find_presented_spell(payload: dict, spell_name: str) -> dict:
        spellcasting_payload = dict(payload.get("presented_spellcasting") or {})
        for section_key in ("current_row_sections", "row_sections", "preparation_row_sections"):
            for section in list(spellcasting_payload.get(section_key) or []):
                for spell in list(dict(section or {}).get("spells") or []):
                    if str(dict(spell).get("name") or "").strip() == spell_name:
                        return dict(spell)
                for level_section in list(dict(section or {}).get("spell_level_sections") or []):
                    for group in list(dict(level_section or {}).get("groups") or []):
                        for spell in list(dict(group or {}).get("spells") or []):
                            if str(dict(spell).get("name") or "").strip() == spell_name:
                                return dict(spell)
        raise AssertionError(f"Presented spell {spell_name!r} was not found.")

    detail_spell = _find_presented_spell(character, "API Detail Spell")
    assert detail_spell["href"].endswith("/systems/entries/phb-spell-api-linked-detail")
    assert "API linked spell detail" in detail_spell["description_html"]
    assert detail_spell["school"] == "Evocation"
    assert detail_spell["at_higher_levels"] == "At higher levels, the spell deals +1d8 healing per spell slot above 1st."
    assert detail_spell["is_upcastable"] is True


def test_api_character_detail_exposes_optional_higher_level_text_only_when_present(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    upcast_spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-api-upcast-detail",
        title="API Upcast Detail",
        metadata={
            "level": 1,
            "school": "evocation",
            "entries_higher_level": "At higher levels, the spell deals more damage.",
        },
        rendered_html="<p>API upcast detail spell.</p>",
    )
    base_spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-api-base-detail",
        title="API Base Detail",
        metadata={"level": 1, "school": "evocation"},
        rendered_html="<p>API base spell detail.</p>",
    )

    def _mutate_definition(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spellcasting["spells"] = [
            {
                "name": "API Upcast Detail",
                "systems_ref": _systems_ref(upcast_spell_entry),
                "casting_time": "1 action",
                "range": "Touch",
                "duration": "Instantaneous",
                "components": "V, S",
                "save_or_hit": "",
            },
            {
                "name": "API Base Detail",
                "systems_ref": _systems_ref(base_spell_entry),
                "casting_time": "1 action",
                "range": "Touch",
                "duration": "Instantaneous",
                "components": "V, S",
                "save_or_hit": "",
            },
        ]
        payload["spellcasting"] = spellcasting

    _write_character_definition(app, "arden-march", _mutate_definition)
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-session-upcast-detail-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert response.status_code == 200
    character = response.get_json()["character"]

    def _find_presented_spell(payload: dict, spell_name: str) -> dict:
        spellcasting_payload = dict(payload.get("presented_spellcasting") or {})
        for section_key in ("current_row_sections", "row_sections", "preparation_row_sections"):
            for section in list(spellcasting_payload.get(section_key) or []):
                for spell in list(dict(section or {}).get("spells") or []):
                    if str(dict(spell).get("name") or "").strip() == spell_name:
                        return dict(spell)
                for level_section in list(dict(section or {}).get("spell_level_sections") or []):
                    for group in list(dict(level_section or {}).get("groups") or []):
                        for spell in list(dict(group or {}).get("spells") or []):
                            if str(dict(spell).get("name") or "").strip() == spell_name:
                                return dict(spell)
        raise AssertionError(f"Presented spell {spell_name!r} was not found.")

    upcast_spell = _find_presented_spell(character, "API Upcast Detail")
    non_upcast_spell = _find_presented_spell(character, "API Base Detail")
    assert upcast_spell["at_higher_levels"] == "At higher levels, the spell deals more damage."
    assert upcast_spell["is_upcastable"] is True
    assert "at_higher_levels" not in non_upcast_spell
    assert non_upcast_spell["is_upcastable"] is False


def test_api_character_session_equipment_state_endpoint_preserves_attunement_limit(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    item_ids = ["light-crossbow-1", "quarterstaff-2", "satchel-3", "crossbow-bolts-4"]
    entries = [
        _seed_systems_item_entry(
            app,
            slug=f"phb-item-api-attuned-relic-{index}",
            title=f"Attuned Relic {index}",
            metadata={"rarity": "rare", "attunement": "requires attunement"},
        )
        for index in range(1, 5)
    ]

    def _mutate_definition(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, item_id in enumerate(item_ids):
            equipment_catalog[index] = {
                **dict(equipment_catalog[index]),
                "id": item_id,
                "name": f"Attuned Relic {index + 1}",
                "systems_ref": _systems_ref(entries[index]),
                "is_equipped": index < 3,
                "is_attuned": index < 3,
            }
        payload["equipment_catalog"] = equipment_catalog

    def _mutate_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index, item_id in enumerate(item_ids):
            inventory[index] = {
                **dict(inventory[index]),
                "id": item_id,
                "catalog_ref": item_id,
                "name": f"Attuned Relic {index + 1}",
                "is_equipped": index < 3,
                "is_attuned": index < 3,
            }
        payload["inventory"] = inventory
        payload["attunement"] = {"max_attuned_items": 3, "attuned_item_refs": item_ids[:3]}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-equipment-attunement-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]

    response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/equipment/crossbow-bolts-4",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "is_equipped": True,
            "is_attuned": True,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    assert "already has 3 attuned items" in response.get_json()["error"]["message"]


def test_api_character_session_feature_state_endpoint_updates_arcane_armor(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    def _mutate_definition(payload: dict) -> None:
        features = list(payload.get("features") or [])
        features.append({"name": "Arcane Armor", "description_markdown": "Armor model controls."})
        payload["features"] = features

    def _mutate_state(payload: dict) -> None:
        payload["feature_states"] = {"arcane_armor": {"enabled": False}}

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-feature-state-api")
    character_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert character_response.status_code == 200
    character = character_response.get_json()["character"]
    assert character["arcane_armor_state"]["available"] is True
    assert character["arcane_armor_state"]["enabled"] is False

    response = client.patch(
        "/api/v1/campaigns/linden-pass/characters/arden-march/session/feature-states/arcane_armor",
        headers=api_headers(owner_token),
        json={
            "expected_revision": character["state_record"]["revision"],
            "enabled": True,
        },
    )

    assert response.status_code == 200
    updated_character = response.get_json()["character"]
    assert updated_character["state_record"]["state"]["feature_states"]["arcane_armor"]["enabled"] is True
    assert updated_character["arcane_armor_state"]["enabled"] is True


def test_api_character_list_derives_multiclass_summary_from_class_rows(client, app, users):
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
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-list-api")

    response = client.get("/api/v1/campaigns/linden-pass/characters", headers=api_headers(dm_token))

    assert response.status_code == 200
    payload = response.get_json()
    tobin = next(character for character in payload["characters"] if character["slug"] == "tobin-slate")
    assert tobin["class_level_text"] == "Fighter 3 / Wizard 2"


def test_api_character_roster_exposes_gen2_links_search_and_portraits(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")

    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    portrait_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "assets"
        / "characters"
        / "arden-march"
        / "portrait.webp"
    )
    portrait_path.parent.mkdir(parents=True, exist_ok=True)
    portrait_path.write_bytes(tiny_png)

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile.update(
            {
                "portrait_asset_ref": "characters/arden-march/portrait.png",
                "portrait_alt": "Arden portrait",
                "portrait_caption": "Shown on the Gen2 sheet.",
            }
        )
        payload["profile"] = profile

    _write_character_definition(app, "arden-march", _mutate)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-gen2-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters?q=arden",
        headers=api_headers(dm_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["query"] == "arden"
    assert payload["result_count"] == 1
    assert payload["tools"]["can_create_characters"] is True
    assert payload["links"]["flask_roster_url"] == "/campaigns/linden-pass/characters"
    assert payload["links"]["create_character_url"] == "/app-next/campaigns/linden-pass/characters/new"
    assert payload["links"]["flask_create_character_url"] == "/campaigns/linden-pass/characters/new"
    arden = payload["characters"][0]
    assert arden["slug"] == "arden-march"
    assert arden["href"] == "/app-next/campaigns/linden-pass/characters/arden-march"
    assert arden["flask_href"] == "/campaigns/linden-pass/characters/arden-march"
    assert arden["portrait"]["url"] == "/campaigns/linden-pass/characters/arden-march/portrait"
    assert arden["portrait"]["alt_text"] == "Arden portrait"
    assert arden["portrait"]["caption"] == "Shown on the Gen2 sheet."
    assert arden["hit_dice"]["value"]
    assert isinstance(arden["resource_preview"], list)

    portrait_response = client.get(arden["portrait"]["url"], headers=api_headers(dm_token))
    assert portrait_response.status_code == 200
    assert portrait_response.mimetype == "image/png"

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload["character"]["portrait"]["url"] == arden["portrait"]["url"]
    assert detail_payload["character"]["permissions"]["can_use_controls"] is True
    assert detail_payload["character"]["controls"]["available"] is True
    assert detail_payload["character"]["controls"]["assignment"]["display_name"] == "Owner Player"
    assert detail_payload["character"]["controls"]["can_delete_character"] is True
    assert detail_payload["character"]["controls"]["can_assign_owner"] is False
    assert detail_payload["links"]["flask_character_url"] == "/campaigns/linden-pass/characters/arden-march"
    assert detail_payload["links"]["advanced_editor_url"] == "/app-next/campaigns/linden-pass/characters/arden-march/edit"
    assert detail_payload["links"]["flask_advanced_editor_url"] == "/campaigns/linden-pass/characters/arden-march/edit"


def test_api_character_detail_serializer_exposes_presenter_parity_payload_fields(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-detail-parity-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )

    assert response.status_code == 200
    character = response.get_json()["character"]

    assert isinstance(character["overview_stat_rows"], list)
    assert character["overview_stat_rows"]
    assert all(isinstance(row, list) for row in character["overview_stat_rows"])
    assert any(
        isinstance(stat, dict) and "label" in stat and "value" in stat for row in character["overview_stat_rows"] for stat in row
    )
    assert isinstance(character["overview_stats"], list)
    assert all(isinstance(stat, dict) for stat in character["overview_stats"])

    assert "player_notes_markdown" in character
    assert "player_notes_html" in character
    assert isinstance(character["player_notes_markdown"], str)
    assert isinstance(character["player_notes_html"], str)
    assert isinstance(character["reference_sections"], list)
    assert isinstance(character["physical_description_markdown"], str)
    assert isinstance(character["physical_description_html"], str)
    assert isinstance(character["personal_background_markdown"], str)
    assert isinstance(character["personal_background_html"], str)
    assert isinstance(character["abilities"], list)
    assert isinstance(character["skills"], list)
    assert isinstance(character["proficiency_groups"], list)


def test_api_character_advanced_editor_context_save_and_access(client, app, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-editor-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-editor-api")
    player_token = issue_api_token(app, users["party"]["email"], label="blocked-character-editor-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["supported"] is True
    assert payload["lane"] == "dnd5e"
    assert payload["links"]["advanced_editor_url"] == "/app-next/campaigns/linden-pass/characters/arden-march/edit"
    assert payload["links"]["flask_advanced_editor_url"] == "/campaigns/linden-pass/characters/arden-march/edit"
    editor = payload["editor"]
    assert editor["state_revision"] == payload["character"]["state_record"]["revision"]
    assert [field["name"] for field in editor["reference_fields"]][:2] == [
        "physical_description_markdown",
        "background_markdown",
    ]
    assert editor["feature_rows"]
    assert editor["equipment_rows"]

    owner_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(owner_token),
    )
    assert owner_response.status_code == 200
    assert owner_response.get_json()["supported"] is True

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    values = _advanced_editor_values(editor)
    values["physical_description_markdown"] = "Gen2 physical reference text."
    values["biography_markdown"] = "Gen2 biography reference text."
    values["stat_adjustment_speed"] = "5"
    update_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
        json={"expected_revision": editor["state_revision"], "values": values},
    )

    assert update_response.status_code == 200
    updated_payload = update_response.get_json()
    assert updated_payload["message"] == "Character details updated."
    assert updated_payload["editor"]["state_revision"] == editor["state_revision"] + 1
    assert updated_payload["character"]["definition"]["profile"]["biography_markdown"] == "Gen2 biography reference text."
    assert updated_payload["character"]["state_record"]["state"]["notes"]["physical_description_markdown"] == (
        "Gen2 physical reference text."
    )
    assert updated_payload["character"]["definition"]["stats"]["manual_adjustments"]["speed"] == 5

    stale_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
        json={"expected_revision": editor["state_revision"], "values": values},
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_retraining_context_save_and_access(client, app, users, set_campaign_visibility):
    feat_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-drill.md"
    )
    feat_page_path.write_text(
        """---
title: Harbor Drill
section: Mechanics
subsection: Feats
published: true
summary: A harbor discipline that grants a fighting style.
character_option:
  kind: feat
  name: Harbor Drill
  description_markdown: Harbor veterans drill you into a practiced fighting style.
  optionalfeature_progression:
    - name: Fighting Style
      featureType:
        - FS:F
      progression:
        "1": 1
---
The harbor masters insist on repetition until every motion is clean.
""",
        encoding="utf-8",
    )

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
            entry_types=["optionalfeature"],
            entries=[
                {
                    "entry_key": "dnd-5e|optionalfeature|phb|archery",
                    "entry_type": "optionalfeature",
                    "slug": "phb-optionalfeature-archery",
                    "title": "Archery",
                    "source_page": "72",
                    "source_path": "data/class/class-fighter.json",
                    "search_text": "archery fighting style",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"feature_type": ["FS:F"]},
                    "body": {},
                    "rendered_html": "<p>Archery.</p>",
                },
                {
                    "entry_key": "dnd-5e|optionalfeature|phb|defense",
                    "entry_type": "optionalfeature",
                    "slug": "phb-optionalfeature-defense",
                    "title": "Defense",
                    "source_page": "72",
                    "source_path": "data/class/class-fighter.json",
                    "search_text": "defense fighting style",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"feature_type": ["FS:F"]},
                    "body": {},
                    "rendered_html": "<p>Defense.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-retraining-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-retraining-api")
    player_token = issue_api_token(app, users["party"]["email"], label="blocked-character-retraining-api")

    editor_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
    )
    assert editor_response.status_code == 200
    editor = editor_response.get_json()["editor"]
    editor_values = _advanced_editor_values(editor)
    editor_values.update(
        {
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-drill",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
            "custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-archery",
        }
    )
    add_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor",
        headers=api_headers(dm_token),
        json={"expected_revision": editor["state_revision"], "values": editor_values},
    )
    assert add_response.status_code == 200
    assert add_response.get_json()["links"]["retraining_url"] == (
        "/app-next/campaigns/linden-pass/characters/arden-march/retraining"
    )

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )
    assert detail_response.status_code == 200
    detail_links = detail_response.get_json()["links"]
    assert detail_links["retraining_url"] == "/app-next/campaigns/linden-pass/characters/arden-march/retraining"
    assert detail_links["flask_retraining_url"] == "/campaigns/linden-pass/characters/arden-march/retraining"

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(dm_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["supported"] is True
    assert payload["lane"] == "dnd5e"
    assert payload["links"]["retraining_url"] == "/app-next/campaigns/linden-pass/characters/arden-march/retraining"
    assert payload["links"]["flask_retraining_url"] == "/campaigns/linden-pass/characters/arden-march/retraining"
    retraining = payload["retraining"]
    assert retraining["state_revision"] == payload["character"]["state_record"]["revision"]
    assert "retraining_context" not in payload["readiness"]
    row = next(
        row
        for row in retraining["feature_rows"]
        if any(field.get("name") == "custom_feature_optionalfeature_1_1_1" for field in row.get("choice_fields", []))
    )
    assert row["name"] == "Harbor Drill"
    choice_field = next(field for field in row["choice_fields"] if field["name"] == "custom_feature_optionalfeature_1_1_1")
    assert choice_field["name"] == "custom_feature_optionalfeature_1_1_1"
    assert choice_field["selected"] == "phb-optionalfeature-archery"

    owner_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(owner_token),
    )
    assert owner_response.status_code == 200
    assert owner_response.get_json()["supported"] is True

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    update_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(dm_token),
        json={
            "expected_revision": retraining["state_revision"],
            "values": {"custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-defense"},
        },
    )
    assert update_response.status_code == 200
    updated_payload = update_response.get_json()
    assert updated_payload["message"] == "Retraining saved."
    assert updated_payload["character"]["state_record"]["revision"] == retraining["state_revision"] + 1

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
    assert record is not None
    feature_slugs = {
        str(dict(feature.get("systems_ref") or {}).get("slug") or "").strip()
        for feature in record.definition.features
    }
    retrained_crossbow = next(attack for attack in record.definition.attacks if "Crossbow" in attack["name"])
    latest_event = list((record.definition.source or {}).get("native_progression", {}).get("history") or [])[-1]
    assert "phb-optionalfeature-archery" not in feature_slugs
    assert "phb-optionalfeature-defense" in feature_slugs
    assert retrained_crossbow["attack_bonus"] == 5
    assert latest_event["action"] == "retrain"
    assert latest_event["kind"] == "retrain"

    stale_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(dm_token),
        json={
            "expected_revision": retraining["state_revision"],
            "values": {"custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-defense"},
        },
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_level_up_context_save_and_access(client, app, users, set_campaign_visibility, monkeypatch):
    set_campaign_visibility("linden-pass", characters="dm", session="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-level-up-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-character-level-up-api")
    player_token = issue_api_token(app, users["party"]["email"], label="blocked-character-level-up-api")

    def _ready_level_up(*_args, **_kwargs):
        return {
            "status": "ready",
            "message": "",
            "current_level": 5,
            "selected_class_rows": [
                {
                    "row_id": "class-row-1",
                    "row_level": 5,
                    "class_payload": {"class_name": "Sorcerer", "level": 5},
                }
            ],
        }

    def _level_up_context(_systems_service, campaign_slug, definition, form_values=None, **_kwargs):
        values = {
            "advancement_mode": "advance_existing",
            "target_class_row_id": "class-row-1",
            "hp_gain": str(dict(form_values or {}).get("hp_gain") or ""),
        }
        return {
            "values": values,
            "character_name": definition.name,
            "current_level": 5,
            "next_level": 6,
            "campaign_slug": campaign_slug,
            "advancement_mode": "advance_existing",
            "mode_options": [{"value": "advance_existing", "label": "Advance existing class"}],
            "can_add_class": False,
            "current_class_rows": ["Sorcerer 5"],
            "target_row_options": [{"value": "class-row-1", "label": "Sorcerer 5"}],
            "target_class_row_id": "class-row-1",
            "row_current_level": 5,
            "row_target_level": 6,
            "new_class_options": [],
            "new_subclass_options": [],
            "multiclass_requirement_text": "",
            "multiclass_requirements_met": True,
            "subclass_options": [],
            "requires_subclass": False,
            "choice_sections": [],
            "limitations": ["Fixture level-up boundary."],
            "preview": {
                "class_level_text": "Sorcerer 6",
                "class_rows": ["Sorcerer 6"],
                "max_hp": 43,
                "gained_features": ["Font of Magic scaling"],
                "resources": ["Sorcery Points: 6"],
                "attacks": [],
                "spell_slots": [],
                "new_spells": [],
            },
            "field_live_preview": {},
            "preview_region_ids": [],
            "live_region_ids": [],
        }

    def _apply_level_up(_campaign_slug, current_definition, _level_up_context, form_values=None, **kwargs):
        payload = current_definition.to_dict()
        profile = dict(payload.get("profile") or {})
        classes = [dict(row or {}) for row in list(profile.get("classes") or [])]
        if classes:
            classes[0]["level"] = 6
        profile["classes"] = classes
        profile["class_level_text"] = "Sorcerer 6"
        payload["profile"] = profile
        stats = dict(payload.get("stats") or {})
        stats["max_hp"] = 43
        payload["stats"] = stats
        return CharacterDefinition.from_dict(payload), kwargs.get("current_import_metadata"), int(
            dict(form_values or {}).get("hp_gain") or 0
        )

    monkeypatch.setattr(api_module, "native_level_up_readiness", _ready_level_up)
    monkeypatch.setattr(api_module, "build_native_level_up_context", _level_up_context)
    monkeypatch.setattr(api_module, "build_native_level_up_character_definition", _apply_level_up)

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )
    assert detail_response.status_code == 200
    detail_links = detail_response.get_json()["links"]
    assert detail_links["level_up_url"] == "/app-next/campaigns/linden-pass/characters/arden-march/level-up"
    assert detail_links["flask_level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"

    owner_detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )
    assert owner_detail_response.status_code == 200
    owner_detail_links = owner_detail_response.get_json()["links"]
    assert owner_detail_links["level_up_url"] == "/app-next/campaigns/linden-pass/characters/arden-march/level-up"
    assert owner_detail_links["flask_level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"
    assert "advanced_editor_url" not in owner_detail_links
    assert "progression_repair_url" not in owner_detail_links

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up?hp_gain=5",
        headers=api_headers(owner_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["supported"] is True
    assert payload["lane"] == "dnd5e"
    assert payload["links"]["level_up_url"] == "/app-next/campaigns/linden-pass/characters/arden-march/level-up"
    assert payload["links"]["flask_level_up_url"] == "/campaigns/linden-pass/characters/arden-march/level-up"
    level_up = payload["level_up"]
    assert level_up["state_revision"] == payload["character"]["state_record"]["revision"]
    assert level_up["current_level"] == 5
    assert level_up["next_level"] == 6
    assert level_up["values"]["hp_gain"] == "5"
    assert level_up["preview"]["class_level_text"] == "Sorcerer 6"

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    update_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up",
        headers=api_headers(owner_token),
        json={"expected_revision": level_up["state_revision"], "values": {"hp_gain": "5"}},
    )

    assert update_response.status_code == 200
    updated_payload = update_response.get_json()
    assert updated_payload["message"] == "Arden March advanced to level 6."
    assert updated_payload["character"]["definition"]["profile"]["class_level_text"] == "Sorcerer 6"
    assert updated_payload["character"]["state_record"]["revision"] == level_up["state_revision"] + 1
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    saved_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    assert saved_definition["profile"]["class_level_text"] == "Sorcerer 6"

    stale_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up",
        headers=api_headers(owner_token),
        json={"expected_revision": level_up["state_revision"], "values": {"hp_gain": "5"}},
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_progression_repair_context_save_and_access(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-repair-api")
    player_token = issue_api_token(app, users["party"]["email"], label="blocked-character-repair-api")

    def _repairable_readiness(*_args, **_kwargs):
        return {
            "status": "repairable",
            "message": "This imported character needs a quick progression repair before native level-up.",
            "reasons": [
                "Choose a supported base class link for this character.",
                "Classify the current imported spell rows so native spell progression can trust them.",
            ],
        }

    def _repair_context(_systems_service, _campaign_slug, definition, form_values=None, **_kwargs):
        values = {
            "repair_class_slug_class-row-1": str(dict(form_values or {}).get("repair_class_slug_class-row-1") or ""),
            "repair_subclass_slug_class-row-1": str(
                dict(form_values or {}).get("repair_subclass_slug_class-row-1") or ""
            ),
            "repair_species_slug": str(dict(form_values or {}).get("repair_species_slug") or ""),
            "repair_background_slug": str(dict(form_values or {}).get("repair_background_slug") or ""),
            "repair_feat_1": str(dict(form_values or {}).get("repair_feat_1") or ""),
            "repair_spell_mark_1": str(dict(form_values or {}).get("repair_spell_mark_1") or ""),
            "repair_spell_class_row_1": str(dict(form_values or {}).get("repair_spell_class_row_1") or ""),
        }
        return {
            "values": values,
            "character_name": definition.name,
            "current_level": 5,
            "readiness": _repairable_readiness(),
            "class_rows": [
                {
                    "row_id": "class-row-1",
                    "row_level": 5,
                    "class_name": "Imported Sorcerer",
                    "class_field_name": "repair_class_slug_class-row-1",
                    "class_selected": values["repair_class_slug_class-row-1"],
                    "class_options": [{"value": "systems:sorcerer", "label": "Sorcerer"}],
                    "subclass_field_name": "repair_subclass_slug_class-row-1",
                    "subclass_selected": values["repair_subclass_slug_class-row-1"],
                    "subclass_options": [{"value": "systems:draconic-bloodline", "label": "Draconic Bloodline"}],
                }
            ],
            "species_options": [{"value": "systems:human", "label": "Human"}],
            "background_options": [{"value": "systems:acolyte", "label": "Acolyte"}],
            "feat_rows": [
                {
                    "index": 1,
                    "name": "repair_feat_1",
                    "selected": values["repair_feat_1"],
                    "options": [{"value": "systems:lucky", "label": "Lucky"}],
                }
            ],
            "optionalfeature_rows": [],
            "spell_rows": [
                {
                    "name": "Fire Bolt",
                    "field_name": "repair_spell_mark_1",
                    "selected": values["repair_spell_mark_1"],
                    "options": [{"value": "known", "label": "Known"}],
                    "class_row_field_name": "repair_spell_class_row_1",
                    "class_row_selected": values["repair_spell_class_row_1"],
                    "class_row_options": [{"value": "class-row-1", "label": "Imported Sorcerer 5"}],
                }
            ],
            "class_entries": [],
            "species_entries": [],
            "background_entries": [],
            "subclass_entries": [],
            "feat_entries": [],
            "optionalfeature_entries": [],
        }

    def _apply_repair(_campaign_slug, current_definition, current_import_metadata, _repair_context, form_values):
        assert dict(form_values).get("repair_class_slug_class-row-1") == "systems:sorcerer"
        payload = current_definition.to_dict()
        source = dict(payload.get("source") or {})
        native_progression = dict(source.get("native_progression") or {})
        native_progression["baseline_repaired_at"] = "2026-06-05T00:00:00Z"
        native_progression["history"] = list(native_progression.get("history") or []) + [
            {"kind": "repair", "action": "repair", "target_level": 5}
        ]
        source["native_progression"] = native_progression
        payload["source"] = source
        return CharacterDefinition.from_dict(payload), current_import_metadata

    monkeypatch.setattr(api_module, "native_level_up_readiness", _repairable_readiness)
    monkeypatch.setattr(api_module, "build_imported_progression_repair_context", _repair_context)
    monkeypatch.setattr(api_module, "apply_imported_progression_repairs", _apply_repair)

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )
    assert detail_response.status_code == 200
    detail_links = detail_response.get_json()["links"]
    assert detail_links["progression_repair_url"] == (
        "/app-next/campaigns/linden-pass/characters/arden-march/progression-repair"
    )
    assert detail_links["flask_progression_repair_url"] == (
        "/campaigns/linden-pass/characters/arden-march/progression-repair"
    )

    level_up_repairable_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/level-up",
        headers=api_headers(dm_token),
    )
    assert level_up_repairable_response.status_code == 200
    level_up_repairable_payload = level_up_repairable_response.get_json()
    assert level_up_repairable_payload["supported"] is False
    assert level_up_repairable_payload["lane"] == "repairable"
    assert level_up_repairable_payload["links"]["progression_repair_url"] == (
        "/app-next/campaigns/linden-pass/characters/arden-march/progression-repair"
    )

    retraining_repairable_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/retraining",
        headers=api_headers(dm_token),
    )
    assert retraining_repairable_response.status_code == 200
    retraining_repairable_payload = retraining_repairable_response.get_json()
    assert retraining_repairable_payload["supported"] is False
    assert retraining_repairable_payload["lane"] == "repairable"
    assert retraining_repairable_payload["links"]["progression_repair_url"] == (
        "/app-next/campaigns/linden-pass/characters/arden-march/progression-repair"
    )

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair",
        headers=api_headers(dm_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["supported"] is True
    assert payload["lane"] == "repairable"
    assert payload["links"]["progression_repair_url"] == (
        "/app-next/campaigns/linden-pass/characters/arden-march/progression-repair"
    )
    repair = payload["repair"]
    assert repair["state_revision"] == payload["character"]["state_record"]["revision"]
    assert repair["class_rows"][0]["class_field_name"] == "repair_class_slug_class-row-1"
    assert repair["species_options"][0]["label"] == "Human"
    assert repair["spell_rows"][0]["field_name"] == "repair_spell_mark_1"

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    update_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair",
        headers=api_headers(dm_token),
        json={
            "expected_revision": repair["state_revision"],
            "values": {
                "repair_class_slug_class-row-1": "systems:sorcerer",
                "repair_subclass_slug_class-row-1": "systems:draconic-bloodline",
                "repair_species_slug": "systems:human",
                "repair_background_slug": "systems:acolyte",
                "repair_feat_1": "systems:lucky",
                "repair_spell_mark_1": "known",
                "repair_spell_class_row_1": "class-row-1",
            },
        },
    )
    assert update_response.status_code == 200
    updated_payload = update_response.get_json()
    assert updated_payload["message"].startswith("Progression repair saved")
    assert updated_payload["character"]["state_record"]["revision"] == repair["state_revision"] + 1

    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    saved_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    latest_event = saved_definition["source"]["native_progression"]["history"][-1]
    assert latest_event["kind"] == "repair"
    assert latest_event["target_level"] == 5

    stale_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair",
        headers=api_headers(dm_token),
        json={
            "expected_revision": repair["state_revision"],
            "values": {"repair_class_slug_class-row-1": "systems:sorcerer"},
        },
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_character_create_context_uses_gen2_links_and_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-create-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-character-create-api")

    response = client.get(
        "/api/v1/campaigns/linden-pass/characters/create",
        headers=api_headers(dm_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["lane"] == "dnd5e"
    assert payload["create"]["lane"] == "dnd5e"
    assert payload["links"]["create_character_url"] == "/app-next/campaigns/linden-pass/characters/new"
    assert payload["links"]["flask_create_character_url"] == "/campaigns/linden-pass/characters/new"
    assert payload["links"]["flask_create_url"] == "/campaigns/linden-pass/characters/new"

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/create",
        headers=api_headers(player_token),
    )

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    anonymous_response = client.get("/api/v1/campaigns/linden-pass/characters/create")

    assert anonymous_response.status_code == 401
    assert anonymous_response.get_json()["error"]["code"] == "auth_required"


def test_api_xianxia_gen2_create_manual_import_and_cultivation_write_native_records(
    client,
    app,
    users,
    set_campaign_visibility,
):
    _configure_xianxia_campaign(app)
    set_campaign_visibility("linden-pass", characters="players")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-authoring-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-xianxia-authoring-api")

    context_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/create",
        headers=api_headers(dm_token),
    )

    assert context_response.status_code == 200
    context_payload = context_response.get_json()
    assert context_payload["lane"] == "xianxia"
    assert context_payload["create"]["lane"] == "xianxia"
    assert context_payload["links"]["create_character_url"] == "/app-next/campaigns/linden-pass/characters/new"
    assert context_payload["links"]["import_xianxia_url"] == "/app-next/campaigns/linden-pass/characters/import/xianxia-manual"
    assert context_payload["links"]["flask_import_xianxia_url"] == "/campaigns/linden-pass/characters/import/xianxia-manual"

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/create",
        headers=api_headers(dm_token),
        json={"values": _valid_xianxia_create_data("Gen2 Crane", slug="gen2-crane")},
    )

    assert create_response.status_code == 200
    create_payload = create_response.get_json()
    assert create_payload["message"] == "Gen2 Crane created."
    assert create_payload["links"]["character_url"] == "/app-next/campaigns/linden-pass/characters/gen2-crane"
    created_definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "gen2-crane"
        / "definition.yaml"
    )
    created_definition = yaml.safe_load(created_definition_path.read_text(encoding="utf-8"))
    assert created_definition["system"] == "Xianxia"
    assert created_definition["xianxia"]["realm"] == "Mortal"

    unsupported_editor_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/advanced-editor",
        headers=api_headers(dm_token),
    )

    assert unsupported_editor_response.status_code == 200
    unsupported_editor_payload = unsupported_editor_response.get_json()
    assert unsupported_editor_payload["supported"] is False
    assert unsupported_editor_payload["lane"] == "unsupported"
    assert unsupported_editor_payload["editor"] is None
    assert unsupported_editor_payload["links"]["cultivation_url"] == (
        "/app-next/campaigns/linden-pass/characters/gen2-crane/cultivation"
    )
    assert unsupported_editor_payload["links"]["flask_cultivation_url"] == (
        "/campaigns/linden-pass/characters/gen2-crane/cultivation"
    )

    unsupported_level_up_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/level-up",
        headers=api_headers(dm_token),
    )
    assert unsupported_level_up_response.status_code == 200
    unsupported_level_up_payload = unsupported_level_up_response.get_json()
    assert unsupported_level_up_payload["supported"] is False
    assert unsupported_level_up_payload["lane"] == "unsupported"
    assert unsupported_level_up_payload["level_up"] is None
    assert unsupported_level_up_payload["links"]["cultivation_url"] == (
        "/app-next/campaigns/linden-pass/characters/gen2-crane/cultivation"
    )

    unsupported_retraining_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/retraining",
        headers=api_headers(dm_token),
    )
    assert unsupported_retraining_response.status_code == 200
    unsupported_retraining_payload = unsupported_retraining_response.get_json()
    assert unsupported_retraining_payload["supported"] is False
    assert unsupported_retraining_payload["lane"] == "unsupported"
    assert unsupported_retraining_payload["retraining"] is None
    assert unsupported_retraining_payload["links"]["cultivation_url"] == (
        "/app-next/campaigns/linden-pass/characters/gen2-crane/cultivation"
    )
    assert unsupported_retraining_payload["links"]["flask_cultivation_url"] == (
        "/campaigns/linden-pass/characters/gen2-crane/cultivation"
    )

    unsupported_repair_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/progression-repair",
        headers=api_headers(dm_token),
    )
    assert unsupported_repair_response.status_code == 200
    unsupported_repair_payload = unsupported_repair_response.get_json()
    assert unsupported_repair_payload["supported"] is False
    assert unsupported_repair_payload["lane"] == "unsupported"
    assert unsupported_repair_payload["repair"] is None
    assert unsupported_repair_payload["links"]["cultivation_url"] == (
        "/app-next/campaigns/linden-pass/characters/gen2-crane/cultivation"
    )

    blocked_level_up_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/level-up",
        headers=api_headers(player_token),
    )
    assert blocked_level_up_response.status_code == 403
    assert blocked_level_up_response.get_json()["error"]["code"] == "forbidden"

    blocked_retraining_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/retraining",
        headers=api_headers(player_token),
    )
    assert blocked_retraining_response.status_code == 403
    assert blocked_retraining_response.get_json()["error"]["code"] == "forbidden"

    blocked_repair_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/progression-repair",
        headers=api_headers(player_token),
    )
    assert blocked_repair_response.status_code == 403
    assert blocked_repair_response.get_json()["error"]["code"] == "forbidden"

    cultivation_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/cultivation",
        headers=api_headers(dm_token),
    )
    assert cultivation_response.status_code == 200
    cultivation_payload = cultivation_response.get_json()
    assert cultivation_payload["supported"] is True
    assert cultivation_payload["lane"] == "xianxia"
    assert cultivation_payload["links"]["cultivation_url"] == (
        "/app-next/campaigns/linden-pass/characters/gen2-crane/cultivation"
    )
    assert cultivation_payload["links"]["flask_cultivation_url"] == (
        "/campaigns/linden-pass/characters/gen2-crane/cultivation"
    )
    assert cultivation_payload["cultivation"]["insight"]["available"] == 0
    cultivation_revision = cultivation_payload["character"]["state_record"]["revision"]

    blocked_cultivation_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/cultivation",
        headers=api_headers(player_token),
    )
    assert blocked_cultivation_response.status_code == 403
    assert blocked_cultivation_response.get_json()["error"]["code"] == "forbidden"

    def _mark_arden_dnd(payload: dict) -> None:
        payload["system"] = "DND-5E"

    _write_character_definition(app, "arden-march", _mark_arden_dnd)
    unsupported_cultivation_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march/cultivation",
        headers=api_headers(dm_token),
    )
    assert unsupported_cultivation_response.status_code == 200
    unsupported_cultivation_payload = unsupported_cultivation_response.get_json()
    assert unsupported_cultivation_payload["supported"] is False
    assert unsupported_cultivation_payload["lane"] == "unsupported"
    assert unsupported_cultivation_payload["cultivation"] is None

    insight_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/cultivation",
        headers=api_headers(dm_token),
        json={
            "expected_revision": cultivation_revision,
            "action": "save_insight",
            "values": {
                "insight_available": "3",
                "insight_spent": "1",
            },
        },
    )
    assert insight_response.status_code == 200
    insight_payload = insight_response.get_json()
    assert insight_payload["message"] == "Insight counters saved."
    assert insight_payload["cultivation"]["insight"]["available"] == 3
    assert insight_payload["cultivation"]["insight"]["spent"] == 1
    assert insight_payload["character"]["state_record"]["revision"] == cultivation_revision + 1
    updated_definition = yaml.safe_load(created_definition_path.read_text(encoding="utf-8"))
    assert updated_definition["xianxia"]["insight"] == {"available": 3, "spent": 1}
    assert updated_definition["xianxia"]["advancement_history"][-1]["action"] == "insight_counter_adjustment"

    stale_cultivation_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/gen2-crane/cultivation",
        headers=api_headers(dm_token),
        json={
            "expected_revision": cultivation_revision,
            "action": "record_gathering_insight",
            "values": {
                "insight_gain_amount": "1",
                "gathering_insight_downtime": "A quiet week",
            },
        },
    )
    assert stale_cultivation_response.status_code == 409
    assert stale_cultivation_response.get_json()["error"]["code"] == "state_conflict"

    import_values = _valid_xianxia_manual_import_data("Gen2 Imported Lotus", slug="gen2-imported-lotus")
    preview_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/import/xianxia-manual",
        headers=api_headers(dm_token),
        json={"values": import_values},
    )

    assert preview_response.status_code == 200
    preview_payload = preview_response.get_json()
    assert preview_payload["message"] == "Review the imported sheet summary, then confirm to create the character."
    assert preview_payload["import_context"]["preview"]["name"] == "Gen2 Imported Lotus"
    preview_definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "gen2-imported-lotus"
        / "definition.yaml"
    )
    assert not preview_definition_path.exists()

    confirm_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/import/xianxia-manual",
        headers=api_headers(dm_token),
        json={"values": import_values, "confirm_import": True},
    )

    assert confirm_response.status_code == 200
    confirm_payload = confirm_response.get_json()
    assert confirm_payload["message"] == "Gen2 Imported Lotus imported."
    assert confirm_payload["links"]["character_url"] == "/app-next/campaigns/linden-pass/characters/gen2-imported-lotus"
    imported_definition = yaml.safe_load(preview_definition_path.read_text(encoding="utf-8"))
    assert imported_definition["system"] == "Xianxia"
    assert imported_definition["source"]["source_path"] == "importer://xianxia-manual"


def test_api_character_controls_assignment_and_delete_use_gen2_contract(client, app, users):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-character-controls-api")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-controls-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-character-controls-api")

    blocked_assign_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls/assignment",
        headers=api_headers(dm_token),
        json={"user_id": users["party"]["id"]},
    )

    assert blocked_assign_response.status_code == 403
    assert blocked_assign_response.get_json()["error"]["code"] == "forbidden"

    assign_response = client.post(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls/assignment",
        headers=api_headers(admin_token),
        json={"user_id": users["party"]["id"]},
    )

    assert assign_response.status_code == 200
    assigned_payload = assign_response.get_json()
    assert assigned_payload["message"] == "Assigned arden-march to party@example.com."
    assert assigned_payload["character"]["controls"]["assignment"]["display_name"] == "Party Player"
    assert assigned_payload["character"]["controls"]["can_assign_owner"] is True
    assert any(
        choice["user_id"] == users["party"]["id"] and choice["is_current"]
        for choice in assigned_payload["character"]["controls"]["player_choices"]
    )

    with app.app_context():
        store = AuthStore()
        assignment = store.get_character_assignment("linden-pass", "arden-march")
        assert assignment is not None
        assert assignment.user_id == users["party"]["id"]

    clear_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls/assignment",
        headers=api_headers(admin_token),
    )

    assert clear_response.status_code == 200
    assert clear_response.get_json()["character"]["controls"]["assignment"] is None

    with app.app_context():
        store = AuthStore()
        assert store.get_character_assignment("linden-pass", "arden-march") is None

    blocked_delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls",
        headers=api_headers(player_token),
        json={"confirm_character_slug": "arden-march"},
    )

    assert blocked_delete_response.status_code == 403
    assert blocked_delete_response.get_json()["error"]["code"] == "forbidden"

    invalid_delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls",
        headers=api_headers(dm_token),
        json={"confirm_character_slug": "not-arden-march"},
    )

    assert invalid_delete_response.status_code == 400
    assert invalid_delete_response.get_json()["error"]["message"] == "Type arden-march to confirm deletion."

    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    assert definition_path.exists()

    delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/controls",
        headers=api_headers(dm_token),
        json={"confirm_character_slug": "arden-march"},
    )

    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["deleted_character_slug"] == "arden-march"
    assert delete_payload["links"]["gen2_roster_url"] == "/app-next/campaigns/linden-pass/characters"

    with app.app_context():
        store = AuthStore()
        state_store = app.extensions["character_state_store"]
        assert store.get_character_assignment("linden-pass", "arden-march") is None
        assert state_store.get_state("linden-pass", "arden-march") is None
    assert not definition_path.exists()


def test_api_character_portrait_upload_remove_uses_revisioned_gen2_contract(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")

    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    encoded_png = base64.b64encode(tiny_png).decode("ascii")
    portrait_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "assets"
        / "characters"
        / "arden-march"
        / "portrait.webp"
    )
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-character-portrait-api")
    other_player_token = issue_api_token(app, users["party"]["email"], label="other-character-portrait-api")

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    starting_revision = detail_response.get_json()["character"]["state_record"]["revision"]

    upload_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        headers=api_headers(dm_token),
        json={
            "expected_revision": starting_revision,
            "portrait_file": {
                "filename": "updated-portrait.png",
                "data_base64": encoded_png,
                "media_type": "image/png",
            },
            "alt_text": "Arden updated portrait",
            "caption": "Uploaded through Gen2.",
        },
    )

    assert upload_response.status_code == 200
    uploaded_character = upload_response.get_json()["character"]
    assert uploaded_character["state_record"]["revision"] == starting_revision + 1
    assert uploaded_character["portrait"]["asset_ref"] == "characters/arden-march/portrait.webp"
    assert uploaded_character["portrait"]["alt_text"] == "Arden updated portrait"
    assert uploaded_character["portrait"]["caption"] == "Uploaded through Gen2."
    portrait_bytes = portrait_path.read_bytes()
    assert portrait_bytes[:4] == b"RIFF"
    assert portrait_bytes[8:12] == b"WEBP"
    profile = yaml.safe_load(definition_path.read_text(encoding="utf-8"))["profile"]
    assert profile["portrait_asset_ref"] == "characters/arden-march/portrait.webp"
    assert profile["portrait_alt"] == "Arden updated portrait"
    assert profile["portrait_caption"] == "Uploaded through Gen2."

    portrait_response = client.get(uploaded_character["portrait"]["url"], headers=api_headers(dm_token))
    assert portrait_response.status_code == 200
    assert portrait_response.mimetype == "image/webp"

    stale_upload_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        headers=api_headers(dm_token),
        json={
            "expected_revision": starting_revision,
            "portrait_file": {
                "filename": "stale-portrait.png",
                "data_base64": encoded_png,
                "media_type": "image/png",
            },
        },
    )

    assert stale_upload_response.status_code == 409
    assert stale_upload_response.get_json()["error"]["code"] == "state_conflict"

    blocked_upload_response = client.put(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        headers=api_headers(other_player_token),
        json={
            "expected_revision": uploaded_character["state_record"]["revision"],
            "portrait_file": {
                "filename": "blocked.png",
                "data_base64": encoded_png,
                "media_type": "image/png",
            },
        },
    )

    assert blocked_upload_response.status_code == 403
    assert blocked_upload_response.get_json()["error"]["code"] == "forbidden"

    remove_response = client.delete(
        "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
        headers=api_headers(dm_token),
        json={"expected_revision": uploaded_character["state_record"]["revision"]},
    )

    assert remove_response.status_code == 200
    removed_character = remove_response.get_json()["character"]
    assert removed_character["state_record"]["revision"] == starting_revision + 2
    assert removed_character["portrait"] is None
    assert not portrait_path.exists()
    profile = yaml.safe_load(definition_path.read_text(encoding="utf-8"))["profile"]
    assert "portrait_asset_ref" not in profile
    assert "portrait_alt" not in profile
    assert "portrait_caption" not in profile


def test_api_content_page_management_requires_dm_and_refreshes_repository(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-pages-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-content-pages-api")

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages",
        headers=api_headers(player_token),
    )

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    create_response = client.put(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-field-report",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "API Field Report",
                "section": "Notes",
                "type": "note",
                "summary": "A published note created through the management API.",
                "published": True,
                "reveal_after_session": 0,
            },
            "body_markdown": "The tower relay is stable, but the east pier wards are flickering.",
        },
    )

    assert create_response.status_code == 200
    created_payload = create_response.get_json()["page_file"]
    assert created_payload["page"]["title"] == "API Field Report"
    assert created_payload["page"]["route_slug"] == "notes/api-field-report"
    assert created_payload["page"]["is_visible"] is True

    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "api-field-report.md"
    assert page_path.exists()

    list_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages",
        headers=api_headers(dm_token),
    )

    assert list_response.status_code == 200
    listed_pages = list_response.get_json()["pages"]
    assert any(item["page_ref"] == "notes/api-field-report" for item in listed_pages)
    listed_field_report = next(
        item for item in listed_pages if item["page_ref"] == "notes/api-field-report"
    )
    assert listed_field_report["can_hard_delete"] is True
    assert listed_field_report["hard_delete_blockers"] == []
    assert listed_field_report["removal_status_label"] == "Hard delete available"
    assert listed_field_report["removal_safety"]["can_hard_delete"] is True

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-field-report",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()["page_file"]
    assert "east pier wards" in detail_payload["body_markdown"]
    assert detail_payload["can_hard_delete"] is True
    assert detail_payload["removal_safety"]["can_hard_delete"] is True

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        stored_page = campaign.pages.get("notes/api-field-report")
        assert stored_page is not None
        assert stored_page.title == "API Field Report"

    delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/content/pages/notes/api-field-report",
        headers=api_headers(dm_token),
    )

    assert delete_response.status_code == 200
    assert delete_response.get_json()["deleted"]["page_ref"] == "notes/api-field-report"
    assert not page_path.exists()


def test_api_content_page_management_blocks_deletion_when_page_is_referenced(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-pages-referenced-api")
    target_page_ref = "notes/api-reference-target"
    referencing_page_ref = "notes/api-reference-hub"

    create_target = client.put(
        f"/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "API Reference Target",
                "section": "Notes",
                "type": "note",
                "summary": "A page intended to be linked.",
                "published": True,
                "reveal_after_session": 0,
            },
            "body_markdown": "This target page should be blocked from hard delete when linked.",
        },
    )
    assert create_target.status_code == 200

    create_referrer = client.put(
        f"/api/v1/campaigns/linden-pass/content/pages/{referencing_page_ref}",
        headers=api_headers(dm_token),
        json={
            "metadata": {
                "title": "API Reference Hub",
                "section": "Notes",
                "type": "note",
                "summary": "This page links to the reference target.",
                "published": True,
                "reveal_after_session": 0,
            },
            "body_markdown": "Cross-check with [[API Reference Target]].",
        },
    )
    assert create_referrer.status_code == 200

    list_response = client.get(
        "/api/v1/campaigns/linden-pass/content/pages",
        headers=api_headers(dm_token),
    )

    assert list_response.status_code == 200
    listed_pages = list_response.get_json()["pages"]
    target_listing = next(item for item in listed_pages if item["page_ref"] == target_page_ref)
    assert target_listing["can_hard_delete"] is False
    assert any("Backlinked from API Reference Hub." in blocker for blocker in target_listing["hard_delete_blockers"])

    blocked_delete = client.delete(
        f"/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}",
        headers=api_headers(dm_token),
    )

    assert blocked_delete.status_code == 409
    blocked_payload = blocked_delete.get_json()
    assert blocked_payload["error"]["code"] == "hard_delete_blocked"
    assert blocked_payload["error"]["details"]["removal_safety"]["can_hard_delete"] is False
    assert any(
        "Backlinked from API Reference Hub." in blocker
        for blocker in blocked_payload["error"]["details"]["removal_safety"]["hard_delete_blockers"]
    )

    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    target_page_path = campaigns_dir / "linden-pass" / "content" / "notes" / "api-reference-target.md"
    assert target_page_path.exists()

    forced_delete = client.delete(
        f"/api/v1/campaigns/linden-pass/content/pages/{target_page_ref}",
        headers=api_headers(dm_token),
        json={"force": True},
    )
    assert forced_delete.status_code == 200
    assert forced_delete.get_json()["deleted"]["page_ref"] == target_page_ref
    assert not target_page_path.exists()


def test_api_content_character_management_can_upsert_and_delete_files(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-content-characters-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-content-characters-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    source_character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"

    definition_payload = yaml.safe_load((source_character_dir / "definition.yaml").read_text(encoding="utf-8"))
    import_payload = yaml.safe_load((source_character_dir / "import.yaml").read_text(encoding="utf-8"))
    definition_payload["name"] = "API Scout"
    definition_payload["profile"]["biography_markdown"] = "A remotely managed scout prepared through the API."
    import_payload["source_path"] = "api://campaigns/linden-pass/characters/api-scout"
    import_payload["parser_version"] = "api-test"
    import_payload["import_status"] = "managed"

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters",
        headers=api_headers(player_token),
    )

    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    create_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/api-scout",
        headers=api_headers(dm_token),
        json={
            "definition": definition_payload,
            "import_metadata": import_payload,
        },
    )

    assert create_response.status_code == 200
    character_file = create_response.get_json()["character_file"]
    assert character_file["definition"]["character_slug"] == "api-scout"
    assert character_file["definition"]["name"] == "API Scout"
    assert character_file["definition"]["system"] == "DND-5E"
    assert character_file["state_created"] is True

    list_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters",
        headers=api_headers(dm_token),
    )

    assert list_response.status_code == 200
    listed_slugs = [item["character_slug"] for item in list_response.get_json()["characters"]]
    assert "api-scout" in listed_slugs

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters/api-scout",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    assert detail_response.get_json()["character_file"]["import_metadata"]["parser_version"] == "api-test"
    assert detail_response.get_json()["character_file"]["definition"]["system"] == "DND-5E"

    with app.app_context():
        store = AuthStore()
        store.upsert_character_assignment(users["party"]["id"], "linden-pass", "api-scout")
        state_store = app.extensions["character_state_store"]
        assert state_store.get_state("linden-pass", "api-scout") is not None

    delete_response = client.delete(
        "/api/v1/campaigns/linden-pass/content/characters/api-scout",
        headers=api_headers(dm_token),
    )

    assert delete_response.status_code == 200
    deleted_payload = delete_response.get_json()["deleted"]
    assert deleted_payload["character_slug"] == "api-scout"
    assert deleted_payload["deleted_files"] is True
    assert deleted_payload["deleted_state"] is True
    assert deleted_payload["deleted_assignment"] is True

    with app.app_context():
        store = AuthStore()
        state_store = app.extensions["character_state_store"]
        assert store.get_character_assignment("linden-pass", "api-scout") is None
        assert state_store.get_state("linden-pass", "api-scout") is None

    assert not (campaigns_dir / "linden-pass" / "characters" / "api-scout" / "definition.yaml").exists()


def test_api_content_dnd5e_definition_load_round_trips_unchanged(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-dnd5e-round-trip-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    definition_path = character_dir / "definition.yaml"
    original_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    expected_definition = deepcopy(original_definition)
    expected_definition["system"] = "DND-5E"
    expected_definition["proficiencies"] = {
        "armor": list(original_definition["proficiencies"].get("armor") or []),
        "weapons": list(original_definition["proficiencies"].get("weapons") or []),
        "tools": list(original_definition["proficiencies"].get("tools") or []),
        "languages": list(original_definition["proficiencies"].get("languages") or []),
        "tool_expertise": list(original_definition["proficiencies"].get("tool_expertise") or []),
    }

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters/arden-march",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    loaded_definition = detail_response.get_json()["character_file"]["definition"]
    assert loaded_definition == expected_definition
    assert "xianxia" not in loaded_definition

    with app.app_context():
        record = app.extensions["character_repository"].get_character("linden-pass", "arden-march")
        assert record is not None
        assert record.definition.to_dict() == expected_definition

    save_loaded_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/arden-march",
        headers=api_headers(dm_token),
        json={"definition": loaded_definition},
    )

    assert save_loaded_response.status_code == 200
    round_tripped_definition = save_loaded_response.get_json()["character_file"]["definition"]
    assert round_tripped_definition == expected_definition
    assert yaml.safe_load(definition_path.read_text(encoding="utf-8")) == expected_definition


def test_api_content_xianxia_definition_round_trips_through_save_and_load(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-round-trip-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    config_path = campaigns_dir / "linden-pass" / "campaign.yaml"
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_payload["system"] = "Xianxia"
    config_payload["systems_library"] = "Xianxia"
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    definition_payload = {
        "name": "Round Trip Cultivator",
        "status": "active",
        "system": "xianxia",
        "xianxia": {
            "realm": "Immortal",
            "action_count": "3",
            "honor": "venerable",
            "reputation": "Known among border sects",
            "attributes": {"str": "2", "dex": 1, "con": 3, "int": 0, "wis": 1, "cha": 0},
            "efforts": {
                "basic": 1,
                "weapon": 2,
                "guns_explosive": 0,
                "magic": 1,
                "ultimate": 1,
            },
            "energy_maxima": {"jing": "3", "qi": 2, "shen": 1},
            "yin_yang": {"yin_max": "2", "yang_max": "1"},
            "dao_max": 3,
            "insight": {"available": "5", "spent": "1"},
            "durability": {
                "hp_max": "18",
                "stance_max": "14",
                "manual_armor_bonus": "2",
                "defense": "99",
            },
            "skills": {"trained": ["Tea Ceremony", "Strategy", "Tea Ceremony"]},
            "equipment": {
                "necessary_weapons": [{"name": "Jian", "reason": "Required by Heavenly Palm"}],
                "necessary_tools": ["Calligraphy brush"],
            },
            "martial_arts": [
                {
                    "systems_ref": {"slug": "heavenly-palm", "entry_type": "martial_art"},
                    "current_rank": "Novice",
                    "learned_rank_refs": ["xianxia:heavenly-palm:initiate"],
                }
            ],
            "generic_techniques": [
                {"systems_ref": {"slug": "qi-blast", "entry_type": "generic_technique"}}
            ],
            "variants": [{"variant_type": "karmic_constraint", "name": "Falling Palm Oath"}],
            "dao_immolating_records": {
                "prepared": [{"name": "Ashen Bell"}],
                "history": [{"name": "River-Cleaving Spark", "approval_status": "approved"}],
            },
            "approval_requests": [{"request_type": "ascendant_art", "status": "pending"}],
            "companions": [{"name": "Ink phantom", "source_ref": "xianxia:ink-stained-historian"}],
            "advancement_history": [{"action": "gather_insight", "amount": 1}],
        },
    }

    create_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/round-trip-cultivator",
        headers=api_headers(dm_token),
        json={"definition": definition_payload},
    )

    assert create_response.status_code == 200
    create_character_file = create_response.get_json()["character_file"]
    assert create_character_file["state_created"] is True
    saved_definition = create_character_file["definition"]
    saved_xianxia = saved_definition["xianxia"]

    assert saved_definition["campaign_slug"] == "linden-pass"
    assert saved_definition["character_slug"] == "round-trip-cultivator"
    assert saved_definition["system"] == "Xianxia"
    assert saved_xianxia["schema_version"] == XIANXIA_CHARACTER_DEFINITION_SCHEMA_VERSION
    assert saved_xianxia["realm"] == "Immortal"
    assert saved_xianxia["actions_per_turn"] == 3
    assert saved_xianxia["honor"] == "Venerable"
    assert saved_xianxia["attributes"]["str"] == 2
    assert saved_xianxia["energies"]["jing"] == {"max": 3}
    assert saved_xianxia["durability"]["defense"] == 15
    assert saved_xianxia["skills"]["trained"] == ["Tea Ceremony", "Strategy"]
    assert saved_xianxia["equipment"]["necessary_tools"] == [{"name": "Calligraphy brush"}]
    assert saved_xianxia["dao_immolating_techniques"]["use_history"][0]["name"] == "River-Cleaving Spark"
    assert "vitals" not in saved_xianxia
    assert "active_stance" not in saved_xianxia
    assert "notes" not in saved_xianxia

    detail_response = client.get(
        "/api/v1/campaigns/linden-pass/content/characters/round-trip-cultivator",
        headers=api_headers(dm_token),
    )

    assert detail_response.status_code == 200
    loaded_definition = detail_response.get_json()["character_file"]["definition"]
    assert loaded_definition == saved_definition

    definition_path = (
        campaigns_dir
        / "linden-pass"
        / "characters"
        / "round-trip-cultivator"
        / "definition.yaml"
    )
    saved_file_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    assert tuple(saved_file_definition["xianxia"]) == XIANXIA_DEFINITION_FIELD_KEYS
    assert saved_file_definition == saved_definition

    with app.app_context():
        record = app.extensions["character_repository"].get_character(
            "linden-pass",
            "round-trip-cultivator",
        )
        assert record is not None
        assert record.definition.to_dict() == saved_definition

    save_loaded_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/round-trip-cultivator",
        headers=api_headers(dm_token),
        json={"definition": loaded_definition},
    )

    assert save_loaded_response.status_code == 200
    round_tripped_file = save_loaded_response.get_json()["character_file"]
    assert round_tripped_file["state_created"] is False
    assert round_tripped_file["definition"] == saved_definition
    assert yaml.safe_load(definition_path.read_text(encoding="utf-8")) == saved_definition


def test_api_content_xianxia_definition_update_preserves_sqlite_mutable_state_split(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-character-split-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    config_path = campaigns_dir / "linden-pass" / "campaign.yaml"
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_payload["system"] = "Xianxia"
    config_payload["systems_library"] = "Xianxia"
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    definition_payload = {
        "name": "API Cultivator",
        "status": "active",
        "system": "xianxia",
        "xianxia": {
            "realm": "Mortal",
            "energy_maxima": {"jing": 3, "qi": 2, "shen": 1},
            "yin_yang": {"yin_max": 2, "yang_max": 1},
            "dao_max": 3,
            "durability": {
                "hp_max": 18,
                "stance_max": 12,
                "manual_armor_bonus": 1,
                "defense": 11,
            },
            "trained_skills": ["Tea Ceremony"],
            "necessary_weapons": ["Jian"],
            "martial_arts": [{"name": "Heavenly Palm", "current_rank": "Initiate"}],
        },
    }

    create_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/api-cultivator",
        headers=api_headers(dm_token),
        json={"definition": definition_payload},
    )

    assert create_response.status_code == 200
    assert create_response.get_json()["character_file"]["state_created"] is True

    with app.app_context():
        repository = app.extensions["character_repository"]
        state_store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", "api-cultivator")
        assert record is not None
        mutable_state = deepcopy(record.state_record.state)
        mutable_state["vitals"]["current_hp"] = 7
        mutable_state["xianxia"]["vitals"]["current_hp"] = 7
        mutable_state["xianxia"]["vitals"]["current_stance"] = 5
        mutable_state["xianxia"]["energies"]["jing"]["current"] = 2
        mutable_state["xianxia"]["yin_yang"]["yin_current"] = 1
        mutable_state["xianxia"]["dao"]["current"] = 2
        mutable_state["xianxia"]["active_stance"] = {"name": "Stone Root"}
        mutable_state["notes"]["player_notes_markdown"] = "Keep the manual pool edits in SQLite."
        updated_state = state_store.replace_state(
            record.definition,
            mutable_state,
            expected_revision=record.state_record.revision,
        )
        edited_revision = updated_state.revision

    updated_definition_payload = deepcopy(definition_payload)
    updated_definition_payload["xianxia"]["energy_maxima"] = {"jing": 1, "qi": 2, "shen": 1}
    updated_definition_payload["xianxia"]["yin_yang"] = {"yin_max": 1, "yang_max": 1}
    updated_definition_payload["xianxia"]["durability"] = {
        "hp_max": 6,
        "stance_max": 4,
        "manual_armor_bonus": 1,
        "defense": 11,
    }

    update_response = client.put(
        "/api/v1/campaigns/linden-pass/content/characters/api-cultivator",
        headers=api_headers(dm_token),
        json={"definition": updated_definition_payload},
    )

    assert update_response.status_code == 200
    assert update_response.get_json()["character_file"]["state_created"] is False

    definition_path = campaigns_dir / "linden-pass" / "characters" / "api-cultivator" / "definition.yaml"
    saved_definition = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    saved_xianxia = saved_definition["xianxia"]
    assert saved_xianxia["durability"]["hp_max"] == 6
    assert saved_xianxia["durability"]["stance_max"] == 4
    assert saved_xianxia["energies"]["jing"] == {"max": 1}
    assert "vitals" not in saved_xianxia
    assert "active_stance" not in saved_xianxia
    assert "notes" not in saved_xianxia
    assert "hp_current" not in saved_definition

    with app.app_context():
        refreshed_record = app.extensions["character_repository"].get_character("linden-pass", "api-cultivator")
        assert refreshed_record is not None
        refreshed_state = refreshed_record.state_record.state

    assert refreshed_record.state_record.revision == edited_revision + 1
    assert refreshed_state["vitals"] == {"current_hp": 6, "temp_hp": 0}
    assert refreshed_state["xianxia"]["vitals"] == {
        "current_hp": 6,
        "temp_hp": 0,
        "current_stance": 4,
        "temp_stance": 0,
    }
    assert refreshed_state["xianxia"]["energies"]["jing"] == {"current": 1}
    assert refreshed_state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 1}
    assert refreshed_state["xianxia"]["dao"] == {"current": 2}
    assert refreshed_state["xianxia"]["active_stance"] == {"name": "Stone Root"}
    assert refreshed_state["notes"]["player_notes_markdown"] == "Keep the manual pool edits in SQLite."


def test_api_content_config_and_assets_refresh_repository_and_manage_files(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-config-assets-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-config-assets-api")
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])

    blocked_config = client.get(
        "/api/v1/campaigns/linden-pass/content/config",
        headers=api_headers(player_token),
    )
    assert blocked_config.status_code == 403

    config_response = client.get(
        "/api/v1/campaigns/linden-pass/content/config",
        headers=api_headers(dm_token),
    )
    assert config_response.status_code == 200
    assert config_response.get_json()["config_file"]["config"]["current_session"] == 2

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert campaign.current_session == 2
        assert campaign.get_visible_page("sessions/session-3-stormglass-heist") is None

    update_response = client.patch(
        "/api/v1/campaigns/linden-pass/content/config",
        headers=api_headers(dm_token),
        json={
            "config": {
                "current_session": 3,
                "summary": "Updated through the API for repository refresh coverage.",
            }
        },
    )
    assert update_response.status_code == 200
    updated_config = update_response.get_json()["config_file"]["config"]
    assert updated_config["current_session"] == 3
    assert "repository refresh coverage" in updated_config["summary"]

    campaign_detail = client.get("/api/v1/campaigns/linden-pass", headers=api_headers(dm_token))
    assert campaign_detail.status_code == 200
    campaign_detail_payload = campaign_detail.get_json()
    assert campaign_detail_payload["campaign"]["current_session"] == 3
    assert campaign_detail_payload["permissions"]["can_manage_visibility"] is True

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert campaign.current_session == 3
        assert campaign.get_visible_page("sessions/session-3-stormglass-heist") is not None

    blocked_assets = client.get(
        "/api/v1/campaigns/linden-pass/content/assets",
        headers=api_headers(player_token),
    )
    assert blocked_assets.status_code == 403

    asset_bytes = b"API managed asset bytes"
    asset_response = client.put(
        "/api/v1/campaigns/linden-pass/content/assets/notes/api-sigil.txt",
        headers=api_headers(dm_token),
        json={
            "asset_file": {
                "filename": "api-sigil.txt",
                "data_base64": base64.b64encode(asset_bytes).decode("ascii"),
            }
        },
    )
    assert asset_response.status_code == 200
    assert asset_response.get_json()["asset_file"]["asset_ref"] == "notes/api-sigil.txt"

    asset_list = client.get(
        "/api/v1/campaigns/linden-pass/content/assets",
        headers=api_headers(dm_token),
    )
    assert asset_list.status_code == 200
    asset_refs = [item["asset_ref"] for item in asset_list.get_json()["assets"]]
    assert "notes/api-sigil.txt" in asset_refs

    asset_detail = client.get(
        "/api/v1/campaigns/linden-pass/content/assets/notes/api-sigil.txt",
        headers=api_headers(dm_token),
    )
    assert asset_detail.status_code == 200
    assert base64.b64decode(asset_detail.get_json()["asset_file"]["data_base64"]) == asset_bytes

    asset_path = campaigns_dir / "linden-pass" / "assets" / "notes" / "api-sigil.txt"
    assert asset_path.exists()
    assert asset_path.read_bytes() == asset_bytes

    delete_asset = client.delete(
        "/api/v1/campaigns/linden-pass/content/assets/notes/api-sigil.txt",
        headers=api_headers(dm_token),
    )
    assert delete_asset.status_code == 200
    assert delete_asset.get_json()["deleted"]["asset_ref"] == "notes/api-sigil.txt"
    assert not asset_path.exists()


def test_api_content_config_can_select_xianxia_system_and_library(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-xianxia-config-api")

    update_response = client.patch(
        "/api/v1/campaigns/linden-pass/content/config",
        headers=api_headers(dm_token),
        json={
            "config": {
                "system": "xianxia",
                "systems_library": "xianxia",
            }
        },
    )

    assert update_response.status_code == 200
    updated_config = update_response.get_json()["config_file"]["config"]
    assert updated_config["system"] == "Xianxia"
    assert updated_config["systems_library"] == "Xianxia"

    campaign_detail = client.get("/api/v1/campaigns/linden-pass", headers=api_headers(dm_token))
    assert campaign_detail.status_code == 200
    campaign_payload = campaign_detail.get_json()["campaign"]
    assert campaign_payload["system"] == "Xianxia"
    assert campaign_payload["systems_library_slug"] == "Xianxia"

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert campaign.system == "Xianxia"
        assert campaign.systems_library_slug == "Xianxia"
        assert app.extensions["systems_service"].get_campaign_library_slug("linden-pass") == "Xianxia"


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


def test_api_systems_import_endpoints_require_admin_and_record_runs(client, app, users, tmp_path):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-api")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-import-api")
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


def test_api_combat_endpoints_allow_dm_management_and_owner_player_vitals_updates(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-combat-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-combat-api")

    add_player = client.post(
        "/api/v1/campaigns/linden-pass/combat/player-combatants",
        headers=api_headers(dm_token),
        json={"character_slug": "arden-march", "turn_value": 18},
    )
    assert add_player.status_code == 200
    arden = _find_tracker_combatant(add_player.get_json(), character_slug="arden-march")
    assert arden is not None
    assert arden["turn_value"] == 18
    assert arden["state_revision"] is not None

    combatant_id = arden["id"]
    starting_revision = arden["state_revision"]

    owner_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{combatant_id}/vitals",
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision,
            "current_hp": 35,
            "temp_hp": 4,
        },
    )
    assert owner_update.status_code == 200
    updated_arden = _find_tracker_combatant(owner_update.get_json(), character_slug="arden-march")
    assert updated_arden is not None
    assert updated_arden["current_hp"] == 35
    assert updated_arden["temp_hp"] == 4
    assert updated_arden["state_revision"] == starting_revision + 1

    blocked_ownerless = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{combatant_id}/vitals",
        headers=api_headers(player_token),
        json={
            "expected_revision": starting_revision + 1,
            "current_hp": 31,
            "temp_hp": 0,
        },
    )
    assert blocked_ownerless.status_code == 403

    add_npc = client.post(
        "/api/v1/campaigns/linden-pass/combat/npc-combatants",
        headers=api_headers(dm_token),
        json={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
    )
    assert add_npc.status_code == 200
    hound = _find_tracker_combatant(add_npc.get_json(), name="Clockwork Hound")
    assert hound is not None

    resources_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/resources",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": hound["combatant_revision"],
            "has_action": True,
            "has_bonus_action": False,
            "has_reaction": False,
            "movement_remaining": 10,
        },
    )
    assert resources_update.status_code == 200
    refreshed_hound = _find_tracker_combatant(resources_update.get_json(), name="Clockwork Hound")
    assert refreshed_hound is not None
    assert refreshed_hound["movement_remaining"] == 10
    assert refreshed_hound["has_action"] is True
    assert refreshed_hound["has_bonus_action"] is False

    condition_update = client.post(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/conditions",
        headers=api_headers(dm_token),
        json={"name": "Restrained", "duration_text": "Until the end of round 2"},
    )
    assert condition_update.status_code == 200
    conditioned_hound = _find_tracker_combatant(condition_update.get_json(), name="Clockwork Hound")
    assert conditioned_hound is not None
    assert conditioned_hound["conditions"][0]["name"] == "Restrained"

    focused_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/vitals?combatant={hound['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": conditioned_hound["combatant_revision"],
            "current_hp": 19,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
    )
    assert focused_update.status_code == 200
    assert focused_update.get_json()["selected_combatant"]["id"] == hound["id"]
    assert focused_update.get_json()["selected_combatant"]["current_hp"] == 19

    live_state = client.get(
        "/api/v1/campaigns/linden-pass/combat/live-state",
        headers=api_headers(dm_token),
    )
    assert live_state.status_code == 200
    assert live_state.get_json()["tracker"]["combatant_count"] == 2


def test_api_combat_read_exposes_gen2_live_selection_and_fallback_links(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-gen2-read-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="owner-combat-gen2-read-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-combat-gen2-read-api")

    add_player = client.post(
        "/api/v1/campaigns/linden-pass/combat/player-combatants",
        headers=api_headers(dm_token),
        json={"character_slug": "arden-march", "turn_value": 18},
    )
    assert add_player.status_code == 200
    arden = _find_tracker_combatant(add_player.get_json(), character_slug="arden-march")
    assert arden is not None

    add_npc = client.post(
        "/api/v1/campaigns/linden-pass/combat/npc-combatants",
        headers=api_headers(dm_token),
        json={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
    )
    assert add_npc.status_code == 200
    hound = _find_tracker_combatant(add_npc.get_json(), name="Clockwork Hound")
    assert hound is not None

    owner_read = client.get(
        f"/api/v1/campaigns/linden-pass/combat?combatant={hound['id']}",
        headers=api_headers(owner_token),
    )
    assert owner_read.status_code == 200
    payload = owner_read.get_json()

    assert payload["ok"] is True
    assert payload["changed"] is True
    assert payload["combat_system_supported"] is True
    assert isinstance(payload["live_revision"], int)
    assert isinstance(payload["live_view_token"], str)
    assert len(payload["live_view_token"]) == 12
    assert payload["selected_combatant"]["name"] == "Clockwork Hound"
    assert payload["selected_combatant_id"] == hound["id"]
    assert payload["selected_player_character"]["character_slug"] == "arden-march"
    combat_section_labels = [section["label"] for section in payload["selected_player_combat_sections"]]
    assert "Attacks" in combat_section_labels
    assert "Features" in combat_section_labels
    attacks_section = next(
        section for section in payload["selected_player_combat_sections"] if section["label"] == "Attacks"
    )
    assert [attack["name"] for attack in attacks_section["attacks"]] == [
        "Light Crossbow",
        "Quarterstaff",
        "Quarterstaff (two-handed)",
    ]
    assert payload["player_character_targets"] == [
        {
            "combatant_id": arden["id"],
            "character_slug": "arden-march",
            "name": "Arden March",
            "subtitle": "Sorcerer 5",
            "is_selected": True,
            "href": f"/app-next/campaigns/linden-pass/combat?combatant={arden['id']}",
            "flask_href": f"/campaigns/linden-pass/combat?combatant={arden['id']}",
        }
    ]
    assert payload["links"]["flask_combat_url"] == "/campaigns/linden-pass/combat"
    assert payload["links"]["flask_dm_status_url"] == ""
    assert payload["poll_settings"]["active_interval_ms"] == 500

    owner_character_list = client.get(
        "/api/v1/campaigns/linden-pass/characters",
        headers=api_headers(owner_token),
    )
    assert owner_character_list.status_code == 200
    assert [character["slug"] for character in owner_character_list.get_json()["characters"]] == ["arden-march"]

    owner_character_detail = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(owner_token),
    )
    assert owner_character_detail.status_code == 200

    unassigned_character_detail = client.get(
        "/api/v1/campaigns/linden-pass/characters/arden-march",
        headers=api_headers(player_token),
    )
    assert unassigned_character_detail.status_code == 403

    unchanged = client.get(
        f"/api/v1/campaigns/linden-pass/combat?combatant={hound['id']}",
        headers={
            **api_headers(owner_token),
            "X-Live-Revision": str(payload["live_revision"]),
            "X-Live-View-Token": payload["live_view_token"],
        },
    )
    assert unchanged.status_code == 200
    unchanged_payload = unchanged.get_json()
    assert unchanged_payload["changed"] is False
    assert unchanged_payload["live_revision"] == payload["live_revision"]
    assert unchanged_payload["live_view_token"] == payload["live_view_token"]
    assert set(unchanged_payload.keys()) == {"ok", "changed", "live_revision", "live_view_token"}

    dm_read = client.get("/api/v1/campaigns/linden-pass/combat", headers=api_headers(dm_token))
    assert dm_read.status_code == 200
    dm_payload = dm_read.get_json()
    dm_links = dm_payload["links"]
    assert dm_links["flask_dm_status_url"] == "/campaigns/linden-pass/combat/dm"
    assert dm_links["flask_dm_controls_url"] == "/campaigns/linden-pass/combat/dm?view=controls"
    assert "Restrained" in dm_payload["combat_condition_options"]
    assert isinstance(dm_payload["available_character_choices"], list)
    assert isinstance(dm_payload["available_statblock_choices"], list)


def test_api_combat_read_reports_unsupported_system_without_live_poll_targets(client, app, users):
    _configure_xianxia_campaign(app)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-gen2-xianxia-api")

    response = client.get("/api/v1/campaigns/linden-pass/combat", headers=api_headers(dm_token))
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["combat_system_supported"] is False
    assert payload["live_revision"] == 0
    assert payload["tracker"]["combatant_count"] == 0
    assert payload["selected_combatant"] is None
    assert payload["selected_player_character"] is None
    assert payload["player_character_targets"] == []
    assert payload["links"]["flask_combat_url"] == "/campaigns/linden-pass/combat"
    assert payload["links"]["flask_campaign_url"] == "/campaigns/linden-pass"
    assert payload["links"]["flask_characters_url"] == "/campaigns/linden-pass/characters"
    assert payload["links"]["flask_session_url"] == "/campaigns/linden-pass/session"


def test_api_combat_statblock_seed_uses_dex_modifier_for_tie_breaker(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-statblock-api")
    with app.app_context():
        statblock = app.extensions["campaign_dm_content_service"].create_statblock(
            "linden-pass",
            filename="alert-guard.md",
            data_blob=b"""---
title: Alert Guard
armor_class: 14
hp: 24
speed: 30 ft.
initiative_bonus: 7
---

STR 10 (+0)  DEX 14 (+2)  CON 12 (+1)  INT 10 (+0)  WIS 10 (+0)  CHA 10 (+0)

## Actions

### Spear

+4 to hit, 5 piercing damage.
""",
            created_by_user_id=users["dm"]["id"],
        )

    response = client.post(
        "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
        headers=api_headers(dm_token),
        json={"statblock_id": statblock.id},
    )

    assert response.status_code == 200
    combatant = _find_tracker_combatant(response.get_json(), name="Alert Guard")
    assert combatant is not None
    assert combatant["turn_value"] == 7
    assert combatant["initiative_bonus_label"] == "+7"
    assert combatant["dexterity_modifier"] == 2
    assert combatant["dexterity_modifier_label"] == "+2"


def test_api_combat_statblock_npc_resources_seed_patch_and_gate_permissions(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-npc-resources-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-combat-npc-resources-api")
    with app.app_context():
        statblock = app.extensions["campaign_dm_content_service"].create_statblock(
            "linden-pass",
            filename="hex-adept.md",
            data_blob=b"""---
title: Hex Adept
armor_class: 13
hp: 33
speed: 30 ft.
initiative_bonus: 2
---

STR 10 (+0)  DEX 14 (+2)  CON 12 (+1)  INT 10 (+0)  WIS 10 (+0)  CHA 16 (+3)

## Traits

### Innate Spellcasting

At will: detect magic, mage hand.
3/day each: misty step, charm person.
1/day: dimension door.

### Legendary Resistance (3/Day)

If the adept fails a saving throw, it can choose to succeed instead.

## Actions

### Fire Breath (Recharge 5-6)

The adept exhales fire in a 15-foot cone.
""",
            created_by_user_id=users["dm"]["id"],
        )

    add_response = client.post(
        "/api/v1/campaigns/linden-pass/combat/statblock-combatants",
        headers=api_headers(dm_token),
        json={"statblock_id": statblock.id},
    )
    assert add_response.status_code == 200
    adept = _find_tracker_combatant(add_response.get_json(), name="Hex Adept")
    assert adept is not None
    counters = {counter["label"].lower(): counter for counter in adept["npc_resource_counters"]}
    assert counters["misty step"]["current_value"] == 3
    assert counters["misty step"]["max_value"] == 3
    assert counters["misty step"]["reset_label"] == "Per day"
    assert counters["misty step"]["can_edit"] is True
    assert counters["charm person"]["max_value"] == 3
    assert counters["dimension door"]["max_value"] == 1
    assert counters["legendary resistance"]["max_value"] == 3
    notes = {(note["label"], note["note"]) for note in adept["npc_resource_notes"]}
    assert ("At-will spellcasting", "detect magic, mage hand") in notes
    assert ("Fire Breath", "Recharge 5-6") in notes

    player_blocked = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{adept['id']}/npc-resources",
        headers=api_headers(player_token),
        json={
            "expected_combatant_revision": adept["combatant_revision"],
            "counters": [{"resource_key": counters["misty step"]["resource_key"], "current_value": 2}],
        },
    )
    assert player_blocked.status_code == 403

    update_response = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{adept['id']}/npc-resources?combatant={adept['id']}",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": adept["combatant_revision"],
            "counters": [{"resource_key": counters["misty step"]["resource_key"], "current_value": 1}],
        },
    )
    assert update_response.status_code == 200
    updated_adept = update_response.get_json()["selected_combatant"]
    updated_counters = {counter["label"].lower(): counter for counter in updated_adept["npc_resource_counters"]}
    assert updated_counters["misty step"]["current_value"] == 1
    assert updated_adept["combatant_revision"] == adept["combatant_revision"] + 1

    stale_response = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{adept['id']}/npc-resources",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": adept["combatant_revision"],
            "counters": [{"resource_key": counters["misty step"]["resource_key"], "current_value": 0}],
        },
    )
    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"]["code"] == "state_conflict"


def test_api_combat_resource_update_rejects_stale_combatant_revision(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-conflict-api")

    add_npc = client.post(
        "/api/v1/campaigns/linden-pass/combat/npc-combatants",
        headers=api_headers(dm_token),
        json={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
    )
    assert add_npc.status_code == 200
    hound = _find_tracker_combatant(add_npc.get_json(), name="Clockwork Hound")
    assert hound is not None

    first_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/resources",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": hound["combatant_revision"],
            "has_action": True,
            "has_bonus_action": True,
            "has_reaction": True,
            "movement_remaining": 10,
        },
    )
    assert first_update.status_code == 200

    stale_update = client.patch(
        f"/api/v1/campaigns/linden-pass/combat/combatants/{hound['id']}/resources",
        headers=api_headers(dm_token),
        json={
            "expected_combatant_revision": hound["combatant_revision"],
            "has_action": True,
            "has_bonus_action": False,
            "has_reaction": False,
            "movement_remaining": 5,
        },
    )
    assert stale_update.status_code == 409
    assert stale_update.get_json()["error"]["code"] == "state_conflict"
    assert stale_update.get_json()["error"]["message"] == (
        "This combatant changed in another combat view. Refresh and try again."
    )

    live_state = client.get("/api/v1/campaigns/linden-pass/combat/live-state", headers=api_headers(dm_token))
    assert live_state.status_code == 200
    refreshed_hound = _find_tracker_combatant(live_state.get_json(), name="Clockwork Hound")
    assert refreshed_hound is not None
    assert refreshed_hound["movement_remaining"] == 10
    assert refreshed_hound["has_bonus_action"] is True
    assert refreshed_hound["has_reaction"] is True


def test_api_combat_systems_monster_search_and_add_use_imported_entries(client, app, users, tmp_path):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-systems-api")

    search_response = client.get(
        "/api/v1/campaigns/linden-pass/combat/systems-monsters/search?q=gob",
        headers=api_headers(dm_token),
    )
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching monster."
    assert search_payload["results"][0]["entry_key"] == goblin_entry_key
    assert search_payload["results"][0]["title"] == "Goblin"

    add_response = client.post(
        "/api/v1/campaigns/linden-pass/combat/systems-monsters",
        headers=api_headers(dm_token),
        json={"entry_key": goblin_entry_key},
    )
    assert add_response.status_code == 200
    goblin = _find_tracker_combatant(add_response.get_json(), name="Goblin")
    assert goblin is not None
    assert goblin["turn_value"] == 2
    assert goblin["current_hp"] == 7
    assert goblin["movement_total"] == 30


def test_api_combat_systems_monster_resources_seed_from_limited_use_traits(client, app, users, tmp_path):
    data_root = tmp_path / "api-systems-npc-resources-source"
    _write_json(
        data_root / "data/bestiary/bestiary-mm.json",
        {
            "monster": [
                {
                    "name": "Hex Adept",
                    "source": "MM",
                    "page": 999,
                    "size": ["M"],
                    "type": {"type": "humanoid"},
                    "alignment": ["N"],
                    "ac": [{"ac": 13}],
                    "hp": {"average": 33, "formula": "6d8 + 6"},
                    "speed": {"walk": 30},
                    "str": 10,
                    "dex": 14,
                    "con": 12,
                    "int": 10,
                    "wis": 10,
                    "cha": 16,
                    "trait": [
                        {
                            "name": "Innate Spellcasting",
                            "entries": [
                                "At will: {@spell detect magic}, {@spell mage hand}.",
                                "3/day each: {@spell misty step}, {@spell charm person}.",
                            ],
                        },
                        {
                            "name": "Legendary Resistance (3/Day)",
                            "entries": ["If the adept fails a saving throw, it can choose to succeed instead."],
                        },
                    ],
                    "action": [
                        {
                            "name": "Arcane Burst (Recharge 5-6)",
                            "entries": ["The adept releases stored force."],
                        }
                    ],
                }
            ]
        },
    )
    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MM", entry_types=["monster"])
        entry = next(
            item
            for item in app.extensions["systems_service"].list_monster_entries_for_campaign("linden-pass")
            if item.title == "Hex Adept"
        )
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-combat-systems-npc-resources-api")

    add_response = client.post(
        "/api/v1/campaigns/linden-pass/combat/systems-monsters",
        headers=api_headers(dm_token),
        json={"entry_key": entry.entry_key},
    )

    assert add_response.status_code == 200
    adept = _find_tracker_combatant(add_response.get_json(), name="Hex Adept")
    assert adept is not None
    counters = {counter["label"].lower(): counter for counter in adept["npc_resource_counters"]}
    assert counters["misty step"]["max_value"] == 3
    assert counters["charm person"]["current_value"] == 3
    assert counters["legendary resistance"]["source_label"] == "Systems MM"
    notes = {(note["label"], note["note"]) for note in adept["npc_resource_notes"]}
    assert ("At-will spellcasting", "detect magic, mage hand") in notes
    assert ("Arcane Burst", "Recharge 5-6") in notes

