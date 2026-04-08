from __future__ import annotations

from html import escape
from typing import Any

from .repository import slugify

DND5E_RULES_REFERENCE_SOURCE_ID = "RULES"
DND5E_RULES_REFERENCE_SOURCE_TITLE = "Character Rules Reference"
DND5E_RULES_REFERENCE_VERSION = "2026-04-07.1"

_RULE_ENTRY_SPECS = (
    {
        "title": "Character Math Overview",
        "aliases": [
            "derived stats",
            "character formulas",
            "sheet math",
        ],
        "summary": (
            "This source collects the core DND 5E formulas the app can reuse when it derives "
            "character values from classes, equipment, proficiencies, and features."
        ),
        "sections": [
            {
                "title": "Core Inputs",
                "paragraphs": [
                    "Most derived values come from the same small set of inputs: ability modifiers, proficiency bonus, proficiency level, equipped item state, attunement state, and any explicit bonuses or penalties from features or magic.",
                    "When a rule says to replace a base formula, use the replacement instead of stacking both formulas together unless the rule also says they combine.",
                ],
                "bullets": [
                    "Ability modifiers feed saves, skills, initiative, attacks, spellcasting, and many class features.",
                    "Proficiency can be absent, full, half, or doubled depending on the rule that grants it.",
                    "Carried inventory matters for tracking and weight, but equipped and attuned items are the states that most often change combat-facing math.",
                ],
            },
            {
                "title": "How To Use This Reference",
                "bullets": [
                    "Use the specific rule entry when the app needs one exact formula.",
                    "Use this overview when a new derived field depends on several rules at once.",
                    "Prefer applying the same rule once in the shared derivation layer rather than re-implementing the same math separately in builder, edit, import, and read-mode code.",
                ],
            },
        ],
    },
    {
        "title": "Ability Scores and Ability Modifiers",
        "aliases": [
            "ability modifier",
            "stat modifier",
            "strength modifier",
            "dexterity modifier",
            "constitution modifier",
            "intelligence modifier",
            "wisdom modifier",
            "charisma modifier",
        ],
        "formula": "Ability modifier = floor((ability score - 10) / 2)",
        "summary": "Every ability score produces a modifier, and that modifier is the base ingredient for most other character math.",
        "sections": [
            {
                "title": "Use The Modifier, Not The Raw Score",
                "paragraphs": [
                    "Checks, saves, attacks, AC formulas, spellcasting formulas, and many class features usually add the ability modifier rather than the raw score.",
                    "A score of 10 or 11 gives a +0 modifier. Every 2 points above or below that usually changes the modifier by 1.",
                ],
                "bullets": [
                    "8-9 -> -1",
                    "10-11 -> +0",
                    "12-13 -> +1",
                    "14-15 -> +2",
                    "16-17 -> +3",
                    "18-19 -> +4",
                    "20-21 -> +5",
                ],
            },
        ],
    },
    {
        "title": "Proficiency Bonus",
        "aliases": [
            "pb",
            "level proficiency",
            "proficiency by level",
        ],
        "formula": "Character proficiency bonus is based on total level: 1-4 +2, 5-8 +3, 9-12 +4, 13-16 +5, 17-20 +6",
        "summary": "A character's proficiency bonus scales by total character level and is reused anywhere the rules say the character is proficient.",
        "sections": [
            {
                "title": "Common Uses",
                "bullets": [
                    "Saving throws you are proficient in",
                    "Skills, tools, weapons, and armor you are proficient with",
                    "Spell attack bonus and spell save DC",
                    "Class and feat features that scale off proficiency bonus",
                ],
            },
            {
                "title": "Modified Proficiency",
                "paragraphs": [
                    "Some rules change the normal proficiency contribution. Expertise doubles it, while some features add half proficiency instead.",
                ],
                "bullets": [
                    "No proficiency -> add 0",
                    "Proficient -> add proficiency bonus",
                    "Expertise -> add double proficiency bonus",
                    "Half proficiency -> add half proficiency bonus, usually rounded down unless the rule says otherwise",
                ],
            },
        ],
    },
    {
        "title": "Saving Throw Bonuses",
        "aliases": [
            "save bonus",
            "saving throw proficiency",
            "saving throws",
        ],
        "formula": "Saving throw bonus = relevant ability modifier + proficiency component + other save modifiers",
        "summary": "Each saving throw starts from its matching ability modifier, then adds proficiency only if the character is proficient in that save.",
        "sections": [
            {
                "title": "Ability Pairings",
                "bullets": [
                    "Strength save -> Strength modifier",
                    "Dexterity save -> Dexterity modifier",
                    "Constitution save -> Constitution modifier",
                    "Intelligence save -> Intelligence modifier",
                    "Wisdom save -> Wisdom modifier",
                    "Charisma save -> Charisma modifier",
                ],
            },
            {
                "title": "Additional Modifiers",
                "paragraphs": [
                    "Features, feats, magic items, and temporary effects can add flat bonuses, advantage, or replacement rules on top of the normal save bonus.",
                ],
            },
        ],
    },
    {
        "title": "Skill Bonuses and Proficiency",
        "aliases": [
            "skill modifier",
            "skill bonus",
            "expertise",
            "half proficiency",
        ],
        "formula": "Skill bonus = linked ability modifier + proficiency component + other skill-specific modifiers",
        "summary": "A skill check uses the modifier for its linked ability, then layers in the proficiency amount the character has for that skill.",
        "sections": [
            {
                "title": "Default Skill Abilities",
                "bullets": [
                    "Athletics -> Strength",
                    "Acrobatics, Sleight of Hand, Stealth -> Dexterity",
                    "Arcana, History, Investigation, Nature, Religion -> Intelligence",
                    "Animal Handling, Insight, Medicine, Perception, Survival -> Wisdom",
                    "Deception, Intimidation, Performance, Persuasion -> Charisma",
                ],
            },
            {
                "title": "Proficiency Levels",
                "bullets": [
                    "No proficiency -> ability modifier only",
                    "Proficient -> ability modifier + proficiency bonus",
                    "Expertise -> ability modifier + double proficiency bonus",
                    "Half proficiency -> ability modifier + half proficiency bonus",
                ],
            },
            {
                "title": "Rule Flexibility",
                "paragraphs": [
                    "The DM can pair a skill with a different ability when the situation calls for it. When that happens, keep the skill proficiency the same and swap only the ability modifier.",
                ],
            },
        ],
    },
    {
        "title": "Passive Checks",
        "aliases": [
            "passive perception",
            "passive insight",
            "passive investigation",
            "passive score",
        ],
        "formula": "Passive check = 10 + the total modifier that would apply to the same check",
        "summary": "Passive checks reuse the same modifiers as active checks, but start from 10 instead of a d20 roll.",
        "sections": [
            {
                "title": "Common Passive Scores",
                "bullets": [
                    "Passive Perception = 10 + Perception modifier",
                    "Passive Insight = 10 + Insight modifier",
                    "Passive Investigation = 10 + Investigation modifier",
                ],
            },
            {
                "title": "Advantage And Disadvantage",
                "paragraphs": [
                    "If a table applies the usual passive-check adjustment, advantage adds 5 and disadvantage subtracts 5 from the passive score.",
                ],
            },
        ],
    },
    {
        "title": "Initiative",
        "aliases": [
            "initiative bonus",
            "turn order bonus",
        ],
        "formula": "Initiative bonus = Dexterity modifier + other initiative modifiers",
        "summary": "Initiative usually starts from Dexterity, then adds any feature, feat, item, or campaign modifier that explicitly changes initiative.",
        "sections": [
            {
                "title": "What Usually Modifies Initiative",
                "bullets": [
                    "Dexterity modifier is the normal base",
                    "Features like Alert can add a flat bonus",
                    "Temporary effects can grant advantage or penalties without changing the stored base bonus",
                ],
            },
        ],
    },
    {
        "title": "Armor Class",
        "aliases": [
            "ac",
            "shield bonus",
            "armor formula",
            "unarmored defense",
        ],
        "formula": "Armor Class = active armor formula + shield bonus if wielded + other AC modifiers",
        "summary": "Armor Class depends on what the character is actually wearing or wielding, plus any replacement formulas or explicit bonuses.",
        "sections": [
            {
                "title": "Base Armor Formulas",
                "bullets": [
                    "No armor -> 10 + Dexterity modifier",
                    "Light armor -> listed armor value + Dexterity modifier",
                    "Medium armor -> listed armor value + Dexterity modifier, maximum +2 unless a rule changes that cap",
                    "Heavy armor -> listed armor value",
                ],
            },
            {
                "title": "Common Additions And Replacements",
                "bullets": [
                    "Shield wielded -> +2 AC unless a rule says otherwise",
                    "Fighting Style: Defense or similar bonuses add on top of the active base formula",
                    "Unarmored Defense and similar features replace the normal unarmored formula when their rules say they do",
                ],
            },
            {
                "title": "Equipment State Matters",
                "paragraphs": [
                    "Carrying armor in inventory is not enough. The character usually needs the armor worn or the shield wielded for that item to affect AC.",
                ],
            },
        ],
    },
    {
        "title": "Attack Rolls and Attack Bonus",
        "aliases": [
            "to hit",
            "attack modifier",
            "weapon attack bonus",
        ],
        "formula": "Attack bonus = relevant ability modifier + proficiency component if proficient + other attack modifiers",
        "summary": "Attack rolls follow the same core pattern as other character math: choose the right ability, add proficiency if the character is proficient, then add any explicit bonuses or penalties.",
        "sections": [
            {
                "title": "Typical Weapon Ability Rules",
                "bullets": [
                    "Most melee weapon attacks use Strength",
                    "Most ranged weapon attacks use Dexterity",
                    "Finesse weapons can use Strength or Dexterity",
                    "Thrown weapons usually keep the ability of the underlying weapon attack",
                ],
            },
            {
                "title": "Common Attack Modifiers",
                "bullets": [
                    "Weapon proficiency adds proficiency bonus",
                    "Magic weapon bonuses add to the attack roll when the item says they do",
                    "Fighting styles, feats, or temporary effects can add or subtract extra modifiers",
                ],
            },
        ],
    },
    {
        "title": "Damage Rolls",
        "aliases": [
            "weapon damage",
            "damage modifier",
            "off-hand damage",
        ],
        "formula": "Damage roll = attack's damage dice + relevant ability modifier when applicable + other damage modifiers",
        "summary": "Damage usually starts from the attack's dice, then adds the same relevant ability modifier the attack roll used when the rules say to do so.",
        "sections": [
            {
                "title": "Common Patterns",
                "bullets": [
                    "Melee and ranged weapon attacks usually add the same relevant ability modifier they used for the attack roll",
                    "Versatile weapons use a different damage die when wielded in two hands",
                    "Thrown attacks usually keep the same damage ability modifier as the weapon's normal attack mode",
                ],
            },
            {
                "title": "Two-Weapon Fighting",
                "paragraphs": [
                    "A normal bonus-action off-hand attack does not add the ability modifier to damage unless a feature or rule says it does.",
                ],
            },
        ],
    },
    {
        "title": "Spell Attacks and Save DCs",
        "aliases": [
            "spell attack bonus",
            "spell save dc",
            "spellcasting ability",
        ],
        "formula": "Spell attack bonus = proficiency bonus + spellcasting ability modifier; Spell save DC = 8 + proficiency bonus + spellcasting ability modifier",
        "summary": "Spellcasting math follows a fixed 5E pattern once the character's spellcasting ability is known.",
        "sections": [
            {
                "title": "Spellcasting Ability",
                "paragraphs": [
                    "Use the spellcasting ability granted by the class, subclass, feat, species trait, or other feature that is providing the spell.",
                ],
            },
            {
                "title": "What Changes The Result",
                "bullets": [
                    "An increased spellcasting ability modifier changes both spell attack bonus and spell save DC",
                    "A changed proficiency bonus changes both values too",
                    "Specific features or items can add a separate bonus on top of the standard formula",
                ],
            },
        ],
    },
    {
        "title": "Hit Points and Hit Dice",
        "aliases": [
            "max hp",
            "hp by level",
            "hit dice",
        ],
        "formula": "Level 1 max HP = class hit die maximum + Constitution modifier; Later HP gain = rolled or fixed hit die increase + Constitution modifier",
        "summary": "Maximum hit points combine class hit dice, level progression, and Constitution modifier, with each level adding another increment.",
        "sections": [
            {
                "title": "Level 1 And Later Levels",
                "bullets": [
                    "At 1st level, use the class hit die at its maximum value",
                    "At later levels, add either the rolled result or the class's fixed average value, then add Constitution modifier",
                    "A Constitution change can also change total max HP if the rule says it applies retroactively",
                ],
            },
            {
                "title": "Hit Dice",
                "paragraphs": [
                    "Characters also track hit dice by class. Those dice matter for rests even when they do not directly change the displayed max HP formula.",
                ],
            },
        ],
    },
    {
        "title": "Carrying Capacity and Encumbrance",
        "aliases": [
            "carry weight",
            "weight limit",
            "encumbered",
            "push drag lift",
        ],
        "formula": "Carrying capacity = 15 x Strength score in pounds; Push, drag, or lift = 30 x Strength score in pounds",
        "summary": "Inventory weight rules use Strength score rather than Strength modifier, with optional encumbrance thresholds adding movement penalties before the full capacity limit.",
        "sections": [
            {
                "title": "Standard Carrying Rules",
                "bullets": [
                    "Carry normally up to 15 times Strength score in pounds",
                    "Push, drag, or lift up to 30 times Strength score in pounds",
                ],
            },
            {
                "title": "Optional Encumbrance Thresholds",
                "bullets": [
                    "Over 5 times Strength score -> encumbered",
                    "Over 10 times Strength score -> heavily encumbered",
                    "These thresholds are optional and should only change sheet math if the campaign is using them",
                ],
            },
        ],
    },
    {
        "title": "Equipped Items, Inventory, and Attunement",
        "aliases": [
            "equipped",
            "inventory",
            "attuned items",
            "attunement limit",
        ],
        "formula": "Inventory tracks what you carry; equipped state applies worn or wielded item rules; attunement is a separate state with a normal limit of 3 items",
        "summary": "Carried items, equipped items, and attuned items are related but distinct states. Treating them separately makes derived character math more reliable.",
        "sections": [
            {
                "title": "Inventory Versus Equipment",
                "bullets": [
                    "Inventory is the full carried list, including stored gear, consumables, treasure, and unequipped equipment",
                    "Equipped items are the worn or wielded items that can actively change AC, attacks, damage, speed, or other sheet values",
                    "An item can be in inventory without being equipped",
                ],
            },
            {
                "title": "Attunement",
                "bullets": [
                    "A character can normally be attuned to up to 3 magic items at once",
                    "Attunement is separate from equipping: an item may need to be both equipped and attuned before its benefits apply",
                    "If an item does not require attunement, its benefits depend only on the states named in that item's rules",
                ],
            },
        ],
    },
)

DND5E_RULES_REFERENCE_SENTINEL_ENTRY_KEY = (
    f"{DND5E_RULES_REFERENCE_SOURCE_ID.lower()}-rule-{slugify(_RULE_ENTRY_SPECS[0]['title'])}"
)


def build_dnd5e_rules_reference_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for spec in _RULE_ENTRY_SPECS:
        title = str(spec["title"]).strip()
        slug = f"{DND5E_RULES_REFERENCE_SOURCE_ID.lower()}-rule-{slugify(title)}"
        aliases = [str(value).strip() for value in list(spec.get("aliases") or []) if str(value).strip()]
        formula = str(spec.get("formula") or "").strip()
        summary = str(spec.get("summary") or "").strip()
        body = {
            "summary": summary,
            "formula": formula,
            "aliases": aliases,
            "sections": list(spec.get("sections") or []),
        }
        metadata = {
            "summary": summary,
            "formula": formula,
            "aliases": aliases,
            "seed_version": DND5E_RULES_REFERENCE_VERSION,
            "source_kind": "app_reference",
        }
        search_parts = [title, formula, summary, *aliases]
        entries.append(
            {
                "entry_key": slug,
                "entry_type": "rule",
                "slug": slug,
                "title": title,
                "source_page": "App reference",
                "source_path": f"builtin:dnd5e-rules:{DND5E_RULES_REFERENCE_VERSION}",
                "search_text": " ".join(part for part in search_parts if part).lower(),
                "player_safe_default": True,
                "dm_heavy": False,
                "metadata": metadata,
                "body": body,
                "rendered_html": _render_rule_entry_html(summary=summary, formula=formula, aliases=aliases, sections=body["sections"]),
            }
        )
    return entries


def _render_rule_entry_html(
    *,
    summary: str,
    formula: str,
    aliases: list[str],
    sections: list[dict[str, Any]],
) -> str:
    parts: list[str] = ['<section class="systems-entry-summary">']
    if formula:
        parts.append(f"<p><strong>Formula:</strong> {escape(formula)}</p>")
    if aliases:
        parts.append(f"<p><strong>Also covers:</strong> {escape(', '.join(aliases))}</p>")
    if summary:
        parts.append(f"<p>{escape(summary)}</p>")
    parts.append("</section>")

    for section in sections:
        title = str(section.get("title") or "").strip()
        paragraphs = [str(value).strip() for value in list(section.get("paragraphs") or []) if str(value).strip()]
        bullets = [str(value).strip() for value in list(section.get("bullets") or []) if str(value).strip()]
        if not title and not paragraphs and not bullets:
            continue
        parts.append("<section>")
        if title:
            parts.append(f"<h2>{escape(title)}</h2>")
        for paragraph in paragraphs:
            parts.append(f"<p>{escape(paragraph)}</p>")
        if bullets:
            parts.append("<ul>")
            parts.extend(f"<li>{escape(item)}</li>" for item in bullets)
            parts.append("</ul>")
        parts.append("</section>")
    return "".join(parts)
