# Characters: Xianxia

Last updated: 2026-06-25

## Owns

- Xianxia character definition/state model, native create, manual existing-character import, read/session sheets, Cultivation, Realm Ascension, approval records, Xianxia inventory/currency, and current deferred automation boundaries.

## Current User-Facing Behavior

- Xianxia character detail subpages: `Quick Reference`, `Martial Arts`, `Techniques`, `Resources`, `Skills`, `Equipment`, `Inventory`, `Portrait`, `Personal`, `Notes`, and `Controls`.
- Xianxia omits DND-5E Spellcasting and Features routes.
- Session Character uses the same Xianxia read-sheet subpage slugs and labels except `Controls`, which remains on the full Character page.
- Quick Reference shows Defense, Realm action count, Effort damage, check formula, EASY/Normal/HARD reminders, Honor reminders, Skills guardrails, Stance Break when relevant, active Stance/Aura reminder cards, and linked rule-text references.
- Martial Arts shows linked arts, rank-progress ladders, learned rank-granted abilities, Systems links, and intentional incomplete-draft markers.
- Techniques shows known Generic Techniques, Basic Actions, approval status groups, optional prepared Dao Immolating notes, use-request forms, and approved-use recording when authorized.
- Resources shows current/max HP, Stance, Jing/Qi/Shen, Yin/Yang, Dao, Insight, and active Stance/Aura names.
- Equipment shows necessary weapons/tools, equipped inventory, and Defense breakdown. Equipped Armor is presentation-only and does not drive Defense yet.
- Inventory supports modeled Xianxia item rows plus Coin, Supply, and Spirit Stones.
- Portrait displays the current portrait and supports upload/remove for authorized users. Personal remains for physical description/background reference text.

## Current Data Contract

- Xianxia `definition.yaml` carries `system: Xianxia` and a top-level `xianxia` stable definition block.
- Stable fields include Realm, actions per turn, Honor/Reputation, Attributes, Efforts, Energy maxima, Yin/Yang maxima, Dao max, Insight balance, durability maxima, manual armor bonus, derived Defense, trained skills, necessary weapons/tools, Martial Arts, Generic Techniques, variants, Dao Immolating records, approval requests, companions, and advancement history.
- Xianxia mutable state lives in SQLite under a top-level `xianxia` state block.
- Mutable fields include current HP/temp HP, current Stance/temp Stance, Jing/Qi/Shen, Yin/Yang, current Dao, active Stance/Aura, Coin/Supply/Spirit Stones, modeled inventory rows, and player notes.
- Shared top-level HP/temp HP, inventory, and notes stay synchronized for existing state-store compatibility. DND currency and spell/resource state stay separate.

## Current Create And Import Contract

- Native Xianxia create dispatches through `player_wiki/system_policy.py` and `player_wiki/xianxia_character_builder.py`.
- Create validates six Attributes with exactly 6 total points and max 3 each, five Efforts with exactly 5 total points and max 3 each, Jing/Qi/Shen maxima with exactly 3 total points, exactly three trained skills, and a starting Martial Art package of either one Novice plus one Initiate or three Initiates.
- Starting Martial Arts come from enabled seeded shared and GM-created custom `martial_art` Systems rows. Custom-source Martial Arts are valid Initiate/Novice options even without seeded rank metadata.
- Create infers only necessary weapons/tools from Martial Art style metadata and known tool-bearing trained skills.
- Create defaults Realm to Mortal, actions to 2, Yin/Yang to 1/1, HP/Stance to 10/10, Insight to available 0/spent 0, current Dao to 0 unless explicitly granted, and Xianxia currency to 0.
- Generic Techniques default to none. Starting Generic Techniques are recorded only when a DM/GM explicitly selects enabled `generic_technique` Systems rows as GM grants.
- Manual existing-character import at `/campaigns/<slug>/characters/import/xianxia-manual` accepts loose copied values, previews before writing, writes normal Xianxia definition/state files, imports maxima rather than current/temp resource values, initializes current pools from maxima, initializes temp HP/Stance to 0, initializes current Dao to 0, and keeps Active Stance/Aura blank.

## Current Cultivation And Advancement Contract

- Cultivation is Xianxia-only at `/campaigns/<slug>/characters/<characterSlug>/cultivation`.
- DM/admin users can record Insight counter adjustments, Gathering Insight downtime gains, direct Cultivation Energy spends, Meditation Yin/Yang spends, Conditioning HP/Effort spends, Training Stance/Attribute spends, Martial Art rank spends, Generic Technique purchases, approved Dao Immolating use recording, Realm Ascension review/reset/rebuild, and final GM confirmation.
- Maximum-increase spend paths update definition-level maxima while preserving current mutable pools until rest or explicit state edit changes them.
- Martial Art rank spends preserve teacher/breakthrough requirements as non-blocking notes. Legendary rank requires all prior ranks plus a quest/mythic-master note.
- Generic Technique purchases use enabled Systems rows and do not require a Master.

## Realm Ascension

- Realm Ascension review starts by verifying the current Stat-max prerequisite and recording pending GM-review details while preserving current definition/state.
- Reset clears only stable Attributes and Efforts after pending review and records a pre-ascension stable-definition snapshot.
- Mortal-to-Immortal rebuild validates 15 Attribute/Effort points, max 6 per Stat, promotes Realm to Immortal, derives action count 3, supports legal HP/Stance trades, and records pre/post snapshots.
- Immortal-to-Divine rebuild validates 25 Attribute/Effort points, max 12 per Stat, promotes Realm to Divine, derives action count 4, supports legal HP/Stance trades, and records pre/post snapshots.
- Final GM confirmation requires a note, marks the rebuild confirmed, records `realm_ascension_gm_confirmation_recorded`, and blocks another Realm review while a rebuild remains unconfirmed.

## Approval Records

- Karmic Constraint and Ascendant Art records normalize through `xianxia.variants`.
- Dao Immolating use records normalize through `xianxia.dao_immolating_techniques.use_history`.
- These approval-gated record families force approval-required state, default to Pending, canonicalize common rejected aliases, and preserve approval notes/timestamps.
- Dao Immolating use records normalize a fixed 10 Insight cost and one-use marker. Approved unused records can be recorded as spent by DM/admin users.
- Prepared Dao Immolating records are optional preparation notes and can be attached as support to a use request; they are not prerequisites.

## Known Limits

- No DND Armor Class, DND attack, or DND spellcasting behavior applies to Xianxia.
- No automated attack/damage resolution, target effects, active-state switching enforcement, companion derivation, social check automation, skill-based combat bonuses, Spirit Stone consumption automation, armor-derived Defense from inventory, Dying Rounds, statuses, or combat automation exists yet.
- Full Karmic/Ascendant authoring and GM approval decision/enforcement forms remain deferred.

## Related Backlog

- `.local/roadmaps/character-backlog.md`
- `.local/xianxia-implementation-roadmap.md` remains historical/domain-specific until migrated.

## Source Pointers

- `player_wiki/system_policy.py`
- `player_wiki/xianxia_character_model.py`
- `player_wiki/xianxia_character_builder.py`
- `player_wiki/xianxia_character_importer.py`
- `player_wiki/xianxia_advancement.py`
- `player_wiki/xianxia_cultivation.py`
- `frontend/src/components/CharacterXianxiaSections.tsx`
- `frontend/src/components/CharacterCultivationRealmAscension.tsx`
