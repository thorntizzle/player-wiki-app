from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import zipfile

from player_wiki.systems_importer import Dnd5eSystemsImporter


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _goblin_payload() -> dict[str, object]:
    return {
        "monster": [
            {
                "name": "Goblin",
                "source": "MM",
                "page": 166,
                "size": ["S"],
                "type": {"type": "humanoid", "tags": ["goblinoid"]},
                "alignment": ["N", "E"],
                "ac": [{"ac": 15, "from": ["leather armor", "shield"]}],
                "hp": {"average": 7, "formula": "2d6"},
                "speed": {"walk": 30},
                "str": 8,
                "dex": 14,
                "con": 10,
                "int": 10,
                "wis": 8,
                "cha": 8,
                "action": [
                    {
                        "name": "Scimitar",
                        "entries": [
                            "{@atk mw} {@hit 4} to hit, reach 5 ft., one target. {@h}5 ({@damage 1d6 + 2}) slashing damage."
                        ],
                    }
                ],
            }
        ]
    }


def _import_systems_goblin(app, tmp_path) -> tuple[str, str]:
    data_root = tmp_path / "systems-dnd5e-source"
    _write_json(data_root / "data/bestiary/bestiary-mm.json", _goblin_payload())
    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MM", entry_types=["monster"])
        entry = next(
            item
            for item in app.extensions["systems_service"].list_monster_entries_for_campaign("linden-pass")
            if item.title == "Goblin"
        )
        return entry.entry_key, entry.slug


def _build_systems_import_archive(tmp_path=None, *, wrapper: str = "") -> bytes:
    wrapper_prefix = f"{wrapper.strip('/')}/" if wrapper.strip("/") else ""
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{wrapper_prefix}data/bestiary/bestiary-mm.json",
            json.dumps(_goblin_payload(), indent=2),
        )
    return archive_buffer.getvalue()


def _build_unsafe_systems_import_archive(tmp_path=None) -> bytes:
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../data/bestiary/bestiary-mm.json", "{}")
    return archive_buffer.getvalue()


def _build_malformed_utf8_systems_import_archive() -> bytes:
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("ATTACKER-SENTINEL.json", "{}")

    malformed = bytearray(archive_buffer.getvalue())
    central_offset = malformed.index(b"PK\x01\x02")
    flags = int.from_bytes(malformed[central_offset + 8 : central_offset + 10], "little")
    malformed[central_offset + 8 : central_offset + 10] = (flags | 0x800).to_bytes(2, "little")
    malformed[central_offset + 46] = 0xFF
    return bytes(malformed)
