# DND equipment activation cutover

Version: `character-equipment-activation-v1`. This is an operator procedure for a future separately authorized cutover. Do not run it against protected or live data as part of a source change.

## Field mapping

| Historical source | Authoritative v1 destination | Rule |
| --- | --- | --- |
| `definition.yaml` `equipment_catalog[].id` | `state_json.inventory[].catalog_ref` and `id` | Match one unique exact ID. Never infer from name, source title, or row order. |
| `equipment_catalog[].is_equipped` | `inventory[].is_equipped` | Existing SQLite boolean wins, including explicit `false`. YAML seeds only a proven absent field or new state row. |
| `equipment_catalog[].is_attuned` | `inventory[].is_attuned` | Existing SQLite boolean wins, including explicit `false`; rebuild `attunement.attuned_item_refs` from authoritative rows. |
| `equipment_catalog[].weapon_wield_mode` | `inventory[].weapon_wield_mode` | Existing SQLite value wins, including explicit empty string. A missing legacy key can seed once from the exact YAML row; v1 stores an explicit empty string. |
| `equipment_catalog` quantity/weight/charges/source/rules metadata | Existing definition and inventory fields | Activation migration does not change definitions, source refs, item quantity, charges, active infusions, spell/prepared choices, or resource templates. |

Successful state carries `equipment_activation.schema_version: 1` and `known_definition_ids`. New structural rows may seed only when their unique ID is absent from that known-ID set. A row missing from a legacy state snapshot has no such proof and is held for manager review. Duplicate, blank, conflicting `id`/`catalog_ref`, orphan, malformed explicit activation values, or incomplete source/state pairs are quarantined. An absent activation key on a unique legacy SQLite row is seeded once from its exact YAML row; explicit `false` and `""` remain authoritative. The manager-only Character repair page displays both historical YAML and SQLite rows and requires an explicit preserve, unique-ID remap, or discard choice. Discarding an unmatched activation retains its inventory quantity, charges, infusions, and notes as a visibly unlinked inventory row. Definition-ID repair requires the manager to select the definition row, a new unique ID, and the SQLite row to map. Exact attack equipment references are remapped with a uniquely identified definition row; duplicate-ID attack links and unsupported other links block that ID repair for separate reconciliation. A definition/import pair with no SQLite state is reported as `source_without_state` and fails closed on ordinary DND reads; it requires separate operator reconciliation because the in-app item repair page needs an existing SQLite revision.

The explicit DND Inventory remove action presents the complete row's quantity, charges, attunement, notes, and active infusions for review. On confirmation with the expected revision and trusted prior exact unique ID, its journaled structural update deletes that whole SQLite inventory row and removes its attunement reference. Manager repair `discard` only clears an unmatched activation choice and retains the inventory row; it cannot authorize removal. Raw content replacement, reimport, manager update, and unexplained omissions or ID changes remain fail-closed.

A page-only item can use mechanics from an eligible published Items page visible to the campaign, even without a structured Systems entry. A required page that is missing, deleted, unpublished, hidden, or ineligible suppresses sourced automation and produces a projection warning; dual-linked items also require their enabled Systems entry. Physical equipped state, manual values, and source reference text remain visible.

## Controlled-copy rehearsal

1. Confirm the repository image, exact dependency locks, SQLite schema ledger, campaign source identity, and `definition.yaml`/`import.yaml` pairs. Pause editors of the controlled copy.
2. Place an operator-created `.cpw-activation-controlled-copy` marker in both the copied campaign root and copied database directory. The command refuses apply without both markers. Use the verified configured shared Python from `./local.ps1 -Action environment-check`; invoke `-m player_wiki.character_equipment_migration --campaigns-dir <copied-campaign-root> --database <copied-db>` for a read-only JSON dry run. The report gives counts and bounded per-row activation provenance, without notes or full source bodies.
3. Review every `quarantined`, `journal_protected`, and `source_without_state` row. Apply only to the controlled copy with `--apply-controlled-copy`. The command writes fully ready characters one SQLite transaction at a time, checks exact state revision/JSON and source bytes before each write, then rereads revision and activation invariants. It leaves ambiguous characters unchanged. Rerun the dry run: completed v1 rows are idempotent, and an interrupted run continues only remaining ready rows.
4. Rehearse manager repair and verify Character, Session Character, Combat, JSON detail/actions, Markdown, and package presented output on the disposable copy. Check false and blank SQLite precedence, source-disabled warnings, attunement indexes, active infusions, spell/prepared/resource behavior, and Xianxia isolation.

## Future live authority boundary

A live cutover requires separate operator authority: rehearse with the compatible new image, pause edits, take a fresh coherent backup, run dry run and migration against the approved target, repair quarantined rows, verify Character/Session/Combat/API/export, then reopen edits. Active publication/deletion journal rows must be resolved first. This code change neither performs that sequence nor authorizes a deployment, backup, restore, or live write.

An old image uses historical YAML activation and cannot safely interpret the new state owner or v1 marker. Do not run it against a migrated database. The migration leaves `definition.yaml` as read-only historical evidence. A reverse cutover needs a separately authorized coherent restore; after new edits, forward repair is the preservation path unless a later restore is separately approved. A controlled-copy rollback is discarding that disposable copy, not rewriting YAML from SQLite.
