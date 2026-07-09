from __future__ import annotations

import json
from pathlib import Path

from player_wiki.campaign_package_exporter import (
    export_campaign_package,
    parse_image_association_report,
)
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_parse_image_association_report_extracts_source_png(tmp_path):
    report_path = tmp_path / "image-report.md"
    report_path.write_text(
        "\n".join(
            [
                "# Live Article Image Report With Vault PNG Sources",
                "",
                "### NPCs (1)",
                "",
                "| Article | Subsection | Page Ref | Live WebP Asset | Source PNG | Source Match |",
                "|---|---|---|---|---|---|",
                "| [Captain Lyra Vale](https://example.test/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale) | Harbor Allies | `npcs/captain-lyra-vale` | [npcs/captain-lyra-vale.webp](https://example.test/campaigns/linden-pass/assets/npcs/captain-lyra-vale.webp) | `C:\\Vault\\Images\\Captain Lyra Vale Portrait.png` | filename-match |",
                "",
            ]
        ),
        encoding="utf-8",
    )

    rows = parse_image_association_report(report_path)

    assert rows == [
        {
            "article": "Captain Lyra Vale",
            "article_url": "https://example.test/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale",
            "section": "NPCs",
            "subsection": "Harbor Allies",
            "page_ref": "npcs/captain-lyra-vale",
            "live_webp_asset_ref": "npcs/captain-lyra-vale.webp",
            "live_webp_asset_url": "https://example.test/campaigns/linden-pass/assets/npcs/captain-lyra-vale.webp",
            "source_png_path": "C:\\Vault\\Images\\Captain Lyra Vale Portrait.png",
            "source_png_exists": False,
            "source_match": "filename-match",
        }
    ]


def test_campaign_package_export_includes_systems_characters_and_image_associations(app, tmp_path):
    report_path = tmp_path / "image-report.md"
    report_path.write_text(
        "\n".join(
            [
                "# Live Article Image Report With Vault PNG Sources",
                "",
                "### NPCs (1)",
                "",
                "| Article | Subsection | Page Ref | Live WebP Asset | Source PNG | Source Match |",
                "|---|---|---|---|---|---|",
                "| [Captain Lyra Vale](https://example.test/app-next/campaigns/linden-pass/pages/npcs/captain-lyra-vale) | Harbor Allies | `npcs/captain-lyra-vale` | [npcs/captain-lyra-vale.png](https://example.test/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png) | `C:\\Vault\\Images\\Captain Lyra Vale Portrait.png` | filename-match |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "campaign-export"

    with app.app_context():
        systems_service = app.extensions["systems_service"]
        systems_store = app.extensions["systems_store"]
        library = systems_service.get_campaign_library(TEST_CAMPAIGN_SLUG)
        assert library is not None
        systems_store.upsert_entry(
            library.library_slug,
            "PHB",
            entry_key="test-classfeature:arcane-recovery",
            entry_type="classfeature",
            slug="classfeature/arcane-recovery-test",
            title="Arcane Recovery Test",
            source_page="115",
            source_path="test://phb/classfeature/arcane-recovery",
            search_text="arcane recovery full systems text",
            player_safe_default=True,
            metadata={"class": "Wizard", "level": 1},
            body={"entries": ["Full Systems text for Arcane Recovery."]},
            rendered_html="<p>Full Systems text for Arcane Recovery.</p>",
        )

        summary = export_campaign_package(
            app=app,
            campaign_slug=TEST_CAMPAIGN_SLUG,
            output_dir=output_dir,
            image_report_path=report_path,
            base_url="https://example.test",
        )

    assert summary["page_count"] > 0
    assert summary["character_count"] >= 3
    assert summary["systems_entry_count"] > 0
    assert summary["image_association_count"] >= 2

    manifest = _read_json(output_dir / "manifest.json")
    assert manifest["options"]["include_binary_assets"] is False

    pages = _read_jsonl(output_dir / "campaign" / "pages.jsonl")
    captain_page = next(page for page in pages if page["route_slug"] == "npcs/captain-lyra-vale")
    assert captain_page["image"]["asset_ref"] == "npcs/captain-lyra-vale.png"
    assert captain_page["url"] == (
        "https://example.test/campaigns/linden-pass/pages/npcs/captain-lyra-vale"
    )

    image_associations = _read_jsonl(output_dir / "assets" / "image-associations.jsonl")
    captain_image = next(
        image for image in image_associations if image["route_slug"] == "npcs/captain-lyra-vale"
    )
    assert captain_image["source_png_path"] == "C:\\Vault\\Images\\Captain Lyra Vale Portrait.png"
    assert captain_image["source_match"] == "filename-match"
    assert captain_image["campaign_asset_path"].endswith("assets\\npcs\\captain-lyra-vale.png")
    assert not (output_dir / "assets" / "files").exists()

    systems_entries = _read_jsonl(output_dir / "systems" / "entries.jsonl")
    arcane_recovery = next(
        entry for entry in systems_entries if entry["entry_key"] == "test-classfeature:arcane-recovery"
    )
    assert arcane_recovery["body"] == {"entries": ["Full Systems text for Arcane Recovery."]}
    assert arcane_recovery["rendered_html"] == "<p>Full Systems text for Arcane Recovery.</p>"

    character_state = _read_json(output_dir / "characters" / "structured" / ASSIGNED_CHARACTER_SLUG / "state.json")
    assert character_state["character_slug"] == ASSIGNED_CHARACTER_SLUG
    assert character_state["revision"] >= 1
    assert (output_dir / "characters" / "markdown" / f"{ASSIGNED_CHARACTER_SLUG}.md").exists()
    assert (output_dir / "characters" / "resolved-systems" / f"{ASSIGNED_CHARACTER_SLUG}.json").exists()

    sqlite_state_rows = _read_jsonl(output_dir / "state" / "sqlite-tables" / "character_state.jsonl")
    assert any(row["character_slug"] == ASSIGNED_CHARACTER_SLUG for row in sqlite_state_rows)

    audit_report = (output_dir / "audit" / "export-report.md").read_text(encoding="utf-8")
    assert "Image binaries are intentionally omitted" in audit_report
