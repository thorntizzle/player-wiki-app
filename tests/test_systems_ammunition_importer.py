from copy import deepcopy
import json

import pytest

from player_wiki.systems_importer import Dnd5eSystemsImporter


# Synthetic mechanics-only fixture; no source-book prose.
AMMUNITION_BASES = (
    ("Arrow", "PHB", "A", "Arrow", 1, 0.05),
    ("Arrows (20)", "PHB", "A", "Arrow", 20, 1),
    ("Blowgun Needle", "PHB", "A", "Blowgun Needle", 1, 0.02),
    ("Blowgun Needles (50)", "PHB", "A", "Blowgun Needle", 50, 1),
    ("Crossbow Bolt", "PHB", "A", "Crossbow Bolt", 1, 0.075),
    ("Crossbow Bolts (20)", "PHB", "A", "Crossbow Bolt", 20, 1.5),
    ("Sling Bullet", "PHB", "A", "Sling Bullet", 1, 0.075),
    ("Sling Bullets (20)", "PHB", "A", "Sling Bullet", 20, 1.5),
    ("Modern Bullet", "DMG", "AF|DMG", "Modern Bullet", 1, 0.1),
    ("Modern Bullets (10)", "DMG", "AF|DMG", "Modern Bullet", 10, 1),
    ("Renaissance Bullet", "DMG", "AF|DMG", "Renaissance Bullet", 1, 0.2),
    ("Renaissance Bullets (10)", "DMG", "AF|DMG", "Renaissance Bullet", 10, 2),
)


def ammunition_base_rows(*, edition="classic"):
    rows = []
    for name, source, item_type, projectile, count, weight in AMMUNITION_BASES:
        row = {"name": name, "source": source, "type": item_type, "weight": weight}
        if edition is not None:
            row["edition"] = edition
        if count > 1:
            member = projectile.lower() + ("|phb" if source == "PHB" else "")
            row["packContents"] = [{"item": member, "quantity": count}]
        rows.append(row)
    return rows


def ammunition_variants(*, edition="classic"):
    rows = []
    for tier in (1, 2, 3):
        row = {
            "name": f"+{tier} Ammunition",
            "type": "GV|DMG",
            "requires": [{"type": "A"}, {"type": "AF|DMG"}, {"type": "A|XPHB"}, {"type": "AF|XDMG"}],
            "inherits": {"source": "DMG", "namePrefix": f"+{tier} ", "bonusWeapon": f"+{tier}", "rarity": "uncommon", "entries": ["Synthetic ammunition reference."]},
        }
        if edition is not None:
            row["edition"] = edition
        rows.append(row)
    return rows


def write_ammunition_data_root(root, *, bases=None, variants=None):
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data/items-base.json").write_text(json.dumps({"baseitem": ammunition_base_rows() if bases is None else bases}), encoding="utf-8")
    (root / "data/magicvariants.json").write_text(json.dumps({"magicvariant": ammunition_variants() if variants is None else variants}), encoding="utf-8")
    return root


def pure_importer(tmp_path, *, bases=None):
    return Dnd5eSystemsImporter(store=None, systems_service=None, data_root=write_ammunition_data_root(tmp_path, bases=bases))


@pytest.mark.parametrize("edition", ["classic", None])
def test_all_36_ammunition_variants_preserve_selected_unit_and_source(tmp_path, edition):
    importer = pure_importer(tmp_path, bases=ammunition_base_rows(edition=edition))
    rows = importer._build_magicvariant_raw_entries(ammunition_variants(edition=edition), "DMG")
    assert len(rows) == 36
    by_name = {row["name"]: row for row in rows}
    for tier in (1, 2, 3):
        for name, source, item_type, projectile, count, weight in AMMUNITION_BASES:
            raw = by_name[f"+{tier} {name}"]
            metadata, _body, _html = importer._build_generic_content("item", raw)
            assert raw["source"] == "DMG"
            assert metadata["base_item"] == f"{name}|{source}"
            assert metadata["weight"] == weight
            assert metadata["type"] == item_type
            assert metadata["bonus_weapon"] == tier
            assert metadata["ammunition"] == {
                "family": "ammunition", "tier": tier,
                "unit_kind": "single" if count == 1 else "bundle",
                "unit_label": name, "projectiles_per_unit": count,
                "projectile_name": projectile, "projectile_source": source,
            }
            assert metadata["pack_contents"] == ([] if count == 1 else [{"item": f"{projectile}|{source}", "quantity": count}])
            for quantity in (1, 2, 3):
                assert metadata["weight"] * quantity == weight * quantity
                assert metadata["ammunition"]["projectiles_per_unit"] * quantity == count * quantity


@pytest.mark.parametrize("edition", ["classic", None])
def test_ammunition_import_and_reimport_keep_all_concrete_identities(app, tmp_path, edition):
    root = write_ammunition_data_root(tmp_path / "synthetic-ammunition", bases=ammunition_base_rows(edition=edition), variants=ammunition_variants(edition=edition))
    with app.app_context():
        store = app.extensions["systems_store"]
        importer = Dnd5eSystemsImporter(store=store, systems_service=app.extensions["systems_service"], data_root=root)
        result = importer.import_source("DMG", entry_types=["item"])
        assert result.imported_count == 40  # Four mundane DMG bullet units plus 36 variants.
        entries = store.list_entries_for_source("DND-5E", "DMG", entry_type="item", limit=100)
        variants = {entry.title: entry for entry in entries if "ammunition" in entry.metadata}
        assert len(variants) == 36
        expected = {}
        for tier in (1, 2, 3):
            for name, source, _type, _projectile, count, weight in AMMUNITION_BASES:
                title = f"+{tier} {name}"
                entry = variants[title]
                stem = "".join(character.lower() for character in title if character.isalnum())
                assert entry.entry_key == f"dnd-5e|item|dmg|{stem}"
                assert entry.slug == f"dmg-item-{stem}"
                assert entry.source_id == "DMG"
                assert entry.metadata["base_item"] == f"{name}|{source}"
                assert entry.metadata["ammunition"]["projectiles_per_unit"] == count
                assert entry.metadata["weight"] == weight
                assert entry.metadata["bonus_weapon"] == tier
                expected[entry.entry_key] = (entry.slug, entry.title, entry.metadata, entry.body)
        repeated = importer.import_source("DMG", entry_types=["item"])
        assert repeated.imported_count == result.imported_count
        actual = {entry.entry_key: (entry.slug, entry.title, entry.metadata, entry.body) for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="item", limit=100) if "ammunition" in entry.metadata}
        assert actual == expected


@pytest.mark.parametrize("base_index,updates", [
    (0, {"source": "XPHB"}), (0, {"source": "DMG"}),
    (8, {"source": "PHB"}), (8, {"source": "XDMG"}),
    (0, {"source": "UNKNOWN"}), (0, {"edition": "one"}),
    (0, {"edition": "EFA"}), (0, {"type": "A|XPHB"}),
    (8, {"type": "AF|XDMG"}), (0, {"type": "M"}),
    (8, {"name": "Energy Cell"}), (0, {"name": "Quiver of Arrows"}),
    (0, {"name": "arrow"}), (0, {"weight": -1}),
    (0, {"weight": 0}), (0, {"weight": None}),
    (0, {"weight": True}), (0, {"weight": "0.05"}),
    (0, {"packContents": [{"item": "arrow|phb", "quantity": 20}]}),
    (1, {"packContents": None}), (1, {"packContents": []}),
    (1, {"packContents": {"item": "arrow|phb", "quantity": 20}}),
    (1, {"packContents": ["arrow|phb"]}),
    (1, {"packContents": [{"item": "arrow|phb", "quantity": 19}]}),
    (1, {"packContents": [{"item": "arrow|phb", "quantity": "20"}]}),
    (1, {"packContents": [{"item": "arrow|phb", "quantity": True}]}),
    (1, {"packContents": [{"item": "arrow|phb", "quantity": 20.0}]}),
    (1, {"packContents": [{"item": "crossbow bolt|phb", "quantity": 20}]}),
    (1, {"packContents": [{"item": "arrow|xphb", "quantity": 20}]}),
    (1, {"packContents": [{"item": "arrow|", "quantity": 20}]}),
    (1, {"packContents": [{"item": "arrow|phb|alias", "quantity": 20}]}),
    (1, {"packContents": [{"item": "arrow|phb", "quantity": 20}, {"item": "sling bullet|phb", "quantity": 20}]}),
    (9, {"packContents": [{"item": "modern bullet|phb", "quantity": 10}]}),
    (11, {"packContents": [{"item": "modern bullet", "quantity": 10}]}),
])
def test_unapproved_or_malformed_ammunition_bases_are_excluded(tmp_path, base_index, updates):
    base = ammunition_base_rows()[base_index]
    base.update(deepcopy(updates))
    importer = pure_importer(tmp_path, bases=[base])
    assert importer._build_magicvariant_raw_entries(ammunition_variants(), "DMG") == []


@pytest.mark.parametrize("updates,inherit_updates", [
    ({"edition": "one"}, {}), ({"edition": "XDMG"}, {}),
    ({"name": "+4 Ammunition"}, {}), ({"name": "1 Ammunition"}, {}),
    ({"name": "Ammunition +1"}, {}), ({"name": "Ammunition of Slaying"}, {}),
    ({}, {"source": "XDMG"}), ({}, {"source": "XPHB"}),
    ({}, {"source": "UNKNOWN"}), ({}, {"source": "EFA"}),
    ({"source": "UNKNOWN"}, {}), ({}, {"edition": "one"}),
    ({}, {"bonusWeapon": "+4"}), ({}, {"bonusWeapon": "+2"}),
    ({}, {"bonusWeapon": None}), ({}, {"bonusWeapon": True}),
    ({}, {"namePrefix": "+2 "}), ({}, {"nameSuffix": " of Slaying"}),
    ({}, {"weight": 999}), ({}, {"type": "A|XPHB"}),
    ({"requires": [{"type": "M"}]}, {}), ({"excludes": [{"ammo": True}]}, {}),
])
def test_unapproved_or_malformed_ammunition_families_are_excluded(tmp_path, updates, inherit_updates):
    variant = ammunition_variants()[0]
    variant.update(deepcopy(updates))
    variant["inherits"].update(deepcopy(inherit_updates))
    importer = pure_importer(tmp_path)
    assert importer._build_magicvariant_raw_entries([variant], "DMG") == []


def test_existing_armor_shield_weapon_expansion_stays_unchanged(tmp_path):
    bases = [
        {"name": "Chain Mail", "source": "PHB", "type": "HA", "armor": True, "ac": 16, "weight": 55},
        {"name": "Shield", "source": "PHB", "type": "S", "ac": 2, "weight": 6},
        {"name": "Longsword", "source": "PHB", "type": "M", "weapon": True, "dmg1": "1d8", "dmgType": "S", "weight": 3},
    ]
    variants = []
    for tier in (1, 2, 3):
        for family, item_type, bonus in (("Armor", "HA", "bonusAc"), ("Shield (*)", "S", "bonusAc"), ("Weapon", "M", "bonusWeapon")):
            variants.append({"name": f"+{tier} {family}", "edition": "classic", "requires": [{"type": item_type}], "inherits": {"source": "DMG", "namePrefix": f"+{tier} ", bonus: f"+{tier}"}})
    importer = pure_importer(tmp_path, bases=bases)
    rows = importer._build_magicvariant_raw_entries(variants, "DMG")
    assert len(rows) == 9
    for raw in rows:
        metadata, _body, _html = importer._build_generic_content("item", raw)
        assert "ammunition" not in metadata
        assert "pack_contents" not in metadata
        assert "bonus_weapon" not in metadata  # Existing generic weapon projection is unchanged.
        base = next(base for base in bases if raw["baseItem"] == f"{base['name']}|PHB")
        assert metadata["weight"] == base["weight"]
        assert metadata["ac"] == base.get("ac")
        if base["type"] in ("HA", "S"):
            assert metadata["bonus_ac"] == raw["bonusAc"]
