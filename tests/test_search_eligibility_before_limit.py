from copy import deepcopy
import re

import pytest
from flask import g, has_request_context, request

from player_wiki.auth import (
    campaign_systems_search_visibilities,
    can_access_campaign_systems_entry,
)
from player_wiki.db import _InstrumentedCursor, get_db, get_db_query_metrics, reset_db_query_metrics
from player_wiki.models import page_sort_key
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.sample_data import ASSIGNED_CHARACTER_SLUG


def seed_systems_search(app, *, hidden_count=1000, visible_count=30, source_id="H6", visibility="players", hidden_visibility=None):
    service = app.extensions["systems_service"]
    store = app.extensions["systems_store"]
    library = service.get_campaign_library_slug("linden-pass")
    store.upsert_source(library, source_id, title="Synthetic H6 source", license_class="custom_campaign", public_visibility_allowed=True)
    store.upsert_campaign_enabled_source("linden-pass", library_slug=library, source_id=source_id, is_enabled=True, default_visibility=visibility)
    entries = []
    for index in range(hidden_count + visible_count):
        hidden = index < hidden_count
        entries.append({
            "entry_key": f"h6|{source_id}|{index}", "entry_type": "item",
            "slug": f"h6-{source_id.lower()}-{index}",
            "title": f"{'A' if hidden else 'Z'} h6needle {index:04d}",
            "metadata": {}, "body": {"entries": ["synthetic " * 880]},
        })
    store.replace_entries_for_source(library, source_id, entries=entries, entry_types=["item"])
    get_db().executemany(
        """INSERT INTO campaign_entry_overrides
           (campaign_slug, library_slug, entry_key, visibility_override, is_enabled_override, updated_at)
           VALUES ('linden-pass', ?, ?, ?, ?, '2026-09-07T00:00:00Z')""",
        [(library, f"h6|{source_id}|{index}", hidden_visibility, 1 if hidden_visibility else 0) for index in range(hidden_count)],
    )
    get_db().commit()
    return service, store, [entry["title"] for entry in entries[hidden_count:]]


@pytest.mark.parametrize("hidden_count", [60, 1000])
@pytest.mark.parametrize("character_read", [False, True])
def test_systems_disabled_prefix_cannot_consume_result_cap(app, hidden_count, character_read, monkeypatch):
    with app.app_context():
        service, store, expected = seed_systems_search(app, hidden_count=hidden_count)
        hydrated = []
        original_map = store._map_entry
        def observe(row):
            if row is not None and row["source_id"] == "H6":
                hydrated.append(row["title"])
            return original_map(row)
        monkeypatch.setattr(store, "_map_entry", observe)
        search = service.search_entries_for_character_read if character_read else service.search_entries_for_campaign
        results = search("linden-pass", query="h6needle", include_source_ids=["H6"], limit=20)
        assert [entry.title for entry in results] == expected[:20]
        assert hydrated == expected[:20]


def test_page_hidden_prefix_and_sql_order_do_not_consume_visible_cap(app):
    with app.app_context():
        store = app.extensions["campaign_page_store"]
        for index in range(70):
            store.upsert_page("linden-pass", f"notes/h6hidden-{index}", metadata={"title": f"A h6needle {index}", "section": "Notes", "published": False}, body_markdown="synthetic", commit=False)
        for index in range(30):
            store.upsert_page("linden-pass", f"notes/h6visible-{index}", metadata={"title": f"Z h6needle {index:03d}", "section": "Notes", "published": True}, body_markdown="synthetic", commit=False)
        get_db().commit()
        records = store.search_page_records("linden-pass", "h6needle", limit=30, current_session=0)
        assert len([record for record in records if record.page.published]) == 30


@pytest.mark.parametrize("hidden_count", [0, 1000])
def test_systems_visibility_prefix_has_bounded_eligible_hydration(app, hidden_count, monkeypatch):
    with app.app_context():
        service, store, expected = seed_systems_search(
            app, hidden_count=hidden_count, visibility="public", hidden_visibility="private",
        )
        hydrated = []
        original_map = store._map_entry

        def observe(row):
            if row is not None and row["source_id"] == "H6":
                hydrated.append(row["title"])
            return original_map(row)

        monkeypatch.setattr(store, "_map_entry", observe)
        # Warm the same existing library/source owners the browser route uses.
        service.search_entries_for_campaign("linden-pass", query="h6needle", visible_to=("public",), limit=30)
        hydrated.clear()
        reset_db_query_metrics()
        results = service.search_entries_for_campaign(
            "linden-pass", query="h6needle", visible_to=("public",), limit=30,
        )
        queries = int(get_db_query_metrics()["query_count"])
        assert [entry.title for entry in results] == expected
        assert hydrated == expected
        assert queries <= 220
        print(f"systems hidden={hidden_count}: queries={queries}, hydrated={len(hydrated)}")
        # Actorless Character options intentionally retain their owning policy.
        actorless = service.search_entries_for_character_read("linden-pass", query="h6needle", limit=20)
        if hidden_count:
            assert all(entry.title.startswith("A ") for entry in actorless)


def seed_systems_visibility_controls(app):
    service = app.extensions["systems_service"]
    store = app.extensions["systems_store"]
    library = service.get_campaign_library_slug("linden-pass")
    for source_id, default, public_allowed, enabled in (
        ("H6-PUBLIC", "public", True, True),
        ("H6-PRIVATE", "private", True, True),
        ("DMG", "players", False, True),
        ("H6-DISABLED", "public", True, False),
    ):
        store.upsert_source(
            library, source_id, title=f"Synthetic {source_id}", license_class="custom_campaign",
            public_visibility_allowed=public_allowed,
        )
        store.upsert_campaign_enabled_source(
            "linden-pass", library_slug=library, source_id=source_id,
            is_enabled=enabled, default_visibility=default,
        )
        rows = []
        for entry_type in ("item", "book"):
            for label in ("default", "empty", "public", "players", "dm", "private", "spaces", "invalid", "disabled"):
                identity = f"{source_id}-{entry_type}-{label}"
                rows.append({
                    "entry_key": f"h6policy|{identity}", "slug": identity.lower(),
                    "entry_type": entry_type, "title": f"h6policy {identity}",
                    "metadata": {"private_search_marker": "h6-prose-only"},
                    "body": {"entries": ["h6-prose-only"]},
                })
        store.replace_entries_for_source(library, source_id, entries=rows, entry_types=["item", "book"])
        for row in rows:
            label = row["entry_key"].rsplit("-", 1)[-1]
            if label == "default":
                continue
            override = {"spaces": "\t\u2003PuBlic\n", "empty": "", "invalid": "unknown", "disabled": "public"}.get(label, label)
            store.upsert_campaign_entry_override(
                "linden-pass", library_slug=library, entry_key=row["entry_key"],
                visibility_override=override, is_enabled_override=label != "disabled",
            )
    return service, store


@pytest.mark.parametrize("floor", ["public", "players", "dm", "private"])
def test_systems_selection_matches_existing_actor_policy_before_cap(app, users, set_campaign_visibility, floor):
    set_campaign_visibility("linden-pass", campaign="public", systems=floor)
    with app.app_context():
        service, store = seed_systems_visibility_controls(app)
        all_entries = store.search_entries("DND-5E", query="h6policy", limit=None)
    for actor in (None, "observer", "outsider", "owner", "dm", "admin"):
        with app.test_request_context("/campaigns/linden-pass/"):
            auth_store = app.extensions["auth_store"]
            g.current_user = auth_store.get_user_by_id(users[actor]["id"]) if actor else None
            g.current_memberships = auth_store.list_memberships_for_user(g.current_user.id) if actor else []
            expected = [
                entry.entry_key for entry in all_entries
                if service.is_entry_enabled_for_campaign("linden-pass", entry)
                and can_access_campaign_systems_entry("linden-pass", entry.slug)
            ]
            visible_to = campaign_systems_search_visibilities("linden-pass")
            selected = service.search_entries_for_campaign(
                "linden-pass", query="h6policy", visible_to=visible_to, limit=7,
            )
            assert [entry.entry_key for entry in selected] == expected[:7], (floor, actor)
            assert all(
                can_access_campaign_systems_entry("linden-pass", entry.slug)
                for entry in selected
            )
            assert campaign_systems_search_visibilities("missing-campaign") == ()
            if floor == "public" and actor in (None, "observer", "outsider"):
                assert visible_to == ("public",)
                assert "h6policy|H6-PRIVATE-book-public" in expected
                assert "h6policy|H6-PUBLIC-book-spaces" in expected
                assert not any("|DMG-" in key for key in expected)
            if floor in ("public", "players") and actor == "owner":
                assert "h6policy|DMG-book-default" not in expected
                assert "h6policy|DMG-book-players" in expected
                assert "h6policy|DMG-book-public" in expected
                assert "h6policy|H6-PRIVATE-item-public" in expected
            if actor == "admin":
                assert visible_to == ("public", "players", "dm", "private")
                assert "h6policy|H6-PRIVATE-item-default" in expected
            assert not any("DISABLED" in key or key.endswith("-disabled") for key in expected)


def test_systems_search_uses_effective_view_as_identity(app, client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", campaign="public", systems="public")
    with app.app_context():
        seed_systems_visibility_controls(app)

    @app.get("/campaigns/linden-pass/h6-test-search")
    def h6_test_search():
        visibilities = campaign_systems_search_visibilities("linden-pass")
        entries = app.extensions["systems_service"].search_entries_for_campaign(
            "linden-pass", query="h6policy", visible_to=visibilities, limit=30,
        )
        return {"visibilities": visibilities, "result_ids": [
            f"systems:{entry.slug}" for entry in entries
        ]}

    sign_in(users["admin"]["email"], users["admin"]["password"])
    assert client.get("/campaigns/linden-pass/h6-test-search").json["visibilities"] == ["public", "players", "dm", "private"]
    for actor, expected in (("observer", ["public"]), ("owner", ["public", "players"]), ("dm", ["public", "players", "dm"])):
        with client.session_transaction() as session:
            session["view_as_user_id"] = users[actor]["id"]
        selected = client.get("/campaigns/linden-pass/h6-test-search").json
        assert selected["visibilities"] == expected
        response = client.get("/campaigns/linden-pass/global-search?q=h6policy")
        assert response.status_code == 200
        assert [row["result_id"] for row in response.json["results"]] == selected["result_ids"]


def test_seeded_search_entry_lookup_is_identity_bound_and_request_local(
    app, client, sign_in, users, monkeypatch,
):
    with app.app_context():
        service, _, _ = seed_systems_search(
            app, hidden_count=0, visible_count=1, visibility="players",
        )
        library_slug = service.get_campaign_library_slug("linden-pass")
    original_seed = service.ensure_builtin_library_seeded
    seed_calls = []

    def observed_seed(slug):
        seed_calls.append(slug)
        return original_seed(slug)

    monkeypatch.setattr(service, "ensure_builtin_library_seeded", observed_seed)
    slug = "h6-h6-0"
    matching = (id(service), "linden-pass", library_slug)
    with app.test_request_context("/campaigns/linden-pass/global-search"):
        for marker, should_seed in (
            (None, True),
            ((id(service) + 1, "linden-pass", library_slug), True),
            ((id(service), "other-campaign", library_slug), True),
            ((id(service), "linden-pass", "Xianxia"), True),
            (matching, False),
        ):
            before = len(seed_calls)
            if marker is None:
                g.pop("_systems_search_seeded_library", None)
            else:
                g._systems_search_seeded_library = marker
            assert service.get_entry_by_slug_for_campaign("linden-pass", slug) is not None
            assert len(seed_calls) - before == int(should_seed)
    with app.test_request_context("/campaigns/linden-pass/global-search"):
        before = len(seed_calls)
        assert service.get_entry_by_slug_for_campaign("linden-pass", slug) is not None
        assert len(seed_calls) == before + 1

    prior = ("outer", "marker", "state")
    observed = []

    @app.before_request
    def set_outer_seed_marker():
        if request.path.endswith("/global-search"):
            g._systems_search_seeded_library = prior

    @app.after_request
    def observe_restored_seed_marker(response):
        if request.path.endswith("/global-search"):
            observed.append(getattr(g, "_systems_search_seeded_library", None))
        return response

    sign_in(users["owner"]["email"], users["owner"]["password"])
    for _ in range(2):
        response = client.get("/campaigns/linden-pass/global-search?q=h6needle")
        assert response.status_code == 200
        assert [row["result_id"] for row in response.json["results"]] == [f"systems:{slug}"]
    assert observed == [prior, prior]


def test_systems_search_preserves_scope_type_token_order_and_body_exclusion(app):
    with app.app_context():
        service, store = seed_systems_visibility_controls(app)
        source_ids = ["H6-PUBLIC", "H6-PRIVATE"]
        # Deliberate same-title rows retain the existing title/id order.
        get_db().execute("UPDATE systems_entries SET title = 'h6policy Tied' WHERE source_id = 'H6-PUBLIC'")
        get_db().commit()
        expected = [
            entry for entry in store.search_entries("DND-5E", query="h6policy", source_ids=source_ids, entry_type="item", limit=None)
            if service.is_entry_enabled_for_campaign("linden-pass", entry)
        ][:20]
        actual = service.search_entries_for_campaign(
            "linden-pass", query=" h6policy  ITEM ", include_source_ids=[" H6-PUBLIC ", "H6-PRIVATE"],
            entry_type="item", limit=20,
        )
        assert [entry.id for entry in actual] == [entry.id for entry in expected]
        assert service.search_entries_for_campaign("linden-pass", query="h6-prose-only") == []
        assert service.search_entries_for_campaign("linden-pass", query="h6policy missingword") == []
        assert service.search_entries_for_campaign("linden-pass", query="h6policy", include_source_ids=["missing-source", "H6-DISABLED"]) == []


@pytest.mark.parametrize("hidden_count", [0, 1000])
@pytest.mark.parametrize("include_body", [False, True])
def test_wiki_selection_matches_full_visible_order_with_scalar_metadata_only(app, monkeypatch, hidden_count, include_body):
    with app.app_context():
        store = app.extensions["campaign_page_store"]
        campaign = deepcopy(app.extensions["repository_store"].get().get_campaign("linden-pass"))
        campaign.current_session = 4
        records = []
        identities = [
            ("Sessions", "", "session", 0), ("Sessions", "", "session", 4),
            ("Sessions", "", "session", 2), ("Sessions", "", "article", 1),
            ("Notes", "", "note", 0),
            ("Locations", "Districts and City Areas", "location", 0),
            ("Locations", "\tCivic and Institutional Sites\u2003", "location", 0),
            ("Locations", "zz", "location", 0), ("Locations", "Ä", "location", 0),
            ("Locations", "á", "location", 0), ("Locations", "ä", "location", 0),
            ("Factions", "Major Powers", "faction", 0),
            ("Factions", "Campaign Institutions", "faction", 0),
            ("Lore", "", "article", 0), ("Ä", "", "article", 0),
            ("á", "", "article", 0), ("ä", "", "article", 0),
        ]
        for index, (section, subsection, page_type, reveal) in enumerate(identities):
            for suffix, title in (("b", "Ä"), ("a", "ä"), ("c", "á")):
                records.append(store.upsert_page(
                    "linden-pass", f"h6wiki/{index:02d}-{suffix}",
                    metadata={"title": f"{title} h6wiki", "section": section, "subsection": subsection,
                              "type": page_type, "published": True, "reveal_after_session": reveal,
                              "display_order": 1 if index == 4 else 10000},
                    body_markdown="synthetic " * 880, commit=False,
                ))
        hidden_metadata = [
            {"published": False}, {"reveal_after_session": 5},
            {"section": "\tOvErViEw\u2003"}, {"type": "\tOVERVIEW\n"},
        ]
        for index in range(max(4, hidden_count)):
            metadata = {"title": "A h6wiki hidden", "section": "Sessions", "published": True}
            metadata.update(hidden_metadata[index % 4])
            records.append(store.upsert_page(
                "linden-pass", f"h6wiki/hidden-{index}", metadata=metadata,
                body_markdown="synthetic " * 880, commit=False,
            ))
        get_db().commit()
        expected = sorted(
            (record for record in records if campaign.is_page_visible(record.page)),
            key=lambda record: (*page_sort_key(record.page), record.page_ref),
        )[:30]
        complete_expected = sorted(
            (record for record in records if campaign.is_page_visible(record.page)),
            key=lambda record: (*page_sort_key(record.page), record.page_ref),
        )
        complete_actual = store.search_page_records("linden-pass", "h6wiki", limit=100, current_session=4)
        assert [record.page_ref for record in complete_actual] == [record.page_ref for record in complete_expected]
        hydrated = []
        original_map = store._map_record

        def observe(row, *, include_body):
            hydrated.append(row["page_ref"])
            assert ("body_markdown" in row.keys()) == include_body
            return original_map(row, include_body=include_body)

        monkeypatch.setattr(store, "_map_record", observe)
        reset_db_query_metrics()
        actual = store.search_page_records(
            "linden-pass", " H6WIKI ", limit=30, current_session=4, include_body=include_body,
        )
        assert [record.page_ref for record in actual] == [record.page_ref for record in expected]
        assert hydrated == [record.page_ref for record in expected]
        assert get_db_query_metrics()["query_count"] == 1
        assert all(bool(record.body_markdown) == include_body for record in actual)
        print(f"wiki hidden={hidden_count}: queries=1, hydrated={len(hydrated)}, body={include_body}")


def seed_wiki_search(app, *, hidden_count=1000, visible_count=30):
    # Seed the filesystem-backed fixture first; subsequent synthetic DB rows
    # must not be mistaken for stale rows during its initial mirror sync.
    app.extensions["repository_store"].get()
    store = app.extensions["campaign_page_store"]
    for index in range(hidden_count + visible_count):
        hidden = index < hidden_count
        metadata = {"title": f"{'A' if hidden else 'Z'} h6needle wiki {index:04d}", "section": "Notes", "published": True}
        if hidden:
            metadata.update((
                {"published": False}, {"reveal_after_session": 1000},
                {"section": "Overview"}, {"type": "overview"},
            )[index % 4])
        store.upsert_page(
            "linden-pass", f"h6search/{index:04d}", metadata=metadata,
            body_markdown="synthetic " * 880, commit=False,
        )
    get_db().commit()


@pytest.mark.parametrize("kind", ["wiki", "systems", "mixed"])
@pytest.mark.parametrize("hidden_count", [0, 1000])
def test_global_search_routes_fill_visible_cap_before_hidden_prefix(app, client, sign_in, users, monkeypatch, kind, hidden_count):
    with app.app_context():
        if kind in ("wiki", "mixed"):
            seed_wiki_search(app, hidden_count=hidden_count, visible_count=15 if kind == "mixed" else 30)
        if kind in ("systems", "mixed"):
            seed_systems_search(app, hidden_count=hidden_count, hidden_visibility="private")
    metrics = []

    @app.after_request
    def record_h6_global_metrics(response):
        metrics.append(dict(get_db_query_metrics()))
        return response

    sign_in(users["owner"]["email"], users["owner"]["password"])
    for _ in range(4):
        assert client.get("/campaigns/linden-pass/global-search?q=h6needle").status_code == 200
    hydrated = {"wiki": [], "systems": []}
    page_store, systems_store = app.extensions["campaign_page_store"], app.extensions["systems_store"]
    original_page_map, original_entry_map = page_store._map_record, systems_store._map_entry

    def observe_page(row, *, include_body):
        if row["page_ref"].startswith("h6search/"):
            hydrated["wiki"].append(row["page_ref"])
        return original_page_map(row, include_body=include_body)

    def observe_entry(row):
        if row is not None and row["source_id"] == "H6":
            hydrated["systems"].append(row["entry_key"])
        return original_entry_map(row)

    monkeypatch.setattr(page_store, "_map_record", observe_page)
    monkeypatch.setattr(systems_store, "_map_entry", observe_entry)
    response = client.get("/campaigns/linden-pass/global-search?q=h6needle")
    results = response.json["results"]
    expected_kinds = {"wiki": ["wiki"] * 30, "systems": ["systems"] * 30, "mixed": ["wiki"] * 15 + ["systems"] * 15}[kind]
    assert [row["kind"] for row in results] == expected_kinds
    assert all(row["title"].startswith("Z ") for row in results)
    assert len(response.data) <= 12288
    assert metrics[-1]["query_count"] <= (15 if kind == "wiki" else 220)
    assert len(hydrated["wiki"]) <= 30
    assert len(hydrated["systems"]) <= 60
    print(f"global {kind} hidden={hidden_count}: queries={metrics[-1]['query_count']}, bytes={len(response.data)}, hydrated={ {key: len(value) for key, value in hydrated.items()} }")


def test_session_wiki_and_native_api_staged_source_search_fill_cap(app, client, sign_in, users):
    with app.app_context():
        seed_wiki_search(app)
        seed_systems_search(app, hidden_visibility="private")
    token = issue_api_token(app, users["dm"]["email"], label="h6-staged-search")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    for path, headers in (
        ("/campaigns/linden-pass/session/wiki-lookup/search", {}),
        ("/campaigns/linden-pass/session/article-sources/search", {}),
        ("/api/v1/campaigns/linden-pass/session/article-sources/search", api_headers(token)),
    ):
        response = client.get(path, query_string={"q": "h6needle"}, headers=headers)
        assert response.status_code == 200
        results = response.json["results"]
        assert len(results) == 30
        assert all("wiki" in row["title"] and row["title"].startswith("Z ") for row in results)
        if "wiki-lookup" in path:
            assert len(response.data) <= 8192
    # With no matching Wiki records, the shared presenter fills from eligible Systems.
    for path, headers in (
        ("/campaigns/linden-pass/session/article-sources/search", {}),
        ("/api/v1/campaigns/linden-pass/session/article-sources/search", api_headers(token)),
    ):
        response = client.get(path, query_string={"q": "h6needle item"}, headers=headers)
        assert len(response.json["results"]) == 30
        assert all(row["source_kind"] == "systems" and row["title"].startswith("Z ") for row in response.json["results"])


def test_systems_native_api_search_preserve_250_visible_cap(app, client, sign_in, users):
    with app.app_context():
        _, _, expected = seed_systems_search(app, hidden_count=300, visible_count=260, hidden_visibility="private")
    token = issue_api_token(app, users["owner"]["email"], label="h6-systems-search")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    api_response = client.get("/api/v1/campaigns/linden-pass/systems/search?q=h6needle", headers=api_headers(token))
    assert api_response.status_code == 200
    assert [row["title"] for row in api_response.json["search_results"]] == expected[:250]
    native = client.get("/campaigns/linden-pass/systems/search?q=h6needle")
    assert native.status_code == 200
    body = native.get_data(as_text=True)
    assert expected[0] in body and expected[249] in body
    assert expected[250] not in body
    assert "A h6needle" not in body


def test_actual_character_picker_keeps_assignment_and_enabled_option_policy(app, client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players", systems="private")
    with app.app_context():
        _, _, expected = seed_systems_search(app, hidden_count=1000, visibility="private")
    path = f"/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}/equipment/systems-items/search?q=h6needle"
    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get(path)
    assert response.status_code == 200
    assert [row["title"] for row in response.json["results"]] == expected[:20]
    sign_in(users["party"]["email"], users["party"]["password"])
    assert client.get(path).status_code == 403


def seed_full_request_hydration_fixture(app):
    """Preserve the frozen H6 plain/crowded data, including unrelated Wiki rows."""
    page_store = app.extensions["campaign_page_store"]
    for crowded, token in ((False, "hbwikiplain"), (True, "hbwikicrowd")):
        for index in range(1030 if crowded else 30):
            hidden = crowded and index < 1000
            page_store.upsert_page(
                "linden-pass", f"npcs/{token}-{index:04}",
                metadata={"title": f"{token} {index:04}", "section": "NPCs",
                          "published": not hidden if index % 2 == 0 else True,
                          "reveal_after_session": 999 if hidden and index % 2 else 0,
                          "order": index},
                body_markdown="Synthetic search body. " * 400,
            )
    store = app.extensions["systems_store"]
    library = app.extensions["systems_service"].get_campaign_library_slug("linden-pass")
    source = "HB-BASELINE"
    store.upsert_source(
        library, source, title="Synthetic baseline", license_class="open_license",
        public_visibility_allowed=True, requires_unofficial_notice=False,
    )
    store.upsert_campaign_enabled_source(
        "linden-pass", library_slug=library, source_id=source,
        is_enabled=True, default_visibility="players",
    )
    entries = []
    for crowded, token in ((False, "hbsysplain"), (True, "hbsyscrowd")):
        for index in range(1030 if crowded else 30):
            entries.append({
                "entry_key": f"dnd-5e|spell|{source}|{token}-{index:04}",
                "entry_type": "spell", "slug": f"{token}-{index:04}",
                "title": f"{token} {index:04}", "source_path": "synthetic.json",
                "search_text": f"{token} {index:04}", "player_safe_default": True,
                "metadata": {}, "body": {"summary": "Synthetic system body. " * 400},
                "rendered_html": "<p>Synthetic system body.</p>",
            })
    store.replace_entries_for_source(library, source, entries=entries)
    for index in range(1000):
        store.upsert_campaign_entry_override(
            "linden-pass", library_slug=library,
            entry_key=f"dnd-5e|spell|{source}|hbsyscrowd-{index:04}",
            visibility_override="dm" if index % 2 else None,
            is_enabled_override=False if index % 2 == 0 else None,
        )


def observe_search_cursor_rows(monkeypatch):
    """Observe all target-request rows, including non-search seed/auth reads."""
    records = []
    original_execute = _InstrumentedCursor.execute

    def execute(cursor, sql, parameters=()):
        cursor.h6_observed_sql = sql
        return original_execute(cursor, sql, parameters)

    def capture(cursor, rows):
        sql = getattr(cursor, "h6_observed_sql", "")
        if has_request_context() and any(
            domain in sql.lower() for domain in ("campaign_pages", "systems_entries")
        ):
            records.append({
                "path": request.full_path, "sql": sql, "rows": len(rows),
                "columns": {column[0] for column in cursor.description or []},
            })
        return rows

    def fetchall(cursor):
        return capture(cursor, cursor._cursor.fetchall())

    def fetchone(cursor):
        row = cursor._cursor.fetchone()
        capture(cursor, [] if row is None else [row])
        return row

    monkeypatch.setattr(_InstrumentedCursor, "execute", execute)
    monkeypatch.setattr(_InstrumentedCursor, "fetchall", fetchall, raising=False)
    monkeypatch.setattr(_InstrumentedCursor, "fetchone", fetchone, raising=False)
    return records


@pytest.mark.parametrize("crowded", [False, True], ids=["plain-30", "hidden-1000-visible-30"])
def test_global_systems_request_bounds_all_full_rows_including_seed_sentinels(
    app, client, sign_in, users, monkeypatch, crowded,
):
    metrics = []

    @app.after_request
    def record_target_request_metrics(response):
        metrics.append(dict(get_db_query_metrics()))
        return response

    with app.app_context():
        app.extensions["campaign_session_service"].begin_session(
            "linden-pass", started_by_user_id=users["dm"]["id"],
        )
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={"display_name": "HB Peer Combat Guard", "turn_value": "11",
              "initiative_priority": "1", "dexterity_modifier": "2", "current_hp": "14",
              "max_hp": "16", "temp_hp": "0", "movement_total": "30"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        seed_full_request_hydration_fixture(app)
    sign_in(users["party"]["email"], users["party"]["password"])
    assert client.get("/campaigns/linden-pass/session").status_code == 200
    token = "hbsyscrowd" if crowded else "hbsysplain"
    path = f"/campaigns/linden-pass/global-search?q={token}"
    for _ in range(4):
        assert client.get(path).status_code == 200
    records = observe_search_cursor_rows(monkeypatch)
    response = client.get(path)
    assert response.status_code == 200
    expected = [f"{token} {index:04}" for index in (range(1000, 1030) if crowded else range(30))]
    assert [row["title"] for row in response.json["results"]] == expected
    assert {row["kind"] for row in response.json["results"]} == {"systems"}
    assert all(row["path"] == path for row in records)
    assert metrics[-1]["query_count"] <= 220
    assert len(response.data) <= 12288
    for domain in ("campaign_pages", "systems_entries"):
        selected = [row for row in records if domain in row["sql"].lower() and re.search(r"\blike\b", row["sql"], re.I)]
        assert sum(row["rows"] for row in selected) <= 30
    full_rows = sum(
        row["rows"] for row in records if "systems_entries" in row["sql"].lower()
        and {"body_json", "rendered_html"} & row["columns"]
    )
    print(f"{token}: all Systems full rows={full_rows}, queries={metrics[-1]['query_count']}, bytes={len(response.data)}")
    assert full_rows <= 60
    # The existing selected-result authorization still loads each of the 30
    # entries. Only the additional seed sentinel reads lose their full bodies.
    authorization_rows = sum(
        row["rows"] for row in records if "systems_entries" in row["sql"].lower()
        and re.search(r"\bslug\s*=\s*\?", row["sql"], re.I)
        and {"body_json", "rendered_html"} & row["columns"]
    )
    assert authorization_rows == 30
    assert full_rows == 60
    assert any(row["rows"] and row["columns"] == {"source_id", "metadata_json"} for row in records)
