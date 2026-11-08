# Characters: DND-5E

Last updated: 2026-11-04

## Owns

- DND-5E native create, Advanced Editor, Level Up, Progression Repair, Retraining, PDF/markdown import convergence, read/session sheet behavior, spellcasting, equipment, Armor Class, attacks, and reimport precedence.

## Current User-Facing Behavior

Selected Systems backgrounds project their unique current narrative features
into the shared Sheet, Session, Combat and markdown presentation. A missing
stored companion does not require adding a feature to the character: the
projection remains separate from raw definitions, update-safe API payloads,
normalization and save inputs. An exact inert companion of that same selected
parent and facet shares the projection; historical copied prose is retained
but does not decide current rules. Missing, disabled, conflicting or ambiguous
current facets remain visibly unavailable.

Native reconstruction offers explicit parent-facet associations for inert
historical class/species summaries. Supported facets are class Hit Points and
Proficiencies, and species Languages, Ability Score Increase, Skills and Feat.
Each choice identifies the exact retained feature payload, selected parent
(including class-row identity), and supported current source facet. Unresolved
is a supported choice and retains the source warning. The original rows, IDs
and prose remain unchanged; typed associations reside in reconstruction source
provenance. The review shows the association and current rule, and an applied
association requires reserved source validation plus independently recovered
audit/prior/published-generation custody on ordinary reads. Copied source YAML
alone never supplies that custody. Reconstructing again cannot silently discard
an existing association.

These summaries grant no additional HP, abilities, proficiencies, feats, spells
or resources; their selected parent remains the sole mechanical owner. Duplicate
parent/facet associations and operative or ambiguously owned rows refuse.
Current source wording is rendered at read time. Structured class Hit Die and
proficiency metadata and species ability metadata supply their corresponding
rules; supported species narrative clauses retain their precise source location.
Unmodeled source shapes remain warnings. This support does not itself apply a
reconstruction, change play state or migrate existing characters.

Spell-slot availability is derived from source-backed pools. Class progression
continues to own its ordinary slots; feature/item contributions retain their
source, owner, capacity, used count and lifecycle separately. Combined totals
never select a source to spend. Unsupported or unqualified contributions remain
retained and read-only, with unknown combined totals where applicable.
Pool identity conflicts apply across the entire pool, including different slot
levels and retained unqualified base-slot observations. The shared qualification
refuses creation before charging points and preserves conflicting capacity on
rest; status, controls, preview and durable validation use the same decision.

Source references retain the canonical Systems library identifier `DND-5E`;
the lowercase entry-key prefix is a separate lookup representation. Class,
child-feature and reference validation use the same exact library contract.

In activated committed-source mode, the current PHB2014 Sorcerer Font of Magic,
Sorcery Points and deterministically attained Flexible Casting sources qualify
bonus-action exchanges. Creating a level 1–5 slot costs 2/3/5/6/7 Sorcery Points;
converting a selected available slot gains its level in points without exceeding
the qualified point maximum. Creation increases both current availability and
effective maximum at that level, independently of class slot capacity. Spending
reduces availability only. Long rest removes the entire qualified temporary
capacity, including spent created slots, and restores ordinary class slots
through their existing recovery path. Spell-specific free casts are not slots.

Character/Session and Combat controls, the JSON payload and modeled item-action
slot choices use the same contribution reader. Granted slots are spent through
an explicit source selection; ordinary usage editing cannot refill them. Atomic
exchanges and temporary-slot spending use the existing authenticated state
transaction, source reservation, revision check and action audit. Normal edit,
advancement and publication preserve the contribution state exactly. The
optional `spell_slot_grants` JSON state vector requires no SQL schema migration;
current source qualification and guarded state transitions own its authority,
without a second per-creation receipt ledger. Only Flexible Casting supplies
additional slots currently; future providers need their own qualified source and
lifecycle contract.

- DND-5E character detail subpages: `Quick Reference`, `Resources`, `Spellcasting`, `Equipment`, `Inventory`, `Abilities and Skills`, `Personal`, `Portrait`, `Notes`, and `Controls`.
- Quick Reference shows core overview rows, HP/temp HP/Hit Dice controls where the target is authorized and, in activated committed-source mode, its numeric owner is verified, tracked resources, carrying capacity when derivable, and defensive rules when modeled. Unverified historical numeric values remain labeled table references; the existing Character and Session forms can still suppress controls for UNKNOWN owners in never-activated mode.
- Combat reminders from `stats.attack_reminder_state` belong on combat-facing attack panels, not normal Character Quick Reference.
- Spellcasting is the durable home for spell-list management. Prepared casters and wizards use local `Current spells` and `Preparation` subviews over the same durable rows.
- Equipment is the durable home for equip/unequip, attunement, weapon wield mode, supported feature-state toggles such as Armorer Arcane Armor, and Artificer infusion activation. Bespoke stateful character boons remain in their owning feature section.
- Equipment activation uses one shared marker/row classifier. An absent legacy marker keeps its existing read policy; a valid exact-integer v1 marker quarantines bad rows individually; a present invalid marker supplies no positive activation, including capability, action and effective API flags. Raw evidence remains unchanged. Repair preservation/remapping/seeding validates original values before conversion, and publication independently replays the closed repair intent against the current raw record.
- Raw equipment-update inputs are validated before construction in both committed and legacy modes. Committed definition-ID repair is an exact ID-only disposition, requiring a complete valid resulting equipment graph and unchanged source declarations, import bytes and intended play state. Affected native item custody or state-ledger links remain unsupported unless their own domain protocol can reconcile them; identity repair does not renew receipts or infer old ambiguous mechanics.
- Identity-repair custody exclusions cover the original physical/catalogue identifiers and the chosen destination. A destination unused by ordinary inventory rows can still collide with an orphan live storage/prepared ledger or another retained semantic owner; it cannot adopt that custody by renaming.
- Inventory is the durable home for carried item rows, supplemental item adds, supported removals, quantity controls, and DND currency.
- Resources shows tracked current/max resource cards. In activated committed-source mode, authorized editors can change a verified tracker through the existing resource state path with both blur autosave and a visible per-card `Save` action; an unverified owner/reset is read-only and labeled `NEEDS REPAIR`. Never-activated state writes retain saved-number and revision/CAS behavior, although the existing Character and Session forms can still suppress UNKNOWN-owner controls.
- Spell detail popups include resolved upcasting text (e.g., `At Higher Levels`) when source-backed spell payload includes it; non-upcastable spells do not show an empty upcast section.
- Personal displays physical description/background reference text. Physical description/background authoring belongs in Advanced Editor.
- Notes displays player notes and imported/reference note sections. Editable users can save or confirmed-delete the mutable player note through the shared revision-checked notes path.
- Portrait displays a large unframed current portrait and supports one portrait slot with upload/remove for authorized users. PNG/JPG uploads are stored as WebP; GIF/WebP uploads pass through validation.
- Controls covers owner status, app-admin assignment/clear, and DM/admin checked deletion.

## Qualified Feature Replacement And Resource Admission

- The shared composition contract recognizes the finite registered Wild Die
  replacement only from an eligible current source, exact Sorcerer/Wild owner
  and attained PHB rule. It suppresses only Wild Magic Surge and carries Tides
  of Chaos and Bend Luck forward. A retained replacement claim preserves intent
  through source unavailability; malformed or conflicting data never enables
  the old feature or grants the replacement. Ordinary edits preserve that claim;
  an explicit reviewed Source Repair relink can change it.
- Effective suppression is recomputed. Authoring retains the original rows,
  order, descriptions and source history. Grants, numeric dependency closure,
  managed trackers and legacy named-feature selectors consume the same bounded
  composition. An arbitrary feature title cannot add unrelated feat mechanics.
- Activated continuation derivation retains an unchanged, qualified historical
  replacement target rather than adding a plain deterministic occurrence of
  the same attained source for the same owner. Current source publications,
  owner identity and the deterministic acquisition slot must agree. Multiple
  aliases, distinct acquisitions, extra observations and conflicting owners
  still reach the strict composition checks; historical rows are not merged.
- Ordinary item Source Repair prepares the publisher's exact item-transition
  definition and state before Review seals their digests. This includes charge
  clearing markers and affected aggregate normalization. Ordinary and reserved
  publication still qualify the current owners, recheck the sealed frame and
  independently recompute normalization; no candidate-digest drift is admitted.
  Shared preparation preserves original numeric-domain errors in every refresh
  context. Only the phase-owning publisher may mark a refusal as certainly
  prepublication; reserved failures retain conservative inspection handling.
- In activated committed-source presentation, a qualified intentionally replaced
  feature displays `Replaced`, with `This feature has been replaced.` as its
  unavailable combat-action reason. Character, Session and Combat presentation
  retain its historical description and suppress its mechanics, links and
  trackers. Unqualified or unresolved suppression keeps the source-repair wording;
  losing replacement qualification does not reactivate the old feature.
- Wild Die capacity derives as floor(total character level / 2), with a valid
  zero at level 1; the die is d6 and recovery is long rest. Tides capacity derives
  as one from its attained PHB source. This models capacity/ownership, not an
  automatic roll procedure, Wild-table consequence, or extra Tides recharge.
- Native requalification schema 6 adds a finite current-source admission for
  previously unwitnessed Tides/Wild trackers alongside the complete current
  spell checkpoint. Existing claims must retain their authenticated origins;
  an invalid old claim cannot use the new lane. Prior template/state/seed,
  exact source owner and versioned recipe are sealed under the reviewed actor,
  generation and state. Only missing owner annotations and source-derived
  template metadata may change; current counts and seed absence/None persist.
- Saved custody is verified against its authenticated original/candidate
  generations and historical recipe. Current source eligibility is checked
  separately per target, so a later rule change withholds affected mechanics
  without discarding unrelated saved spell choices. Review, reserved execution,
  publication/audit, strict loaders and ordinary continuation share the contract.
  Older receipt schema predicates and normal token/session lifetimes remain.
- Exact-state compatibility recognizes a missing resource class owner only when
  it matches one issuer-bound current-admission annotation and its complete
  original/candidate templates. Native Review uses the authenticated producer
  result; ordinary and reserved publication use the complete pending native
  proof containing that result. Copied provenance, another actor or candidate,
  or an unrelated owner change grants no permission. Existing reconstruction
  proof handling stays separate, and reset policies, retained seeds and complete
  play state remain protected by their existing checks.
- This code slice has no character adoption or runtime proof by itself.
  Glenn's current-choice adoption, equipment/Staff/AC closure, resource controls,
  languages and full action/edit/advancement qualification remain explicit work.

## Effective Spell Attack And Save Labels

- Activated DND spell views derive attack/save labels from exact current Systems
  spell rules and each independently qualified casting row's effective metrics,
  after current item and temporary modifiers. The shared mechanics projection
  carries separate display facts; saved definitions, historical `save_or_hit`,
  numeric witnesses, grant/choice/capacity custody and play state are unchanged.
- Character/API, Session/combat presenter views and the spell manager consume
  the same display map. Legacy never-activated and Xianxia paths retain their
  existing behavior. A unique spell identity, publication and casting owner are
  required; class/source ID collisions, retired/unproved ordinary choices,
  missing native casting options and unqualified individual metrics fail closed.
  Item and original-caster sources never borrow a sole class or its item bonuses.
- The bounded compatibility interpreter recognizes explicit named saving-throw
  instructions and caster spell-attack instructions in supported canonical
  narrative containers. Tables, statblocks, unsupported/overflowed containers,
  ambiguous clauses, fixed/foreign metrics and contradictions remain UNKNOWN.
  Missing declarations or prose matches never supply an imported numeric total
  or prove that an arbitrary source has no roll. Future spell imports retain
  present `savingThrow` and `spellAttack` declarations exactly, including empty
  or malformed values, and do not invent missing fields. Existing libraries are
  not rewritten by reads or by this code change.
- Unknown display facts are labeled unavailable and keep casting permission
  separate. Positive labels use only already-qualified integer owner metrics;
  distinct qualified casting options stay distinct. This source contract does
  not establish a saved-sheet observation, item action or full character baseline.

## Current Authoring And Support Matrix

- Native DND-5E create, edit, level-up, progression repair, and retraining are DND-5E-only.
- Native base-class boundary is explicit: PHB base classes plus the TCE Artificer lane.
- Supported subordinate non-PHB rows include current accepted SCAG, XGE, EGW, and DMG rows when attached to supported base classes.
- Native level-up is one level at a time through level 20 and can advance an existing class row or add a class row when the support matrix allows it.
- Native advancement projects the selected ability increase, proficiency bonus, attacks, HP and managed resources together for preview and save. Legal validated ability-base and level-derived proficiency transitions renew their existing current-source ownership through the normal pending proof and confirmed audit; copied numeric markers remain insufficient.
- Advancement preview and its strict producer derive equipment effects from the same SQLite activation state. Durable updates retain unchanged physical source rows and existing resource bootstrap observations; deriving an equipped item bonus does not rewrite those rows, increase the bootstrap count or restore current uses.
- Prospective ability minima default to zero for each unspecified ability, preserving scores below 10 and explicit zero. Recognized native or currently qualified skill choices, including `none`, take precedence over bonus inference during recalculation. Qualified feature grants still apply afterwards; missing or invalid legacy labels retain numeric recovery behavior.
- The selected class/subclass spine includes exact unconditional source grants through attained levels. Bundled direct references without a choice count are grants only when their complete identity resolves unambiguously within that selected source; genuine choices stay explicit. Managed family members deduplicate by source, class row and member while preserving saved feature/tracker identities. Conflicting owners are refused.
- Tracker-member matching is separate from generic source/acquisition identity. Qualified registry members sharing a parent publication retain separate trackers; generated children reuse a unique existing member without replacing its feature ID, exact reference, acquisition or tracker. Continuation preparation retains all real owners for source qualification instead of adding a redundant synthetic child. Proved aliases still require the source-authority pool contract; conflicting members or tracker owners refuse, and class rows remain distinct.
- Reconstructed passive members with an exact attained source may use a unique verified class owner temporarily for generated-child matching. Source authority binds the original feature and class frames and restores the saved citation and class association afterward. This grants neither a resource pool nor a new acquisition. A generated Recovery action remains a member of its parent Psionic Power family with a separate use tracker; it is not an independent feature selection.
- Saved resource `notes` remain retained text and need not equal current derived descriptions during native validation or resource-recipe qualification. Every mechanical, source, owner and observation check remains in force, and proof recipes still bind their current derived content. Qualified shared read projections display current managed-resource notes without rewriting saved text, counters or reset behavior; unqualified and manual resources retain their existing handling.
- If advancement restores a previously omitted historical managed resource, its current count must be entered explicitly between zero and the proved maximum. Existing counts are preserved; growing a maximum never refills a pool. Psionic Energy uses twice total-character proficiency bonus, with its die size based on Fighter level; Recovery, Telekinetic Movement and attained Psi-Powered Leap retain separate free-use trackers.
- Native create and level-up preserve text, ability inputs and HP-gain inputs across full-page refresh and validation/error rendering. In committed-source mode, a Systems background's narrative feature must match the selected background and its current extracted text; that companion link grants no independent mechanics.
- Supported background musical-instrument choices use exact enabled `INS` item references and persist their background owner in `profile.background_choices`. Native create, Advanced Editor, reopen and advancement preserve the selection. Existing characters can add a missing choice through Advanced Editor without replaying starting equipment. Instrument proficiency and carrying the instrument are separate. Other open tool families such as gaming sets and artisan tools retain their existing coverage limits.
- Reconstruction uses that same typed background-instrument contract to explicitly bind an already retained tool proficiency. It preserves an existing typed choice, requires complete current source selections, and grants no inventory. Current instrument references and source content participate in reconstructed tool authority; missing, disabled, changed or mismatched choices refuse qualification. The catalog must already contain the background's structured instrument grant; reconstruction does not repair missing Systems data.
- Committed-source updates retain the exact existing advancement-history prefix as inert history, including references predating progression repair. New history class/subclass references must match their unique current class row; a new subclass reference also proves its actual Systems parent class/source, including an otherwise unchanged parent link. Creation has no retained-history exception. Historical references do not grant current mechanics, and source/currentness/CAS checks still apply under publication lock.
- Progression repair resolves ambiguous imported class/subclass/species/background links and converts legacy imported spell marks to durable spell flags.
- Retraining is intentionally narrow: it supports persisted structured choices on existing linked custom features, not generic rebuilds or full respec.

## Authoritative Ability Inputs And Conditional Recovery

- `stats.ability_inputs` is version 1 with per-ability `base`, `pre_penalty`,
  or `unresolved` records. It preserves authoritative inputs, fixed bonuses,
  applied bonus/minimum layers, and provenance separately from effective
  `stats.ability_scores`. Native creation and fresh import seed explicit inputs;
  advancement updates inputs rather than treating displayed output as an edit.
  Explicit zero is a score. Capped bonuses, minima, and penalties are applied
  from those inputs so repeated normalization and penalty recovery do not
  compound prior output or invent an inverse through saturation.
- Legacy inverse recovery is used only when unambiguous. A zero hidden by a
  recoverable penalty, a score at/below a modeled minimum after adding back
  penalties, or bonus saturation at 20 can require confirmation; a negative
  inferred base is unresolved too. Full normalization retains unresolved
  effective scores. A profile-only scope that omits item layers preserves
  recorded values/provenance rather than completing an incomplete inverse.
- Advanced Edit conditionally exposes `Recover original ability scores` for
  unresolved inputs (or missing inputs with a penalty-hidden zero). Each
  requested `recover_ability_<key>` must be an ASCII whole number of zero or
  more, at the indicated stage: before bonuses/minima (`base`) when those layers
  hid the value, otherwise before recoverable penalties (`pre_penalty`). The
  authorized editor's submission confirms the input and records that
  provenance. Missing/invalid confirmations refuse the dependent save before
  persistence; resolved sheets receive no recovery prompt. Edit normalizes
  legacy provenance before removing old feature/penalty metadata, recovers
  requested inputs, then requires resolution before recalculation.
- Level Up, Progression Repair, Retraining, guided updates, and other supported
  definition-recalculating writes require resolved inputs before persistence.
  A complete raw content API update that changes mechanics checks previous
  unresolved abilities for supplied resolved input records before finalization;
  it retains its non-deriving file-storage contract. This is a conditional
  ability-input refusal, not a blanket ban on legacy characters. Independent
  reads and SQLite-only state edits remain available subject to existing access,
  revision, and reconciliation protection. Portrait/profile-only preparation
  preserves stats, deep-copies the definition and fills missing equipment links
  without mechanics normalization, retaining normal journal/CAS publication.

## Current Guided Character Update Contract

- Existing supported single-class DND-5E characters have a manager reconstruction mode on this same surface after committed-source admission and activation. An unactivated installation refuses with explanatory guidance before character changes. The mode records an existing-target origin; it does not create a replacement character or replay earlier level-ups.
- App admins and campaign DMs can open the manager-only `/campaigns/<campaign-slug>/characters/<character-slug>/update-preview` route for DND-5E characters. They can compose exact source-backed campaign feature or equipment grants, approved items from enabled Systems sources, and safe relinks from one unlinked equipment row to one exact source.
- Assigned-player access to the Advanced Editor does not grant this manager workflow, and observers cannot use it. An app admin using View As can inspect a visibly read-only GET surface, while the global authorization boundary blocks POST.
- The compose, review, and apply flow is server-rendered and works without JavaScript. It accepts only bounded operation choices and quantities; caller-supplied replacement definition, state, YAML, JSON, digest, or other unknown fields are rejected. Apply accepts only the reviewed token plus its intent and CSRF fields.
- Review is a pure, zero-write preview. Ordinary grant operations expose sanitized operation status, state-impact and diagnostic summaries plus features, equipment/inventory, spells, attacks, Armor Class and resources. Reconstruction additionally exposes build and play-state consequences: original-input evidence, permanent/source owners, exact HP contribution policy, explicit mappings, unresolved choices and retained manual clauses. Blocked work receives no Apply token. Responses carrying manager diagnostics or review tokens use private/no-store and no-referrer headers.
- Each Character Update catalog enumeration reuses its loaded campaign and captured effective actor/campaign visibility while retaining the base Systems entry, enablement, override, source and approval checks. With committed source authority, item access does not reload the repository per item. Reconstruction uses the campaign freshly loaded for its proof and rechecks committed source/admission identities, Systems revision, visibility and actor privileges after exact Character evidence and before signing Review. Drift or an old read transaction refuses the token; unrelated session inserts do not invalidate the source basis. Apply retains fresh recomputation and publication checks. This establishes source behavior, not a measured runtime guarantee.
- A `READY` review issues a canonical HMAC-SHA256 `cu1` token that expires after ten minutes. The bounded token is actor-, campaign-, and character-bound and attests the normalized operations; exact definition/import bytes and SQLite state tuple; source, policy, and prepared-native foundations; planner version and state impact; and candidate and semantic digests. It carries no replacement source bodies, file paths, secrets, CSRF data, or audit payload.
- Apply reauthorizes the manager, rejects incomplete or recovery-protected targets, reloads without initializing missing state, and recomputes the accepted operations exactly once from authoritative inputs. Any token, actor, target, operation, definition/import, state revision/serialized bytes/timestamp/updater, source, policy, native foundation, planner, candidate, or semantic drift returns `refused_stale` before publication. A reviewed no-op remains `unchanged` with no coordinator call, write, or audit.
- A changed accepted plan crosses the publication boundary once through `CharacterPublicationCoordinator`. `preserve_exact` keeps the entire SQLite state tuple unchanged. `reconcile_required` can only append the reviewed new resource or inventory rows, cannot change existing or opaque state, and advances the state revision once.
- A known activation prerequisite refused before publication returns an explicit prerequisite refusal with no business changes. Anticipated numeric-projection or HP-recipe failures detected before publication reservation return `failed`; failures after reservation or during readback retain the conservative uncertain classification. Generic exceptions do not prove a zero-write failure, and an uncertain receipt does not assert which publication phase was reached.
- Definition, import metadata, and allowed state are treated as one journal-backed character publication. The initial `BEGIN IMMEDIATE` transaction records the desired state and private recovery row before the exact `definition.yaml` and `import.yaml` bytes are published forward. Active `prepared`, `repository_pending`, or `conflict` rows hide and protect the character; ordinary-request recovery accepts exact prior or already-desired evidence, completes forward, and deletes the row after authoritative refresh. Third-party or missing evidence becomes a retained conflict rather than a rollback or overwrite. This provides forward completion across SQLite and campaign files, not a cross-store atomic transaction.
- Apply records one `character_update_applied` audit with sanitized metadata, including planner/candidate/review identities, state impact, and operation count. The audit is inserted in the same transaction that advances the journal to `repository_pending`, so recovery cannot duplicate it. If the actor account is later deleted, the retained journal truthfully nulls that foreign-key actor reference while preserving event type and metadata; prepared recovery may then write the one null-actor audit, repository-pending recovery writes none, and a retained conflict manufactures no audit.
- Authoritative readback compares definition, unchanged import metadata, exact or reconciled state, the single audit, and the reviewed semantic projection. Results are `confirmed_applied`, `unchanged`, `refused_stale`, `refused_prerequisite` for incompatible activation detected before publication, `failed` for another proven pre-publication zero-write failure, or `uncertain` after a publication-boundary/readback ambiguity. An `uncertain` result explicitly forbids blind retry and directs the manager to inspect current state first.
- The accepted 5B presentation is integrated on `main`: product commit `d1420896ef11e8c41ea66c6814b81542725e1427` and documentation commit `d3abe2fe2f2c90fb96786d3f1a316c83ba0f1ecc` are ancestors of the accepted `161db863694057be31da0d3ff1ee627216269a29` integration checkpoint. This establishes accepted source and integration, not deployment or ordinary-use evidence; the [recorded deployment boundary](ops-deploy.md#current-fly-deployment-shape) remains separate. It keeps the same route and 5A apply contract: no endpoint, persistence, session receipt, schema/migration, API/CLI, or player-facing surface was added, and the existing manager authorization, assigned-player denial, View As GET-only behavior, CSRF fields, private no-store responses, campaign isolation, apply-once semantics, and readback classifications remain unchanged.
- In that accepted local candidate, a `READY` review becomes a one-shot confirmation naming the Character, reviewed operation count, and plain-language state effect. Its primary action is `Confirm and apply update once`, followed by `Back to edit` and `Cancel and return`; apply still submits only CSRF, `intent=apply`, and the reviewed token. A `NO_OP` review immediately returns a `No changes needed` receipt without issuing a token or calling the coordinator, writing data, or recording an audit.
- The local receipts map the six engine results honestly: `Update confirmed`/200, `No changes needed`/200, `Review no longer current`/409, `Equipment activation needs repair`/409, `Update not applied`/500, and `Outcome not confirmed`/503. They expose only the Character display name, captured reviewed-operation count, plain-language state handling, the captured sanitized six-category semantic scope, and canonical links to inspect the Character or return to the roster. Tokens, digests, internal classifications, identifiers, revisions, timestamps, audit/journal data, paths, YAML/JSON, source bodies, and secrets are not rendered.
- An unconfirmed receipt labels the semantic material as reviewed scope rather than current truth, warns against refreshing, resubmitting, or preparing a new review before inspection, and offers no retry/apply/fresh-preview action. The confirmation and all receipts are server-rendered and work with JavaScript disabled or enabled. The accepted browser contract preserves one shared-shell `main` landmark, labelled static sections, visible keyboard focus, first-error focus after the loading curtain clears, correct heading order, mobile one-column actions, and no horizontal overflow at `1280x900` and `390x800`.

## Existing-Character Native Foundation Contract

Recording a completed advancement retains its original typed import fields, warnings and exact committed import sidecar bytes, plus existing definition.source import provenance. The strict private advancement intent binds semantic import identity; the committed publisher checks the current raw preimage again under reservation. Ordinary new advancement retains its existing import-metadata behavior.

- The optional private `character_source_repair_failure_observer` receives the original exception for known source-repair conflicts as well as unexpected failures, including its existing cause chain. The caller owns bounded, nonsecret capture. An absent observer or an observer failure changes no validation, conflict status, outcome, cleanup or response; these diagnostics supply no grant custody or publication authority.

- Native requalification resolves external Systems, policy, configuration and page facts through a detached read view bound to the application's exact connection and one explicit SQLite snapshot. Repeated source interpretation within that phase reuses immutable facts and returns detached values. Model, occurrence, entitlement, original-versus-desired authority and pending-proof checks remain separate; the existing eight Review authority builds and producer callbacks are retained. HTTP/request caches and builder caches do not establish snapshot ownership.
- Each completed native read phase discards its caches and freshly repeats its complete captured source readset, including absent values and ordered results, alongside activation, configuration, pages, character generation/state and audit observations. This comparison detects relevant drift even without a revision-token advance. A later phase reads its facts afresh; prior observations serve only as comparison material. Positive producer binding, completed pending proof, signed Review and publication readiness retain their fresh boundary checks and original digest formats.
- Native preflight owns and ends its read transactions, refuses unknown ambient transactions and closes before publication reservation. Only the publisher supplies its fresh reserved owner after `BEGIN IMMEDIATE`; nested read consumers join that explicit phase rather than acquiring a new transaction. The reserved view cannot perform any DML, end the publisher's transaction or survive the first publication write. Durable readback and reopen use fresh existing reads. Missing libraries can choose the existing initialization path only before an unreserved consumer starts; missing libraries under reservation refuse. No source phase seeds or repairs data.
- A failed owned-read rollback quarantines the exact application connection. Further `get_db` access refuses until application teardown disposes it; fatal responses avoid DB-dependent templates. Cleanup attempts its independently owned resources and retains primary and cleanup failures. These source contracts establish no measured speedup, successful correction, expiry fit or deployment. The normal 600-second Review token, 90-minute temporary session and bounded audit contracts remain unchanged.
- Native publication uses the same guarded rollback containment during reservation acquisition/admission and the reserved body. Unknown ambient transactions refuse before reservation effects. A BEGIN dispatch that raises after taking effect still receives owned cleanup; failed rollback or a rollback that leaves a transaction open quarantines the exact application handle and preserves both failures. Outer cleanup checks the fatal latch before touching the handle, so it cannot retry a known failed rollback. A pre-BEGIN setup refusal does not assert an acquired transaction. Ordinary shared reservation callers retain their existing default contract.
- Native requalification checks typed equipment identity and activation readiness before derivation and again on the complete desired state before signed Review. An authenticated native correction or renewal can retain an absent legacy activation marker only with unchanged complete physical owners and an unchanged complete state frame. Present malformed markers, ambiguous identifiers, coercible flags and unsupported modes refuse; no marker, mode, equip or attune value is inserted. This retention proves preservation, not item benefits or numeric authority, and ordinary activation migration remains an explicit manager workflow.
- The existing reviewed-source proof binds genuine regenerated native output, signed Review, actor/action/target, actual original generation and raw state revision, complete typed frames and current source/configuration. Coordinator, publisher preflight and reserved rebuild repeat the checks; durable state must match the reviewed frame. Valid-marker no-plan renewal can change only independently proved capacities and must preserve the entire reviewed desired frame through ordinary preparation, including unknown fields. An absent-marker renewal that changes any state field refuses. Ordinary updates, new inputs and genuine reconstruction retain their separate strict contracts; no source-only acceptance establishes a successful publication.
- Reconstruction requires explicit original ability scores and original, confirmed or reconstructed provenance, with separate permanent species, feat and advancement layers. Displayed/capped totals and old inverse-derived records do not establish the original input. Unknown source choices remain explicit; they issue no dependent grant or formula and do not become numeric zero. Exact current class/subclass sources and actual attainment determine grants; retained later-level descriptions remain unqualified history.
- The versioned HP recipe retains exact physical aggregates, covered levels and provenance, reference Constitution, included continuing owners/corrections and separately known later events. Fractional means are not rounded and individual historical rolls are not invented. The adopted reconstruction policy uses maximum Hit Die contributions for levels one through three followed by the accepted pool. Other native characters retain their existing HP policy. A later known whole gain keeps its actual meaning when raw method/roll is unknown; a new native advancement appends a genuine event with an explicit bounded physical contribution. Current Constitution and each qualified continuing layer apply once.
- Aggregate qualification precedes its arithmetic. Unknown or conflicting Constitution withholds HP without evaluating the recipe or blocking independently qualified aggregates; genuine zero remains a number. A negative Constitution modifier still requires individual contributions when a nonmaximum accepted pool cannot prove minimum-one arithmetic. Read projection contains an anticipated recipe-domain failure with generic manager-review guidance and does not expose exception details.
- Retained whole HP gains remain exact when current and reference Constitution modifiers match, without being relabeled as physical rolls. A changed modifier requires qualified Hit Die bounds and a uniquely determined minimum-one result across all compatible physical contributions; ambiguous or inconsistent evidence refuses recalculation. Explicit single physical gains and maximum pools apply the minimum per level. Determinate changes remain supported, historical observations and current HP stay untouched, and aggregate pools do not supply invented individual rolls.
- A recipe combining retained whole level-up gains with a nonempty continuing-effect ledger refuses as ambiguous: the stored whole gains do not establish which effects they already include. Retained notes alone do not create that ambiguity. Empty-ledger retained gains and continuing ledgers with only subsequent physical events retain their meanings. Reconstructed advancement preview and strict construction share the prospective physical event, current permanent Constitution and continuing ledger, including a newly selected effect owner. An empty or invalid physical input displays a pending maximum; strict construction refuses it. Ordinary nonrecipe HP inputs retain their existing convention and current HP remains independently owned.
- A current campaign manager can record an already-completed advancement through the existing native level-up browser/API. This mode accepts the recorded whole HP increase, original offset-aware occurrence time and evidence description; it does not infer a physical roll or backdate the current adoption audit. Preview and strict production share the retained-whole recipe branch. Initial support is one existing reconstructed class row, an unchanged class/subclass spine, unchanged reference Constitution, an empty continuing-effect ledger and no intervening physical events. Unsupported combinations refuse. Current HP is preserved during adoption. Newly introduced class-slot pools require explicit recorded spending, including zero; lower-slot spending is retained. New resource trackers without a separately established current-use baseline refuse. Other separately observed play-state changes use their ordinary revisioned controls. Recorded mode retains existing daily preparation rather than inventing choices to fill new preparation capacity; required new known/book spells, cantrips, feats and other genuine choices remain explicit. New native advancement retains its physical-input convention.
- The native editor can review and record one manager-confirmed permanent tool or language proficiency acquired outside starting choices. Its browser/API preparation binds ordinary current numbers from the caller-owned catalog before checking authoring inputs; no source or numeric guard is skipped. A typed append-only acquisition retains known training/reward origin or explicitly unrecorded history, with no invented acquisition date. The confirmed native-edit audit joins exact prior/candidate generations, actor, state and the specific new proficiency; copied ledger rows or numeric markers do not grant authority. Existing state tuples, import bytes, historical data and native choices/waivers remain unchanged. Each acquired value has its own authenticated basis, so unrelated proficiency owners retain their meaning and future checks use current derived proficiency bonus. This records full proficiency, not expertise, an item, a class/background slot or a temporary translation effect.
- The same action can explicitly confirm one already-listed unowned observation. It preserves the complete proficiency array, exact label and ordering, appending only one acquisition declaration and its marker. The ordinary shared source-choice validator must attribute every other value in that category and prove the confirmed observation is its only surplus; incomplete choices, normalized duplicate labels, an already-effective owner or an earlier acquisition receipt refuse. A closed version-2 native-edit proof distinguishes this adoption from unchanged version-1 additions. The complete current source/actor/state/import frame is repeated under publication reservation; only actual prior/published generations and audit can supply durable custody. Unknown acquisition time remains unknown. If an earlier reconstruction stored an unresolved category, a later ordinary reconstruction review retains the receipt, resolves that bookkeeping and issues ordinary source-based witnesses; confirmation itself neither rewrites those choices nor grants other unowned values.
- Ingress preserves identity, assignment, URLs, personal content, original import/history evidence, stable physical item/spell/resource owners and portrait reference/bytes. It preserves the entire SQLite state tuple and definition-owned current selections, including damaged/current/temp HP, spent uses/slots/Hit Dice, quantities, activation/hand modes, charges, currency, prepared marks and unknown/absent/null/opaque observations. It initializes, refills, rests or clamps nothing. New definitions can remain explicitly uninitialized/table-managed when valid; ambiguous owners or incompatible current/max consequences block ingress for a separate disposition.
- An existing state without the equipment-activation schema marker can be reconstructed only under matching current reconstruction proof and exact physical-owner compatibility. Review and both publication boundaries use the same prerequisite. The marker remains absent, missing hand modes remain absent, and no item is implicitly equipped or attuned. A malformed marker, ambiguous or changed owner, altered observation, or unauthenticated mapping still refuses. This exception does not migrate equipment state or relax ordinary equipment-edit requirements.
- An already-valid activation marker keeps its original unique ID-list order and valid membership representation. Reconstruction does not require the sorted list emitted by the marker producer or normalize the retained marker. Invalid schema, duplicate or malformed IDs, incomplete activation rows and changed observations still refuse.
- One reconstruction preparation can reuse detached materialization of fully observed repository/source and audit inputs. Each lookup still observes its current validation inputs; mirror/configuration/image custody checks remain fresh. Refresh and publication-reservation preparations start a separate scope. Candidate-specific authority is rebuilt as its candidate and witnesses change, and source, permission, assignment and exact-state drift still refuses publication. This reuse is a source behavior, not a measured runtime guarantee.
- The bounded form accepts typed build/source choices and HP inputs, not replacement definitions/state or caller-supplied origins/proofs. Fresh Apply reauthorizes actor/access/assignment and binds the prior generation, definition/import, full state tuple, current source/configuration/policy, inputs/recipe and semantic result. Copied markers or source_type grant nothing. Only the matching confirmed committed generation/audit establishes durable origin custody; the pending prospective proof remains internal to reserved publication. Current effect qualification still requires its actual current source basis.
- A trusted pending reconstruction refresh supplies prospective numeric authority before ordinary candidate projection, both before and under publication reservation. Its exact actor, generation, candidate, state, source and policy checks remain required; serialized reconstruction labels cannot select this path. This is a source contract, not evidence that a reconstruction has completed on a runtime target.
- Shared reconstruction composition, native edit, advancement and requalification merge owned derived outputs onto retained raw containers; sanitized read projections do not replace original feature/equipment/spell observations or unknown fields. Supported new native tool/language slots carry validated selections or explicit unresolved placeholders, without choosing from retained labels or changing earlier input/history. Missing or changed current sources withhold dependent mechanics truthfully.
- Reconstructed class spells require exact current class/subclass/spell owners, attainable level and native cantrip/known/prepared limits. Spellbook, ordinary prepared and source-granted always-prepared ownership stay distinct. A retained flag alone supplies no automatic exception. Unattained, conflicting or unsupported rows remain raw and unissued. Original ability inputs, proficiency choices, recipe HP and reconstructed spell/formula/resource bases use their actual owners rather than an unrelated global library/page revision.
- Fresh current item-grant rebuilding preserves a surviving opaque spell ID only
  through a unique exact item-owner/source-row/canonical-publication match and
  global ID collision checks. The current item owner needs a canonical Systems
  definition key; positional or unlinked owner labels do not prove that match. A missing historical owner array is distinct from
  a contradictory explicit owner claim. Old rows supply identity only; current
  source, activation, grant, conflict and quarantine checks still govern benefits.
  New or unresolved occurrences cannot steal another retained ID, and list
  position or display-name equality cannot rename a surviving occurrence.
- Effective spell adapters refresh derived authority status and notes only after
  their actual current qualification succeeds. An earlier projection's refusal
  cannot override that result, but rejected sources, review flags, historical
  UNKNOWN observations and independent grant/casting/count rules remain intact.
- Versioned native feature spell grants use `source.native_acquisitions` and `spellcasting.native_spell_grants`, both schema1. A stable owner acquisition plus authored rule/leaf and exact spell publication identifies each occurrence; source revisions qualify currentness rather than changing identity. Retained feature IDs require authenticated unique custody, exact source linkage and attainment. New automatic acquisitions bind their source rule; selected acquisitions require an authenticated source-bound choice slot. Display titles, list positions and UI field indexes do not establish ownership. Unsupported ambiguous spell-grant choices remain visibly unavailable without disabling unrelated fixed or nongrant creation.
- Activated committed-source creation carries one signed acquisition intent across browser/API context, preview and submit. Progression binds its intent to the actual committed generation, raw state revision and definition digest. Supplied malformed, duplicate, expired or drifted intents refuse; submit never issues a replacement. Ordinary inactive nongrant creation and progression use their existing file-backed contract without an acquisition token or canonical grant containers. Presence of either canonical container cannot select that fallback, and an activation-proof error never means inactive. Draft acquisition/grant facts describe proposed source-supported changes only. They cannot enter verified-witness inputs or supply current mechanics. Confirmed grant custody requires independently authenticated audit, generation, model and acquisition provenance; stored status labels or the fact that bytes were saved do not establish entitlement.
- Ordinary campaign-page feats retain their page reference, opaque identity, choices and supported existing effects. Their synthetic catalogue identity is not a Systems publication or canonical acquisition. The shared feature producer selects that source family before applying Systems rule/slot identity requirements. This compatibility does not establish a campaign-award acquisition or grant unsupported page mechanics.
- Migrated definitions use one qualified-origin spell projection. Feature occurrences remain distinct when they grant the same spell; compatible presentation/counting is grouped by exact spell and casting-class lane, while differing ability, resource or condition paths remain distinct. Class-choice and item adapters contribute only their independently qualified facts within existing supported limits. Raw prepared/bonus-known flags and source labels remain historical observations, never an authority fallback. Resource and slot pools retain their existing qualified identities and current/spent ledgers; this model adds no casting transaction, free-use counter or refill.
- Fixed automatic source ownership and a historical raw feature association are separate facts. The exact selected class/subclass chain and attained unconditional source references establish the automatic origin. Only migration from the authenticated original generation, or genuinely confirmed unchanged retained model custody, can associate an absent historical owner key with its unique attained class row. Raw dictionaries, missing keys, opaque IDs and unattained observations remain unchanged; null, empty, malformed, conflicting or ambiguous ownership is never inferred. Opaque ID uniqueness covers the complete raw feature inventory. An unproved raw or elective observation cannot manufacture an automatic origin or erase an independently proved fixed one.
- New native creation and new progression features keep explicit class-row ownership. Retained progression transports its actual prior definition, target-bound confirmed grant witnesses and independently observed state revision; stored model labels, owner dictionaries or a confirmation boolean are insufficient. Source-only draft inspection supplies no historical association or effective entitlement. Historical migration custody authenticates the original frame, deterministic acquisition and raw/model/plan joins without resolving today's sources; fresh qualification separately checks current source support and any confirmed opaque association. Source withdrawal can withhold present benefits without rewriting historical custody.
- Grant inspection and automatic-output omission use the existing casting adapters in `character_builder_derivation`. The ability adapter returns the same display label stored by class-row derivation, such as `Wisdom`; slot progression returns dictionaries with integer `level` and `max_slots` fields. Correcting these import owners preserves the existing casting checks and payloads. Source inspection of this repair does not establish a successful saved requalification or correction.
- A fixed feature origin and an ordinary counted class choice remain independently manageable when they share a spell. The optional raw-row `native_class_choice_state` records an explicit `active` or `retired` decision; the field alone supplies no proof. Canonical ordinary origin requires an independently admitted decision or actual confirmed native birth, not generic numeric/model custody or a `Known` mark. Older unproved origins remain UNKNOWN. Genuine ordinary creation, advancement and management selections are distinguished before automatic feature, feat, innate, support or campaign outputs merge. An automatic grant marked `Known` or `Prepared` does not become an ordinary selection. Invalid types, unknown values or ambiguous identity withhold dependent choice authority.
- Supported Remove retires only the proved ordinary choice and retains its raw row and history; Add or supported replacement/reselection makes an explicit currently eligible selection or reactivation. Prepared Unprepare remains a preparation operation and does not retire ownership; this adds no cantrip removal or unsupported replacement rule. Raw preparation marks, historical flags, unknown fields and fixed-grant/acquisition identities remain preserved. Confirmed retirement releases only its ordinary contribution and supplies no current ordinary casting benefit; independently qualified feature origins remain usable and can still occupy a pool. Unproved decisions leave dependent capacity unresolved rather than freeing a slot.
- Class-choice accounting separates authenticated historical obligations, currently usable spell benefits and currently proved capacity. A confirmed active choice remains an obligation when its current spell source is unavailable. Missing count category, cost, allowance or required qualified ability makes the affected capacity UNKNOWN; raw level, marks, AP/BK flags and source digests do not supply those facts. Missing or ambiguous historical class ownership withholds every pool it could affect; an independently bound different owner remains separate. UNKNOWN blocks dependent Add and replacement, including net-zero replacement, while unrelated qualified pools, independent grants and nonallocating preservation retain their existing rules. Source withdrawal does not silently retire a choice or refund a slot.
- Management, progression and presented counts consume one qualified ledger before display filtering. Total class occupancy includes compatible proved ordinary and feature contributions; replacement offers only independently eligible ordinary choices. Existing item spell sources retain their independent source-row pools: their source-row flags or a copied class-row ID do not establish a class-capacity contribution. Qualified choices do not need a second literal `Known` display mark to count. Canonical import preserves every ledger-retained original obligation and its exact row/marker, including unresolved and ordinary untyped rows; incoming projected fields grant no authority. Add-class preview carries the same qualified facts and exact class-row identity as existing-class advancement.
- Complete affected prior and prospective pools are checked before choice-marker issuance and again with fresh actual original custody, current sources and qualified inputs under publication reservation. An unchanged typed decision or empty decision envelope does not establish spare capacity. Projected/cached capacity flags cannot authorize their own issuance; source, actor, generation, marker and revision checks remain required.
- First supported pool acquisition distinguishes positively proved prior absence from UNKNOWN history. Exact prior class/source/activation facts and the complete original owner/obligation inventory can prove an inactive pool or genuinely new owner; a missing entry, withdrawn source or unresolved former obligation cannot. Preview and strict production use the same inception contract, then validate complete future sources, inputs, choices and bounds again before issuance and under reservation. Presented preparation controls use the manager's exact unique KNOWN prepared-pool predicate, without preventing Unprepare merely because the pool is full.
- Choice-state confirmation uses the existing full-row selection marker and a bounded decision proof on the actual spell-selection or level-up event. Independent history validation joins its writing actor, actual prior and published generations, exact prior choice/decision, row and marker changes, source basis and state revisions. An ordinary authorized preparation edit or marker renewal carries the confirmed decision forward against the new complete row and marker; it does not invent another acquisition or reactivate retirement. Grant receipts, raw enums, old numeric batches and generic authoring flags cannot certify that decision. Publication repeats the exact prior-custody and transition checks under reservation. Historical retirement survives current source drift without granting current benefits; later normalization, requalification and advancement cannot resurrect an older active choice. Missing confirmation stays unresolved and does not authorize an automatic retry.
- Confirmed first creation can establish an ordinary birth from the actual generation1 receipt, producer-discriminated complete row/current marker and complete event admission, without inventing a prior generation0. The retained history reader joins that actual receipt generation even if identical definition bytes appear in later generations. Later births require actual adjacent generations and independently proved prior raw-row/marker absence, exact owner/source/actor and supported operation. Renaming an unresolved row is not birth. The same positive-origin classification governs adoption, ordinary reads, independent durable readback and retained-origin renewal; a generic renewed marker cannot upgrade UNKNOWN history.
- Future canonical creation and advancement collect actual spell contributors before merging or early source-owner suppression. After complete feature-model assembly and before pending authority or numeric issuance, only genuinely new automatic-only class output completely represented by exact supported native occurrences can stay virtual instead of adding a redundant raw class row. The complete original raw/marker/obligation/migration inventory remains authoritative for preservation. Ordinary selections, old UNKNOWN observations, player preparation, spending and unsupported or conflicting contributors cannot be omitted. Matching one declaration, an alias, missing active state or an AP/BK flag is insufficient. This prospective producer cleanup adds no stored origin proof and does not reclassify historical rows or relax first-adoption requirements.
- Ordinary canonical same-level or later-level reimport retains the paired grant/acquisition containers and all ledger-retained decision rows, observations and markers. Incoming imported proof cannot change a choice state or restore a retired choice. Ambiguous remapping, unsupported observation loss or unproved reactivation refuses before publication. Unresolved current benefits alone do not refuse unchanged nonallocating retention. The reconstructed-character retention path keeps its existing behavior.
- No-plan native requalification requires strict paired-model validation and independently confirmed custody for an existing canonical model, including an empty one, before preparing unrelated numeric changes. Missing, partial, malformed or unproved custody refuses before publication. Shared transition validation reloads actual original custody under reservation before accepting an unchanged model digest; a cached boolean or prospective candidate proof is insufficient. Genuine confirmed owners remain retained when current source conditions withhold their benefits, without repeating first migration or deleting elective ownership.
- First canonical adoption authenticates the existing exact reviewed migration plan before capacity evaluation at each publication boundary. Both prior containers must genuinely be absent; partial or malformed presence never selects legacy or inception behavior. The plan qualifies only its reproduced current source-supported feature occurrences, preserving independent original obligations and UNKNOWN raw origins. Exact nonallocating adoption can retain unknown totals without interpreting them as zero or allowing an extra selection, preparation change or retirement. Any separately confirmed removal remains its own exact semantic delta. Pending migration facts supply neither prior custody nor a durable receipt; saved-generation/audit validation must independently establish the committed model.
- Typed Systems feature metadata uses a strict `native_spell_grants` schema1 contract with authenticated owner/context bases, authored rule/leaf IDs, exact spell references and unlocks. Preparation, known, ritual and counting contributions remain independent, with explicit booleans distinct from absent, null, invalid or conflicting values. A grant-local false is not evidence that another origin is absent. Unsupported conditions, casting or usage dimensions withhold their dependent automation. Existing item parsing does not establish completeness for this strict feature contract; curated feature rules require explicit source reconciliation before reimport can replace them.
- A retained inert subclass container is accepted only when it names the exact selected subclass and its current declared class/source parent. It preserves context and content without granting effects, proficiency slots or Expertise from the container's metadata. Attained class/subclass features remain separate owners.
- The private aggregate frame applies that same exact inert-companion predicate without changing the retained row. Typed publication enumerates reconstruction ability/proficiency/item evidence only at its declared owner paths. New evidence binds current retained owners. Exact item-mapping history is compared by unique physical item ID and the complete stored entry against the same-target, same-origin prior committed pair; unrelated new advancement choices do not turn it into current physical ownership. Changed or dropped mapping history refuses. Historical mapping page references are nonmechanical Items-page evidence; an extant equipment page remains inert context paired to current approved Systems mechanics. Neither historical retention nor a source label grants current mechanics or audit custody. Unknown nested references and copied or unconfirmed origins still refuse; exact current source access and reserved publication checks remain required. Species source typing includes the producer's exact race/subrace alternatives.
- Reconstruction entry loading uses the existing visible, complete, noninitializing target loader before checking both campaign and Character systems. Unsupported or mismatched systems and unavailable targets cannot initialize missing state through this entry; ordinary readers retain their existing policy.
- A structured domain-spells table can use an attained always-prepared rule from the same exact parent class/source. Reconstructed eligibility binds both actual table and context payloads. A literal source-tagged learned-cantrip/count-exemption rule can authenticate a separate bonus-known cantrip; its range, casting-action or other prose does not become automated through that adapter. Class and item grants remain distinct even when they name the same spell.
- Existing page-only physical items have an optional explicit reconstruction choice to add a canonical Systems reference. It requires one current approved, enabled item with an exact consistent published-page relation; names and array positions never establish identity. The same physical ID, original page evidence, all other item content and every current inventory observation remain retained. Review includes the source's modeled/pending clauses. Only independently validated pending reconstruction proof permits this additive metadata exception before and under publication reservation; ordinary source relinking retains its separate state policy. Missing, ambiguous, unapproved or withdrawn relations leave dependent item mechanics unqualified. An authenticated owner does not imply that every item clause is implemented.
- The spell-retirement and aggregate-transition checks share the same current proof-bound same-owner authentication decision. Adding that approved source metadata does not retire the physical owner or require removing its retained spell/source-row IDs, owner links or prepared marks. The decision is rechecked under publication reservation; it does not mint a spell grant or exempt an unrelated owner. Ordinary removal and unproved relinking retain their existing retirement, aggregate and charge safeguards.
- Reconstructed aggregate baseline digests bind their actual linked current class/feature/page/item payloads rather than the global Systems revision. Native Save preserves retained unknown resource bootstrap observations; known numeric observations still require compatible bounds. Source withdrawal or an incompatible owner/max does not become a saved-total fallback.
- Reconstructed aggregate recipes omit uniquely identified, source-unlinked retained descriptions only from their private arithmetic frame after current authority has suppressed those mechanics. Their original rows and repair status remain visible. Missing or duplicate identities, unresolved linked sources, current class/gear/ability dependencies and unsupported adjustments still withhold qualification. Suppressed feature names cannot activate named mechanical rules. Current approved option payloads are not reinterpreted as historical adjustments during this recipe check.
- Reconstructed native requalification checks every newly issued automatic baseline aggregate and recipe HP through the same current recipe used by durable readers before issuing its prospective result. This uses an ephemeral output-pending authority, retains the real input and witness objects, and cannot manufacture historical aggregate custody. Current item casting and prepared-item context strings are freshly derived outputs of that same binder; they may change from the raw authority's empty context while all other input, source and custody references remain unchanged. Both original and derived contexts must be plain strings. A valid saved authorization alone never substitutes for this prospective recipe check. Explicit manager-only manual output keeps its separate existing contract. Source acceptance and disposable coverage do not establish successful saved-reader or UI qualification.
- Requalification remains bounded to historical audited owners and supported managed resource templates. An unchanged manual, unmodeled or unsupported page-owned template can still block renewal; it does not receive an invented witness. This limit does not authorize dropping that owner, changing its observations or treating its pending mechanics as effective.
- Reconstruction can add missing feature/template class ownership only when current typed source records prove one exact class, subclass and attained registered resource relationship. Initial and final issuance repeat that proof; pending publication and the durable prior/new generation join bind the exact additive ownership mapping. Existing nonempty owners, reset policy, display citations, original seeds and all raw play-state observations remain retained.
- Retained source aliases of one registered member can supply one qualified pool during reconstruction, current projection and, in activated committed-source mode, native advancement or progression repair. Continuation feature construction retains distinct exact source links until the complete prospective owner frame qualifies against current admitted sources and revisioned state. Temporary registered-member links and templates supply structure only; proposed preview capacities grant no numeric authority, current count or refill. Native advancement issuance independently recomputes candidate numbers before issuing witnesses and repeats currentness checks under publication reservation and durable readback. Every alias must independently qualify under the same class/source relationship; conflicting, cross-class or unproved owners refuse. Retained feature identities, citations and original bootstrap observations remain intact. Unknown or missing prior play counts, incompatible bounds or opaque resource details that the existing state merge cannot preserve cause a refusal before publication. Singleton, manual and standalone-create tracker paths retain their existing strict behavior; this adds no alias support to never-activated normalization. Source inspection of this continuation contract does not establish a successful saved advancement or repair.
- Publication requests an independent prior numeric view only when its actual retired-item or existing-transition checks require one. Exact physical identity and authenticated additive mappings are checked before deciding that no item retired; transition rows are read before deciding that no renewal is needed. Both decisions repeat under reservation with a fresh prior-view resolver. Candidate proof never supplies prior authority, and genuinely required but unavailable prior authority still refuses publication.
- Ordinary native-input revalidation retains its existing bounded scope. Reconstructed requalification additionally handles supported Expertise, retained supported half proficiency and qualified spell/resource/formula owners, authenticating retained inputs against confirmed actor-bound audit/generation custody and current sources. Final HP/formula totals are outputs, not retained input authority. Exact current state and preparation remain preserved. Reimport retains established reconstructed build/recipe/current choices under native precedence; raw content storage retains its non-deriving contract and cannot forge origin custody.
- Reconstructed native requalification can explicitly review a versioned spell-grant migration plan. Exact old spell IDs map to source-feature grant occurrences and separate unresolved historical-observation edges. Positive automatic grants do not require fabricated elective witnesses or invented negative proof about other origins. Preserve original spell rows, raw preparation/base/bonus-known observations, unknown fields and spent state; only an independently confirmed removal appears as its own recoverable semantic delta. The complete granting feature rule and attained leaves are modeled, rather than a character-specific list of flagged spells. Apply rebuilds draft source/acquisition facts under reservation, separately authenticates original custody, and retains default no-plan equality constraints. Independent durable readback joins the actual committed generation and confirmed audit before qualifying current grants; candidate or draft facts never certify prior or confirmed custody. Historical proof readers remain available for their original schemas.
- The same actor-bound pending plan controls the coordinator's exact spell-marker exception and both preflight and reserved exact-state checks. It grants no general raw-edit or trusted-authoring bypass. Replaced source-transition claims retire only after their actual prior authority, marker, owner and value are independently validated; the new confirmed native batch supplies current ownership while historical audit rows remain intact. Schema3 shares repeated origin headers by strict integer references and expands every original typed witness fact before historical validation, ancestor traversal and Review display; old schemas keep their existing representation. Review and Apply measure the complete sanitized audit with the coordinator's actual storage serializer, including publication fields derived from the current generation/state. The same check repeats under reservation before writing; redaction changes, drift or a payload over 65,536 UTF-8 bytes refuse without enlarging the limit or truncating evidence.
- Native resource renewal consumes the complete current qualified pool and template map. Multiple authenticated source aliases remain separate raw feature rows with one pool and capacity; missing, conflicting, manual or unqualified owners cannot be hidden by choosing one alias. Independently retained ability inputs and current permanent sources qualify provisional formula inputs without issuing resource authority. Durable renewal independently rederives owner/source bases, including every pool member and the separate slot/Hit Die recipes. Historical owner/reset custody does not invent usage or equipment history; current capacity and applicable item bonuses remain qualified from actual state.
- Nonmigrated automatic eligibility retains its bounded source-backed `additional_spells`, `spell_support` and table/parent-rule adapters, including exact edition resolution and unsupported-input withholding. It does not establish complete historical origins. Migrated definitions retire aggregate OR, label-derived bonus-known and source-row-as-origin authority; legacy inputs may contribute only through the shared qualified projection. Historical observations remain readable without granting effects. The temporary item adapter ends when its source rule and owner migrate into the same occurrence contract. An unavailable declared edition never falls back to a same-name spell, and unknown source dimensions never become false merely to complete a migration.
- These source contracts do not establish an operationally accepted foundation or a live cutover. Actual compose/Review/Apply/reopen, stale/access/replay, continuation, recovery, cross-consumer preservation and compatibility evidence remain separate from package/pure diagnostics and source inspection. Deployment, database preparation and live writes retain their own operator gates.

## Current Data/API Contract

- A revisioned DND-5E SourceAuthority classifies numeric fields, proficiency grants, resource owners and reset rules, spell slots, Hit Dice, and item charges separately. A copied source label, native-creation label, saved option, or plausible total does not prove ownership. Automatic spell grants match the current resolved spell identity and their own approved grant or choice; saved names cannot authorize another spell. Resource witnesses bind the exact feature, tracker, and class-row owner. In activated committed-source mode, unwitnessed historical values appear as raw table references with `NEEDS REPAIR`; disputed current sources show `NEEDS ATTENTION`. Neither status supplies an effective numeric zero, entitlement, reset, spend, Combat seed, or automatic derived effect in that mode. Related Character, Session, Combat, presented JSON, Markdown, and package views use the same read revision; unrelated verified effects remain available. Existing Combat snapshots retain unresolved numeric fields as historical table-managed values while a separately verified HP field can still be edited through Character state. Never-activated databases retain legacy saved-number Character state edits, rests, spell slots, and PC Combat and preset seeds with existing revision/CAS checks, even when numeric ownership is UNKNOWN or unattested.
- The integrated Stage 7 activation path can carry a current actor-bound native spell formula/choice or page tracker witness through the one-way source-mode change only when a private transition audit proves the exact original action, target, value, owner, source content, and closed and projected bases. The transition and marker commit together. An activated read accepts it only for the matching current source and target basis, value, and owner; later source changes fail closed. A historical class-row spell without a current choice witness may remain visible as `NEEDS REPAIR` with no automatic benefit and does not alone block activation when it owns no required present numeric value or effect.
- Current page-source authority uses published, campaign-visible Mechanics, Items, and Spells records. Its source snapshot binds canonical record metadata and a monotonically advancing page-record revision, so selective body loading does not change authority. Page writes and deletions advance a durable campaign revision; recreating a deleted source, even with identical content, receives a new revision. Sessions and other page sections do not enter character source witnesses. Hiding, removing, changing the section, or revising an eligible source invalidates source-bound formula and spell-choice witnesses until reverified.
- In activated committed-source mode, HP, per-pool Hit Dice, tracked resource, spell-slot, rest, and Combat movement controls reflect these per-target statuses, and service writes recheck authority with revision/CAS protection. Mixed Hit Die long rests use half the verified total character level as the recovery allowance, apply it only to verified pools, and preserve UNKNOWN pool rows unchanged. Item charge current/max values remain visibly raw until their owner is proved; their raw values do not become verified uses. Native creation and level-up can retain a target-specific owner through a durable post-confirmed private audit witness; a failed witness insert leaves the marker untrusted and the target in repair status. Manager attestation uses the same independent-audit rule for a specific current value or owner/reset rule.
- Supported save-time derivation records historical DND-5E sheet values. Current source authority and trusted owner evidence determine which of those values can participate in effective mechanics.
- The manager-only Source Repair numeric review can explicitly correct one uniquely identified, currently owned skill choice to `none`, `half_proficient`, `proficient`, or `expertise`. It recomputes the skill from qualified ability, proficiency and feature inputs and updates its dependent passive check in the same reviewed action. Nonzero or malformed manual adjustments to that passive require separate repair. Review and Apply bind the exact replacement and one or two fresh numeric witnesses, preserve prior history and play state, and retain actor, source, revision and confirmed-audit checks. Ordinary attestation still confirms the existing raw value when no replacement skill level is selected; a source fix alone does not change an already saved choice.
- Source Repair offers the existing bounded native-progression revalidation for supported single-class characters with ordinary skill proficiency and without spell-slot recovery, plus the separately scoped reconstructed-foundation renewal described above. It joins retained explicit inputs to confirmed actor-bound native audits and immutable generations, validates current source entitlement and derives current outputs. Review exposes retained choices, provenance and sources; Apply checks exact source/definition/state and confirms the audit through durable readback. Missing, disputed or unsupported input refuses its dependent recovery. Ordinary numeric attestation is unchanged. Native edits append a generation-bound audit for later source validation; revalidation preserves spent observations and actual progression history.
- Native revalidation requires all 18 explicit skill inputs and complete retained proficiency/resource ownership before publication. A resource's starting count must match its independently validated historical origin, even when current capacity differs. Earlier revalidation batches must themselves qualify; copying an earlier value does not establish custody. Legacy audit hashes remain readable only after the same input equality checks.
- Native Source Repair Apply checks the signed Review's unchanged 600-second limit at the authenticated manager request boundary, before loading Character context and source catalogues. Tokens already expired, signed in the future, malformed or mismatched still refuse; existing access, missing-target and blocked-health responses retain precedence. One private transient record binds the original pending proof, actual request, token, actor, route and independently loaded actual Character. Binding and capture claim one-way phases under a short lock; fresh validation runs outside that lock. Capture fills only the original incomplete object, with or without a spell-origin plan, and grants complete authority only after the full shared validations succeed. A copied proof or transferred slot cannot use or revoke the original owner's admission; rightful close invalidates retained aliases and prevents ordinary fallback. Owned failures, including aborted completion, close the lifetime without changing the original exception or durable outcome. Both coordinator mutation entries close it on every exit after their publication/replay work; the original route finally also closes earlier exits and follows independent saved-fact readback. Repeated complete checks remain valid throughout mutation. Ordinary and reconstruction proofs retain their separate behavior. No admission renews a token. Fresh source/currentness, complete state, reserved publication, bounded audit and durable readback checks remain required; default and non-native admission retain normal expiry. Source inspection of this boundary does not establish a successful runtime correction or a latency guarantee.
- Native Source Repair compares fresh manual and numeric audit witnesses with detached request-local equality baselines. Plain mappings remain distinct from the exact trusted aggregate, class-choice and grant-custody types; comparison includes the complete mapping and provenance, including generation aliases and migration receipts. Unknown subclasses and unsupported nested values refuse. Comparison data grants no custody and never reconstructs trusted objects: authority consumers retain the original independently verified witnesses. Fresh source-phase, reserved-publication and durable-readback checks remain separate. This compatibility contract does not establish successful Review, save, reopen or latency qualification.
- Per-entry Systems access checks ask only for campaign presence. Ordinary services retain their virtual campaign lookup and absence/error behavior; an open source-phase service proves the exact campaign from captured valid settings without rebuilding the page/link graph. Closed or cross-campaign phases still refuse before actor shortcuts. Actor, entry visibility, enabled-source, override, clamp, floor, role and fresh closing checks remain required; full graph hydration remains available to actual page consumers. This removes redundant projection work without sharing mutable Campaign objects or establishing a latency guarantee.
- Ordinary item Source Repair batches immutable Systems/page facts inside each normalization and review-refresh source phase. Numeric authority and character models are rebuilt; audit witnesses retain their independent verification. Existing item-action audit fields select this read optimization without granting permission or proof. The publisher owns separate preflight and reserved readers; an open phase is explicitly passed to its numeric consumers and never reused across reservation or durable readback. Complete source readsets, including absent/empty results, retain fresh closing checks. Exact normalized candidate, item baseline, policy, actor, target/state/config, proof/CAS and durable outcome checks remain required; shared normalization retains conservative numeric error ownership. This source contract does not establish exercised runtime or measured latency improvement.
- Audit history readers isolate each row's parsed metadata, witnesses, origin envelopes and mutable validation memo. Every connected reader, including native requalification's history producer, admits mappings before event-field access and skips malformed individual envelopes. A decision-bearing event requires complete numeric batch/target/basis admission and successful typed and origin finalization; a rejected batch cannot release occupancy through a retirement witness. Malformed or refused current evidence cannot borrow another row's metadata, erase prior valid history or publish a partial decision event. A valid empty decision list is distinct from a refused empty numeric batch. Independently valid legacy numeric evidence retains its existing behavior when separate grant custody is unavailable. Strict initial query failures still refuse; non-strict query failures return no witnesses. Individual malformed rows remain withheld without weakening actor, generation, marker or source checks.
- Guarded native editing retires copied manager numeric claims when their exact target, value or owner changes. It retains unaffected claims, raw choices and audit history; retired claims supply no current automation until an explicit supported Source Repair review qualifies them again. An ordinary edit does not mint replacement manager proof.
- An authorized managed resource's historical template and current capacity are distinct. Shared projection and resource-service authority derive current capacity from its unique qualified managed owner, required formula inputs and current qualified item activation. Equipment or attunement changes do not restore spent uses. Missing or conflicting managed-owner or formula qualification withholds capacity instead of exposing an old maximum. Unqualified item bonuses supply no benefit; an independently qualified base capacity can remain available. Unsupported manual resources retain their existing contract.
- Managed capacity binding uses the authenticated, SQLite-activation-reconciled structural selection for source, feature-composition, owner and template checks, separately from projected numeric inputs. Suppression of a replaced feature in the effective view does not change the selected ownership frame. Missing or mismatched structural inputs explicitly withhold recognized managed capacities; they cannot fall back to historical maxima. The exact source/owner/audit checks and effective suppression remain unchanged.
- Managed native ownership uses a stable source/base-formula basis independently of mutable item activation. The confirmed audit binds the historical raw template and seed. Native creation and advancement independently validate the complete current template before issuing proof and at confirmed readback; a stable basis alone cannot attest a maximum. Current read, state validation and rest calculations derive the effective capacity separately, and rest previews label that same capacity.
- Item relink confirmation compares the exact reviewed row after the publisher's prescribed clearing of the selected item's attunement and unknown charges. Every other field and the durable audit/currentness checks remain exact. A committed operation with a failed confirmation is inspected before continuation and is not reapplied merely because its response was an error.
- Source Repair enumerates its complete catalogue through the existing request-scoped Character read view after one library initialization per enumeration. Exact entry, source, override, actor and campaign visibility checks retain the manager's existing policy; the read view's stricter character-authoring eligibility does not replace that visibility policy. Campaign visibility settings reuse the existing request cache without eagerly reloading unused defaults.
- New native creation binds class features and their resource templates to the initial class row. Confirmed native create/level-up audits can qualify generated baseline stats and proficiency rows against current Systems revision, source choices, class rows, features, linked current Mechanics-page revisions and authoritative ability inputs. Equipment dependencies follow the target mechanics; ordinary shield activation retains unrelated skill and movement owners, while current AC is recalculated from qualified gear and ability inputs. State-only HP/resource/note saves do not replace those owners. Changed source inputs fail closed; a marker or native label alone remains insufficient. During level-up, qualified prior skill choices and validated new choices survive the in-memory derivation before the ordinary pending publication proof and confirmed audit establish the resulting values. Hit Dice retain absolute current counts as their level-derived maximum grows; level-up implies no rest recovery.
- Read-time projection derives current effective values without rewriting the raw definition or SQLite state. If current source authority cannot prove a component, the presenter exposes its stored value as a labeled table reference and withholds that component from effective automation.
- Native automatic AC, initiative, speed, passive checks and carrying limits are historical outputs, not intentional fixed manual overrides. Their confirmed audit origin establishes eligibility for a current formula; each result still requires its current source, ability, skill, equipment and other relevant inputs. Equipment activation changes those qualified results without changing the stored totals or spent resources. Direct manager numeric attestations retain their fixed manual contract. Native maintenance and advancement use the same current qualification before recalculating mechanics.
- Effective normalization primes a detached authority view from owned, resolved durable ability inputs before formula consumers run. Exact base/pre-penalty records, current modeled bonuses/minima and recoverable penalties supply these values; stored derived totals, unresolved recovery, conflicting owners and transient overrides cannot become base-input proof. Durable tracker inputs remain separate from temporary effects.
- Durable native parity compares current-source base formulas with durable candidate values. Ordinary reads use current qualified transient effects and compare against a recipe in that same role. Original definition/state ownership remains required; unknown roles or mismatched contexts refuse. Neither role rewrites play state or changes audit, witness, token or publication contracts. Spell and preparation qualification remains state-aware independently of the producer's durable formula role.
- Feature closure follows each output's actual dependencies. A registered versioned Divine Avatar form can bound its possible dependencies without authenticating a copied grant or an unpublished source. Known inactivity comes from valid current raw state, not from an empty transient result or suppression flag. Unqualified active or unknown activation withholds affected ability, skill, spell and aggregate outputs; unrelated verified formulas may continue. Unsupported versions, conflicting identities, extra effects and unknown footprints stay conservative. Source-repair warnings remain visible, and published-source eligibility is unchanged.
- Mechanically suppressed or unqualified Avatar rows cannot regain effects through legacy page-reference fallback. Qualified current transformations use the existing versioned adapter once, while durable base records remain unchanged. Persisted exhaustion, restored slots, temporary HP, cooldown and other action consequences retain their own state ownership and are never replayed by read projection.
- Explicit versioned Avatar grants can use an enabled, currently verified Systems feature owner through the existing entry-key or slug reference. Optional supplied identity assertions must match that current source; the authenticated grant retains its actual Systems provenance and accepts the existing singleton dictionary/list producer shapes without coercing versions or extra effects. Structural registration still grants nothing, and a current replacement cannot authorize a malformed raw selection or expose qualified benefit actions. Mechanical Systems enablement remains distinct from actor browsing visibility: private DM source prose stays private, unpublished campaign pages remain ineligible, and no source/character data adoption or historical ownership is inferred.
- Potential Avatar-family discovery recognizes the generic consumer's kind aliases and conservatively fences opaque related carriers without converting them. That discovery is only a refusal boundary: original raw/current selections must still satisfy the exact typed positive grant, source and ownership contract. Aliases, coercible versions, duplicate or extra effects never become authorized through discovery normalization; ordinary unrelated JSON and established inactive/durable behavior remain separate.
- Legacy, unactivated form projection also requires the unique eligible current campaign-page payload and valid current activation. A copied descriptor or page reference alone supplies no temporary benefit. This bounded legacy admission uses the already supplied visible page records; it does not publish hidden rules or create native grant/audit custody.
- Losing form-source qualification does not hide recorded active state, pending end costs, cooldown or existing transition/resolution summaries. A display-only repair card retains those obligations with every action disabled, including End. Presentation does not grant the form or replay its state; detached action history remains available in the presentation packet without adding a new full-history renderer.
- The integrated 10A mechanics-impact extension can compare one explicitly
  selected, separately authorized Character against current and proposed
  versions of one Systems `item`. It requires the Character's exact
  `(entry_key, source_id)` item reference and runs the existing Character
  mechanics projection twice through a request-local in-memory overlay. The
  Character-specific result is digest-only preview evidence: it does not write
  the Character
  definition or state, relink equipment, alter an accepted Character-update
  plan, or apply the proposed Systems row. 10A adds no Character route or UI.
  Exact commit `2ae1d0b4e6f866c727266cfe43b78c6f3cfedec1` is on protected
  `main` and `origin/main`; it is not deployed.
- Shared derivation covers proficiency, saves, skills, passive checks, initiative, speed, carrying capacity, max HP when provenance exists, spell DC/attack, slot progression, Armor Class, attacks, and resource templates.
- Campaign `character_option` metadata supports structured `mechanic_effects` rows for modeled mechanics. Legacy string `modeled_effects` remain supported and are normalized into structured rows while preserving legacy effect keys for existing builder paths.
- Campaign `character_option.resource` grants are also mirrored as structured `resource_template` mechanic effects. Scaled resources such as Wild Magic's half-level Wild Die derive from metadata, keep their scaling payload on generated trackers, and do not require parsing descriptive page prose.
- DND mutable state includes HP/temp HP, per-die-size Hit Dice pools, exhaustion level, resources, spell-slot usage by slot lane, equipment state, inventory quantity, currency, notes, and feature states such as Arcane Armor and Divine Avatar Forms. A Character-page batch validates and applies explicit state changes before one final-HP Avatar transition and one persist, so the transition observes the batch's final HP.
- Divine Avatar Forms is a versioned, registry-backed stateful campaign mechanic. DND-5E sheets receive individual forms through structured `divine_avatar_form_grant` mechanic rows; the exact `mechanics/divine-avatar-forms` page reference remains a narrow compatibility grant for Avatar of Mourning v1. Display titles never grant the mechanic, unknown systems are denied, and adding a future adapter does not implicitly grant that form to existing sheets. Versioned mutable state owns the single active-form identity while preserving opaque future form data.
- Avatar of Mourning activation requires the character to be conscious and below half hit points, grants non-stacking temporary HP, and restores spell slots. While active, an uncached transient derivation pass sets effective Wisdom to exactly 26 and applies AC +4 plus the additive +3 spell attack/save-DC bonus. The stored definition and true Wisdom are never replaced; when the form ends, or when an updated stored Wisdom is read, the inactive sheet immediately derives from that current true score. Projection failures fail closed before persistence and in presentation, while a structurally valid active form retains a permission-gated safe End action. Form actions require explicit confirmation and retain a bounded correction/action audit. Ending applies exhaustion, starts the 40-day cooldown, and creates a persistent pending table-resolution record for the single radiant-damage instance; resolution records the actual table-applied total but does not mutate HP automatically.
- `scripts/export_dnd_character_sheet.py` exports visible DND-5E character sheets to Markdown for a single character or all visible DND-5E characters in a campaign. The export uses the same presenter-normalized definition plus SQLite mutable state as the read sheet and intentionally omits image assets.
- Hit Dice max pools derive from class-row levels and hit-die metadata; current counts stay in SQLite. Long rests restore expended Hit Dice equal to half total character level, capped by pool maximum, and do not auto-heal HP. Rest confirmation fields let the user set final Current HP and current Hit Dice after the modeled rest recovery before applying the rest.
- State reconciliation treats unlabeled legacy spell-slot rows as migration-only once tracked slot lanes exist.
- Artificer active infusion state lives on targeted equipment rows as normalized `active_infusions`. Known infusions derive from modeled Artificer Infusions feature rows and known-infusion summaries, while active capacity derives from Artificer level.

## Current Spellcasting Contract

Recognized literal learned-cantrip/count-exemption clauses contribute only their learned grant and exemption semantics to native spell replacement checks. The actual referenced spell must resolve to level0, with exact source/class/spell context. Range, casting-time and other prose clauses are not inferred by this adapter; unsupported suppressed contributions still refuse complete replacement.

- DND-5E reads build one effective source-authority view from the current approved Systems or published campaign-page source, the character's exact link or selection, and reconciled SQLite equipment activation. Saved spell, feature-manager, item-option, and source-row copies are historical provenance, not proof of an automatic grant. Stale explicit links do not fall back to matching titles. Conflicting current source records pause only their disputed effects and require manager attention; unrelated verified grants continue.
- A legacy spell whose source cannot be verified stays visible for table play with `NEEDS REPAIR` on Character, Session Character, Combat, presented JSON, and exports. It supplies no automatic source row, spell bonus, always-prepared status, or free-use entitlement. An independently manager-authorized entry is labeled `MANUAL`; its versioned authorization binds the character, entry or row, metric or availability, manager action, and audit provenance. A generic manual label or import cannot authorize it. Managers can preview the gained and lost effects of an exact relink before a guarded apply.
- Never-activated sheets retain saved spell badges and the normal Current/Preparation split for rows without source-authority status; activated provisional rows retain repair labels and their table-use visibility.
- Effective spell attack and save DC values retain per-row, per-metric `spell_metric_provenance`. Approved typed `spellcasting_modifiers` from currently active items apply only to proven formula rows. An imported or manual total without proven formula provenance stays final, even if its number matches the formula; the sheet discloses that item bonuses are not automated for it. A sourced `final_override` wins over formula and item effects, while an `adjustment` adds only to proven formula and applicable item effects. Divine Avatar's transient bonus applies once after effective base math without changing saved definition values.
- Formula qualification applies to owned spell rows before deriving the single-class summary. That summary agrees with its qualified row without needing a separate empty-row witness; multiple class rows retain an ambiguous summary. Item actions consume that qualified unique DC, while supported imported/manual final summaries keep their existing contract.
- A metric withheld by current source authority remains unavailable even when historical provenance contains a final override or an item or transient effect applies. An authorized metric with a sourced final override retains that override.
- Approved item modifiers name an `effect_id` and separate integer `spell_attack_bonus` and `spell_save_dc` values. An optional `class_row_id`, `source_row_id`, or `class_selector` narrows the target; only an absent scope applies to all proven spell rows. Invalid or ambiguous typed scope, value, source, or target warns and applies nothing. Equip is required, and attunement-required items also require attunement. Distinct applicable effects add, while identical canonical duplicates count once. Effective values appear only in presentation; the raw definition remains historical through reads and equipment state changes.

- Shared-slot multiclass spellcasting is limited to supported `full`, `1/2`, `artificer`, and currently supported `1/3` subclass-only lanes.
- Warlock Pact Magic remains a separate lane.
- Subclass-only spellcasting requires supported Systems metadata or bundled fallback coverage for PHB Eldritch Knight and Arcane Trickster.
- Spell add/update/remove actions route through an explicit target class row.
- Combat and Session Character consume the Current spell set. Unprepared ordinary candidates stay in Preparation; provisional legacy spells stay visible for table or GM use with `NEEDS REPAIR`. There is no one-click per-spell Cast control.
- Current prepared marks persist on definition spell rows through guarded spell management. This differs from SQLite-backed spell-slot usage and resource pools; preparation's logical role in table play does not change its existing physical storage contract.
- Always-prepared grants stay out of manual prepared counts and should not render as separate source-package cards when each spell card already carries the badge.
- Always-prepared grants require current verified source authority. Historical flags and legacy imported source labels such as `Cleric (Always Prepared)` may remain in the raw definition but do not authenticate an effective always-prepared or free-use entitlement.
- Spell detail popups show `At Higher Levels` upcasting mechanics from presenter spell payloads when available and suppress the section when not present.

### Present Spell Reconstruction For Prepared Casters

- An existing single-class native reconstruction can explicitly confirm its current spell roles through the reviewed native-requalification operation. Schema5 binds the exact original generation/state, actor/action, native foundation, current class/subclass/spell sources and complete retained spell inventory. It records a present checkpoint rather than invented learning dates: chosen cantrips and current ordinary preparations receive genuine current-choice custody; other supported leveled class-list observations receive availability custody, not learned ownership or retirement. Earlier requalification schemas retain their existing contracts. Unsupported modes or ambiguous roles refuse.
- Class-list access, current ordinary preparation, automatic feature grants and item access remain independent. Available unprepared class-list observations consume no learned-choice or preparation capacity. Actual selected preparations and cantrips require complete qualified limits; automatic exemptions are scoped to their independently qualified origins. Historical roles do not grant mechanics after source withdrawal, erase an actual selected obligation, or supply missing numeric inputs. The migration preserves raw rows and historical markers except the explicitly reviewed selected-row state metadata and approved removal; it creates no current-state refill.
- Publication freshly regenerates and authenticates the pending checkpoint under the existing reservation boundary. The saved reader issues exact typed role facts and selected-choice decisions only after audit/actor/generation/state joins. A trusted available retained row is prepared through a distinct preparation event, preserving its ID and raw fields except preparation aliases and its explicit active state. Unprepare retains that state; neither action invents a learned birth or retires a choice. Ordinary Edit preserves unchanged native rows through legacy campaign-option replay and refuses a material existing grant/replacement-source change for source repair. Advancement and import retain the same custody and raw-observation boundaries.

- Shared spell-choice custody indexes observations by their exact validated raw spell IDs and tracks unresolved and profile class owners by their exact validated class-row IDs. Text predicates decide validity and never substitute for identity. Missing, malformed or duplicate spell IDs and ambiguous typed ownership still refuse; invalid or ambiguous prior class ownership keeps automatic-output omission disabled. Identity alone grants no source, choice, capacity or history authority.

## Current Equipment, AC, And Attack Contract

- AC qualification follows the applicable armor recipes: fixed heavy armor does not require Dexterity, Constitution or Wisdom; light/medium armor requires Dexterity; applicable competing unarmored class recipes also require their actual Constitution/Wisdom inputs. Shield constraints and qualified dual-wield occupancy still determine which rules apply.
- Formula reminder DCs require qualified ability and proficiency inputs before formatting feature or item reminders. Missing inputs produce generic current-DC wording across returned definition and reminder views; a genuine zero ability score is preserved. Item-action DC labels also withhold stale numeric text when their qualified spell DC is unavailable.

- DND equip, attune, and wield choices are authoritative in versioned SQLite inventory state. An exact unique item ID joins state to the historical definition; explicit false and empty wield values override YAML. New unique IDs can seed from YAML only when the versioned known-ID record proves they are new. Ambiguous IDs or incomplete rows show warnings and pause affected edits until manager repair. The manager-only `/characters/<character-slug>/equipment-activation-repair` page previews YAML and SQLite rows and journals an explicitly selected preserve, remap, or discard repair. A DND definition/import pair with no SQLite state fails closed on ordinary reads and is reported by the controlled-copy migration for separate operator reconciliation; Xianxia retains its existing missing-state behavior.
- Character, Session Character, Combat, and JSON equipment actions keep their routes and permission boundaries but commit a state-only revision after a fresh definition identity check. Read-time mechanics use a temporary state activation overlay; the definition file remains historical. Disabled or unresolved linked item sources suppress automatic sourced bonuses and actions with a visible warning while retaining physical activation and reference text.
- Automatic item mechanics require the exact eligible Systems item; linked published Items pages supply prose and provenance. A missing, unpublished, hidden, or ineligible required Items page, or an unavailable required Systems entry, suppresses automatic sourced effects while keeping equipment activation and manual/reference data visible. Removing a DND item through the explicit Inventory action requires review of the complete SQLite row and deletes that row and its attunement reference in the same revisioned structural write. Ordinary imported item metadata is supported. Inactive exact page and manual reference rows can be removed or relinked; ambiguous identity, uncertain active effects or changed source proof require repair. Other definition omissions or ID drift remain blocked for repair.
- The versioned controlled-copy migration, dry run, provenance mapping, and separately gated live sequence are described in [DND equipment activation cutover](../character-equipment-activation-migration.md). No live migration or deployment is implied by this source contract.

- Equipment-state controls are narrower than Inventory: weapons, armor, and qualifying magic items belong on Equipment; general gear remains Inventory-only unless durable metadata says otherwise.
- Existing supplemental Inventory and Advanced Editor HTML/JSON note edits update the exact item's definition and current SQLite inventory through the normal guarded publication path. An omitted note preserves both copies; an explicit empty clears. Editor fields show current inventory notes. Submitting an unchanged current note preserves a different historical definition note, so unrelated edits do not rewrite it. Unknown or ambiguous item identities refuse the note change. Built-in editor equipment remains read-only.
- Armor Class derives from equipped armor/shield state when durable equipment metadata is specific enough.
- The PHB Dual Wielder feat contributes +1 Armor Class once while current qualified equipment facts prove two distinct melee weapons wielded one-handed, one in each hand. The conditional bonus requires positive current quantities, explicit valid activation and current feat/item authority; a shield, two-handed mode, ambiguous identity or unavailable authority cannot grant it. It does not require Two-Weapon Fighting or weapon proficiency. The current derived value changes with equipment state while saved historical AC remains intact; fixed direct-MANUAL AC retains its existing behavior.
- Linked Systems armor metadata should be repaired in the Systems library rather than patched with character-side title parsing.
- Generated weapon attacks carry stable equipment refs, mode keys, and variant labels. Ordinary equipment saves retain exact catalog references. Ammunition selections use the referenced catalog unit and selected-unit weight, while later inventory quantity remains mutable state. The catalogue adds no automatic ammunition consumption or attack resolution.
- Lawful weapon variants share applicable item bonuses; two-handed alternatives exclude one-handed Dueling. Approved typed `weapon_extra_damage` rows append bounded unconditional dice and damage types once per generated attack. Full and scoped projections pass the same relevant item catalogue to derivation and final numeric qualification.
- Quick Reference hides linked weapon attacks when source items are not equipped and respects explicit wield modes, using the same eligible item catalogue as derivation. Explicit SQLite unequipped state remains a visibility veto; reads do not repair conflicting stored activation fields.
- Armorer Arcane Armor is mutable character state at `feature_states.arcane_armor.enabled`; it gates Guardian Thunder Gauntlets and Defensive Field availability.
- Eligible Artificers get an Equipment-page Infusions lane. Active selections target eligible nonmagical inventory/equipment items; `Enhanced Defense` is automated as a +1 AC defensive rule while the infused armor or shield is equipped, and unsupported active infusion effects remain visible as active note-only rows instead of silent partial automation.
- Supported magic weapon/item effects require equipped state, and attunement-gated effects require attunement.
- Approved campaign-owned Systems `item` mechanics now use the same item metadata paths as shared DND item rows for supported weapons, armor, attunement, spell grants, resource modifiers, defensive rules, attack reminders, and spell-slot-funded item-use actions.
- Campaign item rows with `draft`, `manual_review`, or `reference_only` mechanics review status are visible as Systems entries but do not drive attacks, Armor Class, spell grants, resource math, or item-use automation.
- Approved `item_capabilities` v1 declares a finite physical-item use counter on the existing inventory `charges_current`/`charges_max` pair, one exact item-spell casting variation, and bounded attuned passive/rest clauses. Source ownership/capacity/reset is independent of current availability. A null pair stays unrecorded; only an explicitly confirmed manager operation can initialize it. Known current uses use the existing authenticated inventory mutation/CAS path (`operation=item_uses`); maximum is source-owned. Duplicate physical/catalog identities, stacks, malformed pairs and changed incompatible source rules withhold positive control without clamping, default-full initialization or equip/attune refills. A previous source-clearing marker remains historical provenance; later qualified admission and ordinary count preservation do not erase it or replay a rest.
- The closed `item_capabilities` v2 source contract adds separate fixed-level free and minimum-slot paid casting modes, plus optional original-caster spell storage. Each mode binds an exact current spell key, activation, timing, components and any first-seen reaction declaration. One physical item's free mode owns its counter independently of paid casting. Paid casting spends one selected qualified class or granted slot atomically; free casting requires known remaining uses and spends no slot. Reads never initialize unknown availability. Item access adds no class spellbook, known or prepared choice. Target eligibility, component fulfillment, checks and effects remain table managed; a lore-check spell does not acquire a class-header save DC.
- Spell storage uses optional top-level SQLite state `item_spell_storage`, keyed by exact physical ID. Absence means unrecorded, distinct from a manager-confirmed empty baseline. An exact current source capability supplies the level budget; the latest actor-bound audit checkpoint for that physical item authenticates the saved contents across source bases. Unproved, malformed or changed-source observations remain stored but withhold positive control. A self-store atomically spends a selected qualified slot and freezes the spell's original class-caster ability modifier, save DC, attack bonus, source fingerprints and slot level. Automatic self-store currently accepts qualified ordinary class spell choices with proved prepared/known access and owner metrics; it does not substitute a class header for a feature/item's distinct casting path. Other actual caster paths can be recorded through the explicitly confirmed manager external-casting observation, with complete original facts and costs recorded separately. Casting from storage removes one selected entry and spends no wearer slot; later wearer/class changes never recalculate stored caster values. Ordinary edits, imports, advancement, reconstruction, rests and equipment/source changes preserve the entire ledger, including spent-state custody. This source contract does not admit any particular Systems declaration, initialize a character baseline or establish an exercised cast.
- Item daily/dawn recovery follows the existing campaign long-rest convention while retaining source wording and exact amounts. The supported v1 counter is fixed full recovery; dice/partial recharge is not silently converted to full. Uses reset only on a real applicable rest. Preview and application share the same source-owned counter and Hit Die recovery calculations. An attuned item can add a qualified recovery allowance beyond the base half-level amount, capped by missing verified dice; no Hit Die capacity growth or qualification of unknown pools occurs.
- The bounded source casting variation uses highest owned qualified spell-slot capacity, including exhausted slots, with no slot expenditure. Its current source ability plus qualified PB derives the save DC; class-specific modifiers cannot leak from a generic class header. Typed per-level damage/half-save/no-wakeup clauses remain distinct from canonical spell rules; target, roll and condition resolution is table managed. Explicit attuned-only ward/recovery clauses stay active while unequipped and turn off when unattuned; independent bonuses retain their previous activation requirements.
- Existing manager Source Repair can authenticate an exact page-only physical item to its unique current approved Systems/page relation without replacing that physical object. Its signed proposal and reserved recheck preserve the complete definition except the additive Systems reference, the original page context, and the complete current state. Genuine source replacements retain ordinary claim retirement and clearing. This code contract does not prove any particular isolated/live adoption or exercised casting/rest.

- The first structured Linden Pass item records cover Consecrated Huran Blade, Censer of Last Light, Hourglass Pendant, Staff of the Crescent Moon, Psionic Circlet, and Innovator's Bolt. Supported fields can automate after approval; item spell support, item defensive rules, Hourglass Pendant, Psionic Circlet, Innovator's Bolt base weapon mechanics, and Innovator's Bolt enchanted bullet spell-slot expenditure now work from approved item metadata rather than title-specific character fallbacks. The approved Innovator's Bolt action exposes Incendiary, Booming, and Smoke choices and spends spell slots; the damage scaling, saves, nearby-creature damage, prone/deafened, and blinded riders are displayed as table-managed reference text and are not applied automatically. Bespoke effects such as extra damage riders, incense healing, initiative shifting, custom Sleep target resolution, and Innovator's Bolt area/condition resolution remain tabletop/reference-level unless a narrower structured hook covers them.

## Noncasting Item Uses

Approved `item_capabilities` v3 supports a noncasting attack-d20 substitution:
while worn/equipped, explicitly choose 10 instead of rolling an attack's d20
and spend one use from that exact physical item. It requires no attunement,
spell slot or spell DC and applies to attacks rather than only weapon attacks.
The choice is not an automatic hit, save/check result, damage roll or completed
attack; modifiers, targets and outcomes remain table managed. Current source
rules, unique quantity-one physical ownership, activation custody and known
compatible remaining uses must all qualify. Unknown, exhausted, unequipped,
ambiguous or source-incompatible items do not enable the action.

The shared source counter supports fixed maxima from 1 through 1000. Clockwork's
documented declaration uses maximum 1 and preserves `source_reset: at_dawn`
with the existing campaign long-rest recovery mapping. No timer or read-time
recovery is introduced. The existing inventory charge pair remains the only
availability ledger; manager confirmation of an actual null/null observation
and ordinary count observations/rests stay separate from spending. Source
support does not itself admit that declaration, equip an item or establish its
current remaining uses.

The shared inventory packet and item-use partial show the rule, source/campaign
recovery and explicit unavailable reasons. Ordinary Sheet and editable Session
forms require confirmation and deliberate submission. Existing read-only
Session/Combat surfaces show the same facts without new mutation controls.
Authenticated HTML/API inventory actions recheck current source and the exact
state under the existing reservation, decrement only the selected current
counter, and commit a bounded choice audit with the CAS state update. All other
state and spell/storage budgets remain exact. Stale or incompatible requests
refuse; the operation never initializes, refills, equips or normalizes unrelated
observations. Existing v1/v2 casting, storage and recovery semantics remain
unchanged.

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

- `player_wiki/character_reconstruction.py`
- `player_wiki/character_reconstruction_authority.py`
- `player_wiki/character_reconstruction_proficiencies.py`
- `player_wiki/character_reconstruction_routes.py`
- `player_wiki/character_reconstruction_state.py`
- `player_wiki/character_hp_recipe.py`
- `player_wiki/character_native_requalification.py`
- `player_wiki/character_spell_reconstruction.py`
- `player_wiki/character_source_reads.py`
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

### Authenticated optional language outcomes

Reconstructed native characters may retain their original choice observations
while a current campaign DM/admin explicitly declines an unresolved optional
language on the existing Character Update review surface. A declined slot grants
no language. Its additive schema1 outcome is bound to the exact current owner,
canonical source ref, owner/category position, ordered source count/domain and
authenticated decision. Fixed grants and already selected observations cannot be
declined. Copied source JSON, player body edits and saved unresolved flags confer
no decision authority.

The same manager review can directly adopt an already observed language for an
undecided source slot. Adoption retains the exact ordered language list and
original unresolved observation; it creates neither a new grant nor an invented
decline. Each adoption binds the current owner, source, slot position/domain,
selected retained label and permission. A source-domain label uses that source;
an ordinary exotic language outside an exact standard-language species or
background domain requires explicit DM permission for that one slot and value.
This does not broaden `anyStandard` or permit secret class communications.
The authenticated receipt, current language basis and ordinary readers consume
the same adopted outcome. Duplicate ownership, reordered observations, unsupported
permission and unrelated changes refuse. Existing decline and later new-selection
semantics remain distinct and unchanged.

The operation preserves original reconstruction inputs/choices/origin, every
non-language basis/marker and the complete play-state row. It does not replay the
foundation or normalize HP/abilities. Review/token, fresh reservation and confirmed
audit/committed-generation custody qualify the same language outcome. A later
explicit legal selection can supersede its exact authenticated decline on that
same bounded surface; carried decisions keep their original IDs and history.
Ordinary body edits and native advancement preserve valid outcomes, while changed
owners/counts/domains remain unresolved and never auto-refill a slot.

The full build-reconstruction receiver refuses a retained outcome vector rather
than silently dropping/reissuing decision history. This unsupported combination is
separate from supported normal edit, advancement and narrow language supersession.
No current character is changed by source implementation or disposable checks;
Common/Celestial and the two source-bound declined electives require a separately
authorized current adoption and saved-reader verification beyond the historical63.

### Ordinary Review prerequisites (source254; source-only qualification)

Ordinary Source Repair relink, manual authorization and numeric attestation now
check equipment activation before expensive review preparation. Before signing,
the coordinator reuses its actual update prerequisite block for retained native
grants, choices, capacities and protected reconstruction/language/source markers,
with factual ordinary None pending inputs. The receiver's current authority and
state preparation and the existing pair bounds are checked without publishing.
Review and Apply share the ordinary audit payload; only bounded finalization using
the actual token hash follows signing. Known activation/state/publication refusals
return no token and the existing manager activation-repair link when applicable.

Normal Update Review uses the same candidate/state, activation and ability checks
as Apply, including the genuine reconstruction exception. Native requalification,
reconstruction and language decisions retain their existing producer/typed proof
paths. No Review check is a pending proof, claim, cached publication input or
permission to mutate. Apply still performs real proof admission/lifetime checks,
fresh source/currentness, reserved validation, CAS, audit and durable readback.
Activation adoption remains an explicit state-changing manager operation; source
acceptance alone establishes neither its final normalized delta nor runtime proof.

### Activation preservation preparation (source255)

The existing manager activation-repair page has an explicit preserve-only preview.
It uses the real current record and preserve planner, coordinator preconditions and
the actual publication preparation path. A private fixed-operation sentinel stops
before reservation and every publisher write; special/pending/audit/reimport/asset
inputs are refused. No client flag can turn arbitrary updates into previews.
Owned source phases and final read-only snapshot checks retain currentness and
cleanup ownership. Complete normalized state, admitted/rendered raw YAML and real
prospective renewal templates are available for comparison. Oversize evidence
refuses rather than truncates. Inserted audit IDs/timestamps and rolling new
identity remain commit-time facts. A preview creates no token or publication
permit, and normal Apply still performs its original fresh reserved checks.


### Historical native spell-choice source binding

An authenticated active spell choice does not need adoption again merely because
an unrelated Systems entry changes the global revision. Current read authority
still resolves the exact class, spell source, list membership and attained level.
For an older globally framed basis, the durable decision reader carries its
authenticated snapshot as ephemeral typed custody. Admission must reproduce the
old audited basis from those fresh local facts, changing only that snapshot.
The exact stored marker, raw selection and typed decision must still agree;
missing, malformed or ambiguous custody refuses. Changes to the local choice frame cannot use this compatibility path. This preserves existing stored basis/receipt formats and
does not renew or rewrite character data on read. Transition proofs keep their
existing identity checks and cannot supply this compatibility path.

### Effective spell range and casting options

Current qualified spell properties are projected separately from entitlement.
The strict item `spell_property_modifiers` list names an `effect_id`, exact
`spell_ref`, `condition: wielded`, integer `range_feet` and optional exact
`legacy_source_row_id`. It does not learn, prepare, grant or duplicate a spell.
Existing source policy, approved metadata and exact physical activation remain
required; equipped/attuned does not establish wielding. Raw definition and state
are never rewritten by this effective view. Reviewed reclassification explicitly
clears the corresponding old `spell_support`; historical raw rows/receipts stay
intact and appear in `spell_modifier_legacy_observations`, without another choice.

Qualified native feature leaves may additionally expose source-derived range
and bonus-action options from the complete supported literal learned-cantrip
paragraph. This ephemeral interpretation does not change the v1 acquisition,
leaf, occurrence or persisted digest formats. Exact source/owner/leaf/custody and
current canonical spell data still govern; imported range/action fields are not
modifier authority. Ephemeral authority comparison identities include the new
current display/property facts. Unmodeled prose is diagnostic, not permission
to remove an independently qualified spell grant.

Effective rows retain canonical base properties, action options and each
source/condition provenance. Equal range replacements do not add together;
conflicting ranges withhold the property with a diagnostic. Each entitled class
occurrence keeps its own ability, slot/capacity and feature ownership. Removing
an item does not remove an independent qualified feature's range/action option.
A separate item occurrence, attack/DC roll or native-feature `casting_paths`
entry is not required to prove a conditional range modifier. This source
contract needs a later genuine saved-sheet qualification; source review alone
does not establish current item metadata adoption or runtime behavior.

Source-only continuation: the same authenticated history classifier is used
before ordinary normalization sanitizes/regenerates item grants. Exact legacy
spell observations and their source rows survive normalization; conflicting new
owners refuse rather than overwrite history. Historical/import paths lacking
current authority refuse only when they would otherwise strip an existing
matching legacy observation. Fresh creation without such history is unaffected.
Standalone sheet history remains visible when no entitled counterpart exists.
Exact import retention preserves the reviewed empty spell_support choice along
with its modifier; conflicting imported grant claims refuse. Old standalone
item attack/DC markers remain authenticated historical custody, not current
formula authority for a non-entitling range modifier. Current class spell math
and every unrelated applicable qualification remain strict.

Legacy classification additionally requires an explicit typed empty grant clear
from the current verified item source, retained independently of activation,
and absence of any currently verified/disputed owner of that source row. Missing
clear evidence is not an empty clear. Derived positive grants, changed physical
owners or changed source-row behavior refuse historical restoration. Only
source-row numerical outputs and generated metric notes may be replaced by the
unchanged historical record. Strict modifier parsing precedes every declaration
key/iteration in normalizers and import retention; malformed source data yields
the existing controlled build/import refusal, not accidental container errors.

The wielded spell-property condition also requires the exact owned physical
inventory row to contain a positive integer quantity, excluding booleans.
Nonpositive quantity cannot activate the modifier even if stale equipped/hand
flags remain set; missing or malformed quantity is an unknown inactive
condition. This guard never edits quantity/activation state, reclassifies clear
intent as entitlement, or removes independently qualified feature benefits.


Current spell reconstruction also accepts known casters through the existing native requalification route. A complete current checkpoint binds every retained role, source identity and row digest; chosen cantrips and known leveled spells receive ordinary current-choice custody within their source-derived capacities. Known spells retain their Known marks and cannot become prepared/list-available observations. This is current confirmation, not an invented acquisition date. A checkpoint may have no automatic-correction or removal targets; the older standalone grant-migration plan still requires a nonempty correction subset. Prepared-list access and ordinary preparation continuation retain their separate semantics.

Wizard current checkpoints use inner checkpoint schema2 with an ordinary
`book` role for every retained leveled spellbook member. Preparation is counted
separately from book membership; copying has no progression maximum. Cantrip,
list, level and preparation limits still require current exact sources. Raw
IDs, ordering, marks, item origins and play state remain preserved. Existing
schema1 prepared/known checkpoints retain their historical contracts. Audited
book roles survive genuine preparation/unprepare continuation without becoming
learning dates; retirement and source withdrawal retain their existing proof
and withholding boundaries. New book source bases additionally bind full local
class/subclass, effective profile and attained rule sources, independently of
mutable preparation selections; older basis recipes remain unchanged.

Current Wizard checkpoint and authenticated book qualification use the same strict
preparation interpretation: `P`, `PO`, `Prepared` and combined plus-separated marks
mean prepared; `O` and plain `Spellbook` alone do not. Explicit Boolean aliases
must agree with each other and with a positive preparation mark. Contradictory or
malformed observations remain unresolved and cannot manufacture free capacity.
The default historical eligibility recipe remains unchanged; current Wizard
interpretation is explicit, separately from persisted legacy source frames.
Effective editing and action controls use current ordinary ledger membership and
preparation, independently of feature-origin capacity contributions. Actual Edit
or advancement preparation changes synchronize each existing Boolean alias;
unchanged imported marks, missing aliases and unrelated rows remain preserved.

A separate explicit item-only book-observation correction can compose with the
whole current Wizard checkpoint. It requires a player-confirmed clarification
with an evidence note, independent removal confirmation, one unprepared erroneous
ordinary PHB Wizard book observation and its unique separate matching item spell.
The original must have no confirmed native choice/grant model or conflicting
authorization; prepared, fixed, item-owned and mapped feature-owned rows refuse.
Fresh item source/state qualification is mandatory. The distinct versioned plan
binds exact original class, spell, item and source-row digests, preserves the item
grant and original import/generation/audit history, and authenticates the removal
through the independent reserved producer and saved loader. This corrects an
unconfirmed observation without inventing learning or retirement custody. Existing
unsupported-unlinked removal and historical checkpoint recipes are unchanged.

Ordinary read annotation can expose a Wizard spellbook ritual only with a
current exact admitted PHB Wizard and attained Spellcasting owner, recognized
Ritual Casting rule text, authenticated usable book membership and current
ritual tag. An unprepared book ritual keeps its independent preparation state.
The annotation never writes raw ritual flags or issues a casting action.
Catalogue-only ritual badges say “Ritual tag.” A separately recognized current
Arcane Recovery rule exposes the rounded-up half-Wizard-level recovery budget
as read guidance, distinct from its use tracker. Registry templates, reset
recipes and actual spent state are unchanged; recovery remains table managed.
When imported Spellcasting omits its class-row field, only a unique exact verified
attained Wizard spine may supply implicit read ownership. Explicit conflicts,
duplicate rows or ambiguous attained owners withhold the rule. Raw feature fields
remain unchanged. Ritual metadata never supplies or restricts book admission;
casting guidance separately requires its qualified feature and usable membership.

Page descriptions remain reference material for item clauses. Mechanical item
benefits require their existing approved Systems sources, exact mapping and
activation/resource qualification; a page link or null charge fields do not
establish entitlement, free uses or stored spells. The Staff v1 variant and
explicit v2 casting/storage families require their own current declarations;
neither interprets arbitrary prose as an operation. Source acceptance alone does
not establish a complete character baseline, edit/advancement readiness or
equipment activation; those require genuine qualification of the actual item
and character sources and preserved state.

Numeric-authority consumers use the same full effective-value normalization,
transient mechanics, authenticated witnesses and projected-number binding as
ordinary reads without constructing display-only spell metrics, attack lists or
item actions. Source/state freshness, separate publication reservation,
conservative failures, CAS and saved-fact readback are unchanged. This separation
does not establish a measured speedup or an exercised save.

Shared spell metric presentation distinguishes unavailable/mismatched sources,
unsupported narrative or external metrics, declaration conflicts and absent
explicit no-roll declarations. Qualified spells whose metric cannot be interpreted
say "See spell rules"; their casting entitlement is separate. Supported target
and creature save instructions use only qualified owner metrics; save modifiers
such as advantage or penalties do not create another caster DC. Missing metadata
is never converted into a declaration of no roll, and historical header/text
values do not supply a fallback metric.

For a currently qualified explicitly linked feature, the shared feature presenter
shows current source rules without appending saved import prose to the active
feature. Saved wording remains unchanged in durable definitions/history;
it does not supply current rules. Qualified Arcane Recovery also shows
its current Wizard recovery budget beside the feature, separately from its use
tracker. Raw descriptions, history and spent state are not rewritten. Legacy
unqualified rendering and suppressed historical features retain their own paths.
Markdown sheets, including campaign-package sheets and nested feature components,
consume the same presented feature description. Raw saved descriptions cannot
override its current, unavailable or empty result. Package structured definitions,
imports and state retain their separate historical data unchanged.

Reconstructed characters carry `native_character_builder` source type and use
the shared effective native normalization and current source-authority path.
Reconstruction preserves historical descriptive rows and imported wording;
unqualified retained feature rows are mechanically suppressed independently of
the qualified species, language, ability and proficiency recipes. This history
does not switch a reconstructed character back to imported mechanics. Native
creation and reconstruction have different acquisition/input provenance, and
neither implies general automation of every feature's rules. The shared read
projection supports versioned source-owned values for the exact PHB Destroy
Undead and Sneak Attack families. It requires a currently qualified acquisition,
an explicit verified owning class row and current matching Systems contracts.
Sneak Attack looks up the owning Rogue level in the preserved twenty-row source
dice table. Destroy Undead selects the highest acquired, attained, qualified
member of its explicit same-facet family; it never grants a missing sibling.
Only that same-owner current presentation is combined. Acquisition rows, IDs,
imported descriptions, history and play state remain intact on advancement.
Sheet, Session, Combat and Markdown feature descriptions share the result.
The typed value is reference guidance, not automatic damage, turning, spending
or resource restoration. Numeric-only derivation does not construct this view.

Existing Systems records need a separately authorized narrow source-data update
before these values are available. Missing/malformed contracts or tables and
missing/ambiguous class ownership report unavailable values while retaining the
existing rules and historical rows. A wrong or unattained character association
still needs its own normal repair; this model does not correct it on read.
Other feature families and general class tables remain outside this initial
coverage. Homebrew replacements, resource-capacity recipes, multiclass rules
and Xianxia mechanics retain their existing paths. Legacy Artificer known-infusion selection
retains prose/name compatibility only until explicit typed recipe adoption. The
bounded adoption contract below separates known recipes from active assignments.

Native reconstruction can explicitly absorb a preexisting historical HP adjustment already included in the confirmed physical pool. The form binds the exact prior signed adjustment, removes only that continuing max_hp key, and records its original value and disposition in authenticated reconstruction choices/inputs. Other manual effects, raw progression events and play state remain owned by their existing paths. Without explicit complete confirmation the adjustment remains active. Derived HP continues to use the recipe, current Constitution and actual retained later gains; imported totals never supply formula authority.


Font of Magic and its exact PHB Sorcery Points child are citations of the same
managed Sorcery Points family. Complete current-source/class/attained proof must
validate every retained citation before reconstructing missing class ownership.
The pool retains one level-derived capacity and its historical current value;
both original feature rows and source citations remain intact. Unknown or
conflicting aliases cannot authorize the pool or silently disappear. Generic
unproved duplicate-owner refusals are unchanged.


Deterministic native feature attainment admits the pinned PHB convention of an
empty subclass-source UID field only inside the exact PHB owning subclass
feature, class, subclass short identity and library. Explicit other versions,
unresolved identities and ambiguous matches remain refused. An automatically
reached progression parent remains attained when its body offers elective
options; only unconditional edges establish additional attained children.
Count-bearing choices and optional-feature selections still require their own
authenticated choice custody. The display card's option groups do not remove
the parent entitlement or authorize the offered children. This source-only
repair does not by itself qualify retained resources, unknown homebrew,
character totals or a complete native reconstruction checkpoint.

Source Repair's feature-class page can associate one existing unowned,
source-backed scaling feature with its unique verified owning class row. The
registered current Systems contract and attained class level establish the
owner; names, imported prose and total character level do not. Review and Apply
use normal manager authorization, CSRF, a ten-minute signed review, fresh source
qualification and reserved publication checks. The action changes only the
existing row's `class_row_id`; it adds no acquisition, history or resource.
Unrelated qualified grants, choices, numeric values and resources must remain
unchanged. Conflicting ownership, unsupported sources and ambiguous class rows
need separate maintenance.

This exact association action can retain a missing legacy equipment-activation
marker only when all physical equipment identities match and the entire saved
play state remains exact. It does not migrate the marker or unblock ordinary
advancement. Publication preserves the original raw state tuple and revision,
and keeps imported history intact. A current feature projection may then derive
its typed value from its owning class and Systems. This maintenance action does
not prove a level-up, rest, gameplay action or historical feature acquisition.

Source Repair's missing managed resource page can restore one tracker for an
existing, already attained feature with an exact current Systems source and
existing verified class association. The shared registry member, current
class/subclass relationship and qualified formula inputs establish the maximum
and reset contract. The manager explicitly enters current remaining uses from
zero through that proven maximum. Names, prose and copied templates grant no
resource ownership. Existing or conflicting feature/member, template, state or
authorization identities refuse; this action does not repair class association.

The signed ten-minute Review binds the actor, exact committed definition/import
and state tuple, source/config snapshot, target and current amount. Apply
freshly rederives the same proposal before and within publication reservation.
It adds only the feature tracker reference, one resource template, one resource
state row and its target-only audited manager owner/reset authorization. Ordinary
source authority independently requires the current managed owner before
exposing capacity. No unrelated numeric claim or transition is renewed. Existing
valid equipment activation is required; legacy activation repair is separate.
Exact additive state preparation preserves all other resources, spent counts,
notes, equipment, spell storage, opaque state and import/history. Independent
reopen checks the saved delta and durable numeric witness. Uncertain outcomes
require inspection and never trigger automatic Apply replay. Source support
does not establish that a particular isolated or live restoration was performed.

## Retained Guardian Model And Artisan Choices

Native reconstruction offers an explicit exact-source Guardian branch choice and an independent historical-summary association. The original summary, including a mistaken level-15 citation, remains unchanged and inert. The existing reconstruction origin, independent audit recovery and current source checks authenticate the selection. Ordinary edit and advancement retain it; a later legitimate attained feature is not deduplicated against the inert summary. This does not add a rest/model-switch operation or change native creation's model authoring.

The supported TCE rule adapter checks exact class/subclass ownership and known rule signatures. Unselected or unproved Armor Model branches do not become unconditional feature grants. The same disposition covers source edges, progression display rows and direct native feature generation, including Perfected Armor's level-15 descendants. Only the authenticated attained collector adds selected mechanical members. Source withdrawal, rule changes, ambiguous owners or missing custody withhold dependent mechanics. Defensive Field retains its PB/long-rest resource ownership and class-level temporary-HP amount; current counts and existing temporary HP are unchanged.

Sheet, Session, Combat and Equipment API use one read projection for Arcane Armor and each hand. The armor consumer authenticates the exact activation overlay of the raw definition against the shared authority and its unchanged raw-state digest; a separately supplied original-definition digest must also match. A strict enabled observation, current activation identity and one uniquely source-qualified equipped suit establish wearing for display only. Explicit compatible main-hand, off-hand and two-handed weapon modes establish occupancy. Missing modes, conflicting owners, unknown activation and unsupported held-object placement remain unknown. Wondrous-item classification alone does not establish whether an item is worn or held; such items can leave hands unknown without preventing independently proved Defensive Field wearing. No hand placement or armor identity is saved by this projection.

Qualified Thunder Gauntlet alternatives use effective Strength or Intelligence plus qualified proficiency, with 1d8 thunder damage plus that ability modifier. Each hand has its own availability reason. Formula qualification does not assert current availability, a hit, an extra bonus-action attack, a rider application or a performed action. These rows are presentation only; historical attacks, exported source and update-safe definitions remain retained. Defensive Field availability is independent of hand occupancy. Use, temporary-HP replacement and doffing consequences remain table managed.

Reconstruction supports typed `anyArtisansTool` grants using the existing native AT option resolver and its bounded standard artisan fallback. Class `toolProficiencies` takes precedence by presence over display strings; an explicit empty list is authoritative and malformed typed values refuse. Class and background selections retain separate owners, require existing retained proficiencies and reject duplicate ownership. Typed artisan support does not supply Tool Expertise, resolve language discrepancies or assign infusions. Ordinary skill correction has the separate explicit reconstruction contract below. Source support alone does not establish a successful target reconstruction or current hand readiness.

## Explicit Source-Owned Skill Adoption

Native reconstruction can correct an existing canonical skill from `none` to `proficient` when a manager separately confirms its exact current ordinary source-choice slot and selects the same skill in that slot. Confirmation defaults to keeping the saved observation. Current source domain/count and unique-owner checks still apply; missing, malformed, duplicate, conflicting or stale confirmations refuse. This does not add skill rows, fixed grants, training, respec, expertise or half-proficiency adoption, and unknown levels are not promoted.

The complete original row, including its old bonus and other fields, remains inert history in `source.native_reconstruction_choices.skill_adoptions`. The normal qualified reconstruction pipeline derives the new bonus and dependent sheet values. Review shows the prior row, selected owner/slot and derived result. No browser field accepts a replacement bonus, row or proof. All existing import/history and exact play-state preservation remain in force.

Initial issuance checks the actual original row. Confirmed generation/audit recovery supplies independent adoption custody; serialized history is only a claim. Later reconstruction must carry that history unchanged with prior custody, and ordinary edits or advancement cannot remove, duplicate or rewrite it. A valid later expertise grant or changed derived bonus remains possible: the historical adoption does not freeze the current skill output. Current source withdrawal, changed slot contracts or missing custody withhold skill authority and remain visible for repair. Raw exports retain both the current observation and its original adoption history; Sheet, Session and Combat use ordinary qualified projections.

This support uses the existing manager reconstruction Review/Apply path and its authentication, CSRF, source reservation, signed review, CAS and durable publication checks. Source support alone does not establish a successful Character preview or authorize applying it. Independent unsupported source contracts can still prevent full reconstruction.

## Optional Class Weapon Proficiencies

The shared class weapon parser separates fixed strings from the closed source clause `{"optional": true, "proficiency": "firearms"}`. The clause alone does not grant Firearms. Manager reconstruction offers a separate explicit current decision to authorize that option and confirm its source conditions, or retain the existing observation unqualified. The choice is never initialized from equipment, an observed label or past use. Its separate input/group preserves ordinary positional proficiency choices. Current class metadata, submitted input, retained weapon observation and existing reconstruction proof/audit custody bind positive qualification. Independently qualified fixed grants such as Simple Weapons remain eligible, and separately supported feature/feat grants keep their own authority.

Positive optional qualification currently supports the exact TCE Artificer/Firearm Proficiency source relation. The enabled governing class feature must belong uniquely to the current class's level-one progression spine, with matching class/source/level metadata. Its current rules are shown in the form. The decision value and current weapons basis bind its exact identity, metadata and body; changed, unavailable, disabled or ambiguous rules cannot retain an old authorization or be silently reapproved by proof refresh. Other class/homebrew mappings need their own supported relation and remain unqualified. This uses semantic progression without constructing embedded display cards.

Malformed or unsupported structured weapon entries explicitly refuse reconstruction. The native extractor used by ordinary reads safely withholds that class's fixed weapon grants for an unsupported block rather than stringifying it or raising a source-shape error through the sheet. Missing, null and empty starting lists retain their empty behavior. Continuation preserves and revalidates optional decisions; original observations and play state do not change. This positive permission path is manager reconstruction only: native creation does not acquire an optional class weapon grant automatically or offer a new permission control.

Empty or whitespace-only weapon/tool grant strings, fixed grant names and choice labels are malformed and are rejected by the summary's shared parsing path. An explicit empty typed tool list is valid and continues to override display strings by presence.

## Conditional Parent Languages And Proficiency Summaries

A background language block can declare `{"ifAlreadyProficient": {"proficiency": "dwarvish", "replacement": {"any": 1}}}` (or `anyStandard: 1`). This is one language: explicitly gain the named language when not already known, or select a different language from the declared domain when the selected species independently supplies the prerequisite. Current totals and later acquired languages do not establish that origin. Unsupported chronology stays unresolved. Existing unconditional blocks retain their ordinary meaning; the app does not rewrite a catalog's unconditional declaration from prose or its title.

Native creation retains exact species/background references and ordered language choices only when the conditional rule is present. Native producer bases bind this acquisition record; ordinary edits and advancement preserve it. Current qualification rechecks its parent rules and branch, and proof refresh compares the record with the independently confirmed creation generation. Missing historical inputs are not reconstructed from totals. Reconstruction uses its explicit source-owned choices and existing custody, preserving all observed languages. A mandatory conditional grant/replacement is not exposed as an elective that can be declined or adopted without the prerequisite.

Current class Proficiencies summaries use the shared typed class grant and choice interpretation, including `toolProficiencies` precedence by presence and optional weapon clauses. Optional clauses are labeled with their permission/condition requirement, not presented as fixed grants. These summaries confer no additional entitlements. The legacy Artificer Infusions parent remains excluded from inert summary association because its prose is mechanically consumed; alternate action rows remain outside passive parent facets.

### Structured feature proficiencies and retained tracker associations

Shared feature tool choices admit `anyGamingSet` only with an exact positive count within the existing four-set domain. Reconstruction uses that same finite domain while retaining its existing choice grammar and stored decisions. Invalid counts, booleans and other proficiency categories refuse rather than becoming fixed tool names.

Class and subclass features can declare bounded fixed proficiency grants and ordinary native choice domains. Native creation and advancement accrue these grants through the shared typed parser. Reconstruction instead qualifies retained matching labels: a newly declared fixed grant does not silently add a missing armor, weapon, tool, language or skill observation. Unsupported or incomplete retained choices remain unresolved. Grants require current attained source/class/member ownership, not a feature title or copied prose.

A conditional tool declaration can grant a named tool or, when already proficient, one different artisan tool. Native acquisition uses prior proficiency inputs and retains its source-bound branch. Reconstruction requires explicit branch confirmation and an independently owned retained prerequisite source for a replacement; current totals alone do not establish acquisition chronology. Unresolved tool branches do not remove independent fixed armor or other-category grants.

The explicit `expertise: [{"allProficientTools": true}]` capability expands automatically over qualified tool proficiencies, including later acquired tools. It creates no per-tool player choices. Retrospective adoption preserves the complete original expertise observation, source/class identity and independent reconstruction audit custody. Later native acquisition uses the native advancement proof. Current read projection derives expertise only from an authenticated current capability and effective tool proficiency grants; it does not rewrite saved observations. Existing named and selected expertise continues separately.

Reconstruction can explicitly associate an existing physical resource tracker with an exact current managed member and class. The association retains the physical ID, complete prior feature/template/state observations, current count, notes and opaque state. Source/class/member identity, unique ownership, capacity and recovery are checked during preparation and repeated under the existing source reservation. Signed review, exact target freshness, CAS, audit recovery and exact-state preservation remain required. No alias is inferred from a label and no tracker is recreated or refilled. Replays retain the same physical ID while normal qualified formulas may scale its maximum.

For a retained feature replacement claim, the shared save receiver accepts a missing class-owner association only when the exact pending reconstruction is freshly rechecked and its complete resource-owner mappings match the actual prior and candidate. Only mapped feature owners become permitted annotations. Feature identity, Systems and page references, replacement claim and suppression state retain their independent exact-binding checks; changing them still requires the reviewed Source Repair relink path. Ordinary writes and unrelated proof families cannot supply these reconstruction annotations. The same checks run before publication and under the reserved save.

Initial association offers are bounded to supported fixed, class-level, total-half-level, proficiency-bonus and threshold formulas (and supported sums) proved from one current source-owned class. Ability-dependent formulas are withheld at this stage because qualified ability inputs are not yet available. A selected source branch in the same reconstruction form may qualify the offer without an earlier Apply. Unknown current observations remain unknown. Actual source declarations and Character adoption are separate operations; adding this support changes neither catalog rows nor Characters.

Conditional reconstruction chronology is bounded to confirmed starting class/species/background grants or strictly earlier attained feature grants of the same class. Later or unordered current grants do not establish the prerequisite; unsupported chronology remains unresolved.

Initial physical association also withholds an offer when a current item source modifies that pool capacity. An existing association with an active item bonus still targeting the canonical pool has unproved current capacity; it cannot silently fall back to a smaller base maximum. The saved physical tracker, count and capacity observations remain intact. This support does not retarget item bonuses.

## Simultaneous Feature Capacities And Known Recipes

The shared read-only feature projection supports registered TCE Magical Tinkering
and Infuse Item capacities. Current exact Systems declarations and a qualified
owning Artificer class are required. Tinkering uses the qualified current
Intelligence modifier, minimum one; Infuse Item uses the admitted original
Infused Items table at that class's level. These are maximum simultaneous-object
values, not spendable uses. Missing or changed source data remains unavailable.
No counter is initialized, clamped, refilled or authorized by this projection;
historical resource rows and their unresolved current-count semantics persist.

Reconstruction offers explicit typed adoption of the complete existing
source-linked Artificer recipe set. It preserves every original feature row and
records exact recipe/class ownership and, for Replicate Magic Item, an explicit
current source-table result reference. Result types are not inventory objects.
Current class progression, attained recipe prerequisites, enabled identities,
unique acquisitions and selected-result eligibility are rechecked. Distinct
Replicate results remain distinct choices; unsupported common-item alternatives
are not guessed. This bounded path does not add new recipes or replace the
native creation/advancement optional-feature choice engine.

Review exposes the knowledge-only delta. Existing reconstruction origin/audit
custody authenticates the exact retained frame; source reservation also covers
selected result references. Ordinary writes preserve adopted choices, and reads
require current source/class/feature qualification plus recovered custody.
Missing, malformed, removed or stale typed evidence never falls back to legacy
prose. The legacy compatibility parser remains for characters without typed
adoption. Typed result presentation uses the exact result reference rather than
parsing a parenthesized name.

Knowledge adoption does not migrate or reconcile active infusion assignments.
For typed adopters the legacy assignment replacement controls remain withheld;
existing inventory infusion observations/effects remain preserved. Equipment API
legacy assignment status is distinct from knowledge. The dedicated assignment
page/API below provides separate observation custody without feeding records into
the legacy name-based effect engine. Recipient/companion mechanics remain manual. The four passive parent-facet associations
remain explicit existing choices and are never applied automatically. Historical
infusion summaries and alternate action/custom item warnings are not silently
cleared by typed knowledge or capacity support. Catalog admission and genuine
character adoption/operational verification remain separate from source support.

Reconstruction separately offers three explicit historical associations: a retained
Artificer Infusions summary to its authenticated typed recipe set and Infuse Item
owner, and a retained STR Thunder Gauntlets action to the unique selected Guardian
Gauntlets owner, and an explicitly selected inert conversion summary to the
existing owned PHB Sorcerer Font of Magic feature and current Flexible Casting
rule. These finite source contracts preserve the entire original row;
they add no source link to that row, grant, tracker, attack or hand assignment.
Recipe/model confirmation is required in the same proposal or existing retained
frame. The form defaults these associations to unresolved; unresolved choices
retain their source warnings. With no adopted history, these checks impose no
additional feature-identity requirement on ordinary reads or writes.

Conversion-summary classification is an explicit history decision, never an
inferred match of a name, description, imported slug or character identity. Only
source-less descriptive bonus-action class-feature rows without mechanical
fields, trackers or competing owners are eligible for that choice. It requires
the exact current Font of Magic, Sorcery Points and Flexible Casting source
contracts and an unambiguous existing Sorcerer resource owner. Preparation binds
source and owner facts without issuing authority; the final association also
requires the actual qualified Flexible Casting provider and resource binding.
The retained row gains no source link, feature acquisition or conversion action.
The independent current rule remains the sole owner of the conversion controls.
Spent counters and advancing the same class do not change the history identity.
Existing saved rows stay unchanged until a genuine reviewed reconstruction
explicitly adopts the relation; installing source support alone hides nothing.

Relations carry exact prior-row, dependency and current-source identities through
the normal reconstruction proof, origin/audit recovery and publication transition.
Only a final dependency-qualified pass marks their source association verified.
Ordinary edits and advancement preserve the relations and historical rows; changes
require the exact reviewed reconstruction. Current source withdrawal or stale
custody withholds the association without restoring prose mechanics. Sheet,
Session and Combat omit these history-only rows from feature cards, counts and
action extraction. Their exact records, source associations and original prose
remain in reference data and exports. The current owner remains the sole producer
of current rules and per-hand alternatives. Malformed or ambiguous history stays
nonoperative and hidden; separate source-repair warnings remain visible. Writes
still reject malformed or removed adopted relations; presentation is not mutation
authority.

All DND feature surfaces share the same contribution-based visibility rule.
Qualified redundant parent summaries and positively replaced mechanics are also
omitted, as are earlier members of a qualified scaling family. Filtering happens
before nesting so a hidden historical container cannot remove contributing
children. Current parent rules do not append saved historical prose. Actual
passive, narrative and background features remain visible, as do spent or
temporarily unavailable abilities and potentially meaningful features needing
source repair. A missing authority or unavailable use alone is not proof that a
feature is redundant. Existing repair diagnostics remain independent of cards.

The full reader uses the shared feature-group presentation stage after ordinary
source/current-state projection. Lightweight section counts use the same
visibility decision. The pure stage accepts already-projected facts; it neither
creates authority nor changes raw definitions/state. A genuine pending-proof
observer can exercise this stage without pretending an unsaved candidate has
durable audit custody. Source acceptance and prospective display evidence do not
establish saved adoption.


## Prepared Ammunition And Triggered Item Reactions

An approved `item_capabilities` v4 source can own one physical prepared-ammunition
load. Its declaration binds an exact required class source, attunement, developed
choices, per-paid-slot damage and conditional save/on-hit rules. Bearer save DC
and ability modifiers are derived from current qualified inputs, never copied
from Ring storage or inferred from the slot used. An ambiguous or unqualified DC
stays unavailable. Qualified independent source rows, including authenticated
manual sources, participate alongside class rows; a missing metric cannot select
another owner by elimination. Save-condition durations are independent (for example,
being knocked prone does not inherit a deafness duration).

`item_prepared_ammunition` is optional physical-item state. Absence means unknown,
not empty. A manager can confirm a first empty, mundane or enchanted observation;
an enchanted observation needs its actual developed choice and already-paid slot
level and does not spend another slot. Existing observations cannot be overwritten.
Normal enchanted loading requires a known empty item, current class/attunement
ownership, explicit reload confirmation and one qualified available slot. Slot
spend and load are one sealed, reserved, revision-checked audited transaction.
Confirmed discharge requires the equipped, attuned item and removes the load
without another slot cost. Reads, rests, source/equipment changes and ordinary
writes preserve the complete ledger. A changed source or missing/malformed audit
checkpoint withholds actions while retaining the observation. Mundane reload,
replacement, unloading/refund, attack/hit resolution and target effects are not
automated. No ammunition count or current infusion is inferred.

The v3 noncasting action family also supports an explicit reaction preventing
only a triggering push, pull, prone or fall effect for the wearer or a willing
visible creature within the declared range. It spends one known physical use;
eligibility, reaction economy and the target's speed 0 until its next-turn start
remain table managed. This has a separate operation and confirmation from the
existing attack-d20 choice. Natural-wetlands movement and navigation reminders
are a separate conditional clause: they require wearing the item but do not
depend on the reaction's current uses, and supply no unconditional skill or
speed bonus. Source recovery is retained. Unknown uses stay unknown.

Sheet, Session and Combat share inventory presentation; action forms remain on
the existing editable views. Session Character and Combat do not gain editing
permission. Source support alone neither adopts an item nor records current
ammunition or uses; catalog changes,
character source associations and baseline facts remain separate operations.

The shared weapon-profile resolver uses a nonblank structured range string from
the current admitted item source in preference to the built-in base weapon's
range. It preserves that source text with outer whitespace removed; range is
descriptive metadata, not a new distance or targeting automation contract.
Missing, blank or nontext range metadata keeps the existing base fallback.
Character notes are not a range authority. The override applies to the copied
profile used by native creation and current derivation, including generated
attack variants and notes, without mutating source metadata or cached defaults.
Equipped/attuned bonus gating and saved character observations are unchanged.


## Player Artificer Assignment Records

The dedicated assignment page is linked from qualified Magical Tinkering and
Infuse Item capacity presentations through shared Sheet, Session and Combat
feature components. It uses existing session-edit permission, CSRF, source writer
reservation, exact revision/CAS and transactional audit. The API exposes the same
status and actions. Loading a character never initializes a baseline.

The optional version1 `artificer_assignments` state ledger keeps infusions and
tinkering independently unknown until explicit authenticated empty confirmation.
Confirmed empty differs from absent. Each active record identifies a physical
instance, recipient/location, chronological order, exact property or qualified
recipe/result, and attunement observation. Source/class/capacity and durable audit
custody are required. Stale observations are preserved and withheld, not cleared.
Legacy assignment observations block silent initialization. Historical counters,
known recipes and all unrelated state remain unchanged; ordinary saves, rests,
definition updates and reconstruction preserve the ledger.

The initial contract covers exact admitted TCE Tinkering rules and typed Enhanced
Defense, Homunculus Servant, Repeating Shot, Boots of the Winding Path, Armor of
Magical Strength, and Replicate Magic Item: Goggles of Night. Other recipes remain
known but unavailable to these controls. An inventory target must be one qualified
nonmagical physical item, not a catalog type or stack. External objects use stable
player-supplied tags and explicit observations; no inventory object is generated.
Known contradictory source types, size or magical status are rejected.

Infusion recording requires actual long-rest completion and touch. Tinkering needs
tools, action, touch and a Tiny nonmagical object. Messages are at most six seconds;
actual displayed text is at most25 words, distinct from a picture description.
At capacity, explicit confirmation identifies the exact oldest assignment to end
before the new one. Duplicate physical assignments and simultaneous use of one
known recipe are rejected. Tinkering can end by action/touch. Infusion endings may
record destruction or the documented expiry after the artificer's death. A campaign
may explicitly enable `allow_artificer_infusion_deactivation` in its committed
configuration, allowing an explicitly confirmed deactivation under that campaign
ruling. An absent or false setting does not allow it. The action binds and audits
the current configuration generation; changing the setting does not rewrite the
ledger or earlier events. Changed knowledge/source custody needs reconciliation.
Moving an active recipe below capacity without a supported ending is not inferred.

This is structured bookkeeping with manual effect resolution, explicitly stated
on the page. It does not create a homunculus, modify recipient inventory/stats or
attunement, initialize charges, or automatically apply bonuses, darkvision,
teleportation, ammunition or reactions. Historical resource counters never supply
occupancy or remaining uses. Unknown attunement stays unknown. Full typed effects,
recipient reconciliation and broader recipes require further support. Saving a
confirmed empty baseline is a separate character operation, not source adoption.


## Read derivation catalog ownership

Owned ordinary read phases may use private complete item/spell facts and a
separate read foundation to avoid copying every enabled catalog record during
normalization. Shared item/spell selectors, automatic preparation and numeric
qualification still use full source observations, exact ambiguity rules and
current authority. Selected ordinary records and derived character payloads
remain detached; no fact handle is persisted in a character or public cache.
Public creation, editing, reusable preparation and writes retain their ordinary
catalog contracts. Targeted/empty and unsupported read recipes retain legacy
construction. This optimization does not change source ownership, saved prose,
choices, resource counts, UNKNOWN behavior or qualification warnings.

## Qualified native continuation

Advancement reuses a uniquely qualified retained deterministic class feature
instead of generating another acquisition merely because its historical row
lacks a literal class association. Exact current publication, prior attainment
and unique owning-class evidence are required; ambiguous or conflicting rows
refuse. Stable feature IDs, choices and historical rows remain unchanged.
Different publications and acquisition points remain distinct. A proved inert
selected-subclass container is hidden through shared parent-summary presentation;
its source-owned members and selected profile remain visible.

Unchanged non-entitling item spell observations can pass from qualified prior
custody through prospective normalization using an in-memory retention carrier.
Exact prior/candidate/state/source frames, physical relation, source declaration,
observation/source rows and empty-grant migration edges are checked. This carrier
only preserves history: it never confirms prospective native grant custody,
permits casting, supplies current numeric values or becomes persisted proof.
Ordinary current readers and durable publication retain their existing checks.

Advancement restores qualified literal modifier history after rebuilding current
class spell output and before binding prospective authority. Missing historical
source rows are retained through the existing collision checks; competing class
or item owners still refuse. Historical rows do not supply new entitlements.

The Advanced Editor API has a manager-only reference-notes preview/save action
for additional notes and allies/organizations. It clones the current server
definition and updates only explicitly supplied text, without full editor
derivation or import restamping. Generation, state revision and review digests
bind the request; actor/source/complete delta and import checks repeat under
publication reservation. Unrelated definition values and exact state/import
bytes are preserved, and validation cannot normalize another play-state field.
A changed save records a notes audit; no-op review/save does not publish.

Reconstruction continuation keeps newly source-derived casting class rows when a flat advancement payload has no saved row family. Those current owner/level/lane facts remain subject to normal source and grant qualification. Complete prospective capacity transfers a prior prepared-list choice's active preparation only for an exact unchanged row with independently qualified prior ordinary/count/preparation facts; current eligibility and marks are checked again. A list-role label of available alone never authorizes a new preparation.
