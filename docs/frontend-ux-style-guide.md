# Frontend UX Style Guide

This guide defines the working UX standards for the Campaign Player Wiki frontend. It is intended for Gen2/TanStack work and for Flask compatibility surfaces that share the same visual language.

The goal is not to copy a generic SaaS design system. The app is a live tabletop operations tool and campaign reference. Its interface should be dense enough for play, calm enough for repeated use, and consistent enough that new features feel native without needing a fresh design conversation every time.

## Source Standards

Use these external standards as the baseline:

- [Nielsen Norman Group: 10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) for broad UX review.
- [W3C WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/) for measurable accessibility requirements.
- [WAI-ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/) for tabs, dialogs, buttons, disclosures, menus, and other interactive patterns.
- [U.S. Web Design System](https://designsystem.digital.gov/) as a practical reference for accessible buttons, forms, cards, validation, and operational layouts. Borrow principles and interaction patterns, not its visual skin.

## Product Principles

- Optimize live-play surfaces for scanning and action. Session, Combat, and Character views should prioritize the values and controls needed at the table.
- Preserve domain language. Use terms players and DMs recognize: Session, Character, Spell Slots, Resources, Staged Articles, Revealed Articles, Combatant, Turn, Vitals.
- Hide implementation details. Do not surface revisions, slugs, internal status fields, source paths, tokens, raw IDs, or backend vocabulary unless the user is in a debugging/admin context where it is meaningful.
- Prefer recognition over recall. Section tabs, button labels, field labels, card headings, and status text should make the next action obvious without reading documentation.
- Keep chrome light. Do not add context widgets, duplicate navigation, or low-value metric boxes when the header, active route, or existing page structure already communicates the information.
- Keep parity intentional. Gen2 can improve on Flask, but it should not drift into a different design language without a reason.

## Page Structure

- Every full page has one `h1` in the hero or primary article header.
- Use compact heroes for work surfaces. Hero text should orient, not market.
- Put page-wide navigation in the hero action area or a stable subheader, not in repeated cards.
- Use direct `main` children for primary page sections. Avoid wrapper panels around the whole route.
- Use `page-layout` when a page has a main column and sidebar.
- Use grid layouts for repeated entities: campaigns, character cards, resources, spell cards, statblocks, Systems entries, and section cards.
- Avoid horizontal overflow at desktop and mobile widths.
- Maintain useful vertical density. If a card only repeats context already visible elsewhere, remove it or move the signal into the page header.

## Typography And Text

- Keep one clear hierarchy: hero eyebrow, `h1`, lede/meta, section `h2`, card `h2` or `h3`, body text, metadata.
- Labels and values must be visually distinct. Labels should be readable enough to scan; values should not visually collide with labels.
- Gameplay values should stand out. HP, AC, spell slots, modifiers, saves, actions, turn state, and resource counts deserve stronger weight, size, or color than ordinary metadata.
- Metadata should stay secondary. Do not use tiny metadata styling for values users need during play.
- Use direct, concrete text. Avoid explaining the interface inside the interface unless the user needs recovery guidance or a workflow constraint.
- Use title case for page and card headings only where the surrounding app already does. Prefer sentence case for helper text and form labels.
- Avoid long unbroken button text. Use concise verb labels and move explanation into nearby meta text if needed.
- Do not use visible text to describe purely visual styling.

## Buttons, Links, And Actions

- Links navigate. Buttons mutate, submit, toggle, reveal, save, start, close, delete, or open in-page UI.
- Use `button-link` for the primary local action when it is a link-shaped navigation affordance.
- Use `ghost-button` for secondary navigation, low-emphasis actions, and confirmed destructive actions after the surrounding form/card has carried the warning.
- Use one primary action per local workflow. Do not make every available action visually primary.
- Use verbs for action labels: `Save`, `Search`, `Reveal`, `Stage article`, `Start session`, `Close session`, `Open sheet`, `Delete log`.
- Destructive actions require confirmation when the action deletes, archives, clears, closes, or otherwise removes user-visible data.
- Destructive actions should be visible but not dominant. The confirmation mechanism should carry the danger, not a loud button style.
- Button groups must have a predictable order: primary action first when it starts the main flow; cancel/back/secondary actions adjacent but visually quieter.
- Disabled controls need a visible reason nearby when the next step is not obvious.

## Forms And Inputs

- Labels must be explicitly associated with inputs.
- Validation and error text should appear near the affected field.
- Form controls should appear in DOM order matching visual order.
- Use select controls for bounded option sets, checkboxes/toggles for binary state, number inputs or steppers for numeric state, and textareas for longer prose.
- Keep save actions near the end of the form or local edit block.
- Separate independent saves when the underlying workflow is independent, such as theme save and chat-order save.
- Preserve user-entered drafts across polling and live updates whenever possible.
- Avoid immediate autosave unless the control clearly behaves as an inline state control and has reliable feedback.

## Cards, Panels, And Density

- Cards are for bounded tools, repeated items, forms, and sidebar blocks.
- Do not put UI cards inside other UI cards.
- Do not use a card just to restate page context.
- Repeated cards should have a stable layout and comparable heights where users scan across rows.
- Prefer three-column grids for dense play modules on desktop when the content supports it: resources, spell slots, spell cards, compact stat modules.
- Use one-column mobile layouts with clear rhythm and no horizontal scrolling.
- Sidebar cards should contain secondary support: navigation, metadata, management actions, or rules notes. They should not hold primary workflow controls unless the page is explicitly a sidebar/main workflow.

## Status, Loading, And Feedback

- Use global route loading only for document or route transitions that change the primary page.
- Do not show the global loading cover for in-page selections after the page is mounted.
- Keep the loading curtain stable while visible. The image or background must not swap while the cover is on screen.
- Short success or informational messages should use toast overlays in the upper left so they are visible regardless of scroll position.
- Persistent warnings, validation errors, and permission denials should stay inline near the relevant control or page region.
- Error messages should name the problem and the next recovery action when possible.
- Avoid bottom-appended status messages for actions that can happen far below the viewport.

## Navigation And Route Behavior

- Keep Gen2 navigation inside `/app-next` unless the user explicitly chooses a Flask fallback or unsupported legacy lane.
- Top navigation and page subnavigation should use real hrefs for fallback and new-tab behavior while preserving same-document TanStack navigation when possible.
- Use hero-local subnavigation for major page modes such as Session, Character, DM, DM Content lanes, and Combat DM subviews.
- Use section-navigation subheaders for wiki section/article pages, but not for the campaign home section-card grid.
- Preserve route search params for meaningful selected state, such as active lanes, combat views, selected combatants, and searches.

## Gameplay Value Presentation

- High-frequency values must be legible at a glance.
- For DND-5E character stats, ability names should use full names when space allows. Avoid showing short and full names together unless the abbreviation provides real utility.
- Modifiers and saves should be visually stronger than raw ability scores when they are more useful during play.
- Skill proficiency should be a visual marker rather than extra cramped text where possible. Thin border can indicate proficiency; thicker border can indicate expertise.
- Spell cards should separate name, level/school, tags, and action/range/duration facts into distinct lines.
- Spell and resource grids should reduce vertical footprint without compressing text into unreadable rows.

## Accessibility Floor

- Text contrast should meet WCAG 2.2 AA: 4.5:1 for normal text and 3:1 for large text.
- Interactive component boundaries, icons, and focus indicators should have sufficient contrast against their backgrounds.
- All interactive elements must be keyboard reachable and visibly focused.
- Native semantic elements are preferred: `button`, `a`, `form`, `label`, `input`, `select`, `textarea`, `details`, `summary`.
- Use ARIA to complete semantics, not to replace native HTML when native HTML works.
- Dialogs, tabs, disclosures, and menus should follow WAI-ARIA APG keyboard and labeling patterns.
- Do not rely on color alone to convey active, error, proficiency, danger, or disabled state.
- Page and control labels should be understandable to screen readers without visual-only context.

## Implementation Standards

- Prefer existing app classes and components before creating new visual systems.
- New reusable patterns should become components only when at least two surfaces need them or when the pattern carries accessibility behavior.
- Use CSS tokens and existing theme variables instead of hard-coded colors.
- Do not introduce one-off button/card/form variants without updating this guide or documenting why the surface is exceptional.
- Tests can enforce source-level structure for important UX contracts, but visual acceptance still needs browser review for dense or responsive surfaces.
- When a UX polish task changes a repeated pattern, update the guide or audit checklist in the same pass.
