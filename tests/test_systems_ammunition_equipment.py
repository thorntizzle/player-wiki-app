from copy import deepcopy

import pytest

from player_wiki.character_editor import normalize_custom_equipment_entry
from player_wiki.systems_importer import Dnd5eSystemsImporter
from tests.helpers.api_test_helpers import _advanced_editor_values, api_headers, issue_api_token
from tests.helpers.character_state_helpers import _character_state_revision, _read_character_definition
from tests.test_systems_ammunition_importer import AMMUNITION_BASES, write_ammunition_data_root


def seed_ammunition(app, tmp_path):
    root = write_ammunition_data_root(tmp_path / "synthetic-ammunition-equipment")
    with app.app_context():
        service, store = app.extensions["systems_service"], app.extensions["systems_store"]
        importer = Dnd5eSystemsImporter(store=store, systems_service=service, data_root=root)
        assert importer.import_source("DMG", entry_types=["item"]).imported_count == 40
        store.upsert_campaign_enabled_source(
            "linden-pass", library_slug="DND-5E", source_id="DMG", is_enabled=True, default_visibility="players",
        )
        return {entry.title: entry for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="item", limit=100) if entry.metadata.get("ammunition")}


def test_ammunition_family_search_preserves_all_tiers_units_and_caps(app, tmp_path):
    entries = seed_ammunition(app, tmp_path)
    with app.app_context():
        service = app.extensions["systems_service"]
        for tier in (1, 2, 3):
            expected = sorted(f"+{tier} {row[0]}" for row in AMMUNITION_BASES)
            matches = service.search_entries_for_campaign("linden-pass", query=f"ammunition +{tier}", limit=20)
            assert [entry.title for entry in matches] == expected
            for unit, count in (("single", 1), ("bundle", None)):
                unit_expected = sorted(f"+{tier} {row[0]}" for row in AMMUNITION_BASES if (row[4] == 1) == (count == 1))
                results = service.search_entries_for_campaign("linden-pass", query=f"+{tier} ammunition {unit}", limit=20)
                assert [entry.title for entry in results] == unit_expected
        assert [entry.title for entry in service.search_entries_for_campaign("linden-pass", query="ammunition", limit=20)] == sorted(entries)[:20]
        assert service.search_entries_for_campaign("linden-pass", query="ammunition", include_source_ids=["PHB"], limit=20) == []


def test_ordinary_equipment_normalization_retains_exact_link_without_title_recovery():
    existing = {
        "id": "manual-item-1", "name": "Curated display name", "default_quantity": 2,
        "weight": "1 lb.", "source_kind": "manual_edit",
        "systems_ref": {"entry_key": "dnd-5e|item|dmg|2modernbullets10", "slug": "dmg-item-2modernbullets10", "entry_type": "item", "title": "+2 Modern Bullets (10)", "source_id": "DMG"},
    }
    before = deepcopy(existing)
    item, quantity = normalize_custom_equipment_entry(name=existing["name"], quantity=3, weight=existing["weight"], existing_item=existing)
    assert item["systems_ref"] == existing["systems_ref"]
    assert item["id"] == existing["id"] and quantity == 3
    assert existing == before


@pytest.mark.parametrize("selection", [{}, {"page_ref": "items/replacement"}, {"systems_ref": {}}, {"page_ref": "items/replacement", "systems_ref": {"slug": "explicit-link"}}])
def test_equipment_link_preservation_keeps_explicit_relink_and_clear(selection):
    old_ref = {"slug": "dmg-item-1arrow", "entry_key": "dnd-5e|item|dmg|1arrow", "source_id": "DMG"}
    existing = {"id": "manual-linked", "systems_ref": old_ref}
    item, _ = normalize_custom_equipment_entry(name="Arrow", quantity=2, existing_item=existing, **selection)
    assert item.get("systems_ref") == (old_ref if not selection else selection.get("systems_ref") or None)


def test_ammunition_family_search_excludes_arbitrary_metadata_and_control_families(app, tmp_path):
    seed_ammunition(app, tmp_path)
    with app.app_context():
        store, service = app.extensions["systems_store"], app.extensions["systems_service"]
        store.upsert_source("DND-5E", "AMMO-CONTROL", title="Synthetic controls", license_class="custom_campaign", public_visibility_allowed=True)
        store.upsert_campaign_enabled_source("linden-pass", library_slug="DND-5E", source_id="AMMO-CONTROL", is_enabled=True, default_visibility="players")
        rows = []
        for index, metadata in enumerate((
            {"type": "M", "bonus_weapon": 1, "aliases": ["ammunition"]},
            {"type": "S", "bonus_ac": 2, "family": "ammunition"},
            {"type": "LA", "bonus_ac": 3, "notes": "ammunition +3 bundle"},
            {"ammunition": {"family": "secret-family", "tier": 2, "unit_kind": "single"}},
            {"ammunition": {"family": "ammunition", "tier": "2", "unit_kind": "single"}},
            {"ammunition": {"family": "ammunition", "tier": 4, "unit_kind": "single"}},
            {"ammunition": {"family": "ammunition", "tier": 2, "unit_kind": "secret-unit"}},
        )):
            rows.append({"entry_key": f"h12-control-{index}", "entry_type": "item", "slug": f"h12-control-{index}", "title": f"Control {index}", "metadata": metadata, "body": {"entries": ["ammunition +1 secret-prose"]}})
        store.replace_entries_for_source("DND-5E", "AMMO-CONTROL", entries=rows, entry_types=["item"])
        assert store.search_entries("DND-5E", query="ammunition", source_ids=["AMMO-CONTROL"]) == []
        for query in ("secret-family", "secret-unit", "secret-prose"):
            assert service.search_entries_for_campaign("linden-pass", query=query) == []
        assert len(store.search_entries("DND-5E", query="control", source_ids=["AMMO-CONTROL"])) == 7


def ammunition_record(app):
    with app.app_context():
        return app.extensions["character_repository"].get_character("linden-pass", "arden-march")


@pytest.mark.parametrize("tier", [1, 2, 3])
def test_all_ammunition_choices_add_and_survive_ordinary_save(app, client, sign_in, users, set_campaign_visibility, tmp_path, tier):
    entries = seed_ammunition(app, tmp_path)
    set_campaign_visibility("linden-pass", characters="players", systems="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    prefix = "/campaigns/linden-pass/characters/arden-march"
    api_path = "/api/v1/campaigns/linden-pass/characters/arden-march/advanced-editor"
    token = issue_api_token(app, users["owner"]["email"], label=f"h12-tier-{tier}")
    search = client.get(prefix + "/equipment/systems-items/search", query_string={"q": f"ammunition +{tier}"})
    assert search.status_code == 200
    assert {row["entry_slug"] for row in search.json["results"]} == {entries[f"+{tier} {base[0]}"].slug for base in AMMUNITION_BASES}
    expected = {}
    for index, (name, base_source, _type, projectile, count, weight) in enumerate(AMMUNITION_BASES):
        entry = entries[f"+{tier} {name}"]
        quantity = 1 + (index + tier - 1) % 3
        response = client.post(prefix + "/equipment/add-systems", data={
            "expected_revision": _character_state_revision(app, "arden-march"),
            "mode": "read", "page": "inventory", "entry_slug": entry.slug, "quantity": str(quantity),
        })
        assert response.status_code == 302
        record = ammunition_record(app)
        item = next(item for item in record.definition.equipment_catalog if (item.get("systems_ref") or {}).get("entry_key") == entry.entry_key)
        state_item = next(row for row in record.state_record.state["inventory"] if row["catalog_ref"] == item["id"])
        assert item["default_quantity"] == state_item["quantity"] == quantity
        assert float(item["weight"].split()[0]) == weight
        assert item["systems_ref"] == {"entry_key": entry.entry_key, "entry_type": "item", "title": entry.title, "slug": entry.slug, "source_id": "DMG"}
        assert entry.metadata["base_item"] == f"{name}|{base_source}"
        assert type(entry.metadata["bonus_weapon"]) is int and entry.metadata["bonus_weapon"] == tier
        assert entry.metadata["ammunition"]["projectiles_per_unit"] * quantity == count * quantity
        assert entry.metadata["weight"] * quantity == pytest.approx(weight * quantity)
        expected[item["id"]] = (deepcopy(item["systems_ref"]), item["weight"], quantity, deepcopy(entry.metadata))
    context_response = client.get(api_path, headers=api_headers(token))
    assert context_response.status_code == 200
    editor = context_response.json["editor"]
    values = _advanced_editor_values(editor)
    values["physical_description_markdown"] = "Synthetic ordinary save."
    first_row = next(row for row in editor["equipment_rows"] if row["id"] in expected)
    values[f"manual_item_name_{first_row['index']}"] = "Curated ammunition display name"
    if tier == 2:
        saved = client.put(api_path, headers=api_headers(token), json={"expected_revision": editor["state_revision"], "values": values})
        assert saved.status_code == 200
    else:
        saved = client.post(prefix + "/edit", data={**values, "expected_revision": editor["state_revision"]})
        assert saved.status_code == 302
    record = ammunition_record(app)
    persisted = _read_character_definition(app, "arden-march")
    items_by_id = {item["id"]: item for item in persisted["equipment_catalog"]}
    for item_id, (reference, weight, quantity, metadata) in expected.items():
        assert items_by_id[item_id]["systems_ref"] == reference
        assert items_by_id[item_id]["weight"] == weight
        assert items_by_id[item_id]["default_quantity"] == quantity
        assert next(row["quantity"] for row in record.state_record.state["inventory"] if row["catalog_ref"] == item_id) == quantity
        with app.app_context():
            linked = app.extensions["systems_service"].get_entry_for_campaign("linden-pass", reference["entry_key"])
            assert linked.metadata == metadata
    assert items_by_id[first_row["id"]]["name"] == "Curated ammunition display name"
    before_stale = (deepcopy(persisted), deepcopy(record.state_record))
    assert client.put(api_path, headers=api_headers(token), json={"expected_revision": editor["state_revision"], "values": values}).status_code == 409
    assert (_read_character_definition(app, "arden-march"), ammunition_record(app).state_record) == before_stale
    # Later inventory saves count selected catalog units, including bundles.
    for item_id, (reference, weight, quantity, metadata) in expected.items():
        current = ammunition_record(app)
        state_item = next(row for row in current.state_record.state["inventory"] if row["catalog_ref"] == item_id)
        updated = client.patch(
            f"/api/v1/campaigns/linden-pass/characters/arden-march/session/inventory/{state_item['id']}",
            headers=api_headers(token), json={"expected_revision": current.state_record.revision, "quantity": quantity + 2},
        )
        assert updated.status_code == 200
        projected = next(row for row in updated.json["character"]["presented_inventory"] if row["item_ref"] == item_id)
        assert projected["quantity"] == quantity + 2
        assert projected["weight"] == weight
        reloaded = ammunition_record(app)
        assert next(row["quantity"] for row in reloaded.state_record.state["inventory"] if row["catalog_ref"] == item_id) == quantity + 2
        assert _read_character_definition(app, "arden-march") == before_stale[0]
        with app.app_context():
            linked = app.extensions["systems_service"].get_entry_for_campaign("linden-pass", reference["entry_key"])
            assert linked.metadata == metadata


def test_ammunition_picker_and_add_refuse_disabled_entry_and_source(app, client, sign_in, users, set_campaign_visibility, tmp_path):
    entries = seed_ammunition(app, tmp_path)
    set_campaign_visibility("linden-pass", characters="players", systems="private")
    entry = entries["+2 Modern Bullets (10)"]
    prefix = "/campaigns/linden-pass/characters/arden-march"
    sign_in(users["owner"]["email"], users["owner"]["password"])
    for disabled_source in (False, True):
        with app.app_context():
            store = app.extensions["systems_store"]
            store.upsert_campaign_entry_override("linden-pass", library_slug="DND-5E", entry_key=entry.entry_key, visibility_override=None, is_enabled_override=None if disabled_source else False)
            store.upsert_campaign_enabled_source("linden-pass", library_slug="DND-5E", source_id="DMG", is_enabled=not disabled_source, default_visibility="players")
        search = client.get(prefix + "/equipment/systems-items/search", query_string={"q": "+2 modern"})
        assert entry.slug not in {row["entry_slug"] for row in search.json["results"]}
        record = ammunition_record(app)
        before = (deepcopy(record.definition.to_dict()), deepcopy(record.state_record))
        refused = client.post(prefix + "/equipment/add-systems", data={"expected_revision": record.state_record.revision, "entry_slug": entry.slug, "quantity": 2, "mode": "read", "page": "inventory"})
        assert refused.status_code == 302
        current = ammunition_record(app)
        assert (current.definition.to_dict(), current.state_record) == before


@pytest.mark.parametrize(("actor", "expected_status"), [("party", 403), ("observer", 404), ("outsider", 404)])
def test_ammunition_picker_and_add_keep_character_assignment_boundary(app, client, sign_in, users, set_campaign_visibility, tmp_path, actor, expected_status):
    entries = seed_ammunition(app, tmp_path)
    set_campaign_visibility("linden-pass", characters="players", systems="players")
    before = ammunition_record(app)
    sign_in(users[actor]["email"], users[actor]["password"])
    prefix = "/campaigns/linden-pass/characters/arden-march"
    assert client.get(prefix + "/equipment/systems-items/search?q=ammunition").status_code == expected_status
    assert client.post(prefix + "/equipment/add-systems", data={"expected_revision": before.state_record.revision, "entry_slug": entries["+1 Modern Bullet"].slug, "quantity": 2}).status_code == expected_status
    current = ammunition_record(app)
    assert current.definition.to_dict() == before.definition.to_dict()
    assert current.state_record == before.state_record
