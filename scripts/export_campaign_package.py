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
        description="Export a Campaign Player Wiki campaign as a migration-ready package."
    )
    parser.add_argument("campaign_slug", help="Campaign slug to export.")
    parser.add_argument(
        "--output-dir",
        help=(
            "Output package directory. Defaults to "
            ".local/campaign-exports/<campaign_slug>-<timestamp>."
        ),
    )
    parser.add_argument(
        "--campaigns-dir",
        help="Optional campaign content root. Defaults to PLAYER_WIKI_CAMPAIGNS_DIR or repo campaigns/.",
    )
    parser.add_argument(
        "--db-path",
        help="Optional SQLite DB path. Defaults to PLAYER_WIKI_DB_PATH or .local/player_wiki.sqlite3.",
    )
    parser.add_argument(
        "--image-report",
        help=(
            "Optional Markdown image association report with live WebP and source PNG columns. "
            "When provided, source PNG paths are folded into assets/image-associations.jsonl."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Optional live app base URL used to write page and protected asset URLs.",
    )
    parser.add_argument(
        "--visible-characters-only",
        action="store_true",
        help="Export only active/visible characters instead of all character definitions.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.campaigns_dir:
        Config.CAMPAIGNS_DIR = Path(args.campaigns_dir).resolve()
    if args.db_path:
        Config.DB_PATH = Path(args.db_path).resolve()

    from player_wiki.app import create_app
    from player_wiki.campaign_package_exporter import export_campaign_package
    from player_wiki.db import init_database

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else REPO_ROOT
        / ".local"
        / "campaign-exports"
        / f"{args.campaign_slug}-{_timestamp_for_path()}"
    )
    image_report_path = Path(args.image_report).resolve() if args.image_report else None

    app = create_app()
    with app.app_context():
        init_database()
        summary = export_campaign_package(
            app=app,
            campaign_slug=args.campaign_slug,
            output_dir=output_dir,
            image_report_path=image_report_path,
            base_url=args.base_url,
            include_inactive_characters=not args.visible_characters_only,
        )

    print(f"Wrote {summary['output_dir']}")
    print(
        "Exported "
        f"{summary['page_count']} pages, "
        f"{summary['systems_entry_count']} Systems entries, "
        f"{summary['character_count']} characters, "
        f"{summary['image_association_count']} image associations."
    )
    if summary["audit_issue_count"]:
        print(f"Audit issues: {summary['audit_issue_count']} (see audit/export-report.md)")
    else:
        print("Audit issues: 0")
    return 0


def _timestamp_for_path() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
