from __future__ import annotations

from copy import deepcopy
from pathlib import Path

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


def test_get_visible_character_reuses_cached_yaml_payloads_when_signatures_are_unchanged(app, monkeypatch):
    repository = app.extensions["character_repository"]
    calls = {"count": 0}
    original_load = repository._load_yaml_payload

    def spy(path: Path) -> dict[str, object]:
        calls["count"] += 1
        return original_load(path)

    monkeypatch.setattr(repository, "_load_yaml_payload", spy)

    with app.app_context():
        repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")
        repository.get_visible_character(TEST_CAMPAIGN_SLUG, "arden-march")

    assert calls["count"] == 2


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


def test_snapshot_source_file_token_reuses_unchanged_campaign_config_without_yaml_reload(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    config_loads = {"count": 0}
    original_load_config = character_repository_module.load_campaign_character_config

    def count_config_load(*args, **kwargs):
        config_loads["count"] += 1
        return original_load_config(*args, **kwargs)

    monkeypatch.setattr(
        character_repository_module,
        "load_campaign_character_config",
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
