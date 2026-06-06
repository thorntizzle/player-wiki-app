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
| Character read/edit shell | `/campaigns/<slug>/characters/<character>` | `/app-next/campaigns/<slug>/characters/<character>` | Feel-test ready | Gen2 reuses the proven Character pane for DND-5E/Xianxia read, inline state edits, portrait upload/remove, owner assignment/clear, checked deletion, and authoring handoff links. |
| Character authoring | `/campaigns/<slug>/characters/new`, `/campaigns/<slug>/characters/import/xianxia-manual`, `/campaigns/<slug>/characters/<character>/edit`, `/campaigns/<slug>/characters/<character>/progression-repair`, `/campaigns/<slug>/characters/<character>/retraining`, `/campaigns/<slug>/characters/<character>/level-up`, `/campaigns/<slug>/characters/<character>/cultivation` | `/app-next/campaigns/<slug>/characters/new`, `/app-next/campaigns/<slug>/characters/import/xianxia-manual`, `/app-next/campaigns/<slug>/characters/<character>/edit`, `/app-next/campaigns/<slug>/characters/<character>/progression-repair`, `/app-next/campaigns/<slug>/characters/<character>/retraining`, `/app-next/campaigns/<slug>/characters/<character>/level-up`, `/app-next/campaigns/<slug>/characters/<character>/cultivation` | Feel-test ready | Gen2 uses JSON-backed native create contexts for DND-5E and Xianxia, Xianxia manual import preview/confirm, DND-5E Advanced Editor context/save, DND-5E progression repair context/save, DND-5E level-up context/save, DND-5E structured retraining context/save, and Xianxia Cultivation context/actions. |
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
| Admin | `/admin` | `/app-next/admin` and `/app-next/admin/users/<user_id>` | Feel-test ready | Gen2 covers dashboard/user detail, invites, membership and assignment management, invite/reset links, disable/enable, checked delete, audit filtering/pagination, CSV export fallback links, non-admin denial, and a Flask fallback link. |
| API token test field | None | Gen2 shell local field | Partial | Local testing aid only; browser cookies remain the default auth path. |

## Remaining Flask-First Surfaces Needing Gen2 Passes

All tracked functional surface passes in the current Gen2 roadmap now have a Gen2 route or explicit Gen2 handoff. Flask fallback links remain in place during manual acceptance, and CLI/bootstrap recovery operations intentionally remain outside the Gen2 browser scope.

## Next Gen2 Route Priority

The remaining Flask-first pages are not equally risky. Use this order unless a specific play-session need changes the priority:

| Priority | Surface | Why next | Acceptance target |
| --- | --- | --- | --- |
| Done | Systems browsing | It is heavily linked from Session, Combat, Characters, and DM Content, and the Flask presenters already separate browse context from browser routes. | Gen2 landing/search, source, category, and entry detail can be used without losing visibility rules or rendered Systems prose. |
| Done | Account settings | It is small, shared, and directly tied to theme and live-session preferences used by the Gen2 shell. | Users can change theme and live-session preference from Gen2 with the same persistence as Flask. |
| Done | Campaign Help | It is mostly static campaign guidance and is a good low-risk test of Gen2 matching Flask's explanatory page layout. | Help content is readable in Gen2, linked from the shared campaign chrome, and backed by player/DM browser coverage. |
| Done | Campaign Control | It is permission-sensitive but smaller than character authoring, and it controls visibility assumptions used by Gen2 navigation. | Visibility/config saves behave like Flask and preserve audit/history expectations. |
| Done | Character authoring and management | It was the largest remaining workflow family. Portrait, Controls/deletion, native create/import, Advanced Editor, Cultivation, progression repair, level-up, and retraining have landed. | Each authoring lane has JSON or browser-backed parity, stale-state handling where needed, and fallback links until the whole family is accepted. |
| Done | Admin | It is sensitive, low-frequency, and does not block player-facing Gen2 promotion. | Admin user-management operations keep their existing permission and safety behavior, with CLI/bootstrap recovery left as an intentional non-browser fallback. |

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

First visual parity slice completed on June 6, 2026: the Gen2 shared shell and Session route now reuse Flask-style theme variables, the centered campaign-title treatment, active campaign navigation pills, denser Session tabs/cards/forms, and desktop/mobile browser smoke coverage. Second visual parity slice completed on June 6, 2026: campaign home, published section pages, and published article pages now use the Flask-like unframed hero, framed browse bands, featured cards, collapsible subsection blocks, article/sidebar typography, image treatment, and desktop/mobile browser smoke coverage. Third visual parity slice completed on June 6, 2026: Characters roster/read shell now use the Flask-like compact roster hero, framed roster tools band, denser roster cards, character read-sheet shell, selector card, stat/resource card treatment, section navigation treatment, and desktop/mobile browser smoke coverage. Fourth visual parity slice completed on June 6, 2026: Combat player, DM status, and DM controls now use the Flask-like unframed combat hero, framed encounter summary, turn-order carousel, inspected-combatant snapshot, tactical/control cards, condition chips, and desktop/mobile browser smoke coverage. Fifth visual parity slice completed on June 6, 2026: DM Content statblocks, staged articles, conditions, Player Wiki, and Systems lanes now use the Flask-like compact hero, lane tab strip, framed editor/library panels, denser content/source cards, staged article and Player Wiki management layouts, Systems management cards, destructive confirmation treatment, and desktop/mobile browser smoke coverage. These are visual checkpoints, not default-route promotions.

| Surface | Flask reference | Gen2 route | Visual checks before promotion |
| --- | --- | --- | --- |
| Shared shell | `base.html`, `player_wiki/static/styles.css` | `/app-next/` and all Gen2 campaign routes | First parity slice covers theme variables, centered campaign title treatment, active campaign nav pills, account/admin affordances, collapsed API-token testing control, and mobile overflow smoke coverage. Loading-cover equivalence and manual visual acceptance remain open. |
| Campaign home and search | `campaign.html` | `/app-next/campaigns/<slug>` | First wiki visual slice covers unframed hero treatment, overview card density, framed browse/search results band, section card hierarchy, and desktop/mobile overflow smoke coverage. Search control placement remains tied to the shared Gen2 shell and still needs manual visual review. |
| Published wiki sections | `section.html` | `/app-next/campaigns/<slug>/sections/<section>` | First wiki visual slice covers unframed section hero, featured page cards, collapsible subsection blocks, collapse/expand controls, long-title wrapping, and mobile stacking smoke coverage. Manual visual review remains open. |
| Published wiki pages | `page.html` | `/app-next/campaigns/<slug>/pages/<page>` | First wiki visual slice covers article width/sidebar context, rendered body typography without boxed preview chrome, image/caption treatment, protected image sizing, and mobile stacking smoke coverage. Backlink/sidebar density still needs manual visual review. |
| Session | `session.html`, `session_character.html`, `session_dm.html` and partials | `/app-next/campaigns/<slug>/session` | First parity slice covers pane-tab density, theme-backed player/DM cards, Session Character workspace cards, desktop/mobile layout smoke coverage, and active campaign nav. Player feed/composer proportions, DM article/log panel comparison screenshots, and manual visual acceptance remain open. |
| Characters | `character_roster.html`, `character_read.html` and character partials | `/app-next/campaigns/<slug>/characters...` | First character visual slice covers roster hero/tools layout, roster card density, portrait sizing, read-shell hierarchy, selector card, section navigation, stat/resource card density, fallback authoring links, assigned-player restricted views, and mobile overflow smoke coverage. Manual visual review remains open. |
| Combat | `combat.html`, `combat_status.html`, `combat_dm.html` and partials | `/app-next/campaigns/<slug>/combat...` | First combat visual slice covers unframed combat hero, framed encounter summary, turn-order carousel/list, inspected-combatant snapshot, selected-PC workspace header, selected-combatant tactical cards, setup forms, condition chips, deep-link focus surfaces, and mobile overflow smoke coverage. Manual visual review and live pressure remeasurement remain open. |
| DM Content | `dm_content.html` and DM Content partials | `/app-next/campaigns/<slug>/dm-content...` | First DM Content visual slice covers lane tabs, editor forms, statblock/source cards, condition list/edit density, staged article store layout, Player Wiki image/upload controls, Systems management cards, destructive confirmation affordances, and mobile overflow smoke coverage. Manual visual review remains open. |
| Systems browsing | `systems_*.html` | `/app-next/campaigns/<slug>/systems...` | Systems search, source cards, source/category lists, entry article typography, source/sidebar context, related-entry links, book/chapter navigation, and shared-entry management fallback links. |
| Account settings | `account_settings.html` | `/app-next/account` | Theme option grid, swatches, account sidebar, save feedback, Flask fallback link, and mobile stacking. |
| Campaign Help | `campaign_help.html` | `/app-next/campaigns/<slug>/help` | Explanatory hero density, current-access summary, surface guidance cards, visibility sidebar, cross-cutting notes, fallback link placement, and mobile stacking. |
| Campaign Control | `campaign_control_panel.html` | `/app-next/campaigns/<slug>/control` | Form density, select sizing, effective/configured/default metadata, campaign-floor override notes, rules sidebar, save feedback, fallback link placement, and mobile stacking. |
| Admin | `admin.html`, admin user-detail templates | `/app-next/admin` and `/app-next/admin/users/<user_id>` | Dashboard/user list density, invite and membership forms, user-detail action grouping, audit filter/list pagination, CSV export fallback placement, destructive confirmation affordances, non-admin denial, and mobile stacking. |

## Manual Acceptance Tracker

Manual acceptance is recorded after the user has tried the Gen2 surface in the local app. Acceptance should mention both functionality and visual/layout fit.

| Surface | Functional manual status | Visual/layout status | Notes |
| --- | --- | --- | --- |
| Session | Accepted for current functionality feel test | First shared-shell/Session parity slice complete; manual visual acceptance still needed | User noted the framework feels more responsive and Session appears functionally at parity. The first visual slice now aligns the shared shell and Session styling with Flask, but it still needs user visual review before promotion. |
| Campaign home/wiki browsing | Pending explicit user acceptance | First visual parity slice complete; manual visual acceptance still needed | Browser coverage exists for home, sections, article pages, protected assets, and the first wiki visual parity smoke. User manual acceptance has not been recorded. |
| Characters read shell | Pending explicit user acceptance | First character visual parity slice complete; manual visual acceptance still needed | Portrait controls, owner assignment/clear, checked deletion, native create/import, Advanced Editor, Cultivation, progression repair, level-up, and retraining now have Gen2 parity. Roster/read shell layout has desktop/mobile visual smoke coverage. |
| Combat | Pending explicit user acceptance | First combat visual parity slice complete; manual visual acceptance still needed | Player, DM status, and DM controls have desktop/mobile visual smoke coverage. Live pressure remeasurement remains open before transport changes. |
| DM Content lanes | Pending explicit user acceptance | First DM Content visual parity slice complete; manual visual acceptance still needed | Functional browser coverage exists for statblocks, conditions, staged articles, Player Wiki, and Systems management. Desktop/mobile visual smoke now covers all five lanes. |
| Systems browsing | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for landing/search, source, category, and entry detail. |
| Account settings | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for theme and live-session preference saves. |
| Campaign Help | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for player and DM guidance views. |
| Campaign Control | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for manager save and player denial behavior. |
| Admin | Pending explicit user acceptance | Needs visual parity pass | Functional API/browser coverage exists for dashboard/user detail, invite/reset, membership, assignment, disable/enable, checked deletion, audit filters, and non-admin denial. |

## Promotion Rules

- Keep Flask routes available until the corresponding Gen2 surface has been accepted after manual feel testing.
- Do not add redirects from Flask routes to Gen2 routes yet. Route-level redirects should wait until a surface is accepted for replacement and the fallback path is still obvious.
- Keep Flask fallback links on Gen2 surfaces for workflows that remain fallback-only or are still awaiting manual acceptance, especially Systems imports/shared-core editing, CLI/bootstrap recovery handoffs, and newly ported surfaces such as Admin.
- Treat visual/layout parity as a promotion gate, not as cosmetic follow-up. Several Gen2 surfaces are functionally feel-test ready while still needing layout polish against the Flask rendition.

## Current Test Coverage

- `tests/test_frontend_pilot.py` verifies `/app-next/` static serving and SPA fallback for deep links.
- `tests/test_frontend_gen2_session_browser.py` covers the current promoted Gen2 feel-test surfaces: shell/session, wiki browsing, character roster/detail including Controls access, Xianxia create/import/Cultivation fallback behavior, combat player/status/controls, all DM Content lanes including Systems, Systems browsing, Account settings, Admin, Campaign Help, and Campaign Control.
- `tests/test_frontend_gen2_session_browser.py::test_gen2_shell_and_session_visual_parity_smoke` covers the first visual parity slice with desktop shell/session style checks and mobile overflow checks.
- `tests/test_frontend_gen2_session_browser.py::test_gen2_wiki_visual_parity_smoke` covers the campaign home, published section, and published article visual parity slice with desktop layout checks and mobile overflow checks.
- `tests/test_frontend_gen2_session_browser.py::test_gen2_character_visual_parity_smoke` covers the character roster/read-shell visual parity slice with desktop layout checks and mobile overflow checks.
- `tests/test_frontend_gen2_session_browser.py::test_gen2_combat_visual_parity_smoke` covers the Combat player, DM status, and DM controls visual parity slice with desktop layout checks and mobile overflow checks.
- `tests/test_frontend_gen2_session_browser.py::test_gen2_dm_content_browser_visual_parity_smoke` covers the DM Content statblocks, staged-articles, conditions, Player Wiki, and Systems visual parity slice with desktop layout checks and mobile overflow checks.
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
- Keep visual/layout parity moving before any redirect decision; the current functional surface backlog is complete for the active Gen2 roadmap, and Systems browsing is the next recommended visual target.
- Re-measure live pressure before changing transport strategy for Session or Combat.
- Decide the first route eligible for a Flask-to-Gen2 redirect only after functionality and layout are accepted.
