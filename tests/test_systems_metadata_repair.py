from __future__ import annotations

from player_wiki.character_builder import _build_item_catalog, normalize_definition_to_native_model
from player_wiki.character_models import CharacterDefinition
from player_wiki.system_policy import DND_5E_SYSTEM_CODE
from player_wiki.systems_metadata_repair import repair_dnd5e_item_metadata


def _systems_ref(entry) -> dict[str, str]:
    return {
        "entry_key": entry.entry_key,
        "entry_type": entry.entry_type,
        "slug": entry.slug,
        "title": entry.title,
        "source_id": entry.source_id,
    }


def _minimal_imported_character_definition() -> CharacterDefinition:
    return CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug="flair-like",
        name="Flair Like",
        status="active",
        profile={
            "sheet_name": "Flair Like",
            "display_name": "Flair Like",
            "class_level_text": "Fighter 3",
            "classes": [
                {
                    "class_name": "Fighter",
                    "subclass_name": "Champion",
                    "level": 3,
                    "systems_ref": {
                        "entry_key": "dnd-5e|class|phb|fighter",
                        "entry_type": "class",
                        "title": "Fighter",
                        "slug": "phb-class-fighter",
                        "source_id": "PHB",
                    },
                }
            ],
            "class_ref": {
                "entry_key": "dnd-5e|class|phb|fighter",
                "entry_type": "class",
                "title": "Fighter",
                "slug": "phb-class-fighter",
                "source_id": "PHB",
            },
            "subclass_ref": {
                "entry_key": "dnd-5e|subclass|phb|champion",
                "entry_type": "subclass",
                "title": "Champion",
                "slug": "phb-subclass-champion",
                "source_id": "PHB",
            },
            "species": "Human",
            "background": "Acolyte",
            "alignment": "Neutral",
            "experience_model": "Milestone",
            "size": "Medium",
            "biography_markdown": "",
            "personality_markdown": "",
        },
        stats={
            "max_hp": 28,
            "armor_class": 12,
            "initiative_bonus": 1,
            "speed": "30 ft.",
            "proficiency_bonus": 2,
            "passive_perception": 12,
            "passive_insight": 11,
            "passive_investigation": 10,
            "ability_scores": {
                "str": {"score": 16, "modifier": 3, "save_bonus": 5},
                "dex": {"score": 12, "modifier": 1, "save_bonus": 1},
                "con": {"score": 14, "modifier": 2, "save_bonus": 4},
                "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                "wis": {"score": 13, "modifier": 1, "save_bonus": 1},
                "cha": {"score": 8, "modifier": -1, "save_bonus": -1},
            },
        },
        skills=[],
        proficiencies={"armor": [], "weapons": [], "tools": [], "languages": ["Common"]},
        attacks=[],
        features=[],
        spellcasting={
            "spellcasting_class": "",
            "spellcasting_ability": "",
            "spell_save_dc": None,
            "spell_attack_bonus": None,
            "slot_progression": [],
            "spells": [],
        },
        equipment_catalog=[],
        reference_notes={
            "additional_notes_markdown": "",
            "allies_and_organizations_markdown": "",
            "custom_sections": [],
        },
        resource_templates=[],
        source={
            "source_path": "imports://flair-like.md",
            "source_type": "markdown_character_sheet",
            "imported_from": "Flair Like.md",
            "imported_at": "2026-03-31T00:00:00Z",
            "parse_warnings": [],
        },
    )


def test_repair_dnd5e_item_metadata_backfills_magic_armor_for_character_math(app):
    with app.app_context():
        store = app.extensions["systems_store"]
        store.upsert_library(DND_5E_SYSTEM_CODE, title="DND 5E", system_code=DND_5E_SYSTEM_CODE)
        store.upsert_source(
            DND_5E_SYSTEM_CODE,
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_source(
            DND_5E_SYSTEM_CODE,
            "DMG",
            title="Dungeon Master's Guide",
            license_class="proprietary_private",
            public_visibility_allowed=False,
            requires_unofficial_notice=True,
        )
        store.upsert_entry(
            DND_5E_SYSTEM_CODE,
            "PHB",
            entry_key="dnd-5e|item|phb|chainmail",
            entry_type="item",
            slug="phb-item-chainmail",
            title="Chain Mail",
            search_text="chain mail",
            player_safe_default=True,
            metadata={
                "type": "HA",
                "ac": None,
                "armor": False,
                "strength": None,
                "stealth_disadvantage": False,
                "rarity": "none",
            },
            body={},
            rendered_html="",
        )
        store.upsert_entry(
            DND_5E_SYSTEM_CODE,
            "DMG",
            entry_key="dnd-5e|item|dmg|1chainmail",
            entry_type="item",
            slug="dmg-item-1chainmail",
            title="+1 Chain Mail",
            search_text="+1 chain mail",
            player_safe_default=False,
            metadata={
                "type": "HA",
                "ac": None,
                "armor": None,
                "base_item": "Chain Mail|PHB",
                "bonus_ac": 0,
                "rarity": "rare",
            },
            body={},
            rendered_html="",
        )

        dry_run = repair_dnd5e_item_metadata(store, dry_run=True, source_ids=["dmg"])
        unchanged_magic = store.get_entry(DND_5E_SYSTEM_CODE, "dnd-5e|item|dmg|1chainmail")

        assert dry_run.scanned_count == 1
        assert dry_run.repairable_count == 1
        assert unchanged_magic is not None
        assert unchanged_magic.metadata["ac"] is None

        result = repair_dnd5e_item_metadata(store, source_ids=["PHB", "DMG"])
        repaired_chain_mail = store.get_entry(DND_5E_SYSTEM_CODE, "dnd-5e|item|phb|chainmail")
        repaired_magic = store.get_entry(DND_5E_SYSTEM_CODE, "dnd-5e|item|dmg|1chainmail")

        assert result.scanned_count == 2
        assert result.repairable_count == 2
        assert result.repaired_count == 2
        assert repaired_chain_mail is not None
        assert repaired_chain_mail.metadata["ac"] == 16
        assert repaired_chain_mail.metadata["armor"] is True
        assert repaired_chain_mail.metadata["strength"] == 13
        assert repaired_chain_mail.metadata["stealth_disadvantage"] is True
        assert repaired_magic is not None
        assert repaired_magic.metadata["ac"] == 16
        assert repaired_magic.metadata["armor"] is True
        assert repaired_magic.metadata["bonus_ac"] == "+1"
        assert repaired_magic.metadata["base_item"] == "Chain Mail|PHB"
        assert repaired_magic.metadata["strength"] == 13
        assert repaired_magic.metadata["stealth_disadvantage"] is True

        clean_second_pass = repair_dnd5e_item_metadata(store, source_ids=["PHB", "DMG"])
        assert clean_second_pass.repairable_count == 0

        definition = _minimal_imported_character_definition()
        definition.equipment_catalog = [
            {
                "id": "chain-mail-1-1",
                "name": "Chain Mail, +1",
                "default_quantity": 1,
                "weight": "55 lb.",
                "notes": "",
                "is_equipped": True,
                "systems_ref": _systems_ref(repaired_magic),
            }
        ]

        normalized = normalize_definition_to_native_model(
            definition,
            item_catalog=_build_item_catalog([repaired_magic]),
        )

        assert normalized.stats["armor_class"] == 17


def test_repair_dnd5e_item_metadata_backfills_phb_weapon_metadata(app):
    with app.app_context():
        store = app.extensions["systems_store"]
        store.upsert_library(DND_5E_SYSTEM_CODE, title="DND 5E", system_code=DND_5E_SYSTEM_CODE)
        store.upsert_source(
            DND_5E_SYSTEM_CODE,
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_source(
            DND_5E_SYSTEM_CODE,
            "DMG",
            title="Dungeon Master's Guide",
            license_class="proprietary_private",
            public_visibility_allowed=False,
            requires_unofficial_notice=True,
        )
        store.upsert_entry(
            DND_5E_SYSTEM_CODE,
            "PHB",
            entry_key="dnd-5e|item|phb|longsword",
            entry_type="item",
            slug="phb-item-longsword",
            title="Longsword",
            search_text="longsword",
            player_safe_default=True,
            metadata={"type": "", "rarity": "none"},
            body={},
            rendered_html="",
        )
        store.upsert_entry(
            DND_5E_SYSTEM_CODE,
            "DMG",
            entry_key="dnd-5e|item|dmg|1longsword",
            entry_type="item",
            slug="dmg-item-1longsword",
            title="+1 Longsword",
            search_text="+1 longsword",
            player_safe_default=False,
            metadata={"base_item": "Longsword|PHB", "bonus_weapon": 0},
            body={},
            rendered_html="",
        )

        dry_run = repair_dnd5e_item_metadata(store, dry_run=True, source_ids=["phb", "dmg"])
        unchanged_longsword = store.get_entry(DND_5E_SYSTEM_CODE, "dnd-5e|item|phb|longsword")
        unchanged_magic = store.get_entry(DND_5E_SYSTEM_CODE, "dnd-5e|item|dmg|1longsword")
        assert dry_run.scanned_count == 2
        assert dry_run.repairable_count == 2
        assert unchanged_longsword is not None
        assert unchanged_magic is not None
        assert unchanged_longsword.metadata["type"] == ""

        result = repair_dnd5e_item_metadata(store, source_ids=["PHB", "DMG"])
        repaired_longsword = store.get_entry(DND_5E_SYSTEM_CODE, "dnd-5e|item|phb|longsword")
        repaired_magic = store.get_entry(DND_5E_SYSTEM_CODE, "dnd-5e|item|dmg|1longsword")

        assert result.scanned_count == 2
        assert result.repairable_count == 2
        assert result.repaired_count == 2

        assert repaired_longsword is not None
        assert repaired_longsword.metadata["type"] == "M"
        assert repaired_longsword.metadata["weapon_category"] == "martial"
        assert repaired_longsword.metadata["dmg1"] == "1d8"
        assert repaired_longsword.metadata["damage"] == "1d8 slashing"
        assert repaired_longsword.metadata["versatile_damage"] == "1d10"
        assert repaired_longsword.metadata["damage_type"] == "S"
        assert repaired_longsword.metadata["range"] == ""
        assert repaired_longsword.metadata["properties"] == ["V"]

        assert repaired_magic is not None
        assert repaired_magic.metadata["type"] == "M"
        assert repaired_magic.metadata["weapon_category"] == "martial"
        assert repaired_magic.metadata["dmg1"] == "1d8"
        assert repaired_magic.metadata["damage"] == "1d8 slashing"
        assert repaired_magic.metadata["versatile_damage"] == "1d10"
        assert repaired_magic.metadata["damage_type"] == "S"
        assert repaired_magic.metadata["range"] == ""
        assert repaired_magic.metadata["properties"] == ["V"]
        assert repaired_magic.metadata["bonus_weapon"] == 1

        clean_second_pass = repair_dnd5e_item_metadata(store, source_ids=["PHB", "DMG"])
        assert clean_second_pass.scanned_count == 2
        assert clean_second_pass.repairable_count == 0
