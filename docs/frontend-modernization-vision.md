# Frontend Modernization Vision

Status: planning reference, not current-state contract.

This document captures the post-backend-rewrite direction for making Campaign
Player Wiki feel like a modern web application instead of a collection of
Flask-era pages. It should guide pilots and backlog decomposition after the
TypeScript backend rewrite has a stable app/API contract.

The holistic backend/frontend rewrite plan lives in
`docs/typescript-backend-rewrite/holistic-rewrite-plan.md`.

Current shipped behavior remains documented in `docs/current-state/`. Active
future work belongs in `.local/roadmaps/gen2-frontend-backlog.md` or the narrow
surface backlog for the pilot being implemented.

## Product Aim

Campaign Player Wiki should feel like a dense, calm tabletop operations
workspace:

- Persistent campaign context stays visible while the active workspace changes.
- Session, Combat, Character, DM Content, Systems, and Wiki surfaces use the
  space available in the viewport instead of inheriting page-shaped Flask
  constraints.
- Frequently used gameplay values and actions are available at a glance.
- Route changes, panel changes, and mutations feel responsive without hiding
  server truth.
- Motion and dynamic layout clarify state changes; they do not decorate or slow
  down live play.

## Source Material

Use the local UX guide first:

- `docs/frontend-ux-style-guide.md`
- `docs/frontend-ux-audit-checklist.md`
- `docs/current-state/frontend-gen2.md`

Use these outside references for specific implementation choices:

- TanStack Router data loading: https://tanstack.com/router/latest/docs/guide/data-loading
- TanStack Router code splitting: https://tanstack.com/router/latest/docs/guide/code-splitting
- TanStack Query invalidation: https://tanstack.com/query/latest/docs/framework/react/guides/query-invalidation
- TanStack Query optimistic updates: https://tanstack.com/query/v4/docs/framework/react/guides/optimistic-updates
- React `useTransition`: https://react.dev/reference/react/useTransition
- React `Suspense`: https://react.dev/reference/react/Suspense
- MDN CSS container queries: https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_queries
- MDN View Transition API: https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API
- Motion layout animations: https://motion.dev/docs/react-layout-animations
- Motion `AnimatePresence`: https://motion.dev/docs/react-animate-presence

These are references, not pre-approved dependencies. Add a runtime dependency
such as Motion only after a pilot proves the app needs it and the bundle/runtime
cost is acceptable.

## App Patterns To Grow

### Persistent Workspace Shell

Keep campaign identity, account/view-as state, global search, and campaign
navigation stable while the inner workspace changes. Favor route-level state and
panel-local state over hard page swaps when the user is staying inside the same
campaign task.

### Adaptive Workspaces

Use split panes, docked sidebars, compact summary bands, and local subviews for
surfaces that users operate during play. Avoid forcing every task into one
vertical document flow.

Good candidates:

- Combat: encounter summary, selected combatant, tracker controls, source
  resources, and character inspection.
- Session: chat, staged/revealed articles, character pane, and DM controls.
- Character: stable identity/vitals header with swappable subpage panels.
- DM Content: statblocks, conditions, staged articles, and Systems management as
  adjacent work lanes.

### Widget-First Gameplay Surfaces

Treat high-frequency gameplay elements as widgets with clear local state:

- HP, AC, saves, initiative, turn state, and conditions.
- Spell slots, resources, equipment state, inventory, and rest previews.
- Staged/revealed article counts and session status.
- Combat source counters and unsupported read-only source notes.

Widgets should be compact, keyboard reachable, and resilient during polling or
background refetches.

### Progressive Data Loading

Prefer route shells that become useful quickly while heavier panels load in
place. Use TanStack Router pending behavior, route chunking, TanStack Query
cache state, and React transition/Suspense boundaries to avoid whole-page
loading for in-page changes.

The global loading cover remains for document or primary route transitions.
In-page selections should use local skeletons, pending affordances, disabled
states with reasons, or inline recovery messages.

### Optimistic But Honest Mutations

Use optimistic updates only where rollback behavior is clear and server
rejection can be explained near the affected control. For authoritative game
state, prefer fast invalidation or targeted cache updates over speculative UI
when a wrong value would confuse play.

Mutation feedback should keep the app interactive:

- Immediate local pending state for the touched widget.
- Toast for short success/info feedback.
- Inline persistent errors for failed saves, permission problems, or validation
  issues.
- Query invalidation or cache update scoped to the affected surface.

### Container-Aware Layout

Use container queries and stable layout primitives so a widget can adapt to
main-column, sidebar, tablet, and mobile placements. Component behavior should
respond to available panel width, not only viewport width.

### Measured Motion

Use motion for orientation:

- Expanding or collapsing panels.
- Moving between list/detail states.
- Reordering visible combat or session elements.
- Entering/exiting local dialogs, drawers, or preview panes.

Motion must respect reduced-motion preferences and should never hide text, delay
action feedback, or make live-play controls harder to target.

## Pilot Candidates

Pick one pilot after the TypeScript backend rewrite stabilizes. Do not redesign
all surfaces at once.

### Combat Workspace Pilot

Why: highest live-play value and strongest need for dense dynamic layout.

Possible pilot scope:

- Persistent encounter summary band.
- Main tracker and selected combatant panel.
- Container-aware source-resource controls.
- Local selected-PC inspection without page scroll reset.
- Verifier pass for keyboard/focus and polling stability.

### Session Workspace Pilot

Why: combines live chat, article reveal workflow, character context, and
DM/player mode differences.

Possible pilot scope:

- Split chat/article/character panes.
- Local pending state for staged/revealed article changes.
- Stable scroll behavior during polling.
- Animated article preview or reveal transitions.

### Character Workspace Pilot

Why: many repeated widgets and high density, but lower live coordination risk
than Combat.

Possible pilot scope:

- Stable character identity/vitals header.
- Adaptive spell/resource/equipment widgets.
- Container-aware subpage layout.
- Local panel transitions for sheet sections.

## Decision Gates

Stop for user input before:

- Choosing the first pilot surface if multiple are viable.
- Adding a new frontend dependency.
- Replacing a core navigation pattern across the app.
- Changing live Combat or Session workflows in ways that alter table behavior.
- Removing Flask fallback behavior before the rewrite plan explicitly calls for
  it.
- Changing source-of-truth semantics for optimistic updates or conflict
  resolution.

## Implementation Sequence

1. Finish the TypeScript backend rewrite slices needed for a stable API
   contract.
2. Audit the chosen pilot surface against this vision and
   `docs/frontend-ux-style-guide.md`.
3. Define a narrow pilot backlog item with target files, user-visible behavior,
   validation checks, and rollback path.
4. Build reusable primitives only when the pilot proves they are needed across
   at least two surfaces.
5. Verify with targeted tests plus browser/screenshot review at desktop, tablet,
   and mobile widths.
6. Update current-state docs only after shipped behavior changes.
7. Use pilot findings to revise this vision or open follow-up items in the
   narrowest backlog.

## Acceptance Checks For Modernized Surfaces

- The surface remains usable on first load and during background refetches.
- Primary gameplay values are visible without scrolling in the common desktop
  layout.
- Keyboard users can reach all controls and see focus.
- Reduced-motion users are not forced through animated transitions.
- Mobile layout avoids horizontal scrolling and preserves action clarity.
- Loading, pending, success, and error states are local to the affected workflow.
- The app shell and global search remain stable during in-campaign navigation.
- The surface uses existing theme tokens and shared components unless a new
  pattern is documented.
