# Characters: DND-5E

Last updated: 2026-08-28

## Owns

- DND-5E native create, Advanced Editor, Level Up, Progression Repair, Retraining, PDF/markdown import convergence, read/session sheet behavior, spellcasting, equipment, Armor Class, attacks, and reimport precedence.

## Current User-Facing Behavior

- DND-5E character detail subpages: `Quick Reference`, `Resources`, `Spellcasting`, `Equipment`, `Inventory`, `Abilities and Skills`, `Personal`, `Portrait`, `Notes`, and `Controls`.
- Quick Reference shows core overview rows, editable HP/temp HP/Hit Dice for authorized users, tracked resources, carrying capacity when derivable, and defensive rules when modeled.
- Combat reminders from `stats.attack_reminder_state` belong on combat-facing attack panels, not normal Character Quick Reference.
- Spellcasting is the durable home for spell-list management. Prepared casters and wizards use local `Current spells` and `Preparation` subviews over the same durable rows.
- Equipment is the durable home for equip/unequip, attunement, weapon wield mode, supported feature-state toggles such as Armorer Arcane Armor, and Artificer infusion activation. Bespoke stateful character boons remain in their owning feature section.
- Inventory is the durable home for carried item rows, supplemental item adds, supported removals, quantity controls, and DND currency.
- Resources shows tracked current/max resource cards. Authorized editors can change each current value through the existing resource state path with both blur autosave and a visible per-card `Save` action.
- Spell detail popups include resolved upcasting text (e.g., `At Higher Levels`) when source-backed spell payload includes it; non-upcastable spells do not show an empty upcast section.
- Personal displays physical description/background reference text. Physical description/background authoring belongs in Advanced Editor.
- Notes displays player notes and imported/reference note sections. Editable users can save or confirmed-delete the mutable player note through the shared revision-checked notes path.
- Portrait displays a large unframed current portrait and supports one portrait slot with upload/remove for authorized users. PNG/JPG uploads are stored as WebP; GIF/WebP uploads pass through validation.
- Controls covers owner status, app-admin assignment/clear, and DM/admin checked deletion.

## Current Authoring And Support Matrix

- Native DND-5E create, edit, level-up, progression repair, and retraining are DND-5E-only.
- Native base-class boundary is explicit: PHB base classes plus the TCE Artificer lane.
- Supported subordinate non-PHB rows include current accepted SCAG, XGE, EGW, and DMG rows when attached to supported base classes.
- Native level-up is one level at a time through level 20 and can advance an existing class row or add a class row when the support matrix allows it.
- Progression repair resolves ambiguous imported class/subclass/species/background links and converts legacy imported spell marks to durable spell flags.
- Retraining is intentionally narrow: it supports persisted structured choices on existing linked custom features, not generic rebuilds or full respec.

## Current Guided Character Update Contract

- App admins and campaign DMs can open the manager-only `/campaigns/<campaign-slug>/characters/<character-slug>/update-preview` route for DND-5E characters. They can compose exact source-backed campaign feature or equipment grants, approved items from enabled Systems sources, and safe relinks from one unlinked equipment row to one exact source.
- Assigned-player access to the Advanced Editor does not grant this manager workflow, and observers cannot use it. An app admin using View As can inspect a visibly read-only GET surface, while the global authorization boundary blocks POST.
- The compose, review, and apply flow is server-rendered and works without JavaScript. It accepts only bounded operation choices and quantities; caller-supplied replacement definition, state, YAML, JSON, digest, or other unknown fields are rejected. Apply accepts only the reviewed token plus its intent and CSRF fields.
- Review is a pure, zero-write preview. It exposes sanitized operation status, state-impact and diagnostic summaries, plus additions, updates, and removals in only six semantic categories: features, equipment/inventory, spells, attacks, Armor Class, and resources.
- A `READY` review issues a canonical HMAC-SHA256 `cu1` token that expires after ten minutes. The bounded token is actor-, campaign-, and character-bound and attests the normalized operations; exact definition/import bytes and SQLite state tuple; source, policy, and prepared-native foundations; planner version and state impact; and candidate and semantic digests. It carries no replacement source bodies, file paths, secrets, CSRF data, or audit payload.
- Apply reauthorizes the manager, rejects incomplete or recovery-protected targets, reloads without initializing missing state, and recomputes the accepted operations exactly once from authoritative inputs. Any token, actor, target, operation, definition/import, state revision/serialized bytes/timestamp/updater, source, policy, native foundation, planner, candidate, or semantic drift returns `refused_stale` before publication. A reviewed no-op remains `unchanged` with no coordinator call, write, or audit.
- A changed accepted plan crosses the publication boundary once through `CharacterPublicationCoordinator`. `preserve_exact` keeps the entire SQLite state tuple unchanged. `reconcile_required` can only append the reviewed new resource or inventory rows, cannot change existing or opaque state, and advances the state revision once.
- Definition, import metadata, and allowed state are treated as one journal-backed character publication. The initial `BEGIN IMMEDIATE` transaction records the desired state and private recovery row before the exact `definition.yaml` and `import.yaml` bytes are published forward. Active `prepared`, `repository_pending`, or `conflict` rows hide and protect the character; ordinary-request recovery accepts exact prior or already-desired evidence, completes forward, and deletes the row after authoritative refresh. Third-party or missing evidence becomes a retained conflict rather than a rollback or overwrite. This provides forward completion across SQLite and campaign files, not a cross-store atomic transaction.
- Apply records one `character_update_applied` audit with sanitized metadata, including planner/candidate/review identities, state impact, and operation count. The audit is inserted in the same transaction that advances the journal to `repository_pending`, so recovery cannot duplicate it. If the actor account is later deleted, the retained journal truthfully nulls that foreign-key actor reference while preserving event type and metadata; prepared recovery may then write the one null-actor audit, repository-pending recovery writes none, and a retained conflict manufactures no audit.
- Authoritative readback compares definition, unchanged import metadata, exact or reconciled state, the single audit, and the six-category semantic projection. Results are `confirmed_applied`, `unchanged`, `refused_stale`, `failed` for a proven pre-publication zero-write failure, or `uncertain` after a publication-boundary/readback ambiguity. An `uncertain` result explicitly forbids blind retry and directs the manager to inspect current state first.

## Current Data/API Contract

- Save-time derivation is the authority for computed DND-5E sheet math on supported write paths.
- Read-time projection is transient compatibility/preview: it reruns supported normalization for current render/API payloads without writing back to the character definition, and failed transient normalization returns projection warnings while falling back to the stored definition/state.
- Shared derivation covers proficiency, saves, skills, passive checks, initiative, speed, carrying capacity, max HP when provenance exists, spell DC/attack, slot progression, Armor Class, attacks, and resource templates.
- Campaign `character_option` metadata supports structured `mechanic_effects` rows for modeled mechanics. Legacy string `modeled_effects` remain supported and are normalized into structured rows while preserving legacy effect keys for existing builder paths.
- Campaign `character_option.resource` grants are also mirrored as structured `resource_template` mechanic effects. Scaled resources such as Wild Magic's half-level Wild Die derive from metadata, keep their scaling payload on generated trackers, and do not require parsing descriptive page prose.
- DND mutable state includes HP/temp HP, per-die-size Hit Dice pools, exhaustion level, resources, spell-slot usage by slot lane, equipment state, inventory quantity, currency, notes, and feature states such as Arcane Armor and Divine Avatar Forms.
- Divine Avatar Forms is a versioned, registry-backed stateful campaign mechanic. DND-5E sheets receive individual forms through structured `divine_avatar_form_grant` mechanic rows; the exact `mechanics/divine-avatar-forms` page reference remains a narrow compatibility grant for Avatar of Mourning v1. Display titles never grant the mechanic, unknown systems are denied, and adding a future adapter does not implicitly grant that form to existing sheets. Versioned mutable state owns the single active-form identity while preserving opaque future form data.
- Avatar of Mourning activation requires the character to be conscious and below half hit points, grants non-stacking temporary HP, and restores spell slots. While active, an uncached transient derivation pass sets effective Wisdom to exactly 26 and applies AC +4 plus the additive +3 spell attack/save-DC bonus. The stored definition and true Wisdom are never replaced; when the form ends, or when an updated stored Wisdom is read, the inactive sheet immediately derives from that current true score. Projection failures fail closed before persistence and in presentation, while a structurally valid active form retains a permission-gated safe End action. Form actions require explicit confirmation and retain a bounded correction/action audit. Ending applies exhaustion, starts the 40-day cooldown, and creates a persistent pending table-resolution record for the single radiant-damage instance; resolution records the actual table-applied total but does not mutate HP automatically.
- `scripts/export_dnd_character_sheet.py` exports visible DND-5E character sheets to Markdown for a single character or all visible DND-5E characters in a campaign. The export uses the same presenter-normalized definition plus SQLite mutable state as the read sheet and intentionally omits image assets.
- Hit Dice max pools derive from class-row levels and hit-die metadata; current counts stay in SQLite. Long rests restore expended Hit Dice equal to half total character level, capped by pool maximum, and do not auto-heal HP. Rest confirmation fields let the user set final Current HP and current Hit Dice after the modeled rest recovery before applying the rest.
- State reconciliation treats unlabeled legacy spell-slot rows as migration-only once tracked slot lanes exist.
- Artificer active infusion state lives on targeted equipment rows as normalized `active_infusions`. Known infusions derive from modeled Artificer Infusions feature rows and known-infusion summaries, while active capacity derives from Artificer level.

## Current Spellcasting Contract

- Shared-slot multiclass spellcasting is limited to supported `full`, `1/2`, `artificer`, and currently supported `1/3` subclass-only lanes.
- Warlock Pact Magic remains a separate lane.
- Subclass-only spellcasting requires supported Systems metadata or bundled fallback coverage for PHB Eldritch Knight and Arcane Trickster.
- Spell add/update/remove actions route through an explicit target class row.
- Combat and Session Character consume only the Current spell set; unprepared candidates do not appear as castable spells there.
- Always-prepared grants stay out of manual prepared counts and should not render as separate source-package cards when each spell card already carries the badge.
- Always-prepared grants come from Systems metadata, explicit spell-support grants, supported class/subclass progression, or the bounded table-backed feature interpreter. The old subclass-title-only fallback is retired; legacy imported source labels such as `Cleric (Always Prepared)` still backfill durable always-prepared flags for older rows.
- Spell detail popups show `At Higher Levels` upcasting mechanics from presenter spell payloads when available and suppress the section when not present.

## Current Equipment, AC, And Attack Contract

- Equipment-state controls are narrower than Inventory: weapons, armor, and qualifying magic items belong on Equipment; general gear remains Inventory-only unless durable metadata says otherwise.
- Armor Class derives from equipped armor/shield state when durable equipment metadata is specific enough.
- Linked Systems armor metadata should be repaired in the Systems library rather than patched with character-side title parsing.
- Generated weapon attacks carry stable equipment refs, mode keys, and variant labels.
- Quick Reference hides linked weapon attacks when source items are not equipped and respects explicit wield modes.
- Armorer Arcane Armor is mutable character state at `feature_states.arcane_armor.enabled`; it gates Guardian Thunder Gauntlets and Defensive Field availability.
- Eligible Artificers get an Equipment-page Infusions lane. Active selections target eligible nonmagical inventory/equipment items; `Enhanced Defense` is automated as a +1 AC defensive rule while the infused armor or shield is equipped, and unsupported active infusion effects remain visible as active note-only rows instead of silent partial automation.
- Supported magic weapon/item effects require equipped state, and attunement-gated effects require attunement.
- Approved campaign-owned Systems `item` mechanics now use the same item metadata paths as shared DND item rows for supported weapons, armor, attunement, spell grants, resource modifiers, defensive rules, attack reminders, and spell-slot-funded item-use actions.
- Campaign item rows with `draft`, `manual_review`, or `reference_only` mechanics review status are visible as Systems entries but do not drive attacks, Armor Class, spell grants, resource math, or item-use automation.
- The first structured Linden Pass item records cover Consecrated Huran Blade, Censer of Last Light, Hourglass Pendant, Staff of the Crescent Moon, Psionic Circlet, and Innovator's Bolt. Supported fields can automate after approval; item spell support, item defensive rules, Hourglass Pendant, Psionic Circlet, Innovator's Bolt base weapon mechanics, and Innovator's Bolt enchanted bullet spell-slot expenditure now work from approved item metadata rather than title-specific character fallbacks. The approved Innovator's Bolt action exposes Incendiary, Booming, and Smoke choices and spends spell slots; the damage scaling, saves, nearby-creature damage, prone/deafened, and blinded riders are displayed as table-managed reference text and are not applied automatically. Bespoke effects such as extra damage riders, incense healing, initiative shifting, custom Sleep target resolution, and Innovator's Bolt area/condition resolution remain tabletop/reference-level unless a narrower structured hook covers them.

## Source Locking And Reimport

- Same-source resolution is required for durable non-PHB refs; do not silently downcast stale TCE/SCAG/XGE/EGW/DMG refs to same-title PHB rows.
- Preserve page-backed species/background/feat selections, campaign `character_option`, and `character_progression` overlays through native edit, level-up, and reimport.
- Reimports preserve stable ids, curated `page_ref` and `systems_ref` links, class-row order, custom display names, spell links, tracker identity, spent tracker state, safe native-managed overlays, and native-progression-managed source rows.
- Reimport precedence favors native progression over stale imports.
- Existing-target CLI `import` and `pdf-import` require both character YAML
  files and the SQLite state row. Complete targets use the durable update
  journal as `markdown_import` or `pdf_import`; partial targets, and targets
  that remain active or conflicted after recovery, fail closed for explicit
  repair without further mutation.
- Reimports preserve the exact SQLite revision, serialized state, update
  timestamp, and updating actor when reconciliation is unchanged, and advance
  the revision once when reconciliation changes state. Interrupted publication
  recovers forward only from exact prior or already-desired bytes; missing or
  third-party bytes remain retained conflicts and are neither reconstructed nor
  overwritten. Active reimports remain hidden and support recovery after
  restart or verified backup restore.

## Known Limits

- Unsupported base classes and unsupported spell-bearing subclass-only lanes stay blocked until progression and spell rules are modeled end to end.
- Additional senses, optional encumbrance thresholds, contextual passive-detection clauses, advanced attack/damage edge cases, broad boons/curses/training rewards, generic respec, and history rewrite remain deferred.

## Related Backlog

- `.local/roadmaps/character-backlog.md`

## Source Pointers

- `player_wiki/character_builder.py`
- `player_wiki/character_editor.py`
- `player_wiki/character_importer.py`
- `player_wiki/character_pdf_importer.py`
- `player_wiki/character_reconciliation.py`
- `player_wiki/character_update_apply.py`
- `player_wiki/character_update_preview_routes.py`
- `player_wiki/migrations.py`
- `player_wiki/character_markdown_exporter.py`
- `player_wiki/character_artificer_infusions.py`
- `player_wiki/character_presenter.py`
- `player_wiki/character_state_service.py`
- `player_wiki/managed_resource_registry.py`
- `player_wiki/character_source_matrix.py`
- `scripts/export_dnd_character_sheet.py`
