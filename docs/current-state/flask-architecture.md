# Flask Architecture And Ownership

Last updated: 2026-07-14

## Owns

- The current Flask application boundary, composition model, domain ownership,
  persistence and presentation split, and the external contracts that later
  rewrite slices must preserve.
- The Session transport ownership and route-count statements added on 2026-07-14
  are verified on `codex/flask-rewrite-phase3b` at
  `44a95ba3b3f6143857c857835a9724a7b7cca16a` only. They do not describe
  `main`, the deployed app, or live production state until separately integrated
  and released.

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
  and Systems services.
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
  and registrar dependency wiring.
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
  published-page read model; `publisher.py` and
  `session_article_publisher.py` own publication workflows.
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
- `RepositoryStore` and `Repository` provide the campaign and published-content
  repository view. `CampaignPageStore` owns the SQLite published-page read
  model, while campaign-content writes keep that read model and mirrored
  Markdown synchronized.

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
  server begins accepting requests.
- `runtime_lease.py` owns the cross-process single-writer lease and startup
  refusal when restore recovery is pending. `backup_archive.py` owns WAL-aware
  verified archives, `restore_transaction.py` owns journaled atomic
  publication/recovery, and `operations.py` exposes the backup, restore,
  status, resume, rollback, and disposable rehearsal command boundary used by
  `ops.py` and `local.ps1`.

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
  and campaign availability without self-healing. These operational modules
  are shipped ownership seams, not the Blueprint/use-case extraction planned
  for Phase 3.

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
  API Blueprint. The qualified Phase 3B inventory leaves 89 decorator
  registrations in `app.py` and 107 in `api.py`; those modules retain shared
  helpers, serializers, composition, dependency wiring, and nonmoved routes.
  Character `/session/character` and character-session routes remain owned by
  Characters, and the low-level content APIs remain owned by Publishing rather
  than Session. App-admin DND-5E ingest
  and the import-run list and detail GET transports now live in
  `systems_api_routes.py`. Broader Blueprint and use-case
  extraction remains roadmap work.

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
- `player_wiki/api.py`
- `player_wiki/auth.py`
- `player_wiki/admin.py`
- `player_wiki/db.py`
- `player_wiki/csrf.py`
- `player_wiki/security_headers.py`
- `player_wiki/input_limits.py`
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
