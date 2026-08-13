from __future__ import annotations

from player_wiki.db import get_db_query_metrics, reset_db_query_metrics
from player_wiki.systems_store import SystemsStore


def _entry(entry_key: str, slug: str, title: str) -> dict[str, object]:
    return {
        "entry_key": entry_key,
        "entry_type": "item",
        "slug": slug,
        "title": title,
        "source_page": "1",
        "source_path": "test.json",
        "search_text": title,
        "player_safe_default": True,
        "dm_heavy": False,
        "metadata": {},
        "body": {},
        "rendered_html": f"<p>{title}</p>",
    }


def test_identity_batch_scopes_library_sources_type_and_disabled_override(app):
    with app.app_context():
        store = SystemsStore()
        store.upsert_library("OTHER", title="Other", system_code="OTHER")
        for library_slug, source_id in (
            ("DND-5E", "PHB"),
            ("DND-5E", "XGE"),
            ("OTHER", "PHB"),
        ):
            store.upsert_source(
                library_slug,
                source_id,
                title=source_id,
                license_class="srd_cc",
                public_visibility_allowed=True,
                requires_unofficial_notice=False,
            )
        store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["item"],
            entries=[
                _entry("item|kept", "kept", "Kept Item"),
                _entry("item|disabled", "disabled", "Disabled Item"),
            ],
        )
        store.replace_entries_for_source(
            "DND-5E",
            "XGE",
            entry_types=["item"],
            entries=[_entry("item|wrong-source", "wrong-source", "Wrong Source")],
        )
        store.replace_entries_for_source(
            "OTHER",
            "PHB",
            entry_types=["item"],
            entries=[_entry("item|wrong-library", "wrong-library", "Wrong Library")],
        )
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug="DND-5E",
            entry_key="item|disabled",
            visibility_override=None,
            is_enabled_override=False,
        )

        reset_db_query_metrics()
        rows = store.list_entries_for_campaign_by_identity(
            "linden-pass",
            "DND-5E",
            ["PHB"],
            entry_type="item",
            entry_keys=[
                "item|kept",
                "item|disabled",
                "item|wrong-source",
                "item|wrong-library",
            ],
        )
        query_count = int(get_db_query_metrics()["query_count"])

    assert [row.entry_key for row in rows] == ["item|kept"]
    assert query_count == 1


def test_identity_batch_normalizes_punctuation_and_returns_duplicate_titles(app):
    with app.app_context():
        store = SystemsStore()
        for source_id in ("PHB", "XGE"):
            store.upsert_source(
                "DND-5E",
                source_id,
                title=source_id,
                license_class="srd_cc",
                public_visibility_allowed=True,
                requires_unofficial_notice=False,
            )
            store.replace_entries_for_source(
                "DND-5E",
                source_id,
                entry_types=["item"],
                entries=[
                    _entry(
                        f"item|{source_id.lower()}|storm",
                        f"{source_id.lower()}-storm",
                        "Storm's Eye +1",
                    )
                ],
            )

        rows = store.list_entries_for_campaign_by_identity(
            "linden-pass",
            "DND-5E",
            ["PHB", "XGE"],
            entry_type="item",
            exact_titles=[" STORM'S--EYE +1 ", "') OR 1=1 --"],
        )
        reset_db_query_metrics()
        empty = store.list_entries_for_campaign_by_identity(
            "linden-pass",
            "DND-5E",
            ["PHB", "XGE"],
            entry_type="item",
        )
        empty_query_count = int(get_db_query_metrics()["query_count"])

    assert [row.source_id for row in rows] == ["PHB", "XGE"]
    assert empty == []
    assert empty_query_count == 0
