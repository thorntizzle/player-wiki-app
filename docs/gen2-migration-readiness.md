# Gen2 Migration Readiness

This document tracks the current Flask-to-Gen2 frontend migration state. Flask remains the production reference UI until an individual surface is accepted for replacement.

## Status Labels

- `Feel-test ready`: Gen2 has practical parity for the listed workflow and local browser coverage.
- `Partial`: Gen2 covers the main read or play workflow, but important authoring, advanced editing, or layout parity remains Flask-first.
- `Flask-first`: Keep using the Flask route for this workflow.
- `Needs Gen2 pass`: No Gen2 replacement exists yet, or the Gen2 surface only links back to Flask for the core workflow.
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
| Character read/edit shell | `/campaigns/<slug>/characters/<character>` | `/app-next/campaigns/<slug>/characters/<character>` | Partial | Gen2 reuses the proven Character pane for DND-5E/Xianxia read, inline state edits, and portrait upload/remove. Broader authoring remains Flask-first. |
| Character create/import | `/campaigns/<slug>/characters/create`, import routes | Flask fallback links from Gen2 | Needs Gen2 pass | Native create, imports, Advanced Editor, Cultivation, level-up, retraining, progression repair, controls, and deletion remain Flask-rendered. |
| Combat player view | `/campaigns/<slug>/combat` | `/app-next/campaigns/<slug>/combat` | Feel-test ready | Player combat workspace, selected PC workspace, carousel, and polling preservation are covered. |
| Combat DM status | `/campaigns/<slug>/combat/dm` or status view | `/app-next/campaigns/<slug>/combat?view=status` | Feel-test ready | Selected-combatant focus, compact tactical edits, condition add/remove, and selected-PC detail are covered. |
| Combat DM controls | `/campaigns/<slug>/combat/dm?view=controls` or controls view | `/app-next/campaigns/<slug>/combat?view=controls` | Feel-test ready | Player/manual/statblock/Systems seeding, turn advance, and checked clear-tracker cleanup are covered. |
| DM Content statblocks | `/campaigns/<slug>/dm-content` | `/app-next/campaigns/<slug>/dm-content` | Feel-test ready | Create/search/read/edit/delete, parser feedback, subsection grouping, and combat seed identity are covered. |
| DM Content conditions | `/campaigns/<slug>/dm-content/conditions` | `/app-next/campaigns/<slug>/dm-content?lane=conditions` | Feel-test ready | Create/search/read/edit/delete and Combat picker merge behavior are covered. |
| DM Content staged articles | `/campaigns/<slug>/dm-content/staged-articles` | `/app-next/campaigns/<slug>/dm-content?lane=staged-articles` | Feel-test ready | Manual/upload/wiki source modes, create/update/delete, and source search are covered. Reveal/log workflows remain on Session DM. |
| DM Content Player Wiki | `/campaigns/<slug>/dm-content/player-wiki` | `/app-next/campaigns/<slug>/dm-content?lane=player-wiki` | Feel-test ready | Create/search/load/edit/archive/checked-delete, removal safety, image upload, and fallback advanced-editor links are covered. |
| DM Content Systems | `/campaigns/<slug>/dm-content/systems` | `/app-next/campaigns/<slug>/dm-content?lane=systems` | Feel-test ready | Source policy, entry overrides, custom entries, sanitized import history, and admin import handoff are covered. |
| Systems browsing | `/campaigns/<slug>/systems` and nested source/type/entry routes | `/app-next/campaigns/<slug>/systems` and nested source/type/entry routes | Feel-test ready | Gen2 handles landing/search, source detail, source category, entry detail, source-scoped rules reference search, rendered Systems entry HTML, and management fallbacks. Shared/core entry editing and imports remain Flask/DM Content handoffs. |
| Campaign Control | `/campaigns/<slug>/control-panel` | `/app-next/campaigns/<slug>/control` | Feel-test ready | Gen2 reads and saves the same campaign/scope visibility rows as Flask Control, preserves admin-only Private visibility, audit events, cache clearing, and a Flask fallback link. |
| Campaign Help | `/campaigns/<slug>/help` | `/app-next/campaigns/<slug>/help` | Feel-test ready | Gen2 reuses the Flask Help context through `/api/v1/campaigns/<slug>/help`, shows current access, visible surfaces, visibility notes, cross-cutting limits, and keeps a Flask fallback link. |
| Account settings | `/account` | `/app-next/account` | Feel-test ready | Gen2 reads the same theme/chat-order choices as Flask, saves account preferences through `/api/v1/me/settings`, updates shell theme hydration, and keeps a Flask fallback link. |
| Admin | `/admin` | Flask route via Gen2 chrome | Needs Gen2 pass | Admin operations remain Flask-rendered. |
| API token test field | None | Gen2 shell local field | Partial | Local testing aid only; browser cookies remain the default auth path. |

## Remaining Flask-First Surfaces Needing Gen2 Passes

These surfaces should not be considered for default-route promotion until they receive their own Gen2 parity pass:

- Character authoring and management: native create, imports, Advanced Editor, Cultivation, controls, level-up, retraining, progression repair, and deletion.
- Admin: app administration, bootstrap/support operations, and admin-only maintenance pages.

These pages can continue to be linked from Gen2 chrome as Flask fallbacks, but each needs a dedicated parity slice before the route can move under `/app-next/` or become a redirect candidate.

## Next Gen2 Route Priority

The remaining Flask-first pages are not equally risky. Use this order unless a specific play-session need changes the priority:

| Priority | Surface | Why next | Acceptance target |
| --- | --- | --- | --- |
| Done | Systems browsing | It is heavily linked from Session, Combat, Characters, and DM Content, and the Flask presenters already separate browse context from browser routes. | Gen2 landing/search, source, category, and entry detail can be used without losing visibility rules or rendered Systems prose. |
| Done | Account settings | It is small, shared, and directly tied to theme and live-session preferences used by the Gen2 shell. | Users can change theme and live-session preference from Gen2 with the same persistence as Flask. |
| Done | Campaign Help | It is mostly static campaign guidance and is a good low-risk test of Gen2 matching Flask's explanatory page layout. | Help content is readable in Gen2, linked from the shared campaign chrome, and backed by player/DM browser coverage. |
| Done | Campaign Control | It is permission-sensitive but smaller than character authoring, and it controls visibility assumptions used by Gen2 navigation. | Visibility/config saves behave like Flask and preserve audit/history expectations. |
| 1 | Character authoring and management | It is the largest remaining workflow family. The portrait slice has landed; remaining lanes include native create/import, Advanced Editor, Cultivation, level-up, retraining, repair, controls, and deletion. | Each authoring lane has JSON or browser-backed parity, stale-state handling where needed, and fallback links until the whole family is accepted. |
| 2 | Admin | It is sensitive, low-frequency, and does not block player-facing Gen2 promotion. | Admin support/maintenance operations keep their existing permission and safety behavior. |

## Visual Parity Gate

Before a Gen2 route becomes the default replacement for a Flask route, it should match the Flask surface's established visual language and working layout closely enough that the framework change feels like a performance and interaction upgrade rather than a product redesign.

Promotion review should compare:

- app shell, campaign header, navigation density, theme behavior, and loading treatment
- page layout, panel hierarchy, spacing, typography, and card/table density
- mobile behavior and overflow handling
- form/control affordances, feedback states, and destructive-action confirmation patterns
- campaign content presentation, including images, captions, sidebar context, and rendered article/system text

## Visual/Layout Parity Checklist

Functional parity and visual parity are tracked separately. A surface can be feel-test ready for interaction while still blocked from default-route promotion by layout gaps.

| Surface | Flask reference | Gen2 route | Visual checks before promotion |
| --- | --- | --- | --- |
| Shared shell | `base.html`, `player_wiki/static/styles.css` | `/app-next/` and all Gen2 campaign routes | Global header height/density, centered campaign title treatment, campaign nav row wrapping, theme variables, account/admin affordances, loading cover/status behavior, and mobile header overflow. |
| Campaign home and search | `campaign.html` | `/app-next/campaigns/<slug>` | Hero scale, search placement, overview card density, section card hierarchy, pinned/featured content treatment, and empty/restricted-state copy rhythm. |
| Published wiki sections | `section.html` | `/app-next/campaigns/<slug>/sections/<section>` | Grouped subsection cards, collapse controls, featured/top-level page treatment, list density, mobile stacking, and long-title wrapping. |
| Published wiki pages | `page.html` | `/app-next/campaigns/<slug>/pages/<page>` | Article width, sidebar context, image/caption placement, rendered body typography, backlink/sidebar card density, and protected image sizing. |
| Session | `session.html`, `session_character.html`, `session_dm.html` and partials | `/app-next/campaigns/<slug>/session` | Pane switch density, player feed/composer proportions, revealed/staged article cards, Character section workspace, DM lifecycle/log panels, live update feedback, and desktop/mobile pane layout. |
| Characters | `character_roster.html`, `character_read.html` and character partials | `/app-next/campaigns/<slug>/characters...` | Roster card layout, portrait sizing, read-shell hierarchy, section navigation, resource/control density, fallback authoring links, and assigned-player restricted views. |
| Combat | `combat.html`, `combat_status.html`, `combat_dm.html` and partials | `/app-next/campaigns/<slug>/combat...` | Encounter summary, combatant carousel/list, selected-PC workspace, selected-combatant tactical card, setup forms, condition controls, deep-link focus, and mobile combat controls. |
| DM Content | `dm_content.html` and DM Content partials | `/app-next/campaigns/<slug>/dm-content...` | Lane tabs, editor forms, statblock/source cards, condition list/edit density, staged article store layout, Player Wiki image/upload controls, Systems management tables, and destructive confirmation affordances. |
| Systems browsing | `systems_*.html` | `/app-next/campaigns/<slug>/systems...` | Systems search, source cards, source/category lists, entry article typography, source/sidebar context, related-entry links, book/chapter navigation, and shared-entry management fallback links. |
| Account settings | `account_settings.html` | `/app-next/account` | Theme option grid, swatches, account sidebar, save feedback, Flask fallback link, and mobile stacking. |
| Campaign Help | `campaign_help.html` | `/app-next/campaigns/<slug>/help` | Explanatory hero density, current-access summary, surface guidance cards, visibility sidebar, cross-cutting notes, fallback link placement, and mobile stacking. |
| Campaign Control | `campaign_control_panel.html` | `/app-next/campaigns/<slug>/control` | Form density, select sizing, effective/configured/default metadata, campaign-floor override notes, rules sidebar, save feedback, fallback link placement, and mobile stacking. |
| Admin | Matching Flask templates | Planned Gen2 routes | Each route needs its own first visual comparison when its Gen2 pass lands. |

## Manual Acceptance Tracker

Manual acceptance is recorded after the user has tried the Gen2 surface in the local app. Acceptance should mention both functionality and visual/layout fit.

| Surface | Functional manual status | Visual/layout status | Notes |
| --- | --- | --- | --- |
| Session | Accepted for current functionality feel test | Needs visual parity pass | User noted the framework feels more responsive and Session appears functionally at parity, but layout still needs to match Flask. |
| Campaign home/wiki browsing | Pending explicit user acceptance | Needs visual parity pass | Browser coverage exists; user manual acceptance has not been recorded. |
| Characters read shell | Pending explicit user acceptance | Needs visual parity pass | Broader authoring remains Flask-first. |
| Combat | Pending explicit user acceptance | Needs visual parity pass | Live pressure remeasurement remains open before transport changes. |
| DM Content lanes | Pending explicit user acceptance | Needs visual parity pass | Functional browser coverage exists for statblocks, conditions, staged articles, Player Wiki, and Systems management. |
| Systems browsing | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for landing/search, source, category, and entry detail. |
| Account settings | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for theme and live-session preference saves. |
| Campaign Help | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for player and DM guidance views. |
| Campaign Control | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for manager save and player denial behavior. |
| Remaining Flask-first surfaces | Not ready | Not ready | Broader character authoring/management and Admin need Gen2 passes before manual acceptance. |

## Promotion Rules

- Keep Flask routes available until the corresponding Gen2 surface has been accepted after manual feel testing.
- Do not add redirects from Flask routes to Gen2 routes yet. Route-level redirects should wait until a surface is accepted for replacement and the fallback path is still obvious.
- Keep Flask fallback links on Gen2 surfaces for workflows that remain Flask-first or are still awaiting manual acceptance, especially character authoring, Systems imports/shared-core editing, Control, Help, Account, and Admin.
- Treat visual/layout parity as a promotion gate, not as cosmetic follow-up. Several Gen2 surfaces are functionally feel-test ready while still needing layout polish against the Flask rendition.

## Current Test Coverage

- `tests/test_frontend_pilot.py` verifies `/app-next/` static serving and SPA fallback for deep links.
- `tests/test_frontend_gen2_session_browser.py` covers the current promoted Gen2 feel-test surfaces: shell/session, wiki browsing, character roster/detail, combat player/status/controls, all DM Content lanes including Systems, Systems browsing, Account settings, Campaign Help, and Campaign Control.
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
- Keep the manual acceptance tracker current as the user tests each Gen2 surface.
- Turn the visual/layout parity checklist into screenshot-backed before/after review notes before any redirect decision.
- Continue the remaining Flask-first app page parity passes in the priority order above.
- Re-measure live pressure before changing transport strategy for Session or Combat.
- Decide the first route eligible for a Flask-to-Gen2 redirect only after functionality and layout are accepted.
