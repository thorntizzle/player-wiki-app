"""Source-qualified spell properties, separate from learning and casting grants.

Item metadata admits only a wielded, exact-spell range replacement. Native
feature properties are inferred from one finite literal learned-cantrip clause
after that exact source/leaf has qualified. Neither path creates an entitlement.
All results are effective views; saved definitions and play state are untouched.
"""
from copy import deepcopy
import json
import re


FIELD = "spell_property_modifiers"


def normalize_item_spell_properties(value):
    from .character_spell_grants import publication_identity
    if type(value) is not list or not 1 <= len(value) <= 16:
        raise ValueError("Spell property modifiers require a bounded nonempty list.")
    result, seen = [], set()
    for raw in value:
        required = {"effect_id", "spell_ref", "condition", "range_feet"}
        if (type(raw) is not dict or not required <= set(raw)
                or set(raw) - required - {"legacy_source_row_id"}
                or type(raw["effect_id"]) is not str
                or not re.fullmatch(r"[a-z0-9][a-z0-9:_-]{0,119}", raw["effect_id"])
                or raw["effect_id"] in seen or raw["condition"] != "wielded"
                or type(raw["range_feet"]) is not int or not 1 <= raw["range_feet"] <= 5280):
            raise ValueError("Unsupported spell property identity, condition or range.")
        if type(raw["spell_ref"]) is not dict:
            raise ValueError("Spell properties require a plain publication reference.")
        ref = publication_identity(raw["spell_ref"])
        if ref["entry_type"] != "spell":
            raise ValueError("A spell property requires an exact spell publication.")
        legacy = raw.get("legacy_source_row_id")
        if "legacy_source_row_id" in raw and (type(legacy) is not str
                or not legacy.startswith("spell-source:item:") or len(legacy) > 200
                or legacy != legacy.strip() or any(ord(c) < 32 for c in legacy)):
            raise ValueError("Legacy item spell representation requires an exact source row.")
        seen.add(raw["effect_id"])
        result.append({**deepcopy(raw), "spell_ref": ref})
    return result


def _paragraphs(body):
    """Only actual source entries; titles and unrelated metadata are not prose."""
    stack, texts, visited = [(body, 0)], [], 0
    while stack:
        value, depth = stack.pop()
        visited += 1
        if visited > 512 or depth > 24:
            return [], False
        if type(value) is str:
            if len(value) > 20000 or len(texts) >= 128:
                return [], False
            texts.append(value)
        elif type(value) is list:
            if len(value) > 128 or len(stack) + len(value) > 512:
                return [], False
            stack.extend((child, depth + 1) for child in reversed(value))
        elif type(value) is dict:
            stack.append((value.get("entries", []), depth + 1))
        else:
            return [], False
    return texts, True


def inferred_cantrip_properties(entry, spell, class_name):
    """Recognize a complete literal clause, never the feature title or raw row.

    Callers bind this to a supported current native leaf and its exact spell.
    Unsupported property prose remains a diagnostic, not a lost spell grant.
    """
    pattern = re.compile(
        r"(?:In addition, )?you learn (?:the )?\{@spell (?P<spell>[^}]+)\} cantrip, "
        r"which (?:doesn't|does not) count against the number of (?P<class>[a-z ]+) cantrips you know\. "
        r"For you, it has a range of (?P<feet>[1-9][0-9]{0,3}) feet, "
        r"and you can cast it as a bonus action\.", re.IGNORECASE)
    matches, relevant = [], False
    paragraphs, complete = _paragraphs(entry.body)
    if not complete:
        return None, ["unmodeled_cantrip_property_source_shape"]
    for paragraph in paragraphs:
        text = " ".join(paragraph.split())
        if "{@spell " not in text:
            continue
        relevant = relevant or ("cantrip" in text.lower() and
            ("range" in text.lower() or "bonus action" in text.lower()))
        match = pattern.fullmatch(text)
        if match is None:
            continue
        selector = match["spell"].split("|")
        source_id = selector[1].strip() if len(selector) == 2 else "PHB"
        if (len(selector) > 2 or not source_id or not selector[0].strip()
                or selector[0].strip().casefold() != spell.title.casefold()
                or source_id.casefold() != spell.source_id.casefold()
                or match["class"].casefold() != class_name.casefold()
                or spell.metadata.get("level") != 0 or int(match["feet"]) > 5280):
            continue
        matches.append({"range_feet": int(match["feet"]), "bonus_action": True})
    if len(matches) == 1:
        return matches[0], []
    return None, (["unmodeled_or_ambiguous_cantrip_properties"] if relevant else [])


def item_spell_property_facts(*, raw_definition, item_entries, native_view,
                              native_custody_confirmed=False):
    """Shared pure classification for the effective reader and real normalizer."""
    from .character_spell_grants import publication_identity, canonical_digest
    warnings, rules, history = [], [], []
    raw_spells = list(raw_definition.spellcasting.get("spells", []))
    raw_sources = list(raw_definition.spellcasting.get("source_rows", []))
    for item in item_entries:
        try:
            effects = normalize_item_spell_properties(item[FIELD])
        except (ValueError, TypeError, KeyError):
            warnings.append({"code": "spell_properties_invalid", "message":
                "An item spell property declaration is unsupported; its modifier is unavailable."})
            continue
        for effect in effects:
            legacy = effect.get("legacy_source_row_id")
            if legacy:
                if (item.get("legacy_entitlement_cleared") is not True
                        or legacy in item.get("current_source_rows", [])):
                    warnings.append({"code": "spell_modifier_entitlement_conflict", "message":
                        "Modifier reclassification needs an explicit current empty grant choice and no competing current source owner."})
                    continue
            origin = {"kind": "item", "instance_id": item["item_id"], "label": item["item_name"],
                "source_ref": deepcopy(item["source_ref"]),
                "source_basis_digest": item["source_basis_digest"],
                "effect_id": effect["effect_id"], "condition": "wielded",
                "condition_known": item["condition_known"], "active": item["wielded"],
                "spell_ref": effect["spell_ref"], "range_feet": effect["range_feet"]}
            rules.append(origin)
            if legacy:
                matching = [row for row in raw_spells if type(row) is dict
                    and row.get("spell_source_row_id") == legacy]
                try:
                    if (len(matching) != 1 or not matching[0].get("id")
                            or matching[0].get("class_row_id")
                            or matching[0].get("spell_source_row_kind") != "item"
                            or publication_identity(matching[0].get("systems_ref")) != effect["spell_ref"]):
                        raise ValueError("Ambiguous legacy spell owner.")
                    source_rows = [row for row in raw_sources if isinstance(row, dict)
                                   and row.get("source_row_id") == legacy]
                    if len(source_rows) != 1 or source_rows[0].get("source_row_kind") != "item":
                        raise ValueError("Historical item source row is unavailable or ambiguous.")
                    edges = [edge for edge in (native_view.migration_edges if native_view is not None else ())
                             if edge.get("old_spell_id") == matching[0]["id"]]
                    if (not native_custody_confirmed or not any(grant.get("status") == "VERIFIED"
                            for grant in (native_view.occurrences if native_view is not None else ()))
                            or len(edges) != 1 or edges[0]["grant_ids"]
                            or edges[0]["unresolved_observation_digest"] != canonical_digest(matching[0])):
                        raise ValueError("Historical observation custody is unavailable.")
                    prior_owner_ids = matching[0].get("item_owner_ids")
                    if prior_owner_ids is not None and prior_owner_ids != [item["item_id"]]:
                        raise ValueError("Conflicting historical item owner.")
                    owners = [candidate for candidate in item_entries
                        if any(rule.get("legacy_source_row_id") == legacy
                               for rule in candidate.get(FIELD, []) if type(rule) is dict)]
                    if len(owners) != 1:
                        raise ValueError("Ambiguous legacy item source.")
                except (ValueError, TypeError, KeyError):
                    warnings.append({"code": "spell_modifier_legacy_ambiguous", "message":
                        "A prior item spell representation has no unique exact owner; it remains visible for review."})
                    continue
                if not any(entry["source_row_id"] == legacy for entry in history):
                    history.append({"reason": "modifier_not_entitlement", "item_id": item["item_id"],
                        "source_ref": deepcopy(item["source_ref"]),
                        "source_row_id": legacy, "source_row": deepcopy(source_rows[0]), "observation": deepcopy(matching[0])})
    return rules, history, warnings


def preserve_modifier_history(spellcasting, raw_definition, history):
    """Keep exact non-entitling observations through ordinary normalization.

    History is supplied by the bound current SourceAuthority classifier. A
    collision is a refusal, never permission to overwrite another new owner.
    """
    if not history:
        return spellcasting
    from .character_spell_grants import publication_identity, canonical_digest
    result = deepcopy(spellcasting)
    spells = list(result.get("spells", []))
    sources = list(result.get("source_rows", []))
    original = {row.get("id"): index for index, row in enumerate(raw_definition.spellcasting.get("spells", []))
                if isinstance(row, dict)}
    for entry in history:
        raw = entry["observation"]
        matches = [row for row in spells if row.get("id") == raw["id"]]
        if len(matches) > 1 or any(row.get("class_row_id")
                or row.get("spell_grant_origin") == "item_effect"
                or ("item_owner_ids" in row and row["item_owner_ids"] != [entry["item_id"]])
                or row.get("spell_source_row_id") != entry["source_row_id"]
                or publication_identity(row.get("systems_ref")) != publication_identity(raw["systems_ref"])
                for row in matches):
            raise ValueError("A derived spell collides with retained item history.")
        spells = [row for row in spells if row.get("id") != raw["id"]]
        spells.insert(min(original[raw["id"]], len(spells)), deepcopy(raw))
        matching_sources = [row for row in sources if row.get("source_row_id") == entry["source_row_id"]]
        derived_only = {"spell_attack_bonus", "spell_save_dc", "spell_metric_notes"}
        expected_behavior = {key: value for key, value in entry["source_row"].items() if key not in derived_only}
        if len(matching_sources) > 1 or any(
                canonical_digest({key: value for key, value in row.items() if key not in derived_only}) != canonical_digest(expected_behavior)
                for row in matching_sources):
            raise ValueError("A derived source row collides with retained item history.")
        sources = [row for row in sources if row.get("source_row_id") != entry["source_row_id"]]
        sources.append(deepcopy(entry["source_row"]))
    result["spells"], result["source_rows"] = spells, sources
    return result


def project_spell_properties(spellcasting, *, raw_definition, bases, item_entries, native_view,
                             native_custody_confirmed=False):
    """Consume only facts supplied by the current owned SourceAuthority.

    No source resolution, authority construction, extra spell_status calls or
    mutation of raw inputs occurs here. Equal range replacements are idempotent;
    unequal replacements withhold that property and retain all diagnostics.
    """
    from .character_spell_grants import publication_identity, canonical_digest
    result = deepcopy(spellcasting)
    rules, history, warnings = item_spell_property_facts(raw_definition=raw_definition,
        item_entries=item_entries, native_view=native_view, native_custody_confirmed=native_custody_confirmed)
    grants = tuple(native_view.occurrences) if native_view is not None else ()
    for grant in grants:
        if grant.get("status") != "VERIFIED":
            continue
        for diagnostic in grant.get("spell_property_diagnostics", []):
            warnings.append({"code": diagnostic, "message":
                "A qualified feature has spell property prose outside the supported contract; the spell grant is retained."})
        effect = grant.get("spell_properties")
        if effect:
            rules.append({"kind": "feature", "instance_id": grant["owner_id"],
                "label": grant.get("spell_property_label", "Class feature"),
                "grant_id": grant["id"], "class_row_id": grant["class_row_id"],
                "source_ref": deepcopy(grant["source_ref"]),
                "source_basis_digest": grant["source_basis_digest"],
                "spell_ref": deepcopy(grant["spell_ref"]), "effect_id": grant["leaf_id"],
                "condition": "qualified_feature", "condition_known": True, "active": True,
                **effect})

    canonical = {identity: json.loads(encoded) for identity, encoded in bases}
    class_rows, counts = [], {}
    for raw in result.get("spells", []):
        if type(raw) is dict:
            counts[raw.get("id")] = counts.get(raw.get("id"), 0) + 1
    for row in result.get("spells", []):
        if type(row) is not dict:
            continue
        legacy_id = row.get("spell_source_row_id") or row.get("authority_original_source_row_id")
        try:
            ref = publication_identity(row.get("systems_ref"))
        except ValueError:
            class_rows.append(row)
            continue
        obsolete = [entry for entry in history if entry["source_row_id"] == legacy_id
                    and publication_identity(entry["observation"]["systems_ref"]) == ref]
        if obsolete:
            # Effective reclassification is explicit and retained below. This
            # never edits/deletes the raw observation or its audit/custody.
            continue
        if (row.get("authority_status") != "VERIFIED" or counts[row.get("id")] != 1
                or not row.get("class_row_id") or row.get("spell_source_row_id")):
            class_rows.append(row)
            continue
        base = canonical.get(row.get("id"))
        origin_grants = [grant for grant in grants if grant.get("status") == "VERIFIED"
            and grant.get("class_row_id") == row.get("class_row_id")
            and publication_identity(grant["spell_ref"]) == ref
            and any(origin.get("id") == grant["id"] for origin in row.get("grant_origins", []))]
        if base is None and origin_grants:
            displays = [grant.get("spell_display") for grant in origin_grants]
            if all(display == displays[0] for display in displays) and displays[0]:
                base = {"spell_ref": ref, **displays[0]}
        if base is None or publication_identity(base["spell_ref"]) != ref:
            warnings.append({"code": "spell_property_base_unavailable", "message":
                "Current canonical spell properties are unavailable; imported modifiers are not authority."})
            row.update(range="--", casting_time="--", spell_property_origins=[], casting_time_options=[])
            class_rows.append(row)
            continue
        row["spell_property_base"] = {key: base[key] for key in ("range", "casting_time")}
        row.update(range=base["range"], casting_time=base["casting_time"])
        applicable = [rule for rule in rules if publication_identity(rule["spell_ref"]) == ref
            and (rule["kind"] == "item" or any(grant["id"] == rule["grant_id"] for grant in origin_grants))]
        row["spell_property_origins"] = deepcopy(applicable)
        active = [rule for rule in applicable if rule["active"] and rule["condition_known"]]
        ranges = {rule["range_feet"] for rule in active}
        if len(ranges) == 1:
            row["range"] = f"{next(iter(ranges))} feet"
        elif len(ranges) > 1:
            row["range"] = "--"
            warnings.append({"code": "spell_range_conflict", "message":
                "Current spell range replacements disagree; no replacement takes precedence."})
        options = [base["casting_time"]]
        if any(rule.get("bonus_action") is True for rule in active):
            options.append("1 bonus action")
        row["casting_time_options"] = list(dict.fromkeys(options))
        row["casting_time"] = " or ".join(row["casting_time_options"])
        class_rows.append(row)
    result["spells"] = class_rows
    removed = {entry["source_row_id"] for entry in history}
    used = {row.get("spell_source_row_id") for row in class_rows}
    result["source_rows"] = [row for row in result.get("source_rows", [])
        if row.get("source_row_id") not in removed or row.get("source_row_id") in used]
    result["spell_modifier_legacy_observations"] = history
    result["spell_property_diagnostics"] = deepcopy(warnings)
    return result, warnings
