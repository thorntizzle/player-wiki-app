from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class NpcResourceCounterSeed:
    resource_key: str
    label: str
    current_value: int
    max_value: int
    reset_label: str
    source_label: str
    reset_kind: str = "source"
    recharge_threshold: int | None = None


@dataclass(frozen=True, slots=True)
class NpcResourceNoteSeed:
    label: str
    note: str
    source_label: str


TAG_PATTERN = re.compile(r"\{@[a-zA-Z0-9_-]+\s+([^}|]+)(?:\|[^}]*)?\}")
MARKDOWN_DECORATION_PATTERN = re.compile(r"[*_`#>\[\]]+")
DAILY_LIST_PATTERN = re.compile(
    r"(?P<max>\d+)\s*/\s*day(?P<each>\s+each)?\s*:\s*(?P<items>[^.;\n]+)",
    re.IGNORECASE,
)
NAMED_DAILY_PATTERN = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 '\-,]{1,90}?)\s*\((?P<max>\d+)\s*/\s*day\)",
    re.IGNORECASE,
)
EXPLICIT_COUNTER_PATTERN = re.compile(
    r"^\s*(?:[-*]\s*)?(?P<label>[A-Za-z][^:|/]{1,80}?)\s*[:|-]\s*(?P<current>\d+)\s*/\s*(?P<max>\d+)\b",
    re.IGNORECASE,
)
AT_WILL_PATTERN = re.compile(r"\bat\s+will\s*:\s*(?P<items>[^.;\n]+)", re.IGNORECASE)
RECHARGE_NOTE_PATTERN = re.compile(r"\(\s*(?P<note>recharge[^)]*)\)", re.IGNORECASE)
RECHARGE_TAG_NOTE_PATTERN = re.compile(r"\{@(?P<note>recharge(?:\s+[^}]*)?)\}", re.IGNORECASE)
STRICT_RECHARGE_SUFFIX_PATTERN = re.compile(
    r"^(?P<label>.+?)\s*\(recharge (?P<low>[2-6])"
    r"(?P<range>[ \t]*[-\u2013\u2014][ \t]*6)?\)\s*$",
    re.IGNORECASE,
)
STRICT_SYSTEMS_RECHARGE_TAG_PATTERN = re.compile(
    r"^(?P<label>.+?)\s*\{@recharge(?: (?P<threshold>[2-6]))?\}\s*$",
    re.IGNORECASE,
)
SYSTEMS_ABILITY_COLLECTIONS = frozenset(
    {
        "traits",
        "actions",
        "bonus_actions",
        "reactions",
        "legendary_actions",
        "mythic_actions",
    }
)


@dataclass(frozen=True, slots=True)
class _RechargeRule:
    label: str
    threshold: int
    note: str


def build_npc_resource_seeds_from_markdown(
    markdown_text: str,
    *,
    source_label: str,
) -> tuple[list[NpcResourceCounterSeed], list[NpcResourceNoteSeed]]:
    lines = str(markdown_text or "").replace("\r\n", "\n").splitlines()
    return _build_npc_resource_seeds(
        lines,
        source_label=source_label,
        recharge_rules=tuple(
            rule
            for raw_line in lines
            if _is_atx_heading(raw_line)
            for rule in (_parse_strict_recharge_rule(_atx_heading_text(raw_line)),)
            if rule is not None
        ),
    )


def build_npc_resource_seeds_from_systems_entry(
    entry: Any,
    *,
    source_label: str | None = None,
) -> tuple[list[NpcResourceCounterSeed], list[NpcResourceNoteSeed]]:
    body = getattr(entry, "body", {}) or {}
    lines = list(_iter_structured_text(body))
    label = source_label or f"Systems {str(getattr(entry, 'source_id', '') or '').strip()}".strip()
    recharge_rules = tuple(
        rule
        for ability_name in _iter_systems_ability_names(body)
        for rule in (_parse_strict_recharge_rule(ability_name, allow_systems_tag=True),)
        if rule is not None
    )
    return _build_npc_resource_seeds(
        lines,
        source_label=label or "Systems",
        recharge_rules=recharge_rules,
    )


def build_npc_resource_seeds_from_text_lines(
    lines: Iterable[str],
    *,
    source_label: str,
) -> tuple[list[NpcResourceCounterSeed], list[NpcResourceNoteSeed]]:
    return _build_npc_resource_seeds(lines, source_label=source_label)


def _build_npc_resource_seeds(
    lines: Iterable[str],
    *,
    source_label: str,
    recharge_rules: tuple[_RechargeRule, ...] = (),
) -> tuple[list[NpcResourceCounterSeed], list[NpcResourceNoteSeed]]:
    counters: list[NpcResourceCounterSeed] = []
    notes: list[NpcResourceNoteSeed] = []
    seen_counter_keys: set[str] = set()
    seen_notes: set[tuple[str, str]] = set()

    for raw_line in lines:
        raw_text = str(raw_line or "")
        line = _normalize_text(raw_line)
        if not line:
            continue

        explicit_match = EXPLICIT_COUNTER_PATTERN.search(line)
        if explicit_match is not None:
            label = _clean_label(explicit_match.group("label"))
            max_value = int(explicit_match.group("max"))
            current_value = min(int(explicit_match.group("current")), max_value)
            _append_counter(
                counters,
                seen_counter_keys,
                label=label,
                current_value=current_value,
                max_value=max_value,
                reset_label="Per source",
                source_label=source_label,
                reset_kind="source",
            )

        for match in NAMED_DAILY_PATTERN.finditer(line):
            label = _clean_label(match.group("label"))
            max_value = int(match.group("max"))
            _append_counter(
                counters,
                seen_counter_keys,
                label=label,
                current_value=max_value,
                max_value=max_value,
                reset_label="Per day",
                source_label=source_label,
                reset_kind="daily",
            )

        for match in DAILY_LIST_PATTERN.finditer(line):
            max_value = int(match.group("max"))
            for label in _split_limited_use_items(match.group("items")):
                _append_counter(
                    counters,
                    seen_counter_keys,
                    label=label,
                    current_value=max_value,
                    max_value=max_value,
                    reset_label="Per day",
                    source_label=source_label,
                    reset_kind="daily",
                )

        for match in AT_WILL_PATTERN.finditer(line):
            note = ", ".join(_split_limited_use_items(match.group("items"))) or _clean_label(match.group("items"))
            if note:
                _append_note(
                    notes,
                    seen_notes,
                    label="At-will spellcasting",
                    note=note,
                    source_label=source_label,
                )

        for label, note in _iter_recharge_notes(raw_text):
            _append_note(
                notes,
                seen_notes,
                label=label,
                note=note,
                source_label=source_label,
            )

    _resolve_recharge_rules(
        counters,
        notes,
        seen_counter_keys,
        recharge_rules,
        source_label=source_label,
    )
    return counters, notes


def _append_counter(
    counters: list[NpcResourceCounterSeed],
    seen_keys: set[str],
    *,
    label: str,
    current_value: int,
    max_value: int,
    reset_label: str,
    source_label: str,
    reset_kind: str,
    recharge_threshold: int | None = None,
) -> None:
    clean_label = _clean_label(label)
    if not clean_label or max_value < 1:
        return
    key = _resource_key(clean_label)
    if key in seen_keys:
        return
    seen_keys.add(key)
    counters.append(
        NpcResourceCounterSeed(
            resource_key=key,
            label=clean_label,
            current_value=max(0, min(current_value, max_value)),
            max_value=max_value,
            reset_label=reset_label,
            source_label=source_label,
            reset_kind=reset_kind,
            recharge_threshold=recharge_threshold,
        )
    )


def _resolve_recharge_rules(
    counters: list[NpcResourceCounterSeed],
    notes: list[NpcResourceNoteSeed],
    seen_counter_keys: set[str],
    rules: tuple[_RechargeRule, ...],
    *,
    source_label: str,
) -> None:
    unique_rules: dict[tuple[str, int], _RechargeRule] = {}
    for rule in rules:
        key = _resource_key(rule.label)
        unique_rules.setdefault((key, rule.threshold), rule)

    rules_by_key: dict[str, list[_RechargeRule]] = {}
    for (key, _threshold), rule in unique_rules.items():
        rules_by_key.setdefault(key, []).append(rule)

    consumed_notes: set[tuple[str, str]] = set()
    for key, keyed_rules in rules_by_key.items():
        thresholds = {rule.threshold for rule in keyed_rules}
        if key in seen_counter_keys or len(thresholds) != 1:
            continue
        rule = keyed_rules[0]
        _append_counter(
            counters,
            seen_counter_keys,
            label=rule.label,
            current_value=1,
            max_value=1,
            reset_label=rule.note,
            source_label=source_label,
            reset_kind="recharge_d6",
            recharge_threshold=rule.threshold,
        )
        consumed_notes.add((_clean_label(rule.label).lower(), _clean_label(rule.note).lower()))

    if consumed_notes:
        notes[:] = [
            note
            for note in notes
            if (note.label.lower(), note.note.lower()) not in consumed_notes
        ]


def _append_note(
    notes: list[NpcResourceNoteSeed],
    seen_notes: set[tuple[str, str]],
    *,
    label: str,
    note: str,
    source_label: str,
) -> None:
    clean_label = _clean_label(label)
    clean_note = _clean_label(note)
    if not clean_label or not clean_note:
        return
    note_key = (clean_label.lower(), clean_note.lower())
    if note_key in seen_notes:
        return
    seen_notes.add(note_key)
    notes.append(
        NpcResourceNoteSeed(
            label=clean_label,
            note=clean_note,
            source_label=source_label,
        )
    )


def _iter_structured_text(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        if str(value).strip():
            yield str(value)
        return
    if isinstance(value, dict):
        name = str(value.get("name") or "")
        entries = value.get("entries", value.get("entry"))
        if name.strip():
            yield name
        yield from _iter_structured_text(entries)
        for key, nested_value in value.items():
            if key in {"name", "entries", "entry"}:
                continue
            if key in SYSTEMS_ABILITY_COLLECTIONS:
                yield from _iter_structured_text(nested_value)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_structured_text(item)
        return


def _iter_systems_ability_names(value: Any) -> Iterable[str]:
    if not isinstance(value, dict):
        return
    for key, nested_value in value.items():
        if key not in SYSTEMS_ABILITY_COLLECTIONS:
            continue
        items = nested_value if isinstance(nested_value, list) else [nested_value]
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            if name.strip():
                yield name
            yield from _iter_systems_ability_names(item)


def _is_atx_heading(value: str) -> bool:
    return re.match(r"^ {0,3}#{1,6}(?:[ \t]+|$)", str(value or "")) is not None


def _atx_heading_text(value: str) -> str:
    heading = re.sub(r"^ {0,3}#{1,6}[ \t]+", "", str(value or ""), count=1)
    return re.sub(r"[ \t]+#+[ \t]*$", "", heading).strip()


def _parse_strict_recharge_rule(
    value: str,
    *,
    allow_systems_tag: bool = False,
) -> _RechargeRule | None:
    text = str(value or "").strip()
    literal_match = STRICT_RECHARGE_SUFFIX_PATTERN.fullmatch(text)
    if literal_match is not None:
        threshold = int(literal_match.group("low"))
        has_range = literal_match.group("range") is not None
        if (threshold == 6 and has_range) or (threshold != 6 and not has_range):
            return None
        label = _clean_label(literal_match.group("label"))
        if label:
            return _RechargeRule(
                label=label,
                threshold=threshold,
                note=_canonical_recharge_label(threshold),
            )
    if allow_systems_tag:
        tag_match = STRICT_SYSTEMS_RECHARGE_TAG_PATTERN.fullmatch(text)
        if tag_match is not None:
            threshold = int(tag_match.group("threshold") or 6)
            label = _clean_label(tag_match.group("label"))
            if label:
                return _RechargeRule(
                    label=label,
                    threshold=threshold,
                    note=_canonical_recharge_label(threshold),
                )
    return None


def _iter_recharge_notes(value: str) -> Iterable[tuple[str, str]]:
    text = str(value or "")
    for match in RECHARGE_NOTE_PATTERN.finditer(text):
        label = _label_before_match(text, match.start()) or "Recharge"
        strict = _parse_strict_recharge_rule(text)
        note = (
            strict.note
            if strict is not None and strict.label.lower() == label.lower()
            else _display_recharge_note(match.group("note"))
        )
        yield label, note
    for match in RECHARGE_TAG_NOTE_PATTERN.finditer(text):
        label = _label_before_match(text, match.start()) or "Recharge"
        strict = _parse_strict_recharge_rule(text, allow_systems_tag=True)
        note = (
            strict.note
            if strict is not None and strict.label.lower() == label.lower()
            else _display_recharge_note(match.group("note"))
        )
        yield label, note


def _display_recharge_note(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if not cleaned:
        return "Recharge"
    return cleaned[0].upper() + cleaned[1:]


def _canonical_recharge_label(threshold: int) -> str:
    return "Recharge 6" if threshold == 6 else f"Recharge {threshold}\u20136"


def _normalize_text(value: str) -> str:
    normalized = str(value or "").replace("\r\n", "\n").replace(chr(8211), "-").replace(chr(8212), "-")
    normalized = TAG_PATTERN.sub(r"\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _split_limited_use_items(value: str) -> list[str]:
    cleaned = _normalize_text(value)
    cleaned = re.sub(r"\band\b", ",", cleaned, flags=re.IGNORECASE)
    items = []
    for item in re.split(r",|;", cleaned):
        label = _clean_label(item)
        if label:
            items.append(label)
    return items


def _clean_label(value: str) -> str:
    cleaned = MARKDOWN_DECORATION_PATTERN.sub("", _normalize_text(value))
    cleaned = re.sub(r"^\s*[-:|.]+\s*", "", cleaned)
    cleaned = re.sub(r"\s*[-:|.]+\s*$", "", cleaned)
    return cleaned.strip()


def _label_before_match(line: str, match_start: int) -> str:
    prefix = line[:match_start].strip()
    prefix = re.split(r"[.;]", prefix)[-1].strip()
    return _clean_label(prefix)


def _resource_key(label: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return normalized[:80] or "resource"
