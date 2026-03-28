from __future__ import annotations

import argparse
import fnmatch
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .repository import normalize_lookup, parse_frontmatter, slugify

DRAFT_REVIEW_COMMENT = """<!--
IMPORTED DRAFT
This file was copied from the GM-side source wiki.
Review and redact it before promoting it into published player content.
-->
"""


class PublishError(Exception):
    pass


@dataclass(slots=True)
class PublishRule:
    source_prefix: str
    target_subdir: str
    section: str
    page_type: str
    preserve_subdirs: bool = False

    @property
    def normalized_prefix(self) -> str:
        return self.source_prefix.replace("\\", "/").strip("/")

    def matches(self, source_ref: str) -> bool:
        return source_ref == self.normalized_prefix or source_ref.startswith(
            f"{self.normalized_prefix}/"
        )


@dataclass(slots=True)
class CampaignPublishConfig:
    title: str
    slug: str
    campaign_dir: Path
    source_wiki_root: Path
    content_dir: Path
    draft_dir: Path
    current_session: int
    publish_ignore_globs: list[str]
    publish_rules: list[PublishRule]
    default_target_subdir: str
    default_section: str
    default_page_type: str


@dataclass(slots=True)
class SourceDocument:
    source_path: Path
    source_ref: str
    title: str
    aliases: list[str]
    summary: str
    body: str


@dataclass(slots=True)
class ImportPlan:
    destination_path: Path
    relative_output_ref: str
    metadata: dict[str, Any]
    body: str


def load_publish_config(project_root: Path, campaign_slug: str) -> CampaignPublishConfig:
    config_path = project_root / "campaigns" / campaign_slug / "campaign.yaml"
    if not config_path.exists():
        raise PublishError(f"Campaign config not found: {config_path}")

    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    campaign_dir = config_path.parent
    source_wiki_root = Path(raw_config.get("source_wiki_root", ""))
    if not source_wiki_root.exists():
        raise PublishError(f"Source wiki root does not exist: {source_wiki_root}")

    rules = [
        PublishRule(
            source_prefix=item["source_prefix"],
            target_subdir=item["target_subdir"],
            section=item["section"],
            page_type=item["type"],
            preserve_subdirs=bool(item.get("preserve_subdirs", False)),
        )
        for item in raw_config.get("publish_rules", [])
    ]

    return CampaignPublishConfig(
        title=raw_config["title"],
        slug=raw_config.get("slug", campaign_slug),
        campaign_dir=campaign_dir,
        source_wiki_root=source_wiki_root,
        content_dir=campaign_dir / raw_config.get("player_content_dir", "content"),
        draft_dir=campaign_dir / raw_config.get("draft_content_dir", "drafts"),
        current_session=int(raw_config.get("current_session", 0)),
        publish_ignore_globs=list(raw_config.get("publish_ignore_globs", [])),
        publish_rules=rules,
        default_target_subdir=raw_config.get("default_target_subdir", "pages"),
        default_section=raw_config.get("default_section", "Pages"),
        default_page_type=raw_config.get("default_type", "page"),
    )


def iter_source_files(config: CampaignPublishConfig) -> list[Path]:
    files: list[Path] = []
    for file_path in sorted(config.source_wiki_root.rglob("*.md")):
        source_ref = file_path.relative_to(config.source_wiki_root).as_posix()
        if any(
            fnmatch.fnmatch(source_ref, pattern.replace("\\", "/"))
            for pattern in config.publish_ignore_globs
        ):
            continue
        files.append(file_path)
    return files


def load_source_document(config: CampaignPublishConfig, source_path: Path) -> SourceDocument:
    raw_text = source_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(raw_text)
    aliases = metadata.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]

    title = metadata.get("title") or extract_heading_title(body) or source_path.stem
    cleaned_body = strip_redundant_heading(body, title).strip()
    summary = metadata.get("summary", "").strip() or summarize_body(cleaned_body)

    return SourceDocument(
        source_path=source_path,
        source_ref=source_path.relative_to(config.source_wiki_root).as_posix(),
        title=title,
        aliases=list(aliases),
        summary=summary,
        body=cleaned_body,
    )


def extract_heading_title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip()
        break
    return ""


def strip_redundant_heading(body: str, title: str) -> str:
    lines = body.splitlines()
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1

    if index >= len(lines):
        return body

    first_line = lines[index].strip()
    if first_line.startswith("# "):
        heading_text = first_line[2:].strip()
        if normalize_lookup(heading_text) == normalize_lookup(title):
            index += 1
            while index < len(lines) and not lines[index].strip():
                index += 1
            return "\n".join(lines[index:])

    return body


def summarize_body(body: str, limit: int = 180) -> str:
    paragraphs = body.replace("\r\n", "\n").split("\n\n")
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue

        content_lines = [
            line
            for line in lines
            if not line.startswith("#")
            and not is_metadata_style_line(line)
        ]

        if not content_lines:
            continue

        if all(line.startswith(("-", "*", ">")) for line in content_lines):
            continue

        text = " ".join(content_lines)
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."
    return ""


def is_metadata_style_line(line: str) -> bool:
    if ": " not in line:
        return False

    key, _, value = line.partition(": ")
    if not key or not value:
        return False

    return len(key) <= 40 and key[0].isupper()


def collect_existing_source_refs(root_dir: Path) -> dict[str, list[Path]]:
    refs: dict[str, list[Path]] = {}
    if not root_dir.exists():
        return refs

    for file_path in sorted(root_dir.rglob("*.md")):
        metadata, _ = parse_frontmatter(file_path.read_text(encoding="utf-8"))
        source_ref = str(metadata.get("source_ref", "")).strip()
        if source_ref:
            refs.setdefault(source_ref, []).append(file_path)
    return refs


def resolve_source_path(config: CampaignPublishConfig, source_arg: str) -> Path:
    direct_candidate = Path(source_arg)
    if direct_candidate.is_absolute() and direct_candidate.exists():
        return direct_candidate

    normalized = source_arg.replace("\\", "/").strip("/")
    candidates = [
        config.source_wiki_root / normalized,
        config.source_wiki_root / f"{normalized}.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    matches: list[Path] = []
    lowered = source_arg.lower()
    for file_path in iter_source_files(config):
        source_info = load_source_document(config, file_path)
        haystacks = [source_info.source_ref.lower(), source_info.title.lower()]
        haystacks.extend(alias.lower() for alias in source_info.aliases)
        if any(lowered in haystack for haystack in haystacks):
            matches.append(file_path)

    if len(matches) == 1:
        return matches[0]

    if not matches:
        raise PublishError(f"No source page matched '{source_arg}'.")

    examples = "\n".join(
        f"  - {match.relative_to(config.source_wiki_root).as_posix()}" for match in matches[:10]
    )
    raise PublishError(
        f"Source path '{source_arg}' is ambiguous. Matches:\n{examples}"
    )


def resolve_draft_path(config: CampaignPublishConfig, draft_arg: str) -> Path:
    direct_candidate = Path(draft_arg)
    if direct_candidate.is_absolute() and direct_candidate.exists():
        return direct_candidate

    normalized = draft_arg.replace("\\", "/").strip("/")
    candidates = [config.draft_dir / normalized, config.draft_dir / f"{normalized}.md"]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    matches: list[Path] = []
    lowered = draft_arg.lower()
    draft_files = sorted(config.draft_dir.rglob("*.md")) if config.draft_dir.exists() else []
    for file_path in draft_files:
        rel_path = file_path.relative_to(config.draft_dir).as_posix().lower()
        metadata, _ = parse_frontmatter(file_path.read_text(encoding="utf-8"))
        title = str(metadata.get("title", file_path.stem)).lower()
        source_ref = str(metadata.get("source_ref", "")).lower()
        if lowered in rel_path or lowered in title or lowered in source_ref:
            matches.append(file_path)

    if len(matches) == 1:
        return matches[0]

    if not matches:
        raise PublishError(f"No draft page matched '{draft_arg}'.")

    examples = "\n".join(
        f"  - {match.relative_to(config.draft_dir).as_posix()}" for match in matches[:10]
    )
    raise PublishError(
        f"Draft path '{draft_arg}' is ambiguous. Matches:\n{examples}"
    )


def find_publish_rule(config: CampaignPublishConfig, source_ref: str) -> PublishRule | None:
    matches = [rule for rule in config.publish_rules if rule.matches(source_ref)]
    if not matches:
        return None
    return sorted(matches, key=lambda rule: len(rule.normalized_prefix), reverse=True)[0]


def build_output_relative_ref(
    source_ref: str, rule: PublishRule | None, title: str, slug_override: str | None, config: CampaignPublishConfig
) -> str:
    source_stem = PurePosixPath(source_ref).with_suffix("")
    leaf_slug = slugify(slug_override or title or source_stem.name)

    if not rule:
        return f"{config.default_target_subdir}/{leaf_slug}"

    if not rule.preserve_subdirs:
        return f"{rule.target_subdir}/{leaf_slug}"

    prefix = PurePosixPath(rule.normalized_prefix)
    remainder = source_stem.relative_to(prefix)
    parts = [slugify(part) for part in remainder.parts[:-1]]
    parts.append(leaf_slug)
    return "/".join([rule.target_subdir, *parts])


def create_frontmatter(metadata: dict[str, Any]) -> str:
    rendered = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{rendered}\n---\n"


def build_import_plan(
    config: CampaignPublishConfig,
    source_doc: SourceDocument,
    *,
    section: str | None,
    page_type: str | None,
    title: str | None,
    slug: str | None,
    summary: str | None,
    reveal_after_session: int | None,
) -> ImportPlan:
    resolved_title = title or source_doc.title
    rule = find_publish_rule(config, source_doc.source_ref)
    relative_output_ref = build_output_relative_ref(
        source_doc.source_ref,
        rule,
        resolved_title,
        slug,
        config,
    )

    metadata: dict[str, Any] = {
        "title": resolved_title,
        "slug": relative_output_ref,
        "section": section or (rule.section if rule else config.default_section),
        "type": page_type or (rule.page_type if rule else config.default_page_type),
        "aliases": source_doc.aliases,
        "summary": summary or source_doc.summary,
        "reveal_after_session": (
            config.current_session if reveal_after_session is None else reveal_after_session
        ),
        "source_ref": source_doc.source_ref,
        "imported_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "published": False,
    }

    output_path = config.draft_dir / Path(relative_output_ref).with_suffix(".md")
    body = f"{DRAFT_REVIEW_COMMENT}\n{source_doc.body.strip()}\n"
    return ImportPlan(
        destination_path=output_path,
        relative_output_ref=relative_output_ref,
        metadata=metadata,
        body=body,
    )


def write_markdown_file(
    destination_path: Path,
    metadata: dict[str, Any],
    body: str,
    *,
    force: bool = False,
) -> None:
    if destination_path.exists() and not force:
        raise PublishError(
            f"Destination already exists: {destination_path}\nUse --force to overwrite it."
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = create_frontmatter(metadata)
    destination_path.write_text(f"{frontmatter}\n{body.strip()}\n", encoding="utf-8")


def strip_draft_review_comment(body: str) -> str:
    stripped = body.lstrip()
    if stripped.startswith("<!--") and "IMPORTED DRAFT" in stripped.split("-->", 1)[0]:
        _, _, remainder = stripped.partition("-->")
        return remainder.lstrip()
    return body


def promote_draft(
    config: CampaignPublishConfig,
    draft_path: Path,
    *,
    force: bool = False,
    reveal_after_session: int | None = None,
) -> Path:
    metadata, body = parse_frontmatter(draft_path.read_text(encoding="utf-8"))
    if not metadata:
        raise PublishError(f"Draft file is missing frontmatter: {draft_path}")

    relative_ref = draft_path.relative_to(config.draft_dir).with_suffix("").as_posix()
    destination_path = config.content_dir / draft_path.relative_to(config.draft_dir)

    metadata["slug"] = str(metadata.get("slug") or relative_ref)
    metadata["published"] = True
    if reveal_after_session is not None:
        metadata["reveal_after_session"] = reveal_after_session

    cleaned_body = strip_draft_review_comment(body)
    write_markdown_file(destination_path, metadata, cleaned_body, force=force)
    return destination_path


def sync_read_model_after_promotion() -> None:
    from .app import create_app
    from .db import init_database

    app = create_app()
    with app.app_context():
        init_database()
        app.extensions["repository_store"].refresh()


def search_sources(config: CampaignPublishConfig, query: str, limit: int) -> list[SourceDocument]:
    query_lower = query.lower().strip()
    results: list[SourceDocument] = []

    for file_path in iter_source_files(config):
        source_doc = load_source_document(config, file_path)
        haystacks = [source_doc.source_ref.lower(), source_doc.title.lower(), source_doc.summary.lower()]
        haystacks.extend(alias.lower() for alias in source_doc.aliases)
        if not query_lower or any(query_lower in haystack for haystack in haystacks):
            results.append(source_doc)

    return results[:limit]


def command_search(project_root: Path, args: argparse.Namespace) -> int:
    config = load_publish_config(project_root, args.campaign)
    draft_refs = collect_existing_source_refs(config.draft_dir)
    published_refs = collect_existing_source_refs(config.content_dir)
    matches = search_sources(config, args.query, args.limit)

    if not matches:
        print(f"No source pages matched '{args.query}'.")
        return 0

    for match in matches:
        states: list[str] = []
        if match.source_ref in draft_refs:
            states.append("draft")
        if match.source_ref in published_refs:
            states.append("published")
        state_text = f" [{' / '.join(states)}]" if states else ""
        print(f"{match.source_ref} | {match.title}{state_text}")
        if match.aliases:
            print(f"  aliases: {', '.join(match.aliases)}")
        if match.summary:
            print(f"  summary: {match.summary}")

    return 0


def command_draft(project_root: Path, args: argparse.Namespace) -> int:
    config = load_publish_config(project_root, args.campaign)
    source_path = resolve_source_path(config, args.source)
    source_doc = load_source_document(config, source_path)
    plan = build_import_plan(
        config,
        source_doc,
        section=args.section,
        page_type=args.page_type,
        title=args.title,
        slug=args.slug,
        summary=args.summary,
        reveal_after_session=args.reveal_after_session,
    )

    if args.dry_run:
        print(f"Source: {source_doc.source_ref}")
        print(f"Draft:  {plan.destination_path}")
        print(f"Slug:   {plan.metadata['slug']}")
        print(f"Section:{plan.metadata['section']}")
        print(f"Type:   {plan.metadata['type']}")
        print(f"Reveal: {plan.metadata['reveal_after_session']}")
        return 0

    write_markdown_file(plan.destination_path, plan.metadata, plan.body, force=args.force)
    print(f"Draft created: {plan.destination_path}")
    print("Review and redact the draft before promotion.")
    return 0


def command_promote(project_root: Path, args: argparse.Namespace) -> int:
    config = load_publish_config(project_root, args.campaign)
    draft_path = resolve_draft_path(config, args.draft)
    if args.dry_run:
        metadata, _ = parse_frontmatter(draft_path.read_text(encoding="utf-8"))
        destination_path = config.content_dir / draft_path.relative_to(config.draft_dir)
        reveal_after_session = (
            args.reveal_after_session
            if args.reveal_after_session is not None
            else metadata.get("reveal_after_session", config.current_session)
        )
        print(f"Draft:   {draft_path}")
        print(f"Publish: {destination_path}")
        print(f"Slug:    {metadata.get('slug', destination_path.stem)}")
        print(f"Section: {metadata.get('section', config.default_section)}")
        print(f"Type:    {metadata.get('type', config.default_page_type)}")
        print(f"Reveal:  {reveal_after_session}")
        return 0

    destination_path = promote_draft(
        config,
        draft_path,
        force=args.force,
        reveal_after_session=args.reveal_after_session,
    )
    sync_read_model_after_promotion()
    print(f"Published content written to: {destination_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search GM wiki pages, import them into drafts, and promote reviewed drafts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search source wiki pages.")
    search_parser.add_argument("campaign", help="Campaign slug, for example linden-pass")
    search_parser.add_argument("query", help="Search text for source path, title, or aliases")
    search_parser.add_argument("--limit", type=int, default=15, help="Maximum results to print")

    draft_parser = subparsers.add_parser("draft", help="Import a source wiki page into drafts.")
    draft_parser.add_argument("campaign", help="Campaign slug, for example linden-pass")
    draft_parser.add_argument("source", help="Source wiki path or unique title/path fragment")
    draft_parser.add_argument("--title", help="Override the imported title")
    draft_parser.add_argument("--slug", help="Override the output slug leaf")
    draft_parser.add_argument("--section", help="Override the target section name")
    draft_parser.add_argument("--page-type", help="Override the page type")
    draft_parser.add_argument("--summary", help="Override the summary")
    draft_parser.add_argument(
        "--reveal-after-session",
        type=int,
        help="Override the session number when the page becomes visible once published",
    )
    draft_parser.add_argument("--force", action="store_true", help="Overwrite an existing draft")
    draft_parser.add_argument(
        "--dry-run", action="store_true", help="Print the planned output without writing a file"
    )

    promote_parser = subparsers.add_parser(
        "promote", help="Promote a reviewed draft into published player content."
    )
    promote_parser.add_argument("campaign", help="Campaign slug, for example linden-pass")
    promote_parser.add_argument("draft", help="Draft path or unique draft path fragment")
    promote_parser.add_argument(
        "--reveal-after-session",
        type=int,
        help="Override reveal_after_session during promotion",
    )
    promote_parser.add_argument("--force", action="store_true", help="Overwrite published content")
    promote_parser.add_argument(
        "--dry-run", action="store_true", help="Print the promotion plan without writing a file"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = Path(__file__).resolve().parent.parent

    try:
        if args.command == "search":
            return command_search(project_root, args)
        if args.command == "draft":
            return command_draft(project_root, args)
        if args.command == "promote":
            return command_promote(project_root, args)
    except PublishError as error:
        print(error)
        return 1

    parser.error(f"Unhandled command: {args.command}")
    return 2
