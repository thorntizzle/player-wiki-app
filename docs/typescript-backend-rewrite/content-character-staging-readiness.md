# Content Character Staging Readiness Decision

Last updated: 2026-06-26

## Decision

The Hono content-character write/delete route family is copied-data rollback ready, but it is not yet staging-write enabled.

Before enabling it against a staging or live campaign volume, run the same route family against an approved staging-volume snapshot that contains realistic campaign character files, portrait assets, `character_state` rows, and `character_assignments` rows. The snapshot rehearsal must prove backup creation, Hono mutation behavior, restore, and post-restore data equivalence.

## Evidence Accepted

- `tests/test_typescript_readonly_slice_contract.py::test_typescript_content_character_dnd_persistence_matches_flask_golden`
  proves DND-5E create/delete parity against copied campaign files and temp SQLite, including exact initialized state JSON, assignment cleanup, and delete flags.
- `tests/test_typescript_readonly_slice_contract.py::test_typescript_content_character_xianxia_persistence_matches_flask_golden`
  proves Xianxia create/update/delete parity against copied campaign files and temp SQLite, including mutable-state clamping and definition-file separation.
- `tests/test_typescript_readonly_slice_contract.py::test_typescript_content_character_backup_restore_rehearsal_recovers_files_assets_and_sqlite`
  proves copied-data rollback across `definition.yaml`, `import.yaml`, portrait assets, `character_state`, and `character_assignments` after a Hono write/delete rehearsal.

## Why Staging Is Still Gated

The accepted evidence uses sanitized copied fixtures. That is enough to prove route semantics and backup/restore mechanics, but it does not prove readiness against the full shape of a real campaign volume. Staging data may include proprietary content, older import metadata, portrait asset variations, legacy state rows, assignment history, and path/layout combinations that are intentionally absent from tracked fixtures.

## Required Staging Snapshot Rehearsal

1. Take or receive an approved snapshot of the staging-equivalent SQLite database and campaign content directory.
2. Run the Hono API with `CPW_DB_PATH` and `CPW_CAMPAIGNS_DIR` pointed at disposable copies of that snapshot.
3. Create a Python backup archive before mutation.
4. Exercise content-character write and delete on at least one DND-5E character and one Xianxia character if both systems are present in the snapshot.
5. Verify response flags for file, asset, state-row, and assignment-row mutation match observed data changes.
6. Restore from the backup archive.
7. Verify definition/import YAML, portrait assets, state row JSON/revision, assignment rows, and sampled character detail responses match the pre-mutation snapshot.
8. Record the command transcript and result in this rewrite evidence folder before changing any staging routing or feature flag.

## Current Label

Current status for this route family: `copied-data rollback ready; staging snapshot required`.
