# Flask Architecture And Ownership

Last updated: 2026-07-19

## Owns

- The current Flask application boundary, composition model, domain ownership,
  persistence and presentation split, and the external contracts that later
  rewrite slices must preserve.
- The final Phase 3B transport ownership and route-count statements are
  integrated on pushed `main` and deployed as Fly release `223`, built from
  exact commit `e5bd742676b958fa5af932c2489b8972d3bbca1a`. The later
  documentation closeout is a docs-only descendant and is not part of that
  deployed image.
- The Phase 4 persistence statements are locally integrated only on
  `codex/flask-rewrite-phase4` at accepted executable commit
  `e24566821301391effae12f27c0923a45ebf66b1`. This includes durable character
  portrait publication and recovery. These changes have not been pushed,
  merged to `main`, deployed, or applied through a live content or database
  write.

## Entrypoints And Application Composition

- Flask is the only browser application. `run.py` is the local development
  entrypoint and `wsgi.py` is the WSGI entrypoint; both import the application
  factory exported by `player_wiki/__init__.py`.
- `player_wiki/app.py` defines `create_app()`. The factory loads configuration,
  registers the rich-text template filter, creates the current stores,
  repositories, and services, and publishes those shared objects through
  `app.extensions`.
- The extension composition includes the repository and campaign-page stores;
  auth, character-state, Session, Combat, DM Content, and Systems stores; the
  `CharacterRepository`; and the character-state, Session, Combat, DM Content,
  and Systems services. It also publishes the `PlayerWikiReconciler` used by
  browser and API Player Wiki mutation paths and ordinary-request recovery.
- `player_wiki/app.py` owns the remaining direct campaign/browser route
  registration and calls the other registration owners.
  `player_wiki/publishing_routes.py` owns the Blueprint/controller boundary
  for protected Wiki assets, section reads, and page reads; it explicitly
  preserves the supported bare endpoint identifiers `campaign_asset`,
  `section_view`, and `page_view` with exactly one rule per path.
  The same module owns the six Player Wiki management controllers. DM Content
  remains their product-surface and route-policy/manifest domain while the
  publishing module owns their browser transport. `player_wiki/dm_content_routes.py`
  owns the Blueprint/controller boundary for the six statblock and custom-condition
  upload/create, update, and delete mutations. It preserves their supported bare
  endpoint identifiers through explicit compatibility registrations, with exactly
  one registered rule per method/path; DM Content remains their product and policy
  owner. `player_wiki/systems_routes.py` owns one Systems Blueprint/controller
  boundary for the five Systems index, search, source, source-category, and entry
  reads; the source-policy and entry-override browser mutations; and the five custom-entry
  create, edit, update, archive, and restore controllers. It also owns the
  app-admin shared/core permission mutation and the shared-entry edit GET and
  update POST controllers, plus the app-admin browser DND-5E import POST.
  Sixteen explicit
  app-level compatibility registrations preserve those routes' supported bare
  endpoint identifiers and exactly one rule per method/path. `app.py` retains the
  four Systems read-context builders, the Systems control-panel and DM Content
  context builders supplied to that transport module, the injected custom-entry
  DOM-ID helper, `build_systems_import_form()`, and the remaining Systems
  control-panel view. The shared-entry
  form/JSON, provenance, changed-field, resolver, and editor-rendering helpers
  used only by those controllers live with them in `systems_routes.py`.
  `player_wiki/session_routes.py` owns the Session Blueprint/controller boundary
  for 19 live-session browser handlers and rules: nine GET and ten POST rules.
  Its compatibility registrar preserves the supported bare Flask endpoint
  identifiers and one-rule-per-method/path behavior. `app.py` retains Session's
  shared context, rendering, serialization, composition, and dependency wiring.
  The Character registrar family owns all 86 Character rules and 93
  method/path contracts across 65 registrar modules, with transport parity
  covered by 68 dedicated transport test modules. `character_routes.py`
  coordinates the browser Character registrations, while the Character API
  registrar modules attach to the existing API Blueprint. Character service,
  repository, state, presenter, and persistence ownership remains unchanged.
  Twelve Auth registrar modules own all 13 Auth rules and 15 method/path
  contracts; `auth.py` retains request hooks, shared auth/access helpers,
  dependency wiring, and one direct route decorator. `admin.py` retains 14
  browser rules, `admin_api_routes.py` owns 12 Admin API rules, and
  `campaign_visibility_routes.py` owns four campaign-visibility rules, for a
  singular 30-rule/30-contract Admin boundary.
  `player_wiki/db.py` registers database
  teardown, `player_wiki/auth.py` registers identity/account handlers and
  request hooks, and `player_wiki/admin.py` registers Admin handlers.
  `player_wiki/api.py` creates and registers the `/api/v1` Blueprint. It retains
  the shared API serializers, authorization and error boundaries, repository and
  service and importer/store composition, request helpers and decorators, the
  remaining nonmoved Systems JSON routes, and cross-domain JSON handlers.
  `player_wiki/session_api_routes.py` owns 13 live-session JSON handlers and
  explicit registrations on that existing API Blueprint. `api.py` retains the
  Session serializers, shared request/auth/error helpers, service composition,
  and registrar dependency wiring. Character, Auth, and Admin API registrar
  families also attach their extracted handlers to this existing Blueprint;
  they do not create alternate public API roots.
  `player_wiki/systems_api_routes.py` owns 15 Systems handlers and registers
  their 16 rules on that existing Blueprint: seven read handlers across eight
  GET rules plus eight mutation handlers for source policy, entry overrides,
  custom-entry create/update/archive/restore, campaign item-mechanics import,
  and app-admin DND-5E ingest. The two additional reads are the app-admin-only,
  read-only import-run list and detail transports. The two landing/search rules intentionally share
  the supported `api.systems_index` endpoint; the other registrations preserve their existing
  `api.systems_import_run_list`, `api.systems_import_run_detail`,
  `api.systems_source_list`, `api.systems_source_update`,
  `api.systems_entry_override_update`, `api.systems_custom_entry_create`,
  `api.systems_custom_entry_update`, `api.systems_custom_entry_archive`,
  `api.systems_custom_entry_restore`, `api.systems_item_mechanics_import`,
  `api.systems_import_dnd5e`,
  `api.systems_source_detail`,
  `api.systems_source_category_detail`, and `api.systems_entry_detail`
  identifiers.

## Domain Orchestration Owners

- Campaign content and publishing: `campaign_content_service.py` owns guarded
  campaign config, page, asset, and character-file operations;
  `campaign_page_store.py`, `repository.py`, and `repository_store.py` own the
  published-page read model; `session_article_publisher.py` prepares and guards
  one-shot Session article conversion, including stable source provenance and
  optional image preparation; `player_wiki_reconciliation.py` performs durable
  page/image/database publication and forward completion for that conversion,
  browser page create/update/unpublish, and API page upsert; and `publisher.py`
  owns the remaining publication workflows.
- Session: `CampaignSessionService` and `CampaignSessionStore` own lifecycle,
  messages, staged/revealed articles, images, and logs.
- Combat: `CampaignCombatService` and `CampaignCombatStore` own tracker and
  combatant orchestration and persistence.
- DM Content: `CampaignDMContentService` and `CampaignDMContentStore` own
  SQLite-backed statblock bodies and parsed fields plus campaign condition
  definitions; statblock uploads are not retained or mirrored to Markdown. The
  Player Wiki, Systems, and Staged Articles lanes delegate to their owning
  content, Systems, and Session components.
- Characters: `CharacterRepository` hydrates file-backed definitions together
  with `CharacterStateStore` state; `CharacterStateService` owns
  revision-checked mutable-state operations. `character_service.py` owns
  definition/state normalization and merging, while
  `character_mechanics_projection.py` owns mechanics projections.
  `CharacterPublicationCoordinator` owns durable absent-target publication for
  browser native create, Xianxia manual import, first-time Markdown/PDF import,
  and first-time content API create, plus interactive existing-character
  definition/import/state updates across their browser, API, Session, and
  Combat adapters. It also owns portrait set, replacement, and removal as the
  `portrait_upsert` and `portrait_remove` operation kinds.
- Systems: `SystemsService` owns shared-library and campaign policy operations,
  entries, overrides, and Systems-linked mechanics; `SystemsStore` owns their
  SQLite persistence, including custom campaign entries, source-policy records,
  entry overrides, and import-run records. `Dnd5eSystemsImporter` in
  `systems_importer.py` executes DND-5E imports, with archive extraction and
  ingest boundaries in `systems_ingest.py`; `systems_routes.py` owns the browser
  invocation, `systems_api_routes.py` owns the JSON transport, and `api.py`
  supplies the JSON transport's importer/store/service composition.

## Persistence Ownership

- `player_wiki/db.py` owns the shared SQLite connection lifecycle and schema
  initialization, delegating ordered schema evolution to `migrations.py`.
  Domain stores own SQL access for auth, page records, character state,
  Session, Combat, DM Content, and Systems data.
- `CharacterRepository` reads stable character definitions from campaign files
  and combines them with mutable SQLite state from `CharacterStateStore`.
- `character_reconciliation.py` commits either revision-1 new-character state
  or an interactive update's next expected state revision together with a
  `prepared` recovery row in one `BEGIN IMMEDIATE` transaction before atomic
  `definition.yaml` then `import.yaml` publication. Interactive updates retain
  previous and desired YAML/state digests so recovery accepts desired bytes,
  advances only exact prior bytes, and treats missing or third-party bytes as a
  retained `conflict` without reconstruction or overwrite. Active `prepared`,
  `repository_pending`, and `conflict` rows hide and protect that character
  from normal reads, update, delete, and automatic state initialization while
  unrelated characters continue normally; successful refresh and final
  authority validation delete the journal row.
- A portrait operation prepares its next SQLite state revision and private
  recovery row together, then proceeds forward in this order: publish the
  desired portrait asset when applicable; publish `definition.yaml`; publish
  `import.yaml`; validate the desired state; durably unlink a superseded
  portrait; commit the `repository_pending` transition; refresh the repository;
  and authoritatively delete the journal. Only after that deletion commits does
  best-effort empty-directory pruning run. If the superseded asset is already
  absent while the journal remains active, recovery durably syncs the retained
  parent directory before advancing so another restart can retry that boundary.
- Active portrait operations inherit the character read-hiding boundary.
  Recovery accepts already-desired evidence, advances only exact prior
  evidence, and retains unexpected, unsafe, or third-party asset evidence as a
  conflict without overwrite. This is forward reconciliation across SQLite
  and campaign files, not a cross-store atomic transaction.
- `CharacterDeletionCoordinator` uses the separate private
  `character_deletion_operations` journal. Its first keyed-lock,
  runtime-lease, `BEGIN IMMEDIATE` transaction is the sole behavioral commit
  point: it revalidates exact prior evidence and both character journals,
  inserts `prepared`, deletes any matching state and assignment, and writes the
  one Controls audit when applicable before any filesystem mutation. Raw
  content deletion writes no audit.
- After that commit, recovery moves only the exact captured definition, import,
  and one exact managed portrait to deterministic private same-parent
  tombstones, transitions to `repository_pending`, proves the repository
  absent, durably removes the tombstones, and deletes the journal under final
  owner, state, database, cross-journal, and file-authority guards. Active rows
  hide and protect the key while unrelated characters and files continue
  normally. Unexpected, unsafe, symlink, special, unmanaged, third-state, or
  ambiguous portrait evidence is retained as a conflict. Partial raw targets
  remain supported, while Combat snapshot and string references are preserved.
- `RepositoryStore` and `Repository` provide the campaign and published-content
  repository view. `CampaignPageStore` owns the SQLite published-page read
  model. Player Wiki reconciliation treats mirrored Markdown as authoritative,
  keeps its SQLite page row as a derived read model, and protects pages with an
  active prepared, repository-pending, or conflict publication or deletion
  journal row from filesystem reload upsert or deletion while unrelated pages
  continue to synchronize.
- `player_wiki_reconciliation.py` stores exact sanitized desired Markdown as a
  private transient recovery payload only while forward completion may need it;
  the payload is nonempty, bounded to 96 MiB, and excluded from normal reads,
  APIs, logs, and audit metadata. It stores no image BLOB. A changed image is
  primary, while identical-image and no-image mutations are Markdown-primary.
  Prepared operations precede the file commit; authoritative Markdown precedes
  a transaction containing page-row, optional browser-audit, and
  `repository_pending` writes. Refresh reads finalized SQLite without
  filesystem resynchronization, final desired authority is revalidated, and
  successful cleanup deletes the journal row. Conflicts retain the recovery
  payload and block that page; repository-pending retries refresh and cleanup.
- The same coordinator uses the separate
  `player_wiki_deletion_operations` journal for browser checked-delete and API
  page delete. The commit is an atomic no-replace move of a nonempty regular
  Markdown file, bounded to 96 MiB, to a short private same-directory non-`.md`
  tombstone. It rejects unsafe paths, symlinks/reparse points, and destination
  races. Page-row deletion, optional browser audit, and
  `repository_pending` transition are one transaction; repository refresh is
  database-authoritative, and durable tombstone cleanup precedes journal
  deletion. Recovery is state-checked and idempotent, conflicts retain the
  journal and any private tombstone evidence, API deletion writes no browser
  audit, and page assets are never deleted by this workflow.

## Presentation Ownership

- `player_wiki/templates/` owns server-rendered page structure and the shared
  Flask shell. `player_wiki/static/` owns shared CSS and browser JavaScript.
- Presenter modules such as `character_presenter.py`, `combat_presenter.py`,
  `session_presenter.py`, `live_presenter.py`, and `loading_presenter.py` build
  reusable view data outside templates.
- Flask route handlers in `app.py` may return rendered HTML or JSON for
  browser/live endpoints. The Session Blueprint owns its 19 live-session browser
  transports, while the Session API registrar owns its 13 JSON transports on the
  existing API Blueprint. The publishing Blueprint returns rendered HTML or
  protected campaign asset files. The DM Content Blueprint owns HTML form
  mutation transport for statblocks and custom condition definitions while the
  shared DM Content page/context builder remains in `app.py`. The Systems
  Blueprint owns HTML transport for its five browser reads, two policy/override
  mutations, five custom-entry lifecycle controllers, the shared/core
  permission mutation, the shared-entry edit GET and update POST controllers,
  and the browser DND-5E import POST;
  Systems product and persistence ownership remains with `SystemsService` and
  `SystemsStore`, while
  DM Content remains the presentation
  lane for the embedded Systems management panel and the Systems control panel
  remains the second custom-entry presentation surface. `api.py` owns shared
  JSON serialization and the `/api/v1` Blueprint; `systems_api_routes.py` owns
  transport for seven Systems read handlers, including the two import-run
  reads, and the eight source-policy, entry-override, custom-entry,
  campaign item-mechanics, and app-admin DND-5E ingest mutation handlers,
  while their service, store, authorization, policy, audit, persistence,
  request-helper, serializer, and full DM Content Systems-payload dependencies
  keep their existing owners. The DND-5E API transport writes one app-global
  success audit after the full import and before run refetch or serialization;
  the existing browser import remains a separate campaign-attributed audited lane.
  The authoritative API surface and payload details are
  documented in [API v1](../api-v1.md).
- Final route accounting is 299 Flask rules and 308 method/path contracts:
  171 browser, 136 API, and one framework static entry. Domain rule/contract
  ownership is app shell 13/13, Auth 13/15, Admin 30/30, Publishing 20/20,
  DM Content 25/25, Systems 33/33, Live Session 32/32, Combat 46/46,
  Characters 86/93, and framework 1/1. Each rule and contract has one owner.

## Cross-Cutting Policy

- `auth.py` and `auth_store.py` own authentication, memberships, roles, and
  access helpers. `campaign_visibility.py` owns campaign/scope visibility and
  privacy floors.
- `system_policy.py` owns canonical campaign-system capabilities and route-lane
  policy.
- `rich_text.py` owns the allowlist sanitizer, and `create_app()` registers its
  `safe_rich_html` Jinja filter. The shipped sanitizer contract is documented
  in [Rich-Text Security](rich-text-security.md).
- `csrf.py` owns browser-mutation CSRF enforcement, `security_headers.py` owns
  CSP nonces and response security/cache/privacy headers, and `input_limits.py`
  owns the bounded request and upload envelope.
- `migrations.py` owns ordered, numbered schema evolution and recorded
  migration state. Startup applies those migrations before the production
  server begins accepting requests. Migration
  `0002_player_wiki_reconciliation_operations` owns the publication journal
  schema, while `0003_player_wiki_deletion_reconciliation_operations` carries
  the distinct deletion journal. Migration
  `0004_character_reconciliation_operations` carries the private new-character
  publication journal. Migration `0005_character_reconciliation_updates`
  extends that journal with interactive-update revision evidence and
  constraints; `0006_character_reimport_reconciliation` adds existing-target
  Markdown/PDF reimport kinds; `0007_character_content_api_update_reconciliation`
  adds complete existing-target raw content API updates;
  `0008_character_portrait_reconciliation` carries the current schema and adds
  bounded portrait asset evidence; and
  `0009_character_deletion_reconciliation` adds the separate private character
  deletion journal. The version-1 through version-8 migration payloads and
  checksums remain immutable.
- `runtime_lease.py` owns the cross-process single-writer lease and startup
  refusal when restore recovery is pending. `backup_archive.py` owns WAL-aware
  verified archives, `restore_transaction.py` owns journaled atomic
  publication/recovery, and `operations.py` exposes the backup, restore,
  status, resume, rollback, and disposable rehearsal command boundary used by
  `ops.py` and `local.ps1`.
- `player_wiki_reconciliation_inspection.py` owns the read-only, pre-application
  inspection boundary for active Player Wiki publication and deletion journals.
  `ops.py` and `local.ps1` expose it as the reconciliation dry-run command; it
  does not share the mutation or recovery authority of the coordinators.

## Runtime And Recovery Boundary

- The supported production topology is one application process with one
  Gunicorn worker against the SQLite volume. The runtime lease serializes
  state-changing operational workflows; it is not a substitute for a
  multi-writer database architecture.
- Restore publication over an existing, nonempty target requires a
  transaction-correlated prebackup and durable journal; an empty target
  intentionally creates no prebackup. Rehearsal uses a nonempty synthetic
  target so the verified-v2 prebackup path is always exercised. Startup fails
  closed when an interrupted transaction needs recovery, and operators must
  inspect, resume, or roll back through the recovery CLI.
- Liveness is dependency-free; readiness reports database, migration, storage,
  and campaign availability without self-healing or initializing storage. The
  `/healthz`, `/livez`, and `/readyz` paths bypass both Player Wiki and
  character publication recovery before any recovery database or repository
  access. Ordinary application requests retain the bounded internal recovery
  triggers. These operational modules are shipped ownership seams, not the
  Blueprint/use-case extraction planned for Phase 3.
- Backup and restore preserve active Player Wiki publication/deletion rows and
  active character publication/update/reimport/content-API/portrait/deletion
  rows. The archive format remains verified v2 while the current schema
  registry is version 9. Supported self-consistent older producer ledgers
  validate and restore with current-app evidence and `migration_required=True`; later
  `manage.py init-db` advances them to version 9 before server startup.
  Current-version portrait rows retain their private desired image bytes
  through verified-v2 backup/restore and resume forward recovery.
  Current-version deletion rows retain exact metadata-only recovery evidence
  and resume forward recovery; captured file bytes remain only in their
  private same-parent tombstones.
  Tampered, future, and internally inconsistent producer evidence remains
  rejected.
- Runtime lease ownership, keyed process locks, partial unique active-page and
  active-character indexes, and `BEGIN IMMEDIATE` transactions guard app-owned
  Player Wiki, new-character publication, and interactive existing-character
  updates. An out-of-band external file mutation after the relevant final
  authority check is treated as a new external authority event rather than part
  of the completed app-owned operation.
- The reconciliation dry run inspects only active journal-owned work. It checks
  the complete versioned migration/table/index inventory before filters, reads
  SQLite in `mode=ro` and query-only mode with committed-WAL awareness, and
  requires two stable scans of database and relevant filesystem evidence. It
  emits redacted deterministic JSON and fails closed for active restore,
  malformed, unsafe, tampered, future, inconsistent, busy, or changing
  evidence. It does not initialize the app, acquire the runtime lease, create
  storage or temporary files, refresh repositories, invoke recovery, or apply
  a repair.
- The Player Wiki dry run accepts a verified applied version-2 ledger for its
  publication journal and verified applied version-3 through version-9 ledgers
  for the publication and deletion journals under the current version-9
  registry. It remains Player-Wiki-only: it neither inspects the character
  publication or deletion journals nor emits their private recovery evidence.

## Storage Split

- SQLite stores auth and membership data, visibility, the published-page read
  model, mutable character state, Session and Combat state, DM Content records,
  and Systems libraries and policy.
- Campaign configuration and character definitions are file-backed under
  `campaigns/<campaign-slug>/`. Published campaign content and assets are
  mirrored as Markdown and files under each campaign directory.
- In production, application code is baked into the image while SQLite and
  campaign content live on the mounted `/data` volume.

## Preserved External Boundaries

- Rewrite slices preserve public URLs, supported endpoint identifiers used by
  `url_for()`, manifests, policy keys, and API links, JSON API shapes, role and
  visibility
  behavior, existing SQLite data, mirrored-content contracts, and Flask browser
  delivery unless an explicitly approved slice changes a named contract.
- API readers should use [API v1](../api-v1.md). The explicit access-policy
  source and deterministic route/API/role/visibility manifest live under
  `docs/contracts/`. `scripts/generate_route_manifest.py` generates or checks
  the manifest, and `tests/test_route_contract_manifest.py` checks policy
  coverage, registered-route parity, and generated-byte drift. These contracts
  are descriptive parity evidence; runtime authorization remains enforced by
  the application rather than by the manifest.

## Transitional Boundary

- `player_wiki/app.py` and `player_wiki/api.py` still contain substantial
  transport, orchestration, serialization, and presentation logic. The current
  services, stores, repositories, presenters, and policy modules provide real
  ownership seams. Publishing read and Player Wiki management routes now have a
  Blueprint/controller boundary, with framework-light presenters and mutation
  orchestration where applicable. The six DM Content statblock/condition
  mutation controllers have their own Blueprint/controller boundary; the mixed
  DM Content shell and subpage context builder remain in `app.py`. The Systems
  Blueprint now owns its five browser read controllers, the source-policy and
  entry-override mutation controllers, and the five custom-entry lifecycle
  controllers plus the shared/core permission and shared-entry editor
  controllers plus the browser DND-5E import controller through sixteen
  compatibility registrations; the Systems context builders, import-form
  builder, templates, importer, service, store, and remaining control-panel view
  keep their existing owners. Fifteen Systems API handlers live in
  `systems_api_routes.py` and contribute 16 explicit rules to the existing
  API Blueprint. Session browser transport now lives in `session_routes.py` as
  19 handlers/rules, and Session JSON transport now lives in
  `session_api_routes.py` as 13 handlers/explicit registrations on the existing
  API Blueprint. Character transport now owns 86 rules/93 method contracts
  across 65 registrar modules; Auth owns 13/15 across 12 registrar modules;
  and Admin owns 30/30 across the 14 `admin.py` browser rules, 12
  `admin_api_routes.py` API rules, and four `campaign_visibility_routes.py`
  rules. The final qualified Phase 3B inventory leaves 26 direct route
  decorators in `app.py`, 35 in `api.py`, one in `auth.py`, and 14 in
  `admin.py`; those modules retain shared helpers, serializers, composition,
  dependency wiring, request hooks, and nonmoved routes.
  Character `/session/character` and character-session routes remain owned by
  Characters, and the low-level content APIs remain owned by Publishing rather
  than Session. App-admin DND-5E ingest
  and the import-run list and detail GET transports now live in
  `systems_api_routes.py`. Phase 3B transport ownership is fully assigned;
  Phase 4 persistence work is locally underway on its durable branch, while
  later presentation work remains a separate roadmap phase.

## Related Current-State Docs

- [Flask Browser App](flask-browser.md)
- [Admin, Auth, And Visibility](admin-auth.md)
- [Published Wiki And Publishing](published-wiki.md)
- [Live Session](live-session.md)
- [Combat](combat.md)
- [DM Content](dm-content.md)
- [Characters Overview](characters-overview.md)
- [Systems Wiki](systems.md)
- [Ops And Fly Deployment](ops-deploy.md)

## Source Pointers

- `run.py`
- `wsgi.py`
- `player_wiki/__init__.py`
- `player_wiki/app.py`
- `player_wiki/publishing_routes.py`
- `player_wiki/dm_content_routes.py`
- `player_wiki/systems_routes.py`
- `player_wiki/systems_api_routes.py`
- `player_wiki/session_routes.py`
- `player_wiki/session_api_routes.py`
- `player_wiki/character_routes.py`
- `player_wiki/character_*_routes.py`
- `player_wiki/auth_*_routes.py`
- `player_wiki/admin_api_routes.py`
- `player_wiki/campaign_visibility_routes.py`
- `player_wiki/api.py`
- `player_wiki/auth.py`
- `player_wiki/admin.py`
- `player_wiki/db.py`
- `player_wiki/csrf.py`
- `player_wiki/security_headers.py`
- `player_wiki/input_limits.py`
- `player_wiki/campaign_page_store.py`
- `player_wiki/character_reconciliation.py`
- `player_wiki/character_portrait_mutation_routes.py`
- `player_wiki/character_portrait_mutation_api_routes.py`
- `player_wiki/character_controls_delete_routes.py`
- `player_wiki/character_controls_delete_api_routes.py`
- `player_wiki/campaign_content_service.py`
- `player_wiki/character_repository.py`
- `player_wiki/character_store.py`
- `player_wiki/file_publication.py`
- `player_wiki/player_wiki_reconciliation.py`
- `player_wiki/player_wiki_reconciliation_inspection.py`
- `player_wiki/publishing_mutations.py`
- `player_wiki/session_article_publisher.py`
- `player_wiki/session_routes.py`
- `player_wiki/migrations.py`
- `player_wiki/runtime_lease.py`
- `player_wiki/backup_archive.py`
- `player_wiki/restore_transaction.py`
- `player_wiki/operations.py`
- `ops.py`
- `player_wiki/systems_importer.py`
- `player_wiki/systems_ingest.py`
- `player_wiki/templates/`
- `player_wiki/static/`
- `docs/contracts/route-access-policies.json`
- `docs/contracts/route-api-role-visibility-manifest.json`
- `scripts/generate_route_manifest.py`
- `tests/test_route_contract_manifest.py`
- `tests/test_campaign_session_page.py`
- `tests/test_dm_content_player_wiki.py`
- `tests/test_player_wiki_reconciliation.py`
- `tests/test_character_reconciliation.py`
- `tests/test_character_portrait_mutation_route_transport.py`
- `tests/test_api_character_portrait_mutation_route_transport.py`
- `tests/test_file_publication.py`
