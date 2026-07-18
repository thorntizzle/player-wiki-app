# Admin, Auth, And Visibility

Last updated: 2026-07-18

## Owns

- Authentication, account settings, user preferences, app/campaign roles, campaign visibility settings, character assignment choices, admin audit/activity, and bootstrap/admin recovery boundaries.

## Current User-Facing Behavior

- Signed-in users have an `Account` link in the global header. `/account` exposes account settings.
- User-level color themes are stored in SQLite and drive shared shell/card/form styling through CSS variables.
- User-level live-session chat order is stored in SQLite and controls the signed-in viewer's live Session chat order.
- Current theme presets are `Parchment`, `Moonlit Ledger`, `Verdant Archive`, and `Ember Court`.
- App admins can access Admin dashboard/user-detail surfaces and campaign-wide controls.
- App admins can use `View as` to preview campaign pages as another active user. The real admin remains the authenticated actor for `/me`, account, and admin surfaces, while campaign-facing safe reads use the selected user's effective role, memberships, and visibility.
- Campaign DMs can manage campaign content and scoped surfaces according to campaign permissions.

## Role And Visibility Contract

- App roles include app-wide `admin` plus campaign-scoped `dm`, `player`, and `observer`.
- Visibility states are `public`, `players`, `dm`, and `private`.
- Effective visibility for a campaign scope is the more private of campaign-level visibility and that scope's own visibility.
- Only admins can set `private`.
- Current Linden Pass defaults are campaign/wiki `public`, systems/session/combat `players`, and DM Content/characters `dm`.
- Campaign system policy can override unconfigured per-scope defaults before SQLite visibility rows exist.

## Admin Contract

- Admin dashboard and user detail share context helpers for campaign titles, campaign select choices, character assignment choices, invite defaults, membership edit defaults, assignment edit defaults, audit user references, and dashboard user-card summaries.
- Audit/activity presentation is shared between Flask Admin and the Admin API.
- Account-action and destructive admin workflows should keep checked/confirmed flows where needed.
- `View as` is admin-only, cannot be enabled by non-admin users, clears stale or invalid targets, and blocks campaign API writes while active with `403 view_as_read_only` so previewing another user's access does not accidentally mutate campaign state.

## Technical Ownership

- The final Phase 3B Auth/Admin ownership inventory is integrated on pushed `main` and deployed as Fly release `223`, built from exact commit `e5bd742676b958fa5af932c2489b8972d3bbca1a`. This deployment performed no explicit database or content sync and no private-data write; the later documentation closeout is not part of the deployed image.
- Twelve Auth registrar modules own all 13 Auth rules and 15 method/path contracts with singular ownership and dedicated transport coverage. `auth.py` retains request hooks, shared auth/access helpers, dependency wiring, and one direct route decorator.
- Admin owns 30 rules and 30 method/path contracts: 14 browser rules remain in `admin.py`, 12 API rules are registered by `admin_api_routes.py`, and four campaign-visibility rules are registered by `campaign_visibility_routes.py`. The extraction preserves supported endpoints, methods, authorization, payloads, redirects, audit ordering, persistence behavior, and wrapper order.

## Security And Runtime Contract

- Failed authentication uses constant-cost credential checking and bounded per-client/per-account throttling, including bounded in-memory throttle state.
- Browser mutations require CSRF validation. Existing JSON API bearer-token behavior and the public route, role, and visibility contracts are unchanged.
- Production startup fails fast when the application secret is missing, weak, or still a known development default.
- Request and application logging omit query values, redact one-time path credentials, and avoid exception text that could disclose tokens or other credentials.
- Auth, token-bearing, account, and Admin HTML responses use `no-store`. Shared security and privacy headers apply to browser responses, including nonce-based content security policy and production HSTS where appropriate.

## Current Tests Or Verification

- Auth/admin changes usually need focused route tests, permission checks, audit assertions, API checks for membership, assignment, theme/preference, and visibility behavior, and security checks for throttling, CSRF, log redaction, cache policy, and production configuration.

The Phase 3B transport boundary is on pushed `main` and deployed as release `223`. The deployed startup kept schema version 1 at version 1 and created no pre-migration backup because no migration was pending; no explicit database/content sync or private-data write was performed.

## Known Limits

- CLI/bootstrap recovery remains the safest path when browser access or initial admin setup is broken.

## Related Backlog

- `.local/roadmaps/ops-backlog.md`

## Source Pointers

- `player_wiki/auth.py`
- `player_wiki/auth_*_routes.py`
- `player_wiki/auth_store.py`
- `player_wiki/admin.py`
- `player_wiki/admin_api_routes.py`
- `player_wiki/admin_context.py`
- `player_wiki/admin_audit.py`
- `player_wiki/campaign_visibility.py`
- `player_wiki/campaign_visibility_routes.py`
- `player_wiki/player_choices.py`
