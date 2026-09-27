"""Source observations and pure refresh planning; this module has no DB owner."""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .repository import build_page_from_content, extract_obsidian_targets, parse_frontmatter


class StaleCampaignRefreshPlan(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason if reason in {"source", "rows", "protection", "sync", "config"} else "source"
        super().__init__("Campaign refresh inputs changed; a fresh refresh is required.")


class CampaignRefreshTransactionError(RuntimeError):
    """Admission refusal, before this owner has any transaction to clean up."""


def normalize_page_ref(page_ref: str) -> str:
    normalized = str(page_ref or "").strip().replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("A relative page reference is required.")
    pure_path = PurePosixPath(normalized)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError("Relative page references must stay within the campaign content tree.")
    if pure_path.suffix and pure_path.suffix.lower() != ".md":
        raise ValueError("Only .md pages are supported.")
    if pure_path.suffix.lower() == ".md":
        pure_path = pure_path.with_suffix("")
    return pure_path.as_posix()


def build_page_payload(campaign_slug: str, page_ref: str, *, metadata: dict[str, Any],
                       body_markdown: str, updated_at: str) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ValueError("Page metadata must be an object.")
    if not isinstance(body_markdown, str):
        raise ValueError("body_markdown must be a string.")
    normalized_page_ref = normalize_page_ref(page_ref)
    normalized_metadata = dict(metadata)
    normalized_body = body_markdown.strip()
    page = build_page_from_content(
        source_path=f"db://{campaign_slug}/{normalized_page_ref}",
        default_slug=normalized_page_ref, metadata=normalized_metadata,
        body_markdown=normalized_body, raw_link_targets=extract_obsidian_targets(normalized_body),
        content_loaded=True,
    )
    searchable_text = " ".join(part for part in (
        page.title, page.subsection, page.summary, normalized_body, " ".join(page.aliases),
    ) if part).lower()
    return dict(page_ref=normalized_page_ref, route_slug=page.route_slug, title=page.title,
                section=page.section, subsection=page.subsection, page_type=page.page_type,
                display_order=page.display_order, published=int(page.published),
                aliases_json=json.dumps(list(page.aliases), sort_keys=True), summary=page.summary,
                image_path=page.image_path, image_alt=page.image_alt, image_caption=page.image_caption,
                reveal_after_session=page.reveal_after_session, source_ref=page.source_ref,
                metadata_json=json.dumps(normalized_metadata, sort_keys=True),
                raw_link_targets_json=json.dumps(list(page.raw_link_targets), sort_keys=True),
                searchable_text=searchable_text, body_markdown=normalized_body, updated_at=updated_at)


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode), value.st_mtime_ns, value.st_size)


@dataclass(frozen=True, slots=True)
class PathWitness:
    path: Path
    resolved: Path
    lexical_identity: tuple[int, ...] | None
    target_identity: tuple[int, ...] | None
    metadata: bool = True


def observe_path(path: Path, *, metadata: bool = True) -> PathWitness:
    path = Path(os.path.abspath(path))
    # Only genuine absence is an empty input. Permission/stat failures propagate.
    try:
        lexical = _stat_identity(path.lstat())
    except FileNotFoundError:
        lexical = None
    try:
        target = _stat_identity(path.stat())
    except FileNotFoundError:
        target = None
    if not metadata:
        lexical = lexical[:3] if lexical is not None else None
        target = target[:3] if target is not None else None
    return PathWitness(path, path.resolve(), lexical, target, metadata)


def ancestor_witnesses(path: Path) -> tuple[PathWitness, ...]:
    path = Path(os.path.abspath(path))
    entries = tuple(reversed((path, *path.parents)))
    observations = tuple(observe_path(entry) for entry in entries)
    # Ancestors witness resolution/object replacement, rather than unrelated
    # siblings' edits. A missing root also witnesses its nearest existing parent
    # with metadata so creation/removal cannot be acknowledged as stable absence.
    metadata_paths = {path}
    if observations[-1].target_identity is None:
        for observation in reversed(observations[:-1]):
            if observation.target_identity is not None:
                metadata_paths.add(observation.path)
                break
    return tuple(observation if observation.path in metadata_paths else PathWitness(
        observation.path, observation.resolved,
        observation.lexical_identity[:3] if observation.lexical_identity is not None else None,
        observation.target_identity[:3] if observation.target_identity is not None else None, False,
    ) for observation in observations)


def validate_witnesses(witnesses: Iterable[PathWitness], *, reason: str = "source") -> None:
    for witness in witnesses:
        if observe_path(witness.path, metadata=witness.metadata) != witness:
            raise StaleCampaignRefreshPlan(reason)


@dataclass(frozen=True, slots=True)
class CampaignSourceSnapshot:
    content_dir: Path
    discovered_refs: tuple[str, ...]
    witnesses: tuple[PathWitness, ...]
    texts: tuple[tuple[str, str], ...] = ()
    source_paths: tuple[tuple[str, Path], ...] = ()


def discover_source_snapshot(content_dir: Path) -> CampaignSourceSnapshot:
    """Metadata only. Retain all directories, including empty and alias targets."""
    content_dir = Path(os.path.abspath(content_dir))
    witnesses = list(ancestor_witnesses(content_dir))
    root = witnesses[-1]
    source_paths: list[Path] = []
    if root.target_identity is not None:
        if root.target_identity[2] != stat.S_IFDIR:
            raise ValueError("Campaign content root must be a directory.")

        def fail(error: OSError) -> None:
            raise error

        for directory, dirs, files in os.walk(content_dir, onerror=fail, followlinks=False):
            dirs.sort()
            directory_path = Path(directory)
            witnesses.append(observe_path(directory_path))
            for name in sorted(dirs):
                witnesses.append(observe_path(directory_path / name))
                if os.path.normcase(name).endswith(os.path.normcase(".md")):
                    source_paths.append(directory_path / name)
            for name in sorted(files):
                if not os.path.normcase(name).endswith(os.path.normcase(".md")):
                    continue
                path = directory_path / name
                witness = observe_path(path)
                if witness.target_identity is None:
                    raise StaleCampaignRefreshPlan("source")
                witnesses.append(witness)
                source_paths.append(path)
    elif root.lexical_identity is not None:
        # A dangling root alias is not a stably absent configured root.
        raise ValueError("Campaign content root target is unavailable.")
    paths = tuple((path.relative_to(content_dir).with_suffix("").as_posix(), path)
                  for path in sorted(source_paths))
    snapshot = CampaignSourceSnapshot(content_dir, tuple(ref for ref, _ in paths), tuple(witnesses), source_paths=paths)
    validate_witnesses(snapshot.witnesses)
    return snapshot


def capture_source_snapshot(content_dir: Path, *, protected_page_refs: Iterable[str]) -> CampaignSourceSnapshot:
    snapshot = discover_source_snapshot(content_dir)
    protected = frozenset(protected_page_refs)
    texts = []
    for ref, path in snapshot.source_paths:
        if ref in protected or normalize_page_ref(ref) in protected:
            continue
        # The discovery witness brackets the read; final validation checks all
        # files and directories again after every read, before parsing begins.
        texts.append((ref, path.read_text(encoding="utf-8")))
    validate_witnesses(snapshot.witnesses)
    return CampaignSourceSnapshot(snapshot.content_dir, snapshot.discovered_refs, snapshot.witnesses, tuple(texts), snapshot.source_paths)


RowIdentity = tuple[tuple[tuple[str, Any], ...], ...]
ProtectionIdentity = tuple[tuple[str, ...], ...]


def row_identity(rows: Iterable[Mapping[str, Any]]) -> RowIdentity:
    return tuple(tuple(sorted(dict(row).items())) for row in sorted(rows, key=lambda row: row["page_ref"]))


@dataclass(frozen=True, slots=True)
class CampaignRefreshPlan:
    campaign_slug: str
    source: CampaignSourceSnapshot
    rows: RowIdentity
    protection: ProtectionIdentity
    payloads: tuple[tuple[tuple[str, Any], ...], ...]
    changes: tuple[str, ...]
    deletions: tuple[str, ...]
    sync_identity: tuple[tuple[str, Any], ...] | None = None


def diff_page_payloads(payloads: Iterable[Mapping[str, Any]], rows: Iterable[Mapping[str, Any]],
                       discovered_refs: Iterable[str], protected_refs: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    existing = {row["page_ref"]: dict(row) for row in rows}
    original_refs = frozenset(existing)
    occupancy = {row["route_slug"]: row["page_ref"] for row in existing.values()}
    changes: list[str] = []
    seen: set[str] = set()
    # Preserve sorted upsert-before-delete collision order, including releases.
    for payload in payloads:
        ref, route = payload["page_ref"], payload["route_slug"]
        if ref in seen:
            raise ValueError("Duplicate wiki page reference.")
        seen.add(ref)
        if route in occupancy and occupancy[route] != ref:
            raise ValueError("That wiki page slug is already in use. Choose a different slug.")
        previous = existing.get(ref)
        if previous is None or any(previous[field] != value for field, value in payload.items() if field != "updated_at"):
            changes.append(ref)
        if previous is not None:
            occupancy.pop(previous["route_slug"], None)
        occupancy[route] = ref
        existing[ref] = dict(payload)
    deletions = tuple(sorted(original_refs - set(discovered_refs) - set(protected_refs)))
    return tuple(changes), deletions


def plan_campaign_refresh(campaign_slug: str, source_snapshot: CampaignSourceSnapshot,
                          row_snapshot: Iterable[Mapping[str, Any]],
                          protection_snapshot: ProtectionIdentity) -> CampaignRefreshPlan:
    rows = row_identity(row_snapshot)
    protected = frozenset(row[3] for row in protection_snapshot)
    payloads = []
    for ref, text in source_snapshot.texts:
        if ref in protected or normalize_page_ref(ref) in protected:
            continue
        metadata, body = parse_frontmatter(text)
        payloads.append(build_page_payload(campaign_slug, ref, metadata=metadata, body_markdown=body, updated_at=""))
    changes, deletions = diff_page_payloads(payloads, (dict(row) for row in rows),
                                           source_snapshot.discovered_refs, (row[3] for row in protection_snapshot))
    return CampaignRefreshPlan(campaign_slug, source_snapshot, rows, protection_snapshot,
                               tuple(tuple(payload.items()) for payload in payloads), changes, deletions)
