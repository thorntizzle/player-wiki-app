# Characters: DND-5E

Last updated: 2026-06-28

## Owns

- DND-5E native create, Advanced Editor, Level Up, Progression Repair, Retraining, PDF/markdown import convergence, read/session sheet behavior, spellcasting, equipment, Armor Class, attacks, and reimport precedence.

## Current User-Facing Behavior

- DND-5E character detail subpages: `Quick Reference` or Gen2 `Overview`, `Resources`, `Spellcasting` or Gen2 `Spells`, `Equipment`, `Inventory`, `Abilities and Skills`, `Personal`, `Portrait`, `Notes`, and `Controls`.
- Quick Reference or Gen2 Overview shows core overview rows, editable HP/temp HP/Hit Dice for authorized users, tracked resources, carrying capacity when derivable, and defensive rules when modeled. On the normal Gen2 sheet, the vitals/rest editor appears only on Overview rather than repeating across every subpage.
- Combat reminders from `stats.attack_reminder_state` belong on combat-facing attack panels, not normal Character Quick Reference.
- Spellcasting is the durable home for spell-list management. Prepared casters and wizards use local `Current spells` and `Preparation` subviews over the same durable rows.
- Equipment is the durable home for equip/unequip, attunement, weapon wield mode, supported feature-state toggles such as Armorer Arcane Armor, and Artificer infusion activation.
- Inventory is the durable home for carried item rows, supplemental item adds, supported removals, quantity controls, and DND currency.
- Resources shows tracked current/max resource cards. Authorized editors can change each current value through the existing resource state path with both blur autosave and a visible per-card `Save` action.
- Spell detail popups in Gen2 include resolved upcasting text (e.g., `At Higher Levels`) when source-backed spell payload includes it; non-upcastable spells do not show an empty upcast section.
- Personal displays physical description/background reference text. Physical description/background authoring belongs in Advanced Editor.
- Notes displays player notes and imported/reference note sections. Editable users can save or confirmed-delete the mutable player note through the shared revision-checked notes path.
- Portrait displays a large unframed current portrait and supports one portrait slot with upload/remove for authorized users. PNG/JPG uploads are stored as WebP; GIF/WebP uploads pass through validation.
- Controls covers owner status, app-admin assignment/clear, and DM/admin checked deletion.

## Current Authoring And Support Matrix

- Native DND-5E create, edit, level-up, progression repair, and retraining are DND-5E-only.
- Native base-class boundary is explicit: PHB base classes plus the TCE Artificer lane.
- The TypeScript create parity path currently has bounded level-one PHB Fighter, PHB Barbarian, PHB Bard, PHB Cleric/Life Domain, PHB Druid, PHB Rogue, PHB Ranger, PHB Monk, PHB Paladin, PHB Sorcerer/Draconic Bloodline, PHB Warlock/Fiend, and PHB Wizard slices; full DND builder parity remains pending.
- Supported subordinate non-PHB rows include current accepted SCAG, XGE, EGW, and DMG rows when attached to supported base classes.
- Native level-up is one level at a time through level 20 and can advance an existing class row or add a class row when the support matrix allows it.
- The TypeScript level-up parity path currently supports bounded TypeScript-created PHB Fighter, PHB Barbarian, PHB Rogue, PHB Ranger, PHB Monk, and PHB Paladin level-one to level-two saves; the Barbarian slice adds Reckless Attack and Danger Sense, the Rogue slice adds Cunning Action, the Ranger slice adds deferred-choice Fighting Style, Spellcasting, two first-level known-spell choices, and first-level Ranger spell slots, the Monk slice adds Ki, Unarmored Movement, a 2-point Ki resource, and the level-2 speed increase, and the Paladin slice adds deferred-choice Fighting Style, Spellcasting, Divine Smite, first-level Paladin spell slots, and Lay on Hands scaling with HP/Hit Dice/resource reconciliation, copied definition/import YAML writes, SQLite revision bumps, and native progression history.
- Progression repair resolves ambiguous imported class/subclass/species/background links and converts legacy imported spell marks to durable spell flags.
- Retraining is intentionally narrow: it supports persisted structured choices on existing linked custom features, not generic rebuilds or full respec.

## Current Data/API Contract

- Save-time derivation is the authority for computed DND-5E sheet math on supported write paths.
- Shared derivation covers proficiency, saves, skills, passive checks, initiative, speed, carrying capacity, max HP when provenance exists, spell DC/attack, slot progression, Armor Class, attacks, and resource templates.
- DND mutable state includes HP/temp HP, per-die-size Hit Dice pools, resources, spell-slot usage by slot lane, equipment state, inventory quantity, currency, notes, and feature states such as Arcane Armor.
- Hit Dice max pools derive from class-row levels and hit-die metadata; current counts stay in SQLite. Long rests restore expended Hit Dice equal to half total character level, capped by pool maximum, and do not auto-heal HP. Gen2 rest confirmation fields let the user set final Current HP and current Hit Dice after the modeled rest recovery before applying the rest.
- State reconciliation treats unlabeled legacy spell-slot rows as migration-only once tracked slot lanes exist.
- Artificer active infusion state lives on targeted equipment rows as normalized `active_infusions`. Known infusions derive from modeled Artificer Infusions feature rows and known-infusion summaries, while active capacity derives from Artificer level.

## Current Spellcasting Contract

- Shared-slot multiclass spellcasting is limited to supported `full`, `1/2`, `artificer`, and currently supported `1/3` subclass-only lanes.
- The TypeScript create parity path now has a bounded PHB Sorcerer/Draconic Bloodline level-one slice with known spells, first-level slots, Charisma spell DC/attack, Draconic language, and Draconic Resilience HP/AC; broader Sorcerous Origin choices, ancestry choices, Sorcery Points, Metamagic, and Sorcerer progression remain outside full builder parity.
- Warlock Pact Magic remains a separate lane from shared-slot full-caster math. The TypeScript create parity path now has a bounded PHB Warlock/Fiend level-one slice with a distinct Pact Magic slot lane, but broader Warlock progression, invocations, pact boons, and multiclass Pact Magic remain outside full builder parity.
- PHB Paladin level-one TypeScript create parity is intentionally non-spellcasting: it writes Divine Sense and Lay on Hands tracked resources, bounded proficiencies/skills, starter equipment/attacks, and initialized mutable state. The bounded TypeScript level-one to level-two save slice adds deferred-choice Fighting Style, Spellcasting with Charisma DC/attack and two first-level slots, Divine Smite, and Lay on Hands maximum scaling; prepared-spell choice UI, Sacred Oath, level 3+ Paladin progression, and broad Fighting Style UI remain pending.
- PHB Monk level-one TypeScript create parity is intentionally non-spellcasting and pre-Ki: it writes Unarmored Defense, Martial Arts, bounded Acrobatics/Insight skills, deterministic Calligrapher's supplies proficiency, shortsword/darts/explorer's pack starter equipment, unarmed/shortsword/dart attacks, and initialized mutable state. The bounded TypeScript level-one to level-two save slice adds Ki, Unarmored Movement, the 2-point Ki resource, and the level-2 speed increase; Monastic Tradition, level 3+ Monk progression, and broad choice UI remain pending.
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
- Approved campaign-owned Systems `item` mechanics now use the same item metadata paths as shared DND item rows for supported weapons, armor, attunement, spell grants, resource modifiers, defensive rules, and attack reminders.
- Campaign item rows with `draft`, `manual_review`, or `reference_only` mechanics review status are visible as Systems entries but do not drive attacks, Armor Class, spell grants, or resource math. Published item page fallback remains available only where no structured item record is linked or the mechanic is still intentionally manual.
- The first structured Linden Pass item records cover Consecrated Huran Blade, Censer of Last Light, Hourglass Pendant, Staff of the Crescent Moon, Psionic Circlet, and Innovator's Bolt. Supported fields can automate after approval; bespoke effects such as extra damage riders, incense healing, initiative shifting, custom Sleep riders, and enchanted bullet effects remain flagged for implementation/manual handling.

## Source Locking And Reimport

- Same-source resolution is required for durable non-PHB refs; do not silently downcast stale TCE/SCAG/XGE/EGW/DMG refs to same-title PHB rows.
- Preserve page-backed species/background/feat selections, campaign `character_option`, and `character_progression` overlays through native edit, level-up, and reimport.
- Reimports preserve stable ids, curated `page_ref` and `systems_ref` links, class-row order, custom display names, spell links, tracker identity, spent tracker state, safe native-managed overlays, and native-progression-managed source rows.
- Reimport precedence favors native progression over stale imports.

## Known Limits

- Unsupported base classes and unsupported spell-bearing subclass-only lanes stay blocked until progression and spell rules are modeled end to end.
- Additional senses, optional encumbrance thresholds, contextual passive-detection clauses, advanced attack/damage edge cases, broad boons/curses/training rewards, generic respec, and history rewrite remain deferred.

## Related Backlog

- `.local/roadmaps/character-backlog.md`

## Source Pointers

- `player_wiki/character_builder.py`
- `player_wiki/character_editor.py`
- `player_wiki/character_artificer_infusions.py`
- `player_wiki/character_presenter.py`
- `player_wiki/character_state_service.py`
- `player_wiki/managed_resource_registry.py`
- `player_wiki/character_source_matrix.py`
- `frontend/src/components/CharacterDndSections.tsx`
