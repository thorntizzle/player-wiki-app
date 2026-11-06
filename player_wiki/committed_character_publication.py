"""Atomic Character definition authority for activated committed-source mode.

The SQLite generation is the success boundary. Files are independently
recoverable mirrors and are never consulted to decide a Character write.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePath
from uuid import uuid4

import yaml

from .character_importer import render_character_yaml
from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
from .character_path_safety import validate_character_slug
from .character_store import CharacterStateConflictError, CharacterStateUnavailableError
from .committed_publication import CommittedSourceConflict, _reserve, config, current, read_snapshot
from .committed_source_store import _now, _record_status, _character_system_code
from .db import get_db
from .system_policy import normalize_system_code


MAX_PAIR_BYTES = 2 * 1024 * 1024
MAX_CREATE_SOURCE_LINKS = 256
MAX_CREATE_PAGE_LINKS = 64


@dataclass(frozen=True, slots=True)
class CreateSourceProof:
    config_revision: int
    current_session: int
    systems_token: str
    library_slug: str
    pages: tuple[tuple[str, str, int, str], ...]
    entries: tuple[tuple[str, str, str, str, str, str, str, str], ...]


@dataclass(frozen=True, slots=True, order=True)
class CreateSourceLink:
    owner: str
    field_kind: str
    source_kind: str
    identity: str
    allowed_types: tuple[str, ...]
    expected_slug: str = ""
    expected_source_id: str = ""
    expected_type: str = ""
    expected_title: str = ""
    expected_library: str = ""
    companion_option_json: str = ""
    companion_spell_manager_json: str = ""
    companion_name: str = ""
    companion_description: str = ""
    companion_source: str = ""
    companion_activation: str = ""
    companion_tracker_ref: str = ""
    companion_feature_id: str = ""
    companion_tracker_json: str = ""
    companion_level: int = 1
    parent_class_owner: str = ""
    subclass_companion_json: str = ""
    parent_facet_json: str = ""
    armor_model_json: str = ""
    parent_companion_json: str = ""


_FEATURE_TYPES = ("classfeature", "feat", "feature", "optionalfeature", "subclassfeature")
_ITEM_TYPES = ("item",)
_XIANXIA_EQUIPMENT_TYPES = ("armor", "equipment", "item", "tool", "weapon")
_EXACT_LINK_FIELDS = frozenset({
    "systems_ref", "page_ref", "class_ref", "subclass_ref", "species_ref",
    "background_ref", "species_page_ref", "background_page_ref",
})


def _claim(value):
    if value is None or value == {} or value == []:
        return False
    return not (isinstance(value, str) and not value.strip())


def _inert_item_context_metadata(metadata: dict) -> bool:
    """A paired Items page describes the item; it cannot supply mechanics."""
    from math import isfinite
    from .campaign_item_mechanics import CAMPAIGN_ITEM_METADATA_KEYS

    if not isinstance(metadata, dict) or "character_option" in metadata:
        return False
    item_fields = {field.casefold() for field in CAMPAIGN_ITEM_METADATA_KEYS} - {"type"}
    for key, value in metadata.items():
        if not isinstance(key, str):
            return False
        lowered = key.casefold()
        if lowered == "type":
            if key != "type" or not isinstance(value, str) or not value.strip():
                return False
        elif isinstance(value, (dict, list)):
            # Structured metadata could carry a nested mechanics model.
            return False
        elif isinstance(value, float) and not isfinite(value):
            return False
        elif (lowered in item_fields or lowered.startswith("campaign_item_mechanics")
              or lowered.startswith("item_") or "mechanic" in lowered
              or "review" in lowered or "model" in lowered):
            if _claim(value):
                return False
    return True


def _link_kind(path: tuple[str | int, ...], field: str, system: str):
    """Give an explicit link the mechanics kind of its owning retained row."""
    if len(path) < 2:
        return None
    if path[:2] == ("definition", "profile"):
        if len(path) == 2 and field in {"class_ref", "subclass_ref", "species_ref",
                                        "background_ref", "species_page_ref", "background_page_ref"}:
            return field.removesuffix("_page_ref").removesuffix("_ref")
        if len(path) == 4 and path[2] == "classes" and isinstance(path[3], int):
            return "subclass" if field == "subclass_ref" else "class" if field == "systems_ref" else None
        return None
    if (len(path) == 4 and path[:3] == ("definition", "spellcasting", "class_rows")
            and isinstance(path[3], int) and field == "class_ref"):
        return "class"
    if (len(path) == 5 and path[:4] == ("definition", "source", "native_progression", "history")
            and isinstance(path[4], int) and field in {"class_ref", "subclass_ref"}):
        return "subclass" if field == "subclass_ref" else "class"
    if field in {"class_ref", "subclass_ref", "species_ref", "background_ref",
                 "species_page_ref", "background_page_ref"}:
        return None
    if path[0] == "definition" and path[1] not in {
            "features", "attacks", "equipment_catalog", "spellcasting", "xianxia"}:
        return None
    if path[0] == "initial_state" and path[1] not in {"inventory", "spellcasting", "xianxia"}:
        return None
    if path[1] == "xianxia":
        allowed_xianxia_roots = (
            {"martial_arts", "generic_techniques", "equipment", "inventory",
             "dao_immolating_techniques", "techniques", "maneuvers", "stances", "auras"}
            if path[0] == "definition" else
            {"inventory", "active_stance", "active_aura", "active_state"}
        )
        if len(path) < 3 or path[2] not in allowed_xianxia_roots:
            return None
    if "generic_techniques" in path:
        return "generic_technique"
    for segment, kind in (("techniques", "technique"), ("maneuvers", "maneuver"),
                          ("stances", "stance"), ("auras", "aura"),
                          ("martial_art_ranks", "martial_art_rank")):
        if segment in path:
            return kind
    if "active_stance" in path:
        return "stance"
    if "active_aura" in path:
        return "aura"
    if "martial_arts" in path:
        return "martial_art"
    if "necessary_weapons" in path or "necessary_tools" in path:
        return "xianxia_equipment"
    if "spells" in path or "additional_spells" in path:
        return "spell"
    if path[1] in {"equipment_catalog", "attacks", "inventory"} or "inventory" in path or "equipment" in path:
        return "xianxia_equipment" if system == "Xianxia" else "item"
    if path[1] == "features" or "features" in path or "grants" in path or "feats" in path:
        return "feature"
    if path[1] == "spellcasting":
        return "spell"
    return None


def _link_owner(path: tuple[str | int, ...]) -> str:
    owner = str(path[0])
    for segment in path[1:]:
        owner += f"[{segment}]" if isinstance(segment, int) else f".{segment}"
    return owner


def _paired_page_feature_links(definition: CharacterDefinition, links: set[CreateSourceLink]):
    """Recognize one retained companion row per page-backed profile choice."""
    by_owner = {link.owner: link for link in links}
    profile_pages = {
        subject: by_owner.get(f"definition.profile.{subject}_page_ref")
        for subject in ("species", "background")
    }
    if (profile_pages["species"] is not None and profile_pages["background"] is not None and
            profile_pages["species"].identity == profile_pages["background"].identity):
        raise CommittedSourceConflict("Character species and background cannot share one page choice.")
    paired: dict[str, str] = {}
    for item in definition.equipment_catalog or []:
        if isinstance(item, dict) and isinstance(item.get("campaign_option"), dict) and (
                str(item["campaign_option"].get("kind") or "").strip().lower()
                in {"species", "background"}):
            raise CommittedSourceConflict("Character equipment has an unpaired profile option grant.")
    allowed_fields = {
        "id", "name", "category", "kind", "source", "description_markdown",
        "activation_type", "tracker_ref", "systems_ref", "page_ref",
        "campaign_option", "spell_manager",
    }
    for index, feature in enumerate(definition.features or []):
        if not isinstance(feature, dict):
            continue
        owner = f"definition.features[{index}].page_ref"
        link = by_owner.get(owner)
        category = str(feature.get("category") or feature.get("kind") or "").strip()
        subject = {"species_trait": "species", "background_feature": "background"}.get(category)
        raw_option = feature.get("campaign_option")
        option_kind = str(raw_option.get("kind") or "").strip().lower() if isinstance(raw_option, dict) else ""
        if _claim(raw_option) and not (_claim(feature.get("page_ref")) or
                                       _claim(feature.get("systems_ref"))):
            raise CommittedSourceConflict("Character feature option has no exact source link.")
        if link is None or subject is None:
            if (option_kind in {"species", "background"} or
                    subject is not None and (_claim(raw_option) or _claim(feature.get("spell_manager")))):
                raise CommittedSourceConflict("Character has an unpaired species or background grant.")
            continue
        if (_claim(feature.get("kind")) and feature["kind"] != category or
                _claim(feature.get("category")) and feature["category"] != category):
            raise CommittedSourceConflict("Character page companion has a contradictory feature kind.")
        profile_link = profile_pages[subject]
        if profile_link is None or profile_link.identity != link.identity:
            raise CommittedSourceConflict("Character page companion does not match its profile choice.")
        if subject in paired:
            raise CommittedSourceConflict("Character has duplicate page companion grants.")
        if any(_claim(value) for field, value in feature.items() if field not in allowed_fields):
            raise CommittedSourceConflict("Character page companion has independent mechanics.")
        if _claim(feature.get("systems_ref")):
            raise CommittedSourceConflict("Character page companion has conflicting mechanics or source.")
        option = raw_option
        if _claim(option) and not isinstance(option, dict):
            raise CommittedSourceConflict("Character page companion option is malformed.")
        option = dict(option or {})
        activation = str(feature.get("activation_type") or "").strip()
        if activation != str(option.get("activation_type") or "passive").strip():
            raise CommittedSourceConflict("Character page companion activation differs from its selected option.")
        option_link = by_owner.get(f"definition.features[{index}].campaign_option.page_ref")
        if option and (option_link is None or option_link.identity != link.identity or
                       str(option.get("kind") or "").strip().lower() != subject):
            raise CommittedSourceConflict("Character page companion option disagrees with its profile choice.")
        manager = feature.get("spell_manager")
        if _claim(manager) and (not isinstance(manager, dict) or not option):
            raise CommittedSourceConflict("Character page companion has unproved spell mechanics.")
        tracker_ref = str(feature.get("tracker_ref") or "").strip()
        if tracker_ref and not option:
            raise CommittedSourceConflict("Character page companion has an unproved tracker.")
        feature_id = str(feature.get("id") or "").strip()
        tracker_json = ""
        if not tracker_ref and feature_id and any(
                isinstance(row, dict) and row.get("id") == f"campaign-option-tracker:{feature_id}"
                for row in (definition.resource_templates or [])):
            raise CommittedSourceConflict("Character page companion has an orphaned option tracker.")
        if tracker_ref:
            matches = [row for row in (definition.resource_templates or [])
                       if isinstance(row, dict) and row.get("id") == tracker_ref]
            if (not feature_id or tracker_ref != f"campaign-option-tracker:{feature_id}"
                    or len(matches) != 1):
                raise CommittedSourceConflict("Character page companion tracker is unpaired.")
            tracker_json = json.dumps(matches[0], sort_keys=True, ensure_ascii=False)
        from .character_profile import profile_total_level
        paired[subject] = owner
        links.remove(link)
        links.add(replace(
            link, field_kind=subject, allowed_types=(subject,),
            companion_option_json=json.dumps(option, sort_keys=True, ensure_ascii=False) if option else "",
            companion_spell_manager_json=json.dumps(manager, sort_keys=True, ensure_ascii=False) if manager else "",
            companion_name=str(feature.get("name") or "").strip(),
            companion_description=str(feature.get("description_markdown") or "").strip(),
            companion_source=str(feature.get("source") or "").strip(),
            companion_activation=str(feature.get("activation_type") or "").strip(),
            companion_tracker_ref=tracker_ref,
            companion_feature_id=feature_id,
            companion_tracker_json=tracker_json,
            companion_level=profile_total_level(definition.profile, default=1),
        ))
        if option_link is not None:
            links.remove(option_link)
            links.add(replace(option_link, field_kind=subject, allowed_types=(subject,)))
    for link in links:
        if link.source_kind != "page" or not link.owner.startswith("definition.features["):
            continue
        for subject, profile_link in profile_pages.items():
            if profile_link is not None and link.identity == profile_link.identity and (
                    link.owner != paired.get(subject) and
                    link.owner != paired.get(subject, "").removesuffix(".page_ref") + ".campaign_option.page_ref"):
                raise CommittedSourceConflict("Character page choice has an independent or duplicate feature claim.")
    return links


def _companion_spell_manager_matches(link: CreateSourceLink, option: dict) -> bool:
    """Accept only a manager payload obtainable from the current page option."""
    from .character_builder_spells import (
        _campaign_feature_spell_manager_entries,
        _campaign_feature_spell_manager_source_row_payload,
        _selected_campaign_feature_spell_manager_config,
        _structured_spell_manager_option_value,
        _structured_spell_manager_payload,
    )

    manager_entries = _campaign_feature_spell_manager_entries(
        [{"page_ref": link.identity, "label": link.companion_name,
          "campaign_option": option}], field_prefix_base="campaign_spell_manager",
    )
    if len(manager_entries) != 1:
        return False
    manager_entry = manager_entries[0]
    support = dict(manager_entry.get("support_config") or {})
    source_options = support.get("source_options") or []
    if (not isinstance(source_options, list) or len(source_options) > 64 or
            any(not isinstance(item, dict) for item in source_options)):
        return False
    selections = (
        [_structured_spell_manager_option_value(item, index)
         for index, item in enumerate(source_options, start=1)]
    )
    if not source_options:
        selections = [""]
    for selection in selections:
        selected = _selected_campaign_feature_spell_manager_config(
            manager_entry,
            {f"{manager_entry['field_prefix']}_source_1": selection} if selection else {},
        )
        if not selected:
            continue
        row = _campaign_feature_spell_manager_source_row_payload(
            manager_entry, support_config=selected,
        )
        expected = _structured_spell_manager_payload(
            support_config=selected, source_row_payload=row,
        )
        if expected is not None and json.dumps(expected, sort_keys=True, ensure_ascii=False) == link.companion_spell_manager_json:
            return True
    return False


def _companion_tracker_matches(link: CreateSourceLink, option: dict) -> bool:
    from .character_builder_features import _build_campaign_option_tracker_template

    expected = _build_campaign_option_tracker_template(
        {"id": link.companion_feature_id, "name": link.companion_name,
         "campaign_option": option, "activation_type": link.companion_activation,
         "tracker_ref": link.companion_tracker_ref},
        display_order=0, current_level=link.companion_level,
    )
    if expected is None:
        return False
    expected.pop("activation_type", None)
    actual = json.loads(link.companion_tracker_json)
    if not isinstance(actual, dict):
        return False
    expected.pop("display_order", None)
    actual.pop("display_order", None)
    return expected == actual


def _companion_display_matches(link: CreateSourceLink, option: dict, page_ref: str) -> bool:
    return (
        link.companion_name == str(option.get("display_name") or "").strip()
        and link.companion_description == str(option.get("description_markdown") or "").strip()
        and link.companion_source == page_ref
        and link.companion_activation == str(option.get("activation_type") or "passive").strip()
    )


def _allowed_types(field_kind: str, source_kind: str):
    if field_kind in {"class", "subclass", "background", "spell", "martial_art",
                      "martial_art_rank", "generic_technique", "technique", "maneuver",
                      "stance", "aura"}:
        return (field_kind,)
    if field_kind == "species":
        return ("race", "subrace", "species")
    if field_kind == "feature":
        return _FEATURE_TYPES if source_kind != "page" else ("feature", "feat")
    if field_kind == "reconstruction_feature":
        return (*_FEATURE_TYPES, "race", "subrace", "background") if source_kind != "page" else ()
    if field_kind in {"item", "item_reference"}:
        return _ITEM_TYPES
    if field_kind == "xianxia_equipment":
        return _XIANXIA_EQUIPMENT_TYPES
    return ()


def _exact_page_link(value, owner, field_kind):
    from .character_source_authority import _page_ref
    if isinstance(value, dict):
        if any(isinstance(item, (dict, list)) for item in value.values()):
            raise CommittedSourceConflict(f"Character page link at {owner} is malformed.")
        if any(_claim(value.get(field)) for field in _EXACT_LINK_FIELDS - {"page_ref"}):
            raise CommittedSourceConflict(f"Character page link at {owner} is contradictory.")
        claims = [value[key] for key in ("page_ref", "slug", "page_slug") if _claim(value.get(key))]
        if not claims or any(not isinstance(item, str) for item in claims):
            raise CommittedSourceConflict(f"Character page link at {owner} is malformed.")
        refs = {_page_ref(item) for item in claims}
        if len(refs) != 1:
            raise CommittedSourceConflict(f"Character page link at {owner} is contradictory.")
        ref = refs.pop()
    elif isinstance(value, str):
        ref = _page_ref(value)
    else:
        raise CommittedSourceConflict(f"Character page link at {owner} is malformed.")
    if not ref or ref.startswith("../") or "/../" in ref or ref == "..":
        raise CommittedSourceConflict(f"Character page link at {owner} has no exact identity.")
    return CreateSourceLink(owner, field_kind, "page", ref, _allowed_types(field_kind, "page"))


def _exact_systems_link(value, owner, field_kind):
    if not isinstance(value, dict):
        raise CommittedSourceConflict(f"Character Systems link at {owner} is malformed.")
    if any(isinstance(item, (dict, list)) for item in value.values()):
        raise CommittedSourceConflict(f"Character Systems link at {owner} is malformed.")
    if any(_claim(value.get(field)) for field in _EXACT_LINK_FIELDS):
        raise CommittedSourceConflict(f"Character Systems link at {owner} is contradictory.")
    for field in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug"):
        if field in value and value[field] is not None and not isinstance(value[field], str):
            raise CommittedSourceConflict(f"Character Systems link at {owner} is malformed.")
    key = str(value.get("entry_key") or "").strip()
    slug = str(value.get("slug") or "").strip()
    if not key and not slug:
        raise CommittedSourceConflict(f"Character Systems link at {owner} has no exact identity.")
    expected_type = str(value.get("entry_type") or "").strip()
    allowed = _allowed_types(field_kind, "systems")
    if expected_type and expected_type not in allowed:
        raise CommittedSourceConflict(f"Character Systems link at {owner} has the wrong kind.")
    return CreateSourceLink(
        owner, field_kind, "systems_key" if key else "systems_slug", key or slug, allowed,
        slug if key else "", str(value.get("source_id") or "").strip(),
        expected_type, str(value.get("title") or "").strip(),
        str(value.get("library_slug") or "").strip(),
    )


def _progression_history_tokens(definition: CharacterDefinition) -> tuple[str, ...]:
    """Identify immutable events, without turning history into current authority."""
    progression = (definition.source or {}).get("native_progression")
    if progression is None:
        return ()
    if not isinstance(progression, dict):
        raise CommittedSourceConflict("Character progression history is malformed.")
    history = progression.get("history", [])
    if not isinstance(history, list) or any(not isinstance(event, dict) for event in history):
        raise CommittedSourceConflict("Character progression history is malformed.")
    if len(history) > 10000:
        raise CommittedSourceConflict("Character source links exceed their preparation bound.")
    try:
        return tuple(json.dumps(event, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False) for event in history)
    except (TypeError, ValueError, RecursionError) as exc:
        raise CommittedSourceConflict("Character progression history is malformed.") from exc


def _create_source_links(definition: CharacterDefinition, initial_state: dict, *,
                         retained_history: tuple[str, ...] = (), retained_reconstruction=False,
                         retained_item_mappings=()):
    """Enumerate typed exact claims in the canonical pair and prepared state."""
    if ("native_spell_grants" in definition.spellcasting or "native_acquisitions" in definition.source):
        from .character_spell_grants import validate_native_grant_model
        try:
            validate_native_grant_model(definition)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise CommittedSourceConflict("Character native grant evidence is invalid.") from exc
    history = _progression_history_tokens(definition)
    if history[:len(retained_history)] != retained_history:
        raise CommittedSourceConflict("Character retained progression history changed.")
    from .character_reconstruction_authority import reconstruction_source_links
    try:
        reconstruction_links = reconstruction_source_links(definition, retained=retained_reconstruction,
                                                            retained_item_mappings=retained_item_mappings)
    except (TypeError, ValueError, KeyError) as exc:
        raise CommittedSourceConflict("Character reconstruction source evidence is invalid.") from exc
    links: set[CreateSourceLink] = set()
    parent_companion_claims = set()
    pending = [(definition.to_dict(), ("definition",), 0), (initial_state, ("initial_state",), 0)]
    visited = 0
    while pending:
        value, path, depth = pending.pop()
        visited += 1
        if visited > 10000 or depth > 24:
            raise CommittedSourceConflict("Character source links exceed their preparation bound.")
        if isinstance(value, dict):
            dual_item = (
                normalize_system_code(definition.system) == "DND-5E"
                and len(path) == 3 and path[:2] == ("definition", "equipment_catalog")
                and isinstance(path[2], int)
                and _claim(value.get("systems_ref")) and _claim(value.get("page_ref"))
            )
            evidence_dual = reconstruction_links.get((*path, "systems_ref"), {}).get("dual", False)
            if _claim(value.get("systems_ref")) and _claim(value.get("page_ref")) and not (dual_item or evidence_dual):
                raise CommittedSourceConflict(f"Character source row at {_link_owner(path)} has conflicting links.")
            for field, child in value.items():
                if path == ("definition", "source") and field == "source_authorizations":
                    # Private numeric markers carry page_ref as evidence, not as
                    # a Character source claim. Their audit and basis are checked
                    # separately; retained feature/page links remain below.
                    continue
                child_path = (*path, field)
                child_owner = _link_owner(child_path)
                if (field in _EXACT_LINK_FIELDS or child_path in reconstruction_links) and _claim(child):
                    parent_class_owner = ""
                    if isinstance(child, dict):
                        visited += 1
                        if visited > 10000 or depth + 1 > 24:
                            raise CommittedSourceConflict("Character source links exceed their preparation bound.")
                    evidence = reconstruction_links.get(child_path, {})
                    kind = evidence.get("kind") or _link_kind(path, field, normalize_system_code(definition.system))
                    parent_class_owner = evidence.get("parent", "")
                    if kind is None:
                        raise CommittedSourceConflict(f"Character source link at {child_owner} has no owning kind.")
                    if path[:4] == ("definition", "source", "native_progression", "history"):
                        from .character_profile import profile_class_rows
                        owners = [(index, row) for index, row in enumerate(profile_class_rows(definition.profile))
                                  if isinstance(value.get("class_row_id"), str)
                                  and value["class_row_id"].strip()
                                  and row.get("row_id") == value["class_row_id"]]
                        if len(owners) != 1:
                            raise CommittedSourceConflict("Character progression source disagrees with its class row.")
                        index, owner = owners[0]
                        # Only the exact committed prefix may describe a former
                        # class/subclass after repair. New events bind today's row.
                        if path[4] >= len(retained_history):
                            row_field = "subclass_ref" if field == "subclass_ref" else "systems_ref"
                            if child != owner.get(row_field):
                                raise CommittedSourceConflict("Character progression source disagrees with its class row.")
                            if field == "subclass_ref":
                                if not _claim(value.get("class_ref")) or value["class_ref"] != owner.get("systems_ref"):
                                    raise CommittedSourceConflict("Character progression subclass has no matching class source.")
                                parent_class_owner = f"definition.profile.classes[{index}].systems_ref"
                    if field.endswith("page_ref"):
                        links.add(_exact_page_link(child, child_owner,
                                                   "item_context" if dual_item else kind))
                    else:
                        companion = None
                        if (normalize_system_code(definition.system) == "DND-5E"
                                and len(path) == 3 and path[:2] == ("definition", "features")
                                and isinstance(path[2], int) and field == "systems_ref"):
                            from .character_background_companion import is_systems_background_companion
                            if is_systems_background_companion(value, definition.profile):
                                kind, companion = "background", value
                            elif isinstance(child, dict) and child.get("entry_type") in {"race", "subrace"}:
                                from .character_parent_facets import inert, parent
                                if (inert(value, "species", linked=True)
                                        and child == parent(definition.profile, "species")):
                                    kind, companion = "species", value
                        link = _exact_systems_link(child, child_owner, kind)
                        if parent_class_owner:
                            link = replace(link, parent_class_owner=parent_class_owner)
                        if evidence.get("companion") is not None:
                            link = replace(link, subclass_companion_json=json.dumps(
                                evidence["companion"], sort_keys=True, ensure_ascii=False, allow_nan=False))
                        if evidence.get("parent_facet") is not None:
                            link = replace(link, parent_facet_json=json.dumps(
                                evidence["parent_facet"], sort_keys=True, ensure_ascii=False, allow_nan=False))
                        if evidence.get("armor_model") is not None:
                            link = replace(link, armor_model_json=json.dumps(
                                evidence["armor_model"], sort_keys=True, ensure_ascii=False, allow_nan=False))
                        if companion is not None:
                            claim = (child.get("entry_key"), companion["name"])
                            if claim in parent_companion_claims:
                                raise CommittedSourceConflict("Character has duplicate selected parent companions.")
                            parent_companion_claims.add(claim)
                            link = replace(link,
                                parent_companion_json=json.dumps(companion, sort_keys=True, ensure_ascii=False, allow_nan=False),
                                companion_feature_id=companion["id"],
                                companion_name=companion["name"],
                                companion_description=companion["description_markdown"],
                                companion_source=companion["source"],
                                companion_activation="passive")
                        links.add(link)
                elif isinstance(child, (dict, list)):
                    pending.append((child, child_path, depth + 1))
        elif isinstance(value, list):
            pending.extend((child, (*path, index), depth + 1)
                           for index, child in enumerate(value) if isinstance(child, (dict, list)))
    links = _paired_page_feature_links(definition, links)
    pages = tuple(sorted(link for link in links if link.source_kind == "page"))
    entries = tuple(sorted(link for link in links if link.source_kind != "page"))
    if len(pages) > MAX_CREATE_PAGE_LINKS or len(links) > MAX_CREATE_SOURCE_LINKS:
        raise CommittedSourceConflict("Character has too many linked sources for one publication.")
    profile = definition.profile or {}
    if isinstance(profile, dict):
        rows = profile.get("classes") or []
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            primary = rows[0]
            for alias, row_field in (("class_ref", "systems_ref"), ("subclass_ref", "subclass_ref")):
                alias_value, row_value = profile.get(alias), primary.get(row_field)
                if _claim(alias_value) and _claim(row_value):
                    if not isinstance(alias_value, dict) or not isinstance(row_value, dict):
                        raise CommittedSourceConflict("Character primary class link is malformed.")
                    for field in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug"):
                        left, right = alias_value.get(field), row_value.get(field)
                        if _claim(left) and _claim(right) and left != right:
                            raise CommittedSourceConflict("Character primary class row and alias disagree.")
        for subject in ("species", "background"):
            if _claim(profile.get(f"{subject}_ref")) and _claim(profile.get(f"{subject}_page_ref")):
                raise CommittedSourceConflict(f"Character {subject} has conflicting page and Systems links.")
    if (definition.source or {}).get("source_type") == "native_character_builder" and not entries:
        raise CommittedSourceConflict("Native Character creation has no exact Systems source proof.")
    return pages, entries


def _create_source_proof(campaign_slug, pages, entries, *, connection):
    """Select linked source proof through the caller's SQLite snapshot."""
    from .committed_publication import page_row
    from .models import is_deprecated_wiki_identity
    from .system_policy import default_systems_library_slug
    from .campaign_item_mechanics import (
        campaign_item_mechanics_is_approved, is_campaign_item_mechanics_metadata,
    )
    from .character_campaign_options import normalize_campaign_character_option
    from .character_builder_constants import CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND
    from .repository import normalize_lookup

    settings_source, settings = config(campaign_slug, connection=connection)
    raw_session = settings.get("current_session", 0)
    if type(raw_session) is int:
        session = raw_session
    elif isinstance(raw_session, str) and raw_session.strip().isdecimal():
        session = int(raw_session.strip())
    else:
        session = -1
    if session < 0:
        raise CommittedSourceConflict("Committed campaign session proof is malformed.")
    token_row = connection.execute("SELECT token FROM systems_revision WHERE singleton=1").fetchone()
    if token_row is None or not isinstance(token_row["token"], str) or not token_row["token"]:
        raise CommittedSourceConflict("Systems revision proof is unavailable.")
    library_slug = default_systems_library_slug(settings.get("systems_library") or settings["system"])
    page_proofs = []
    page_records = {}
    entry_owners = {link.owner for link in entries if link.field_kind == "item"}
    context_entry_owners = {
        link.owner.removesuffix(".page_ref") + ".systems_ref"
        for link in pages if link.field_kind == "item_context"
    }
    for link in pages:
        ref = link.identity
        if link.field_kind == "item_context" and (
                link.owner.removesuffix(".page_ref") + ".systems_ref" not in entry_owners):
            raise CommittedSourceConflict("Character item context has no paired Systems mechanics source.")
        if ref not in page_records:
            source = current(campaign_slug, "page", ref, connection=connection)
            row = page_row(campaign_slug, ref, connection=connection) if source is not None else None
            page_records[ref] = (source, row)
        source, row = page_records[ref]
        if (source is None or row is None or row["published"] != 1
                or row["section"] not in {"Mechanics", "Items", "Spells"}
                or type(row["reveal_after_session"]) is not int
                or row["reveal_after_session"] > session
                or is_deprecated_wiki_identity(row["section"], row["page_type"])):
            raise CommittedSourceConflict("Character page source is unavailable or hidden.")
        required_section = {
            "species": {"Mechanics"}, "background": {"Mechanics"},
            "feature": {"Mechanics"}, "item": {"Items"}, "item_context": {"Items"}, "item_reference": {"Items"},
            "spell": {"Mechanics", "Spells"},
            "xianxia_equipment": {"Items"},
        }.get(link.field_kind, set())
        if row["section"] not in required_section:
            raise CommittedSourceConflict(f"Character page source at {link.owner} has the wrong section.")
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError) as exc:
            raise CommittedSourceConflict("Character page mechanics are malformed.") from exc
        if not isinstance(metadata, dict):
            raise CommittedSourceConflict("Character page mechanics are malformed.")
        if link.field_kind == "item_context" and not _inert_item_context_metadata(metadata):
            raise CommittedSourceConflict(f"Character item context at {link.owner} claims mechanics.")
        if link.field_kind in {"species", "background", "feature"}:
            raw_option = metadata.get("character_option")
            option = (
                normalize_campaign_character_option(
                    raw_option, page_ref=ref, title=row["title"],
                    summary=row["summary"], default_kind=link.field_kind,
                ) if isinstance(raw_option, dict) else None
            )
            if (not isinstance(raw_option, dict) or
                    str(raw_option.get("kind") or "").strip().lower() not in link.allowed_types or
                    option is None):
                raise CommittedSourceConflict(f"Character page source at {link.owner} has no approved option kind.")
            if link.companion_option_json and json.dumps(option, sort_keys=True, ensure_ascii=False) != link.companion_option_json:
                raise CommittedSourceConflict("Character page companion mechanics differ from its committed option.")
            if link.owner.startswith("definition.features[") and link.owner.endswith(".page_ref") and link.field_kind in {"species", "background"}:
                if not _companion_display_matches(link, option, ref):
                    raise CommittedSourceConflict("Character page companion display or activation differs from its committed option.")
            if link.companion_spell_manager_json and not _companion_spell_manager_matches(link, option):
                raise CommittedSourceConflict("Character page companion spell mechanics differ from its option.")
            if link.companion_tracker_ref and not _companion_tracker_matches(link, option):
                raise CommittedSourceConflict("Character page companion tracker differs from its option.")
            allowed_subsections = CAMPAIGN_MIXED_SOURCE_SUBSECTIONS_BY_KIND.get(link.field_kind)
            subsection = normalize_lookup(str(row["subsection"] or ""))
            if allowed_subsections is not None and subsection and subsection not in allowed_subsections:
                raise CommittedSourceConflict(f"Character page source at {link.owner} has the wrong subsection.")
        if link.field_kind in {"item", "xianxia_equipment"} and (
                not is_campaign_item_mechanics_metadata(metadata) or
                not campaign_item_mechanics_is_approved(metadata)):
            raise CommittedSourceConflict(f"Character item page at {link.owner} needs mechanics review.")
        if link.field_kind in {"item", "xianxia_equipment"} and "character_option" in metadata:
            option = metadata["character_option"]
            if not isinstance(option, dict) or str(option.get("kind") or "").strip().lower() != "item":
                raise CommittedSourceConflict(f"Character item page at {link.owner} has the wrong option kind.")
        page_proofs.append((link.owner, ref, int(source["revision"]), source["primary_sha256"]))
    entry_proofs = []
    entry_metadata = {}
    if entries:
        library = connection.execute(
            "SELECT status,system_code FROM systems_libraries WHERE library_slug=?",
            (library_slug,),
        ).fetchone()
        policy = connection.execute(
            "SELECT library_slug,status FROM campaign_system_policies WHERE campaign_slug=?",
            (campaign_slug,),
        ).fetchone()
        if (library is None or library["status"] != "active"
                or normalize_system_code(library["system_code"]) != normalize_system_code(settings["system"])
                or policy is not None and (policy["library_slug"] != library_slug
                                           or policy["status"] != "active")):
            raise CommittedSourceConflict("Character Systems library or policy is unavailable.")
        from .systems_service import BUILTIN_LIBRARY_CATALOG
        defaults = {
            row["source_id"]: bool(row.get("enabled_by_default", False))
            for row in BUILTIN_LIBRARY_CATALOG.get(library_slug, {}).get("sources", ())
        }
        seeds = {
            str(row.get("source_id") or "").strip(): bool(row.get("enabled"))
            for row in (settings.get("systems_sources") or ())
            if isinstance(row, dict) and "enabled" in row
        }
        for link in entries:
            if link.expected_library and link.expected_library != library_slug:
                raise CommittedSourceConflict(f"Character Systems library at {link.owner} changed.")
            column = "entry_key" if link.source_kind == "systems_key" else "slug"
            matches = connection.execute(
                f"SELECT entry_key,slug,source_id,entry_type,title,metadata_json,body_json FROM systems_entries "
                f"WHERE library_slug=? AND {column}=?", (library_slug, link.identity),
            ).fetchall()
            if len(matches) != 1:
                raise CommittedSourceConflict("Character Systems entry is missing or ambiguous.")
            entry = matches[0]
            if link.expected_slug and entry["slug"] != link.expected_slug:
                raise CommittedSourceConflict("Character Systems link identity changed.")
            if (entry["entry_type"] not in link.allowed_types or
                    link.expected_source_id and entry["source_id"] != link.expected_source_id or
                    link.expected_type and entry["entry_type"] != link.expected_type or
                    link.expected_title and entry["title"] != link.expected_title):
                raise CommittedSourceConflict("Character Systems link metadata changed.")
            try:
                metadata = json.loads(entry["metadata_json"] or "{}")
            except (TypeError, ValueError) as exc:
                raise CommittedSourceConflict("Character Systems mechanics are malformed.") from exc
            if not isinstance(metadata, dict) or (
                    is_campaign_item_mechanics_metadata(metadata) and
                    not campaign_item_mechanics_is_approved(metadata)):
                raise CommittedSourceConflict("Character Systems mechanics need review.")
            entry_metadata[link.owner] = metadata
            if link.armor_model_json:
                from types import SimpleNamespace
                from .character_armor_models import MODEL, supported_rule
                choice = json.loads(link.armor_model_json)
                if entry["entry_key"] == MODEL and not supported_rule(SimpleNamespace(
                        **dict(entry), metadata=metadata, body=json.loads(entry["body_json"]))):
                    raise CommittedSourceConflict("The selected Armor Model rule changed during publication.")
            if link.parent_facet_json or link.parent_companion_json:
                from types import SimpleNamespace
                from .character_parent_facets import current_facet, linked_companion_facet
                try:
                    current_entry = SimpleNamespace(**dict(entry), library_slug=library_slug,
                                                    metadata=metadata, body=json.loads(entry["body_json"]))
                    if link.parent_facet_json:
                        mapping = json.loads(link.parent_facet_json)
                        facet = current_facet(current_entry, mapping["facet"])
                        valid = facet is not None and facet["location"] == mapping["location"]
                    else:
                        companion = json.loads(link.parent_companion_json)
                        role = "background" if entry["entry_type"] == "background" else "species"
                        valid = linked_companion_facet(companion,
                            {role + "_ref": companion["systems_ref"]}, current_entry) is not None
                except (KeyError, TypeError, ValueError):
                    valid = False
                if not valid:
                    raise CommittedSourceConflict("Character parent facet is unavailable or structurally changed.")
            if link.field_kind == "background" and link.owner.startswith("definition.features["):
                from types import SimpleNamespace
                from .character_background_companion import systems_background_companion_matches
                ref = {key: entry[key] for key in
                       ("entry_key", "slug", "source_id", "entry_type", "title")}
                feature = {"id": link.companion_feature_id, "category": "background_feature", "systems_ref": ref,
                           "name": link.companion_name, "source": link.companion_source,
                           "description_markdown": link.companion_description,
                           "activation_type": link.companion_activation}
                try:
                    current_entry = SimpleNamespace(**dict(entry), library_slug=library_slug,
                                                    body=json.loads(entry["body_json"]))
                    valid = systems_background_companion_matches(
                        feature, {"background_ref": ref}, current_entry)
                except (TypeError, ValueError):
                    valid = False
                if not valid:
                    raise CommittedSourceConflict("Character background feature differs from its current source.")
            if link.owner in context_entry_owners and (
                    link.field_kind != "item" or
                    not is_campaign_item_mechanics_metadata(metadata) or
                    not campaign_item_mechanics_is_approved(metadata)):
                raise CommittedSourceConflict("Character item context needs approved Systems mechanics.")
            source = connection.execute(
                "SELECT status FROM systems_sources WHERE library_slug=? AND source_id=?",
                (library_slug, entry["source_id"]),
            ).fetchone()
            enabled = connection.execute(
                "SELECT library_slug,is_enabled FROM campaign_enabled_sources "
                "WHERE campaign_slug=? AND source_id=?",
                (campaign_slug, entry["source_id"]),
            ).fetchone()
            override = connection.execute(
                "SELECT library_slug,is_enabled_override FROM campaign_entry_overrides "
                "WHERE campaign_slug=? AND entry_key=?",
                (campaign_slug, entry["entry_key"]),
            ).fetchone()
            allowed = (enabled["library_slug"] == library_slug and enabled["is_enabled"] == 1
                       if enabled is not None else
                       seeds.get(entry["source_id"], defaults.get(entry["source_id"], False)))
            if (source is None or source["status"] != "active" or not allowed
                    or enabled is not None and enabled["is_enabled"] not in (0, 1)
                    or override is not None and (override["library_slug"] != library_slug
                                                 or override["is_enabled_override"] not in (None, 0, 1)
                                                 or override["is_enabled_override"] == 0)):
                raise CommittedSourceConflict("Character Systems source or entry is disabled.")
            entry_proofs.append((link.owner, link.source_kind, link.identity, entry["slug"],
                                 entry["entry_key"], entry["source_id"], entry["entry_type"], entry["title"]))
    proofs_by_owner = {row[0]: row for row in entry_proofs}
    for link in entries:
        if not link.parent_class_owner:
            continue
        parent = proofs_by_owner.get(link.parent_class_owner)
        child = proofs_by_owner.get(link.owner)
        metadata = entry_metadata.get(link.owner, {})
        if (parent is None or child is None or parent[6] != "class" or child[6] != "subclass"
                or normalize_lookup(str(metadata.get("class_name") or "")) != normalize_lookup(parent[7])
                or str(metadata.get("class_source") or "").strip().upper() != parent[5].strip().upper()):
            raise CommittedSourceConflict("Character progression subclass belongs to another class source.")
        if link.subclass_companion_json:
            from types import SimpleNamespace
            from .character_subclass_companion import selected_subclass_companion_matches
            def record(proof):
                return SimpleNamespace(entry_key=proof[4], slug=proof[3], source_id=proof[5],
                    entry_type=proof[6], title=proof[7], library_slug=library_slug,
                    metadata=entry_metadata[proof[0]])
            cls, subclass = record(parent), record(child)
            ref = lambda entry: {key: getattr(entry, key) for key in
                                ("entry_key", "slug", "source_id", "entry_type", "title")}
            service = SimpleNamespace(get_entry_for_campaign=lambda campaign, key:
                                      cls if campaign == campaign_slug and key == cls.entry_key else None)
            if not selected_subclass_companion_matches(json.loads(link.subclass_companion_json),
                    {"classes": [{"systems_ref": ref(cls), "subclass_ref": ref(subclass)}]},
                    subclass, service, campaign_slug):
                raise CommittedSourceConflict("Character subclass container is not the exact inert selected companion.")
    resolved = {row[0]: row[4] for row in entry_proofs}
    for alias, row_field in (("class_ref", "systems_ref"), ("subclass_ref", "subclass_ref")):
        alias_owner = f"definition.profile.{alias}"
        row_owner = f"definition.profile.classes[0].{row_field}"
        if alias_owner in resolved and row_owner in resolved and resolved[alias_owner] != resolved[row_owner]:
            raise CommittedSourceConflict("Character primary class row and alias disagree.")
    return CreateSourceProof(int(settings_source["revision"]), session, token_row["token"],
                             library_slug, tuple(page_proofs), tuple(entry_proofs))


def _update_source_claims(prior_record, definition, prepared_state):
    """Reprove changed exact claims, including a moved list owner."""
    from .character_reconstruction_authority import _retained_reconstruction_item_mappings
    try:
        prior_item_history = _retained_reconstruction_item_mappings(prior_record.definition, prior_record.definition)
        candidate_item_history = _retained_reconstruction_item_mappings(prior_record.definition, definition)
    except (TypeError, ValueError, KeyError) as exc:
        raise CommittedSourceConflict("Character retained item evidence changed.") from exc
    retained_history = _progression_history_tokens(prior_record.definition)
    prior_pages, prior_entries = _create_source_links(
        prior_record.definition, prior_record.state_record.state,
        retained_history=retained_history,
        retained_reconstruction=bool(prior_record.definition.source.get("native_reconstruction")),
        retained_item_mappings=prior_item_history,
    )
    # Only the byte-identical frame of the exact prior committed pair can keep
    # other historical owner links after an ordinary repair. Item mappings use
    # the exact per-entry comparison above, so unrelated advancement cannot
    # resurrect a removed physical owner. New layers still bind current owners.
    # The coordinator independently rejects copied origins/unreviewed changes.
    from .character_language_electives import historical_choices_equal
    retained_reconstruction = bool(prior_record.definition.source.get("native_reconstruction")) and (
        definition.source.get("native_reconstruction") == prior_record.definition.source.get("native_reconstruction")
        and historical_choices_equal(prior_record.definition, definition))
    pages, entries = _create_source_links(definition, prepared_state,
        retained_history=retained_history, retained_reconstruction=retained_reconstruction,
        retained_item_mappings=candidate_item_history)
    prior = set((*prior_pages, *prior_entries))
    changed = {link for link in (*pages, *entries) if link not in prior}
    for link in entries:
        if link.parent_class_owner:
            parents = [parent for parent in entries if parent.owner == link.parent_class_owner]
            if len(parents) != 1:
                raise CommittedSourceConflict("Character progression subclass has no unique class source.")
            new_reconstruction = (definition.source.get("native_reconstruction")
                                  != prior_record.definition.source.get("native_reconstruction"))
            if not link.subclass_companion_json or new_reconstruction or link in changed or parents[0] in changed:
                changed.update((link, parents[0]))
    # The primary class alias and its row must still resolve to one entry if
    # either claim changes. A disabled retained companion cannot certify a
    # newly retargeted alias through the retained-link exception.
    coupled = (
        ("definition.profile.class_ref", "definition.profile.classes[0].systems_ref"),
        ("definition.profile.subclass_ref", "definition.profile.classes[0].subclass_ref"),
    )
    for owners in coupled:
        if any(link.owner in owners for link in changed):
            changed.update(link for link in entries if link.owner in owners)
    for link in pages:
        if link.field_kind != "item_context":
            continue
        paired_owner = link.owner.removesuffix(".page_ref") + ".systems_ref"
        pair = [entry for entry in entries if entry.owner == paired_owner]
        if len(pair) != 1:
            raise CommittedSourceConflict("Character item context has no unique Systems mechanics source.")
        # A retained context link is still a current claim on every update.
        # Reprove both owners together so a page or Systems change fails closed.
        changed.update((link, pair[0]))
    return (pages, entries,
            tuple(link for link in pages if link in changed),
            tuple(link for link in entries if link in changed))


def _sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _native_create_grant_source_frame(definition, actor_id):
    """Bind current feature sources before creation, without issuing custody.

    Replaying the shared producer inspects a proposed model. Actual acquisition
    custody still requires its independent saved audit and generation.
    """
    if "native_spell_grants" not in definition.spellcasting and "native_acquisitions" not in definition.source:
        return None
    from .auth import get_systems_service
    from .character_spell_grants import (AcquisitionContext, build_occurrences,
        canonical_digest, validate_native_grant_model)
    try:
        model = validate_native_grant_model(definition)
        intent = definition.source["native_acquisitions"]["intent"]
        context = AcquisitionContext(intent.get("intent_id"), definition.campaign_slug,
            actor_id, "create", None, None, None)
        if (type(actor_id) is not int or actor_id < 1 or intent != context.to_dict()
                or not isinstance(context.intent_id, str) or len(context.intent_id) != 64):
            raise ValueError("Creation acquisition intent changed.")
        rebuilt_model, rebuilt_acquisitions = build_occurrences(
            definition, get_systems_service(), acquisition_context=context)
        if (rebuilt_model != model or rebuilt_acquisitions != definition.source["native_acquisitions"]):
            raise ValueError("Creation feature-grant producer changed.")
        return canonical_digest({"model": rebuilt_model, "acquisitions": rebuilt_acquisitions})
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise CharacterStateConflictError("Native creation feature-grant sources need review.") from exc


def exact_character(campaign_slug: str, character_slug: str, *, connection=None,
                    allow_tombstone: bool = False):
    """Return a digest-checked pair, never a file/cache or half a generation."""
    from .committed_source_store import _load_committed_yaml

    connection = connection or get_db()
    _reject_journals(connection, campaign_slug, character_slug)
    row = current(campaign_slug, "character", character_slug,
                  connection=connection, allow_tombstone=allow_tombstone)
    if row is None:
        return None
    if row["tombstone"]:
        if any(row[key] is not None for key in (
            "primary_bytes", "secondary_bytes", "primary_sha256", "secondary_sha256"
        )):
            raise CommittedSourceConflict("Character tombstone proof is invalid.")
        return row
    secondary = row["secondary_bytes"]
    if (not isinstance(secondary, bytes) or not secondary or len(secondary) > MAX_PAIR_BYTES
            or _sha(secondary) != row["secondary_sha256"]):
        raise CommittedSourceConflict("Committed Character import proof failed; manager repair required.")
    try:
        definition = _load_committed_yaml(row["primary_bytes"])
        imported = _load_committed_yaml(secondary)
    except (UnicodeError, yaml.YAMLError, ValueError, OverflowError, RecursionError) as exc:
        raise CommittedSourceConflict("Committed Character pair is malformed; manager repair required.") from exc
    if (not isinstance(definition, dict) or not isinstance(imported, dict)
            or definition.get("campaign_slug") != campaign_slug
            or definition.get("character_slug") != character_slug
            or imported.get("campaign_slug") != campaign_slug
            or imported.get("character_slug") != character_slug
            or not isinstance(definition.get("name"), str) or not definition["name"].strip()
            or not isinstance(definition.get("status"), str) or not definition["status"].strip()
            or _character_system_code(definition) != row["system_code"]
            or not all(isinstance(imported.get(key), str) for key in
                       ("source_path", "imported_at_utc", "parser_version", "import_status"))
            or not isinstance(imported.get("warnings"), list)
            or not all(isinstance(value, str) for value in imported["warnings"])):
        raise CommittedSourceConflict("Committed Character identity failed; manager repair required.")
    return row


def portrait_bytes(campaign_slug: str, character_slug: str, *, connection=None):
    connection = connection or get_db()
    owned = not connection.in_transaction
    if owned:
        connection.execute("BEGIN")
    try:
        return _portrait_bytes_in_snapshot(campaign_slug, character_slug, connection)
    finally:
        if owned:
            connection.rollback()


def _portrait_bytes_in_snapshot(campaign_slug: str, character_slug: str, connection):
    from .committed_source_store import _load_committed_yaml

    source = exact_character(campaign_slug, character_slug, connection=connection)
    if source is None:
        return None
    definition = _load_committed_yaml(source["primary_bytes"])
    profile = definition.get("profile") or {}
    if not isinstance(profile, dict):
        raise CommittedSourceConflict("Character portrait metadata is malformed.")
    ref = str(profile.get("portrait_asset_ref") or "").strip()
    proof = connection.execute(
        "SELECT asset_ref, sha256, image_bytes FROM committed_character_portraits "
        "WHERE campaign_slug=? AND character_slug=? AND revision=?",
        (campaign_slug, character_slug, source["revision"]),
    ).fetchone()
    if not ref:
        if proof is not None:
            raise CommittedSourceConflict("Unexpected Character portrait proof; manager repair required.")
        return None
    from .character_assets import resolve_character_portrait_asset_path
    from .character_repository import load_campaign_character_config
    from flask import current_app
    resolve_character_portrait_asset_path(
        load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug).campaign_dir,
        character_slug, ref,
    )
    if (proof is None or proof["asset_ref"] != ref or not isinstance(proof["image_bytes"], bytes)
            or _sha(proof["image_bytes"]) != proof["sha256"]):
        raise CommittedSourceConflict("Character portrait proof failed; manager repair required.")
    from .campaign_content_service import validated_campaign_asset_media_type
    if validated_campaign_asset_media_type(Path(ref), data_blob=proof["image_bytes"]) is None:
        raise CommittedSourceConflict("Character portrait image proof failed; manager repair required.")
    return ref, bytes(proof["image_bytes"])


def load_for_write(repository, campaign_slug: str, character_slug: str) -> CharacterRecord | None:
    from .committed_source_store import _load_committed_yaml

    validate_character_slug(character_slug)
    connection = get_db()
    owned = not connection.in_transaction
    if owned:
        connection.execute("BEGIN")
    try:
        source = exact_character(campaign_slug, character_slug, connection=connection)
        if source is None:
            return None
        # Verify the current portrait even when the caller changes another field.
        portrait_bytes(campaign_slug, character_slug, connection=connection)
        _, settings = config(campaign_slug, connection=connection)
        definition_payload = _load_committed_yaml(source["primary_bytes"])
        if _character_system_code(definition_payload) != normalize_system_code(settings.get("system")):
            raise CommittedSourceConflict("Character system and committed campaign settings differ.")
        imported = _load_committed_yaml(source["secondary_bytes"])
        state = repository.state_store.get_state(campaign_slug, character_slug)
        if state is None:
            raise CharacterStateUnavailableError("Committed Character has no mutable state; manager repair required.")
        return CharacterRecord(
            CharacterDefinition.from_dict(definition_payload),
            CharacterImportMetadata.from_dict(imported), state,
            committed_revision=int(source["revision"]),
        )
    finally:
        if owned:
            connection.rollback()


def _pair(definition, import_metadata):
    primary = render_character_yaml("definition.yaml", definition.to_dict()).encode("utf-8")
    secondary = render_character_yaml("import.yaml", import_metadata.to_dict()).encode("utf-8")
    if not primary or not secondary or len(primary) + len(secondary) > MAX_PAIR_BYTES:
        raise CommittedSourceConflict("Character pair exceeds its committed payload bound.")
    return primary, secondary


def _elective_import_bytes(prior_record, import_metadata, reviewed_source_proof, audit_metadata, *, connection=None):
    """This operation alone preserves the server-owned admitted sidecar bytes.

    No raw bytes parameter or ordinary publication escape hatch is exposed.
    The signed Update review, private proof and locked stored pair must agree.
    """
    from .character_reconciliation import PendingReviewedSourceProof
    from .character_language_electives import PendingElectiveDecision
    if type(reviewed_source_proof) is not PendingReviewedSourceProof:
        raise CharacterStateConflictError("Import preservation requires the exact reviewed language owner.")
    reviewed_source_proof.require_complete()
    elective = reviewed_source_proof.native_elective_decision
    reviewed = audit_metadata.get("language_review_basis") if type(audit_metadata) is dict else None
    if (type(elective) is not PendingElectiveDecision or type(reviewed) is not dict
            or type(reviewed.get("secondary_sha256")) is not str
            or reviewed["secondary_sha256"] != elective.prior_identity["prior_import_raw_digest"]
            or import_metadata.to_dict() != prior_record.import_metadata.to_dict()):
        raise CharacterStateConflictError("The reviewed import identity changed for this language decision.")
    definition = prior_record.definition
    source = exact_character(definition.campaign_slug, definition.character_slug, connection=connection)
    raw = source["secondary_bytes"] if source is not None else None
    if (source is None or source["tombstone"] or source["revision"] != prior_record.committed_revision
            or type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != reviewed["secondary_sha256"]
            or CharacterImportMetadata.from_dict(yaml.safe_load(raw.decode("utf-8"))).to_dict() != import_metadata.to_dict()):
        raise CharacterStateConflictError("The exact stored import sidecar changed; review again.")
    return raw


def _reject_journals(connection, campaign_slug, character_slug):
    for table in ("character_reconciliation_operations", "character_deletion_operations"):
        if connection.execute(
            f"SELECT 1 FROM {table} WHERE campaign_slug=? AND character_slug=? "
            "AND state IN ('prepared','repository_pending','conflict') LIMIT 1",
            (campaign_slug, character_slug),
        ).fetchone():
            raise CommittedSourceConflict("Character has an unresolved journal; manager repair required.")
    if connection.execute(
        "SELECT 1 FROM committed_source_publications WHERE campaign_slug=? "
        "AND object_kind='character' AND object_ref=? AND state IN ('prepared','conflict') LIMIT 1",
        (campaign_slug, character_slug),
    ).fetchone():
        raise CommittedSourceConflict("Character has an unresolved publication; manager repair required.")


def _append(connection, *, campaign_slug, character_slug, previous, primary, secondary,
            portrait, actor, system):
    prior_revision = int(previous["revision"]) if previous else None
    number = (prior_revision or 0) + 1
    now = _now()
    previous_primary = previous["primary_sha256"] if previous else None
    previous_secondary = previous["secondary_sha256"] if previous else None
    connection.execute(
        """INSERT INTO committed_source_generations
        (campaign_slug,object_kind,object_ref,revision,system_code,primary_bytes,
         secondary_bytes,primary_sha256,secondary_sha256,tombstone,actor_user_id,reason,committed_at)
        VALUES (?,'character',?,?,?,?,?,?,?,?,?,?,?)""",
        (campaign_slug, character_slug, number, system, primary, secondary,
         _sha(primary), _sha(secondary), int(primary is None), actor,
         "deletion" if primary is None else "publication", now),
    )
    if portrait is not None:
        ref, image = portrait
        connection.execute(
            "INSERT INTO committed_character_portraits "
            "(campaign_slug,character_slug,revision,asset_ref,sha256,image_bytes) VALUES (?,?,?,?,?,?)",
            (campaign_slug, character_slug, number, ref, _sha(image), image),
        )
    connection.execute(
        "INSERT INTO committed_source_current VALUES (?,'character',?,?) "
        "ON CONFLICT(campaign_slug,object_kind,object_ref) DO UPDATE SET revision=excluded.revision",
        (campaign_slug, character_slug, number),
    )
    _record_status(connection, campaign_slug, "character", character_slug,
                   "admitted", "publication", number)
    connection.execute(
        """INSERT INTO committed_source_publications
        (operation_id,campaign_slug,object_kind,object_ref,state,expected_revision,
         expected_primary_sha256,expected_secondary_sha256,desired_primary_bytes,
         desired_secondary_bytes,desired_primary_sha256,desired_secondary_sha256,
         committed_revision,actor_user_id,created_at,updated_at)
        VALUES (?,?,'character',?,'committed',?,?,?,?,?,?,?,?,?,?,?)""",
        (uuid4().hex, campaign_slug, character_slug, prior_revision, previous_primary,
         previous_secondary, primary, secondary, _sha(primary), _sha(secondary),
         number, actor, now, now),
    )
    pending = connection.execute(
        "SELECT expected_primary_sha256,expected_secondary_sha256 FROM committed_source_outbox "
        "WHERE campaign_slug=? AND object_kind='character' AND object_ref=? "
        "AND state IN ('pending','retry') ORDER BY revision LIMIT 1",
        (campaign_slug, character_slug),
    ).fetchone()
    basis_primary = pending[0] if pending else previous_primary
    basis_secondary = pending[1] if pending else previous_secondary
    connection.execute(
        """INSERT INTO committed_source_outbox
        (campaign_slug,object_kind,object_ref,revision,expected_primary_sha256,
         expected_secondary_sha256,state,created_at,updated_at)
        VALUES (?,'character',?,?,?,?,'pending',?,?)""",
        (campaign_slug, character_slug, number, basis_primary, basis_secondary, now, now),
    )
    return number


def publish_create(coordinator, definition, import_metadata, initial_state, *,
                   operation_kind, updated_by_user_id=None):
    coordinator._validate_create_input(definition, import_metadata, operation_kind)
    expected_native_grants = _native_create_grant_source_frame(definition, updated_by_user_id)
    prepared = coordinator.state_store.prepare_initial_state(definition, initial_state)
    pages, entries = _create_source_links(definition, prepared.validated_state)
    connection = get_db()
    owned_snapshot = not connection.in_transaction
    if owned_snapshot:
        connection.execute("BEGIN")
    try:
        expected_source = _create_source_proof(
            definition.campaign_slug, pages, entries, connection=connection,
        )
    finally:
        if owned_snapshot:
            connection.rollback()
    from .character_equipment_activation import analyze_activation
    from .system_policy import is_dnd_5e_system
    if is_dnd_5e_system(definition.system) and analyze_activation(definition, initial_state)["blocked"]:
        raise CharacterStateConflictError("Equipment activation identity needs repair.")
    primary, secondary = _pair(definition, import_metadata)
    if (definition.profile or {}).get("portrait_asset_ref"):
        raise CommittedSourceConflict("A new portrait requires verified bytes in the same publication.")
    _reserve(connection)
    try:
        locked_config, settings = config(definition.campaign_slug, connection=connection)
        locked_source = _create_source_proof(
            definition.campaign_slug, pages, entries, connection=connection,
        )
        if (locked_source != expected_source
                or locked_config["revision"] != expected_source.config_revision
                or normalize_system_code(settings.get("system")) != definition.system):
            raise CommittedSourceConflict("Character source changed before publication.")
        if _native_create_grant_source_frame(definition, updated_by_user_id) != expected_native_grants:
            raise CharacterStateConflictError("Native creation feature-grant sources changed before publication.")
        slug = definition.character_slug
        _reject_journals(connection, definition.campaign_slug, slug)
        pointer = connection.execute(
            "SELECT revision FROM committed_source_current WHERE campaign_slug=? "
            "AND object_kind='character' AND object_ref=?", (definition.campaign_slug, slug)
        ).fetchone()
        if pointer is not None or connection.execute(
            "SELECT 1 FROM character_state WHERE campaign_slug=? AND character_slug=?",
            (definition.campaign_slug, slug),
        ).fetchone() or connection.execute(
            "SELECT 1 FROM character_assignments WHERE campaign_slug=? AND character_slug=?",
            (definition.campaign_slug, slug),
        ).fetchone():
            raise CharacterStateConflictError("Character already exists or needs manager repair.")
        coordinator.state_store.insert_initial_state_in_transaction(
            connection, definition, prepared, updated_at=_now(),
            updated_by_user_id=updated_by_user_id,
        )
        number = _append(connection, campaign_slug=definition.campaign_slug, character_slug=slug,
                         previous=None, primary=primary, secondary=secondary, portrait=None,
                         actor=updated_by_user_id, system=definition.system)
        state = coordinator.state_store.get_state(definition.campaign_slug, slug)
        if state is None:
            raise CharacterStateUnavailableError("Committed Character state was not inserted.")
        result = CharacterRecord(definition, import_metadata, state, committed_revision=number)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    coordinator.repository.invalidate_character(definition.campaign_slug, definition.character_slug)
    _replay_after_commit(coordinator.campaigns_dir, definition.campaign_slug)
    return result


def _prepare_transition_renewals(prior_record, definition, state, authority,
                                 prior_authority, connection, *, withheld_resource_ids=(),
                                 prior_authority_provider=None, reviewed_source_proof=None, actor_id=None,
                                 spell_choice_decisions=(), source_read_owner=None):
    """Prove each surviving activation chain against the proposed exact owner."""
    from .character_equipment_activation import effective_definition
    from .character_source_authority import (
        numeric_target_owner_digest, numeric_target_values, numeric_value_digest,
        valid_numeric_authorization,
    )
    from .character_source_repair import _current_transition_proof_rows

    campaign, slug = definition.campaign_slug, definition.character_slug
    prior = _current_transition_proof_rows(connection, campaign, slug)
    if not prior:
        return ()
    if authority is None:
        raise CharacterStateConflictError("Character transition source authority is unavailable.")
    reconciled, _ = effective_definition(definition, state)
    values = numeric_target_values(reconciled, state)
    markers = list(dict(reconciled.source or {}).get("source_authorizations") or [])
    withheld = {("resource", f"resource:{resource_id}", "owner_reset")
                for resource_id in withheld_resource_ids}
    if withheld and (set(dict(reconciled.source or {}).get(
            "item_transition_withheld_resources") or []) != set(withheld_resource_ids)):
        raise CharacterStateConflictError("Withheld resource identity changed.")
    prior_effective, _ = effective_definition(
        prior_record.definition, prior_record.state_record.state,
    )
    prior_values = numeric_target_values(prior_effective, prior_record.state_record.state)
    prior_markers = list(dict(prior_effective.source or {}).get("source_authorizations") or [])
    origin_plan = (reviewed_source_proof.native_spell_origin_delta(
        prior_record, definition, state, actor_id, source_read_owner=source_read_owner)
        if reviewed_source_proof is not None else None)
    migrated_choices = ({("spell_choice", f"spell_choice:{row['spell_id']}", "selection")
        for row in (*origin_plan["automatic"], *origin_plan["removed"])}
        if origin_plan is not None and origin_plan.get("schema_version") == 2 else set())
    superseded_choices = {("spell_choice", f"spell_choice:{row['spell_id']}", "selection"): row
        for row in spell_choice_decisions
        if row["operation"] in {"retire", "continue", "prepare", "reactivate"}
        and isinstance(row.get("prior_authorization"), dict)}
    prepared = []
    seen = set()
    for row in prior:
        proof = row["proof"]
        key = (proof["target_kind"], proof["target_id"], proof["metric"])
        if key in migrated_choices or key in superseded_choices:
            # The old chain is custody for an observed aggregate, not a veto
            # on an independently proved positive feature occurrence. Retire
            # only this exact choice claim; never renew it as a new grant.
            old_matching = [marker for marker in prior_markers if isinstance(marker, dict)
                and (marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) == key]
            prior_owner = numeric_target_owner_digest(prior_effective, prior_record.state_record.state, *key)
            if (key in seen or len(old_matching) != 1 or old_matching[0] != proof["authorization"]
                    or key not in prior_values or prior_owner != proof["owner_digest"]
                    or numeric_value_digest(prior_values[key]) != proof["value_digest"]
                    or not valid_numeric_authorization(old_matching[0], character_slug=slug,
                        target_kind=key[0], target_id=key[1], metric=key[2], raw_value=prior_values[key],
                        owner_digest=prior_owner, verified_actions=(old_matching[0],))):
                raise CharacterStateConflictError("A migrated spell needs exact independent prior custody.")
            if key in superseded_choices:
                decision = superseded_choices[key]
                current_matching = [marker for marker in markers if isinstance(marker, dict) and
                    (marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) == key]
                if (decision["prior_authorization"] != old_matching[0]
                        or decision["prior_owner_digest"] != prior_owner
                        or decision["before_row_digest"] != numeric_value_digest(prior_values[key])
                        or len(current_matching) != 1 or key not in values
                        or current_matching[0].get("schema_version") != 2
                        or current_matching[0].get("value_digest") != decision["after_row_digest"]
                        or numeric_value_digest(values[key]) != decision["after_row_digest"]
                        or not valid_numeric_authorization(current_matching[0], character_slug=slug,
                            target_kind=key[0], target_id=key[1], metric=key[2], raw_value=values[key],
                            verified_actions=(current_matching[0],))):
                    raise CharacterStateConflictError("A superseded choice needs its exact prior and replacement marker.")
                # This ends only the old claim. The selected/leveled event must
                # independently confirm its replacement; no count is refunded.
            seen.add(key)
            continue
        if prior_authority is None and prior_authority_provider is not None:
            prior_authority = prior_authority_provider()
        if prior_authority is None:
            raise CharacterStateConflictError("Character transition source authority is unavailable.")
        if (proof["new_basis"] != prior_authority.numeric_basis_digest(key[1])
                or proof["new_snapshot"] != prior_authority.source_snapshot_digest):
            if key in withheld:
                raise CharacterStateConflictError("Withheld resource proof is stale.")
            continue
        if key in seen:
            raise CharacterStateConflictError("Character transition target is ambiguous.")
        seen.add(key)
        if key in withheld:
            old_matching = [marker for marker in prior_markers if isinstance(marker, dict)
                            and (marker.get("target_kind"), marker.get("target_id"),
                                 marker.get("metric")) == key]
            current_matching = [marker for marker in markers if isinstance(marker, dict)
                                and (marker.get("target_kind"), marker.get("target_id"),
                                     marker.get("metric")) == key]
            resource_id = key[1].removeprefix("resource:")
            templates = [template for template in definition.resource_templates
                         if isinstance(template, dict) and template.get("id") == resource_id]
            state_rows = [resource for resource in state.get("resources") or []
                          if isinstance(resource, dict) and resource.get("id") == resource_id]
            if (len(old_matching) != 1 or old_matching[0] != proof["authorization"]
                    or len(current_matching) != 1 or current_matching[0] != old_matching[0]
                    or key not in prior_values
                    or numeric_target_owner_digest(prior_effective,
                        prior_record.state_record.state, *key) != proof["owner_digest"]
                    or numeric_value_digest(prior_values[key]) != proof["value_digest"]
                    or len(templates) != 1 or len(state_rows) != 1
                    or any(templates[0].get(field) is not None
                           for field in ("max", "initial_current"))
                    or any(state_rows[0].get(field) is not None
                           for field in ("max", "current"))
                    or str(templates[0].get("authority_status") or "").casefold()
                       != "needs repair"
                    or str(state_rows[0].get("authority_status") or "").casefold()
                       != "needs repair"):
                raise CharacterStateConflictError("Withheld resource proof needs manager repair.")
            continue
        matching = [marker for marker in markers if isinstance(marker, dict)
                    and (marker.get("target_kind"), marker.get("target_id"),
                         marker.get("metric")) == key]
        if not matching and key not in values:
            # An explicitly removed target needs no new claim.
            continue
        if (len(matching) == 1 and matching[0] != proof["authorization"] and origin_plan is not None
                and matching[0] in reviewed_source_proof.native_requalification_markers
                and matching[0].get("provenance") == "native_requalification"):
            old_matching = [marker for marker in prior_markers if isinstance(marker, dict)
                            and (marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) == key]
            prior_owner = numeric_target_owner_digest(prior_effective, prior_record.state_record.state, *key)
            if (len(old_matching) != 1 or old_matching[0] != proof["authorization"] or key not in prior_values
                    or prior_owner != proof["owner_digest"]
                    or numeric_value_digest(prior_values[key]) != proof["value_digest"]
                    or not valid_numeric_authorization(old_matching[0], character_slug=slug,
                        target_kind=key[0], target_id=key[1], metric=key[2], raw_value=prior_values[key],
                        owner_digest=prior_owner, verified_actions=(old_matching[0],))
                    or key not in values or not authority.numeric_basis_digest(key[1])
                    or not valid_numeric_authorization(matching[0], character_slug=slug,
                        target_kind=key[0], target_id=key[1], metric=key[2], raw_value=values[key],
                        verified_actions=(matching[0],))):
                raise CharacterStateConflictError("A replaced native transition needs exact prior and reviewed current ownership.")
            # The new confirmed native batch, not a forged old-origin renewal,
            # will own this exact replacement. Retain all historical audit rows.
            continue
        if len(matching) != 1 or matching[0] != proof["authorization"] or key not in values:
            raise CharacterStateConflictError("Character transition owner needs manager repair.")
        owner = numeric_target_owner_digest(reconciled, state, *key)
        value = numeric_value_digest(values[key])
        basis = authority.numeric_basis_digest(key[1])
        snapshot = authority.source_snapshot_digest
        if (owner != proof["owner_digest"] or value != proof["value_digest"]
                or not basis or not snapshot
                or not valid_numeric_authorization(
                    matching[0], character_slug=slug, target_kind=key[0],
                    target_id=key[1], metric=key[2], raw_value=values[key],
                    owner_digest=owner, verified_actions=(matching[0],))):
            raise CharacterStateConflictError("Character transition source or owner changed.")
        prepared.append({
            **{name: proof[name] for name in (
                "campaign_slug", "character_slug", "target_kind", "target_id", "metric",
                "authorization", "origin_audit_id", "origin_actor_user_id",
                "origin_event_type", "origin_metadata_sha256", "value_digest",
                "owner_digest", "activated_at")},
            "schema_version": 2,
            "old_basis": proof["new_basis"], "new_basis": basis,
            "old_snapshot": proof["new_snapshot"], "new_snapshot": snapshot,
            "prior_generation": proof["identity"]["generation"],
            "prior_transition_audit_id": row["audit_id"],
            "prior_transition_metadata_sha256": row["metadata_sha256"],
        })
    return tuple(prepared)


def _append_transition_renewals(connection, campaign, slug, renewals):
    if not renewals:
        return
    from .character_source_repair import (_current_transition_identity,
                                          _current_transition_proof_rows)

    identity = _current_transition_identity(connection, campaign, slug)
    if not identity:
        raise CharacterStateConflictError("Character transition identity is unavailable.")
    expected = []
    audit_rows = connection.execute(
        """SELECT id,actor_user_id,event_type,metadata_json FROM auth_audit_log
           WHERE campaign_slug=? AND character_slug=? ORDER BY id""",
        (campaign, slug),
    ).fetchall()
    audit_digest = hashlib.sha256(b"[")
    for index, row in enumerate(audit_rows):
        if index:
            audit_digest.update(b",")
        audit_digest.update(json.dumps(tuple(row), sort_keys=True, default=str,
                                       separators=(",", ":")).encode())
    audit_count = len(audit_rows)
    for renewal in renewals:
        closed_digest = audit_digest.copy()
        closed_digest.update(b"]")
        proof = {**renewal, "identity": {**identity, "audit": closed_digest.hexdigest()}}
        metadata = json.dumps(proof, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False)
        cursor = connection.execute(
            """INSERT INTO auth_audit_log
               (actor_user_id,target_user_id,campaign_slug,character_slug,
                event_type,metadata_json,created_at)
               VALUES (NULL,NULL,?,?,'character_source_transition_confirmed',?,?)""",
            (campaign, slug, metadata, _now()),
        )
        expected.append(cursor.lastrowid)
        if audit_count:
            audit_digest.update(b",")
        audit_digest.update(json.dumps((cursor.lastrowid, None,
            "character_source_transition_confirmed", metadata), sort_keys=True,
            default=str, separators=(",", ":")).encode())
        audit_count += 1
    loaded = _current_transition_proof_rows(connection, campaign, slug)
    if not all(sum(row["audit_id"] == audit_id for row in loaded) == 1
               for audit_id in expected):
        raise CharacterStateConflictError("Character transition readback failed.")


def _authenticated_reconstruction_item_ids(prior_definition, definition,
                                          candidate_authority, prior_state, *,
                                          reconstruction=None, prior_record=None,
                                          actor_id=None, same_physical_mapping=None, source_read_owner=None):
    """Qualify additive source authentication of exact retained physical owners.

    This decision is shared by both retirement consumers. A stored mapping or
    a caller-supplied item ID alone never exempts an owner from retirement.
    Currentness is rechecked by the publisher before each validation boundary.
    """
    if same_physical_mapping is not None:
        from .character_reconstruction_items import PendingSamePhysicalItemMapping
        from .character_source_reads import SourceReadOwner, native_character_source_context
        from flask import current_app
        if (reconstruction is not None or type(same_physical_mapping) is not PendingSamePhysicalItemMapping
                or prior_record is None or prior_definition.to_dict() != prior_record.definition.to_dict()):
            raise CharacterStateConflictError("The additive physical source mapping has conflicting ownership.")
        same_physical_mapping.validate_binding(prior_record, definition, prior_state, actor_id)
        owned = source_read_owner is None
        owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
            get_db(), definition.campaign_slug, definition.character_slug)
        try:
            with native_character_source_context(prior_record, source_read_owner=owner,
                    systems_service=current_app.extensions["systems_service"],
                    purpose="same-physical-publication-check") as (phase, service, pages, _owner):
                if phase is None:
                    raise CharacterStateConflictError("Same-physical mapping needs an initialized source snapshot.")
                same_physical_mapping.validate_sources(prior_record, service, pages)
            owner.checkpoint()
        finally:
            if owned:
                owner.close()
        if candidate_authority is None or candidate_authority.status_for("item", same_physical_mapping.target_id) != "VERIFIED":
            raise CharacterStateConflictError("The same physical item's current source is not qualified.")
        return frozenset({same_physical_mapping.target_id})
    if reconstruction is None:
        return frozenset()
    from .character_equipment_activation import require_update_activation
    from .character_reconstruction_authority import PendingNativeReconstruction
    from .character_source_authority import VERIFIED
    if (not isinstance(reconstruction, PendingNativeReconstruction) or prior_record is None
            or prior_definition.to_dict() != prior_record.definition.to_dict()):
        raise CharacterStateConflictError("An exact physical mapping needs reconstruction proof.")
    reconstruction.validate_binding(prior_record, definition, prior_state, actor_id)
    require_update_activation(prior_record, definition, prior_state,
        reconstruction=reconstruction, actor_id=actor_id)
    new_items = {str(item.get("id") or "").strip(): item
                 for item in definition.equipment_catalog
                 if isinstance(item, dict) and not item.get("is_currency_only")}
    authenticated = set()
    for item in prior_definition.equipment_catalog:
        if not isinstance(item, dict) or item.get("is_currency_only"):
            continue
        item_id = str(item.get("id") or "").strip()
        if (item_id in new_items and item != new_items[item_id]
                and reconstruction.permits_item_mapping(prior_record, definition, item_id)):
            if candidate_authority is None or candidate_authority.status_for("item", item_id) != VERIFIED:
                raise CharacterStateConflictError("The authenticated physical item's current source is not qualified.")
            authenticated.add(item_id)
    return frozenset(authenticated)


def _reject_retired_item_spell_rows(prior_definition, definition,
                                    candidate_authority=None, prior_state=None, *,
                                    reconstruction=None, prior_record=None, actor_id=None,
                                    same_physical_mapping=None, source_read_owner=None):
    """Raw removal or relink cannot carry the old item's spell claims."""
    from .system_policy import is_dnd_5e_system
    if not is_dnd_5e_system(definition.system):
        return
    previous = {str(item.get("id") or "").strip(): item
                for item in prior_definition.equipment_catalog if isinstance(item, dict)}
    current = {str(item.get("id") or "").strip(): item
               for item in definition.equipment_catalog if isinstance(item, dict)}
    authenticated = _authenticated_reconstruction_item_ids(
        prior_definition, definition, candidate_authority, prior_state,
        reconstruction=reconstruction, prior_record=prior_record, actor_id=actor_id,
        same_physical_mapping=same_physical_mapping, source_read_owner=source_read_owner,
    )
    relinked = {item_id for item_id, old in previous.items()
                if item_id and item_id not in authenticated and (item_id not in current
                or old.get("systems_ref") != current[item_id].get("systems_ref"))}
    if not relinked:
        return
    old_spells = list(dict(prior_definition.spellcasting or {}).get("spells") or [])
    old_source_ids = {
        str(spell.get("spell_source_row_id") or "").strip()
        for spell in old_spells if isinstance(spell, dict)
        and isinstance(spell.get("item_owner_ids"), list)
        and relinked.intersection(spell["item_owner_ids"])
        and str(spell.get("spell_source_row_id") or "").strip()
    }
    retired_spell_ids = {
        str(spell.get("id") or "").strip()
        for spell in old_spells if isinstance(spell, dict)
        and isinstance(spell.get("item_owner_ids"), list)
        and relinked.intersection(spell["item_owner_ids"])
        and str(spell.get("id") or "").strip()
    }
    from flask import current_app
    from .character_source_authority import _current_payload, _source_identity
    from .item_spell_support import parse_item_spell_support
    retired_source_ids = set()
    systems_service = current_app.extensions.get("systems_service")
    for item_id in relinked:
        item = previous[item_id]
        source_kind, source_key = _source_identity(item)
        if not source_kind.startswith("systems") or not source_key or systems_service is None:
            continue
        metadata, reason = _current_payload(
            campaign_slug=prior_definition.campaign_slug, kind="item",
            source_kind=source_kind, source_key=source_key,
            systems_service=systems_service, pages={},
            expected_slug=str(dict(item.get("systems_ref") or {}).get("slug") or ""),
            expected_ref=dict(item.get("systems_ref") or {}),
        )
        if reason or metadata is None:
            continue
        parsed = parse_item_spell_support(metadata.get("spell_support"))
        retired_source_ids.update(row.source_row_id for row in parsed.records
                                  if row.source_row_id)
        retired_source_ids.update(source_id for _, source_id, _, _ in
                                  parsed.source_declarations if source_id)
    legacy_spell_ids = {
        str(spell.get("id") or "").strip()
        for spell in old_spells if isinstance(spell, dict)
        and (spell.get("spell_grant_origin") == "item_effect"
             or spell.get("spell_source_row_kind") == "item")
        and not spell.get("item_owner_ids")
        and str(spell.get("spell_source_row_id") or "").strip() in retired_source_ids
        and str(spell.get("id") or "").strip()
    }
    old_source_ids.update(
        str(spell.get("spell_source_row_id") or "").strip()
        for spell in old_spells if isinstance(spell, dict)
        and str(spell.get("id") or "").strip() in legacy_spell_ids
        and str(spell.get("spell_source_row_id") or "").strip()
    )
    if not old_source_ids and len(previous) == len(relinked):
        old_source_ids.update(
            str(row.get("source_row_id") or "").strip()
            for row in list(dict(prior_definition.spellcasting or {}).get("source_rows") or [])
            if isinstance(row, dict) and row.get("source_row_kind") == "item"
            and str(row.get("source_row_id") or "").strip()
        )
    candidate = dict(definition.spellcasting or {})
    old_refs = {json.dumps(previous[item_id]["systems_ref"], sort_keys=True)
                for item_id in relinked if previous[item_id].get("systems_ref")}
    surviving_old_owners = {
        item_id for item_id, item in current.items() if item_id not in relinked
        and item_id in previous and item.get("systems_ref") == previous[item_id].get("systems_ref")
        and json.dumps(item.get("systems_ref"), sort_keys=True) in old_refs
    }
    surviving_sources = set()
    for spell in list(candidate.get("spells") or []):
        if not isinstance(spell, dict):
            continue
        source_id = str(spell.get("spell_source_row_id") or "").strip()
        item_spell = (spell.get("spell_grant_origin") == "item_effect"
                      or spell.get("spell_source_row_kind") == "item")
        owners = spell.get("item_owner_ids")
        spell_id = str(spell.get("id") or "").strip()
        if spell_id in legacy_spell_ids or (spell_id in retired_spell_ids
                                            and source_id not in old_source_ids):
            raise CharacterStateConflictError("Retired item spell identity needs manager repair before relink.")
        if source_id not in old_source_ids:
            continue
        if not item_spell:
            raise CharacterStateConflictError("Retired item spell source is ambiguous.")
        if isinstance(owners, list) and relinked.intersection(owners):
            raise CharacterStateConflictError("Retired item spell ownership needs manager repair.")
        if item_spell and (not isinstance(owners, list) or not owners
                           or any(owner not in surviving_old_owners for owner in owners)):
            raise CharacterStateConflictError("Item spell ownership needs manager repair before relink.")
        if item_spell and source_id and source_id in old_source_ids:
            surviving_sources.add(source_id)
    for row in list(candidate.get("source_rows") or []):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_row_id") or "").strip()
        if (row.get("source_row_kind") == "item" and source_id
                and source_id in old_source_ids and source_id not in surviving_sources):
            raise CharacterStateConflictError("Retired item spell source needs manager repair.")


def _exact_item_transition_baseline(prior_definition, definition,
                                    prior_authority, candidate_authority, prior_state, *,
                                     reconstruction=None, prior_record=None, actor_id=None,
                                     prior_authority_provider=None,
                                     same_physical_mapping=None, source_read_owner=None, source_read_phase=None):
    """Bind retired physical owners and their exact approved source bytes.

    Aggregate values are handled separately. Their saved totals are never an
    input to this source proof or an inverse of a retired item effect.
    """
    from flask import current_app
    from .character_source_authority import VERIFIED, _current_payload, _source_identity
    from .item_spell_support import parse_item_spell_support
    from .system_policy import is_dnd_5e_system

    if not is_dnd_5e_system(definition.system):
        return ((), (), (), ())
    old_items = [item for item in prior_definition.equipment_catalog
                 if isinstance(item, dict) and not item.get("is_currency_only")]
    new_items = [item for item in definition.equipment_catalog
                 if isinstance(item, dict) and not item.get("is_currency_only")]
    old_ids = [str(item.get("id") or "").strip() for item in old_items]
    new_ids = [str(item.get("id") or "").strip() for item in new_items]
    if (not all(old_ids + new_ids) or len(old_ids) != len(set(old_ids))
            or len(new_ids) != len(set(new_ids))):
        raise CharacterStateConflictError("Item identity needs manager repair before publication.")
    new_by_id = dict(zip(new_ids, new_items))
    # Additive authentication of the exact same physical owner retires no
    # prior source grant. Other relinks retain the full aggregate/charge path.
    # Its new mechanics still require freshly constructed current authority.
    authenticated = _authenticated_reconstruction_item_ids(
        prior_definition, definition, candidate_authority, prior_state,
        reconstruction=reconstruction, prior_record=prior_record, actor_id=actor_id,
        same_physical_mapping=same_physical_mapping, source_read_owner=source_read_owner,
    )
    retired = [(item_id, item) for item_id, item in zip(old_ids, old_items)
               if item_id not in authenticated and (item_id not in new_by_id
               or item.get("systems_ref") != new_by_id[item_id].get("systems_ref")
               or item.get("page_ref") != new_by_id[item_id].get("page_ref"))]
    if not retired:
        return ((), (), (), ())
    if prior_authority is None and prior_authority_provider is not None:
        prior_authority = prior_authority_provider()
    systems_service = (source_read_phase.systems_view() if source_read_phase is not None
                       else current_app.extensions.get("systems_service"))
    if systems_service is None or prior_authority is None or candidate_authority is None:
        raise CharacterStateConflictError("Item source needs manager repair before publication.")
    from .campaign_item_mechanics import (
        CAMPAIGN_ITEM_METADATA_KEYS, campaign_item_character_metadata,
        campaign_item_mechanics_is_approved, is_campaign_item_mechanics_metadata,
    )
    safe_metadata = set(CAMPAIGN_ITEM_METADATA_KEYS) | {"campaign_item_mechanics_review_status", "rarity",
                     "spell_support", "attunement", "requires_attunement",
                     "weight", "value", "source", "source_id", "description",
                     "body_format", "body_markdown", "campaign_item",
                     "campaign_item_mechanics", "campaign_item_mechanics_field_provenance",
                     "campaign_item_mechanics_flags", "campaign_item_mechanics_support_state",
                     "campaign_item_mechanics_version", "custom_campaign_slug",
                     "provenance", "search_metadata", "updated_by_user_id", "armor",
                     "page_ref", "linked_published_page_ref"}
    structured_metadata = {"spell_support", "spellcasting_modifiers", "spell_property_modifiers",
                           "ability_score_minimums", "resource_template_bonuses",
                           "defensive_rules", "attack_reminder_rules", "item_use_actions",
                           "item_uses", "armor_profile", "weapon_profile", "charges",
                           "properties", "weapon_extra_damage", "page_ref", "linked_published_page_ref", "campaign_item_mechanics",
                           "campaign_item_mechanics_field_provenance",
                           "campaign_item_mechanics_flags", "search_metadata"}
    safe_item = {"id", "name", "default_quantity", "weight", "notes",
                 "source_kind", "systems_ref", "page_ref", "campaign_option",
                 "is_equipped", "is_attuned", "weapon_wield_mode",
                 "currency", "is_currency_only", "equipped_state_explicit",
                 "charges_current", "charges_max", "tags"}
    identities = []
    affected_ac = set()
    affected_abilities = set()
    affected_resources = set()
    from .character_equipment_activation import analyze_activation
    activation = analyze_activation(prior_definition, prior_state)
    physical_rows = {row["id"]: row["state"] for row in activation["rows"]
                     if row["source"] == "sqlite" and row["status"] == "exact"}

    def note_effects(item_id, metadata, authority):
        if item_id not in authority.active_item_ids:
            return
        if any(metadata.get(key) not in (None, "", 0, False, [], {}) for key in
               ("bonus_ac", "ac", "armor_profile", "defensive_rules")):
            affected_ac.add("stats.armor_class")
        minimums = metadata.get("ability_score_minimums") or {}
        if not isinstance(minimums, dict):
            raise CharacterStateConflictError("Item ability minimum needs manager repair.")
        for key in minimums:
            if key not in {"str", "dex", "con", "int", "wis", "cha"}:
                raise CharacterStateConflictError("Item ability minimum needs manager repair.")
            affected_abilities.add(key)
        bonuses = metadata.get("resource_template_bonuses") or []
        if not isinstance(bonuses, list):
            raise CharacterStateConflictError("Item resource bonus needs manager repair.")
        for bonus in bonuses:
            if not isinstance(bonus, dict) or not str(bonus.get("id") or "").strip():
                raise CharacterStateConflictError("Item resource bonus needs manager repair.")
            affected_resources.add(str(bonus["id"]).strip())
    for item_id, item in retired:
        source_kind, source_key = _source_identity(item)
        prior_identity_digest = None
        if (set(item) - safe_item
                or (source_kind != "page" and item.get("campaign_option") not in (None, {}, []))):
            raise CharacterStateConflictError(
                "Item owner or aggregate baseline needs manager repair before publication."
            )
        if source_kind.startswith("systems"):
            if not source_key or prior_authority.status_for("item", item_id) != VERIFIED:
                raise CharacterStateConflictError("Item exact source needs manager repair.")
            metadata, reason = _current_payload(
                campaign_slug=definition.campaign_slug, kind="item",
                source_kind=source_kind, source_key=source_key,
                systems_service=systems_service, pages={},
                expected_slug=str(dict(item.get("systems_ref") or {}).get("slug") or ""),
                expected_ref=dict(item.get("systems_ref") or {}),
            )
        else:
            physical = physical_rows.get(item_id)
            if (activation["blocked"] or physical is None
                    or physical.get("is_equipped") is not False
                    or physical.get("is_attuned") is not False
                    or physical.get("weapon_wield_mode")):
                raise CharacterStateConflictError("Unqualified active item needs manager repair.")
            # An inactive reference has no automatic aggregate contribution.
            # A linked page still needs its exact current published identity;
            # a manual row is identified only by its unique physical instance.
            proof = None
            if source_kind == "page":
                link = _exact_page_link(item["page_ref"], f"retired.{item_id}.page_ref", "item_reference")
                proof = _create_source_proof(definition.campaign_slug, (link,), (), connection=get_db())
                if item.get("campaign_option") not in (None, {}, []):
                    from .character_campaign_options import build_campaign_page_character_option
                    page_store = (source_read_phase.page_store() if source_read_phase is not None
                                  else current_app.extensions.get("campaign_page_store"))
                    record = page_store.get_page_record(definition.campaign_slug, source_key) if page_store else None
                    option = build_campaign_page_character_option(record, default_kind="item") if record else None
                    if option is None or item["campaign_option"] != option:
                        raise CharacterStateConflictError("Item page option needs manager repair.")
            elif source_kind or item.get("systems_ref"):
                raise CharacterStateConflictError("Item reference identity needs manager repair.")
            prior_identity_digest = hashlib.sha256(json.dumps({"item": item, "physical": physical,
                    "page_proof": repr(proof)}, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
            metadata, reason = {}, ""
        if reason or metadata is None or set(metadata) - safe_metadata:
            raise CharacterStateConflictError(
                "Item aggregate effects or exact source need manager repair before publication."
            )
        for field in safe_metadata - structured_metadata - {"campaign_item_mechanics_review_status"}:
            if field in metadata and not isinstance(metadata[field], (str, int, float, bool, type(None))):
                raise CharacterStateConflictError("Item source metadata needs manager repair.")
        if (is_campaign_item_mechanics_metadata(metadata)
                and not campaign_item_mechanics_is_approved(metadata)):
            raise CharacterStateConflictError("Item aggregate effects need approved source review.")
        effects = (campaign_item_character_metadata(metadata)
                   if is_campaign_item_mechanics_metadata(metadata) else metadata)
        parsed = parse_item_spell_support(effects.get("spell_support"))
        if parsed.diagnostics or any(record.invalid for record in parsed.records):
            raise CharacterStateConflictError("Item spell source needs manager repair before publication.")
        ability_keys = {record.source_ability_key for record in parsed.records
                        if record.source_ability_key}
        if ability_keys and (not prior_authority.field_status("stats.proficiency_bonus").is_effective
                             or not candidate_authority.field_status("stats.proficiency_bonus").is_effective
                             or any(not prior_authority.field_status(
                                 f"stats.ability_scores.{key}.score").is_effective
                                 or not candidate_authority.field_status(
                                     f"stats.ability_scores.{key}.score").is_effective
                                 for key in ability_keys)):
            raise CharacterStateConflictError(
                "Independent spell formula inputs need manager repair before item transition."
            )
        identities.append((item_id, source_kind or "manual", source_key,
                           prior_identity_digest or hashlib.sha256(json.dumps(metadata, sort_keys=True,
                               separators=(",", ":"), default=str).encode()).hexdigest()))
        note_effects(item_id, effects, prior_authority)
        replacement = new_by_id.get(item_id)
        if replacement is not None:
            new_kind, new_key = _source_identity(replacement)
            if (not new_kind.startswith("systems") or not new_key
                    or candidate_authority.status_for("item", item_id) != VERIFIED
                    or set(replacement) - safe_item
                    or replacement.get("campaign_option") not in (None, {}, [])):
                raise CharacterStateConflictError(
                    "Replacement item owner or aggregate baseline needs manager repair."
                )
            new_metadata, reason = _current_payload(
                campaign_slug=definition.campaign_slug, kind="item",
                source_kind=new_kind, source_key=new_key,
                systems_service=systems_service, pages={},
                expected_slug=str(dict(replacement.get("systems_ref") or {}).get("slug") or ""),
                expected_ref=dict(replacement.get("systems_ref") or {}),
            )
            if reason or new_metadata is None or set(new_metadata) - safe_metadata:
                raise CharacterStateConflictError(
                    "Replacement aggregate effects or exact source need manager repair."
                )
            for field in safe_metadata - structured_metadata - {"campaign_item_mechanics_review_status"}:
                if field in new_metadata and not isinstance(new_metadata[field],
                                                            (str, int, float, bool, type(None))):
                    raise CharacterStateConflictError("Replacement source metadata needs manager repair.")
            if (is_campaign_item_mechanics_metadata(new_metadata)
                    and not campaign_item_mechanics_is_approved(new_metadata)):
                raise CharacterStateConflictError("Replacement aggregate effects need approved source review.")
            new_effects = (campaign_item_character_metadata(new_metadata)
                           if is_campaign_item_mechanics_metadata(new_metadata)
                           else new_metadata)
            new_parsed = parse_item_spell_support(new_effects.get("spell_support"))
            if new_parsed.diagnostics or any(record.invalid for record in new_parsed.records):
                raise CharacterStateConflictError("Replacement spell source needs manager repair.")
            new_abilities = {record.source_ability_key for record in new_parsed.records
                             if record.source_ability_key}
            if new_abilities and (not candidate_authority.field_status(
                    "stats.proficiency_bonus").is_effective
                    or any(not candidate_authority.field_status(
                        f"stats.ability_scores.{key}.score").is_effective
                        for key in new_abilities)):
                raise CharacterStateConflictError(
                    "Replacement spell formula inputs need manager repair."
                )
            identities.append((item_id, new_kind, new_key,
                               hashlib.sha256(json.dumps(new_metadata, sort_keys=True,
                                   separators=(",", ":"), default=str).encode()).hexdigest()))
            note_effects(item_id, new_effects, candidate_authority)
    return (tuple(identities), tuple(sorted(affected_ac)),
            tuple(sorted(affected_abilities)), tuple(sorted(affected_resources)))


def _withhold_item_transition_aggregates(prior_definition, definition, state,
                                         prior_authority, candidate_authority,
                                         item_baseline, *, source_read_phase=None):
    """Replace only affected current metrics with a proved value or null.

    The prior aggregate is never used to calculate a new number. This runs
    before serialization and source-authority renewal, so raw API and package
    bytes have the same withheld values as the projected sheet.
    """
    from copy import deepcopy
    from flask import current_app
    from .character_ability_inputs import input_records
    from .character_builder import (
        _effective_item_catalog_for_definition, normalize_definition_to_native_model,
    )
    from .character_builder_derivation import (
        _character_profile_class_names, _character_profile_subclass_names,
        _derive_armor_class_from_character_inputs,
    )
    from .character_source_authority import NEEDS_REPAIR, VERIFIED

    identities, ac_paths, ability_keys, resource_ids = item_baseline
    payload = deepcopy(definition.to_dict())
    next_state = deepcopy(state)
    source = dict(payload.get("source") or {})
    source.pop("item_transition_withheld_resources", None)
    source.pop("item_transition_cleared_charges", None)
    from collections import Counter
    relinked_ids = {item_id for item_id, count in
                    Counter(identity[0] for identity in identities).items() if count == 2}
    for item_id in relinked_ids:
        prior_rows = [row for row in prior_definition.equipment_catalog
                      if isinstance(row, dict) and row.get("id") == item_id]
        current_rows = [row for row in payload.get("equipment_catalog") or []
                        if isinstance(row, dict) and row.get("id") == item_id]
        state_rows = [row for row in next_state.get("inventory") or []
                      if isinstance(row, dict)
                      and str(row.get("catalog_ref") or row.get("id") or "").strip() == item_id]
        if len(prior_rows) != 1 or len(current_rows) != 1 or len(state_rows) != 1:
            raise CharacterStateConflictError("Relinked item identity needs manager repair.")
        current_rows[0].update(is_attuned=False, charges_current=None, charges_max=None)
        state_rows[0].update(is_attuned=False, charges_current=None, charges_max=None)
    if relinked_ids:
        from .character_service import _normalize_attunement_state
        next_state["attunement"] = _normalize_attunement_state(
            next_state.get("attunement"), next_state.get("inventory") or [],
        )
        source["item_transition_cleared_charges"] = sorted(relinked_ids)
    if not (ac_paths or ability_keys or resource_ids):
        payload["source"] = source
        return type(definition).from_dict(payload), next_state

    stats = dict(payload.get("stats") or {})
    abilities = dict(stats.get("ability_scores") or {})
    inputs = input_records(dict(prior_definition.stats or {}))
    provable_abilities = {
        key for key in ability_keys
        if inputs.get(key, {}).get("stage") == "base"
        and prior_authority.field_status(
            f"stats.ability_scores.{key}.score"
        ).reason == "baseline_authorized"
        and prior_authority.field_status(
            f"stats.ability_scores.{key}.score"
        ).is_effective
    }
    # The native formula pass consumes the separately witnessed base input.
    # It is never allowed to recover a base from the saved final score.
    projected = None
    if provable_abilities or ac_paths:
        try:
            projected = normalize_definition_to_native_model(
                definition, mode="authoring", source_authority=candidate_authority,
                systems_service=(source_read_phase.systems_view() if source_read_phase is not None
                                 else current_app.extensions.get("systems_service")),
            )
        except (ValueError, TypeError, KeyError):
            projected = None
    projected_stats = dict(projected.stats or {}) if projected is not None else {}
    projected_abilities = dict(projected_stats.get("ability_scores") or {})
    ability_labels = {"str": "strength", "dex": "dexterity", "con": "constitution",
                      "int": "intelligence", "wis": "wisdom", "cha": "charisma"}
    for key in ability_keys:
        row = dict(abilities.get(key) or {})
        resolved = dict(projected_abilities.get(key) or {})
        if key in provable_abilities and type(resolved.get("score")) is int:
            for field in ("score", "modifier", "save_bonus"):
                row[field] = resolved.get(field)
        else:
            for field in ("score", "modifier", "save_bonus"):
                row[field] = None
            input_payload = dict(stats.get("ability_inputs") or {})
            score_inputs = dict(input_payload.get("scores") or {})
            score_inputs[key] = {"stage": "unresolved", "provenance": "item_transition_needs_repair"}
            input_payload["scores"] = score_inputs
            stats["ability_inputs"] = input_payload
        row["authority_status"] = NEEDS_REPAIR if row.get("score") is None else row.get("authority_status")
        abilities[key] = row
        if ability_labels[key] in abilities:
            abilities[ability_labels[key]] = deepcopy(row)
    stats["ability_scores"] = abilities
    dependent_stats = {
        "str": ("carrying_capacity", "push_drag_lift"),
        "dex": ("initiative_bonus",),
        "int": ("passive_investigation",),
        "wis": ("passive_perception", "passive_insight"),
        "con": ("max_hp",),
    }
    for key in ability_keys:
        for field in dependent_stats.get(key, ()):
            candidate = projected_stats.get(field)
            stats[field] = (candidate if key in provable_abilities
                            and type(candidate) is int else None)
    spellcasting = dict(payload.get("spellcasting") or {})
    projected_spellcasting = dict(projected.spellcasting or {}) if projected else {}
    spell_ability_keys = {
        label: key for key, label in ability_labels.items()
    }
    spell_ability_keys.update({key: key for key in ability_labels})
    def spell_ability(row):
        raw = str(row.get("ability_key") or row.get("spellcasting_ability") or "").strip().casefold()
        return spell_ability_keys.get(raw)
    pb_proved = candidate_authority.field_status("stats.proficiency_bonus").is_effective
    affected_spell_row = False
    for row_key, id_key in (("class_rows", "class_row_id"),
                            ("source_rows", "source_row_id")):
        computed_rows = {str(row.get(id_key) or "").strip(): row
                         for row in projected_spellcasting.get(row_key) or []
                         if isinstance(row, dict) and str(row.get(id_key) or "").strip()}
        for row in spellcasting.get(row_key) or []:
            if not isinstance(row, dict):
                continue
            key = spell_ability(row)
            if key not in ability_keys:
                continue
            affected_spell_row = True
            row_id = str(row.get(id_key) or "").strip()
            computed = computed_rows.get(row_id, {})
            verified_rows = (candidate_authority.verified_class_rows
                             if row_key == "class_rows" else
                             candidate_authority.verified_source_rows)
            provenance = row.get("spell_metric_provenance")
            formula = provenance if isinstance(provenance, dict) else {}
            for metric in ("spell_save_dc", "spell_attack_bonus"):
                value = computed.get(metric)
                row[metric] = (value if pb_proved and key in provable_abilities
                               and row_id in verified_rows
                               and spell_ability(computed) == key
                               and isinstance(formula.get(metric), dict)
                               and formula[metric].get("kind") == "formula"
                               and type(value) is int else None)
            if any(row.get(metric) is None for metric in
                   ("spell_save_dc", "spell_attack_bonus")):
                row["authority_status"] = NEEDS_REPAIR
    top_ability = spell_ability(spellcasting)
    if not top_ability and len(spellcasting.get("class_rows") or []) == 1:
        top_ability = spell_ability(spellcasting["class_rows"][0])
    if top_ability in ability_keys or (not top_ability and affected_spell_row):
        computed = projected_spellcasting
        provenance = spellcasting.get("spell_metric_provenance")
        formula = provenance if isinstance(provenance, dict) else {}
        for metric in ("spell_save_dc", "spell_attack_bonus"):
            value = computed.get(metric)
            spellcasting[metric] = (
                value if pb_proved and top_ability in provable_abilities
                and spell_ability(computed) == top_ability
                and isinstance(formula.get(metric), dict)
                and formula[metric].get("kind") == "formula"
                and type(value) is int else None
            )
        if any(spellcasting.get(metric) is None for metric in
               ("spell_save_dc", "spell_attack_bonus")):
            spellcasting["authority_status"] = NEEDS_REPAIR
    payload["spellcasting"] = spellcasting
    skill_abilities = {
        "athletics": "str", "acrobatics": "dex", "sleight of hand": "dex",
        "stealth": "dex", "arcana": "int", "history": "int",
        "investigation": "int", "nature": "int", "religion": "int",
        "animal handling": "wis", "insight": "wis", "medicine": "wis",
        "perception": "wis", "survival": "wis", "deception": "cha",
        "intimidation": "cha", "performance": "cha", "persuasion": "cha",
    }
    projected_skills = {str(row.get("name") or "").strip().casefold(): row
                        for row in list(projected.skills or []) if isinstance(row, dict)} if projected else {}
    for row in payload.get("skills") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip().casefold()
        key = skill_abilities.get(name)
        if key not in ability_keys:
            continue
        computed = projected_skills.get(name, {}).get("bonus")
        row["bonus"] = (computed if key in provable_abilities and type(computed) is int
                        and candidate_authority.field_status(f"skills.{name}").is_effective
                        else None)
        if row["bonus"] is None:
            row["authority_status"] = NEEDS_REPAIR
    projected_attacks = {str(row.get("id") or "").strip(): row
                         for row in list(projected.attacks or []) if isinstance(row, dict)} if projected else {}
    for attack in payload.get("attacks") or []:
        if not isinstance(attack, dict):
            continue
        dependencies = attack.get("authority_ability_dependencies")
        affected = bool(isinstance(dependencies, list)
                        and set(dependencies).intersection(ability_keys))
        if not affected and not dependencies and {"str", "dex"}.intersection(ability_keys):
            affected = True
        if not affected:
            continue
        computed = projected_attacks.get(str(attack.get("id") or "").strip(), {})
        proven = (projected is not None
                  and all(key in provable_abilities for key in set(dependencies or [])
                          .intersection(ability_keys))
                  and candidate_authority.attack_inputs_effective(computed, definition))
        for field in ("attack_bonus", "attack_roll_bonus", "to_hit_bonus",
                      "damage_bonus", "save_dc", "damage_formula", "damage"):
            if field in attack:
                attack[field] = deepcopy(computed.get(field)) if proven else None
        if not proven:
            attack["authority_status"] = NEEDS_REPAIR
            attack["mechanics_suppressed"] = True
    if ac_paths or {"dex", "con", "wis"}.intersection(ability_keys):
        dependent_keys = {"dex", "con", "wis"}
        safe_inputs = all(
            (key not in ability_keys or key in provable_abilities)
            and candidate_authority.field_status(
                f"stats.ability_scores.{key}.score"
            ).is_effective
            for key in dependent_keys
        )
        exact_remaining = all(
            candidate_authority.status_for("item", str(item.get("id") or "")) == VERIFIED
            for item in definition.equipment_catalog
            if isinstance(item, dict) and item.get("is_equipped")
        )
        derived_ac = None
        if (safe_inputs and exact_remaining and projected is not None
                and candidate_authority.verified_class_rows
                and all(candidate_authority.status_for("feature", str(row.get("id") or ""))
                        == VERIFIED for row in definition.features if isinstance(row, dict))):
            effective = candidate_authority.effective_definition(definition)
            scores = {key: dict(projected_abilities.get(key) or {}).get("score")
                      for key in ("str", "dex", "con", "int", "wis", "cha")}
            if all(type(score) is int for score in scores.values()):
                catalog = _effective_item_catalog_for_definition(
                    effective, systems_service=(source_read_phase.systems_view() if source_read_phase is not None
                                               else current_app.extensions.get("systems_service")),
                )
                derived_ac = _derive_armor_class_from_character_inputs(
                    ability_scores=scores,
                    equipment_catalog=list(effective.equipment_catalog or []),
                    features=list(effective.features or []),
                    class_names=_character_profile_class_names(effective),
                    subclass_names=_character_profile_subclass_names(effective),
                    item_catalog=catalog,
                    allow_plain_unarmored_base=(
                        str((effective.source or {}).get("source_type") or "")
                        == "native_character_builder"
                    ),
                )
        if derived_ac is not None:
            stats["armor_class"] = derived_ac
            stats["defensive_state"] = deepcopy(projected_stats.get("defensive_state"))
        else:
            stats["armor_class"] = None
            stats["defensive_state"] = None
    payload["stats"] = stats

    withheld = set(resource_ids)
    for template in payload.get("resource_templates") or []:
        if isinstance(template, dict) and str(template.get("id") or "").strip() in withheld:
            template["max"] = None
            template["initial_current"] = None
            template["authority_status"] = NEEDS_REPAIR
    for resource in next_state.get("resources") or []:
        if isinstance(resource, dict) and str(resource.get("id") or "").strip() in withheld:
            resource["current"] = None
            resource["max"] = None
            resource["authority_status"] = "Needs repair"
    if withheld:
        source["item_transition_withheld_resources"] = sorted(withheld)
    payload["source"] = source
    return type(definition).from_dict(payload), next_state


def _update_numeric_authority(coordinator, prior_record, definition, desired_state, *,
                              pending_numeric_authority=None, reviewed_source_proof=None,
                              prepublication=True, source_read_owner=None, source_read_phase=None):
    """Refresh reviewed pending inputs before ordinary numeric projection.

    Only callers before reservation may mark an anticipated domain refusal as
    certainly prepublication. Reserved paths preserve conservative ambiguity.
    """
    from .character_hp_recipe import HitPointRecipeError
    from .character_mechanics_projection import CharacterNumericProjectionError
    from .character_reconciliation import CharacterPublicationPreflightError
    try:
        if pending_numeric_authority is not None:
            authority = pending_numeric_authority.recheck(prior_record, definition, desired_state)
        elif (reviewed_source_proof is not None
                and reviewed_source_proof.refresh_numeric_authority is not None):
            # The callback is an in-memory issuance, independently rechecked
            # against actor, target generation, raw state and candidate bytes.
            authority = None
        else:
            phased_provider = getattr(coordinator, "source_read_numeric_authority_provider", None)
            phase_args = ({"source_read_phase": source_read_phase} if source_read_phase is not None else {})
            authority = (phased_provider(prior_record, definition, desired_state,
                                        source_read_owner=source_read_owner, **phase_args)
                if source_read_owner is not None and phased_provider is not None else
                coordinator.numeric_authority_provider(prior_record, definition, desired_state)
                if coordinator.numeric_authority_provider is not None else None)
        if reviewed_source_proof is not None:
            authority = reviewed_source_proof.prospective_authority(
                authority, definition, prior_record.state_record.state, source_read_owner=source_read_owner,
            )
        return authority
    except (HitPointRecipeError, CharacterNumericProjectionError) as exc:
        if not prepublication:
            raise
        raise CharacterPublicationPreflightError(
            "Character mechanics need manager review before publication."
        ) from exc


def _prior_numeric_authority_loader(coordinator, prior_record, *, prepublication=True,
                                    source_read_owner=None, source_read_phase=None):
    """Resolve the real prior view only for a consumer that needs it.

    Each publication phase owns a separate loader. Candidate proof never
    authenticates this view, and the reserved phase cannot reuse preflight data.
    """
    resolved = False
    authority = None

    def load():
        nonlocal resolved, authority
        if not resolved:
            authority = _update_numeric_authority(
                coordinator, prior_record, prior_record.definition,
                prior_record.state_record.state, prepublication=prepublication, source_read_owner=source_read_owner,
                source_read_phase=source_read_phase,
            )
            resolved = True
        return authority

    return load


def prepare_native_requalification_audit(coordinator, prior_record, definition, desired_state,
                                         metadata, actor_id, *, connection=None):
    """Size the complete final audit using actual current publication inputs.

    Revision derivation is the same increment used by _append and the state
    writer below. Call again under reservation before either writer runs.
    This is a prospective size check, never evidence of a saved publication.
    """
    from .character_update_apply import canonical_digest
    db = connection if connection is not None else get_db()
    source = exact_character(definition.campaign_slug, definition.character_slug, connection=db)
    row = db.execute("SELECT revision,state_json FROM character_state WHERE campaign_slug=? AND character_slug=?",
        (definition.campaign_slug, definition.character_slug)).fetchone()
    if (source is None or source["revision"] != prior_record.committed_revision
            or canonical_digest(CharacterDefinition.from_dict(yaml.safe_load(source["primary_bytes"])).to_dict())
               != canonical_digest(prior_record.definition.to_dict())
            or row is None or row["revision"] != prior_record.state_record.revision
            or canonical_digest(json.loads(row["state_json"])) != canonical_digest(prior_record.state_record.state)
            or not isinstance(metadata, dict) or metadata.get("source") != "character_source_repair"
            or metadata.get("manager_action") != "native_requalify" or metadata.get("review_action") != "native_requalify"
            or type(metadata.get("numeric_actor_id")) is not int
            or metadata.get("numeric_actor_id") != actor_id or type(actor_id) is not int or actor_id < 1):
        raise CharacterStateConflictError("Native audit publication inputs changed before review or apply.")
    payload = dict(metadata)
    proof = payload.get("native_requalification")
    if (not isinstance(proof, dict) or proof.get("schema_version") not in {1, 2, 3, 4, 5, 6}
            or proof.get("prior_generation") != source["revision"]
            or proof.get("prior_definition_digest") != canonical_digest(prior_record.definition.to_dict())
            or proof.get("prior_state_revision") != row["revision"]
            or proof.get("prior_state_digest") != canonical_digest(prior_record.state_record.state)
            or payload.get("candidate_digest") != canonical_digest(definition.to_dict())
            or proof["schema_version"] in {3, 4, 5, 6}
                and canonical_digest(desired_state) != canonical_digest(prior_record.state_record.state)):
        raise CharacterStateConflictError("Native audit prior, candidate or exact state changed.")
    final = {"published_definition_digest": canonical_digest(definition.to_dict()),
             "published_revision": int(source["revision"]) + 1,
             "published_state_revision": (row["revision"] if proof["schema_version"] in {3, 4, 5, 6} else
                 row["revision"] + int(canonical_digest(desired_state) != canonical_digest(prior_record.state_record.state)))}
    if any(key in payload and payload[key] != value for key, value in final.items()):
        raise CharacterStateConflictError("Native audit publication revisions changed.")
    payload.update(final)
    prepared = coordinator._prepare_update_audit(
        operation_kind="character_update_apply", audit_event_type="character_update_applied",
        audit_actor_user_id=actor_id, audit_target_user_id=None, audit_metadata=payload)
    if (coordinator.auth_store.sanitize_audit_metadata(payload) != payload
            or json.dumps(payload, sort_keys=True) != prepared[3]):
        raise CharacterStateConflictError("Native audit evidence cannot be redacted or truncated.")
    return prepared


def _prepare_native_choice_audit(coordinator, prior_record, definition, state, authority, *,
                                actor_id, markers, decisions, callback, leveled):
    """Bound the complete future event without treating it as saved custody."""
    if callback is None:
        if decisions:
            raise CharacterStateConflictError("A class choice decision needs its complete audit preparation.")
        return None
    from .character_spell_grants import canonical_digest, grant_model_digest, CLASS_CHOICE_STATE_FIELD
    if not callable(callback) or authority is None or coordinator.auth_store is None:
        raise CharacterStateConflictError("Native choice audit preparation is unavailable.")
    payload = callback()
    expected_revision = prior_record.state_record.revision + int(state != prior_record.state_record.state)
    if (not isinstance(payload, dict) or payload.get("numeric_actor_id") != actor_id
            or type(actor_id) is not int or actor_id < 1
            or payload.get("source") != ("native_level_up_confirmed" if leveled else "native_spell_choice_confirmed")
            or payload.get("numeric_authorizations") != list(markers)
            or payload.get("definition_digest") != canonical_digest(definition.to_dict())
            or payload.get("prior_state_revision") != prior_record.state_record.revision
            or payload.get("state_revision") != expected_revision
            or payload.get("source_snapshot_digest") != authority.source_snapshot_digest
            or payload.get("source_basis_digests") != {
                marker["target_id"]: authority.numeric_basis_digest(marker["target_id"]) for marker in markers}):
        raise CharacterStateConflictError("Native choice audit inputs changed before publication.")
    if decisions or any(CLASS_CHOICE_STATE_FIELD in row for model in (prior_record.definition, definition)
                        for row in model.spellcasting.get("spells", []) if isinstance(row, dict)):
        expected = {"schema_version": 1,
            "event_type": "character_native_leveled" if leveled else "character_native_spell_selected",
            "actor_id": actor_id, "prior_generation": prior_record.committed_revision,
            "generation": prior_record.committed_revision + 1,
            "prior_definition_digest": canonical_digest(prior_record.definition.to_dict()),
            "definition_digest": canonical_digest(definition.to_dict()),
            "prior_state_revision": prior_record.state_record.revision, "state_revision": expected_revision,
            "prior_state_digest": canonical_digest(prior_record.state_record.state),
            "state_digest": canonical_digest(state),
            "prior_model_digest": grant_model_digest(prior_record.definition),
            "model_digest": grant_model_digest(definition), "decisions": list(decisions)}
        if payload.get("spell_choice_decisions") != expected:
            raise CharacterStateConflictError("Native choice decision audit changed before publication.")
    elif "spell_choice_decisions" in payload:
        raise CharacterStateConflictError("An unrelated choice decision cannot accompany this publication.")
    sanitized = coordinator.auth_store.sanitize_audit_metadata(payload)
    if sanitized != payload or len(json.dumps(payload, sort_keys=True, allow_nan=False).encode("utf-8")) > 65536:
        raise CharacterStateConflictError("Native choice confirmation exceeds the bounded audit contract.")
    return payload


_ACTIVATION_PREPARATION = object()


def preview_activation_repair(coordinator, prior_record, *, row_index, actor_id):
    """Prepare one real preserve operation; never reserve, publish or issue a permit."""
    from .character_equipment_activation import repair_activation_state
    from .system_policy import is_dnd_5e_system
    if (type(prior_record) is not CharacterRecord or type(actor_id) is not int or actor_id < 1
            or type(row_index) is not int or not is_dnd_5e_system(prior_record.definition.system)):
        raise CharacterStateConflictError("Activation preview needs the current Character and manager.")
    connection = get_db()
    if connection.in_transaction:
        raise CharacterStateConflictError("Activation preview cannot borrow an ambient transaction.")
    initial_changes = connection.total_changes
    desired_state = repair_activation_state(prior_record.definition, prior_record.state_record.state,
        row_index=row_index, choice="preserve")
    coordinator._validate_update_preconditions(
        prior_record, prior_record.definition, prior_record.import_metadata, desired_state,
        expected_revision=prior_record.state_record.revision, updated_by_user_id=actor_id,
        operation_kind="activation_repair", audit_event_type=None, audit_actor_user_id=None,
        pending_numeric_authority=None, reviewed_source_proof=None,
        trusted_spell_choice_authoring=False, reconcile_reimport_state=False,
        reimport_source_authority=None)
    result = publish_update(coordinator, prior_record, prior_record.definition,
        prior_record.import_metadata, desired_state, expected_revision=prior_record.state_record.revision,
        updated_by_user_id=actor_id, operation_kind="activation_repair",
        _activation_preparation=_ACTIVATION_PREPARATION)
    if connection.total_changes != initial_changes:
        raise CharacterStateConflictError("Activation preparation performed an unexpected database write.")
    return result


def _activation_preparation_result(prior_record, definition, import_metadata, desired_state,
        prepared, primary, secondary, authority, prospective_transitions, prospective_choice_audit,
        choice_decisions, choice_capacity, expected_config, expected_source, expected_assignment,
        new_pages, new_entries, clean_audit, prior_authority, *, connection, actor_id):
    """Capture real prepared bytes in an owned final read snapshot, before reservation."""
    from .character_equipment_activation import activation_frame_digest
    from .db import rollback_source_read_connection
    if connection.in_transaction:
        raise CharacterStateConflictError("Activation preview requires its own final read snapshot.")
    primary_failure = None
    try:
        connection.execute("BEGIN")
        campaign, slug = definition.campaign_slug, definition.character_slug
        _reject_journals(connection, campaign, slug)
        source = exact_character(campaign, slug, connection=connection)
        row = connection.execute(
            "SELECT revision,state_json FROM character_state WHERE campaign_slug=? AND character_slug=?",
            (campaign, slug)).fetchone()
        current_config, _ = config(campaign, connection=connection)
        assignment = connection.execute(
            "SELECT id,user_id FROM character_assignments WHERE campaign_slug=? AND character_slug=?",
            (campaign, slug)).fetchone()
        if (source is None or source["revision"] != prior_record.committed_revision
                or row is None or row["revision"] != prior_record.state_record.revision
                or activation_frame_digest(json.loads(row["state_json"]))
                   != activation_frame_digest(prior_record.state_record.state)
                or CharacterDefinition.from_dict(yaml.safe_load(source["primary_bytes"])).to_dict()
                   != prior_record.definition.to_dict()
                or CharacterImportMetadata.from_dict(yaml.safe_load(source["secondary_bytes"])).to_dict()
                   != prior_record.import_metadata.to_dict()
                or current_config != expected_config
                or (tuple(assignment) if assignment is not None else None) != expected_assignment
                or _create_source_proof(campaign, new_pages, new_entries, connection=connection) != expected_source):
            raise CharacterStateConflictError("Activation preparation changed before its final capture.")
        if _prepare_transition_renewals(prior_record, definition, prepared.validated_state,
                authority, prior_authority, connection, actor_id=actor_id,
                spell_choice_decisions=choice_decisions) != prospective_transitions:
            raise CharacterStateConflictError("Activation renewal basis changed before its final capture.")
        audit_rows = connection.execute(
            "SELECT id,actor_user_id,event_type,metadata_json FROM auth_audit_log "
            "WHERE campaign_slug=? AND character_slug=? ORDER BY id", (campaign, slug)).fetchall()
        audit_prefix = _sha(json.dumps([tuple(row) for row in audit_rows], sort_keys=True,
            default=str, separators=(",", ":")).encode())
        def limit(status):
            return {"path": status.path, "status": status.status, "raw": status.raw,
                    "effective": status.effective, "reason": status.reason}
        result = {
            "schema_version": 1, "preparation_only": True, "committed": False,
            "campaign_slug": campaign, "character_slug": slug,
            "generation": source["revision"], "state_revision": row["revision"],
            "definition_before": prior_record.definition.to_dict(), "definition_after": definition.to_dict(),
            "import_before": prior_record.import_metadata.to_dict(), "import_after": import_metadata.to_dict(),
            "state_before": json.loads(row["state_json"]), "state_requested": desired_state,
            "state_prepared": prepared.validated_state,
            "state_json_before": row["state_json"], "state_json_prepared": prepared.state_json,
            "primary_before_utf8": source["primary_bytes"].decode("utf-8"),
            "primary_prepared_utf8": primary.decode("utf-8"),
            "secondary_before_utf8": source["secondary_bytes"].decode("utf-8"),
            "secondary_prepared_utf8": secondary.decode("utf-8"),
            "primary_before_sha256": source["primary_sha256"], "primary_prepared_sha256": _sha(primary),
            "secondary_before_sha256": source["secondary_sha256"], "secondary_prepared_sha256": _sha(secondary),
            "authority_identity": authority.identity if authority is not None else None,
            "source_snapshot_digest": authority.source_snapshot_digest if authority is not None else None,
            "hp_limit": limit(authority.field_status("stats.max_hp")) if authority is not None else None,
            "resource_limits": [limit(status) for status in authority.resource_statuses] if authority is not None else [],
            "renewal_templates": list(prospective_transitions),
            "renewal_finalization": "New committed identity, audit chain digests, inserted IDs and timestamps are assigned only by a later real commit.",
            "choice_audit": prospective_choice_audit, "choice_decisions": list(choice_decisions),
            "choice_capacity": choice_capacity, "main_audit": list(clean_audit),
            "audit_prefix_count": len(audit_rows), "audit_prefix_sha256": audit_prefix,
            "source_proof": asdict(expected_source), "config_revision": expected_config["revision"],
            "assignment": list(expected_assignment) if expected_assignment is not None else None,
        }
        # Refuse oversize evidence rather than return an incomplete preview.
        if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 8 * MAX_PAIR_BYTES:
            raise CharacterStateConflictError("The complete activation preparation exceeds its preview bound.")
        return result
    except BaseException as exc:
        primary_failure = exc
        raise
    finally:
        try:
            rollback_source_read_connection(connection)
        except BaseException as cleanup:
            if primary_failure is not None:
                raise cleanup from BaseExceptionGroup("Activation preview primary and rollback failures", [primary_failure])
            raise

def _ordinary_item_source_reads(operation_kind, metadata, proof):
    """Select bounded source reads, never authorize a manager action."""
    from .character_reconciliation import PendingReviewedSourceProof
    return (operation_kind == "character_update_apply"
            and type(proof) is PendingReviewedSourceProof
            and proof.native_result is None and proof.same_physical_mapping is None
            and proof.native_reconstruction is None and proof.native_elective_decision is None
            and proof.refresh_numeric_authority is None and callable(proof.refresh_review_basis)
            and isinstance(metadata, dict)
            and metadata.get("source") == "character_source_repair"
            and metadata.get("manager_action") == "source_relink"
            and metadata.get("review_action") == "relink"
            and metadata.get("review_family") == "item")


def _native_source_publication_scope(function):
    from functools import wraps

    @wraps(function)
    def wrapped(coordinator, prior_record, definition, *args, **kwargs):
        if "source_read_owner" in kwargs:
            raise TypeError("Publication constructs its own source-read owners.")
        proof = kwargs.get("reviewed_source_proof")
        preparation = kwargs.get("_activation_preparation")
        if preparation is not None and (preparation is not _ACTIVATION_PREPARATION
                or proof is not None or kwargs.get("pending_numeric_authority") is not None):
            raise CharacterStateConflictError("Activation preparation cannot carry pending publication authority.")
        ordinary_item_reads = _ordinary_item_source_reads(
            kwargs.get("operation_kind"), kwargs.get("audit_metadata"), proof)
        if preparation is None and not ordinary_item_reads and (proof is None or (
                getattr(proof, "native_result", None) is None
                and getattr(proof, "same_physical_mapping", None) is None
                and getattr(proof, "feature_class_association", None) is None
                and getattr(proof, "managed_resource_restoration", None) is None)):
            return function(coordinator, prior_record, definition, *args, **kwargs)
        from .character_source_reads import SourceReadOwner
        owner = SourceReadOwner.owned(get_db(), definition.campaign_slug, definition.character_slug)
        try:
            return function(coordinator, prior_record, definition, *args, source_read_owner=owner, **kwargs)
        finally:
            owner.close()
    return wrapped


@_native_source_publication_scope
def publish_update(coordinator, prior_record, definition, import_metadata, desired_state, *,
                   expected_revision, updated_by_user_id=None, operation_kind,
                   desired_asset_ref="", desired_asset_bytes=b"", audit_event_type=None,
                   audit_actor_user_id=None, audit_target_user_id=None, audit_metadata=None,
                   pending_numeric_authority=None, reviewed_source_proof=None,
                   trusted_spell_choice_authoring=False,
                   native_choice_audit=None,
                   explicit_removed_item_id=None,
                   reconcile_reimport_state=False, reimport_source_authority=None, source_read_owner=None,
                   _activation_preparation=None):
    if _activation_preparation is not None and (
            _activation_preparation is not _ACTIVATION_PREPARATION
            or operation_kind != "activation_repair" or type(prior_record) is not CharacterRecord
            or definition is not prior_record.definition or import_metadata is not prior_record.import_metadata
            or type(updated_by_user_id) is not int or updated_by_user_id < 1
            or type(expected_revision) is not int or expected_revision != prior_record.state_record.revision
            or any(value is not None for value in (audit_event_type, audit_actor_user_id,
                audit_target_user_id, audit_metadata, pending_numeric_authority, reviewed_source_proof,
                native_choice_audit, reimport_source_authority))
            or desired_asset_ref or desired_asset_bytes or explicit_removed_item_id
            or trusted_spell_choice_authoring is not False or reconcile_reimport_state is not False
            or source_read_owner is None):
        raise CharacterStateConflictError("Only fixed current activation preservation can be prepared.")
    coordinator._validate_update_input(prior_record, definition, import_metadata,
                                       expected_revision=expected_revision,
                                       operation_kind=operation_kind)
    if reviewed_source_proof is not None:
        reviewed_source_proof.require_complete()
    reconstruction = (reviewed_source_proof.native_reconstruction
                      if reviewed_source_proof is not None else None)
    elective = (reviewed_source_proof.native_elective_decision
                if reviewed_source_proof is not None else None)
    from .character_feature_proficiency_grants import validate_native_transition
    validate_native_transition(prior_record, definition, pending_numeric_authority)
    from .character_skill_adoptions import validate_transition as validate_skill_adoption_transition
    from .character_infusion_recipes import validate_transition as validate_recipe_transition
    from .character_feature_history import validate_transition as validate_history_transition
    validate_history_transition(prior_record, definition, reconstruction,
        actor_id=updated_by_user_id, state=desired_state)
    validate_recipe_transition(prior_record, definition, reconstruction,
        actor_id=updated_by_user_id, state=desired_state)
    validate_skill_adoption_transition(prior_record, definition, reconstruction,
        actor_id=updated_by_user_id, state=desired_state)
    from .character_feature_proficiency_grants import validate_automatic_transition, validate_condition_transition
    validate_automatic_transition(prior_record, definition, reconstruction,
        actor_id=updated_by_user_id, state=desired_state)
    validate_condition_transition(prior_record, definition, reconstruction,
        actor_id=updated_by_user_id, state=desired_state)
    from .character_tracker_associations import validate_transition as validate_tracker_transition
    validate_tracker_transition(prior_record, definition, reconstruction,
        actor_id=updated_by_user_id, state=desired_state)
    same_physical_mapping = (reviewed_source_proof.same_physical_mapping
                            if reviewed_source_proof is not None else None)
    association = (reviewed_source_proof.feature_class_association
                   if reviewed_source_proof is not None else None)
    restoration = (reviewed_source_proof.managed_resource_restoration
                   if reviewed_source_proof is not None else None)
    if restoration is not None:
        from .character_managed_resource_restoration import PendingManagedResourceRestoration, prepare_restoration_state
        if (type(restoration) is not PendingManagedResourceRestoration
                or operation_kind != "character_update_apply" or pending_numeric_authority is not None
                or reconstruction is not None or elective is not None or association is not None
                or same_physical_mapping is not None or trusted_spell_choice_authoring or reconcile_reimport_state
                or audit_event_type != "character_update_applied" or audit_actor_user_id != updated_by_user_id):
            raise CharacterStateConflictError("Tracker restoration requires its separate reviewed manager action.")
        restoration.validate_binding(prior_record, definition, desired_state, updated_by_user_id,
                                     import_metadata=import_metadata)
        metadata = audit_metadata or {}
        if (metadata.get("managed_resource_restoration") != restoration.descriptor()
                or metadata.get("manager_action") != "numeric_attest"
                or metadata.get("review_action") != "managed_resource_restoration"
                or metadata.get("numeric_authorization") != restoration.authorization
                or metadata.get("numeric_actor_id") != updated_by_user_id
                or metadata.get("action_id") != restoration.action_id
                or metadata.get("numeric_authorizations") is not None
                or metadata.get("manual_authorization") is not None
                or metadata.get("native_requalification") is not None):
            raise CharacterStateConflictError("The tracker restoration audit no longer matches Review.")
    if association is not None:
        from .character_feature_class_association import PendingFeatureClassAssociation, prepare_association_state
        if (type(association) is not PendingFeatureClassAssociation
                or operation_kind != "character_update_apply"
                or pending_numeric_authority is not None or reconstruction is not None
                or elective is not None or same_physical_mapping is not None
                or trusted_spell_choice_authoring or reconcile_reimport_state):
            raise CharacterStateConflictError("Class association requires its separate reviewed manager action.")
        association.validate_binding(prior_record, definition, desired_state, updated_by_user_id,
                                     import_metadata=import_metadata)
        if (audit_metadata or {}).get("feature_class_association") != association.descriptor():
            raise CharacterStateConflictError("The class association audit no longer matches Review.")
    ordinary_item_reads = _ordinary_item_source_reads(operation_kind, audit_metadata, reviewed_source_proof)
    if same_physical_mapping is not None:
        if operation_kind != "character_update_apply":
            raise CharacterStateConflictError("Same-physical source mapping requires its reviewed manager action.")
        same_physical_mapping.validate_binding(prior_record, definition, desired_state, updated_by_user_id)
        if (audit_metadata or {}).get("same_physical_mapping") != same_physical_mapping.descriptor():
            raise CharacterStateConflictError("The same-physical source audit no longer matches Review.")
    if elective is not None:
        from .character_language_electives import PendingElectiveDecision, validate_transition
        if operation_kind != "character_update_apply" or type(elective) is not PendingElectiveDecision:
            raise CharacterStateConflictError("Language decision publication lacks its reviewed proof.")
        validate_transition(prior_record, definition, elective, actor_id=updated_by_user_id, state=desired_state)
    native_proof = (reviewed_source_proof if reviewed_source_proof is not None
                    and reviewed_source_proof.native_result is not None else None)
    if native_proof is not None and operation_kind != "character_update_apply":
        raise CharacterStateConflictError("Native retention is unavailable for this update.")
    if reconstruction is None and same_physical_mapping is None:
        _reject_retired_item_spell_rows(prior_record.definition, definition)
    expected_config, _ = config(definition.campaign_slug)
    if reconcile_reimport_state and operation_kind not in {"markdown_import", "pdf_import"}:
        raise CharacterStateConflictError("Reimport reconciliation is unavailable for this update.")
    if pending_numeric_authority is not None and not pending_numeric_authority.claimed:
        raise CharacterStateConflictError("Native level-up proof was not claimed for publication.")
    from .character_equipment_activation import (
        ActivationPrerequisiteError, activation_frame_digest, require_update_activation,
    )
    from .system_policy import is_dnd_5e_system
    if operation_kind != "activation_repair" and is_dnd_5e_system(definition.system):
        try:
            require_update_activation(prior_record, definition, desired_state,
                reconstruction=reconstruction, actor_id=updated_by_user_id, native_proof=native_proof,
                source_read_owner=source_read_owner, feature_class_association=association)
        except ActivationPrerequisiteError as exc:
            if operation_kind == "character_update_apply":
                raise
            raise CharacterStateConflictError(str(exc)) from exc
    if explicit_removed_item_id and operation_kind != "interactive_update":
        raise CharacterStateConflictError("Explicit equipment removal is unavailable for this update.")
    if explicit_removed_item_id:
        from .character_service import prospective_exact_item_removal_state
        prospective_exact_item_removal_state(
            prior_record.definition, definition, prior_record.state_record.state,
            explicit_removed_item_id,
        )
    original_definition, original_state = definition, desired_state
    from .character_reconciliation import (
        validate_native_grant_transition, validate_native_spell_choice_authorizations,
    )
    load_prior_authority = _prior_numeric_authority_loader(coordinator, prior_record, source_read_owner=source_read_owner)
    # These are comparison facts only. The reserved phase rebuilds both pools
    # from authenticated original custody and freshly loaded current sources.
    choice_capacity = []
    choice_decisions = validate_native_grant_transition(
        prior_record, definition, desired_state, reviewed_source_proof=reviewed_source_proof,
        pending_numeric_authority=pending_numeric_authority, actor_id=updated_by_user_id,
        operation_kind=operation_kind, trusted_spell_choice_authoring=trusted_spell_choice_authoring,
        prior_authority_provider=load_prior_authority,
        source_context_provider=coordinator.native_choice_source_context_provider,
        capacity_snapshots=choice_capacity,
        source_read_owner=source_read_owner,
        source_read_context_provider=getattr(coordinator, "source_read_native_choice_context_provider", None),
    )
    authority = _update_numeric_authority(
        coordinator, prior_record, definition, desired_state,
        pending_numeric_authority=pending_numeric_authority, reviewed_source_proof=reviewed_source_proof,
        source_read_owner=source_read_owner,
    )
    if reviewed_source_proof is not None:
        reviewed_source_proof.recheck(prior_record, definition, desired_state,
                                      authority, expected_config["revision"], source_read_owner=source_read_owner,
                                      source_read_refresh=ordinary_item_reads)
    if reconstruction is not None or same_physical_mapping is not None:
        _reject_retired_item_spell_rows(
            prior_record.definition, definition, authority, prior_record.state_record.state,
            reconstruction=reconstruction, prior_record=prior_record, actor_id=updated_by_user_id,
            same_physical_mapping=same_physical_mapping, source_read_owner=source_read_owner,
        )
    if trusted_spell_choice_authoring and operation_kind != "interactive_update":
        raise CharacterStateConflictError("Spell choice authority is unavailable for this update.")
    admitted_choice_markers = (validate_native_spell_choice_authorizations(
        prior_record, definition, desired_state, authority, actor_id=updated_by_user_id)
        if trusted_spell_choice_authoring else ())
    from .character_item_casting import require_storage_preserved
    require_storage_preserved(prior_record.state_record.state, desired_state)
    from .character_item_prepared import require_preserved
    require_preserved(prior_record.state_record.state, desired_state)
    from .character_artificer_assignments import require_preserved as preserve_assignments
    preserve_assignments(prior_record.state_record.state, desired_state)
    item_baseline = _exact_item_transition_baseline(
        prior_record.definition, definition, None, authority, prior_record.state_record.state,
        reconstruction=reconstruction, prior_record=prior_record, actor_id=updated_by_user_id,
        prior_authority_provider=load_prior_authority,
        same_physical_mapping=same_physical_mapping, source_read_owner=source_read_owner,
    )
    if not item_baseline[0] and dict(definition.source or {}).get(
            "item_transition_withheld_resources") != dict(
            prior_record.definition.source or {}).get("item_transition_withheld_resources"):
        raise CharacterStateConflictError("Item transition repair marker needs an exact retired source.")
    if not item_baseline[0] and dict(definition.source or {}).get(
            "item_transition_cleared_charges") not in (
            None, dict(prior_record.definition.source or {}).get(
                "item_transition_cleared_charges")):
        raise CharacterStateConflictError("Item charge repair marker needs an exact relinked source.")
    if not item_baseline[0]:
        carried_charge_ids = set(dict(definition.source or {}).get(
            "item_transition_cleared_charges") or [])
        for old_row in prior_record.state_record.state.get("inventory") or []:
            if not isinstance(old_row, dict):
                continue
            catalog_id = str(old_row.get("catalog_ref") or old_row.get("id") or "").strip()
            if catalog_id not in carried_charge_ids:
                continue
            old_pair = (old_row.get("charges_current"), old_row.get("charges_max"))
            current_rows = [row for row in desired_state.get("inventory") or [] if isinstance(row, dict)
                and str(row.get("catalog_ref") or row.get("id") or "").strip() == catalog_id]
            if (len(current_rows) != 1 or current_rows[0].get("id") != old_row.get("id")
                    or (current_rows[0].get("charges_current"), current_rows[0].get("charges_max")) != old_pair):
                raise CharacterStateConflictError("A carried item-clearing marker cannot change later current-use observations.")
    if item_baseline[0]:
        definition, desired_state = _withhold_item_transition_aggregates(
            prior_record.definition, definition, desired_state,
            load_prior_authority(), authority, item_baseline,
        )
        authority = _update_numeric_authority(
            coordinator, prior_record, definition, desired_state,
            source_read_owner=source_read_owner,
        )
    primary, secondary = _pair(definition, import_metadata)
    elective_secondary = None
    if restoration is not None:
        retained = exact_character(definition.campaign_slug, definition.character_slug)
        if (retained is None or retained["revision"] != restoration.prior_generation
                or CharacterImportMetadata.from_dict(yaml.safe_load(retained["secondary_bytes"].decode("utf-8"))).to_dict()
                   != prior_record.import_metadata.to_dict()):
            raise CharacterStateConflictError("The exact tracker restoration import sidecar changed.")
        secondary = retained["secondary_bytes"]
        if len(primary) + len(secondary) > MAX_PAIR_BYTES:
            raise CommittedSourceConflict("Character pair exceeds its committed payload bound.")
    if elective is not None:
        secondary = elective_secondary = _elective_import_bytes(prior_record, import_metadata,
            reviewed_source_proof, audit_metadata)
        if len(primary) + len(secondary) > MAX_PAIR_BYTES:
            raise CommittedSourceConflict("Character pair exceeds its committed payload bound.")
    if explicit_removed_item_id:
        from .character_service import merge_state_with_definition
        expected_state = merge_state_with_definition(
            definition, prior_record.state_record.state,
            prior_definition=prior_record.definition,
            explicit_removed_item_id=explicit_removed_item_id,
            source_authority=authority,
        )
        if desired_state != expected_state:
            raise CharacterStateConflictError("Equipment removal state changed before publication.")
    if reimport_source_authority is not None and (
        authority is None
        or authority.identity != reimport_source_authority.identity
        or authority.source_snapshot_digest != reimport_source_authority.source_snapshot_digest
    ):
        raise CharacterStateConflictError(
            "Character source changed before reimport; inspect the Character and retry."
        )
    exact_reconstruction_state = reconstruction is not None or bool(native_proof is not None and (
        "equipment_activation" not in prior_record.state_record.state
        or native_proof.native_spell_origin_plan is not None))
    if elective is not None:
        from .character_language_electives import prepare_decision_state
        prepared = prepare_decision_state(prior_record, definition, desired_state, elective, updated_by_user_id)
    elif restoration is not None:
        prepared = prepare_restoration_state(prior_record, definition, desired_state, restoration,
            updated_by_user_id, import_metadata=import_metadata)
    elif association is not None:
        prepared = prepare_association_state(prior_record, definition, desired_state, association,
            updated_by_user_id, import_metadata=import_metadata)
    elif exact_reconstruction_state:
        from .character_reconstruction_state import prepare_exact_reconstruction_state
        prepared = prepare_exact_reconstruction_state(prior_record, definition, desired_state, authority,
            mapping_proof=reconstruction, actor_id=updated_by_user_id, spell_origin_proof=reviewed_source_proof,
            source_read_owner=source_read_owner)
    else:
        prepared = coordinator.state_store.prepare_initial_state(
            definition, desired_state, source_authority=authority,
            previous_state=prior_record.state_record.state,
        )
    if (same_physical_mapping is not None
            and activation_frame_digest(prepared.validated_state) != activation_frame_digest(prior_record.state_record.state)):
        raise CharacterStateConflictError("Additive physical source preparation changed current play facts.")
    if native_proof is not None and activation_frame_digest(prepared.validated_state) != activation_frame_digest(desired_state):
        raise CharacterStateConflictError("Native preparation changed the complete reviewed state.")
    if choice_decisions and prepared.validated_state != desired_state:
        raise CharacterStateConflictError("A class choice decision must preserve its exact reviewed state.")
    choice_audit_callback = (pending_numeric_authority.prepare_audit if pending_numeric_authority is not None
                             else native_choice_audit)
    choice_audit_markers = (pending_numeric_authority.markers if pending_numeric_authority is not None
                            else admitted_choice_markers)
    prospective_choice_audit = _prepare_native_choice_audit(
        coordinator, prior_record, definition, prepared.validated_state, authority,
        actor_id=updated_by_user_id, markers=choice_audit_markers, decisions=choice_decisions,
        callback=choice_audit_callback, leveled=pending_numeric_authority is not None,
    )
    prospective_transitions = _prepare_transition_renewals(
        prior_record, definition, prepared.validated_state, authority, None, get_db(),
        withheld_resource_ids=item_baseline[3] if item_baseline[0] else (),
        prior_authority_provider=load_prior_authority,
        reviewed_source_proof=reviewed_source_proof, actor_id=updated_by_user_id,
        spell_choice_decisions=choice_decisions, source_read_owner=source_read_owner,
    )
    if reconstruction is not None and prospective_transitions:
        raise CharacterStateConflictError("Exact reconstruction cannot renew existing transition grants.")
    if restoration is not None and (prospective_transitions or prospective_choice_audit or choice_decisions):
        raise CharacterStateConflictError("Tracker restoration cannot renew unrelated grants or choices.")
    if (reviewed_source_proof is not None and reviewed_source_proof.page_feature_markers
            and prepared.validated_state != desired_state):
        raise CharacterStateConflictError("Page feature state changed during validation.")
    pages, entries, new_pages, new_entries = _update_source_claims(
        prior_record, definition, prepared.validated_state,
    )
    connection = get_db()
    owned_snapshot = not connection.in_transaction
    if source_read_owner is not None and not owned_snapshot:
        from .character_source_reads import SourceReadConflict
        raise SourceReadConflict("Native preflight cannot borrow an ambient source transaction.")
    snapshot_failure = None
    try:
        if owned_snapshot:
            connection.execute("BEGIN")
        expected_source = _create_source_proof(
            definition.campaign_slug, new_pages, new_entries, connection=connection,
        )
    except BaseException as exc:
        snapshot_failure = exc
        raise
    finally:
        if owned_snapshot:
            try:
                if source_read_owner is not None:
                    source_read_owner._rollback_owned()
                else:
                    connection.rollback()
            except BaseException as cleanup:
                if snapshot_failure is not None:
                    details = [snapshot_failure]
                    if cleanup.__cause__ is not None:
                        details.append(cleanup.__cause__)
                    raise cleanup from BaseExceptionGroup("Source preflight primary and cleanup failures", details)
                raise
    clean_audit = coordinator._prepare_update_audit(
        operation_kind=operation_kind, audit_event_type=audit_event_type,
        audit_actor_user_id=audit_actor_user_id, audit_target_user_id=audit_target_user_id,
        audit_metadata=audit_metadata,
    )
    native_audit = (isinstance(audit_metadata, dict) and audit_metadata.get("source") == "character_source_repair"
                    and audit_metadata.get("manager_action") == "native_requalify")
    if native_proof is not None and (not native_audit or audit_actor_user_id != updated_by_user_id
            or audit_metadata.get("action_id") != native_proof.native_action_id
            or audit_metadata.get("review_digest") != hashlib.sha256(native_proof.native_review_token.encode("utf-8")).hexdigest()
            or activation_frame_digest(audit_metadata.get("native_requalification"))
               != activation_frame_digest(native_proof.native_result.provenance)
            or activation_frame_digest(audit_metadata.get("numeric_authorizations"))
               != activation_frame_digest(native_proof.native_requalification_markers)):
        raise CharacterStateConflictError("Native publication needs the complete signed audit context.")
    if native_audit:
        clean_audit = prepare_native_requalification_audit(
            coordinator, prior_record, definition, desired_state, audit_metadata, audit_actor_user_id,
            connection=connection)
    assignment = get_db().execute(
        "SELECT id,user_id FROM character_assignments WHERE campaign_slug=? AND character_slug=?",
        (definition.campaign_slug, definition.character_slug),
    ).fetchone()
    expected_assignment = tuple(assignment) if assignment is not None else None
    if desired_asset_bytes:
        from .campaign_content_service import validated_campaign_asset_media_type
        if operation_kind != "portrait_upsert" or not desired_asset_ref:
            raise CommittedSourceConflict("Portrait bytes are not allowed for this update.")
        filename = Path(desired_asset_ref).name
        if validated_campaign_asset_media_type(Path(filename), data_blob=bytes(desired_asset_bytes)) is None:
            raise CommittedSourceConflict("Portrait bytes failed image validation.")
    if _activation_preparation is not None:
        preparation_prior_authority = load_prior_authority()
        source_read_owner.require_live()
        if source_read_owner._declined or source_read_owner._last_guard is None:
            raise CharacterStateConflictError("Complete activation preparation needs an owned current source phase.")
        result = _activation_preparation_result(prior_record, definition, import_metadata, desired_state,
            prepared, primary, secondary, authority, prospective_transitions, prospective_choice_audit,
            choice_decisions, choice_capacity, expected_config, expected_source, expected_assignment,
            new_pages, new_entries, clean_audit, preparation_prior_authority, connection=connection,
            actor_id=updated_by_user_id)
        source_read_owner.checkpoint()
        source_read_owner.close()
        return result
    if source_read_owner is not None:
        source_read_owner.checkpoint()
        source_read_owner.close()
    scoped_source_reads = (native_proof is not None or same_physical_mapping is not None
                           or association is not None or restoration is not None or ordinary_item_reads)
    _reserve(connection, source_read_cleanup=scoped_source_reads)
    try:
        if scoped_source_reads:
            from .character_source_reads import SourceReadOwner
            source_read_owner = SourceReadOwner._after_publication_reserve(
                connection, definition.campaign_slug, definition.character_slug)
        slug = definition.character_slug
        campaign = definition.campaign_slug
        _reject_journals(connection, campaign, slug)
        source = exact_character(campaign, slug, connection=connection)
        if source is None or prior_record.committed_revision != source["revision"]:
            raise CharacterStateConflictError("Character definition changed before publication.")
        loaded_definition = CharacterDefinition.from_dict(
            yaml.safe_load(source["primary_bytes"].decode("utf-8"))
        )
        loaded_import = CharacterImportMetadata.from_dict(
            yaml.safe_load(source["secondary_bytes"].decode("utf-8"))
        )
        if (loaded_definition.to_dict() != prior_record.definition.to_dict()
                or loaded_import.to_dict() != prior_record.import_metadata.to_dict()):
            raise CharacterStateConflictError("Character definition was not loaded from current committed bytes.")
        if elective is not None:
            locked_secondary = _elective_import_bytes(prior_record, import_metadata,
                reviewed_source_proof, audit_metadata, connection=connection)
            if locked_secondary != elective_secondary or source["secondary_bytes"] != elective_secondary:
                raise CharacterStateConflictError("The physical import sidecar changed under reservation.")
            secondary = locked_secondary
        if restoration is not None and source["secondary_bytes"] != secondary:
            raise CharacterStateConflictError("The tracker restoration import sidecar changed under reservation.")
        if native_proof is not None and (
                activation_frame_digest(loaded_definition.to_dict()) != native_proof.prior_definition_digest
                or activation_frame_digest(loaded_import.to_dict()) != activation_frame_digest(prior_record.import_metadata.to_dict())):
            raise CharacterStateConflictError("Native original typed frame changed before publication.")
        locked_config, settings = config(campaign, connection=connection)
        if (locked_config["revision"] != expected_config["revision"]
                or normalize_system_code(settings.get("system")) != definition.system):
            raise CommittedSourceConflict("Character system changed before publication.")
        row = connection.execute(
            "SELECT revision,state_json FROM character_state WHERE campaign_slug=? AND character_slug=?",
            (campaign, slug),
        ).fetchone()
        if (row is None or row["revision"] != expected_revision
                or json.loads(row["state_json"]) != prior_record.state_record.state):
            raise CharacterStateConflictError("Character state changed before publication.")
        if native_proof is not None and activation_frame_digest(json.loads(row["state_json"])) != native_proof.prior_state_digest:
            raise CharacterStateConflictError("Native original typed state changed before publication.")
        load_locked_prior_authority = _prior_numeric_authority_loader(
            coordinator, prior_record, prepublication=False, source_read_owner=source_read_owner,
        )
        locked_capacity = []
        locked_choices = validate_native_grant_transition(
            prior_record, definition, desired_state, reviewed_source_proof=reviewed_source_proof,
            pending_numeric_authority=pending_numeric_authority, actor_id=updated_by_user_id,
            connection=connection, operation_kind=operation_kind,
            trusted_spell_choice_authoring=trusted_spell_choice_authoring,
            prior_authority_provider=load_locked_prior_authority,
            source_context_provider=coordinator.native_choice_source_context_provider,
            capacity_snapshots=locked_capacity,
            source_read_owner=source_read_owner,
            source_read_context_provider=getattr(coordinator, "source_read_native_choice_context_provider", None),
        )
        if locked_capacity != choice_capacity:
            raise CharacterStateConflictError("Character spell choice capacity changed before publication.")
        if locked_choices != choice_decisions:
            raise CharacterStateConflictError("Character spell choice decision changed before publication.")
        locked_assignment = connection.execute(
            "SELECT id,user_id FROM character_assignments WHERE campaign_slug=? AND character_slug=?",
            (campaign, slug),
        ).fetchone()
        if (tuple(locked_assignment) if locked_assignment is not None else None) != expected_assignment:
            raise CharacterStateConflictError("Character assignment changed before publication.")
        refreshed = authority
        if authority is not None:
            refreshed = _update_numeric_authority(
                coordinator, prior_record, definition, desired_state,
                pending_numeric_authority=pending_numeric_authority,
                reviewed_source_proof=(reviewed_source_proof if not item_baseline[0] else None),
                prepublication=False,
                source_read_owner=source_read_owner,
            )
            if (refreshed is None or refreshed.identity != authority.identity
                    or refreshed.source_snapshot_digest != authority.source_snapshot_digest):
                raise CharacterStateConflictError("Character source proof changed before publication.")
            if reviewed_source_proof is not None and not item_baseline[0]:
                reviewed_source_proof.recheck(prior_record, definition, desired_state,
                                              refreshed, locked_config["revision"], source_read_owner=source_read_owner,
                                              source_read_refresh=ordinary_item_reads)
            if native_proof is not None:
                require_update_activation(prior_record, definition, desired_state,
                    actor_id=updated_by_user_id, native_proof=native_proof, source_read_owner=source_read_owner)
            if association is not None:
                require_update_activation(prior_record, definition, desired_state,
                    actor_id=updated_by_user_id, feature_class_association=association,
                    source_read_owner=source_read_owner)
            if elective is not None:
                locked_prepared = prepare_decision_state(prior_record, definition, desired_state,
                    elective, updated_by_user_id, exact_state_json=row["state_json"])
                if locked_prepared.validated_state != prepared.validated_state:
                    raise CharacterStateConflictError("The exact language decision state changed.")
                prepared = locked_prepared
            elif restoration is not None:
                locked_prepared = prepare_restoration_state(prior_record, definition, desired_state,
                    restoration, updated_by_user_id, import_metadata=import_metadata,
                    exact_state_json=row["state_json"])
                if (locked_prepared.validated_state != prepared.validated_state
                        or locked_prepared.state_json != prepared.state_json):
                    raise CharacterStateConflictError("The exact tracker restoration state changed.")
                prepared = locked_prepared
            elif association is not None:
                locked_prepared = prepare_association_state(prior_record, definition, desired_state,
                    association, updated_by_user_id, import_metadata=import_metadata,
                    exact_state_json=row["state_json"])
                if (locked_prepared.validated_state != prepared.validated_state
                        or locked_prepared.state_json != prepared.state_json):
                    raise CharacterStateConflictError("The exact class association state changed.")
                prepared = locked_prepared
            elif exact_reconstruction_state:
                locked_prepared = prepare_exact_reconstruction_state(
                    prior_record, definition, desired_state, refreshed, exact_state_json=row["state_json"],
                    mapping_proof=reconstruction, actor_id=updated_by_user_id, spell_origin_proof=reviewed_source_proof,
                    source_read_owner=source_read_owner)
                if activation_frame_digest(locked_prepared.validated_state) != activation_frame_digest(prepared.validated_state):
                    raise CharacterStateConflictError("Reconstruction state compatibility changed.")
                prepared = locked_prepared
            elif native_proof is not None:
                locked_prepared = coordinator.state_store.prepare_initial_state(
                    definition, desired_state, source_authority=refreshed,
                    previous_state=prior_record.state_record.state)
                if (activation_frame_digest(locked_prepared.validated_state) != activation_frame_digest(desired_state)
                        or activation_frame_digest(locked_prepared.validated_state) != activation_frame_digest(prepared.validated_state)):
                    raise CharacterStateConflictError("Native preparation changed the complete reviewed state under reservation.")
                prepared = locked_prepared
            if explicit_removed_item_id:
                locked_expected_state = merge_state_with_definition(
                    definition, prior_record.state_record.state,
                    prior_definition=prior_record.definition,
                    explicit_removed_item_id=explicit_removed_item_id,
                    source_authority=refreshed,
                )
                if desired_state != locked_expected_state:
                    raise CharacterStateConflictError("Equipment removal state changed before publication.")
        if reconcile_reimport_state:
            from .character_importer import reconcile_imported_state
            from .system_policy import is_xianxia_system
            if refreshed is None and not is_xianxia_system(definition.system):
                raise CharacterStateConflictError(
                    "Character numeric authority is unavailable; repair source links before reimport."
                )
            try:
                reserved_state = reconcile_imported_state(
                    definition, prior_record.state_record.state,
                    previous_definition=prior_record.definition,
                    source_authority=refreshed,
                )
            except ValueError as exc:
                raise CharacterStateConflictError(
                    "Reimport source or state needs manager repair before publication."
                ) from exc
            if reserved_state != desired_state:
                raise CharacterStateConflictError(
                    "Character source or state changed before reimport; inspect the Character and retry."
                )
            reserved_prepared = coordinator.state_store.prepare_initial_state(
                definition, reserved_state, source_authority=refreshed,
                previous_state=prior_record.state_record.state,
            )
            if reserved_prepared.validated_state != prepared.validated_state:
                raise CharacterStateConflictError(
                    "Character source or state changed before reimport; inspect the Character and retry."
                )
            prepared = reserved_prepared
        if trusted_spell_choice_authoring and validate_native_spell_choice_authorizations(
                prior_record, definition, desired_state, refreshed, actor_id=updated_by_user_id
                ) != admitted_choice_markers:
            raise CharacterStateConflictError("Character spell choice marker changed before publication.")
        if same_physical_mapping is not None:
            locked_mapping_state = coordinator.state_store.prepare_initial_state(
                definition, desired_state, source_authority=refreshed,
                previous_state=prior_record.state_record.state)
            if (activation_frame_digest(locked_mapping_state.validated_state) != activation_frame_digest(prior_record.state_record.state)
                    or activation_frame_digest(prepared.validated_state) != activation_frame_digest(locked_mapping_state.validated_state)):
                raise CharacterStateConflictError("Additive physical source state changed under reservation.")
        locked_pages, locked_entries, locked_new_pages, locked_new_entries = _update_source_claims(
            prior_record, definition, prepared.validated_state,
        )
        if ((locked_pages, locked_entries, locked_new_pages, locked_new_entries)
                != (pages, entries, new_pages, new_entries)):
            raise CommittedSourceConflict("Character source claims changed before publication.")
        locked_source = _create_source_proof(
            campaign, locked_new_pages, locked_new_entries, connection=connection,
        )
        if (locked_source != expected_source
                or locked_source.config_revision != locked_config["revision"]):
            raise CommittedSourceConflict("Character source changed before publication.")
        if reconstruction is not None or same_physical_mapping is not None:
            _reject_retired_item_spell_rows(
                prior_record.definition, definition, refreshed, prior_record.state_record.state,
                reconstruction=reconstruction, prior_record=prior_record, actor_id=updated_by_user_id,
                same_physical_mapping=same_physical_mapping, source_read_owner=source_read_owner,
            )
        if _exact_item_transition_baseline(
            prior_record.definition, definition, None, refreshed, prior_record.state_record.state,
            reconstruction=reconstruction, prior_record=prior_record, actor_id=updated_by_user_id,
            prior_authority_provider=load_locked_prior_authority,
            same_physical_mapping=same_physical_mapping, source_read_owner=source_read_owner,
        ) != item_baseline:
            raise CharacterStateConflictError("Item baseline changed before publication.")
        if item_baseline[0]:
            locked_original_authority = _update_numeric_authority(
                coordinator, prior_record, original_definition, original_state,
                reviewed_source_proof=reviewed_source_proof, prepublication=False,
                source_read_owner=source_read_owner,
            )
            if reviewed_source_proof is not None:
                reviewed_source_proof.recheck(
                    prior_record, original_definition, original_state,
                    locked_original_authority, locked_config["revision"], source_read_owner=source_read_owner,
                    source_read_refresh=ordinary_item_reads)
            if (locked_original_authority is None or authority is None
                    or locked_original_authority.source_snapshot_digest
                       != authority.source_snapshot_digest):
                raise CharacterStateConflictError("Item transition source changed before publication.")
            locked_definition, locked_state = _withhold_item_transition_aggregates(
                prior_record.definition, original_definition, original_state,
                load_locked_prior_authority(), locked_original_authority, item_baseline,
            )
            if (locked_definition.to_dict() != definition.to_dict()
                    or locked_state != desired_state):
                raise CharacterStateConflictError("Item transition proof changed before publication.")
        locked_transitions = _prepare_transition_renewals(
            prior_record, definition, prepared.validated_state, refreshed,
            None, connection,
            withheld_resource_ids=item_baseline[3] if item_baseline[0] else (),
            prior_authority_provider=load_locked_prior_authority,
            reviewed_source_proof=reviewed_source_proof, actor_id=updated_by_user_id,
            spell_choice_decisions=locked_choices, source_read_owner=source_read_owner,
        )
        if locked_transitions != prospective_transitions:
            raise CharacterStateConflictError("Character transition proof changed before publication.")
        prior_portrait = portrait_bytes(campaign, slug, connection=connection)
        ref = str((definition.profile or {}).get("portrait_asset_ref") or "").strip()
        if operation_kind == "portrait_upsert":
            if not desired_asset_bytes or ref != desired_asset_ref:
                raise CommittedSourceConflict("Portrait publication is incomplete.")
            portrait = (ref, bytes(desired_asset_bytes))
        elif operation_kind == "portrait_remove":
            if ref or desired_asset_bytes or desired_asset_ref:
                raise CommittedSourceConflict("Portrait removal is incomplete.")
            portrait = None
        else:
            if desired_asset_bytes or desired_asset_ref:
                raise CommittedSourceConflict("Unexpected portrait bytes.")
            if ref != (prior_portrait[0] if prior_portrait else ""):
                raise CommittedSourceConflict("Portrait reference requires a portrait publication.")
            portrait = prior_portrait
        preserve_exact_state = (
            operation_kind in {"markdown_import", "pdf_import", "content_api_update", "character_update_apply"}
            and (activation_frame_digest(desired_state) == activation_frame_digest(prior_record.state_record.state)
                 if native_proof is not None or same_physical_mapping is not None else desired_state == prior_record.state_record.state)
        )
        if native_audit and prepare_native_requalification_audit(
                coordinator, prior_record, definition, desired_state, audit_metadata, audit_actor_user_id,
                connection=connection) != clean_audit:
            raise CharacterStateConflictError("Native audit evidence changed under publication reservation.")
        if _prepare_native_choice_audit(
                coordinator, prior_record, definition, prepared.validated_state, refreshed,
                actor_id=updated_by_user_id, markers=choice_audit_markers, decisions=locked_choices,
                callback=choice_audit_callback, leveled=pending_numeric_authority is not None,
                ) != prospective_choice_audit:
            raise CharacterStateConflictError("Native choice audit changed under publication reservation.")
        if source_read_owner is not None:
            source_read_owner.checkpoint()
            source_read_owner.before_publication_write()
        state_changed = (activation_frame_digest(prepared.validated_state) != activation_frame_digest(prior_record.state_record.state)
                         if native_proof is not None or same_physical_mapping is not None else prepared.validated_state != prior_record.state_record.state)
        if not preserve_exact_state and state_changed:
            cursor = connection.execute(
                "UPDATE character_state SET revision=revision+1,state_json=?,updated_at=?,"
                "updated_by_user_id=? WHERE campaign_slug=? AND character_slug=? AND revision=?",
                (prepared.state_json, _now(), updated_by_user_id, campaign, slug, expected_revision),
            )
            if cursor.rowcount != 1:
                raise CharacterStateConflictError("Character state changed before publication.")
        number = _append(connection, campaign_slug=campaign, character_slug=slug, previous=source,
                         primary=primary, secondary=secondary, portrait=portrait,
                         actor=updated_by_user_id, system=definition.system)
        if clean_audit[0] is not None:
            audit_payload = json.loads(clean_audit[3])
            if elective is not None:
                from .character_language_electives import confirmed_metadata as elective_confirmation
                audit_payload.update(elective_confirmation(elective, definition=definition,
                    prior_record=prior_record, state=desired_state, actor_id=audit_actor_user_id,
                    generation=number, review_digest=audit_payload.get("review_digest"),
                    plan_digest=audit_payload.get("plan_digest"),
                    source_digest=reviewed_source_proof.reviewed_source_digest,
                    policy_digest=reviewed_source_proof.reviewed_policy_digest,
                    review_basis=audit_payload.get("language_review_basis")))
                sanitized = coordinator.auth_store.sanitize_audit_metadata(audit_payload)
                if sanitized != audit_payload or len(json.dumps(sanitized, sort_keys=True).encode("utf-8")) > 65536:
                    raise CharacterStateConflictError("Language decision confirmation exceeds the bounded audit contract.")
            if reconstruction is not None:
                from .character_reconstruction_authority import confirmed_metadata
                audit_payload.update(confirmed_metadata(
                    reconstruction, definition=definition, prior_record=prior_record,
                    state=desired_state, actor_id=audit_actor_user_id, generation=number))
                audit_payload["published_definition_digest"] = audit_payload["definition_digest"]
                sanitized = coordinator.auth_store.sanitize_audit_metadata(audit_payload)
                if sanitized != audit_payload or len(json.dumps(sanitized, sort_keys=True).encode("utf-8")) > 65536:
                    raise CharacterStateConflictError("Reconstruction confirmation exceeds the bounded audit contract.")
            if ((clean_audit[0] == "character_update_applied"
                    and audit_payload.get("source") == "character_source_repair"
                    and audit_payload.get("review_digest"))
                    or (clean_audit[0] == "character_native_edited"
                        and audit_payload.get("source") == "native_edit_confirmed")):
                from .character_update_apply import canonical_digest
                audit_payload["published_definition_digest"] = canonical_digest(
                    definition.to_dict())
                audit_payload["published_revision"] = number
                audit_payload["published_state_revision"] = connection.execute(
                    "SELECT revision FROM character_state WHERE campaign_slug=? AND character_slug=?",
                    (campaign, slug),
                ).fetchone()[0]
            if native_audit and coordinator._prepare_update_audit(
                    operation_kind=operation_kind, audit_event_type=clean_audit[0],
                    audit_actor_user_id=clean_audit[1], audit_target_user_id=clean_audit[2],
                    audit_metadata=audit_payload) != clean_audit:
                raise CharacterStateConflictError("Native audit serialization changed before confirmation.")
            coordinator.auth_store.insert_audit_event(
                event_type=clean_audit[0], actor_user_id=clean_audit[1],
                target_user_id=clean_audit[2], campaign_slug=campaign,
                character_slug=slug, metadata=audit_payload, commit=False,
            )
        if reviewed_source_proof is not None and reviewed_source_proof.page_feature_markers:
            if (operation_kind != "character_update_apply" or clean_audit[0] != "character_update_applied"
                    or audit_actor_user_id is None or not isinstance(audit_metadata, dict)):
                raise CharacterStateConflictError("Page feature grant audit is unavailable.")
            from .character_source_authority import numeric_target_values, numeric_value_digest
            from .character_service import build_resource_state
            values = numeric_target_values(definition, desired_state)
            prior_resources = list(prior_record.state_record.state.get("resources") or [])
            desired_resources = list(desired_state.get("resources") or [])
            if desired_resources[:len(prior_resources)] != prior_resources:
                raise CharacterStateConflictError("Page feature grant changed existing state.")
            added_resources = desired_resources[len(prior_resources):]
            marker_ids = {marker["target_id"].removeprefix("resource:") for marker in
                          reviewed_source_proof.page_feature_markers}
            if (len(marker_ids) != len(reviewed_source_proof.page_feature_markers)
                    or {row.get("id") for row in added_resources if isinstance(row, dict)} != marker_ids
                    or len(added_resources) != len(marker_ids)):
                raise CharacterStateConflictError("Page feature grant state is incomplete.")
            review_digest = audit_metadata.get("review_digest")
            candidate_digest = audit_metadata.get("candidate_digest")
            action_ids = {marker.get("action_id") for marker in
                          reviewed_source_proof.page_feature_markers}
            if (len(action_ids) != 1 or not all(isinstance(value, str) and len(value) == 64
                                                for value in action_ids)
                    or connection.execute(
                        "SELECT 1 FROM auth_audit_log WHERE event_type=? AND campaign_slug=? "
                        "AND character_slug=? AND metadata_json LIKE ?",
                        ("character_page_feature_grant_confirmed", campaign, slug,
                         f'%"action_id": "{next(iter(action_ids))}"%'),
                    ).fetchone()):
                raise CharacterStateConflictError("Page feature grant witness was already used.")
            for marker in reviewed_source_proof.page_feature_markers:
                key = ("resource", marker["target_id"], "owner_reset")
                matching = [row for row in added_resources if isinstance(row, dict)
                            and row.get("id") == marker["target_id"].removeprefix("resource:")]
                if (key not in values or numeric_value_digest(values[key]) != marker["value_digest"]
                        or len(matching) != 1 or matching[0] != build_resource_state(values[key])):
                    raise CharacterStateConflictError("Page feature grant witness changed.")
                coordinator.auth_store.insert_audit_event(
                    event_type="character_page_feature_grant_confirmed",
                    actor_user_id=audit_actor_user_id, campaign_slug=campaign,
                    character_slug=slug, metadata={
                        "source": "page_feature_update_confirmed",
                        "numeric_actor_id": audit_actor_user_id,
                        "numeric_authorization": marker,
                        "source_basis_digest": marker["source_basis_digest"],
                        "action_id": marker["action_id"],
                        "review_digest": review_digest,
                        "candidate_digest": candidate_digest,
                        "committed_revision": number,
                        "prior_state_revision": expected_revision,
                        "state_revision": expected_revision + 1,
                    }, commit=False,
                )
        _append_transition_renewals(connection, campaign, slug, locked_transitions)
        state = coordinator.state_store.get_state(campaign, slug)
        if state is None:
            raise CharacterStateUnavailableError("Committed Character state disappeared before publication.")
        if native_proof is not None and (
                activation_frame_digest(state.state) != native_proof.desired_state_digest
                or state.revision != expected_revision + int(state_changed)):
            raise CharacterStateConflictError("Native durable state differs from its complete reviewed frame.")
        result = CharacterRecord(definition, import_metadata, state, committed_revision=number)
        connection.commit()
    except BaseException as primary:
        if scoped_source_reads:
            from .db import rollback_source_read_connection
            rollback_source_read_connection(connection, primary=primary)
        else:
            try:
                connection.rollback()
            except BaseException as cleanup:
                raise primary from cleanup
        raise
    finally:
        if source_read_owner is not None:
            source_read_owner.close()
    coordinator.repository.invalidate_character(definition.campaign_slug, definition.character_slug)
    _replay_after_commit(coordinator.campaigns_dir, definition.campaign_slug)
    return result


def publish_delete(coordinator, campaign_slug, character_slug, *, operation_kind,
                   actor_user_id=None, audit_source=None,
                   expected_definition_revision=None, expected_state_revision=None):
    from .character_reconciliation import CharacterDeletionConflict, CharacterDeletionError, CharacterDeletionResult
    validate_character_slug(character_slug)
    if (type(expected_definition_revision) is not int or expected_definition_revision < 1
            or type(expected_state_revision) is not int or expected_state_revision < 1):
        raise CharacterDeletionConflict("Character deletion requires observed definition and state revisions.")
    if operation_kind == "content_api":
        if actor_user_id is not None or audit_source is not None:
            raise CharacterDeletionError("Raw content deletion cannot create an audit event.")
    elif audit_source != operation_kind:
        raise CharacterDeletionError("Character deletion audit source is invalid.")
    connection = get_db()
    _reserve(connection)
    try:
        _reject_journals(connection, campaign_slug, character_slug)
        source = exact_character(campaign_slug, character_slug, connection=connection,
                                 allow_tombstone=True)
        pointer = connection.execute(
            "SELECT revision FROM committed_source_current WHERE campaign_slug=? "
            "AND object_kind='character' AND object_ref=?", (campaign_slug, character_slug),
        ).fetchone()
        if source is None:
            if pointer is not None:
                raise CharacterDeletionError("Character committed proof needs manager repair.")
            raise CharacterDeletionConflict("Character changed before deletion confirmation.")
        if source["tombstone"]:
            raise CharacterDeletionConflict("Character changed before deletion confirmation.")
        if source["revision"] != expected_definition_revision:
            raise CharacterDeletionConflict("Character definition changed before deletion confirmation.")
        portrait = portrait_bytes(campaign_slug, character_slug, connection=connection)
        _, settings = config(campaign_slug, connection=connection)
        state = connection.execute(
            "SELECT revision FROM character_state WHERE campaign_slug=? AND character_slug=?",
            (campaign_slug, character_slug),
        ).fetchone()
        if state is None or state["revision"] != expected_state_revision:
            raise CharacterDeletionConflict("Character state changed before deletion confirmation.")
        assignment = connection.execute(
            "SELECT user_id FROM character_assignments WHERE campaign_slug=? AND character_slug=?",
            (campaign_slug, character_slug),
        ).fetchone()
        connection.execute("DELETE FROM character_state WHERE campaign_slug=? AND character_slug=?",
                           (campaign_slug, character_slug))
        connection.execute("DELETE FROM character_assignments WHERE campaign_slug=? AND character_slug=?",
                           (campaign_slug, character_slug))
        _append(connection, campaign_slug=campaign_slug, character_slug=character_slug,
                previous=source, primary=None, secondary=None, portrait=None,
                actor=actor_user_id, system=normalize_system_code(settings["system"]))
        if operation_kind != "content_api":
            coordinator.auth_store.insert_audit_event(
                event_type="character_deleted", actor_user_id=actor_user_id,
                target_user_id=assignment["user_id"] if assignment else None,
                campaign_slug=campaign_slug, character_slug=character_slug,
                metadata={"deleted_files": True, "deleted_state": True,
                          "deleted_assignment": assignment is not None,
                          "deleted_assets": portrait is not None, "source": audit_source},
                commit=False,
            )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    coordinator.repository.invalidate_character(campaign_slug, character_slug)
    _replay_after_commit(coordinator.campaigns_dir, campaign_slug)
    return CharacterDeletionResult(character_slug, True, True, assignment is not None,
                                   portrait is not None)


def _replay_after_commit(campaigns_dir, campaign_slug):
    try:
        from .committed_publication import replay_mirrors
        replay_mirrors(campaigns_dir, campaign_slug=campaign_slug)
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        # SQLite is authoritative; a later manager replay can finish mirrors.
        pass


def replay_character_mirror(connection, campaigns_dir, row, source, settings):
    """Compare each file against its own retained basis, then replay this pair."""
    from .committed_publication import _mirror_bytes, _safe_mirror_path
    from .file_publication import atomic_move_file, atomic_write_bytes_no_replace
    from .character_assets import resolve_character_portrait_asset_path
    from .character_path_safety import resolve_character_definition_import_paths
    from .character_assets import CHARACTER_PORTRAIT_MAX_BYTES

    slug, character_slug = row["campaign_slug"], row["object_ref"]
    source_root = Path(campaigns_dir) / slug
    configured_dir = settings.get("character_dir", "characters")
    if (not isinstance(configured_dir, str) or not configured_dir
            or Path(configured_dir).is_absolute() or ".." in PurePath(configured_dir).parts
            or "\\" in configured_dir):
        raise CommittedSourceConflict("Committed Character mirror root is unsafe.")
    character_root = source_root / configured_dir
    if not character_root.resolve().is_relative_to(source_root.resolve()):
        raise CommittedSourceConflict("Committed Character mirror root escapes its campaign.")
    definition_path, import_path = resolve_character_definition_import_paths(
        character_root, character_slug,
    )
    desired_pair = (source["primary_bytes"], source["secondary_bytes"])
    basis_pair = (row["expected_primary_sha256"], row["expected_secondary_sha256"])
    observed = []
    conflict = False
    for path, desired, basis in zip((definition_path, import_path), desired_pair, basis_pair):
        path = _safe_mirror_path(path, create_parents=True)
        retained = path.with_name(path.name + f".committed-{row['id']}.draft")
        actual = _mirror_bytes(path)
        if conflict:
            observed.append(actual)
            continue
        if _sha(actual) == _sha(desired):
            observed.append(actual)
            continue
        local_conflict = False
        if basis is None:
            if actual is not None:
                local_conflict = True
        elif actual is not None and _sha(actual) == basis and not retained.exists():
            atomic_move_file(path, retained)
            actual = None
        elif actual is not None:
            local_conflict = True
        if retained.exists() and _sha(_mirror_bytes(retained)) != basis:
            local_conflict = True
        if actual is None and basis is not None and not retained.exists():
            local_conflict = True
        if not local_conflict and desired is not None:
            try:
                atomic_write_bytes_no_replace(path, desired)
            except FileExistsError:
                if _sha(_mirror_bytes(path)) != _sha(desired):
                    local_conflict = True
        conflict = conflict or local_conflict
        observed.append(_mirror_bytes(path))
    portrait = portrait_bytes(slug, character_slug, connection=connection) if not source["tombstone"] else None
    old_proof = connection.execute(
        "SELECT asset_ref,sha256,image_bytes FROM committed_character_portraits "
        "WHERE campaign_slug=? AND character_slug=? AND revision=?",
        (slug, character_slug, source["revision"] - 1),
    ).fetchone()
    if old_proof is not None and _sha(old_proof["image_bytes"]) != old_proof["sha256"]:
        raise CommittedSourceConflict("Prior portrait proof failed; manager repair required.")

    def asset_bytes(path):
        path = _safe_mirror_path(path, create_parents=True)
        if not path.exists():
            return None
        if path.stat().st_size > CHARACTER_PORTRAIT_MAX_BYTES:
            raise CommittedSourceConflict("Portrait mirror exceeds its payload bound.")
        return path.read_bytes()

    if not conflict and old_proof is not None and (portrait is None or portrait[0] != old_proof["asset_ref"]):
        _, old_path = resolve_character_portrait_asset_path(
            source_root, character_slug, old_proof["asset_ref"],
        )
        old_path = _safe_mirror_path(old_path, create_parents=True)
        retained = old_path.with_name(old_path.name + f".committed-{row['id']}.draft")
        old_actual = asset_bytes(old_path)
        if old_actual is not None and _sha(old_actual) == old_proof["sha256"] and not retained.exists():
            atomic_move_file(old_path, retained)
        elif (old_actual is not None or not retained.exists()
              or _sha(asset_bytes(retained)) != old_proof["sha256"]):
            conflict = True
    if not conflict and portrait is not None:
        ref, image = portrait
        _, asset_path = resolve_character_portrait_asset_path(source_root, character_slug, ref)
        asset_path = _safe_mirror_path(asset_path, create_parents=True)
        actual_image = asset_bytes(asset_path)
        if _sha(actual_image) != _sha(image):
            retained = asset_path.with_name(asset_path.name + f".committed-{row['id']}.draft")
            if (old_proof is not None and old_proof["asset_ref"] == ref
                    and actual_image is not None and _sha(actual_image) == old_proof["sha256"]
                    and not retained.exists()):
                atomic_move_file(asset_path, retained)
                actual_image = None
            if (actual_image is not None or
                    old_proof is not None and old_proof["asset_ref"] == ref
                    and (not retained.exists() or _sha(asset_bytes(retained)) != old_proof["sha256"])):
                conflict = True
            elif not conflict:
                try:
                    atomic_write_bytes_no_replace(asset_path, image)
                except FileExistsError:
                    if _sha(asset_bytes(asset_path)) != _sha(image):
                        conflict = True
    state = "conflict" if conflict else "complete"
    connection.execute(
        """INSERT INTO committed_source_mirrors
        (campaign_slug,object_kind,object_ref,expected_primary_sha256,
         expected_secondary_sha256,mirrored_revision,state,draft_primary_bytes,
         draft_secondary_bytes,observed_primary_sha256,observed_secondary_sha256,updated_at)
        VALUES (?,'character',?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(campaign_slug,object_kind,object_ref) DO UPDATE SET
        expected_primary_sha256=excluded.expected_primary_sha256,
        expected_secondary_sha256=excluded.expected_secondary_sha256,
        mirrored_revision=excluded.mirrored_revision,state=excluded.state,
        draft_primary_bytes=excluded.draft_primary_bytes,
        draft_secondary_bytes=excluded.draft_secondary_bytes,
        observed_primary_sha256=excluded.observed_primary_sha256,
        observed_secondary_sha256=excluded.observed_secondary_sha256,
        updated_at=excluded.updated_at""",
        (slug, character_slug, _sha(desired_pair[0]), _sha(desired_pair[1]), row["revision"],
         "matching" if not conflict else "conflict",
         observed[0] if conflict else None, observed[1] if conflict else None,
         _sha(observed[0]), _sha(observed[1]), _now()),
    )
    connection.execute(
        "UPDATE committed_source_outbox SET state=?,attempt_count=attempt_count+1,updated_at=? WHERE id=?",
        (state, _now(), row["id"]),
    )
    return state


def character_journal_repairs(campaign_slug: str, *, connection=None):
    """Bounded manager-only journal identities, without operation payloads."""
    connection = connection or get_db()
    queries = (
        ("reconciliation", "SELECT character_slug,state FROM character_reconciliation_operations "
         "WHERE campaign_slug=? AND state IN ('prepared','repository_pending','conflict')"),
        ("deletion", "SELECT character_slug,state FROM character_deletion_operations "
         "WHERE campaign_slug=? AND state IN ('prepared','repository_pending','conflict')"),
        ("publication", "SELECT object_ref AS character_slug,state FROM committed_source_publications "
         "WHERE campaign_slug=? AND object_kind='character' AND state IN ('prepared','conflict')"),
    )
    result = []
    for kind, sql in queries:
        rows = connection.execute(sql + " LIMIT 1001", (campaign_slug,)).fetchall()
        if len(rows) > 1000:
            raise CommittedSourceConflict("Character journal inventory exceeds its bound.")
        result.extend({"character_slug": row["character_slug"],
                       "reason": "character_journal_requires_manager_repair",
                       "journal_kind": kind, "journal_state": row["state"]}
                      for row in rows)
    return result


def character_mirror_comparison(campaign_slug: str, character_slug: str, *,
                                connection=None, config_record=None):
    """Compare current mirror bytes with the committed pair, even with a journal."""
    connection = connection or get_db()
    from flask import current_app
    from .committed_publication import _mirror_bytes
    from .character_path_safety import resolve_character_definition_import_paths
    from .character_repository import load_campaign_character_config

    result = {"mirror_current_state": "proof_unavailable",
              "definition_mirror": "unavailable", "import_mirror": "unavailable"}
    try:
        source = current(campaign_slug, "character", character_slug,
                         connection=connection, allow_tombstone=True)
        if source is None or source["tombstone"]:
            result["mirror_current_state"] = "not_applicable"
            return result
        secondary = source["secondary_bytes"]
        if (not isinstance(secondary, bytes) or not secondary or len(secondary) > MAX_PAIR_BYTES
                or _sha(secondary) != source["secondary_sha256"]):
            return result
        result["mirror_current_state"] = "unavailable"
        config_record = config_record or load_campaign_character_config(
            current_app.config["CAMPAIGNS_DIR"], campaign_slug)
        if not config_record.characters_dir.resolve().is_relative_to(config_record.campaign_dir.resolve()):
            return result
        paths = resolve_character_definition_import_paths(config_record.characters_dir, character_slug)
        for label, path, expected in zip(
            ("definition", "import"), paths,
            (source["primary_sha256"], source["secondary_sha256"]),
        ):
            try:
                observed = _mirror_bytes(path)
            except (CommittedSourceConflict, OSError, ValueError, RuntimeError):
                result[label + "_mirror"] = "unavailable"
            else:
                result[label + "_mirror"] = (
                    "matching" if _sha(observed) == expected else
                    "missing" if observed is None else "modified"
                )
    except (CommittedSourceConflict, OSError, ValueError, TypeError, RuntimeError):
        return result
    states = {result["definition_mirror"], result["import_mirror"]}
    result["mirror_current_state"] = (
        "matching" if states == {"matching"} else
        "unavailable" if "unavailable" in states else
        "missing" if "missing" in states else "modified"
    )
    return result


@read_snapshot
def character_repairs(campaign_slug: str):
    """Manager-only actionable non-payload inventory for committed Characters."""
    connection = get_db()
    refs = {row[0] for row in connection.execute(
        "SELECT object_ref FROM committed_source_current WHERE campaign_slug=? AND object_kind='character'",
        (campaign_slug,),
    ).fetchall()}
    refs.update(row[0] for row in connection.execute(
        "SELECT object_ref FROM committed_source_admission WHERE campaign_slug=? AND object_kind='character'",
        (campaign_slug,),
    ).fetchall())
    journal_repairs = character_journal_repairs(campaign_slug, connection=connection)
    refs.update(row["character_slug"] for row in journal_repairs)
    journal_refs = {row["character_slug"] for row in journal_repairs}
    repairs = list(journal_repairs)
    from flask import current_app
    from .committed_publication import _mirror_bytes, _safe_mirror_path
    from .character_assets import resolve_character_portrait_asset_path
    from .character_assets import CHARACTER_PORTRAIT_MAX_BYTES
    from .character_path_safety import resolve_character_definition_import_paths
    from .character_repository import load_campaign_character_config
    config_record = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
    try:
        safe_root = config_record.characters_dir.resolve().is_relative_to(
            config_record.campaign_dir.resolve())
    except (OSError, RuntimeError, ValueError):
        safe_root = False
    if safe_root and config_record.characters_dir.is_dir():
        drafts = list(config_record.characters_dir.glob("*/definition.yaml"))
        drafts.extend(config_record.characters_dir.glob("*/import.yaml"))
        if len(drafts) > 1000:
            raise CommittedSourceConflict("Character mirror inventory exceeds its bound.")
        for draft in drafts:
            try:
                validate_character_slug(draft.parent.name)
            except ValueError:
                continue
            refs.add(draft.parent.name)
    for ref in sorted(refs):
        if ref in journal_refs:
            # A journal blocks exact_character. Report each journal first and
            # compare mirror bytes separately; never call the pair failure generic.
            if not safe_root:
                repairs.append({"character_slug": ref, "reason": "character_mirror_root_unsafe",
                                "mirror_current_state": "unavailable",
                                "definition_mirror": "unavailable", "import_mirror": "unavailable"})
                continue
            mirror_health = character_mirror_comparison(
                campaign_slug, ref, connection=connection, config_record=config_record)
            if mirror_health["mirror_current_state"] == "proof_unavailable":
                repairs.append({"character_slug": ref,
                                "reason": "committed_pair_or_portrait_invalid"})
            elif mirror_health["mirror_current_state"] in {"missing", "modified", "unavailable"}:
                repairs.append({"character_slug": ref,
                                "reason": "character_pair_mirror_missing_or_modified"
                                if mirror_health["mirror_current_state"] != "unavailable"
                                else "character_pair_mirror_unavailable",
                                **mirror_health})
            continue
        reason = None
        comparison = {}
        committed_proof_valid = False
        deletion_journal = connection.execute(
            "SELECT state FROM character_deletion_operations WHERE campaign_slug=? "
            "AND character_slug=? AND state IN ('prepared','repository_pending','conflict') "
            "ORDER BY updated_at DESC LIMIT 1",
            (campaign_slug, ref),
        ).fetchone()
        try:
            if deletion_journal is not None:
                comparison["deletion_journal_state"] = deletion_journal["state"]
                raise CommittedSourceConflict("Legacy Character deletion journal needs manager repair.")
            source = exact_character(campaign_slug, ref, connection=connection, allow_tombstone=True)
            if source is None:
                known = connection.execute(
                    "SELECT 1 FROM committed_source_current WHERE campaign_slug=? "
                    "AND object_kind='character' AND object_ref=? UNION ALL "
                    "SELECT 1 FROM committed_source_admission WHERE campaign_slug=? "
                    "AND object_kind='character' AND object_ref=? LIMIT 1",
                    (campaign_slug, ref, campaign_slug, ref),
                ).fetchone()
                reason = ("committed_pair_missing_or_blocked" if known is not None
                          else "unadmitted_file_only_draft")
            else:
                comparison["committed_revision"] = source["revision"]
                portrait = portrait_bytes(campaign_slug, ref, connection=connection) if not source["tombstone"] else None
                committed_proof_valid = True
                if not safe_root:
                    raise CommittedSourceConflict("Character mirror root is unsafe.")
                paths = resolve_character_definition_import_paths(config_record.characters_dir, ref)
                expected = (source["primary_sha256"], source["secondary_sha256"])
                observed = tuple(_mirror_bytes(path) for path in paths)
                actual = tuple(_sha(value) for value in observed)
                for label, value, digest in zip(("definition", "import"), observed, expected):
                    comparison[label + "_mirror"] = (
                        "matching" if _sha(value) == digest else
                        "missing" if value is None else "modified"
                    )
                if actual != expected:
                    reason = "character_pair_mirror_missing_or_modified"
                if portrait is not None:
                    _, asset_path = resolve_character_portrait_asset_path(
                        config_record.campaign_dir, ref, portrait[0],
                    )
                    asset_path = _safe_mirror_path(asset_path)
                    if (not asset_path.is_file()
                            or asset_path.stat().st_size > CHARACTER_PORTRAIT_MAX_BYTES
                            or _sha(asset_path.read_bytes()) != _sha(portrait[1])):
                        reason = "character_portrait_mirror_missing_or_modified"
                        comparison["portrait_mirror"] = (
                            "missing" if not asset_path.exists() else "modified"
                        )
                    else:
                        comparison["portrait_mirror"] = "matching"
                elif source["tombstone"]:
                    prior_image = connection.execute(
                        "SELECT asset_ref FROM committed_character_portraits WHERE campaign_slug=? "
                        "AND character_slug=? AND revision=?",
                        (campaign_slug, ref, source["revision"] - 1),
                    ).fetchone()
                    if prior_image is not None:
                        _, asset_path = resolve_character_portrait_asset_path(
                            config_record.campaign_dir, ref, prior_image["asset_ref"],
                        )
                        asset_path = _safe_mirror_path(asset_path)
                        if asset_path.exists():
                            reason = "character_portrait_mirror_not_retired"
        except (CommittedSourceConflict, OSError, ValueError, TypeError, UnicodeError, yaml.YAMLError):
            mirror_health = character_mirror_comparison(
                campaign_slug, ref, connection=connection, config_record=config_record)
            comparison.update(mirror_health)
            if deletion_journal is not None:
                reason = "legacy_deletion_journal_requires_manager_repair"
            elif committed_proof_valid:
                reason = ("character_mirror_root_unsafe" if not safe_root
                          else "character_pair_mirror_unavailable")
            else:
                reason = "committed_pair_or_portrait_invalid"
        mirror = connection.execute(
            "SELECT state FROM committed_source_mirrors WHERE campaign_slug=? "
            "AND object_kind='character' AND object_ref=?", (campaign_slug, ref),
        ).fetchone()
        if reason is None and mirror is not None and mirror["state"] in {"conflict", "missing", "unknown"}:
            reason = "character_pair_last_replay_conflict"
            comparison["mirror_last_replay_state"] = mirror["state"]
        if reason is not None:
            repairs.append({"character_slug": ref, "reason": reason, **comparison})
    return repairs
