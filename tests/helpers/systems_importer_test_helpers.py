from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from player_wiki.systems_importer import Dnd5eSystemsImporter
from player_wiki.systems_models import SystemsEntryRecord
from tests.helpers.systems_importer_book_fakes import (
    SCAG_CLASSES_TEST_HEADERS,
    TCE_RULES_REFERENCE_TEST_TITLES,
    XGE_RULES_REFERENCE_TEST_TITLES,
    build_dmg_book_data_root,
    build_egw_character_option_wrapper_data_root,
    build_egw_dunamis_book_data_root,
    build_egw_heroic_chronicle_book_data_root,
    build_egw_treasure_progression_data_root,
    build_mm_book_data_root,
    build_mtf_book_data_root,
    build_phb_book_data_root,
    build_scag_backgrounds_book_data_root,
    build_scag_book_data_root,
    build_scag_classes_book_data_root,
    build_scag_entry_source_context_data_root,
    build_scag_first_slice_boundary_data_root,
    build_tce_book_data_root,
    build_vgm_book_data_root,
    build_vgm_monster_lore_data_root,
    build_xge_book_data_root,
    build_xge_book_related_entities_data_root,
)
from tests.helpers.systems_importer_feature_fakes import (
    build_additional_spell_metadata_data_root,
    build_campaign_subclass_progression_data_root,
    build_class_optionalfeature_progression_data_root,
    build_class_progression_metadata_data_root,
    build_efa_variant_subclass_data_root,
    build_feat_metadata_data_root,
    build_large_feat_data_root,
    build_spell_class_lookup_data_root,
    build_spell_class_variant_data_root,
    build_spell_metadata_data_root,
    build_subclass_optionalfeature_progression_data_root,
    build_subclass_short_name_matching_data_root,
    build_subclass_spellcasting_data_root,
    build_unsupported_cross_source_subclassfeature_data_root,
    build_xphb_variant_subclass_data_root,
)
from tests.helpers.systems_importer_fakes import (
    build_test_data_root,
    write_json,
)


def build_magicvariant_data_root(root: Path) -> Path:
    data_root = build_test_data_root(root)
    write_json(
        root / "data/magicvariants.json",
        {
            "magicvariant": [
                {
                    "name": "+1 Armor",
                    "edition": "classic",
                    "type": "GV|DMG",
                    "requires": [{"armor": True}],
                    "inherits": {
                        "namePrefix": "+1 ",
                        "source": "DMG",
                        "page": 152,
                        "rarity": "rare",
                        "bonusAc": "+1",
                        "entries": ["You have a {=bonusAc} bonus to AC while wearing this armor."],
                    },
                }
            ]
        },
    )
    return data_root


def build_scag_background_data_root(root: Path) -> Path:
    write_json(
        root / "data/backgrounds.json",
        {
            "background": [
                {
                    "name": "Clan Crafter",
                    "source": "SCAG",
                    "page": 145,
                    "skillProficiencies": [{"history": True, "insight": True}],
                    "languageProficiencies": [{"dwarvish": True}, {"anyStandard": 1}],
                    "toolProficiencies": [{"anyArtisansTool": 1}],
                    "startingEquipment": [
                        {
                            "_": [
                                {"equipmentType": "toolArtisan"},
                                {"special": "maker's mark chisel"},
                                "traveler's clothes|phb",
                                {"item": "pouch|phb", "containsValue": 1500},
                            ]
                        }
                    ],
                    "entries": [
                        {
                            "name": "Feature: Respect of the Stout Folk",
                            "type": "entries",
                            "entries": [
                                "Dwarves offer you hospitality and assistance in their settlements."
                            ],
                            "data": {"isFeature": True},
                        }
                    ],
                }
            ]
        },
    )
    return root
