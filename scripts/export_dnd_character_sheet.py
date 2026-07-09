from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from player_wiki.config import Config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export DND-5E app character sheets to Markdown."
    )
    parser.add_argument("campaign_slug", help="Campaign slug to export from.")
    parser.add_argument(
        "character_slug",
        nargs="?",
        help="Optional character slug. When omitted, all visible DND-5E characters are exported.",
    )
    parser.add_argument(
        "--output",
        help="Output Markdown file for a single-character export. Defaults to stdout.",
    )
    parser.add_argument(
        "--output-dir",
        help=(
            "Directory for campaign-wide exports, or a single-character export by generated filename. "
            "Defaults to .local/character-exports/<campaign_slug> for campaign-wide exports."
        ),
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include inactive characters when listing/exporting a campaign or resolving a specific slug.",
    )
    parser.add_argument(
        "--campaigns-dir",
        help="Optional campaign content root. Defaults to PLAYER_WIKI_CAMPAIGNS_DIR or repo campaigns/.",
    )
    parser.add_argument(
        "--db-path",
        help="Optional SQLite DB path. Defaults to PLAYER_WIKI_DB_PATH or .local/player_wiki.sqlite3.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.output and not args.character_slug:
        parser.error("--output can only be used when character_slug is provided.")

    if args.campaigns_dir:
        Config.CAMPAIGNS_DIR = Path(args.campaigns_dir).resolve()
    if args.db_path:
        Config.DB_PATH = Path(args.db_path).resolve()

    from player_wiki.app import create_app
    from player_wiki.character_markdown_exporter import (
        CharacterMarkdownExportError,
        export_filename_for_character,
        render_dnd_character_markdown,
    )
    from player_wiki.character_page_records import list_visible_character_page_records
    from player_wiki.db import init_database
    from player_wiki.system_policy import is_dnd_5e_system

    app = create_app()
    with app.app_context():
        init_database()
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign(args.campaign_slug)
        if campaign is None:
            raise SystemExit(f"Unknown campaign slug: {args.campaign_slug}")

        character_repository = app.extensions["character_repository"]
        if args.character_slug:
            getter = (
                character_repository.get_character
                if args.include_inactive
                else character_repository.get_visible_character
            )
            record = getter(args.campaign_slug, args.character_slug)
            if record is None:
                raise SystemExit(
                    f"Character not found or not visible: {args.campaign_slug}/{args.character_slug}"
                )
            records = [record]
        else:
            records = (
                character_repository.list_characters(args.campaign_slug)
                if args.include_inactive
                else character_repository.list_visible_characters(args.campaign_slug)
            )
            records = [
                record
                for record in records
                if is_dnd_5e_system(record.definition.system)
            ]
            if not records:
                raise SystemExit(f"No DND-5E characters found for campaign: {args.campaign_slug}")

        campaign_page_records = list_visible_character_page_records(
            app.extensions["campaign_page_store"],
            args.campaign_slug,
            campaign,
            include_body=True,
            excluded_sections={"Sessions"},
        )
        systems_service = app.extensions["systems_service"]

        try:
            rendered = [
                (
                    record,
                    render_dnd_character_markdown(
                        campaign,
                        record,
                        systems_service=systems_service,
                        campaign_page_records=campaign_page_records,
                    ),
                )
                for record in records
            ]
        except CharacterMarkdownExportError as exc:
            raise SystemExit(str(exc)) from exc

    if args.character_slug and not args.output and not args.output_dir:
        print(rendered[0][1], end="")
        return 0

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered[0][1], encoding="utf-8")
        print(f"Wrote {output_path}")
        return 0

    output_dir = Path(args.output_dir) if args.output_dir else REPO_ROOT / ".local" / "character-exports" / args.campaign_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    for record, markdown_text in rendered:
        output_path = output_dir / export_filename_for_character(record)
        output_path.write_text(markdown_text, encoding="utf-8")
        print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
