from __future__ import annotations

from .system_policy import XIANXIA_SYSTEM_CODE

BASE_SYSTEMS_ENTRY_TYPE_LABELS = {
    "action": "Actions",
    "background": "Backgrounds",
    "book": "Book Chapters",
    "class": "Classes",
    "classfeature": "Class Features",
    "condition": "Conditions",
    "disease": "Diseases",
    "feat": "Feats",
    "item": "Items",
    "monster": "Monsters",
    "optionalfeature": "Optional Features",
    "race": "Races",
    "rule": "Rules",
    "sense": "Senses",
    "skill": "Skills",
    "spell": "Spells",
    "status": "Statuses",
    "subclass": "Subclasses",
    "subclassfeature": "Subclass Features",
    "variantrule": "Variant Rules",
}
XIANXIA_SYSTEMS_ENTRY_TYPE_LABELS = {
    "attribute": "Attributes",
    "effort": "Efforts",
    "energy": "Energies",
    "yin_yang": "Yin/Yang",
    "dao": "Dao",
    "realm": "Realms",
    "honor_rank": "Honor Ranks",
    "skill_rule": "Skill Rules",
    "equipment": "Equipment",
    "armor": "Armor",
    "martial_art": "Martial Arts",
    "martial_art_rank": "Martial Art Ranks",
    "technique": "Techniques",
    "maneuver": "Maneuvers",
    "stance": "Stances",
    "aura": "Auras",
    "generic_technique": "Generic Techniques",
    "basic_action": "Basic Actions",
    "karmic_constraint_rule": "Karmic Constraint Rules",
    "ascendant_art_rule": "Ascendant Art Rules",
    "dao_immolating_rule": "Dao Immolating Rules",
    "range_rule": "Range Rules",
    "timing_rule": "Timing Rules",
    "critical_hit_rule": "Critical Hit Rules",
    "sneak_attack_rule": "Sneak Attack Rules",
    "dying_rule": "Dying Rules",
    "minion_tag": "Minion Tags",
    "companion_rule": "Companion Rules",
    "gm_approval_rule": "GM Approval Rules",
}
SYSTEMS_ENTRY_TYPE_LABELS = {
    **BASE_SYSTEMS_ENTRY_TYPE_LABELS,
    **XIANXIA_SYSTEMS_ENTRY_TYPE_LABELS,
}
SYSTEMS_ENTRY_TYPE_ORDER = (
    "book",
    "class",
    "subclass",
    "classfeature",
    "subclassfeature",
    "spell",
    "feat",
    "optionalfeature",
    "item",
    "race",
    "rule",
    "background",
    "action",
    "skill",
    "sense",
    "variantrule",
    "condition",
    "status",
    "disease",
    "monster",
    "basic_action",
    "attribute",
    "effort",
    "energy",
    "yin_yang",
    "dao",
    "realm",
    "honor_rank",
    "skill_rule",
    "equipment",
    "armor",
    "martial_art",
    "martial_art_rank",
    "technique",
    "maneuver",
    "stance",
    "aura",
    "generic_technique",
    "karmic_constraint_rule",
    "ascendant_art_rule",
    "dao_immolating_rule",
    "range_rule",
    "timing_rule",
    "critical_hit_rule",
    "sneak_attack_rule",
    "dying_rule",
    "minion_tag",
    "companion_rule",
    "gm_approval_rule",
)
SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES = {"classfeature", "optionalfeature", "subclassfeature"}


def systems_entry_type_label(entry_type: str) -> str:
    normalized = str(entry_type or "").strip().lower()
    return SYSTEMS_ENTRY_TYPE_LABELS.get(
        normalized,
        normalized.replace("_", " ").replace("-", " ").title(),
    )


def systems_entry_type_sort_key(entry_type: str) -> tuple[int, str]:
    normalized = str(entry_type or "").strip().lower()
    try:
        return (SYSTEMS_ENTRY_TYPE_ORDER.index(normalized), normalized)
    except ValueError:
        return (len(SYSTEMS_ENTRY_TYPE_ORDER), normalized)


def systems_entry_type_choice_labels(library_slug: str) -> dict[str, str]:
    labels = dict(BASE_SYSTEMS_ENTRY_TYPE_LABELS)
    if str(library_slug or "").strip().lower() == XIANXIA_SYSTEM_CODE.lower():
        labels.update(XIANXIA_SYSTEMS_ENTRY_TYPE_LABELS)
    return labels


def systems_source_browse_intro(library_slug: str) -> str:
    if str(library_slug or "").strip().lower() == XIANXIA_SYSTEM_CODE.lower():
        return (
            "Choose a Xianxia content category to load that entry list. Rules, Martial Arts, "
            "techniques, equipment, and other Xianxia catalogs stay separated by source policy."
        )
    return (
        "Choose a content category to load that entry list. Large sources stay lighter when "
        "each category loads on its own page."
    )
