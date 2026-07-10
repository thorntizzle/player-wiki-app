from __future__ import annotations

from player_wiki.systems_service import XIANXIA_HOMEBREW_SOURCE_ID
from tests.helpers.character_state_helpers import _write_campaign_config


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


def _valid_xianxia_create_data(
    name: str = "Cultivation Crane",
    *,
    slug: str = "",
    attributes: dict[str, str | int] | None = None,
) -> dict[str, str]:
    data = {
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
    for ability, value in dict(attributes or {}).items():
        data[f"attribute_{ability}"] = str(value)
    return data


def _valid_xianxia_manual_import_data(
    name: str = "Imported Lotus",
    *,
    slug: str = "imported-lotus",
) -> dict[str, str]:
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
