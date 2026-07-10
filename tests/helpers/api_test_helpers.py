from __future__ import annotations

from tests.helpers.character_state_helpers import (
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
)
from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
    _valid_xianxia_manual_import_data,
)
from tests.helpers.systems_import_helpers import (
    _build_systems_import_archive,
    _build_unsafe_systems_import_archive,
    _import_systems_goblin,
)
from tests.helpers.systems_seed_helpers import (
    _seed_systems_item_entry,
    _seed_systems_spell_entry,
    _systems_ref,
)
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
from tests.sample_data import approved_innovators_bolt_item_mechanics


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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def _find_tracker_combatant(payload: dict[str, object], *, name: str | None = None, character_slug: str | None = None):
    for combatant in payload["tracker"]["combatants"]:
        if name is not None and combatant["name"] == name:
            return combatant
        if character_slug is not None and combatant["character_slug"] == character_slug:
            return combatant
    return None
