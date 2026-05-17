from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from tests.sample_data import TEST_CAMPAIGN_SLUG


def _character_definition_path(app, character_slug: str) -> Path:
    return (
        app.config["TEST_CAMPAIGNS_DIR"]
        / TEST_CAMPAIGN_SLUG
        / "characters"
        / character_slug
        / "definition.yaml"
    )


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
