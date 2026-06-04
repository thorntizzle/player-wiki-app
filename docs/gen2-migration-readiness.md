# Gen2 Migration Readiness

This document tracks the current Flask-to-Gen2 frontend migration state. Flask remains the production reference UI until an individual surface is accepted for replacement.

## Status Labels

- `Feel-test ready`: Gen2 has practical parity for the listed workflow and local browser coverage.
- `Partial`: Gen2 covers the main read or play workflow, but important authoring, advanced editing, or layout parity remains Flask-first.
- `Flask-first`: Keep using the Flask route for this workflow.
- `Deferred`: Not a current Gen2 migration target.

## Route Parity Matrix

| Surface | Flask route | Gen2 route | Status | Notes |
| --- | --- | --- | --- | --- |
| Campaign list | `/` | `/app-next/` | Feel-test ready | Gen2 campaign selector and authenticated shell are covered by the browser suite. |
| Campaign home | `/campaigns/<slug>` | `/app-next/campaigns/<slug>` | Feel-test ready | Gen2 handles home cards and campaign search handoff. |
| Published wiki sections | `/campaigns/<slug>/sections/<section>` | `/app-next/campaigns/<slug>/sections/<section>` | Feel-test ready | Grouped subsections, featured pages, and collapse/expand behavior are covered. |
| Published wiki pages | `/campaigns/<slug>/pages/<page>` | `/app-next/campaigns/<slug>/pages/<page>` | Feel-test ready | Gen2 renders safe article HTML, sidebar context, and protected assets. |
| Session | `/campaigns/<slug>/session` | `/app-next/campaigns/<slug>/session` | Feel-test ready | Player Session, Session Character, DM Session, live polling, local state preservation, and article handoffs are covered. |
| Characters roster | `/campaigns/<slug>/characters` | `/app-next/campaigns/<slug>/characters` | Feel-test ready | Roster search, cards, portraits, and fallback tool links are covered. |
| Character read/edit shell | `/campaigns/<slug>/characters/<character>` | `/app-next/campaigns/<slug>/characters/<character>` | Partial | Gen2 reuses the proven Character pane for DND-5E/Xianxia read and inline state edits. Broader authoring remains Flask-first. |
| Character create/import | `/campaigns/<slug>/characters/create`, import routes | Flask fallback links from Gen2 | Flask-first | Native create, imports, portrait upload/remove, Advanced Editor, Cultivation, level-up, retraining, progression repair, controls, and deletion remain Flask-rendered. |
| Combat player view | `/campaigns/<slug>/combat` | `/app-next/campaigns/<slug>/combat` | Feel-test ready | Player combat workspace, selected PC workspace, carousel, and polling preservation are covered. |
| Combat DM status | `/campaigns/<slug>/combat/dm` or status view | `/app-next/campaigns/<slug>/combat?view=status` | Feel-test ready | Selected-combatant focus, compact tactical edits, condition add/remove, and selected-PC detail are covered. |
| Combat DM controls | `/campaigns/<slug>/combat/dm?view=controls` or controls view | `/app-next/campaigns/<slug>/combat?view=controls` | Feel-test ready | Player/manual/statblock/Systems seeding, turn advance, and checked clear-tracker cleanup are covered. |
| DM Content statblocks | `/campaigns/<slug>/dm-content` | `/app-next/campaigns/<slug>/dm-content` | Feel-test ready | Create/search/read/edit/delete, parser feedback, subsection grouping, and combat seed identity are covered. |
| DM Content conditions | `/campaigns/<slug>/dm-content/conditions` | `/app-next/campaigns/<slug>/dm-content?lane=conditions` | Feel-test ready | Create/search/read/edit/delete and Combat picker merge behavior are covered. |
| DM Content staged articles | `/campaigns/<slug>/dm-content/staged-articles` | `/app-next/campaigns/<slug>/dm-content?lane=staged-articles` | Feel-test ready | Manual/upload/wiki source modes, create/update/delete, and source search are covered. Reveal/log workflows remain on Session DM. |
| DM Content Player Wiki | `/campaigns/<slug>/dm-content/player-wiki` | `/app-next/campaigns/<slug>/dm-content?lane=player-wiki` | Feel-test ready | Create/search/load/edit/archive/checked-delete, removal safety, image upload, and fallback advanced-editor links are covered. |
| DM Content Systems | `/campaigns/<slug>/dm-content/systems` | `/app-next/campaigns/<slug>/dm-content?lane=systems` | Feel-test ready | Source policy, entry overrides, custom entries, sanitized import history, and admin import handoff are covered. |
| Systems browsing | `/campaigns/<slug>/systems` and nested source/type/entry routes | Flask route via Gen2 nav/fallback | Flask-first | Gen2 currently manages Systems through DM Content, but player/DM Systems browsing remains Flask-rendered. |
| Campaign Control | `/campaigns/<slug>/control` | Flask route via Gen2 nav | Flask-first | Visibility/config controls remain Flask-rendered. |
| Campaign Help | `/campaigns/<slug>/help` | Flask route via Gen2 nav | Flask-first | Help remains Flask-rendered. |
| Account settings | `/account` | Flask route via Gen2 chrome | Flask-first | Account preferences and theme selection remain Flask-rendered. |
| Admin | `/admin` | Flask route via Gen2 chrome | Flask-first | Admin operations remain Flask-rendered. |
| API token test field | None | Gen2 shell local field | Partial | Local testing aid only; browser cookies remain the default auth path. |

## Promotion Rules

- Keep Flask routes available until the corresponding Gen2 surface has been accepted after manual feel testing.
- Do not add redirects from Flask routes to Gen2 routes yet. Route-level redirects should wait until a surface is accepted for replacement and the fallback path is still obvious.
- Keep Flask fallback links on Gen2 surfaces for workflows that remain Flask-first, especially character authoring, Systems browsing, Control, Help, Account, and Admin.
- Treat layout parity separately from functionality parity. Several Gen2 surfaces are functionally feel-test ready while still needing layout polish against the Flask rendition.

## Current Test Coverage

- `tests/test_frontend_pilot.py` verifies `/app-next/` static serving and SPA fallback for deep links.
- `tests/test_frontend_gen2_session_browser.py` covers the current promoted Gen2 feel-test surfaces: shell/session, wiki browsing, character roster/detail, combat player/status/controls, and all DM Content lanes including Systems.
- Focused API coverage exists in `tests/test_api.py` for the JSON contracts used by the Gen2 surfaces.

## Local Build And Host

Build the Gen2 bundle:

```powershell
cd C:\Users\thorn\Documents\my_scripts\campaign_player_wiki\frontend
C:\Users\thorn\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe node_modules\typescript\bin\tsc --noEmit
C:\Users\thorn\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe node_modules\vite\bin\vite.js build
```

Host through Flask:

```powershell
cd C:\Users\thorn\Documents\my_scripts\campaign_player_wiki
$env:PLAYER_WIKI_PORT = "5006"
C:\Users\thorn\Documents\my_scripts\.venv\Scripts\python.exe run.py
```

Open:

- `http://127.0.0.1:5006/app-next/`
- `http://127.0.0.1:5006/app-next/campaigns/linden-pass/dm-content?lane=systems`
- `http://127.0.0.1:5006/healthz`

## Build Artifact Decision

Keep `frontend/dist/` local-only for now. It remains ignored by Git and Docker context hygiene, and Fly does not yet run a frontend build stage.

Revisit deployment packaging when one of these becomes true:

- a Gen2 route is accepted as the default replacement for a Flask route
- `/app-next/` needs to work on Fly without a manual local build artifact
- asset versioning/caching needs to be managed as part of normal deploys

Until then, local testing should rebuild `frontend/dist/` before hosting, and production deployment should continue to treat Gen2 as side-by-side migration work.

## Next Readiness Work

- Add a manual acceptance column once the user has feel-tested each Gen2 surface.
- Re-measure live pressure before changing transport strategy for Session or Combat.
- Decide the first route eligible for a Flask-to-Gen2 redirect only after functionality and layout are accepted.
