# Flask Architecture And Ownership

Last updated: 2026-07-11

## Owns

- The current Flask application boundary, composition model, domain ownership,
  persistence and presentation split, and the external contracts that later
  rewrite slices must preserve.

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
  `player_wiki/db.py` registers database
  teardown, `player_wiki/auth.py` registers identity/account handlers and
  request hooks, and `player_wiki/admin.py` registers Admin handlers.
  `player_wiki/api.py` creates and registers the `/api/v1` Blueprint.

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
  statblocks and campaign condition definitions. The Player Wiki, Systems, and
  Staged Articles lanes delegate to their owning content, Systems, and Session
  components.
- Characters: `CharacterRepository` hydrates file-backed definitions together
  with `CharacterStateStore` state; `CharacterStateService` owns
  revision-checked mutable-state operations. `character_service.py` owns
  definition/state normalization and merging, while
  `character_mechanics_projection.py` owns mechanics projections.
- Systems: `SystemsService` owns shared-library and campaign policy operations,
  entries, overrides, and Systems-linked mechanics; `SystemsStore` owns their
  persistence, including import-run records. `Dnd5eSystemsImporter` in
  `systems_importer.py` executes DND-5E imports, with archive extraction and
  ingest boundaries in `systems_ingest.py`; `app.py` and `api.py` invoke those
  import components.

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
  browser/live endpoints. The publishing Blueprint returns rendered HTML or
  protected campaign asset files. `api.py` owns JSON serialization and responses
  within `/api/v1`. The authoritative API surface and payload details are
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
  ownership seams. The first publishing read slice now has a Blueprint plus
  framework-light presenters; broader Blueprint and use-case extraction
  remains roadmap work.

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
