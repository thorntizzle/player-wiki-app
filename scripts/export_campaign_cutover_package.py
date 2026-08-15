from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from player_wiki.campaign_cutover_exporter import (
    CampaignCutoverExportError,
    CampaignRoot,
    export_campaign_cutover_package,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CampaignCutoverExportError(
            "invalid_cli", "The cutover export invocation is invalid."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        description="Create a deterministic Campaign Player Wiki cutover package v2."
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--campaigns-parent", required=True)
    parser.add_argument(
        "--campaign",
        action="append",
        required=True,
        metavar="SLUG=STABLE_ID=PATH",
        help="Repeat once for each operator-approved campaign root.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-stable-id", required=True)
    parser.add_argument("--exporter-commit", required=True)
    parser.add_argument("--exporter-tree", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        campaigns = [_parse_campaign(value) for value in args.campaign]
        _prove_clean_exporter_identity(args.exporter_commit, args.exporter_tree)
        summary = export_campaign_cutover_package(
            database_path=Path(args.database),
            campaigns_parent=Path(args.campaigns_parent),
            campaigns=campaigns,
            output_dir=Path(args.output_dir),
            source_stable_id=args.source_stable_id,
            exporter_commit=args.exporter_commit,
            exporter_tree=args.exporter_tree,
        )
        print(
            json.dumps(
                {
                    "blob_count": summary.blob_count,
                    "content_root_digest": summary.content_root_sha256,
                    "family_counts": summary.family_counts,
                    "file_count": summary.file_count,
                    "format": summary.format,
                    "format_version": summary.format_version,
                    "manifest_digest": summary.manifest_sha256,
                    "status": "ok",
                    "table_count": summary.table_count,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except CampaignCutoverExportError as exc:
        _write_refusal(exc.code, exc.safe_message)
        return 2
    except BaseException:
        _write_refusal(
            "unexpected_refusal", "The cutover export was refused without publishing."
        )
        return 3


def _parse_campaign(value: str) -> CampaignRoot:
    parts = value.split("=", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise CampaignCutoverExportError(
            "invalid_campaign_argument", "An approved campaign argument is invalid."
        )
    return CampaignRoot(parts[0].strip(), parts[1].strip(), Path(parts[2].strip()))


def _prove_clean_exporter_identity(commit: str, tree: str) -> None:
    try:
        actual_commit = _git("rev-parse", "HEAD")
        actual_tree = _git("rev-parse", "HEAD^{tree}")
        tracked_status = _git("status", "--short", "--untracked-files=all")
    except (OSError, subprocess.SubprocessError) as exc:
        raise CampaignCutoverExportError(
            "exporter_identity_unavailable",
            "The exporter Git identity could not be proved.",
        ) from exc
    if actual_commit != commit or actual_tree != tree or tracked_status:
        raise CampaignCutoverExportError(
            "exporter_identity_mismatch",
            "The exporter is not the requested clean commit and tree.",
        )


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()


def _write_refusal(code: str, message: str) -> None:
    print(
        json.dumps(
            {"code": code, "message": message, "status": "refused"},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
