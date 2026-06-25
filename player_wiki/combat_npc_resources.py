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
RECHARGE_PATTERN = re.compile(r"\((?P<note>recharge\s+\d+\s*[-+]\s*\d+)\)", re.IGNORECASE)


def build_npc_resource_seeds_from_markdown(
    markdown_text: str,
    *,
    source_label: str,
) -> tuple[list[NpcResourceCounterSeed], list[NpcResourceNoteSeed]]:
    return build_npc_resource_seeds_from_text_lines(
        str(markdown_text or "").replace("\r\n", "\n").splitlines(),
        source_label=source_label,
    )


def build_npc_resource_seeds_from_systems_entry(
    entry: Any,
    *,
    source_label: str | None = None,
) -> tuple[list[NpcResourceCounterSeed], list[NpcResourceNoteSeed]]:
    lines = list(_iter_structured_text(getattr(entry, "body", {}) or {}))
    label = source_label or f"Systems {str(getattr(entry, 'source_id', '') or '').strip()}".strip()
    return build_npc_resource_seeds_from_text_lines(lines, source_label=label or "Systems")


def build_npc_resource_seeds_from_text_lines(
    lines: Iterable[str],
    *,
    source_label: str,
) -> tuple[list[NpcResourceCounterSeed], list[NpcResourceNoteSeed]]:
    counters: list[NpcResourceCounterSeed] = []
    notes: list[NpcResourceNoteSeed] = []
    seen_counter_keys: set[str] = set()
    seen_notes: set[tuple[str, str]] = set()

    for raw_line in lines:
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

        for match in RECHARGE_PATTERN.finditer(line):
            label = _label_before_match(line, match.start()) or "Recharge"
            _append_note(
                notes,
                seen_notes,
                label=label,
                note=_clean_label(match.group("note")).title(),
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
        )
    )


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
        clean = _normalize_text(value)
        if clean:
            yield clean
        return
    if isinstance(value, dict):
        name = _normalize_text(str(value.get("name") or ""))
        entries = value.get("entries", value.get("entry"))
        if name:
            yield name
        yield from _iter_structured_text(entries)
        for key, nested_value in value.items():
            if key in {"name", "entries", "entry"}:
                continue
            if key in {"traits", "actions", "bonus_actions", "reactions", "legendary_actions", "mythic_actions"}:
                yield from _iter_structured_text(nested_value)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_structured_text(item)
        return


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
