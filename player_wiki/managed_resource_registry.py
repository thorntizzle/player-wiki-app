from __future__ import annotations

from typing import Any

from .repository import normalize_lookup


def managed_resource_formula_fixed(value: int) -> dict[str, Any]:
    return {"kind": "fixed", "value": int(value)}


def managed_resource_formula_level(
    *,
    multiplier: int = 1,
    bonus: int = 0,
    minimum: int | None = None,
) -> dict[str, Any]:
    return {
        "kind": "level",
        "multiplier": int(multiplier),
        "bonus": int(bonus),
        "minimum": None if minimum is None else int(minimum),
    }


def managed_resource_formula_proficiency_bonus(
    *,
    multiplier: int = 1,
    bonus: int = 0,
    minimum: int | None = None,
) -> dict[str, Any]:
    return {
        "kind": "proficiency_bonus",
        "multiplier": int(multiplier),
        "bonus": int(bonus),
        "minimum": None if minimum is None else int(minimum),
    }


def managed_resource_formula_ability_modifier(
    ability_key: str,
    *,
    bonus: int = 0,
    minimum: int | None = None,
) -> dict[str, Any]:
    return {
        "kind": "ability_modifier",
        "ability": str(ability_key or "").strip().lower(),
        "bonus": int(bonus),
        "minimum": None if minimum is None else int(minimum),
    }


def managed_resource_formula_threshold(*thresholds: tuple[int, int]) -> dict[str, Any]:
    return {
        "kind": "threshold",
        "thresholds": [(int(level), int(value)) for level, value in thresholds],
    }


def managed_resource_formula_sum(*parts: dict[str, Any], minimum: int | None = None) -> dict[str, Any]:
    return {
        "kind": "sum",
        "parts": [dict(part) for part in parts],
        "minimum": None if minimum is None else int(minimum),
    }


def managed_resource_tracker(
    tracker_id: str,
    label: str,
    *,
    max_formula: dict[str, Any],
    reset_on: str,
    activation_type: str,
    reset_to: str | int = "max",
    notes: str | None = None,
    rest_behavior: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(tracker_id or "").strip(),
        "label": str(label or "").strip(),
        "max_formula": dict(max_formula),
        "reset_on": str(reset_on or "manual").strip() or "manual",
        "reset_to": reset_to,
        "notes": str(notes if notes is not None else label or "").strip(),
        "activation_type": str(activation_type or "passive").strip() or "passive",
        "rest_behavior": str(rest_behavior or "").strip() or None,
    }


def managed_resource_member(
    key: str,
    name: str,
    *,
    activation_type: str,
    tracker: dict[str, Any] | None = None,
    aliases: tuple[str, ...] = (),
    description_markdown: str = "",
    generate_from_primary: bool = False,
) -> dict[str, Any]:
    match_names = [normalize_lookup(name)]
    match_names.extend(normalize_lookup(alias) for alias in aliases if str(alias or "").strip())
    return {
        "key": str(key or "").strip(),
        "name": str(name or "").strip(),
        "activation_type": str(activation_type or "passive").strip() or "passive",
        "tracker": dict(tracker) if tracker is not None else None,
        "match_names": tuple(value for value in match_names if value),
        "description_markdown": str(description_markdown or "").strip(),
        "generate_from_primary": bool(generate_from_primary),
    }


def managed_resource_family(
    *,
    category: str,
    source: str,
    inventory: tuple[tuple[str, str], ...],
    primary: dict[str, Any],
    members: tuple[dict[str, Any], ...] = (),
    match_slug_members: dict[str, str] | None = None,
    page_refs: tuple[str, ...] = (),
    allow_fallback: bool = True,
) -> dict[str, Any]:
    normalized_slug_members = {
        normalize_lookup(slug): str(member_key or "").strip()
        for slug, member_key in dict(match_slug_members or {}).items()
        if normalize_lookup(slug) and str(member_key or "").strip()
    }
    if not normalized_slug_members:
        normalized_slug_members = {
            normalize_lookup(slug): str(primary.get("key") or "primary").strip()
            for slug, _title in inventory
            if normalize_lookup(slug)
        }
    members_by_key = {
        str(primary.get("key") or "primary").strip(): dict(primary),
        **{
            str(member.get("key") or "").strip(): dict(member)
            for member in members
            if str(member.get("key") or "").strip()
        },
    }
    return {
        "category": normalize_lookup(category),
        "source": normalize_lookup(source),
        "inventory": tuple(
            {
                "slug": str(slug or "").strip(),
                "title": str(title or "").strip(),
            }
            for slug, title in inventory
            if str(slug or "").strip()
        ),
        "primary": dict(primary),
        "members": tuple(dict(member) for member in members),
        "members_by_key": members_by_key,
        "match_slug_members": normalized_slug_members,
        "page_refs": tuple(normalize_lookup(page_ref) for page_ref in page_refs if str(page_ref or "").strip()),
        "allow_fallback": bool(allow_fallback),
        "fallback_key": (
            normalize_lookup(category),
            normalize_lookup(str(primary.get("name") or "")),
            normalize_lookup(source),
            "",
        ),
    }


MANAGED_RESOURCE_FAMILIES: tuple[dict[str, Any], ...] = (
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-secondwind-fighter-phb-1", "Second Wind"),),
        primary=managed_resource_member(
            "primary",
            "Second Wind",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "second-wind",
                "Second Wind",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="short_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-rage-barbarian-phb-1", "Rage"),),
        primary=managed_resource_member(
            "primary",
            "Rage",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "rage",
                "Rage",
                max_formula=managed_resource_formula_threshold((1, 2), (3, 3), (6, 4), (12, 5), (17, 6)),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-bardicinspiration-bard-phb-1", "Bardic Inspiration"),),
        primary=managed_resource_member(
            "primary",
            "Bardic Inspiration",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "bardic-inspiration",
                "Bardic Inspiration",
                max_formula=managed_resource_formula_ability_modifier("cha", minimum=1),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-actionsurge-fighter-phb-2", "Action Surge"),),
        primary=managed_resource_member(
            "primary",
            "Action Surge",
            activation_type="special",
            tracker=managed_resource_tracker(
                "action-surge",
                "Action Surge",
                max_formula=managed_resource_formula_threshold((2, 1), (17, 2)),
                reset_on="short_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-arcanerecovery-wizard-phb-1", "Arcane Recovery"),),
        primary=managed_resource_member(
            "primary",
            "Arcane Recovery",
            activation_type="special",
            tracker=managed_resource_tracker(
                "arcane-recovery",
                "Arcane Recovery",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="long_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-divinesense-paladin-phb-1", "Divine Sense"),),
        primary=managed_resource_member(
            "primary",
            "Divine Sense",
            activation_type="action",
            tracker=managed_resource_tracker(
                "divine-sense",
                "Divine Sense",
                max_formula=managed_resource_formula_ability_modifier("cha", bonus=1, minimum=1),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-layonhands-paladin-phb-1", "Lay on Hands"),),
        primary=managed_resource_member(
            "primary",
            "Lay on Hands",
            activation_type="action",
            tracker=managed_resource_tracker(
                "lay-on-hands",
                "Lay on Hands",
                max_formula=managed_resource_formula_level(multiplier=5, minimum=5),
                reset_on="long_rest",
                activation_type="action",
                notes="Lay on Hands pool",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(
            ("phb-classfeature-channeldivinity-cleric-phb-2", "Channel Divinity"),
            ("phb-classfeature-channeldivinity-cleric-phb-6", "Channel Divinity"),
            ("phb-classfeature-channeldivinity-cleric-phb-18", "Channel Divinity"),
            ("phb-classfeature-channeldivinity-paladin-phb-3", "Channel Divinity"),
        ),
        primary=managed_resource_member(
            "primary",
            "Channel Divinity",
            activation_type="passive",
            tracker=managed_resource_tracker(
                "channel-divinity",
                "Channel Divinity",
                max_formula=managed_resource_formula_threshold((2, 1), (6, 2), (18, 3)),
                reset_on="short_rest",
                activation_type="passive",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-wildshape-druid-phb-2", "Wild Shape"),),
        primary=managed_resource_member(
            "primary",
            "Wild Shape",
            activation_type="action",
            tracker=managed_resource_tracker(
                "wild-shape",
                "Wild Shape",
                max_formula=managed_resource_formula_fixed(2),
                reset_on="short_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="PHB",
        inventory=(("phb-subclassfeature-warpriest-cleric-phb-war-phb-1", "War Priest"),),
        match_slug_members={
            "phb-subclassfeature-warpriest-cleric-phb-war-phb-1": "primary",
            "phb-subclassfeature-war-priest": "primary",
        },
        primary=managed_resource_member(
            "primary",
            "War Priest",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "war-priest",
                "War Priest",
                max_formula=managed_resource_formula_ability_modifier("wis", minimum=1),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-arcaneshot-fighter-phb-arcanearcher-xge-3", "Arcane Shot"),),
        match_slug_members={
            "xge-subclassfeature-arcaneshot-fighter-phb-arcanearcher-xge-3": "primary",
            "xge-subclassfeature-arcane-shot": "primary",
        },
        primary=managed_resource_member(
            "primary",
            "Arcane Shot",
            activation_type="special",
            tracker=managed_resource_tracker(
                "arcane-shot",
                "Arcane Shot",
                max_formula=managed_resource_formula_fixed(2),
                reset_on="short_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="EGW",
        inventory=(("egw-subclassfeature-chronalshift-wizard-phb-chronurgy-egw-2", "Chronal Shift"),),
        match_slug_members={
            "egw-subclassfeature-chronalshift-wizard-phb-chronurgy-egw-2": "primary",
            "egw-subclassfeature-chronal-shift": "primary",
        },
        primary=managed_resource_member(
            "primary",
            "Chronal Shift",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "chronal-shift",
                "Chronal Shift",
                max_formula=managed_resource_formula_fixed(2),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(
            ("tce-subclassfeature-psionicpower-fighter-phb-psiwarrior-tce-3", "Psionic Power"),
            ("tce-subclassfeature-telekineticmovement-fighter-phb-psiwarrior-tce-3", "Telekinetic Movement"),
        ),
        primary=managed_resource_member(
            "primary",
            "Psionic Power",
            activation_type="passive",
            tracker=managed_resource_tracker(
                "psionic-power-psionic-energy",
                "Psionic Power: Psionic Energy",
                max_formula=managed_resource_formula_proficiency_bonus(multiplier=2, minimum=2),
                reset_on="long_rest",
                activation_type="passive",
                notes="Psionic Power",
            ),
        ),
        members=(
            managed_resource_member(
                "protective-field",
                "Psionic Power: Protective Field",
                aliases=("Protective Field",),
                activation_type="reaction",
                description_markdown=(
                    "Reaction to shield yourself or another creature you can see within 30 feet, "
                    "reducing the damage taken."
                ),
                generate_from_primary=True,
            ),
            managed_resource_member(
                "psionic-strike",
                "Psionic Power: Psionic Strike",
                aliases=("Psionic Strike",),
                activation_type="special",
                description_markdown=(
                    "When you hit a target with a weapon attack, expend one Psionic Energy die "
                    "to deal extra force damage."
                ),
                generate_from_primary=True,
            ),
            managed_resource_member(
                "telekinetic-movement",
                "Psionic Power: Telekinetic Movement",
                aliases=("Telekinetic Movement",),
                activation_type="action",
                description_markdown="You can move an object or a creature with your mind.",
                generate_from_primary=True,
                tracker=managed_resource_tracker(
                    "psionic-power-telekinetic-movement",
                    "Psionic Power: Telekinetic Movement",
                    max_formula=managed_resource_formula_fixed(1),
                    reset_on="short_rest",
                    activation_type="action",
                    notes="Psionic Power: Telekinetic Movement",
                ),
            ),
            managed_resource_member(
                "recovery",
                "Psionic Power: Recovery",
                activation_type="bonus_action",
                description_markdown="As a bonus action, you can regain one expended Psionic Energy die.",
                generate_from_primary=True,
                tracker=managed_resource_tracker(
                    "psionic-power-recovery",
                    "Psionic Power: Recovery",
                    max_formula=managed_resource_formula_fixed(1),
                    reset_on="short_rest",
                    activation_type="bonus_action",
                    notes="Psionic Power: Recovery",
                ),
            ),
        ),
        match_slug_members={
            "tce-subclassfeature-psionicpower-fighter-phb-psiwarrior-tce-3": "primary",
            "tce-subclassfeature-psionic-power": "primary",
            "tce-subclassfeature-protectivefield-fighter-phb-psiwarrior-tce-3": "protective-field",
            "tce-subclassfeature-protective-field": "protective-field",
            "tce-subclassfeature-psionicstrike-fighter-phb-psiwarrior-tce-3": "psionic-strike",
            "tce-subclassfeature-psionic-strike": "psionic-strike",
            "tce-subclassfeature-telekineticmovement-fighter-phb-psiwarrior-tce-3": "telekinetic-movement",
            "tce-subclassfeature-telekinetic-movement": "telekinetic-movement",
        },
        page_refs=("mechanics/psi-warrior/psionic-power",),
        allow_fallback=False,
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-psionicpower-rogue-phb-soulknife-tce-3", "Psionic Power"),),
        primary=managed_resource_member(
            "primary",
            "Psionic Power",
            activation_type="passive",
            tracker=managed_resource_tracker(
                "psionic-power-psionic-energy",
                "Psionic Power: Psionic Energy",
                max_formula=managed_resource_formula_proficiency_bonus(multiplier=2, minimum=2),
                reset_on="long_rest",
                activation_type="passive",
                notes="Psionic Power",
            ),
        ),
        members=(
            managed_resource_member(
                "psi-bolstered-knack",
                "Psi-Bolstered Knack",
                activation_type="special",
            ),
            managed_resource_member(
                "psychic-whispers",
                "Psychic Whispers",
                activation_type="action",
            ),
            managed_resource_member(
                "recovery",
                "Psionic Power: Recovery",
                activation_type="bonus_action",
                description_markdown="As a bonus action, you can regain one expended Psionic Energy die.",
                generate_from_primary=True,
                tracker=managed_resource_tracker(
                    "psionic-power-recovery",
                    "Psionic Power: Recovery",
                    max_formula=managed_resource_formula_fixed(1),
                    reset_on="short_rest",
                    activation_type="bonus_action",
                    notes="Psionic Power: Recovery",
                ),
            ),
        ),
        match_slug_members={
            "tce-subclassfeature-psionicpower-rogue-phb-soulknife-tce-3": "primary",
            "tce-subclassfeature-psibolsteredknack-rogue-phb-soulknife-tce-3": "psi-bolstered-knack",
            "tce-subclassfeature-psi-bolstered-knack": "psi-bolstered-knack",
            "tce-subclassfeature-psychicwhispers-rogue-phb-soulknife-tce-3": "psychic-whispers",
            "tce-subclassfeature-psychic-whispers": "psychic-whispers",
        },
        allow_fallback=False,
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-ki-monk-phb-2", "Ki"),),
        primary=managed_resource_member(
            "primary",
            "Ki",
            activation_type="passive",
            tracker=managed_resource_tracker(
                "ki",
                "Ki",
                max_formula=managed_resource_formula_level(minimum=2),
                reset_on="short_rest",
                activation_type="passive",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-fontofmagic-sorcerer-phb-2", "Font of Magic"),),
        primary=managed_resource_member(
            "primary",
            "Font of Magic",
            activation_type="passive",
            tracker=managed_resource_tracker(
                "sorcery-points",
                "Sorcery Points",
                max_formula=managed_resource_formula_level(minimum=2),
                reset_on="long_rest",
                activation_type="passive",
                notes="Sorcery Points",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="PHB",
        inventory=(("phb-subclassfeature-combatsuperiority-fighter-phb-battlemaster-phb-3", "Combat Superiority"),),
        primary=managed_resource_member(
            "primary",
            "Combat Superiority",
            activation_type="special",
            tracker=managed_resource_tracker(
                "superiority-dice",
                "Superiority Dice",
                max_formula=managed_resource_formula_threshold((3, 4), (7, 5), (15, 6)),
                reset_on="short_rest",
                activation_type="special",
                notes="Combat Superiority",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-indomitable-fighter-phb-9", "Indomitable"),),
        primary=managed_resource_member(
            "primary",
            "Indomitable",
            activation_type="special",
            tracker=managed_resource_tracker(
                "indomitable",
                "Indomitable",
                max_formula=managed_resource_formula_threshold((9, 1), (13, 2), (17, 3)),
                reset_on="long_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="TCE",
        inventory=(("tce-classfeature-flashofgenius-artificer-tce-7", "Flash of Genius"),),
        primary=managed_resource_member(
            "primary",
            "Flash of Genius",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "flash-of-genius",
                "Flash of Genius",
                max_formula=managed_resource_formula_ability_modifier("int", minimum=1),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-experimentalelixir-artificer-tce-alchemist-tce-3", "Experimental Elixir"),),
        primary=managed_resource_member(
            "primary",
            "Experimental Elixir",
            activation_type="action",
            tracker=managed_resource_tracker(
                "experimental-elixir",
                "Experimental Elixir",
                max_formula=managed_resource_formula_threshold((3, 1), (6, 2), (15, 3)),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-eldritchcannon-artificer-tce-artillerist-tce-3", "Eldritch Cannon"),),
        primary=managed_resource_member(
            "primary",
            "Eldritch Cannon",
            activation_type="action",
            tracker=managed_resource_tracker(
                "eldritch-cannon",
                "Eldritch Cannon",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-arcanejolt-artificer-tce-battlesmith-tce-9", "Arcane Jolt"),),
        primary=managed_resource_member(
            "primary",
            "Arcane Jolt",
            activation_type="special",
            tracker=managed_resource_tracker(
                "arcane-jolt",
                "Arcane Jolt",
                max_formula=managed_resource_formula_ability_modifier("int", minimum=1),
                reset_on="long_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-defensivefield-artificer-tce-armorer-tce-3", "Defensive Field"),),
        primary=managed_resource_member(
            "primary",
            "Defensive Field",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "defensive-field",
                "Defensive Field",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-magicawareness-barbarian-phb-wildmagic-tce-3", "Magic Awareness"),),
        primary=managed_resource_member(
            "primary",
            "Magic Awareness",
            activation_type="action",
            tracker=managed_resource_tracker(
                "magic-awareness",
                "Magic Awareness",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-bolsteringmagic-barbarian-phb-wildmagic-tce-6", "Bolstering Magic"),),
        primary=managed_resource_member(
            "primary",
            "Bolstering Magic",
            activation_type="action",
            tracker=managed_resource_tracker(
                "bolstering-magic",
                "Bolstering Magic",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-infectiousfury-barbarian-phb-beast-tce-10", "Infectious Fury"),),
        primary=managed_resource_member(
            "primary",
            "Infectious Fury",
            activation_type="special",
            tracker=managed_resource_tracker(
                "infectious-fury",
                "Infectious Fury",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-callthehunt-barbarian-phb-beast-tce-14", "Call the Hunt"),),
        primary=managed_resource_member(
            "primary",
            "Call the Hunt",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "call-the-hunt",
                "Call the Hunt",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="PHB",
        inventory=(("phb-subclassfeature-wardingflare-cleric-phb-light-phb-1", "Warding Flare"),),
        primary=managed_resource_member(
            "primary",
            "Warding Flare",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "warding-flare",
                "Warding Flare",
                max_formula=managed_resource_formula_ability_modifier("wis", minimum=1),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="PHB",
        inventory=(("phb-subclassfeature-wrathofthestorm-cleric-phb-tempest-phb-1", "Wrath of the Storm"),),
        primary=managed_resource_member(
            "primary",
            "Wrath of the Storm",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "wrath-of-the-storm",
                "Wrath of the Storm",
                max_formula=managed_resource_formula_ability_modifier("wis", minimum=1),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-eyesofthegrave-cleric-phb-grave-xge-1", "Eyes of the Grave"),),
        primary=managed_resource_member(
            "primary",
            "Eyes of the Grave",
            activation_type="action",
            tracker=managed_resource_tracker(
                "eyes-of-the-grave",
                "Eyes of the Grave",
                max_formula=managed_resource_formula_ability_modifier("wis", minimum=1),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-sentinelatdeathsdoor-cleric-phb-grave-xge-6", "Sentinel at Death's Door"),),
        primary=managed_resource_member(
            "primary",
            "Sentinel at Death's Door",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "sentinel-at-deaths-door",
                "Sentinel at Death's Door",
                max_formula=managed_resource_formula_ability_modifier("wis", minimum=1),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-emboldeningbond-cleric-phb-peace-tce-1", "Emboldening Bond"),),
        primary=managed_resource_member(
            "primary",
            "Emboldening Bond",
            activation_type="action",
            tracker=managed_resource_tracker(
                "emboldening-bond",
                "Emboldening Bond",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-stepsofnight-cleric-phb-twilight-tce-6", "Steps of Night"),),
        primary=managed_resource_member(
            "primary",
            "Steps of Night",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "steps-of-night",
                "Steps of Night",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-balmofthesummercourt-druid-phb-dreams-xge-2", "Balm of the Summer Court"),),
        primary=managed_resource_member(
            "primary",
            "Balm of the Summer Court",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "balm-of-the-summer-court",
                "Balm of the Summer Court",
                max_formula=managed_resource_formula_level(minimum=2),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-cosmicomen-druid-phb-stars-tce-6", "Cosmic Omen"),),
        primary=managed_resource_member(
            "primary",
            "Cosmic Omen",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "cosmic-omen",
                "Cosmic Omen",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-cauterizingflames-druid-phb-wildfire-tce-10", "Cauterizing Flames"),),
        primary=managed_resource_member(
            "primary",
            "Cauterizing Flames",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "cauterizing-flames",
                "Cauterizing Flames",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-hiddenpaths-druid-phb-dreams-xge-10", "Hidden Paths"),),
        primary=managed_resource_member(
            "primary",
            "Hidden Paths",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "hidden-paths",
                "Hidden Paths",
                max_formula=managed_resource_formula_ability_modifier("wis", minimum=1),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-fightingspirit-fighter-phb-samurai-xge-3", "Fighting Spirit"),),
        primary=managed_resource_member(
            "primary",
            "Fighting Spirit",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "fighting-spirit",
                "Fighting Spirit",
                max_formula=managed_resource_formula_fixed(3),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-giantsmight-fighter-phb-runeknight-tce-3", "Giant's Might"),),
        primary=managed_resource_member(
            "primary",
            "Giant's Might",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "giants-might",
                "Giant's Might",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-runicshield-fighter-phb-runeknight-tce-7", "Runic Shield"),),
        primary=managed_resource_member(
            "primary",
            "Runic Shield",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "runic-shield",
                "Runic Shield",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="EGW",
        inventory=(("egw-subclassfeature-unleashincarnation-fighter-phb-echoknight-egw-3", "Unleash Incarnation"),),
        primary=managed_resource_member(
            "primary",
            "Unleash Incarnation",
            activation_type="special",
            tracker=managed_resource_tracker(
                "unleash-incarnation",
                "Unleash Incarnation",
                max_formula=managed_resource_formula_ability_modifier("con", minimum=1),
                reset_on="long_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="EGW",
        inventory=(("egw-subclassfeature-reclaimpotential-fighter-phb-echoknight-egw-15", "Reclaim Potential"),),
        primary=managed_resource_member(
            "primary",
            "Reclaim Potential",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "reclaim-potential",
                "Reclaim Potential",
                max_formula=managed_resource_formula_ability_modifier("con", minimum=1),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-wardingmaneuver-fighter-phb-cavalier-xge-7", "Warding Maneuver"),),
        primary=managed_resource_member(
            "primary",
            "Warding Maneuver",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "warding-maneuver",
                "Warding Maneuver",
                max_formula=managed_resource_formula_ability_modifier("con", minimum=1),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-unwaveringmark-fighter-phb-cavalier-xge-3", "Unwavering Mark"),),
        primary=managed_resource_member(
            "primary",
            "Unwavering Mark",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "unwavering-mark",
                "Unwavering Mark",
                max_formula=managed_resource_formula_ability_modifier("str", minimum=1),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="class_feature",
        source="PHB",
        inventory=(("phb-classfeature-cleansingtouch-paladin-phb-14", "Cleansing Touch"),),
        primary=managed_resource_member(
            "primary",
            "Cleansing Touch",
            activation_type="action",
            tracker=managed_resource_tracker(
                "cleansing-touch",
                "Cleansing Touch",
                max_formula=managed_resource_formula_ability_modifier("cha", minimum=1),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-gloriousdefense-paladin-phb-glory-tce-15", "Glorious Defense"),),
        primary=managed_resource_member(
            "primary",
            "Glorious Defense",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "glorious-defense",
                "Glorious Defense",
                max_formula=managed_resource_formula_ability_modifier("cha", minimum=1),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-wailsfromthegrave-rogue-phb-phantom-tce-3", "Wails from the Grave"),),
        primary=managed_resource_member(
            "primary",
            "Wails from the Grave",
            activation_type="special",
            tracker=managed_resource_tracker(
                "wails-from-the-grave",
                "Wails from the Grave",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-unerringeye-rogue-phb-inquisitive-xge-13", "Unerring Eye"),),
        primary=managed_resource_member(
            "primary",
            "Unerring Eye",
            activation_type="action",
            tracker=managed_resource_tracker(
                "unerring-eye",
                "Unerring Eye",
                max_formula=managed_resource_formula_ability_modifier("wis", minimum=1),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-masterduelist-rogue-phb-swashbuckler-xge-17", "Master Duelist"),),
        primary=managed_resource_member(
            "primary",
            "Master Duelist",
            activation_type="special",
            tracker=managed_resource_tracker(
                "master-duelist",
                "Master Duelist",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="short_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-restorebalance-sorcerer-phb-clockworksoul-tce-1", "Restore Balance"),),
        primary=managed_resource_member(
            "primary",
            "Restore Balance",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "restore-balance",
                "Restore Balance",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-strengthofthegrave-sorcerer-phb-shadow-xge-1", "Strength of the Grave"),),
        primary=managed_resource_member(
            "primary",
            "Strength of the Grave",
            activation_type="special",
            tracker=managed_resource_tracker(
                "strength-of-the-grave",
                "Strength of the Grave",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="long_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-warpingimplosion-sorcerer-phb-aberrantmind-tce-18", "Warping Implosion"),),
        primary=managed_resource_member(
            "primary",
            "Warping Implosion",
            activation_type="action",
            tracker=managed_resource_tracker(
                "warping-implosion",
                "Warping Implosion",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-healinglight-warlock-phb-celestial-xge-1", "Healing Light"),),
        primary=managed_resource_member(
            "primary",
            "Healing Light",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "healing-light",
                "Healing Light",
                max_formula=managed_resource_formula_sum(
                    managed_resource_formula_fixed(1),
                    managed_resource_formula_level(),
                    minimum=2,
                ),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-tentacleofthedeeps-warlock-phb-fathomless-tce-1", "Tentacle of the Deeps"),),
        primary=managed_resource_member(
            "primary",
            "Tentacle of the Deeps",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "tentacle-of-the-deeps",
                "Tentacle of the Deeps",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-hexbladescurse-warlock-phb-hexblade-xge-1", "Hexblade's Curse"),),
        primary=managed_resource_member(
            "primary",
            "Hexblade's Curse",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "hexblades-curse",
                "Hexblade's Curse",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="short_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-accursedspecter-warlock-phb-hexblade-xge-6", "Accursed Specter"),),
        primary=managed_resource_member(
            "primary",
            "Accursed Specter",
            activation_type="special",
            tracker=managed_resource_tracker(
                "accursed-specter",
                "Accursed Specter",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="long_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="PHB",
        inventory=(("phb-subclassfeature-arcaneward-wizard-phb-abjuration-phb-2", "Arcane Ward"),),
        primary=managed_resource_member(
            "primary",
            "Arcane Ward",
            activation_type="passive",
            tracker=managed_resource_tracker(
                "arcane-ward",
                "Arcane Ward",
                max_formula=managed_resource_formula_sum(
                    managed_resource_formula_level(multiplier=2),
                    managed_resource_formula_ability_modifier("int"),
                    minimum=1,
                ),
                reset_on="manual",
                activation_type="passive",
                reset_to="unchanged",
                rest_behavior="manual_only",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="TCE",
        inventory=(("tce-subclassfeature-bladesong-wizard-phb-bladesinging-tce-2", "Bladesong"),),
        primary=managed_resource_member(
            "primary",
            "Bladesong",
            activation_type="bonus_action",
            tracker=managed_resource_tracker(
                "bladesong",
                "Bladesong",
                max_formula=managed_resource_formula_proficiency_bonus(minimum=2),
                reset_on="long_rest",
                activation_type="bonus_action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="XGE",
        inventory=(("xge-subclassfeature-powersurge-wizard-phb-war-xge-6", "Power Surge"),),
        primary=managed_resource_member(
            "primary",
            "Power Surge",
            activation_type="special",
            tracker=managed_resource_tracker(
                "power-surge",
                "Power Surge",
                max_formula=managed_resource_formula_ability_modifier("int", minimum=1),
                reset_on="long_rest",
                activation_type="special",
                reset_to=1,
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="EGW",
        inventory=(("egw-subclassfeature-momentarystasis-wizard-phb-chronurgy-egw-6", "Momentary Stasis"),),
        primary=managed_resource_member(
            "primary",
            "Momentary Stasis",
            activation_type="action",
            tracker=managed_resource_tracker(
                "momentary-stasis",
                "Momentary Stasis",
                max_formula=managed_resource_formula_ability_modifier("int", minimum=1),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="EGW",
        inventory=(("egw-subclassfeature-arcaneabeyance-wizard-phb-chronurgy-egw-10", "Arcane Abeyance"),),
        primary=managed_resource_member(
            "primary",
            "Arcane Abeyance",
            activation_type="special",
            tracker=managed_resource_tracker(
                "arcane-abeyance",
                "Arcane Abeyance",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="short_rest",
                activation_type="special",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="EGW",
        inventory=(("egw-subclassfeature-violentattraction-wizard-phb-graviturgy-egw-10", "Violent Attraction"),),
        primary=managed_resource_member(
            "primary",
            "Violent Attraction",
            activation_type="reaction",
            tracker=managed_resource_tracker(
                "violent-attraction",
                "Violent Attraction",
                max_formula=managed_resource_formula_ability_modifier("int", minimum=1),
                reset_on="long_rest",
                activation_type="reaction",
            ),
        ),
    ),
    managed_resource_family(
        category="subclass_feature",
        source="EGW",
        inventory=(("egw-subclassfeature-eventhorizon-wizard-phb-graviturgy-egw-14", "Event Horizon"),),
        primary=managed_resource_member(
            "primary",
            "Event Horizon",
            activation_type="action",
            tracker=managed_resource_tracker(
                "event-horizon",
                "Event Horizon",
                max_formula=managed_resource_formula_fixed(1),
                reset_on="long_rest",
                activation_type="action",
            ),
        ),
    ),
)
MANAGED_RESOURCE_EXCLUSIONS_BY_SLUG: dict[str, dict[str, str]] = {
    "tce-subclassfeature-protectivefield-fighter-phb-psiwarrior-tce-3": {
        "title": "Protective Field",
        "reason": "parent-resource-consumer",
    },
    "tce-subclassfeature-psionicstrike-fighter-phb-psiwarrior-tce-3": {
        "title": "Psionic Strike",
        "reason": "parent-resource-consumer",
    },
    "tce-subclassfeature-psibolsteredknack-rogue-phb-soulknife-tce-3": {
        "title": "Psi-Bolstered Knack",
        "reason": "parent-resource-consumer",
    },
    "tce-subclassfeature-psychicwhispers-rogue-phb-soulknife-tce-3": {
        "title": "Psychic Whispers",
        "reason": "parent-resource-consumer",
    },
    "phb-classfeature-mysticarcanum6thlevel-warlock-phb-11": {
        "title": "Mystic Arcanum (6th level)",
        "reason": "spell-support",
    },
    "phb-classfeature-mysticarcanum7thlevel-warlock-phb-13": {
        "title": "Mystic Arcanum (7th level)",
        "reason": "spell-support",
    },
    "phb-classfeature-mysticarcanum8thlevel-warlock-phb-15": {
        "title": "Mystic Arcanum (8th level)",
        "reason": "spell-support",
    },
    "phb-classfeature-mysticarcanum9thlevel-warlock-phb-17": {
        "title": "Mystic Arcanum (9th level)",
        "reason": "spell-support",
    },
    "phb-classfeature-spellmastery-wizard-phb-18": {
        "title": "Spell Mastery",
        "reason": "spell-support",
    },
    "phb-classfeature-signaturespells-wizard-phb-20": {
        "title": "Signature Spells",
        "reason": "spell-support",
    },
    "tce-subclassfeature-limitedwish-warlock-phb-genie-tce-14": {
        "title": "Limited Wish",
        "reason": "spell-support",
    },
    "tce-subclassfeature-manifestmind-wizard-phb-scribes-tce-6": {
        "title": "Manifest Mind",
        "reason": "spell-support",
    },
}
MANAGED_RESOURCE_TRACKER_INVENTORY: dict[str, dict[str, str]] = {
    entry["slug"]: {"title": entry["title"], "status": "supported"}
    for family in MANAGED_RESOURCE_FAMILIES
    for entry in family["inventory"]
}
MANAGED_RESOURCE_TRACKER_INVENTORY.update(
    {
        slug: {
            "title": str(entry.get("title") or "").strip(),
            "status": str(entry.get("reason") or "").strip(),
        }
        for slug, entry in MANAGED_RESOURCE_EXCLUSIONS_BY_SLUG.items()
    }
)


def managed_resource_member_by_name(family: dict[str, Any], feature_name: str) -> dict[str, Any] | None:
    normalized_name = normalize_lookup(feature_name)
    if not normalized_name:
        return None
    primary = dict(family.get("primary") or {})
    if normalized_name in set(primary.get("match_names") or ()):
        return primary
    for member in list(family.get("members") or []):
        if normalized_name in set(member.get("match_names") or ()):
            return dict(member)
    return None


def _managed_resource_fallback_categories(feature_payload: dict[str, Any]) -> tuple[str, ...]:
    categories: list[str] = []

    def add_category(value: Any) -> None:
        normalized = normalize_lookup(str(value or "").strip())
        if normalized and normalized not in categories:
            categories.append(normalized)

    add_category(feature_payload.get("category"))
    entry_type = normalize_lookup(str(dict(feature_payload.get("systems_ref") or {}).get("entry_type") or "").strip())
    if entry_type == normalize_lookup("subclassfeature"):
        add_category("subclass_feature")
        add_category("class_feature")
    elif entry_type in {normalize_lookup("classfeature"), normalize_lookup("optionalfeature")}:
        add_category("class_feature")
    return tuple(categories)


def _build_managed_resource_family_maps() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[tuple[str, str, str, str], dict[str, Any]]]:
    families_by_slug: dict[str, dict[str, Any]] = {}
    families_by_page_ref: dict[str, dict[str, Any]] = {}
    fallback_candidates: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for family in MANAGED_RESOURCE_FAMILIES:
        for slug, _member_key in family["match_slug_members"].items():
            if slug:
                families_by_slug[slug] = family
        for page_ref in family["page_refs"]:
            if page_ref:
                families_by_page_ref[page_ref] = family
        if family["allow_fallback"]:
            fallback_candidates.setdefault(family["fallback_key"], []).append(family)
    families_by_fallback = {
        key: families[0]
        for key, families in fallback_candidates.items()
        if len(families) == 1
    }
    return families_by_slug, families_by_page_ref, families_by_fallback


(
    _MANAGED_RESOURCE_FAMILIES_BY_SLUG,
    _MANAGED_RESOURCE_FAMILIES_BY_PAGE_REF,
    _MANAGED_RESOURCE_FAMILIES_BY_FALLBACK,
) = _build_managed_resource_family_maps()


def resolve_managed_resource_family_and_member(feature_payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    systems_ref = dict(feature_payload.get("systems_ref") or {})
    systems_slug = normalize_lookup(str(systems_ref.get("slug") or "").strip())
    page_ref = normalize_lookup(str(feature_payload.get("page_ref") or "").strip())
    family = _MANAGED_RESOURCE_FAMILIES_BY_SLUG.get(systems_slug)
    if family is not None:
        canonical_family_slugs = {
            normalize_lookup(str(entry.get("slug") or "").strip())
            for entry in list(family.get("inventory") or ())
            if normalize_lookup(str(entry.get("slug") or "").strip())
        }
        page_ref_family = _MANAGED_RESOURCE_FAMILIES_BY_PAGE_REF.get(page_ref) if page_ref else None
        if page_ref_family is not None and systems_slug not in canonical_family_slugs:
            family = page_ref_family
        member = managed_resource_member_by_name(family, str(feature_payload.get("name") or ""))
        if member is not None:
            return family, member
        member_key = str(dict(family.get("match_slug_members") or {}).get(systems_slug) or "").strip()
        if member_key:
            return family, dict(dict(family.get("members_by_key") or {}).get(member_key) or {})
        return family, dict(family.get("primary") or {})

    family = _MANAGED_RESOURCE_FAMILIES_BY_PAGE_REF.get(page_ref)
    if family is not None:
        member = managed_resource_member_by_name(family, str(feature_payload.get("name") or ""))
        return family, member or dict(family.get("primary") or {})

    normalized_name = normalize_lookup(str(feature_payload.get("name") or "").strip())
    normalized_source = normalize_lookup(str(feature_payload.get("source") or "").strip())
    for category in _managed_resource_fallback_categories(feature_payload):
        fallback_key = (
            category,
            normalized_name,
            normalized_source,
            "",
        )
        family = _MANAGED_RESOURCE_FAMILIES_BY_FALLBACK.get(fallback_key)
        if family is None:
            continue
        member = managed_resource_member_by_name(family, str(feature_payload.get("name") or ""))
        return family, member or dict(family.get("primary") or {})
    return None, None
