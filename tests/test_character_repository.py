from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
import shutil

import pytest
import yaml

import player_wiki.character_repository as character_repository_module
from tests.sample_data import TEST_CAMPAIGN_SLUG


def _character_definition_path(app, character_slug: str) -> Path:
    return (
        app.config["TEST_CAMPAIGNS_DIR"]
        / TEST_CAMPAIGN_SLUG
        / "characters"
        / character_slug
        / "definition.yaml"
    )


def _character_import_path(app, character_slug: str) -> Path:
    return _character_definition_path(app, character_slug).with_name("import.yaml")


def test_combat_seed_exact_read_is_active_complete_and_reads_state_once_without_initializing(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    with app.app_context():
        assert repository.get_visible_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        ) is not None
    state_reads = {"count": 0}
    original_get_state = repository.state_store.get_state

    def get_state(*args, **kwargs):
        state_reads["count"] += 1
        return original_get_state(*args, **kwargs)

    def fail_state_initialization(*_args, **_kwargs):
        raise AssertionError("combat seed read initialized character state")

    monkeypatch.setattr(repository.state_store, "get_state", get_state)
    monkeypatch.setattr(
        repository.state_store,
        "initialize_state_if_missing",
        fail_state_initialization,
    )
    with app.app_context():
        record = repository.get_combat_seed_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        )

    assert record is not None
    assert record.definition.character_slug == "arden-march"
    assert record.definition.status == "active"
    assert state_reads["count"] == 1


def test_combat_seed_exact_read_rejects_missing_state_without_initializing(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    state_reads = {"count": 0}

    def missing_state(*_args, **_kwargs):
        state_reads["count"] += 1
        return None

    def fail_state_initialization(*_args, **_kwargs):
        raise AssertionError("combat seed read initialized missing character state")

    monkeypatch.setattr(repository.state_store, "get_state", missing_state)
    monkeypatch.setattr(
        repository.state_store,
        "initialize_state_if_missing",
        fail_state_initialization,
    )
    with app.app_context():
        assert repository.get_combat_seed_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        ) is None
    assert state_reads["count"] == 1


def test_combat_seed_exact_read_rejects_missing_inactive_and_reconciliation_protected(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    with app.app_context():
        assert repository.get_visible_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        ) is not None
        assert repository.get_combat_seed_character(
            TEST_CAMPAIGN_SLUG,
            "not-a-character",
        ) is None

    definition_path = _character_definition_path(app, "arden-march")
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    payload["status"] = "archived"
    definition_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    repository.invalidate_character(TEST_CAMPAIGN_SLUG, "arden-march")
    with app.app_context():
        assert repository.get_combat_seed_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        ) is None

    payload["status"] = "active"
    definition_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    repository.invalidate_character(TEST_CAMPAIGN_SLUG, "arden-march")
    monkeypatch.setattr(repository, "_is_reconciliation_protected", lambda *_args: True)
    with app.app_context():
        assert repository.get_combat_seed_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        ) is None


def test_combat_seed_exact_read_requires_complete_definition_and_import_pair(app):
    repository = app.extensions["character_repository"]
    import_path = _character_import_path(app, "arden-march")
    import_path.unlink()

    assert repository.get_combat_seed_character(
        TEST_CAMPAIGN_SLUG,
        "arden-march",
    ) is None


def test_get_visible_character_reuses_cached_yaml_payloads_when_signatures_are_unchanged(app, monkeypatch):
    repository = app.extensions["character_repository"]
    calls = {"count": 0}
    original_load = repository._load_yaml_payload

    def spy(path: Path, payload: bytes | None = None) -> dict[str, object]:
        calls["count"] += 1
        return original_load(path, payload)

    monkeypatch.setattr(repository, "_load_yaml_payload", spy)

    with app.app_context():
        repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")
        repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")

    assert calls["count"] == 2


def test_cached_character_payloads_remain_detached_after_record_mutation(app):
    repository = app.extensions["character_repository"]

    with app.app_context():
        first = repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")
        assert first is not None
        first.definition.profile["classes"][0]["class_name"] = "Mutated"
        first.definition.features[0]["name"] = "Mutated feature"

        cached = repository._character_payload_cache[
            (TEST_CAMPAIGN_SLUG, "arden-march")
        ]
        assert cached.definition_payload["profile"]["classes"][0]["class_name"] != "Mutated"
        assert cached.definition_payload["features"][0]["name"] != "Mutated feature"

        second = repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")

    assert second is not None
    assert second.definition.profile["classes"][0]["class_name"] != "Mutated"
    assert second.definition.features[0]["name"] != "Mutated feature"


def test_get_visible_character_refreshes_cached_yaml_payloads_when_definition_changes(app):
    repository = app.extensions["character_repository"]
    definition_path = _character_definition_path(app, "arden-march")

    with app.app_context():
        first = repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")
        assert first is not None
        assert first.definition.name == "Arden March"

    original_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    mutated_payload = deepcopy(original_payload)
    mutated_payload["name"] = "Arden March (Updated)"
    definition_path.write_text(yaml.safe_dump(mutated_payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        second = repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")
        assert second is not None
        assert second.definition.name == "Arden March (Updated)"


def test_character_payload_cache_and_snapshot_token_detect_same_stat_replacements(app):
    repository = app.extensions["character_repository"]
    definition_path = _character_definition_path(app, "arden-march")
    import_path = _character_import_path(app, "arden-march")

    with app.app_context():
        baseline_record = repository.get_visible_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        )
    baseline_token = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
    )
    assert baseline_record is not None
    assert baseline_token is not None

    def replace_with_same_stat(path: Path, old: bytes, new: bytes) -> None:
        original_stat = path.stat()
        original_payload = path.read_bytes()
        replacement_payload = original_payload.replace(old, new, 1)
        assert replacement_payload != original_payload
        assert len(replacement_payload) == len(original_payload)
        replacement = path.with_name(f"{path.name}.replacement")
        replacement.write_bytes(replacement_payload)
        os.utime(
            replacement,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        os.replace(replacement, path)
        assert repository._file_signature(path) == (
            original_stat.st_mtime_ns,
            original_stat.st_size,
        )

    replace_with_same_stat(
        definition_path,
        b"name: Arden March",
        b"name: Arden Marsh",
    )
    with app.app_context():
        definition_changed_record = repository.get_visible_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        )
    definition_changed_token = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
        previous=baseline_token,
    )
    assert definition_changed_record is not None
    assert definition_changed_record.definition.name == "Arden Marsh"
    assert definition_changed_token is not None
    assert definition_changed_token != baseline_token

    replace_with_same_stat(
        import_path,
        b"parser_version: fixture",
        b"parser_version: mixture",
    )
    with app.app_context():
        import_changed_record = repository.get_visible_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        )
    import_changed_token = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
        previous=definition_changed_token,
    )
    assert import_changed_record is not None
    assert import_changed_record.import_metadata.parser_version == "mixture"
    assert import_changed_token is not None
    assert import_changed_token != definition_changed_token


def test_character_reads_reuse_revision_checked_campaign_config(app, monkeypatch):
    repository = app.extensions["character_repository"]
    real_load = character_repository_module._campaign_character_config_from_bytes
    config_loads: list[str] = []

    def tracked_load(config_path, campaign_slug, payload):
        config_loads.append(campaign_slug)
        return real_load(config_path, campaign_slug, payload)

    monkeypatch.setattr(
        character_repository_module,
        "_campaign_character_config_from_bytes",
        tracked_load,
    )

    with app.app_context():
        assert repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")
        assert repository.list_visible_characters(TEST_CAMPAIGN_SLUG)
        assert repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")

    assert config_loads == [TEST_CAMPAIGN_SLUG]
    config = repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)
    with pytest.raises(FrozenInstanceError):
        config.system = "Mutated"


def test_list_characters_content_validates_campaign_config_once_for_nested_loads(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    repository._campaign_config_cache.clear()
    campaign_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / TEST_CAMPAIGN_SLUG
        / "campaign.yaml"
    ).resolve()
    original_read_bytes = Path.read_bytes
    config_reads: list[Path] = []
    nested_configs = []
    original_load_character = repository._load_character

    def tracked_read_bytes(path: Path) -> bytes:
        if path.resolve() == campaign_path:
            config_reads.append(path)
        return original_read_bytes(path)

    def tracked_load_character(*args, **kwargs):
        nested_configs.append(kwargs.get("campaign_config"))
        return original_load_character(*args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
    monkeypatch.setattr(repository, "_load_character", tracked_load_character)

    with app.app_context():
        records = repository.list_characters(TEST_CAMPAIGN_SLUG)

    assert len(records) >= 2
    assert config_reads == [campaign_path]
    assert len(nested_configs) >= 2
    assert all(config is nested_configs[0] for config in nested_configs)


def test_character_config_cache_refreshes_on_campaign_file_signature_change(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    campaign_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / TEST_CAMPAIGN_SLUG
        / "campaign.yaml"
    )
    real_load = character_repository_module._campaign_character_config_from_bytes
    config_loads: list[str] = []

    def tracked_load(config_path, campaign_slug, payload):
        config_loads.append(campaign_slug)
        return real_load(config_path, campaign_slug, payload)

    monkeypatch.setattr(
        character_repository_module,
        "_campaign_character_config_from_bytes",
        tracked_load,
    )

    with app.app_context():
        assert repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")
    campaign_payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    campaign_payload["system"] = "Xianxia"
    campaign_payload["character_dir"] = "characters"
    campaign_payload["character_source_root"] = "changed-source"
    campaign_payload["character_source_glob"] = "**/*Character*.md"
    campaign_path.write_text(
        yaml.safe_dump(campaign_payload, sort_keys=False),
        encoding="utf-8",
    )
    with app.app_context():
        assert repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")

    assert config_loads == [TEST_CAMPAIGN_SLUG, TEST_CAMPAIGN_SLUG]
    refreshed = repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)
    assert refreshed.system == "Xianxia"
    assert refreshed.characters_dir == campaign_path.parent / "characters"
    assert refreshed.source_root == Path("changed-source")
    assert refreshed.source_glob == "**/*Character*.md"


def test_campaign_config_digest_detects_atomic_same_stat_replacement(app):
    repository = app.extensions["character_repository"]
    campaign_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / TEST_CAMPAIGN_SLUG
        / "campaign.yaml"
    )
    original_stat = campaign_path.stat()
    original_payload = campaign_path.read_bytes()
    changed_payload = original_payload.replace(
        b"slug: linden-pass",
        b"slug: linden-past",
        1,
    )
    assert len(changed_payload) == len(original_payload)

    original = repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)
    replacement = campaign_path.with_name("campaign-replacement.yaml")
    replacement.write_bytes(changed_payload)
    os.utime(
        replacement,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    os.replace(replacement, campaign_path)
    assert repository._file_signature(campaign_path) == (
        original_stat.st_mtime_ns,
        original_stat.st_size,
    )

    refreshed = repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)

    assert original.campaign_slug == "linden-pass"
    assert refreshed.campaign_slug == "linden-past"


def test_campaign_config_digest_detects_in_place_same_stat_rewrite(app):
    repository = app.extensions["character_repository"]
    campaign_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / TEST_CAMPAIGN_SLUG
        / "campaign.yaml"
    )
    original_stat = campaign_path.stat()
    original_payload = campaign_path.read_bytes()
    changed_payload = original_payload.replace(
        b"**/* - Character Sheet.md",
        b"**/* - Character Sheer.md",
        1,
    )
    assert len(changed_payload) == len(original_payload)

    original = repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)
    campaign_path.write_bytes(changed_payload)
    os.utime(
        campaign_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    assert repository._file_signature(campaign_path) == (
        original_stat.st_mtime_ns,
        original_stat.st_size,
    )

    refreshed = repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)

    assert original.source_glob == "**/* - Character Sheet.md"
    assert refreshed.source_glob == "**/* - Character Sheer.md"


def test_campaign_config_failures_are_not_cached(app, monkeypatch):
    repository = app.extensions["character_repository"]
    repository._campaign_config_cache.clear()
    real_load = character_repository_module._campaign_character_config_from_bytes
    calls: list[str] = []

    def fail_once(config_path, campaign_slug, payload):
        calls.append(campaign_slug)
        if len(calls) == 1:
            raise yaml.YAMLError("synthetic parse failure")
        return real_load(config_path, campaign_slug, payload)

    monkeypatch.setattr(
        character_repository_module,
        "_campaign_character_config_from_bytes",
        fail_once,
    )

    with pytest.raises(yaml.YAMLError, match="synthetic parse failure"):
        repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)
    resolved = repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)

    assert resolved.campaign_slug == TEST_CAMPAIGN_SLUG
    assert calls == [TEST_CAMPAIGN_SLUG, TEST_CAMPAIGN_SLUG]


def test_campaign_config_cache_isolates_campaign_slugs(app):
    repository = app.extensions["character_repository"]
    other_slug = "other-campaign"
    other_dir = app.config["TEST_CAMPAIGNS_DIR"] / other_slug
    other_dir.mkdir()
    (other_dir / "campaign.yaml").write_text(
        (
            "title: Other\n"
            f"slug: {other_slug}\n"
            "system: Xianxia\n"
            "character_dir: heroes\n"
        ),
        encoding="utf-8",
    )

    first = repository._get_campaign_character_config(TEST_CAMPAIGN_SLUG)
    other = repository._get_campaign_character_config(other_slug)

    assert first.campaign_slug == TEST_CAMPAIGN_SLUG
    assert other.campaign_slug == other_slug
    assert other.system == "Xianxia"
    assert other.characters_dir == other_dir / "heroes"
    assert set(repository._campaign_config_cache) >= {
        TEST_CAMPAIGN_SLUG,
        other_slug,
    }


def test_campaign_character_directory_switch_never_reuses_same_signature_payload(
    app,
):
    repository = app.extensions["character_repository"]
    campaign_dir = app.config["TEST_CAMPAIGNS_DIR"] / TEST_CAMPAIGN_SLUG
    campaign_path = campaign_dir / "campaign.yaml"
    old_characters_dir = campaign_dir / "characters"
    new_characters_dir = campaign_dir / "alternate-characters"
    shutil.copytree(old_characters_dir, new_characters_dir, copy_function=shutil.copy2)
    new_definition_path = (
        new_characters_dir / "arden-march" / "definition.yaml"
    )

    with app.app_context():
        first = repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")
    assert first is not None
    assert first.definition.name == "Arden March"

    original_stat = new_definition_path.stat()
    original_bytes = new_definition_path.read_bytes()
    original_text = original_bytes.decode("utf-8")
    original_payload = yaml.safe_load(original_text) or {}
    original_name = str(original_payload["name"])
    assert len(original_name) == len("Arden Mirth")
    rendered_payload = original_bytes.replace(
        f"name: {original_name}".encode("utf-8"),
        b"name: Arden Mirth",
        1,
    )
    assert len(rendered_payload) == original_stat.st_size
    new_definition_path.write_bytes(rendered_payload)
    new_definition_path.touch()
    os.utime(
        new_definition_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    assert repository._file_signature(new_definition_path) == (
        original_stat.st_mtime_ns,
        original_stat.st_size,
    )

    campaign_payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    campaign_payload["character_dir"] = "alternate-characters"
    campaign_path.write_text(
        yaml.safe_dump(campaign_payload, sort_keys=False),
        encoding="utf-8",
    )

    with app.app_context():
        switched = repository.get_visible_character(
            TEST_CAMPAIGN_SLUG,
            "arden-march",
        )

    assert switched is not None
    assert switched.definition.name == "Arden Mirth"


def test_snapshot_source_file_token_reuses_unchanged_campaign_config_without_yaml_reload(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    config_loads = {"count": 0}
    original_load_config = character_repository_module._campaign_character_config_from_bytes

    def count_config_load(*args, **kwargs):
        config_loads["count"] += 1
        return original_load_config(*args, **kwargs)

    monkeypatch.setattr(
        character_repository_module,
        "_campaign_character_config_from_bytes",
        count_config_load,
    )

    first = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
    )
    second = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
        previous=first,
    )

    assert first is not None
    assert second == first
    assert config_loads["count"] == 1


def test_snapshot_source_file_token_does_not_trust_previous_config_fields(app):
    repository = app.extensions["character_repository"]
    baseline = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
    )
    assert baseline is not None

    forged_previous = replace(
        baseline,
        configured_campaign_slug="forged-campaign",
        system="xianxia",
    )
    refreshed = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
        previous=forged_previous,
    )

    assert refreshed == baseline


def test_snapshot_source_file_token_tracks_definition_import_and_campaign_config_signatures(app):
    repository = app.extensions["character_repository"]
    definition_path = _character_definition_path(app, "arden-march")
    import_path = _character_import_path(app, "arden-march")
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / TEST_CAMPAIGN_SLUG / "campaign.yaml"

    baseline = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
    )
    assert baseline is not None

    definition_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    definition_payload["name"] = "Arden March (Token Definition)"
    definition_path.write_text(
        yaml.safe_dump(definition_payload, sort_keys=False),
        encoding="utf-8",
    )
    definition_changed = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
        previous=baseline,
    )
    assert definition_changed is not None
    assert definition_changed != baseline

    import_payload = yaml.safe_load(import_path.read_text(encoding="utf-8")) or {}
    import_payload["snapshot_token_probe"] = "import"
    import_path.write_text(
        yaml.safe_dump(import_payload, sort_keys=False),
        encoding="utf-8",
    )
    import_changed = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
        previous=definition_changed,
    )
    assert import_changed is not None
    assert import_changed != definition_changed

    campaign_payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    campaign_payload["snapshot_token_probe"] = "config"
    campaign_path.write_text(
        yaml.safe_dump(campaign_payload, sort_keys=False),
        encoding="utf-8",
    )
    config_changed = repository.get_snapshot_source_file_token(
        TEST_CAMPAIGN_SLUG,
        ["arden-march"],
        previous=import_changed,
    )
    assert config_changed is not None
    assert config_changed != import_changed


def test_snapshot_source_file_token_rejects_missing_unsafe_and_indeterminate_files(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    import_path = _character_import_path(app, "arden-march")
    missing_path = import_path.with_name("import.yaml.missing")
    import_path.replace(missing_path)
    try:
        assert (
            repository.get_snapshot_source_file_token(
                TEST_CAMPAIGN_SLUG,
                ["arden-march"],
            )
            is None
        )
    finally:
        missing_path.replace(import_path)

    assert (
        repository.get_snapshot_source_file_token(
            TEST_CAMPAIGN_SLUG,
            [".."],
        )
        is None
    )

    original_signature = repository._file_signature

    def invalid_signature(path: Path):
        signature = original_signature(path)
        if path.name == "definition.yaml":
            return (-1, signature[1])
        return signature

    monkeypatch.setattr(repository, "_file_signature", invalid_signature)
    assert (
        repository.get_snapshot_source_file_token(
            TEST_CAMPAIGN_SLUG,
            ["arden-march"],
        )
        is None
    )


def test_snapshot_token_config_signature_and_read_errors_fail_closed_without_poisoning_reads(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    campaign_path = (
        app.config["TEST_CAMPAIGNS_DIR"] / TEST_CAMPAIGN_SLUG / "campaign.yaml"
    )
    original_signature = repository._file_signature

    def invalid_config_signature(path: Path):
        signature = original_signature(path)
        if path == campaign_path:
            return (-1, signature[1])
        return signature

    monkeypatch.setattr(repository, "_file_signature", invalid_config_signature)
    assert (
        repository.get_snapshot_source_file_token(
            TEST_CAMPAIGN_SLUG,
            ["arden-march"],
        )
        is None
    )
    with app.app_context():
        assert repository.get_character(TEST_CAMPAIGN_SLUG, "arden-march") is not None

    monkeypatch.setattr(repository, "_file_signature", original_signature)
    original_read_bytes = Path.read_bytes

    def fail_config_read(path: Path):
        if path == campaign_path:
            raise OSError("snapshot config read failed")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_config_read)
    assert (
        repository.get_snapshot_source_file_token(
            TEST_CAMPAIGN_SLUG,
            ["arden-march"],
        )
        is None
    )
