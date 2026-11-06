"""Bounded custom spell profiles and same-entry preservation for prose edits.

Profiles describe source rules; they do not authorize casting, resolve a roll,
or adopt a spell into a character. Ordinary transport audits remain separate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from html import escape
import json
import re

from .db import get_db
from .rich_text import sanitize_rich_markdown
from .systems_mutations import systems_transaction
from .systems_service import SystemsPolicyValidationError, _systems_service_cache_clear


PROFILE_FIELDS = frozenset({"level", "school", "ritual", "casting_time", "range",
                            "components", "duration", "classes", "savingThrow", "spellAttack"})
_REQUIRED = PROFILE_FIELDS - {"ritual", "savingThrow", "spellAttack"}
_EDITOR_FIELDS = frozenset({"custom_campaign_slug", "provenance", "search_metadata",
                            "body_format", "body_markdown", "updated_by_user_id"})


def _fail(message):
    raise SystemsPolicyValidationError(message)


def _object(value, allowed, required=()):
    if type(value) is not dict or set(value) - set(allowed) or not set(required) <= set(value):
        _fail("Spell details contain missing or unsupported fields.")


def _text(value, limit=512):
    return (type(value) is str and 0 < len(value) <= limit and value == value.strip()
            and all(ord(char) >= 32 for char in value))


def _number(value, minimum=1, maximum=1000000):
    return type(value) is int and minimum <= value <= maximum


def _blocks(value, maximum=8, minimum=1):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _fail("Spell details need a bounded list of source declarations.")
    return value


def normalize_spell_profile(value):
    """None means preserve; an explicit profile is complete, closed and typed."""
    if value is None:
        return None
    _object(value, PROFILE_FIELDS, _REQUIRED)
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False)) > 16000:
            _fail("Spell details must stay under 16,000 characters.")
    except (TypeError, ValueError, RecursionError):
        _fail("Spell details must contain bounded JSON values.")
    if not _number(value["level"], 0, 9) or value["school"] not in tuple("ACDEVINT"):
        _fail("Choose a spell level from 0 to 9 and a supported school code.")
    if "ritual" in value and type(value["ritual"]) is not bool:
        _fail("Ritual status must be an explicit boolean.")
    for time in _blocks(value["casting_time"]):
        _object(time, {"number", "unit", "condition"}, {"number", "unit"})
        if (not _number(time["number"], maximum=10000)
                or time["unit"] not in ("action", "bonus", "reaction", "round", "minute", "hour")
                or "condition" in time and not _text(time["condition"], 2000)):
            _fail("Casting time needs a source amount, unit and optional condition.")
    distance = value["range"]
    _object(distance, {"type", "distance"}, {"type"})
    if distance["type"] == "point":
        amount = distance.get("distance")
        _object(amount, {"type", "amount"}, {"type"})
        if amount["type"] in ("feet", "miles"):
            if not _number(amount.get("amount")):
                _fail("A measured spell range needs a positive distance.")
        elif amount["type"] not in ("self", "touch", "sight", "unlimited") or "amount" in amount:
            _fail("Choose a supported point range.")
    elif distance["type"] not in ("self", "special") or "distance" in distance:
        _fail("Choose a point, self or special range; retain other geometry in the rules.")
    components = value["components"]
    _object(components, {"v", "s", "m"})
    if any(type(components[key]) is not bool for key in ("v", "s") if key in components):
        _fail("Verbal and somatic components must be explicit booleans.")
    if "m" in components:
        material = components["m"]
        if type(material) is str:
            if not _text(material, 2000):
                _fail("Supply a bounded material description.")
        else:
            _object(material, {"text", "cost", "consume"}, {"text"})
            if (not _text(material["text"], 2000)
                    or "cost" in material and not _number(material["cost"], 0, 100000000)
                    or "consume" in material and type(material["consume"]) is not bool):
                _fail("Material details need text, optional copper-piece cost and explicit consumption.")
    for duration in _blocks(value["duration"]):
        _object(duration, {"type", "duration", "concentration", "ends"}, {"type"})
        if duration["type"] == "timed":
            span = duration.get("duration")
            _object(span, {"type", "amount"}, {"type", "amount"})
            if span["type"] not in ("round", "minute", "hour", "day", "week", "year") or not _number(span["amount"]):
                _fail("Timed duration needs a source amount and unit.")
            if "concentration" in duration and type(duration["concentration"]) is not bool:
                _fail("Concentration must be an explicit boolean.")
            if "ends" in duration:
                _fail("Timed duration cannot include permanent ending conditions.")
        elif duration["type"] == "permanent":
            if set(duration) - {"type", "ends"}:
                _fail("Permanent duration accepts only its ending conditions.")
            if "ends" in duration and any(end not in ("dispel", "trigger") for end in _blocks(duration["ends"])):
                _fail("Choose supported permanent ending conditions.")
        elif duration["type"] not in ("instant", "special") or set(duration) != {"type"}:
            _fail("Choose an instantaneous, timed, permanent or special duration.")
    classes = value["classes"]
    _object(classes, {"fromClassList"}, {"fromClassList"})
    class_lists = {}
    for row in _blocks(classes["fromClassList"], 32, 0):
        _object(row, {"name", "source"}, {"name", "source"})
        if not _text(row["name"], 100) or not _text(row["source"], 80):
            _fail("Class lists need explicit class names and source identities.")
        names = class_lists.setdefault(row["source"].upper(), [])
        if any(name.casefold() == row["name"].casefold() for name in names):
            _fail("Spell class-list entries must be distinct.")
        names.append(row["name"])
    for key, choices in (("savingThrow", ("str", "dex", "con", "int", "wis", "cha")),
                         ("spellAttack", ("M", "R", "O"))):
        if key in value:
            values = _blocks(value[key], 6, 0)
            if any(type(item) is not str or item not in choices for item in values) or len(set(values)) != len(values):
                _fail("Spell roll declarations must use distinct supported source values.")
    return {**deepcopy(value), "class_lists": class_lists}


def parse_spell_profile_form(raw):
    if not str(raw or "").strip():
        return None
    if len(raw) > 16000:
        _fail("Spell details must stay under 16,000 characters.")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        _fail("Spell details must be a JSON object.")
    normalize_spell_profile(value)
    return value


def spell_profile_for_editor(entry):
    if getattr(entry, "entry_type", None) != "spell":
        return None
    metadata = dict(entry.metadata or {})
    profile = {key: deepcopy(metadata[key]) for key in PROFILE_FIELDS if key in metadata}
    return profile or None


def structured_spell_metadata(metadata):
    return type(metadata) is dict and bool(set(metadata) - _EDITOR_FIELDS)


def render_spell_summary(metadata):
    """Render supported source fields, without duplicating them in authored rules."""
    profile = {key: metadata[key] for key in PROFILE_FIELDS if key in metadata}
    try:
        normalize_spell_profile(profile)
    except SystemsPolicyValidationError:
        # Preserve older profiles outside this editor's vocabulary without guessing.
        return ""
    schools = dict(zip("ACDEVINT", ("Abjuration", "Conjuration", "Divination", "Enchantment",
                                  "Evocation", "Illusion", "Necromancy", "Transmutation")))
    def quantity(number, unit):
        label = "bonus action" if unit == "bonus" else unit
        return f"{number} {label}" + ("s" if number != 1 else "")
    times = [quantity(row["number"], row["unit"]) +
             (", " + row["condition"] if row.get("condition") else "")
             for row in profile["casting_time"]]
    distance = profile["range"]
    if distance["type"] == "point":
        distance = distance["distance"]
    range_label = (f'{distance["amount"]} {distance["type"]}' if "amount" in distance
                   else distance["type"].capitalize())
    components = profile["components"]
    component_labels = [label.upper() for label in ("v", "s") if components.get(label)]
    if "m" in components:
        material = components["m"]
        text = material if isinstance(material, str) else material["text"]
        if isinstance(material, dict) and "cost" in material:
            cost = material["cost"]
            gold = f"{cost // 100}.{cost % 100:02d}".rstrip("0").rstrip(".")
            text += "; cost: " + gold + " gp"
        if isinstance(material, dict) and material.get("consume") is True:
            text += "; consumed"
        component_labels.append("M (" + text + ")")
    durations = []
    for row in profile["duration"]:
        if row["type"] == "timed":
            span = row["duration"]
            label = quantity(span["amount"], span["type"])
            if row.get("concentration"):
                label = "Concentration, up to " + label
        elif row["type"] == "permanent":
            label = "Permanent"
            if row.get("ends"):
                label += " (until " + " or ".join(
                    "dispelled" if end == "dispel" else "triggered" for end in row["ends"]) + ")"
        else:
            label = "Instantaneous" if row["type"] == "instant" else "Special"
        durations.append(label)
    pairs = [("Level", "Cantrip" if profile["level"] == 0 else str(profile["level"])),
             ("School", schools[profile["school"]]),
             ("Casting Time", " or ".join(times)), ("Range", range_label),
             ("Components", ", ".join(component_labels) or "None"),
             ("Duration", " or ".join(durations)),
             ("Classes", ", ".join(row["name"] for row in profile["classes"]["fromClassList"]))]
    if profile.get("ritual"):
        pairs.append(("Ritual", "Yes"))
    return '<section class="systems-entry-summary">' + "".join(
        f'<p><strong>{escape(label)}:</strong> <span>{escape(value)}</span></p>'
        for label, value in pairs if value) + "</section>"


def spell_narrative(metadata, body, main, higher):
    """Project authored text at save time; do not parse or infer game rules."""
    old_higher = body.get("entries_higher_level")
    if higher is None:
        if old_higher and "spell_higher_level_markdown" not in metadata:
            _fail("Supply the existing higher-level rules explicitly before editing this legacy structured spell.")
        higher = metadata.get("spell_higher_level_markdown", "")
    if type(higher) is not str or len(higher) > 30000:
        _fail("Higher-level rules must be text under 30,000 characters.")
    if old_higher and "spell_higher_level_markdown" not in metadata and not higher.strip():
        _fail("Separate the existing higher-level rules before editing this legacy structured spell.")
    higher = sanitize_rich_markdown(higher).strip()
    metadata["spell_higher_level_markdown"] = higher
    body.pop("markdown", None)
    body["entries"] = [main]
    body["entries_higher_level"] = [higher] if higher else []
    return main + ("\n\n### At Higher Levels\n\n" + higher if higher else "")


@dataclass
class _SpellWrite:
    service: object
    connection: object
    campaign_slug: str
    library: object
    source_id: str
    previous: object
    previous_override: object
    retain_visibility: bool
    prepared_item_page_ref: str = ""
    prepared_item_page: object = None
    active: bool = True


def spell_write_library(context, service, campaign_slug, source, entry_key, slug):
    if (type(context) is not _SpellWrite or not context.active
            or context.service is not service or context.connection is not get_db()
            or not context.connection.in_transaction or context.campaign_slug != campaign_slug
            or context.library.library_slug != source.library_slug or context.source_id != source.source_id
            or context.previous.entry_key != entry_key or context.previous.slug != slug):
        raise RuntimeError("Spell save context is no longer current or owned.")
    return context.library


def save_custom_spell_edit(service, campaign_slug, entry_slug, *, expected_entry, **values):
    """Preserve current server fields under the same entry/override write owner."""
    target_type = re.sub(r"[^a-z0-9_]+", "", str(values.get("entry_type") or "").strip().lower())
    # Published-page preparation can seed its mirror; finish it before ownership.
    page_ref = str(values.get("source_page_ref") or "").strip()
    page = None
    if page_ref:
        if target_type != "item" or len(page_ref) > 500:
            _fail("Only item entries can link a bounded published item page reference.")
        page = service._get_campaign_item_page_record(campaign_slug, page_ref)
        if page is None:
            _fail("Choose a valid published item page before saving item mechanics.")
    with systems_transaction():
        library_slug = service.get_campaign_library_slug(campaign_slug)
        library = service.store.get_library(library_slug)
        previous = service.store.get_entry_by_slug(library_slug, entry_slug)
        if (library is None or previous is None or previous.entry_type != "spell"
                or any(getattr(previous, key) != getattr(expected_entry, key)
                       for key in ("id", "library_slug", "source_id", "entry_key", "entry_type", "slug"))):
            _fail("That custom spell identity changed; reload before editing.")
        if target_type != "spell" and structured_spell_metadata(dict(previous.metadata or {})):
            _fail("Structured spell rules cannot be moved to another entry type by editing prose.")
        source = service.store.get_source(library_slug, previous.source_id)
        if (source is None or source.license_class != "custom_campaign"
                or dict(previous.metadata or {}).get("custom_campaign_slug", "") not in ("", campaign_slug)):
            _fail("Choose a spell owned by this campaign.")
        override = service.store.get_campaign_entry_override(campaign_slug, previous.entry_key)
        if override is not None and override.library_slug != library_slug:
            _fail("That spell override belongs to another library.")
        retain = not str(values.get("visibility") or "").strip()
        if retain:
            values["visibility"] = ((override.visibility_override if override is not None else None)
                                    or ("dm" if previous.dm_heavy else "players"))
        context = _SpellWrite(service, get_db(), campaign_slug, library, source.source_id,
                              previous, override, retain, page_ref, page)
        try:
            entry = service._save_custom_campaign_entry(
                campaign_slug, source=source, entry_key=previous.entry_key, slug=previous.slug,
                is_enabled_override=override.is_enabled_override if override is not None else None,
                _spell_write=context, **values)
        finally:
            context.active = False
    _systems_service_cache_clear()
    return entry
