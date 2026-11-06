"""Reconstruction mode of the existing manager Character Update surface."""
from __future__ import annotations

from copy import deepcopy
import json

from flask import abort, current_app, render_template, request

from .character_source_repair import SourceRepairError


def _reconstruction_source_revision(campaign_slug, actor_id):
    """Cheap identities for already-validated immutable source, not its bodies."""
    from .committed_publication import active, read_snapshot
    from .db import get_db

    @read_snapshot
    def capture():
        connection = get_db()
        if not active(connection):
            raise SourceRepairError("Reconstruction source authority is no longer available.")
        heads = connection.execute(
            """SELECT c.object_kind,c.object_ref,c.revision,
                      g.primary_sha256,g.secondary_sha256,g.tombstone
               FROM committed_source_current c
               LEFT JOIN committed_source_generations g
                 USING(campaign_slug,object_kind,object_ref,revision)
               WHERE c.campaign_slug=? ORDER BY c.object_kind,c.object_ref""",
            (campaign_slug,),
        ).fetchall()
        admissions = connection.execute(
            """SELECT object_kind,object_ref,status,revision
               FROM committed_source_admission WHERE campaign_slug=?
               ORDER BY object_kind,object_ref""", (campaign_slug,),
        ).fetchall()
        systems = connection.execute(
            "SELECT token FROM systems_revision WHERE singleton=1"
        ).fetchone()
        visibility = connection.execute(
            """SELECT scope,visibility FROM campaign_visibility_settings
               WHERE campaign_slug=? ORDER BY scope""", (campaign_slug,),
        ).fetchall()
        actor = connection.execute(
            "SELECT status,is_admin,auth_version FROM users WHERE id=?", (actor_id,),
        ).fetchone()
        membership = connection.execute(
            """SELECT role,status FROM campaign_memberships
               WHERE user_id=? AND campaign_slug=?""", (actor_id, campaign_slug),
        ).fetchone()
        if systems is None:
            raise SourceRepairError("Reconstruction source revision is unavailable.")
        return (tuple(map(tuple, heads)), tuple(map(tuple, admissions)),
                systems[0], tuple(map(tuple, visibility)),
                tuple(actor) if actor is not None else None,
                tuple(membership) if membership is not None else None)

    return capture()


def _prepare_reconstruction_review_validation(dependencies, campaign_slug, actor_id):
    from .db import get_db
    connection = get_db()
    revision = _reconstruction_source_revision(campaign_slug, actor_id)

    def validate():
        # A retained read transaction could hide a concurrent commit. The issuer
        # invokes this after its exact Character evidence snapshot has closed.
        if get_db() is not connection or connection.in_transaction:
            raise SourceRepairError("Reconstruction needs a fresh source observation.")
        _require_current_manager(dependencies, campaign_slug, actor_id)
        if _reconstruction_source_revision(campaign_slug, actor_id) != revision:
            raise SourceRepairError("Character source changed during reconstruction review. Review again.")

    return validate


def _require_current_manager(dependencies, campaign_slug, actor_id):
    """Do not reuse request-cached membership/account facts under reservation."""
    from .db import get_db
    actor = dependencies.get_authenticated_user()
    if (type(actor_id) is not int or actor_id < 1
            or getattr(actor, "id", None) != actor_id
            or dependencies.get_current_auth_source() == "view_as"):
        raise SourceRepairError("Current manager access is required for reconstruction.")
    row = get_db().execute("SELECT status,is_admin,auth_version FROM users WHERE id=?", (actor_id,)).fetchone()
    if (row is None or row["status"] != "active"
            or row["auth_version"] != getattr(actor, "auth_version", None)
            or row["is_admin"] != int(bool(getattr(actor, "is_admin", False)))):
        raise SourceRepairError("The reconstruction actor is no longer active or authenticated.")
    if row["is_admin"] == 1:
        return
    membership = get_db().execute("SELECT role,status FROM campaign_memberships WHERE user_id=? AND campaign_slug=?",
                                  (actor_id, campaign_slug)).fetchone()
    if membership is None or membership["status"] != "active" or membership["role"] != "dm":
        raise SourceRepairError("Current campaign DM access is required for reconstruction.")


def semantic_rows(before, after, systems_service=None):
    from .character_update_planner import SemanticDiffRow, SemanticCategory, ChangeKind
    rows = []
    labels = {"profile": "Identity and class/source owners", "stats": "Ability inputs and derived sheet values",
              "skills": "Skills and expertise", "proficiencies": "Tools, languages and other proficiencies",
              "features": "Features and source choices", "spellcasting": "Spell ownership and prepared selections",
              "equipment_catalog": "Physical equipment owners", "resource_templates": "Resource owners and capacities",
              "attacks": "Attacks", "reference_notes": "Retained notes"}
    for name, label in labels.items():
        old, new = getattr(before, name), getattr(after, name)
        if old != new:
            rows.append(SemanticDiffRow(SemanticCategory.BUILD, name, label, ChangeKind.UPDATED,
                json.dumps(old, ensure_ascii=False, sort_keys=True), json.dumps(new, ensure_ascii=False, sort_keys=True)))
    old = dict(before.source.get("native_progression") or {}).get("hp_recipe")
    new = dict(after.source.get("native_progression") or {}).get("hp_recipe")
    if old != new:
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, "hp_recipe", "Exact accepted HP contribution recipe",
            ChangeKind.UPDATED, json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False)))
    unresolved = dict(after.source.get("native_reconstruction_choices") or {}).get("unresolved_proficiencies", [])
    if unresolved:
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, "unresolved_proficiencies", "Retained unresolved proficiency dependencies",
            ChangeKind.UPDATED, "Retained observations", ", ".join(unresolved) + ": retained without a source grant; dependent mechanics remain unqualified"))
    frame = dict(after.source.get("native_reconstruction_choices") or {})
    from .character_infusion_recipes import FRAME as RECIPE_FRAME
    old_recipes = dict(before.source.get("native_reconstruction_choices") or {}).get(RECIPE_FRAME)
    if frame.get(RECIPE_FRAME) != old_recipes:
        recipes = [{"feature_id": row["feature_id"], "class_row_id": row["class_row_id"],
                    "recipe": row["systems_ref"], "result_type": row["selected_item_ref"]}
                   for row in frame.get(RECIPE_FRAME, [])]
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, "artificer_recipe_choices", "Known recipe ownership (no active assignment or counter change)",
            ChangeKind.UPDATED, "Retained historical observations", json.dumps(recipes, ensure_ascii=False)))
    for family, identity in (("class_rows", "class_row_id"), ("source_rows", "source_row_id")):
        prior_rows = {row.get(identity): row for row in before.spellcasting.get(family, []) if isinstance(row, dict)}
        for row in after.spellcasting.get(family, []):
            if not isinstance(row, dict):
                continue
            old = prior_rows.get(row.get(identity), {})
            if old.get("spell_metric_provenance") != row.get("spell_metric_provenance"):
                rows.append(SemanticDiffRow(SemanticCategory.BUILD, f"formula_{family}_{row.get(identity)}",
                    f"Native spell formula ownership: {row.get(identity)}", ChangeKind.UPDATED,
                    json.dumps({key: old.get(key) for key in ("spell_attack_bonus", "spell_save_dc", "spell_metric_provenance")}, ensure_ascii=False),
                    "Current exact native owner and confirmed ability/proficiency recipe; item modifiers apply in current projection. "
                    + json.dumps({key: row.get(key) for key in ("spell_attack_bonus", "spell_save_dc", "spell_metric_provenance")}, ensure_ascii=False)))
    if frame.get("initial_unattained_features"):
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, "unattained_features", "Retained features without current attainment proof",
            ChangeKind.UPDATED, "Original descriptions and references preserved",
            ", ".join(row["name"] for row in frame["initial_unattained_features"]) + ": retained as unqualified history; no dependent grant issued"))
    inputs = dict(frame.get("inputs") or {})
    for ability in ("str", "dex", "con", "int", "wis", "cha"):
        layers = [f"{row.get('owner_id')}: +{row.get('amount')} ({dict(row.get('systems_ref') or {}).get('title', 'current source')})"
                  for row in dict(frame.get("ability_layers") or {}).get(ability, [])]
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, f"input_{ability}", f"{ability.upper()} original input and permanent owners",
            ChangeKind.UPDATED, "Original input not previously qualified by this reconstruction",
            f"{inputs.get('base_' + ability)} ({inputs.get('provenance_' + ability)}); " + "; ".join(layers)))
    owner_labels = {row.get("id"): row.get("name", row.get("id")) for row in after.features if isinstance(row, dict)}
    owner_labels.update({"class": "Class", "species": "Species", "background": "Background"})
    for group, values in dict(frame.get("choices") or {}).items():
        parts = group.split(":")
        label = f"{owner_labels.get(parts[1], parts[1])} — {parts[-1]}" if len(parts) >= 3 else group
        display = ["Unresolved; no dependent grant issued" if str(value).startswith("__unresolved_") else str(value) for value in values]
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, f"choice_{group}", f"Retained source choice: {label}",
            ChangeKind.UPDATED, "Prior content and history retained", ", ".join(display)))
    from .character_skill_adoptions import stored as skill_adoptions
    from .repository import normalize_lookup
    for adoption in skill_adoptions(after):
        current = next(row for row in after.skills if normalize_lookup(row.get("name")) == adoption["skill_key"])
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, "skill_adoption_" + adoption["skill_key"],
            "Explicit source-owned skill adoption: " + current["name"], ChangeKind.UPDATED,
            adoption["prior_row_json"], json.dumps({"current_skill": current,
                "source": adoption["systems_ref"], "owner": adoption["owner_id"],
                "skill_slot": adoption["position"] + 1}, ensure_ascii=False, sort_keys=True)
            + "; original observation retained in reconstruction history; current bonus derived from qualified inputs."))
    if frame.get("weapon_mappings"):
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, "weapon_mappings", "Explicit imported weapon label mappings",
            ChangeKind.UPDATED, json.dumps(frame.get("original_weapon_proficiencies"), ensure_ascii=False),
            "; ".join(", ".join(row["raw"]) + " → " + row["canonical"] + " (" + row["source_entry"] + ")"
                      for row in frame["weapon_mappings"])))
    if frame.get("item_source_mappings"):
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, "item_source_mappings", "Explicit same-physical-owner source authentication",
            ChangeKind.UPDATED, "Original physical IDs, page evidence and all inventory observations retained",
            json.dumps(frame["item_source_mappings"], ensure_ascii=False, sort_keys=True)
            + "; additive source metadata only; unsupported clauses remain pending, no activation, refill or new counter."))
    from .character_parent_facets import FRAME_KEY, stored_mappings, resolve_mapping
    if frame.get(FRAME_KEY):
        summaries = []
        for mapping in stored_mappings(after):
            facet = resolve_mapping(after, mapping, systems_service) if systems_service is not None else None
            summaries.append({**mapping, "current_rule": facet["description_markdown"] if facet else "Current facet unavailable"})
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, FRAME_KEY, "Explicit historical summary associations",
            ChangeKind.UPDATED, "Complete original feature rows and text retained",
            json.dumps(summaries, ensure_ascii=False, sort_keys=True)
            + "; references to current parent rules only; no additional HP, abilities, proficiencies, feats or resources."))
    from .character_armor_models import stored as armor_choices
    from .character_feature_history import stored as feature_history, FRAME as HISTORY_FRAME
    history = feature_history(after)
    if history:
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, HISTORY_FRAME, "Historical owner associations (no mechanics)",
            ChangeKind.UPDATED, "Exact original feature rows and play state retained",
            json.dumps(list(history), ensure_ascii=False, sort_keys=True)
            + "; current owner citations only; no additional grant, action, hand assignment or resource."))
    if armor_choices(after):
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, "armor_model_choices", "Explicit retained Armor Model",
            ChangeKind.UPDATED, "Historical model summary and all play observations retained",
            json.dumps(list(armor_choices(after)), ensure_ascii=False, sort_keys=True)
            + "; Guardian branch only; hand availability requires independent current equipment proof. No rest or model switch."))
    from .character_feature_proficiency_grants import automatic_history, conditional_history
    from .character_tracker_associations import stored as tracker_history
    for key, label, history in (("automatic_tool_expertise", "Automatic expertise adoption", automatic_history(after)),
            ("feature_proficiency_conditions", "Conditional proficiency acquisition", conditional_history(after)),
            ("tracker_associations", "Existing physical tracker association", tracker_history(after))):
        if history:
            rows.append(SemanticDiffRow(SemanticCategory.BUILD, key, label, ChangeKind.UPDATED,
                "Complete original observations retained in history",
                json.dumps(list(history), ensure_ascii=False, sort_keys=True)))
    rows.append(SemanticDiffRow(SemanticCategory.PLAY_STATE, "exact_state", "Entire existing play-state tuple",
        ChangeKind.UPDATED, "Current observations, opaque fields, absent/null values and prepared marks",
        "Exactly preserved; no initialization, refill, rest or clamp"))
    return tuple(rows)


def prepare_reconstruction_review(dependencies, campaign, record, inputs, actor_id):
    from .character_update_apply import CharacterUpdateRecompute, canonical_digest
    from .character_update_planner import (CharacterUpdatePlan, PlannedOperation, OperationKind,
        OperationStatus, PlanStatus, StateImpact, StateReconciliation, PLANNER_VERSION)
    from .character_update_preview_routes import _build_source_foundation, _source_digest, _policy_digest
    from .character_reconstruction import compose_reconstruction, bounded_inputs, retain_reconstruction_content
    from .character_reconstruction_authority import issue_reconstruction
    from .character_reconstruction_state import prepare_exact_reconstruction_state
    from .character_builder import normalize_definition_to_native_model
    from .committed_publication import active, config
    if not (dependencies.is_dnd_5e_system(getattr(campaign, "system", ""))
            and dependencies.is_dnd_5e_system(record.definition.system)):
        raise SourceRepairError("Native reconstruction requires a DND-5E Character and campaign.")
    if not active():
        raise SourceRepairError("Native reconstruction is unavailable until this installation has admitted committed source authority. No Character changes were made.")
    if (not dependencies.can_manage_campaign_session(campaign.slug)
            or dependencies.get_current_auth_source() == "view_as"
            or getattr(dependencies.get_authenticated_user(), "id", None) != actor_id):
        raise SourceRepairError("Current manager access is required for reconstruction.")
    inputs = bounded_inputs(inputs)
    validate_review_basis = _prepare_reconstruction_review_validation(
        dependencies, campaign.slug, actor_id,
    )
    _require_current_manager(dependencies, campaign.slug, actor_id)
    action = canonical_digest({"campaign": campaign.slug, "character": record.definition.character_slug,
        "actor": actor_id, "generation": record.committed_revision, "inputs": inputs})
    def refresh_proof():
        return prepare_current()[0]

    def _prepare_current():
        _require_current_manager(dependencies, campaign.slug, actor_id)
        current = dependencies.load_character_apply_context(campaign.slug, record.definition.character_slug)
        if current is None or not dependencies.can_manage_campaign_session(campaign.slug):
            raise SourceRepairError("The reconstruction target or manager access is unavailable.")
        current_campaign, current_record = current
        if not (dependencies.is_dnd_5e_system(getattr(current_campaign, "system", ""))
                and dependencies.is_dnd_5e_system(current_record.definition.system)):
            raise SourceRepairError("The reconstruction target is no longer a DND-5E Character.")
        if (dependencies.get_current_auth_source() == "view_as"
                or getattr(dependencies.get_authenticated_user(), "id", None) != actor_id):
            raise SourceRepairError("Manager access changed before reconstruction.")
        # Reconstruction needs authority inputs, not the ordinary update choice catalog.
        authority_page_records = tuple(
            dependencies.list_visible_character_page_records(campaign.slug, current_campaign))
        systems_service = dependencies.get_systems_service()
        candidate, _ = compose_reconstruction(record=current_record, inputs=inputs,
            systems_service=systems_service, campaign_page_records=list(authority_page_records))
        proof = issue_reconstruction(record=current_record, candidate=candidate,
            systems_service=systems_service, campaign_page_records=list(authority_page_records),
            actor_id=actor_id, action_id=action, input_digest=canonical_digest(inputs), refresh=refresh_proof)
        derived = normalize_definition_to_native_model(proof.candidate, mode="authoring",
            source_authority=proof.authority, systems_service=systems_service,
            campaign_page_records=list(authority_page_records))
        normalized = derived
        derived = retain_reconstruction_content(proof.candidate, derived)
        final = issue_reconstruction(record=current_record, candidate=derived,
            systems_service=systems_service, campaign_page_records=list(authority_page_records),
            actor_id=actor_id, action_id=action, input_digest=canonical_digest(inputs), refresh=refresh_proof)
        from .character_skill_adoptions import require_qualified_outputs
        require_qualified_outputs(current_record.definition, final, normalized, input_proof=proof,
            state=current_record.state_record.state, systems_service=systems_service,
            campaign_page_records=list(authority_page_records))
        prepare_exact_reconstruction_state(current_record, final.candidate, current_record.state_record.state, final.authority,
            mapping_proof=final, actor_id=actor_id)
        return final, current_campaign

    def prepare_current():
        from .character_reconstruction_inputs import reconstruction_input_scope
        # A refresh callback never inherits a prior preparation's retained
        # inputs. In particular the reservation creates its own fresh epoch.
        revision = _reconstruction_source_revision(campaign.slug, actor_id)
        with reconstruction_input_scope((campaign.slug, actor_id)):
            result = _prepare_current()
            _require_current_manager(dependencies, campaign.slug, actor_id)
            if _reconstruction_source_revision(campaign.slug, actor_id) != revision:
                raise SourceRepairError("Reconstruction source or access changed during preparation.")
            return result
    proof, current_campaign = prepare_current()
    foundation = _build_source_foundation(dependencies, campaign.slug, current_campaign, record)
    source_digest = _source_digest(foundation, proof.source_snapshot_digest)
    policy_digest = _policy_digest(foundation)
    rows = semantic_rows(record.definition, proof.candidate, dependencies.get_systems_service())
    plan_digest = canonical_digest({"operation": "native_reconstruction", "inputs": inputs,
        "definition": proof.candidate.to_dict(), "source": source_digest, "policy": policy_digest})
    plan = CharacterUpdatePlan(PLANNER_VERSION, record.definition.character_slug,
        str(record.committed_revision), PlanStatus.READY,
        (PlannedOperation(action, OperationKind.NATIVE_RECONSTRUCTION, PLANNER_VERSION, (), OperationStatus.READY),),
        StateImpact.PRESERVE_EXACT, StateReconciliation(), rows, plan_digest,
        proof.candidate.to_dict(), {"definition": proof.candidate.to_dict(), "state": deepcopy(record.state_record.state)})
    def refresh_basis():
        current, fresh_campaign = prepare_current()
        fresh_foundation = _build_source_foundation(dependencies, campaign.slug, fresh_campaign, record)
        return (_source_digest(fresh_foundation, current.source_snapshot_digest), _policy_digest(fresh_foundation))
    return CharacterUpdateRecompute(record, plan, ({"kind": "native_reconstruction", "inputs": inputs},),
        source_digest, policy_digest, canonical_digest({"inputs": inputs, "recipe": proof.origin["recipe_digest"]}),
            lambda saved: semantic_rows(record.definition, saved.definition, dependencies.get_systems_service()), proof.authority,
        config(campaign.slug)[0]["revision"], (), refresh_basis, proof,
        validate_review_basis)


def prepare_language_elective_review(dependencies, campaign, record, submitted, actor_id):
    """The existing Update publisher, without native foundation reconstruction."""
    from .character_language_electives import operation, issue_decision, OPERATION
    from .character_update_apply import CharacterUpdateRecompute, canonical_digest
    from .character_update_planner import (CharacterUpdatePlan, PlannedOperation, OperationKind,
        OperationStatus, PlanStatus, StateImpact, StateReconciliation, PLANNER_VERSION)
    from .character_update_preview_routes import _build_source_foundation, _source_digest, _policy_digest
    from .character_reconstruction_inputs import reconstruction_input_scope
    from .committed_publication import active, config
    submitted = operation(submitted)
    if not active() or not (dependencies.is_dnd_5e_system(campaign.system)
            and dependencies.is_dnd_5e_system(record.definition.system)):
        raise SourceRepairError("Language decisions require an admitted DND-5E Character.")
    _require_current_manager(dependencies, campaign.slug, actor_id)
    validate_review_basis = _prepare_reconstruction_review_validation(dependencies, campaign.slug, actor_id)
    def prepare_current():
        revision = _reconstruction_source_revision(campaign.slug, actor_id)
        with reconstruction_input_scope((campaign.slug, actor_id)):
            _require_current_manager(dependencies, campaign.slug, actor_id)
            loaded = dependencies.load_character_apply_context(campaign.slug, record.definition.character_slug)
            if loaded is None:
                raise SourceRepairError("The language decision target is unavailable.")
            current_campaign, current_record = loaded
            if (current_record.committed_revision != record.committed_revision
                    or current_record.definition.to_dict() != record.definition.to_dict()
                    or current_record.import_metadata.to_dict() != record.import_metadata.to_dict()
                    or current_record.state_record.revision != record.state_record.revision
                    or current_record.state_record.state != record.state_record.state):
                raise SourceRepairError("The exact language decision target changed.")
            proof = issue_decision(record=current_record, submitted=submitted, actor_id=actor_id,
                systems_service=dependencies.get_systems_service(),
                campaign_page_records=list(dependencies.list_visible_character_page_records(campaign.slug, current_campaign)),
                refresh=lambda: prepare_current()[0])
            _require_current_manager(dependencies, campaign.slug, actor_id)
            if _reconstruction_source_revision(campaign.slug, actor_id) != revision:
                raise SourceRepairError("Language source or manager access changed during review.")
            return proof, current_campaign
    proof, current_campaign = prepare_current()
    # An actual no-op is reachable only after authenticated current decision
    # resolution. It has no pending publication proof or duplicate receipt.
    candidate = proof.candidate if proof is not None else record.definition
    authority = proof.authority if proof is not None else None
    if proof is None:
        from .character_source_authority import build_reconciled_source_authority
        from .character_source_repair import load_verified_manual_actions, load_verified_numeric_actions
        authority = build_reconciled_source_authority(definition=candidate,
            state=record.state_record.state, state_revision=record.state_record.revision,
            systems_service=dependencies.get_systems_service(),
            campaign_page_records=list(dependencies.list_visible_character_page_records(campaign.slug, current_campaign)),
            verified_manual_actions=load_verified_manual_actions(campaign.slug, candidate.character_slug, strict=True),
            verified_numeric_actions=load_verified_numeric_actions(campaign.slug, candidate.character_slug, strict=True))
    foundation = _build_source_foundation(dependencies, campaign.slug, current_campaign, record)
    source_digest = _source_digest(foundation, authority.source_snapshot_digest)
    policy_digest = _policy_digest(foundation)
    rows = language_elective_semantic_rows(record.definition, candidate)
    plan_digest = canonical_digest({"operation": submitted, "definition": candidate.to_dict(),
        "source": source_digest, "policy": policy_digest})
    action = proof.decision_id if proof is not None else canonical_digest(submitted)
    plan = CharacterUpdatePlan(PLANNER_VERSION, candidate.character_slug, str(record.committed_revision),
        PlanStatus.READY if proof is not None else PlanStatus.NO_OP,
        (PlannedOperation(action, OperationKind.NATIVE_LANGUAGE_ELECTIVE_DECISION, PLANNER_VERSION, (),
            OperationStatus.READY if proof is not None else OperationStatus.ALREADY_SATISFIED),),
        StateImpact.PRESERVE_EXACT, StateReconciliation(), rows, plan_digest, candidate.to_dict(),
        {"definition": candidate.to_dict(), "state": deepcopy(record.state_record.state)})
    def refresh_basis():
        fresh, fresh_campaign = prepare_current()
        fresh_authority = fresh.authority if fresh is not None else authority
        fresh_foundation = _build_source_foundation(dependencies, campaign.slug, fresh_campaign, record)
        return _source_digest(fresh_foundation, fresh_authority.source_snapshot_digest), _policy_digest(fresh_foundation)
    return CharacterUpdateRecompute(record=record, plan=plan, operations=(submitted,),
        source_digest=source_digest, policy_digest=policy_digest,
        native_digest=canonical_digest({"operation": submitted, "outcomes": candidate.source.get("native_reconstruction_choices", {}).get("language_elective_outcomes", [])}),
        readback_semantic_rows=lambda saved: language_elective_semantic_rows(record.definition, saved.definition),
        reviewed_authority=authority, reviewed_config_revision=config(campaign.slug)[0]["revision"],
        refresh_review_basis=refresh_basis, validate_review_basis=validate_review_basis,
        pending_native_elective_decision=proof)


def language_elective_semantic_rows(before, after):
    from .character_language_electives import outcome_rows
    from .character_update_planner import SemanticDiffRow, SemanticCategory, ChangeKind
    old = {(row["owner_id"], row["position"]): row for row in outcome_rows(before)}
    rows = []
    for row in outcome_rows(after):
        key = row["owner_id"], row["position"]
        if old.get(key) == row:
            continue
        if row["outcome"] == "declined":
            label = "DM declined; no language grant"
        elif row["outcome"] == "adopted":
            label = "Adopt already observed " + row["selected_value"]
            if row["permission"] == "dm_exotic":
                label += "; DM permission for this exotic source-slot choice"
        else:
            label = "Selected " + row["selected_value"]
        rows.append(SemanticDiffRow(SemanticCategory.BUILD, f"language:{key[0]}:{key[1]}",
            f"Source-owned language elective: {key[0]} / {key[1] + 1}", ChangeKind.UPDATED,
            "Original observation and decision history retained", label))
    rows.append(SemanticDiffRow(SemanticCategory.BUILD, "qualified_languages", "Current source-qualified languages",
        ChangeKind.UPDATED, ", ".join(before.proficiencies.get("languages", [])),
        ", ".join(after.proficiencies.get("languages", []))))
    rows.append(SemanticDiffRow(SemanticCategory.PLAY_STATE, "exact_state", "Complete current play state",
        ChangeKind.UPDATED, "Current observations", "Exactly preserved; no initialization or refill"))
    return tuple(rows)


def reconstruction_view(dependencies, campaign_slug, character_slug, *, preview_only):
    from .character_reconstruction import reconstruction_context, bounded_inputs, STATIC_FIELDS, KEYS
    from .character_update_preview_routes import _project_plan
    from .committed_publication import active
    # The ordinary read loader may initialize legacy non-DND state. The
    # existing apply-context loader is visible, complete and noninitializing.
    loaded = dependencies.load_character_apply_context(campaign_slug, character_slug)
    if loaded is None:
        abort(404)
    campaign, record = loaded
    if not (dependencies.is_dnd_5e_system(campaign.system) and dependencies.is_dnd_5e_system(record.definition.system)):
        abort(400)
    error, review, status = None, None, 200
    language_fields = []
    values = {}
    context = None
    available = active()
    try:
        if not available:
            raise SourceRepairError("Native reconstruction is unavailable until this installation has admitted committed source authority. Existing Character data is unchanged.")
        service = dependencies.get_systems_service()
        pages = dependencies.list_builder_campaign_page_records(campaign_slug, campaign)
        from .character_language_electives import decision_fields, form_operation
        language_fields = decision_fields(record.definition, service)
        language_intent = request.method == "POST" and request.form.get("intent") == "review_languages"
        if request.method == "POST":
            from .csrf import CSRF_FIELD_NAME
            if preview_only or not dependencies.can_manage_campaign_session(campaign_slug):
                abort(403)
            if any(len(request.form.getlist(key)) != 1 for key in request.form):
                abort(400)
            if request.form.get("intent") not in {"review", "review_languages"}:
                abort(400)
            raw_values = {key: value for key, value in request.form.items()
                          if key not in {CSRF_FIELD_NAME, "mode", "intent"}}
            values = raw_values if language_intent else bounded_inputs(raw_values)
        context = reconstruction_context(record.definition, service, pages, values, state=record.state_record.state)
        if request.method == "GET":
            # This default records no association. The generic template reads
            # values rather than field.selected; new mappings stay explicit.
            from .character_parent_facets import UNRESOLVED
            for section in context["choice_sections"]:
                for field in section["fields"]:
                    if field.get("kind") in {"parent_facet", "armor_model", "recipe_ownership", "recipe_result", "feature_history"}:
                        values.setdefault(field["name"], field["options"][0]["value"])
        if request.method == "POST":
            actor_id = getattr(dependencies.get_authenticated_user(), "id", None)
            recompute = (prepare_language_elective_review(dependencies, campaign, record,
                         form_operation(values, language_fields), actor_id) if language_intent else
                         prepare_reconstruction_review(dependencies, campaign, record, values, actor_id))
            review = _project_plan(recompute.plan)
            review["review_token"] = dependencies.character_update_apply_engine.issue_review(
                recompute, actor_user_id=actor_id).token
    except (SourceRepairError, ValueError) as exc:
        error, status = str(exc), 400
    return render_template("character_reconstruction.html", campaign=campaign, character=record.definition,
        reconstruction=context, values=values, keys=KEYS, error=error, review=review,
        language_elective_fields=language_fields,
        available=available, preview_only=preview_only, active_nav="characters"), status
