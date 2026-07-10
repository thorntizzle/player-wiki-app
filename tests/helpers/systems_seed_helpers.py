from __future__ import annotations


def _seed_systems_item_entry(
    app,
    *,
    slug: str = "phb-item-rope",
    title: str = "Rope",
    metadata: dict[str, object] | None = None,
    rendered_html: str | None = None,
):
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
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
            for record in systems_store.list_entries_for_source("DND-5E", "PHB", entry_type="item")
            if str(record.slug or "").strip() != slug
        ]
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["item"],
            entries=existing_entries
            + [
                {
                    "entry_key": f"dnd-5e|item|phb|{slug}",
                    "entry_type": "item",
                    "slug": slug,
                    "title": title,
                    "source_page": "150",
                    "source_path": "data/items-base.json",
                    "search_text": f"{title.lower()} rope gear",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "weight": 10,
                        **dict(metadata or {}),
                    },
                    "body": {},
                    "rendered_html": rendered_html if rendered_html is not None else f"<p>{title}.</p>",
                }
            ],
        )
        entry = app.extensions["systems_service"].get_entry_by_slug_for_campaign("linden-pass", slug)
        assert entry is not None
        return entry


def _seed_systems_spell_entry(
    app,
    *,
    slug: str = "phb-spell-api-detail",
    title: str = "API Detail Spell",
    metadata: dict[str, object] | None = None,
    rendered_html: str | None = None,
):
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
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
            for record in systems_store.list_entries_for_source("DND-5E", "PHB", entry_type="spell")
            if str(record.slug or "").strip() != slug
        ]
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=existing_entries
            + [
                {
                    "entry_key": f"dnd-5e|spell|phb|{slug}",
                    "entry_type": "spell",
                    "slug": slug,
                    "title": title,
                    "source_page": "220",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": title.lower(),
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"level": 1, "school": "evocation", **dict(metadata or {})},
                    "body": {},
                    "rendered_html": rendered_html if rendered_html is not None else f"<p>{title} spell detail.</p>",
                }
            ],
        )
        entry = app.extensions["systems_service"].get_entry_by_slug_for_campaign("linden-pass", slug)
        assert entry is not None
        return entry


def _seed_systems_spell_entries(app, entries: list[dict[str, object]]) -> dict[str, object]:
    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        source_titles = {
            "PHB": "Player's Handbook",
            "TCE": "Tasha's Cauldron of Everything",
            "XGE": "Xanathar's Guide to Everything",
        }
        source_ids = {
            str(entry.get("source_id") or "PHB").strip().upper()
            for entry in entries
        }
        for source_id in sorted(source_ids):
            if not source_id:
                continue
            systems_store.upsert_source(
                "DND-5E",
                source_id,
                title=source_titles.get(source_id, source_id),
                license_class="srd_cc",
                public_visibility_allowed=True,
                requires_unofficial_notice=False,
            )
        for source_id in sorted(source_ids):
            if not source_id:
                continue
            systems_store.replace_entries_for_source(
                "DND-5E",
                source_id,
                entry_types=["spell"],
                entries=[
                    {
                        "entry_key": f"dnd-5e|spell|{source_id.lower()}|{str(entry['slug'])}",
                        "entry_type": "spell",
                        "slug": str(entry["slug"]),
                        "title": str(entry["title"]),
                        "source_page": str(entry.get("source_page") or "200"),
                        "source_path": f"data/spells/spells-{source_id.lower()}.json",
                        "search_text": str(entry.get("search_text") or f"{entry['title']} spell"),
                        "player_safe_default": True,
                        "dm_heavy": False,
                        "metadata": {
                            "level": int(entry.get("level") or 0),
                            "class_lists": dict(entry.get("class_lists") or {"PHB": []}),
                            "ritual": bool(entry.get("ritual")),
                            "casting_time": list(entry.get("casting_time") or [{"number": 1, "unit": "action"}]),
                            "range": dict(entry.get("range") or {"type": "point", "distance": {"type": "feet", "amount": 60}}),
                            "duration": list(entry.get("duration") or [{"type": "timed", "duration": {"type": "round", "amount": 1}}]),
                            "components": dict(entry.get("components") or {"v": True}),
                        },
                        "body": {},
                        "rendered_html": f"<p>{entry['title']}.</p>",
                    }
                    for entry in entries
                    if str(entry.get("source_id") or "PHB").strip().upper() == source_id
                ],
            )
        systems_service = app.extensions["systems_service"]
        return {
            str(entry["slug"]): systems_service.get_entry_by_slug_for_campaign("linden-pass", str(entry["slug"]))
            for entry in entries
        }


def _systems_ref(entry) -> dict[str, str]:
    return {
        "entry_key": str(entry.entry_key or "").strip(),
        "entry_type": str(entry.entry_type or "").strip(),
        "title": str(entry.title or "").strip(),
        "slug": str(entry.slug or "").strip(),
        "source_id": str(entry.source_id or "").strip(),
    }
