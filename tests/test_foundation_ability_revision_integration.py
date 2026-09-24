"""Known ability inputs survive source revisions through real warm read caches."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from flask import Flask

from player_wiki.campaign_item_mechanics import build_campaign_item_mechanics_metadata
from player_wiki.character_ability_inputs import KEYS, input_records, seed_base_inputs
from player_wiki.character_builder_catalogs import (
    _build_targeted_item_support_catalog,
    _clear_builder_static_bundle_cache,
)
from player_wiki.character_mechanics_projection import (
    _clear_normalized_definition_cache,
    build_character_mechanics_projection,
)
from player_wiki.character_read_projection import (
    build_character_read_projection_cache_key,
    load_cached_character_read_projection,
    reset_character_read_projection_cache_for_tests,
)
from player_wiki.db import close_db, init_database
from player_wiki.models import Campaign
from player_wiki.systems_service import SystemsService
from player_wiki.systems_store import SystemsStore
from tests.helpers.character_builder_fakes import _minimal_character_definition, _systems_ref


LIBRARY = "FOUNDATION-X1"
ENTRY = "item|foundation-x1|strength-stone"


class _Repository:
    def __init__(self):
        self.campaign = Campaign(
            title="Foundation integration", slug="foundation-x1", summary="",
            system="DND-5E", current_session=1, source_wiki_root="",
            player_content_dir="", assets_dir="", systems_library_slug=LIBRARY,
        )

    def get(self):
        return self

    def get_campaign(self, slug):
        assert slug == self.campaign.slug
        return self.campaign


def _upsert_stone(store, minimum):
    return store.upsert_entry(
        LIBRARY, "TEST", entry_key=ENTRY, entry_type="item",
        slug="strength-stone", title="Strength Stone", player_safe_default=True,
        metadata=build_campaign_item_mechanics_metadata(
            title="Strength Stone", body_markdown="",
            explicit_mechanics={"ability_score_minimums": {"str": minimum}} if minimum else {},
            source_page_ref="items/strength-stone", review_status="approved",
        ), body={},
    )


@pytest.fixture
def integration_app(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "player_wiki.systems_store.utcnow",
        lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    app = Flask(__name__)
    app.config.update(DB_PATH=tmp_path / "foundation.sqlite3", TESTING=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_database()
        store = SystemsStore()
        store.upsert_library(LIBRARY, title="Foundation integration", system_code="DND-5E")
        store.upsert_source(LIBRARY, "TEST", title="Test", license_class="srd_cc")
        store.upsert_campaign_policy("foundation-x1", library_slug=LIBRARY)
        store.upsert_campaign_enabled_source(
            "foundation-x1", library_slug=LIBRARY, source_id="TEST",
            is_enabled=True, default_visibility="players",
        )
        _upsert_stone(store, 14)
    _clear_builder_static_bundle_cache()
    _clear_normalized_definition_cache()
    reset_character_read_projection_cache_for_tests()
    yield app
    reset_character_read_projection_cache_for_tests()
    _clear_normalized_definition_cache()
    _clear_builder_static_bundle_cache()


@pytest.mark.parametrize("scoped", [False, True], ids=["full", "scoped"])
@pytest.mark.parametrize("prefetched", [False, True], ids=["direct", "prefetched"])
def test_source_revision_preserves_saturated_input_through_warm_projection_caches(integration_app, scoped, prefetched):
    repository = _Repository()
    campaign = repository.campaign
    service = SystemsService(SystemsStore(), repository).character_read_view()
    state = {"vitals": {"current_hp": 7, "temp_hp": 2}}
    scope = {
        "components": frozenset(), "catalog_components": frozenset(),
        "derivation_components": frozenset({"item_ability_minimums"}),
    } if scoped else {}
    definition = _minimal_character_definition()
    definition.campaign_slug = campaign.slug
    scores = {key: 10 for key in KEYS}
    scores["str"] = 8
    for key, value in scores.items():
        definition.stats["ability_scores"][key] = {
            "score": value, "modifier": (value - 10) // 2, "save_bonus": (value - 10) // 2,
        }
    seed_base_inputs(definition.stats, scores, provenance="synthetic_author")
    definition.stats["recoverable_penalties"] = [{
        "id": "drain", "kind": "ability_score", "ability_key": "str",
        "amount": 20, "source": "Synthetic drain",
    }]

    def project(source):
        projected = build_character_mechanics_projection(
            campaign=campaign, definition=source, state=state,
            systems_service=service, campaign_page_records=[], **scope,
        )
        assert not projected.get("projection_warnings")
        assert projected["state"]["vitals"]["current_hp"] == 7
        assert projected["state"]["vitals"]["temp_hp"] == 2
        return projected["definition"]

    def cache_key(source):
        return build_character_read_projection_cache_key(
            "foundation-integration-" + str(scoped), campaign_slug=campaign.slug,
            record=SimpleNamespace(definition=source, state_record=SimpleNamespace(revision=1)),
            systems_service=service, campaign_page_records=[],
            campaign_current_session=1, effective_visibility="players",
        )

    def assert_strength(projected, effective, pre_penalty):
        assert projected.stats["ability_scores"]["str"]["score"] == effective
        row = input_records(projected.stats)["str"]
        assert row["stage"] == "base"
        assert row["score"] == 8
        assert row["pre_penalty"] == pre_penalty
        assert row["provenance"] == "synthetic_author"

    with integration_app.test_request_context("/"):
        store = SystemsStore()
        before_entry = store.get_entry(LIBRARY, ENTRY)
        definition.equipment_catalog = [{
            "id": "stone", "name": before_entry.title, "default_quantity": 1,
            "is_equipped": True, "is_attuned": True, "systems_ref": _systems_ref(before_entry),
        }]
        if prefetched:
            catalog = _build_targeted_item_support_catalog(
                definition.equipment_catalog, campaign_slug=campaign.slug,
                systems_service=service, campaign_page_records=[],
            )
            service.set_enabled_entry_subset_for_request(
                campaign.slug, entry_type="item", entries=list(catalog["entries"]),
                source_generation=catalog["systems_source_generation"],
            )
        original = deepcopy(definition.to_dict())
        before_token = store.get_durable_revision()
        warm = project(definition)
        assert_strength(warm, 0, 14)
        assert_strength(project(warm), 0, 14)
        assert_strength(project(definition), 0, 14)

        builds = []
        def build_metadata():
            builds.append(True)
            return {"stats": deepcopy(project(definition).stats)}

        old_key = cache_key(definition)
        assert old_key is not None
        prepared = load_cached_character_read_projection(old_key, build_metadata)
        prepared["stats"]["ability_scores"]["str"]["score"] = 99
        assert load_cached_character_read_projection(old_key, build_metadata)["stats"]["ability_scores"]["str"]["score"] == 0
        assert len(builds) == 1

        after_entry = _upsert_stone(store, 18)
        assert after_entry.id == before_entry.id
        assert after_entry.updated_at == before_entry.updated_at
        assert store.get_durable_revision() != before_token
        changed = project(definition)
        assert_strength(changed, 0, 18)
        assert_strength(project(warm), 0, 18)
        # A retained key must rebuild, even though displayed STR is still zero.
        prepared = load_cached_character_read_projection(old_key, build_metadata)
        assert input_records(prepared["stats"])["str"]["pre_penalty"] == 18
        assert len(builds) == 2
        current_key = cache_key(definition)
        assert current_key != old_key
        load_cached_character_read_projection(current_key, build_metadata)
        load_cached_character_read_projection(current_key, build_metadata)
        assert len(builds) == 3

        changed.stats["recoverable_penalties"] = []
        recovered = project(changed)
        assert_strength(recovered, 18, 18)
        _upsert_stone(store, None)
        restored = project(recovered)
        assert_strength(restored, 8, 8)
        assert_strength(project(restored), 8, 8)
        assert definition.to_dict() == original
        assert state == {"vitals": {"current_hp": 7, "temp_hp": 2}}

    with integration_app.test_request_context("/"):
        assert_strength(project(restored), 8, 8)
