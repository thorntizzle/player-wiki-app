from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3
from dataclasses import replace
from threading import Event

import pytest
from flask import Flask

from player_wiki.backup_archive import create_backup_archive_v2
from player_wiki.campaign_content_service import (
    CampaignContentError,
    delete_campaign_character_file,
    get_campaign_character_file,
    list_campaign_character_files,
    write_campaign_character_file,
)
from player_wiki.character_models import CharacterDefinition, CharacterImportMetadata
from player_wiki.character_reconciliation import (
    CharacterPublicationConflict,
    CharacterPublicationCoordinator,
    CharacterPublicationExistsError,
    CharacterReconciliationHooks,
    is_character_reconciliation_protected,
)
from player_wiki.character_repository import load_campaign_character_config
from player_wiki.character_repository import CharacterRepository
from player_wiki.character_service import build_initial_state
from player_wiki.character_store import CharacterStateConflictError, CharacterStateStore
from player_wiki.db import get_db, init_database
from player_wiki.operations import restore_backup_archive


def _definition(slug: str) -> CharacterDefinition:
    return CharacterDefinition.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": slug,
            "name": slug.replace("-", " ").title(),
            "status": "active",
            "system": "DND-5E",
            "profile": {},
            "stats": {},
            "skills": [],
            "proficiencies": {},
            "attacks": [],
            "features": [],
            "spellcasting": {},
            "equipment_catalog": [],
            "reference_notes": {},
            "resource_templates": [],
            "source": {"source_path": f"test://{slug}"},
        }
    )


def _metadata(slug: str) -> CharacterImportMetadata:
    return CharacterImportMetadata.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": slug,
            "source_path": f"test://{slug}",
            "imported_at_utc": "2026-07-18T00:00:00Z",
            "parser_version": "test",
            "import_status": "clean",
            "warnings": [],
        }
    )


def _paths(app, slug: str):
    config = load_campaign_character_config(
        app.config["CAMPAIGNS_DIR"],
        "linden-pass",
    )
    return (
        config.characters_dir / slug / "definition.yaml",
        config.characters_dir / slug / "import.yaml",
    )


def _coordinator(app, on_event):
    return CharacterPublicationCoordinator(
        campaigns_dir=app.config["CAMPAIGNS_DIR"],
        database_path=app.config["DB_PATH"],
        state_store=app.extensions["character_state_store"],
        repository=app.extensions["character_repository"],
        hooks=CharacterReconciliationHooks(on_event=on_event),
    )


def _thread_coordinator(app, name: str, on_event):
    worker_app = Flask(name)
    worker_app.config["DB_PATH"] = app.config["DB_PATH"]
    worker_app.config["CAMPAIGNS_DIR"] = app.config["CAMPAIGNS_DIR"]
    state_store = CharacterStateStore()
    repository = CharacterRepository(
        worker_app.config["CAMPAIGNS_DIR"],
        state_store,
    )
    return worker_app, CharacterPublicationCoordinator(
        campaigns_dir=worker_app.config["CAMPAIGNS_DIR"],
        database_path=worker_app.config["DB_PATH"],
        state_store=state_store,
        repository=repository,
        hooks=CharacterReconciliationHooks(on_event=on_event),
    )


def _update_payload(record, *, name: str = "Updated Character"):
    definition_payload = record.definition.to_dict()
    definition_payload["name"] = name
    definition = CharacterDefinition.from_dict(definition_payload)
    metadata_payload = record.import_metadata.to_dict()
    metadata_payload["parser_version"] = "test-update"
    metadata = CharacterImportMetadata.from_dict(metadata_payload)
    state = dict(record.state_record.state)
    state["notes"] = {"player_notes_markdown": name}
    return definition, metadata, state


def _create_existing(app, slug: str):
    definition = _definition(slug)
    app.extensions["character_publication_coordinator"].create(
        definition,
        _metadata(slug),
        build_initial_state(definition),
        operation_kind="native_create",
    )
    record = app.extensions["character_repository"].get_character(
        "linden-pass",
        slug,
    )
    assert record is not None
    return record


def test_update_commit_recovers_pair_forward(app):
    with app.app_context():
        prior = _create_existing(app, "up-a")
        definition_path, import_path = _paths(app, "up-a")
        previous_definition = definition_path.read_bytes()
        previous_import = import_path.read_bytes()
        definition, metadata, state = _update_payload(prior)
        updater = app.extensions["auth_store"].create_user(
            "update-reconciliation@example.invalid",
            "Update Reconciliation",
        )

        def crash(event: str, _operation_id: str) -> None:
            if event == "after_commit":
                raise RuntimeError("update restart")

        with pytest.raises(RuntimeError, match="update restart"):
            _coordinator(app, crash).update(
                prior,
                definition,
                metadata,
                state,
                expected_revision=prior.state_record.revision,
                updated_by_user_id=updater.id,
            )

        row = get_db().execute(
            """
            SELECT * FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'up-a'
            """
        ).fetchone()
        assert row["operation_kind"] == "interactive_update"
        assert row["state"] == "prepared"
        assert row["previous_state_revision"] == 1
        assert row["desired_state_revision"] == 2
        assert len(row["previous_definition_digest"]) == 64
        assert len(row["previous_import_digest"]) == 64
        assert len(row["previous_state_digest"]) == 64
        assert definition_path.read_bytes() == previous_definition
        assert import_path.read_bytes() == previous_import
        state_row = get_db().execute(
            """SELECT revision, state_json, updated_by_user_id FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'up-a'"""
        ).fetchone()
        assert state_row["revision"] == 2
        assert state_row["updated_by_user_id"] == updater.id
        assert app.extensions["character_repository"].get_character(
            "linden-pass", "up-a"
        ) is None

        assert _coordinator(app, None).recover_key("linden-pass", "up-a") is True
        recovered = app.extensions["character_repository"].get_character(
            "linden-pass", "up-a"
        )
        assert recovered is not None
        assert recovered.definition.name == "Updated Character"
        assert recovered.import_metadata.parser_version == "test-update"
        assert recovered.state_record.revision == 2
        assert recovered.state_record.state["notes"]["player_notes_markdown"] == (
            "Updated Character"
        )
        assert get_db().execute(
            "SELECT 1 FROM character_reconciliation_operations WHERE character_slug = 'up-a'"
        ).fetchone() is None


def test_update_prior_guard_rolls_back(app):
    with app.app_context():
        prior = _create_existing(app, "up-b")
        definition, metadata, state = _update_payload(prior)
        definition_path, _ = _paths(app, "up-b")
        definition_path.write_bytes(b"third-party-definition")
        state_before = get_db().execute(
            "SELECT revision, state_json FROM character_state WHERE character_slug = 'up-b'"
        ).fetchone()

        with pytest.raises(CharacterStateConflictError):
            app.extensions["character_publication_coordinator"].update(
                prior,
                definition,
                metadata,
                state,
                expected_revision=prior.state_record.revision,
            )

        state_after = get_db().execute(
            "SELECT revision, state_json FROM character_state WHERE character_slug = 'up-b'"
        ).fetchone()
        assert tuple(state_after) == tuple(state_before)
        assert definition_path.read_bytes() == b"third-party-definition"
        assert get_db().execute(
            "SELECT 1 FROM character_reconciliation_operations WHERE character_slug = 'up-b'"
        ).fetchone() is None


def test_update_third_file_conflicts(app):
    with app.app_context():
        prior = _create_existing(app, "up-c")
        definition, metadata, state = _update_payload(prior)
        third_bytes = b"third-party-definition"

        def tamper(event: str, _operation_id: str) -> None:
            if event == "after_commit":
                definition_path, _ = _paths(app, "up-c")
                definition_path.write_bytes(third_bytes)

        with pytest.raises(CharacterPublicationConflict):
            _coordinator(app, tamper).update(
                prior,
                definition,
                metadata,
                state,
                expected_revision=prior.state_record.revision,
            )
        row = get_db().execute(
            """SELECT state, error_code, previous_state_revision, desired_state_revision
            FROM character_reconciliation_operations WHERE character_slug = 'up-c'"""
        ).fetchone()
        assert tuple(row) == ("conflict", "definition_digest_conflict", 1, 2)
        definition_path, _ = _paths(app, "up-c")
        assert definition_path.read_bytes() == third_bytes
        assert get_db().execute(
            "SELECT revision FROM character_state WHERE character_slug = 'up-c'"
        ).fetchone()[0] == 2


def test_update_equal_files_still_advances_state(app):
    with app.app_context():
        prior = _create_existing(app, "up-d")
        definition_path, import_path = _paths(app, "up-d")
        previous_pair = (definition_path.read_bytes(), import_path.read_bytes())
        state = dict(prior.state_record.state)
        state["notes"] = {"player_notes_markdown": "state-only"}
        record = app.extensions["character_publication_coordinator"].update(
            prior,
            prior.definition,
            prior.import_metadata,
            state,
            expected_revision=prior.state_record.revision,
        )
        assert record.state_record.revision == 2
        assert (definition_path.read_bytes(), import_path.read_bytes()) == previous_pair


@pytest.mark.parametrize("missing_target", ("definition", "import"))
def test_update_missing_prior_file_conflicts_without_reconstruction_or_overwrite(
    app,
    missing_target,
):
    slug = f"up-missing-{missing_target}"
    with app.app_context():
        prior = _create_existing(app, slug)
        definition, metadata, state = _update_payload(prior)
        definition_path, import_path = _paths(app, slug)
        previous_definition = definition_path.read_bytes()
        previous_import = import_path.read_bytes()

        def remove_prior(event: str, _operation_id: str) -> None:
            if event == "after_commit":
                target = definition_path if missing_target == "definition" else import_path
                target.unlink()

        with pytest.raises(CharacterPublicationConflict):
            _coordinator(app, remove_prior).update(
                prior,
                definition,
                metadata,
                state,
                expected_revision=prior.state_record.revision,
            )

        row = get_db().execute(
            """
            SELECT state, error_code, desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert row is not None
        assert row["state"] == "conflict"
        assert row["error_code"] == f"{missing_target}_digest_conflict"
        assert bytes(row["desired_definition_yaml"])
        assert bytes(row["desired_import_yaml"])
        assert definition_path.exists() is (missing_target != "definition")
        assert import_path.exists() is (missing_target != "import")
        if definition_path.exists():
            expected_definition = (
                bytes(row["desired_definition_yaml"])
                if missing_target == "import"
                else previous_definition
            )
            assert definition_path.read_bytes() == expected_definition
        if import_path.exists():
            assert import_path.read_bytes() == previous_import
        assert get_db().execute(
            "SELECT revision FROM character_state WHERE character_slug = ?",
            (slug,),
        ).fetchone()[0] == 2
        assert app.extensions["character_repository"].get_character(
            "linden-pass", slug
        ) is None


def test_update_restart_after_definition_publication_completes_import_and_cleanup(app):
    slug = "up-restart-second-file"
    with app.app_context():
        prior = _create_existing(app, slug)
        definition, metadata, state = _update_payload(prior)
        definition_path, import_path = _paths(app, slug)
        previous_import = import_path.read_bytes()

        def crash(event: str, _operation_id: str) -> None:
            if event == "after_definition_publish":
                raise RuntimeError("restart after first publication")

        with pytest.raises(RuntimeError, match="restart after first publication"):
            _coordinator(app, crash).update(
                prior,
                definition,
                metadata,
                state,
                expected_revision=prior.state_record.revision,
            )
        row = get_db().execute(
            """
            SELECT state, desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert row is not None and row["state"] == "prepared"
        assert definition_path.read_bytes() == bytes(row["desired_definition_yaml"])
        assert import_path.read_bytes() == previous_import

        restarted = _coordinator(app, None)
        assert restarted.recover_key("linden-pass", slug) is True
        assert import_path.read_bytes() == bytes(row["desired_import_yaml"])
        recovered = app.extensions["character_repository"].get_character(
            "linden-pass", slug
        )
        assert recovered is not None
        assert recovered.definition.name == "Updated Character"
        assert recovered.import_metadata.parser_version == "test-update"
        assert recovered.state_record.revision == 2
        assert get_db().execute(
            "SELECT 1 FROM character_reconciliation_operations WHERE character_slug = ?",
            (slug,),
        ).fetchone() is None


def test_competing_interactive_updates_commit_one_winner_without_loser_effects(app):
    slug = "up-competing"
    with app.app_context():
        prior = _create_existing(app, slug)
        winner_payload = _update_payload(prior, name="Winning Update")
        loser_payload = _update_payload(prior, name="Losing Update")
        definition_path, import_path = _paths(app, slug)
        previous_pair = (definition_path.read_bytes(), import_path.read_bytes())

    winner_preparing = Event()
    loser_preparing = Event()

    def winner_hook(event: str, _operation_id: str) -> None:
        if event == "before_commit":
            winner_preparing.set()
            assert loser_preparing.wait(timeout=5)
        if event == "after_commit":
            raise RuntimeError("hold committed winner")

    def loser_hook(event: str, _operation_id: str) -> None:
        if event == "before_prepare":
            loser_preparing.set()

    winner_app, winner = _thread_coordinator(app, "winner-update", winner_hook)
    loser_app, loser = _thread_coordinator(app, "loser-update", loser_hook)

    def run(worker_app, coordinator, payload):
        with worker_app.app_context():
            try:
                coordinator.update(
                    prior,
                    *payload,
                    expected_revision=prior.state_record.revision,
                )
            except BaseException as exc:
                return exc
        return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        winner_future = executor.submit(run, winner_app, winner, winner_payload)
        assert winner_preparing.wait(timeout=5)
        loser_future = executor.submit(run, loser_app, loser, loser_payload)
        winner_error = winner_future.result(timeout=10)
        loser_error = loser_future.result(timeout=10)

    assert isinstance(winner_error, RuntimeError)
    assert str(winner_error) == "hold committed winner"
    assert isinstance(loser_error, CharacterStateConflictError)
    with app.app_context():
        rows = get_db().execute(
            """
            SELECT operation_id, state, desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["state"] == "prepared"
        assert b"Winning Update" in bytes(rows[0]["desired_definition_yaml"])
        assert b"Losing Update" not in bytes(rows[0]["desired_definition_yaml"])
        assert (definition_path.read_bytes(), import_path.read_bytes()) == previous_pair
        state_row = get_db().execute(
            "SELECT revision, state_json FROM character_state WHERE character_slug = ?",
            (slug,),
        ).fetchone()
        assert state_row["revision"] == 2
        assert "Winning Update" in state_row["state_json"]
        assert "Losing Update" not in state_row["state_json"]

        assert _coordinator(app, None).recover_key("linden-pass", slug) is True
        recovered = app.extensions["character_repository"].get_character(
            "linden-pass", slug
        )
        assert recovered is not None
        assert recovered.definition.name == "Winning Update"
        assert recovered.state_record.revision == 2


@pytest.mark.parametrize(
    "operation_kind",
    (
        "native_create",
        "manual_import",
        "markdown_import",
        "pdf_import",
        "content_api_create",
    ),
)
def test_all_new_character_kinds_commit_empty_prior_and_cleanup(app, operation_kind):
    slug = f"durable-{operation_kind.replace('_', '-')}"
    definition = _definition(slug)
    with app.app_context():
        record = app.extensions["character_publication_coordinator"].create(
            definition,
            _metadata(slug),
            build_initial_state(definition),
            operation_kind=operation_kind,
        )
        definition_path, import_path = _paths(app, slug)
        assert definition_path.is_file()
        assert import_path.is_file()
        assert record.definition.character_slug == slug
        state = app.extensions["character_state_store"].get_state(
            "linden-pass",
            slug,
        )
        assert state is not None and state.revision == 1
        assert get_db().execute(
            "SELECT 1 FROM character_reconciliation_operations WHERE character_slug = ?",
            (slug,),
        ).fetchone() is None


@pytest.mark.parametrize("target", ("definition", "import"))
def test_tampered_private_payload_conflicts_before_any_publication(app, target):
    slug = f"tampered-{target}"
    definition = _definition(slug)
    secret_marker = b"private-wrong-yaml"

    def tamper(event: str, operation_id: str) -> None:
        if event != "after_commit":
            return
        column = f"desired_{target}_yaml"
        get_db().execute(
            f"UPDATE character_reconciliation_operations SET {column} = ? WHERE operation_id = ?",
            (sqlite3.Binary(secret_marker), operation_id),
        )
        get_db().commit()

    with app.app_context():
        with pytest.raises(CharacterPublicationConflict):
            _coordinator(app, tamper).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        definition_path, import_path = _paths(app, slug)
        assert not definition_path.exists()
        assert not import_path.exists()
        row = get_db().execute(
            """
            SELECT state, error_code, desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations WHERE character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert row["state"] == "conflict"
        assert row["error_code"] == f"{target}_payload_mismatch"
        assert bytes(row[f"desired_{target}_yaml"]) == secret_marker


def test_crash_after_first_yaml_never_publishes_wrong_bytes_and_recovers(app):
    slug = "crash-after-definition"
    definition = _definition(slug)

    def crash(event: str, _operation_id: str) -> None:
        if event == "after_definition_publish":
            raise RuntimeError("definition crash")

    with app.app_context():
        with pytest.raises(RuntimeError, match="definition crash"):
            _coordinator(app, crash).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        definition_path, import_path = _paths(app, slug)
        desired_definition = bytes(
            get_db().execute(
                "SELECT desired_definition_yaml FROM character_reconciliation_operations WHERE character_slug = ?",
                (slug,),
            ).fetchone()[0]
        )
        assert definition_path.read_bytes() == desired_definition
        assert not import_path.exists()
        assert app.extensions["character_repository"].get_character(
            "linden-pass",
            slug,
        ) is None

        assert app.extensions["character_publication_coordinator"].recover_key(
            "linden-pass",
            slug,
        ) is True
        assert import_path.is_file()
        assert app.extensions["character_repository"].get_character(
            "linden-pass",
            slug,
        ) is not None


def test_active_journal_blocks_reads_and_state_auto_initialization_until_cleanup(app):
    slug = "protected-restart"
    definition = _definition(slug)

    def crash(event: str, _operation_id: str) -> None:
        if event == "after_commit":
            raise RuntimeError("restart")

    with app.app_context():
        with pytest.raises(RuntimeError, match="restart"):
            _coordinator(app, crash).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        assert app.extensions["character_repository"].get_character(
            "linden-pass",
            slug,
        ) is None
        assert all(
            record.definition.character_slug != slug
            for record in app.extensions["character_repository"].list_characters(
                "linden-pass"
            )
        )
        assert get_campaign_character_file(
            app.config["CAMPAIGNS_DIR"],
            "linden-pass",
            slug,
        ) is None
        assert all(
            record.character_slug != slug
            for record in list_campaign_character_files(
                app.config["CAMPAIGNS_DIR"],
                "linden-pass",
            )
        )
        state_before = get_db().execute(
            "SELECT revision, state_json FROM character_state WHERE character_slug = ?",
            (slug,),
        ).fetchone()
        assert state_before is not None and state_before["revision"] == 1

        fresh = _coordinator(app, None)
        assert fresh.recover_key("linden-pass", slug) is True
        state_after = get_db().execute(
            "SELECT revision, state_json FROM character_state WHERE character_slug = ?",
            (slug,),
        ).fetchone()
        assert tuple(state_after) == tuple(state_before)
        assert app.extensions["character_repository"].get_character(
            "linden-pass",
            slug,
        ) is not None


def test_no_context_guard_is_inert_but_real_app_context_enforces_active_row(app):
    slug = "context-protection"
    definition = _definition(slug)

    def crash(event: str, _operation_id: str) -> None:
        if event == "after_commit":
            raise RuntimeError("hold")

    with app.app_context():
        with pytest.raises(RuntimeError, match="hold"):
            _coordinator(app, crash).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="markdown_import",
            )
        assert is_character_reconciliation_protected("linden-pass", slug) is True

    assert is_character_reconciliation_protected("linden-pass", slug) is False


def test_conflicted_journal_blocks_content_update_and_delete_with_payload_retained(app):
    slug = "blocked-content-write"
    definition = _definition(slug)
    metadata = _metadata(slug)

    def crash(event: str, _operation_id: str) -> None:
        if event == "after_commit":
            raise RuntimeError("hold conflict")

    with app.app_context():
        with pytest.raises(RuntimeError, match="hold conflict"):
            _coordinator(app, crash).create(
                definition,
                metadata,
                build_initial_state(definition),
                operation_kind="content_api_create",
            )
        get_db().execute(
            """
            UPDATE character_reconciliation_operations
            SET state = 'conflict', error_code = 'injected_conflict'
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        )
        get_db().commit()
        row_before = get_db().execute(
            """
            SELECT desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()

        with pytest.raises(CampaignContentError, match="active reconciliation"):
            write_campaign_character_file(
                app.config["CAMPAIGNS_DIR"],
                "linden-pass",
                slug,
                definition_payload=definition.to_dict(),
                import_metadata_payload=metadata.to_dict(),
                state_store=app.extensions["character_state_store"],
                coordinator=app.extensions["character_publication_coordinator"],
            )
        with pytest.raises(CampaignContentError, match="active reconciliation"):
            delete_campaign_character_file(
                app.config["CAMPAIGNS_DIR"],
                "linden-pass",
                slug,
                state_store=app.extensions["character_state_store"],
                auth_store=app.extensions["auth_store"],
            )
        row_after = get_db().execute(
            """
            SELECT state, error_code, desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert row_after["state"] == "conflict"
        assert row_after["error_code"] == "injected_conflict"
        assert bytes(row_after["desired_definition_yaml"]) == bytes(
            row_before["desired_definition_yaml"]
        )
        assert bytes(row_after["desired_import_yaml"]) == bytes(
            row_before["desired_import_yaml"]
        )
        definition_path, import_path = _paths(app, slug)
        assert not definition_path.exists()
        assert not import_path.exists()


@pytest.mark.parametrize(
    ("crash_event", "expected_state"),
    (
        ("after_commit", "prepared"),
        ("after_repository_pending", "repository_pending"),
    ),
)
def test_active_journal_backup_restore_and_forward_recovery(
    app,
    tmp_path,
    crash_event,
    expected_state,
):
    slug = f"backup-{expected_state.replace('_', '-')}"
    definition = _definition(slug)

    def crash(event: str, _operation_id: str) -> None:
        if event == crash_event:
            raise RuntimeError("backup hold")

    with app.app_context():
        with pytest.raises(RuntimeError, match="backup hold"):
            _coordinator(app, crash).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        row = get_db().execute(
            "SELECT state FROM character_reconciliation_operations WHERE character_slug = ?",
            (slug,),
        ).fetchone()
        assert row["state"] == expected_state
        archive = create_backup_archive_v2(
            db_path=app.config["DB_PATH"],
            campaigns_dir=app.config["CAMPAIGNS_DIR"],
            backup_root=tmp_path / f"backup-{expected_state}",
            archive_basename=f"character-{expected_state}",
            created_at="2026-07-18T00:00:00Z",
        )

    restored_campaigns = tmp_path / f"restored-{expected_state}" / "campaigns"
    restored = restore_backup_archive(
        archive_path=archive.archive_path,
        db_path=tmp_path / f"restored-{expected_state}" / "wiki.sqlite3",
        campaigns_dir=restored_campaigns,
    )
    assert restored.migration_required is False

    recovery_app = Flask(f"recovery-{expected_state}")
    recovery_app.config["DB_PATH"] = restored.database_path
    recovery_app.config["CAMPAIGNS_DIR"] = restored_campaigns
    state_store = CharacterStateStore()
    repository = CharacterRepository(restored_campaigns, state_store)
    coordinator = CharacterPublicationCoordinator(
        campaigns_dir=restored_campaigns,
        database_path=restored.database_path,
        state_store=state_store,
        repository=repository,
    )
    with recovery_app.app_context():
        init_database()
        assert coordinator.recover_key("linden-pass", slug) is True
        assert repository.get_character("linden-pass", slug) is not None
        assert get_db().execute(
            "SELECT 1 FROM character_reconciliation_operations WHERE character_slug = ?",
            (slug,),
        ).fetchone() is None


@pytest.mark.parametrize(
    ("crash_event", "expected_state", "expected_file_disposition"),
    (
        ("after_commit", "prepared", "previous"),
        ("after_repository_pending", "repository_pending", "desired"),
    ),
)
def test_active_interactive_update_survives_verified_backup_restore_and_recovers_forward(
    app,
    tmp_path,
    crash_event,
    expected_state,
    expected_file_disposition,
):
    slug = f"update-backup-{expected_state.replace('_', '-')}"

    def crash(event: str, _operation_id: str) -> None:
        if event == crash_event:
            raise RuntimeError("update backup hold")

    with app.app_context():
        prior = _create_existing(app, slug)
        definition_path, import_path = _paths(app, slug)
        previous_definition = definition_path.read_bytes()
        previous_import = import_path.read_bytes()
        previous_state = get_db().execute(
            """
            SELECT revision, state_json FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        definition, metadata, desired_state = _update_payload(
            prior,
            name=f"Recovered {expected_state}",
        )

        with pytest.raises(RuntimeError, match="update backup hold"):
            _coordinator(app, crash).update(
                prior,
                definition,
                metadata,
                desired_state,
                expected_revision=prior.state_record.revision,
            )

        journal = get_db().execute(
            """
            SELECT * FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        desired_state_row = get_db().execute(
            """
            SELECT revision, state_json FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        desired_definition = bytes(journal["desired_definition_yaml"])
        desired_import = bytes(journal["desired_import_yaml"])
        assert journal["operation_kind"] == "interactive_update"
        assert journal["state"] == expected_state
        assert journal["previous_state_revision"] == previous_state["revision"] == 1
        assert journal["desired_state_revision"] == desired_state_row["revision"] == 2
        assert journal["previous_state_digest"] == hashlib.sha256(
            previous_state["state_json"].encode("utf-8")
        ).hexdigest()
        assert journal["desired_state_digest"] == hashlib.sha256(
            desired_state_row["state_json"].encode("utf-8")
        ).hexdigest()
        assert journal["previous_definition_digest"] == hashlib.sha256(
            previous_definition
        ).hexdigest()
        assert journal["desired_definition_digest"] == hashlib.sha256(
            desired_definition
        ).hexdigest()
        assert journal["previous_import_digest"] == hashlib.sha256(
            previous_import
        ).hexdigest()
        assert journal["desired_import_digest"] == hashlib.sha256(
            desired_import
        ).hexdigest()
        expected_definition = (
            previous_definition
            if expected_file_disposition == "previous"
            else desired_definition
        )
        expected_import = (
            previous_import
            if expected_file_disposition == "previous"
            else desired_import
        )
        assert definition_path.read_bytes() == expected_definition
        assert import_path.read_bytes() == expected_import
        journal_identity = {
            key: journal[key]
            for key in (
                "operation_id",
                "operation_kind",
                "previous_definition_digest",
                "desired_definition_digest",
                "previous_import_digest",
                "desired_import_digest",
                "previous_state_digest",
                "desired_state_digest",
                "previous_state_revision",
                "desired_state_revision",
                "state",
                "error_code",
            )
        }
        archive = create_backup_archive_v2(
            db_path=app.config["DB_PATH"],
            campaigns_dir=app.config["CAMPAIGNS_DIR"],
            backup_root=tmp_path / f"update-backup-{expected_state}",
            archive_basename=f"character-update-{expected_state}",
            created_at="2026-07-18T00:00:00Z",
        )

    restored_root = tmp_path / f"restored-update-{expected_state}"
    restored_campaigns = restored_root / "campaigns"
    restored = restore_backup_archive(
        archive_path=archive.archive_path,
        db_path=restored_root / "wiki.sqlite3",
        campaigns_dir=restored_campaigns,
    )
    assert restored.migration_required is False

    recovery_app = Flask(f"update-recovery-{expected_state}")
    recovery_app.config["DB_PATH"] = restored.database_path
    recovery_app.config["CAMPAIGNS_DIR"] = restored_campaigns
    state_store = CharacterStateStore()
    repository = CharacterRepository(restored_campaigns, state_store)
    coordinator = CharacterPublicationCoordinator(
        campaigns_dir=restored_campaigns,
        database_path=restored.database_path,
        state_store=state_store,
        repository=repository,
    )
    with recovery_app.app_context():
        init_database()
        assert get_db().execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0] == 5
        restored_journal = get_db().execute(
            """
            SELECT * FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert {
            key: restored_journal[key]
            for key in journal_identity
        } == journal_identity
        assert bytes(restored_journal["desired_definition_yaml"]) == desired_definition
        assert bytes(restored_journal["desired_import_yaml"]) == desired_import
        restored_state = get_db().execute(
            """
            SELECT revision, state_json FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert restored_state["revision"] == 2
        assert hashlib.sha256(restored_state["state_json"].encode("utf-8")).hexdigest() == (
            restored_journal["desired_state_digest"]
        )
        restored_definition_path, restored_import_path = _paths(recovery_app, slug)
        assert restored_definition_path.read_bytes() == expected_definition
        assert restored_import_path.read_bytes() == expected_import
        assert repository.get_character("linden-pass", slug) is None

        assert coordinator.recover_key("linden-pass", slug) is True
        recovered = repository.get_character("linden-pass", slug)
        assert recovered is not None
        assert recovered.definition.name == f"Recovered {expected_state}"
        assert recovered.import_metadata.parser_version == "test-update"
        assert recovered.state_record.revision == 2
        assert recovered.state_record.state["notes"]["player_notes_markdown"] == (
            f"Recovered {expected_state}"
        )
        assert restored_definition_path.read_bytes() == desired_definition
        assert restored_import_path.read_bytes() == desired_import
        assert get_db().execute(
            """
            SELECT 1 FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone() is None


def test_partial_targets_are_rejected_without_state_journal_or_file_mutation(app):
    slug = "partial-definition"
    definition = _definition(slug)
    with app.app_context():
        definition_path, import_path = _paths(app, slug)
        definition_path.parent.mkdir(parents=True, exist_ok=True)
        definition_path.write_bytes(b"third-party")
        with pytest.raises(FileExistsError):
            app.extensions["character_publication_coordinator"].create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        assert definition_path.read_bytes() == b"third-party"
        assert not import_path.exists()
        assert get_db().execute(
            "SELECT 1 FROM character_state WHERE character_slug = ?",
            (slug,),
        ).fetchone() is None
        assert get_db().execute(
            "SELECT 1 FROM character_reconciliation_operations WHERE character_slug = ?",
            (slug,),
        ).fetchone() is None


def test_private_payloads_are_excluded_from_repr_and_equality(app):
    slug = "private-repr"
    definition = _definition(slug)

    def crash(event: str, _operation_id: str) -> None:
        if event == "after_commit":
            raise RuntimeError("hold")

    with app.app_context():
        with pytest.raises(RuntimeError, match="hold"):
            _coordinator(app, crash).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        operation = app.extensions[
            "character_publication_coordinator"
        ]._load_active_operation("linden-pass", slug)
        assert operation is not None
        rendered = repr(operation)
        assert "desired_definition_yaml" not in rendered
        assert "desired_import_yaml" not in rendered
        assert operation == replace(
            operation,
            desired_definition_yaml=b"different-private-definition",
            desired_import_yaml=b"different-private-import",
        )


def test_competing_prepare_serializes_to_one_active_key_without_file_publication(app):
    slug = "competing-prepare"
    definition = _definition(slug)
    first_committed = Event()
    second_preparing = Event()

    def first_hook(event: str, _operation_id: str) -> None:
        if event == "after_commit":
            first_committed.set()
            assert second_preparing.wait(timeout=5)
            raise RuntimeError("hold prepared winner")

    def second_hook(event: str, _operation_id: str) -> None:
        if event == "before_prepare":
            second_preparing.set()

    first_app, first = _thread_coordinator(app, "first-prepare", first_hook)
    second_app, second = _thread_coordinator(app, "second-prepare", second_hook)

    def run(worker_app, coordinator):
        with worker_app.app_context():
            try:
                coordinator.create(
                    definition,
                    _metadata(slug),
                    build_initial_state(definition),
                    operation_kind="native_create",
                )
            except BaseException as exc:
                return exc
        return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(run, first_app, first)
        assert first_committed.wait(timeout=5)
        second_future = executor.submit(run, second_app, second)
        first_error = first_future.result(timeout=10)
        second_error = second_future.result(timeout=10)

    assert isinstance(first_error, RuntimeError)
    assert str(first_error) == "hold prepared winner"
    assert isinstance(second_error, CharacterPublicationExistsError)
    with app.app_context():
        rows = get_db().execute(
            """
            SELECT operation_id, state
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["state"] == "prepared"
        definition_path, import_path = _paths(app, slug)
        assert not definition_path.exists()
        assert not import_path.exists()


def test_cleanup_revalidates_owner_and_retains_concurrently_changed_journal(app):
    slug = "stale-cleanup-owner"
    definition = _definition(slug)

    def change_owner(event: str, operation_id: str) -> None:
        if event != "before_cleanup":
            return
        get_db().execute(
            """
            UPDATE character_reconciliation_operations
            SET desired_state_digest = ?
            WHERE operation_id = ? AND state = 'repository_pending'
            """,
            ("0" * 64, operation_id),
        )
        get_db().commit()

    with app.app_context():
        with pytest.raises(
            CharacterPublicationConflict,
            match="ownership changed",
        ):
            _coordinator(app, change_owner).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        row = get_db().execute(
            """
            SELECT state, desired_state_digest
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert row is not None
        assert row["state"] == "repository_pending"
        assert row["desired_state_digest"] == "0" * 64
        definition_path, import_path = _paths(app, slug)
        assert definition_path.is_file()
        assert import_path.is_file()


@pytest.mark.parametrize(
    ("fault_event", "slug_suffix", "expected_journal_state", "expected_files"),
    (
        ("before_prepare", "bp", None, (False, False)),
        ("before_commit", "bc", None, (False, False)),
        ("after_commit", "ac", "prepared", (False, False)),
        ("before_definition_publish", "bd", "prepared", (False, False)),
        ("after_definition_publish", "ad", "prepared", (True, False)),
        ("before_import_publish", "bi", "prepared", (True, False)),
        ("after_import_publish", "ai", "prepared", (True, True)),
        ("before_repository_pending", "br", "prepared", (True, True)),
        ("after_repository_pending", "ar", "repository_pending", (True, True)),
        ("before_refresh", "bf", "repository_pending", (True, True)),
        ("after_refresh", "af", "repository_pending", (True, True)),
        ("before_cleanup", "cl", "repository_pending", (True, True)),
    ),
)
def test_fault_matrix_preserves_commit_boundary_and_recovers_forward(
    app,
    fault_event,
    slug_suffix,
    expected_journal_state,
    expected_files,
):
    slug = f"fault-{slug_suffix}"
    definition = _definition(slug)

    def crash(event: str, _operation_id: str) -> None:
        if event == fault_event:
            raise RuntimeError(f"fault at {fault_event}")

    with app.app_context():
        with pytest.raises(RuntimeError, match=fault_event):
            _coordinator(app, crash).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        definition_path, import_path = _paths(app, slug)
        assert (definition_path.exists(), import_path.exists()) == expected_files
        row = get_db().execute(
            """
            SELECT * FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        state_row = get_db().execute(
            """
            SELECT revision FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        if expected_journal_state is None:
            assert row is None
            assert state_row is None
            return

        assert row["state"] == expected_journal_state
        assert state_row is not None and state_row["revision"] == 1
        if definition_path.exists():
            assert definition_path.read_bytes() == bytes(row["desired_definition_yaml"])
        if import_path.exists():
            assert import_path.read_bytes() == bytes(row["desired_import_yaml"])
        assert app.extensions["character_repository"].get_character(
            "linden-pass",
            slug,
        ) is None

        assert _coordinator(app, None).recover_key("linden-pass", slug) is True
        assert get_db().execute(
            "SELECT 1 FROM character_reconciliation_operations WHERE operation_id = ?",
            (row["operation_id"],),
        ).fetchone() is None
        assert app.extensions["character_repository"].get_character(
            "linden-pass",
            slug,
        ) is not None


@pytest.mark.parametrize("prepublished", ("import_only", "both"))
def test_recovery_accepts_absent_desired_pair_permutations(app, prepublished):
    slug = f"pair-{prepublished.replace('_', '-')}"
    definition = _definition(slug)

    def prepublish(event: str, operation_id: str) -> None:
        if event != "after_commit":
            return
        row = get_db().execute(
            """
            SELECT desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        definition_path, import_path = _paths(app, slug)
        import_path.parent.mkdir(parents=True, exist_ok=True)
        import_path.write_bytes(bytes(row["desired_import_yaml"]))
        if prepublished == "both":
            definition_path.write_bytes(bytes(row["desired_definition_yaml"]))
        raise RuntimeError("preset pair")

    with app.app_context():
        with pytest.raises(RuntimeError, match="preset pair"):
            _coordinator(app, prepublish).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        assert _coordinator(app, None).recover_key("linden-pass", slug) is True
        assert app.extensions["character_repository"].get_character(
            "linden-pass",
            slug,
        ) is not None


def test_repository_pending_third_file_conflicts_without_overwrite(app):
    slug = "repository-pending-third-file"
    definition = _definition(slug)
    third_bytes = b"third-party-import"

    def tamper(event: str, _operation_id: str) -> None:
        if event == "after_repository_pending":
            _, import_path = _paths(app, slug)
            import_path.write_bytes(third_bytes)

    with app.app_context():
        with pytest.raises(CharacterPublicationConflict):
            _coordinator(app, tamper).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        _, import_path = _paths(app, slug)
        assert import_path.read_bytes() == third_bytes
        row = get_db().execute(
            """
            SELECT state, error_code, desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert row["state"] == "conflict"
        assert row["error_code"] == "import_digest_conflict"
        assert bytes(row["desired_definition_yaml"])
        assert bytes(row["desired_import_yaml"])


def test_prepared_state_digest_conflict_is_retained_without_sqlite_overwrite(app):
    slug = "prepared-third-state"
    definition = _definition(slug)

    def tamper(event: str, _operation_id: str) -> None:
        if event != "before_repository_pending":
            return
        get_db().execute(
            """
            UPDATE character_state SET state_json = '{}'
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        )
        get_db().commit()

    with app.app_context():
        with pytest.raises(CharacterPublicationConflict):
            _coordinator(app, tamper).create(
                definition,
                _metadata(slug),
                build_initial_state(definition),
                operation_kind="native_create",
            )
        row = get_db().execute(
            """
            SELECT state, error_code, desired_definition_yaml, desired_import_yaml
            FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert row["state"] == "conflict"
        assert row["error_code"] == "state_digest_conflict"
        assert bytes(row["desired_definition_yaml"])
        assert bytes(row["desired_import_yaml"])
        state_row = get_db().execute(
            """
            SELECT revision, state_json FROM character_state
            WHERE campaign_slug = 'linden-pass' AND character_slug = ?
            """,
            (slug,),
        ).fetchone()
        assert state_row["revision"] == 1
        assert state_row["state_json"] == "{}"
