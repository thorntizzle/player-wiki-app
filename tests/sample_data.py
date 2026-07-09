from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

TEST_CAMPAIGN_SLUG = "linden-pass"
TEST_CAMPAIGN_TITLE = "Echoes of the Alloy Coast"

ASSIGNED_CHARACTER_SLUG = "arden-march"
ASSIGNED_CHARACTER_NAME = "Arden March"
SECOND_CHARACTER_SLUG = "selene-brook"
SECOND_CHARACTER_NAME = "Selene Brook"
THIRD_CHARACTER_SLUG = "tobin-slate"
THIRD_CHARACTER_NAME = "Tobin Slate"

TEST_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "sample_campaigns"


def build_test_campaigns_dir(tmp_path: Path) -> Path:
    campaigns_dir = tmp_path / "campaigns"
    shutil.copytree(TEST_FIXTURES_ROOT, campaigns_dir)
    return campaigns_dir


def approved_innovators_bolt_item_mechanics(
    *,
    allowed_levels: list[int] | tuple[int, ...] | None = None,
) -> dict[str, Any]:
    return {
        "item_use_actions": [
            {
                "id": "innovators-bolt-enchanted-bullet",
                "kind": "spell_slot_item_attack",
                "label": "Enchanted Bullet",
                "requires_equipped": True,
                "requires_attunement": True,
                "slot_cost": {
                    "lane": "spellcasting",
                    "allowed_levels": list(allowed_levels or [1, 2, 3, 4, 5]),
                },
                "choices": [
                    {
                        "id": "incendiary",
                        "label": "Incendiary",
                        "support_state": "modeled",
                        "damage_scaling": {"per_slot_level": "1d6 fire"},
                        "save": {
                            "ability": "dex",
                            "dc_source": "character_spell_save_dc",
                        },
                        "summary": (
                            "Deals 1d6 fire per spell level. Nearby-creature "
                            "Dexterity saves and any fire damage are table-managed."
                        ),
                    },
                    {
                        "id": "booming",
                        "label": "Booming",
                        "support_state": "modeled",
                        "damage_scaling": {"per_slot_level": "1d8 thunder"},
                        "save": {
                            "ability": "con",
                            "dc_source": "character_spell_save_dc",
                        },
                        "summary": (
                            "Deals 1d8 thunder per spell level. Constitution save "
                            "plus deafened/prone rider are table-managed."
                        ),
                    },
                    {
                        "id": "smoke",
                        "label": "Smoke",
                        "support_state": "modeled",
                        "damage_scaling": {"per_slot_level": "1d6 bludgeoning"},
                        "save": {
                            "ability": "wis",
                            "dc_source": "character_spell_save_dc",
                        },
                        "summary": (
                            "Deals 1d6 bludgeoning per spell level. Wisdom save "
                            "plus blinded rider are table-managed."
                        ),
                    },
                ],
            }
        ]
    }
