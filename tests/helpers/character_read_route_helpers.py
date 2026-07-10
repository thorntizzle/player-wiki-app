from __future__ import annotations

import re
from pathlib import Path

from player_wiki.systems_models import SystemsEntryRecord
from tests.helpers.systems_seed_helpers import _systems_ref

TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\x8f\x9b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
TEST_JPG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00"
    + (b"\x08" * 64)
    + b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\x00\xff\xd9"
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _character_read_shell_script_text() -> str:
    return (PROJECT_ROOT / "player_wiki" / "static" / "character-read-shell.js").read_text(encoding="utf-8")


def _assert_event_contains(event: dict, expected: dict) -> None:
    assert {key: event.get(key) for key in expected} == expected


def _read_shell_target_subpages(html: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(r'data-character-read-target-subpage="([^"]+)"', html)
    ]


def _seed_systems_entry(
    app,
    *,
    source_id: str,
    entry_type: str,
    slug: str,
    title: str,
    rendered_html: str = "",
    metadata: dict[str, object] | None = None,
) -> SystemsEntryRecord:
    normalized_source_id = source_id.strip().upper()
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        source_titles = {
            "DMG": "Dungeon Master's Guide",
            "PHB": "Player's Handbook",
            "TCE": "Tasha's Cauldron of Everything",
            "XGE": "Xanathar's Guide to Everything",
        }
        systems_store.upsert_source(
            "DND-5E",
            normalized_source_id,
            title=source_titles.get(normalized_source_id, normalized_source_id),
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        existing_entries = [
            {
                "entry_key": record.entry_key,
                "entry_type": record.entry_type,
                "slug": record.slug,
                "title": record.title,
                "source_page": record.source_page,
                "source_path": record.source_path,
                "search_text": record.search_text,
                "player_safe_default": record.player_safe_default,
                "dm_heavy": record.dm_heavy,
                "metadata": dict(record.metadata or {}),
                "body": dict(record.body or {}),
                "rendered_html": record.rendered_html,
            }
            for record in systems_store.list_entries_for_source(
                "DND-5E",
                normalized_source_id,
                entry_type=entry_type,
            )
            if str(record.slug or "").strip() != slug
        ]
        systems_store.replace_entries_for_source(
            "DND-5E",
            normalized_source_id,
            entry_types=[entry_type],
            entries=existing_entries
            + [
                {
                    "entry_key": f"dnd-5e|{entry_type}|{normalized_source_id.lower()}|{slug}",
                    "entry_type": entry_type,
                    "slug": slug,
                    "title": title,
                    "source_page": "1",
                    "source_path": f"test/{entry_type}.json",
                    "search_text": f"{title} {entry_type}",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": dict(metadata or {}),
                    "body": {},
                    "rendered_html": rendered_html or f"<p>{title}.</p>",
                }
            ],
        )
        entry = app.extensions["systems_service"].get_entry_by_slug_for_campaign("linden-pass", slug)
        assert entry is not None
        return entry


def _spell_payload(
    entry: SystemsEntryRecord,
    *,
    source: str,
    mark: str = "",
    is_always_prepared: bool = False,
    is_bonus_known: bool = False,
    **extra: object,
) -> dict[str, object]:
    metadata = dict(entry.metadata or {})
    payload = {
        "name": str(entry.title or "").strip(),
        "casting_time": "1 action",
        "range": "60 feet" if int(metadata.get("level") or 0) > 0 else "Self",
        "duration": "Instantaneous" if int(metadata.get("level") or 0) > 0 else "1 round",
        "components": "V",
        "save_or_hit": "",
        "source": source,
        "reference": f"p. {entry.source_page or '200'}",
        "mark": mark,
        "is_always_prepared": is_always_prepared,
        "is_bonus_known": is_bonus_known,
        "systems_ref": _systems_ref(entry),
    }
    payload.update(dict(extra or {}))
    return payload
