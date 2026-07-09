from __future__ import annotations


def _seed_systems_item_entry(
    app,
    *,
    slug: str = "phb-item-rope",
    title: str = "Rope",
    metadata: dict[str, object] | None = None,
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
                    "rendered_html": f"<p>{title}.</p>",
                }
            ],
        )
        entry = app.extensions["systems_service"].get_entry_by_slug_for_campaign("linden-pass", slug)
        assert entry is not None
        return entry
