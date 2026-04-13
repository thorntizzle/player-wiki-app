# Campaign Player Wiki

`Campaign Player Wiki` is a reusable, player-facing web app for tabletop campaigns. It serves curated Markdown content as a searchable wiki while keeping the publishing layer separate from GM-facing source notes.

This starter version is built with Python and Flask so it can run in the current local environment without requiring Node. The important architectural decisions are already in place:

- Campaigns are isolated in `campaigns/<campaign-slug>/`
- Published player content lives separately from GM/wiki source material
- Markdown pages support YAML frontmatter
- `[[Obsidian-style links]]` are resolved into app routes
- Pages can be gated by session number with `reveal_after_session`

## Project Layout

```text
campaign_player_wiki/
  campaigns/
    sample-campaign/
      campaign.yaml
      content/
      characters/
  characters.py
  manage.py
  ops.py
  player_wiki/
    admin.py
    app.py
    auth.py
    auth_store.py
    character_importer.py
    character_models.py
    character_repository.py
    character_service.py
    character_store.py
    config.py
    db.py
    repository.py
    repository_store.py
    models.py
    operations.py
    templates/
    static/
  tests/
  requirements.txt
  requirements-dev.txt
  requirements-prod.txt
  run.py
  wsgi.py
  deploy/
```

## Local-First Quick Start

From the directory that contains `campaign_player_wiki`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\campaign_player_wiki\requirements.txt
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py init-db
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py create-admin admin@example.com "Admin User" --password "replace-me"
.\.venv\Scripts\python.exe .\campaign_player_wiki\run.py
```

Then open `http://127.0.0.1:5000`.

### Windows Local Workflow

If you want a single Windows-friendly entrypoint, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\campaign_player_wiki\local.ps1 -Action bootstrap -AdminEmail admin@example.com -AdminName "Admin User" -AdminPassword "replace-me"
powershell -ExecutionPolicy Bypass -File .\campaign_player_wiki\local.ps1 -Action run
```

Useful actions:

- `bootstrap`: install dev dependencies, initialize the local DB, and optionally create or confirm an admin user
- `run`: start the local Flask app
- `test`: run the pytest suite
- `check`: run `compileall` and the pytest suite
- `backup`: create a timestamped archive of the local SQLite DB and `campaigns/` content
- `restore`: restore a backup archive back into the active local DB and `campaigns/` content
- `prepare-fly-campaigns`: seed Fly's `/data/campaigns` volume from the current image if the volume is still empty
- `sync-fly`: mirror Fly's live DB and campaign content into the active local app paths
- `deploy-fly`: deploy to the real Fly app using a locally supplied `PLAYER_WIKI_FLY_APP` value

The script assumes your local interpreter is:

```text
.\.venv\Scripts\python.exe
```

You can override that with `-PythonPath` if needed.

For isolated local runs, you can also override the SQLite target with `-DbPath`.

For Fly operations, keep the real app name local instead of committing it into the repo:

```powershell
$env:PLAYER_WIKI_FLY_APP = "your-real-fly-app"
powershell -ExecutionPolicy Bypass -File .\campaign_player_wiki\local.ps1 -Action deploy-fly
```

You can also pass `-FlyApp` directly for one-off use. The tracked `fly.toml` stays generic on purpose, and the runtime derives the real base URL and instance name from the actual Fly app at deploy/runtime.

If you prefer VS Code tasks, the workspace now includes:

- `Player Wiki: Bootstrap Local`
- `Player Wiki: Run App`
- `Player Wiki: Run Tests`
- `Player Wiki: Check`
- `Player Wiki: Backup Local State`

The app is private by default now:

- anonymous users are redirected to sign-in
- authenticated users only see campaigns they can access
- app-wide `admin` users can see every campaign
- campaign access for `dm`, `player`, and `observer` is managed separately from the Markdown content
- the wiki experience itself is read-only in MVP

For local authoring, content reload is enabled by default. That makes Windows iteration easy: edit content in the vault, run the app locally, and use the CLI to manage access without needing a real server or domain first.

The repo keeps live campaign content out of Git. For automated coverage, the test suite uses sanitized sample data under `tests/fixtures/sample_campaigns/`.

## App And Data Workflow

The app now treats deployed functionality and live content as separate concerns:

- app code ships through Git and `fly deploy`
- live SQLite-backed content is updated through the JSON API
- live campaign files on Fly live on the mounted `/data/campaigns` volume instead of inside the image
- campaign config, published assets, published wiki pages, and character definition/import files can also be managed through the JSON API
- shared DND 5E source ingest can now be driven through an admin-only JSON API upload plus import-run history endpoints
- systems source policy and combat tracker state now have API coverage in addition to the browser UI
- the Systems UI now exposes an initial DM-default DMG book-backed browse slice (`Treasure`, `Running the Game`, and `Dungeon Master's Workshop`) through the normal source/category/detail path while keeping it hidden from players under source policy
- the Systems UI now also exposes player-visible XGE and TCE `Book Chapters` slices through the normal source/category/detail flow; XGE includes the readable `Shared Campaigns` wrapper plus `Tool Proficiencies`, `Spellcasting`, `Encounter Building`, `Random Encounters: A World of Possibilities`, `Traps Revisited`, `Downtime Revisited`, and `Awarding Magic Items`, while the current TCE slice includes `Ten Rules to Remember`, `Customizing Your Origin`, `Changing a Skill`, and `Changing Your Subclass`
- DM session management can lazy-search visible published wiki pages and accessible Systems entries, then pull either into the session article store as a revealable snapshot
- local testing can mirror Fly by pulling down both `/data/player_wiki.sqlite3` and `/data/campaigns`
- published wiki pages are mirrored to `campaigns/<slug>/content/`, but the app now serves them from a SQLite read model
- published wiki routes keep a lightweight metadata index in memory and only hydrate page Markdown when a page is actually viewed
- body-text search now uses the SQLite read model instead of hydrating every page body in memory

Useful commands for that workflow:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\ops.py prepare-fly-campaigns
.\.venv\Scripts\python.exe .\campaign_player_wiki\ops.py sync-from-fly --yes
.\.venv\Scripts\python.exe .\campaign_player_wiki\ops.py pull-fly-db
```

The app now surfaces a visible version/build footer in the UI and includes version metadata in `/healthz` and `/api/v1/app`. The semantic app version lives in the repo-root `VERSION` file, while deploy builds can stamp the exact Git state through `PLAYER_WIKI_BUILD_ID` and `PLAYER_WIKI_GIT_SHA`.

## Fly Identity Hygiene

The public repo intentionally keeps `fly.toml` sanitized:

- the tracked `app` value is a placeholder
- the tracked config does not hardcode the real Fly base URL or instance name
- `deploy/fly-entrypoint.sh` derives `PLAYER_WIKI_BASE_URL` from `FLY_APP_NAME` on Fly when needed
- `player_wiki/version.py` derives the runtime instance name from Fly when `PLAYER_WIKI_INSTANCE_NAME` is unset

Recommended workflow for real deploys:

1. Set `PLAYER_WIKI_FLY_APP` locally in your shell or PowerShell profile.
2. Run `powershell -ExecutionPolicy Bypass -File .\campaign_player_wiki\local.ps1 -Action deploy-fly`.
3. Let the helper pass `--app <real-app>` plus build metadata to `flyctl deploy`.

That keeps the real app identifier out of Git while still making the normal deploy path deterministic.

For live content automation, use bearer tokens against `/api/v1/campaigns/<campaign-slug>/...`. DM/admin tokens can manage:

- campaign config values such as `current_session`
- published asset files under `assets/`
- published page files under `content/`
- staged session articles, including snapshots pulled from visible published wiki pages or Systems entries
- character `definition.yaml` and `import.yaml` files under `characters/`
- systems source policy and entry overrides
- combat tracker state and DM-side combat mutations

App-admin tokens can additionally manage the shared systems library through:

- `POST /api/v1/systems/imports/dnd5e`
- `GET /api/v1/systems/import-runs`
- `GET /api/v1/systems/import-runs/<import_run_id>`

That means the normal workflow can now be:

1. sync local state from Fly when you want a fresh mirror
2. test app changes locally
3. deploy app functionality to Fly
4. push live content changes through the API instead of editing the server filesystem manually
5. use the admin-only systems ingest API when shared DND 5E source data needs to be refreshed

## Fly Capacity And Upgrade Checklist

The current Fly shape is intentionally simple:

- one always-on machine
- one mounted volume at `/data`
- one SQLite database on that volume
- one Gunicorn worker with a small thread pool

That is still a valid live setup for modest use. In practice, keep the current shape when:

- you usually have one active table or campaign group at a time
- most traffic is page browsing with intermittent chat, combat, or API writes
- uptime expectations are tolerant of a brief interruption during deploys or a machine restart

Treat the following as upgrade triggers:

- users start hitting `database is locked`, `SQLITE_BUSY`, or similar write-contention symptoms
- session, combat, or API write activity feels slow when multiple people are active at once
- the single Fly machine is regularly close to its CPU or memory ceiling
- you want zero-downtime expectations instead of a single-machine service window during deploys
- you need more than one app machine for redundancy or traffic
- you expect multiple groups to use the app heavily at the same time

Recommended upgrade path:

1. Strengthen the current single-machine setup first.
   Increase the Fly VM size before changing the storage model. This is the lowest-risk step and may be enough for moderate growth.
2. Make backups and monitoring explicit.
   Keep regular DB/volume backups and watch Fly machine health, memory pressure, and app logs so upgrade timing is based on signals instead of guesswork.
3. Move the primary database from SQLite to Postgres before adding multiple app machines.
   The current SQLite-on-volume design is good for simplicity, but it is not the right long-term base for horizontal scaling or stronger availability.
4. Only add multi-machine Fly deployment after the database move.
   Multiple app machines with a single SQLite volume-backed writer is not the direction to scale this app.

A practical rule of thumb:

- if growth only means "more readers," upgrade the Fly VM first
- if growth means "more simultaneous writes" or "higher uptime expectations," plan the Postgres migration
- if growth means "redundancy across app machines," Postgres becomes a prerequisite

## Git And Release Workflow

Use Git for application state, and use the API plus Fly volume sync for content state.

- app code, templates, styles, scripts, docs, and sanitized fixtures belong in Git
- live SQLite files and live campaign content do not belong in Git
- content-only updates should go through the API and do not require `fly deploy`
- app functionality changes should be versioned, committed, pushed, and then deployed

Recommended flow for app changes:

1. sync from Fly first if you want local app data to match production
2. make and test the app change locally
3. review `git status` and confirm the diff is app-only
4. update `VERSION` when the app state has meaningfully changed
5. commit the change to `main`
6. push `main` to `origin`
7. deploy that pushed app revision to Fly

Recommended flow for content changes:

1. leave the app code alone unless the feature itself is changing
2. pull Fly state locally if you want a fresh mirror before editing
3. push content updates through the authenticated API
4. pull from Fly again locally if you want your active local copy to mirror the new live state

## Content Model

Each published page is a Markdown file with optional YAML frontmatter:

```yaml
---
title: Captain Rowan Vale
section: NPCs
type: npc
aliases:
  - Eliza
summary: A player-safe profile of Sample Campaign harbor captain Captain Rowan Vale.
reveal_after_session: 1
source_ref: Sample Campaign/NPCs/Harbor Watch/Captain Rowan Vale.md
---
```

Supported fields:

- `title`: display title
- `slug`: optional route slug; defaults to the relative file path
- `section`: top-level grouping shown in the UI
- `type`: freeform content type such as `npc`, `location`, `session`
- `aliases`: alternate names used for link resolution and search
- `summary`: short preview text
- `reveal_after_session`: hide the page until the campaign reaches that session number
- `source_ref`: optional pointer back to the GM-side source document
- `published`: if `false`, the app will not serve the page

Player-facing visibility is controlled by:

- `published`
- `reveal_after_session`

Editorial-only fields such as `source_ref` stay in frontmatter and internal tooling. They are not shown in the normal wiki page UI.

Published page files still matter operationally because they are the portable mirror format and the draft/publish pipeline still writes them, but the running app now reads published wiki pages from SQLite. API writes and publish flows update both the DB read model and the mirrored Markdown file so local/Fly sync and backups still behave the same way.

## Campaign Config

Each campaign defines its own metadata in `campaign.yaml`. The important fields are:

- `title`
- `slug`
- `summary`
- `current_session`
- `player_content_dir`
- `source_wiki_root`

Only content in the player content directory is published by the app. This avoids accidentally exposing GM-only notes.

An empty `content/` directory is still a valid state if you want to reset a campaign and rebuild from drafts. In that case, the campaign landing page continues to work and simply shows that there are no visible wiki pages yet.

## Draft And Publish Workflow

The safe workflow is:

1. Search the GM-side wiki source
2. Import a source page into `drafts/`
3. Review and redact the draft
4. Promote the reviewed draft into `content/`

Example commands:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\publish.py search sample-campaign Rowan
.\.venv\Scripts\python.exe .\campaign_player_wiki\publish.py draft sample-campaign "Sample Campaign\NPCs\Harbor Watch\Captain Rowan Vale.md" --dry-run
.\.venv\Scripts\python.exe .\campaign_player_wiki\publish.py draft sample-campaign "Sample Campaign\NPCs\Harbor Watch\Captain Rowan Vale.md"
.\.venv\Scripts\python.exe .\campaign_player_wiki\publish.py promote sample-campaign "npcs\harbor-watch\captain-rowan-vale.md" --dry-run
.\.venv\Scripts\python.exe .\campaign_player_wiki\publish.py promote sample-campaign "npcs\harbor-watch\captain-rowan-vale.md"
```

Draft imports are marked with `published: false` and written into the campaign's `drafts/` directory, which the app does not serve.

When a reviewed draft is promoted into `content/`, the CLI also refreshes the SQLite page read model so the published page is immediately available through the app's DB-backed wiki routes.

## Character Import Workflow

Character sheets now follow a separate import path from the wiki pages:

- character definitions and import metadata live on disk under `campaigns/<campaign-slug>/characters/<character-slug>/`
- mutable character state lives in SQLite
- re-import updates definition files but preserves live mutable state by default

For a local campaign, the source root can be configured to read from:

```text
Campaign Wiki/Player Characters
```

Search available character sheets:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\characters.py search sample-campaign Rowan
```

Import one character sheet:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\characters.py import sample-campaign Rowan
```

That creates:

```text
campaigns/sample-campaign/characters/rowan-vale/definition.yaml
campaigns/sample-campaign/characters/rowan-vale/import.yaml
```

and initializes a `character_state` row in SQLite if one does not already exist.

The sanitized test fixture set includes:

- `arden-march`
- `selene-brook`
- `tobin-slate`

The importer is designed for partial success:

- stable sheet data becomes structured YAML
- mutable play data starts in SQLite
- parseable trackers become `resource_templates`
- ambiguous or unusual source material is preserved in definition text instead of being silently discarded
- re-import does not wipe player state

## Character Read Routes

Imported characters now have dedicated player-facing routes:

- `/campaigns/<campaign-slug>/characters`
- `/campaigns/<campaign-slug>/characters/<character-slug>`

The roster route is campaign-scoped and read-only. It includes a lightweight search over the imported character set.

Native in-app character authoring is currently DND-5E-only. The roster and sheet routes still work for other campaign systems, but the native builder, native edit flow, native level-up flow, and imported progression-repair flow stay hidden and redirect back to the roster or sheet with a friendly error if someone hits those URLs directly.

The detail route renders the structured character definition plus live SQLite-backed state in read mode:

- subpage navigation for `Quick Reference`, `Features`, `Equipment`, `Personal`, and `Notes`
- a read-mode `Equipment` manager for editable users so they can add Systems-linked or custom supplemental gear without opening the advanced editor
- a portrait slot on `Personal`, stored as a campaign asset and shown in both read mode and session mode
- a permissioned `Controls` subpage for editable users, with room for current admin/DM controls and future player-owned controls
- current HP and temp HP
- resource trackers
- spell slots
- attacks
- features and traits
- inventory and currency
- reference notes and biography

## Character Session Mode

Character sheets now support an in-session edit layer on the same detail route:

- `/campaigns/<campaign-slug>/characters/<character-slug>?mode=session`

Session mode is available only to:

- app `admin`
- campaign `dm`
- assigned `player` owner of that character

Campaign `observer` users remain read-only and cannot activate session mode.

### Editable MVP State

Session mode supports:

- current HP
- temp HP
- generic resource tracker values
- spell slot usage
- inventory quantities for existing items
- currency values
- player notes

### Save Behavior

The current MVP uses server-rendered forms:

- vitals, trackers, spell slots, inventory quantities, and currency save immediately on submit
- player notes use explicit save
- all writes are validated on the server
- all writes are revision-checked to prevent stale overwrites

If a stale write is submitted, the app shows a conflict message and asks the user to refresh before trying again.

### Rest Actions

Session mode includes short-rest and long-rest confirmation flows.

The app applies only modeled rest behavior:

- resource trackers reset based on their structured `reset_on` and `reset_to` values
- long rest restores modeled spell slot usage
- manual trackers remain unchanged

The app does not infer broader tabletop rule effects that are not explicitly represented in character state.

## Auth Bootstrap And Local User Management

The app now uses a local SQLite database for identity, memberships, session tracking, invite links, password reset links, and audit events.

It also stores mutable character state in the same SQLite database.

By default the database lives at:

```text
campaign_player_wiki/.local/player_wiki.sqlite3
```

That file is ignored by git.

### Common Local Admin Commands

Initialize the auth schema:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py init-db
```

Create the first app-wide admin:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py create-admin admin@example.com "Admin User" --password "replace-me"
```

Invite a user and print a local setup URL:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py invite-user player@example.com "Player One" --actor-email admin@example.com
```

Grant campaign access:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py set-membership player@example.com sample-campaign player --actor-email admin@example.com
```

Assign a character owner:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py assign-character player@example.com sample-campaign rowan-vale --actor-email admin@example.com
```

Issue an admin-managed password reset:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py issue-password-reset player@example.com --actor-email admin@example.com
```

Disable a user and revoke active sessions:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\manage.py disable-user player@example.com --actor-email admin@example.com
```

The CLI remains the required admin path for MVP bootstrap and recovery. The internal admin screen is now available for lighter work, but it still stays a convenience layer on top of the same auth service.

## Internal Admin Screen

The app now includes a minimal internal admin screen for lighter operational work:

- `/admin`

It is available only to app-wide `admin` users.

Current admin screen capabilities:

- invite a new user
- review existing users
- open a user detail page
- review recent auth and access activity
- page through and export filtered audit activity as CSV
- set campaign membership
- edit or remove existing campaign memberships from the user detail view
- assign a visible character to a player
- clear existing character assignments from the user detail view
- generate invite links for invited users
- generate password reset links for active users
- disable another user

The screen intentionally stays thin. It uses the same underlying auth-store actions and audit events as the CLI, and the CLI remains the safer path for bootstrap, recovery, and bulk changes.

Recent activity panels are now available on:

- the main admin dashboard for cross-app activity
- each admin user-detail page for user-specific history

The admin activity views now support lightweight filtering by:

- free-text search
- event type
- campaign

They also now support:

- page navigation through longer activity histories
- CSV export of the currently filtered result set

The audit view intentionally redacts raw invite and password-reset URLs, so the log stays useful without becoming a store of live credentials.

## Local Backup And Restore

For local iteration, the app now includes a separate operations CLI:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\ops.py backup
```

That writes a timestamped zip archive under:

```text
campaign_player_wiki/.local/backups
```

Each archive includes:

- a SQLite snapshot of the current local auth and character-state DB
- the current `campaign_player_wiki/campaigns/` directory
- a small manifest describing the archive format

You can add an optional filename label:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\ops.py backup --label before-import
```

Restore is intentionally guarded because it overwrites the active local DB and campaign content:

```powershell
.\.venv\Scripts\python.exe .\campaign_player_wiki\ops.py restore .\campaign_player_wiki\.local\backups\player-wiki-backup-EXAMPLE.zip --yes
```

By default, restore creates an automatic pre-restore safety backup first. Use `--skip-pre-restore-backup` only if you explicitly do not want that extra safety copy.

The same operations are available through `local.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File .\campaign_player_wiki\local.ps1 -Action backup -BackupLabel before-session
powershell -ExecutionPolicy Bypass -File .\campaign_player_wiki\local.ps1 -Action restore -BackupArchive .\campaign_player_wiki\.local\backups\player-wiki-backup-EXAMPLE.zip -ForceRestore
```

Restore should be run while the local app is stopped.

## Configuration

Environment variables:

- `PLAYER_WIKI_ENV`: `development`, `testing`, or `production`
- `PLAYER_WIKI_SECRET_KEY`: required in production
- `PLAYER_WIKI_HOST`: local development bind host, defaults to `127.0.0.1`
- `PLAYER_WIKI_PORT`: local development port, defaults to `5000`
- `PLAYER_WIKI_BASE_URL`: base URL used when the CLI prints invite/reset links, defaults to the local host and port
- `PLAYER_WIKI_CAMPAIGNS_DIR`: optional override for the campaign content root, useful for testing against a temporary content set
- `PLAYER_WIKI_DB_PATH`: SQLite path for auth and other mutable MVP state, defaults to `campaign_player_wiki/.local/player_wiki.sqlite3`
- `PLAYER_WIKI_RELOAD_CONTENT`: `true` or `false`
- `PLAYER_WIKI_CONTENT_SCAN_INTERVAL_SECONDS`: how often to check for content changes when reload is enabled
- `PLAYER_WIKI_TRUST_PROXY`: enable `ProxyFix` when running behind nginx or another reverse proxy
- `PLAYER_WIKI_PROXY_FIX_HOPS`: number of trusted proxy hops, usually `1`
- `PLAYER_WIKI_PREFERRED_URL_SCHEME`: defaults to `https` when proxy trust is enabled
- `PLAYER_WIKI_SESSION_TTL_HOURS`: session lifetime for signed-in users, defaults to `336`
- `PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS`: how often to update `last_seen_at`, defaults to `300`
- `PLAYER_WIKI_INVITE_TTL_HOURS`: invite link lifetime, defaults to `72`
- `PLAYER_WIKI_RESET_TTL_HOURS`: password reset link lifetime, defaults to `24`
- `PLAYER_WIKI_SESSION_COOKIE_NAME`: Flask session cookie name, defaults to `player_wiki_session`
- `PLAYER_WIKI_SESSION_COOKIE_SECURE`: defaults to `true` in production and `false` locally
- `PLAYER_WIKI_SESSION_COOKIE_SAMESITE`: defaults to `Lax`

## Production Deployment

Recommended Phase 1 deployment:

- Linux server
- Gunicorn as the WSGI server
- nginx as the reverse proxy
- Markdown files on disk as the source of truth for curated content
- local SQLite on disk for auth, sessions, memberships, assignments, and other mutable MVP state

Install production dependencies on the server:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-prod.txt
```

Start Gunicorn:

```bash
export PLAYER_WIKI_ENV=production
export PLAYER_WIKI_SECRET_KEY='replace-with-a-real-secret'
export PLAYER_WIKI_TRUST_PROXY=true
export PLAYER_WIKI_PROXY_FIX_HOPS=1
export PLAYER_WIKI_RELOAD_CONTENT=false
export PLAYER_WIKI_DB_PATH='/srv/campaign-player-wiki/.local/player_wiki.sqlite3'
gunicorn -w 2 -b 127.0.0.1:8000 wsgi:app
```

Deployment helpers:

- Sample `systemd` unit: `deploy/campaign-player-wiki.service`
- Sample nginx config: `deploy/nginx-campaign-player-wiki.conf`
- Health endpoint: `/healthz`

The app now caches the loaded repository and only rescans content when reload mode is enabled. That keeps local authoring convenient without making production re-parse every Markdown file on every request.

The local-first workflow is still the recommended place to iterate:

1. curate content on Windows
2. manage users locally with `manage.py`
3. validate behavior at `http://127.0.0.1:5000`
4. move to a Linux host only once the feature set and access rules feel stable

## Automated Tests

Install the test dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\campaign_player_wiki\requirements-dev.txt
```

Run the suite from the directory that contains `campaign_player_wiki`:

```powershell
.\.venv\Scripts\python.exe -m pytest .\campaign_player_wiki
```

The current tests cover:

- auth and campaign access boundaries
- admin dashboard and admin user-detail behavior
- admin activity filtering
- admin activity pagination and CSV export
- admin membership and assignment workflow actions
- wiki access for members versus outsiders
- character roster and read-mode behavior
- session-mode access rules
- mutable state writes
- rest previews and applies
- local backup and restore helpers
- isolated CLI backup/restore round-trip behavior
- stale-revision conflict handling
