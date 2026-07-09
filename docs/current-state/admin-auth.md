# Admin, Auth, And Visibility

Last updated: 2026-07-09

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

## Current Tests Or Verification

- Auth/admin changes usually need focused route tests, permission checks, audit assertions, or API checks for membership, assignment, theme/preference, and visibility behavior.

## Known Limits

- CLI/bootstrap recovery remains the safest path when browser access or initial admin setup is broken.

## Related Backlog

- `.local/roadmaps/ops-backlog.md`

## Source Pointers

- `player_wiki/auth.py`
- `player_wiki/auth_store.py`
- `player_wiki/admin_context.py`
- `player_wiki/admin_audit.py`
- `player_wiki/campaign_visibility.py`
- `player_wiki/player_choices.py`
