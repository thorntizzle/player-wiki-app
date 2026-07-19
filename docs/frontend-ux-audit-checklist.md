# Frontend UX Audit Checklist

Use this checklist when reviewing or polishing Flask browser surfaces. The detailed standards live in [frontend-ux-style-guide.md](frontend-ux-style-guide.md).

The checklist is intentionally practical. Mark each item as Pass, Needs Work, or Not Applicable, then capture the smallest concrete follow-up that would make the page consistent.

## Audit Scope

Record the following before starting:

- Page or route:
- Viewport sizes checked:
- User role checked:
- Campaign/system checked:
- Data state checked:
- Browser verification method:

Recommended baseline viewports:

- Desktop: `1280x900`
- Mobile: `390x800`

Recommended baseline roles:

- Signed-out public viewer when supported
- Player
- DM
- App admin when the surface has admin-only controls

## 1. Page Orientation

- The page has one clear `h1`.
- The hero or primary heading identifies the current surface without duplicating obvious context.
- The lede or helper copy is useful and not decorative.
- Campaign and user context are not repeated in bulky cards when already visible in the shell.
- Section navigation appears only where it helps the current workflow.
- Unsupported or permission-denied states explain what is unavailable and why.

## 2. Navigation And Route Behavior

- Links stay on Flask routes such as `/campaigns/...`, `/account`, and `/admin` unless they intentionally leave the app.
- Links use real `href` values and work with open-in-new-tab behavior.
- Route search params preserve meaningful state, such as active lane, selected combatant, selected page, or search query.
- Subnavigation active states are visually obvious and not color-only.
- Back, close, cancel, and return links have predictable destinations.
- The first focus stop is a visible `.skip-link` whose real `href` targets the named `#main-content` landmark, and activation visibly transfers focus to that landmark.

## 3. Text Hierarchy And Formatting

- Labels are legible and visually distinct from values.
- Gameplay values are visually stronger than metadata.
- Metadata is not used for values needed during live play.
- Long labels or values wrap cleanly without overlap.
- Button text fits its container on desktop and mobile.
- Body text is direct and uses user-facing terms rather than internal jargon.
- There are no visible implementation details such as revisions, raw slugs, raw IDs, source paths, or internal status fields unless the user is in a debug/admin context.

## 4. Buttons, Links, And Actions

- Links navigate; buttons mutate, submit, toggle, or open in-page UI.
- The primary local action is clear and singular.
- Secondary actions use quieter styling.
- Destructive actions are confirmed and visually contained.
- Action labels are concise verbs or verb phrases.
- Button groups have a predictable order.
- `.action-group` layouts retain native semantics: links navigate and buttons keep their intended submit or in-page behavior.
- Disabled actions have a visible reason when the next step is not obvious.
- Icon-only controls have accessible names and tooltips when the icon is not universally obvious.

## 5. Forms And Inputs

- Each input has an explicit label.
- Validation appears near the affected input.
- DOM order matches visual order.
- Inputs use the right control type for the job.
- Save actions are close to the form section they save.
- Independent saves are separated when the underlying data is independent.
- Draft input survives live polling and route updates where practical.
- Numeric inputs have clear bounds, units, and current/max context where needed.

## 6. Cards, Layout, And Density

- Cards frame bounded tools, repeated entities, forms, or sidebar support.
- There are no nested cards unless a modal or embedded object truly requires it.
- Repeated cards have consistent structure.
- Dense repeated modules use grids where appropriate.
- Desktop layout avoids excessive vertical stacking.
- Mobile layout stacks cleanly with no horizontal overflow.
- Sidebar content is secondary and does not hide primary workflow controls.
- Empty states use a card or clear section only when they replace missing content.
- Static empty, unavailable, and error `.state-panel` regions are associated with a visible or `.visually-hidden` heading and do not use `aria-live`, `role="status"`, or `role="alert"`.

## 7. Status, Loading, And Feedback

- Route loading appears only for document or route transitions.
- In-page selections after mount do not show the global loading cover.
- The loading cover does not swap images or visibly reset while shown.
- Toast messages are used for short success/info status.
- Persistent warnings and errors stay inline near the relevant region.
- Errors name the problem and give a recovery path when possible.
- Status messages are not appended at the bottom of long pages where users may miss them.
- Polling or live updates do not steal focus, reset drafts, or collapse open details unexpectedly.

## 8. Accessibility

- Text contrast meets WCAG 2.2 AA.
- Component borders, focus rings, and active states are visible.
- All interactive controls are keyboard reachable.
- Focus order matches visual order.
- The surface uses the single shared `.visually-hidden` helper rather than a competing utility definition.
- Native semantic elements are used where possible.
- ARIA is used only to complete behavior that native HTML cannot express.
- Dialogs, tabs, disclosures, and menus follow WAI-ARIA APG interaction patterns.
- Active, disabled, danger, proficiency, and error states are not conveyed by color alone.

## 9. Gameplay Surface Checks

For Session, Combat, and Character surfaces:

- High-frequency values are readable at a glance.
- HP, AC/Defense, saves, modifiers, spell slots, resources, turn state, and action economy are visually prioritized.
- Session status is compact and visible without taking content space.
- DM-only data is hidden from player Session views.
- Spell cards separate name, level/school, tags, and mechanics.
- Resource and spell-slot controls use compact multi-column layouts on desktop.
- Character skills show proficiency/expertise with visual markers rather than cramped text.
- Combat selection changes update the mounted view without hard route reload or global loading.

## 10. Source And Component Consistency

- The surface uses existing app classes and components before introducing new variants.
- New repeated patterns are componentized when they carry behavior or appear on multiple surfaces.
- New colors use theme variables or tokens.
- New UX conventions are added to the style guide if they are expected to repeat.
- Source-level tests are added or updated when the UX contract is important and stable.
- Browser or screenshot checks are run for responsive/dense layout changes.
- Representative desktop and mobile evidence covers keyboard skip navigation, visible focus, and no horizontal overflow where shared presentation primitives affect layout.

## Page-Specific Review Targets

Use these reminders for the major current surfaces:

- Campaign Picker: compact hero, campaign cards, no redundant shortcuts, clear signed-in/signed-out copy.
- Campaign Home: section-card grid, no wiki section subheader, no embedded Overview page dependency.
- Wiki Section and Article: section-navigation subheader, readable article body, backlink/sidebar only when useful.
- Session Player: compact session active/inactive signal, chat/composer first, no DM-only revealed article management.
- Session Character: high-density play values, compact resources/spells/inventory, no slugs or internal status fields.
- Session DM: staged/revealed/log/control hierarchy, DM-only management, clear lifecycle controls.
- Combat Player: selected tracked character, target controls, no loading cover for in-page combatant selection.
- Combat DM: tactical controls grouped by task, selected combatant state clear, destructive clear-tracker confirmation.
- Characters Roster: compact grid, clear create/import affordances, no unsupported-tool copy unless relevant.
- Character Detail: full-name ability headings, prioritized modifiers/saves, compact section navigation.
- DM Content: lane navigation in hero, dense item rows/cards, mutation feedback near the workflow.
- Systems: search and browse bands, source/category sidebars, no visible Flask fallback shortcuts for supported routes.
- Account: separate preference saves, clear current state, no retired frontend selector.
- Admin: dense operational layout, clear audit filtering, destructive account actions confirmed.

## Outcome Format

Use this concise format after an audit:

```text
Route:
Role/Data State:
Viewport Coverage:

Findings:
- [Severity] Area: issue and why it matters.

Follow-ups:
- Smallest concrete change.

Residual Risk:
- Anything not checked or needing manual confirmation.
```
