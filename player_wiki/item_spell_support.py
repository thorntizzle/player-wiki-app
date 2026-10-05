"""Pure, item-scoped interpretation of fixed spell-support leaves.

The parser retains the outer unlock level separately from inner ``_`` wrappers.
Callers choose whether diagnostics reject a new import or quarantine a legacy
read. No database, catalog, or importer state is consulted here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
from typing import Any


@dataclass(frozen=True)
class SpellSupportRecord:
    availability: int | None
    invalid: bool
    source_row_id: str
    source_row_kind: str
    source_row_title: str
    source_ability_key: str
    source_mode: str
    spell_list_class_name: str
    grant_source_label: str
    spell: str
    spell_key: str
    spell_selector: str
    access_type: str
    access_uses: int
    access_reset_on: str
    mark: str
    always_prepared: bool
    ritual: bool
    bonus_known: bool
    details: tuple[tuple[str, str], ...]
    origin: str
    field_path: str


@dataclass(frozen=True)
class SpellSupportDiagnostic:
    code: str
    field_path: str
    origin: str


@dataclass(frozen=True)
class SpellSupportParseResult:
    records: tuple[SpellSupportRecord, ...]
    diagnostics: tuple[SpellSupportDiagnostic, ...]
    # (block index, effective ID, kind, title), even without a spell leaf.
    source_declarations: tuple[tuple[int, str, str, str], ...] = ()


_SEMANTIC_KEYS = {
    "_", "spell", "value", "title", "slug", "spell_source", "source",
    "spell_source_row_id", "spell_source_row_kind", "spell_source_row_title",
    "spell_source_ability_key", "spell_source_mode",
    "spell_source_spell_list_class_name", "grant_source_label",
    "spell_access_type", "access_type", "spell_access_uses", "access_uses",
    "spell_access_reset_on", "access_reset_on", "mark", "bonus_known",
    "is_bonus_known", "ritual", "is_ritual", "is_always_prepared",
    "always_prepared", "isAlwaysPrepared", "alwaysPrepared", "prepared",
    "category", "kind",
}
_ABILITY_NAMES = {
    "strength": "str", "dexterity": "dex", "constitution": "con",
    "intelligence": "int", "wisdom": "wis", "charisma": "cha",
}


def _lookup(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s/-]", "", value).strip().lower()
    return "/".join(
        re.sub(r"\s+", "-", part.strip())
        for part in cleaned.split("/") if part.strip()
    )


def _spell_selector(value: Any) -> str:
    clean = str(value or "").strip()
    match = re.fullmatch(r"\{@spell ([^}]+)\}", clean)
    if match:
        clean = match.group(1)
    return clean.strip()


def _spell_name(value: Any) -> str:
    return _spell_selector(value).split("|", 1)[0].split("#", 1)[0].replace("_", " ").strip()


def _spell_key(selector: str) -> str:
    for delimiter in ("|", "#"):
        if delimiter in selector:
            title, source_id = selector.split(delimiter, 1)
            if delimiter == "|":
                source_id = source_id.split("|", 1)[0]
            return f"{_lookup(_spell_name(title))}|{source_id.strip().casefold()}"
    return _lookup(_spell_name(selector))


def _availability(key: Any) -> int | None | bool:
    if str(key).strip() == "_":
        return None
    if isinstance(key, int):
        return key
    match = re.search(r"(\d+)", str(key or "").strip())
    return int(match.group(1)) if match else False


def _field_diagnostics(payload: dict[str, Any], path: str) -> list[SpellSupportDiagnostic]:
    """Inspect raw aliases before precedence can discard a bad declaration."""
    source_fields = (("spell_source", payload.get("spell_source")),
                     ("source", payload.get("source")))
    def nonblank(value: Any) -> bool:
        return value is not None and str(value).strip() != ""

    values: dict[str, list[tuple[str, str]]] = {}
    issues: list[SpellSupportDiagnostic] = []
    for prefix, source in source_fields:
        if prefix in payload and nonblank(source) and not isinstance(source, dict):
            issues.append(SpellSupportDiagnostic("invalid_source", f"{path}.{prefix}", ""))
        if not isinstance(source, dict):
            continue
        for key, field in (("row_id", "id"), ("id", "id"),
                           ("row_kind", "kind"), ("kind", "kind"),
                           ("title", "title"), ("label", "title"),
                           ("ability_key", "ability"), ("spellcasting_ability_key", "ability"),
                           ("mode", "mode"), ("spell_list_class_name", "list"),
                           ("class_name", "list")):
            if key in source and nonblank(source[key]):
                values.setdefault(field, []).append((f"{path}.{prefix}.{key}", str(source[key]).strip()))
    for key, field in (("spell_source_row_id", "id"), ("spell_source_row_title", "title"),
                       ("spell_source_row_kind", "kind"), ("spell_source_ability_key", "ability"),
                       ("spell_source_mode", "mode"), ("spell_access_type", "access"),
                       ("access_type", "access"),
                       ("spell_source_spell_list_class_name", "list")):
        if key in payload and nonblank(payload[key]):
            values.setdefault(field, []).append((f"{path}.{key}", str(payload[key]).strip()))
    # A top-level block ``kind`` is a flat source-kind alias. Nested wrappers
    # and spell leaves use ``kind`` as a grant category.
    block = re.fullmatch(r"spell_support\[\d+\]", path) is not None
    if block and "kind" in payload and nonblank(payload["kind"]):
        values.setdefault("kind", []).append((f"{path}.kind", str(payload["kind"]).strip()))
    if not block:
        for key in ("kind", "category"):
            if key in payload and nonblank(payload[key]):
                values.setdefault("grant", []).append((f"{path}.{key}", str(payload[key]).strip()))
    allowed = {"id": None, "title": None, "list": None,
               "kind": {"item", "source"}, "ability": {"str", "dex", "con", "int", "wis", "cha"},
               "mode": set(), "access": {"at_will", "free_cast"}, "grant": {"prepared"}}
    for field, aliases in values.items():
        normalized: set[str] = set()
        for field_path, raw in aliases:
            value = (_ABILITY_NAMES.get(_lookup(raw), _lookup(raw)) if field == "ability"
                     else raw if field == "id" else raw.casefold())
            if allowed[field] is not None and value not in allowed[field]:
                issues.append(SpellSupportDiagnostic(f"invalid_{field}", field_path, ""))
            else:
                normalized.add(value)
        if len(normalized) > 1:
            issues.append(SpellSupportDiagnostic(f"conflicting_{field}_aliases", aliases[-1][0], ""))
    return issues


def _source_fields(raw: Any, inherited: dict[str, Any] | None = None) -> dict[str, Any]:
    result = dict(inherited or {})
    payload = raw if isinstance(raw, dict) else {}
    source = payload.get("spell_source", payload.get("source"))
    source = source if isinstance(source, dict) else {}
    row_id = str(payload.get("spell_source_row_id") or source.get("row_id") or source.get("id") or "").strip()
    title = str(payload.get("spell_source_row_title") or source.get("title") or source.get("label") or "").strip()
    if not row_id and title:
        row_id = f"spell-source:{_slugify(title)}"
    label = str(payload.get("grant_source_label") or source.get("grant_source_label") or title or "").strip()
    if row_id:
        result["source_row_id"] = row_id
        result["source_row_kind"] = str(
            payload.get("spell_source_row_kind") or source.get("row_kind") or source.get("kind")
            or (payload.get("kind") if not any(key in payload for key in ("spell", "value", "slug"))
                and str(payload.get("kind") or "").strip().casefold() in {"item", "source"} else "")
            or "source"
        ).strip().casefold() or "source"
        if title:
            result["source_row_title"] = title
        ability = _ABILITY_NAMES.get(_lookup(
            payload.get("spell_source_ability_key") or source.get("ability_key")
            or source.get("spellcasting_ability_key") or ""
        ), _lookup(
            payload.get("spell_source_ability_key") or source.get("ability_key")
            or source.get("spellcasting_ability_key") or ""
        ))
        if ability in {"str", "dex", "con", "int", "wis", "cha"}:
            result["source_ability_key"] = ability
        mode = str(payload.get("spell_source_mode") or source.get("mode") or "").strip()
        if mode:
            result["source_mode"] = mode
        list_class = str(
            payload.get("spell_source_spell_list_class_name") or source.get("spell_list_class_name")
            or source.get("class_name") or ""
        ).strip()
        if list_class:
            result["spell_list_class_name"] = list_class
    if label:
        result["grant_source_label"] = label
    access_type = str(payload.get("spell_access_type") or payload.get("access_type") or "").strip().casefold()
    if access_type in {"at_will", "free_cast"}:
        result["access_type"] = access_type
        result["access_uses"] = 0
        result["access_reset_on"] = ""
        if access_type == "free_cast":
            try:
                uses = int(payload.get("spell_access_uses", payload.get("access_uses")) or 0)
            except (ValueError, TypeError):
                uses = 0
            result["access_uses"] = max(uses, 0)
            result["access_reset_on"] = str(
                payload.get("spell_access_reset_on") or payload.get("access_reset_on") or ""
            ).strip()
    return result


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        return _lookup(value) in {"1", "true", "yes", "always", "prepared"}
    return False


def _record(raw: Any, support: dict[str, Any], availability: int | None,
            invalid: bool, origin: str, path: str) -> SpellSupportRecord | None:
    payload = raw if isinstance(raw, dict) else {}
    selector = _spell_selector(
        payload.get("spell") or payload.get("value") or payload.get("title")
        or payload.get("slug") or ""
    ) if isinstance(raw, dict) else _spell_selector(raw)
    spell = _spell_name(selector)
    if not spell:
        return None
    effective = _source_fields(payload, support)
    mark = str(payload.get("mark") or "").strip() if isinstance(raw, dict) else "Granted"
    bonus_known = bool(payload.get("bonus_known") or payload.get("is_bonus_known"))
    if not bonus_known and _lookup(mark) in {"known", "cantrip"}:
        bonus_known, mark = True, ""
    prepared = _lookup(payload.get("category") or payload.get("kind")) == "prepared" or any(
        _flag(payload.get(key)) for key in (
            "is_always_prepared", "always_prepared", "isAlwaysPrepared", "alwaysPrepared", "prepared"
        )
    )
    details = tuple(sorted(
        (str(key), json.dumps(value, sort_keys=True, ensure_ascii=True, default=str))
        for key, value in payload.items() if key not in _SEMANTIC_KEYS
    ))
    return SpellSupportRecord(
        availability=availability,
        invalid=invalid,
        source_row_id=effective.get("source_row_id", ""),
        source_row_kind=effective.get("source_row_kind", ""),
        source_row_title=effective.get("source_row_title", ""),
        source_ability_key=effective.get("source_ability_key", ""),
        source_mode=effective.get("source_mode", ""),
        spell_list_class_name=effective.get("spell_list_class_name", ""),
        grant_source_label=effective.get("grant_source_label", ""),
        spell=spell,
        spell_key=_spell_key(selector),
        spell_selector=selector,
        access_type=effective.get("access_type", ""),
        access_uses=effective.get("access_uses", 0),
        access_reset_on=effective.get("access_reset_on", ""),
        mark=mark,
        always_prepared=prepared,
        ritual=bool(payload.get("ritual") or payload.get("is_ritual")),
        bonus_known=bonus_known,
        details=details,
        origin=origin,
        field_path=path,
    )


def parse_item_spell_support(
    blocks: Any, *, strict: bool = False, origin: str = ""
) -> SpellSupportParseResult:
    """Return supported fixed leaves and privacy-safe structural diagnostics.

    ``strict`` is the admission policy hint; diagnostics are returned in both
    modes so tolerant callers can show review and withhold ambiguous grants.
    """
    records: list[SpellSupportRecord] = []
    diagnostics: list[SpellSupportDiagnostic] = []
    source_declarations: list[tuple[int, str, str, str]] = []

    def issue(code: str, path: str) -> None:
        diagnostics.append(SpellSupportDiagnostic(code, path, origin))

    def walk(value: Any, support: dict[str, Any], availability: int | None,
             invalid: bool, path: str, block_index: int) -> None:
        if isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, support, availability, invalid, f"{path}[{index}]", block_index)
        elif isinstance(value, dict):
            diagnostics.extend(replace(diagnostic, origin=origin)
                               for diagnostic in _field_diagnostics(value, path))
            effective = _source_fields(value, support)
            source_id = effective.get("source_row_id", "")
            if source_id:
                source_declarations.append((
                    block_index, source_id, effective.get("source_row_kind", "source"),
                    effective.get("source_row_title", ""),
                ))
            if "_" in value:
                walk(value["_"], effective, availability, invalid, f"{path}._", block_index)
            record = _record(value, support, availability, invalid, origin, path)
            if record:
                records.append(record)
            elif "_" not in value and value:
                issue("unsupported_leaf", path)
        elif isinstance(value, str):
            record = _record(value, support, availability, invalid, origin, path)
            if record:
                records.append(record)
        elif value not in (None, "", [], {}):
            issue("unsupported_leaf", path)

    if not isinstance(blocks, list):
        if blocks not in (None, "", [], {}):
            issue("malformed_blocks", "spell_support")
        return SpellSupportParseResult(tuple(records), tuple(diagnostics), ())
    for index, block in enumerate(blocks):
        path = f"spell_support[{index}]"
        if not isinstance(block, dict):
            issue("malformed_block", path)
            continue
        diagnostics.extend(replace(diagnostic, origin=origin)
                           for diagnostic in _field_diagnostics(block, path))
        block_support = _source_fields(block)
        block_source_id = block_support.get("source_row_id", "")
        if block_source_id:
            source_declarations.append((
                index, block_source_id, block_support.get("source_row_kind", "source"),
                block_support.get("source_row_title", ""),
            ))
        has_grants = "grants" in block
        branch = "grants" if has_grants else "fixed"
        raw = block.get(branch)
        if has_grants and "fixed" in block and block.get("grants") not in (None, "", [], {}) and block.get("fixed") not in (None, "", [], {}):
            issue("shadowed_fixed", path)
        if raw in (None, "", [], {}):
            continue
        if not isinstance(raw, dict):
            issue("malformed_outer_map", f"{path}.{branch}")
            walk(raw, _source_fields(block), None, True, f"{path}.{branch}", index)
            continue
        support = _source_fields(block)
        for unlock_index, (key, value) in enumerate(raw.items()):
            unlock = _availability(key)
            leaf_path = f"{path}.{branch}[{unlock_index}]"
            if unlock is False:
                if value not in (None, "", [], {}):
                    issue("unknown_unlock", leaf_path)
                    walk(value, support, None, True, leaf_path, index)
                continue
            walk(value, support, unlock, False, leaf_path, index)
    return SpellSupportParseResult(
        tuple(records), tuple(diagnostics), tuple(dict.fromkeys(source_declarations))
    )
