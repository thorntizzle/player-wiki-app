from __future__ import annotations

from copy import deepcopy

import yaml


def _write_character_definition(app, character_slug: str, mutator) -> None:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_character_state(app, character_slug: str, mutator) -> None:
    with app.app_context():
        repository = app.extensions["character_repository"]
        store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", character_slug)
        assert record is not None
        payload = deepcopy(record.state_record.state)
        mutator(payload)
        store.replace_state(
            record.definition,
            payload,
            expected_revision=record.state_record.revision,
        )


def _read_character_definition(app, character_slug: str) -> dict:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    return yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}


def _character_state_revision(app, character_slug: str) -> int:
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character("linden-pass", character_slug)
        assert record is not None
        return int(record.state_record.revision)


def _write_campaign_config(app, mutator) -> None:
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with app.app_context():
        repository_store = app.extensions.get("repository_store")
        if repository_store is not None:
            repository_store.refresh()
