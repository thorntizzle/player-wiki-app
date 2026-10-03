"""Atomic Character definition authority for activated committed-source mode.

The SQLite generation is the success boundary. Files are independently
recoverable mirrors and are never consulted to decide a Character write.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path, PurePath
from uuid import uuid4

import yaml

from .character_importer import render_character_yaml
from .character_models import CharacterDefinition, CharacterImportMetadata, CharacterRecord
from .character_path_safety import validate_character_slug
from .character_store import CharacterStateConflictError, CharacterStateUnavailableError
from .committed_publication import CommittedSourceConflict, _reserve, config, current, read_snapshot
from .committed_source_store import _now, _record_status
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
        return ("race", "species")
    if field_kind == "feature":
        return _FEATURE_TYPES if source_kind != "page" else ("feature", "feat")
    if field_kind == "item":
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


def _create_source_links(definition: CharacterDefinition, initial_state: dict):
    """Enumerate typed exact claims in the canonical pair and prepared state."""
    links: set[CreateSourceLink] = set()
    pending = [(definition.to_dict(), ("definition",), 0), (initial_state, ("initial_state",), 0)]
    visited = 0
    while pending:
        value, path, depth = pending.pop()
        visited += 1
        if visited > 10000 or depth > 24:
            raise CommittedSourceConflict("Character source links exceed their preparation bound.")
        if isinstance(value, dict):
            if _claim(value.get("systems_ref")) and _claim(value.get("page_ref")):
                raise CommittedSourceConflict(f"Character source row at {_link_owner(path)} has conflicting links.")
            for field, child in value.items():
                if path == ("definition", "source") and field == "source_authorizations":
                    # Private numeric markers carry page_ref as evidence, not as
                    # a Character source claim. Their audit and basis are checked
                    # separately; retained feature/page links remain below.
                    continue
                child_path = (*path, field)
                child_owner = _link_owner(child_path)
                if field in _EXACT_LINK_FIELDS and _claim(child):
                    if isinstance(child, dict):
                        visited += 1
                        if visited > 10000 or depth + 1 > 24:
                            raise CommittedSourceConflict("Character source links exceed their preparation bound.")
                    kind = _link_kind(path, field, normalize_system_code(definition.system))
                    if kind is None:
                        raise CommittedSourceConflict(f"Character source link at {child_owner} has no owning kind.")
                    if field.endswith("page_ref"):
                        links.add(_exact_page_link(child, child_owner, kind))
                    else:
                        links.add(_exact_systems_link(child, child_owner, kind))
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
    for link in pages:
        ref = link.identity
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
            "feature": {"Mechanics"}, "item": {"Items"},
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
            entry = connection.execute(
                f"SELECT entry_key,slug,source_id,entry_type,title,metadata_json FROM systems_entries "
                f"WHERE library_slug=? AND {column}=?", (library_slug, link.identity),
            ).fetchone()
            if entry is None:
                raise CommittedSourceConflict("Character Systems entry is missing.")
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
    prior_pages, prior_entries = _create_source_links(
        prior_record.definition, prior_record.state_record.state,
    )
    pages, entries = _create_source_links(definition, prepared_state)
    prior = set((*prior_pages, *prior_entries))
    changed = {link for link in (*pages, *entries) if link not in prior}
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
    return (pages, entries,
            tuple(link for link in pages if link in changed),
            tuple(link for link in entries if link in changed))


def _sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def exact_character(campaign_slug: str, character_slug: str, *, connection=None,
                    allow_tombstone: bool = False):
    """Return a digest-checked pair, never a file/cache or half a generation."""
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
        definition = yaml.safe_load(row["primary_bytes"].decode("utf-8"))
        imported = yaml.safe_load(secondary.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError, ValueError, OverflowError, RecursionError) as exc:
        raise CommittedSourceConflict("Committed Character pair is malformed; manager repair required.") from exc
    if (not isinstance(definition, dict) or not isinstance(imported, dict)
            or definition.get("campaign_slug") != campaign_slug
            or definition.get("character_slug") != character_slug
            or imported.get("campaign_slug") != campaign_slug
            or imported.get("character_slug") != character_slug
            or not isinstance(definition.get("name"), str) or not definition["name"].strip()
            or not isinstance(definition.get("status"), str) or not definition["status"].strip()
            or normalize_system_code(definition.get("system")) != row["system_code"]
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
    source = exact_character(campaign_slug, character_slug, connection=connection)
    if source is None:
        return None
    definition = yaml.safe_load(source["primary_bytes"].decode("utf-8"))
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
        definition_payload = yaml.safe_load(source["primary_bytes"].decode("utf-8"))
        if normalize_system_code(definition_payload.get("system")) != normalize_system_code(settings.get("system")):
            raise CommittedSourceConflict("Character system and committed campaign settings differ.")
        imported = yaml.safe_load(source["secondary_bytes"].decode("utf-8"))
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


def publish_update(coordinator, prior_record, definition, import_metadata, desired_state, *,
                   expected_revision, updated_by_user_id=None, operation_kind,
                   desired_asset_ref="", desired_asset_bytes=b"", audit_event_type=None,
                   audit_actor_user_id=None, audit_target_user_id=None, audit_metadata=None,
                   pending_numeric_authority=None, reviewed_source_proof=None,
                   trusted_spell_choice_authoring=False,
                   reconcile_reimport_state=False, reimport_source_authority=None):
    coordinator._validate_update_input(prior_record, definition, import_metadata,
                                       expected_revision=expected_revision,
                                       operation_kind=operation_kind)
    expected_config, _ = config(definition.campaign_slug)
    if reconcile_reimport_state and operation_kind not in {"markdown_import", "pdf_import"}:
        raise CharacterStateConflictError("Reimport reconciliation is unavailable for this update.")
    if pending_numeric_authority is not None and not pending_numeric_authority.claimed:
        raise CharacterStateConflictError("Native level-up proof was not claimed for publication.")
    from .character_equipment_activation import analyze_activation
    from .system_policy import is_dnd_5e_system
    if operation_kind != "activation_repair" and is_dnd_5e_system(definition.system):
        if analyze_activation(definition, desired_state)["blocked"]:
            raise CharacterStateConflictError("Equipment activation identity needs manager repair.")
    primary, secondary = _pair(definition, import_metadata)
    authority = (
        pending_numeric_authority.recheck(prior_record, definition, desired_state)
        if pending_numeric_authority is not None else
        coordinator.numeric_authority_provider(prior_record, definition)
        if coordinator.numeric_authority_provider is not None else None
    )
    if reviewed_source_proof is not None:
        authority = reviewed_source_proof.prospective_authority(
            authority, definition, prior_record.state_record.state,
        )
        reviewed_source_proof.recheck(prior_record, definition, desired_state,
                                      authority, expected_config["revision"])
    if reimport_source_authority is not None and (
        authority is None
        or authority.identity != reimport_source_authority.identity
        or authority.source_snapshot_digest != reimport_source_authority.source_snapshot_digest
    ):
        raise CharacterStateConflictError(
            "Character source changed before reimport; inspect the Character and retry."
        )
    prepared = coordinator.state_store.prepare_initial_state(
        definition, desired_state, source_authority=authority,
        previous_state=prior_record.state_record.state,
    )
    if (reviewed_source_proof is not None and reviewed_source_proof.page_feature_markers
            and prepared.validated_state != desired_state):
        raise CharacterStateConflictError("Page feature state changed during validation.")
    pages, entries, new_pages, new_entries = _update_source_claims(
        prior_record, definition, prepared.validated_state,
    )
    connection = get_db()
    owned_snapshot = not connection.in_transaction
    if owned_snapshot:
        connection.execute("BEGIN")
    try:
        expected_source = _create_source_proof(
            definition.campaign_slug, new_pages, new_entries, connection=connection,
        )
    finally:
        if owned_snapshot:
            connection.rollback()
    clean_audit = coordinator._prepare_update_audit(
        operation_kind=operation_kind, audit_event_type=audit_event_type,
        audit_actor_user_id=audit_actor_user_id, audit_target_user_id=audit_target_user_id,
        audit_metadata=audit_metadata,
    )
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
    _reserve(connection)
    try:
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
        locked_assignment = connection.execute(
            "SELECT id,user_id FROM character_assignments WHERE campaign_slug=? AND character_slug=?",
            (campaign, slug),
        ).fetchone()
        if (tuple(locked_assignment) if locked_assignment is not None else None) != expected_assignment:
            raise CharacterStateConflictError("Character assignment changed before publication.")
        refreshed = authority
        if authority is not None:
            refreshed = (
                pending_numeric_authority.recheck(prior_record, definition, desired_state)
                if pending_numeric_authority is not None else
                coordinator.numeric_authority_provider(prior_record, definition)
            )
            if reviewed_source_proof is not None:
                refreshed = reviewed_source_proof.prospective_authority(
                    refreshed, definition, prior_record.state_record.state,
                )
            if (refreshed is None or refreshed.identity != authority.identity
                    or refreshed.source_snapshot_digest != authority.source_snapshot_digest):
                raise CharacterStateConflictError("Character source proof changed before publication.")
            if reviewed_source_proof is not None:
                reviewed_source_proof.recheck(prior_record, definition, desired_state,
                                              refreshed, locked_config["revision"])
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
            and desired_state == prior_record.state_record.state
        )
        if not preserve_exact_state and prepared.validated_state != prior_record.state_record.state:
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
            coordinator.auth_store.insert_audit_event(
                event_type=clean_audit[0], actor_user_id=clean_audit[1],
                target_user_id=clean_audit[2], campaign_slug=campaign,
                character_slug=slug, metadata=json.loads(clean_audit[3]), commit=False,
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
        state = coordinator.state_store.get_state(campaign, slug)
        if state is None:
            raise CharacterStateUnavailableError("Committed Character state disappeared before publication.")
        result = CharacterRecord(definition, import_metadata, state, committed_revision=number)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
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
