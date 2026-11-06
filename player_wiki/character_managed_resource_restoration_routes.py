"""Manager Review/Apply for one missing already attained managed tracker."""
from __future__ import annotations

import hashlib
from uuid import uuid4

from flask import abort, current_app, make_response, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .auth import campaign_scope_access_required
from .character_feature_class_association_routes import _fresh_manager
from .character_managed_resource_restoration import prepare_managed_resource_restoration
from .character_reconciliation import CharacterPublicationError, PendingReviewedSourceProof
from .character_source_repair import SourceRepairError, load_verified_manual_actions, load_verified_numeric_actions
from .character_source_reads import SourceReadOwner, native_character_source_context
from .character_store import CharacterStateConflictError
from .character_update_apply import canonical_digest
from .committed_publication import CommittedSourceConflict, active
from .csrf import CSRF_FIELD_NAME
from .db import get_db

_SALT = "character-managed-resource-restoration-v1"
_TTL = 600


def evaluate_restoration_review(record, feature_id, current, actor_id, action_id, dependencies,
                                campaign, *, manager_facts, source_read_owner=None):
    from .character_source_repair_routes import _authority
    owned = source_read_owner is None
    owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
        get_db(), record.definition.campaign_slug, record.definition.character_slug)
    try:
        with native_character_source_context(record, source_read_owner=owner,
                systems_service=dependencies.get_systems_service(), campaign=campaign,
                purpose="managed-resource-restoration-review") as (phase, service, pages, _owner):
            if phase is None:
                raise SourceRepairError("Current source qualification is unavailable.")
            auth = manager_facts()
            campaign_slug, slug = record.definition.campaign_slug, record.definition.character_slug
            manual = load_verified_manual_actions(campaign_slug, slug, connection=phase.connection, strict=True)
            numeric = load_verified_numeric_actions(campaign_slug, slug, connection=phase.connection, strict=True)

            def authority(payload, state, pending):
                return _authority(payload, state, dependencies, campaign_slug, campaign, manual,
                    (*numeric, *pending), state_revision=record.state_record.revision, source_read_phase=phase)

            before = authority(record.definition.to_dict(), record.state_record.state, ())
            plan, desired, state, after = prepare_managed_resource_restoration(record, feature_id,
                current, actor_id, action_id, systems_service=service, pages=pages,
                before_authority=before, authority_builder=authority)
            feature = next(row for row in desired.features if row["id"] == feature_id)
            cls = next(row for row in desired.profile["classes"] if row["row_id"] == plan.class_row_id)
            refs = [feature["systems_ref"], cls["systems_ref"]]
            if cls.get("subclass_ref"):
                refs.append(cls["subclass_ref"])
            for ref in refs:
                if not dependencies.can_access_campaign_systems_entry(campaign_slug, ref["slug"], systems_service=service):
                    abort(403)
            policy = canonical_digest({"plan": plan.descriptor(), "manager": auth,
                "audit_prefix": phase.fact("audit"), "source_identity": phase.fact("identity"),
                "snapshot": after.source_snapshot_digest, "config_revision": phase.fact("config")[0]["revision"]})
        owner.checkpoint()
        return plan, desired, state, after, (plan.source_basis_digest, policy)
    finally:
        if owned:
            owner.close()


def register_managed_resource_restoration_route(app, *, dependencies):
    def view(campaign_slug, character_slug):
        from .character_source_repair_routes import _one, _ordinary_action_audit, _audit_outcome
        if not active():
            abort(404)
        if (not dependencies.can_manage_campaign_session(campaign_slug)
                or dependencies.get_current_auth_source() == "view_as"):
            abort(403)
        actor = dependencies.get_authenticated_user()
        if actor is None or type(actor.id) is not int:
            abort(403)
        _fresh_manager(dependencies, actor, campaign_slug)
        try:
            context = dependencies.load_character_apply_context(campaign_slug, character_slug)
        except (CommittedSourceConflict, OSError, TypeError, ValueError):
            abort(409)
        if context is None:
            abort(404)
        campaign, record = context
        if not dependencies.is_dnd_5e_system(record.definition.system):
            abort(404)
        coordinator = dependencies.character_update_apply_engine.coordinator
        serializer = URLSafeTimedSerializer(current_app.secret_key, salt=_SALT)
        review, outcome, status, attempted = None, "", 200, False

        def evaluate(feature, current, action_id, *, source_read_owner=None):
            return evaluate_restoration_review(record, feature, current, actor.id, action_id,
                dependencies, campaign, manager_facts=lambda: _fresh_manager(dependencies, actor, campaign_slug),
                source_read_owner=source_read_owner)

        try:
            if request.method == "POST":
                intent = _one("intent")
                fields = ({CSRF_FIELD_NAME, "intent", "feature_id", "current"} if intent == "review"
                          else {CSRF_FIELD_NAME, "intent", "review_token"} if intent == "apply" else set())
                if not fields or set(request.form) != fields:
                    raise SourceRepairError("The tracker restoration form is incomplete.")
                _one(CSRF_FIELD_NAME, max_bytes=256)
                if intent == "review":
                    raw = _one("current", max_bytes=10)
                    if not raw.isascii() or not raw.isdecimal():
                        raise SourceRepairError("Enter the explicit whole-number current amount.")
                    action_id = str(uuid4())
                    plan, desired, state, _view, basis = evaluate(_one("feature_id"), int(raw), action_id)
                    owner = SourceReadOwner.owned(get_db(), campaign_slug, character_slug)
                    try:
                        coordinator.check_source_repair_review(record, desired, record.import_metadata,
                            state, actor_id=actor.id, source_read_owner=owner, managed_resource_restoration=plan)
                        owner.checkpoint()
                    finally:
                        owner.close()
                    claims = {"v": 1, "actor": actor.id, "campaign": campaign_slug,
                        "character": character_slug, "action": "managed_resource_restoration",
                        "family": "feature", "target_id": plan.feature_id, "source": plan.resource_id,
                        "current": plan.current, "action_id": action_id,
                        "candidate_digest": canonical_digest(desired.to_dict()),
                        "source_digest": basis[0], "policy_digest": basis[1], "restoration": plan.descriptor()}
                    review = {"token": serializer.dumps(claims), "label": plan.template["label"],
                              "current": plan.current, "max": plan.template["max"]}
                else:
                    token = _one("review_token", max_bytes=16384)
                    claims = serializer.loads(token, max_age=_TTL)
                    if (type(claims) is not dict or claims.get("v") != 1
                            or claims.get("action") != "managed_resource_restoration"
                            or claims.get("actor") != actor.id or claims.get("campaign") != campaign_slug
                            or claims.get("character") != character_slug):
                        raise SourceRepairError("Review is for a different manager or Character.")
                    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                    seen, _current = _audit_outcome(token_digest, claims, record, claims.get("source_digest"))
                    if seen:
                        raise SourceRepairError("This Review already has a durable outcome. Inspect the Character before another action.")
                    plan, desired, state, authority, basis = evaluate(
                        claims.get("target_id"), claims.get("current"), claims.get("action_id"))
                    if (plan.descriptor() != claims.get("restoration")
                            or plan.resource_id != claims.get("source")
                            or canonical_digest(desired.to_dict()) != claims.get("candidate_digest")
                            or basis != (claims.get("source_digest"), claims.get("policy_digest"))):
                        raise SourceRepairError("The reviewed Character or source changed. Review again.")

                    def refreshed(*, source_read_owner=None):
                        current = evaluate(plan.feature_id, plan.current, plan.action_id,
                                           source_read_owner=source_read_owner)
                        if current[0].descriptor() != plan.descriptor() or current[4] != basis:
                            raise SourceRepairError("The reviewed tracker changed.")
                        return current

                    proof = PendingReviewedSourceProof.capture(record, desired, state, authority,
                        source_digest=basis[0], policy_digest=basis[1], managed_resource_restoration=plan,
                        refresh_review_basis=lambda **kwargs: refreshed(**kwargs)[4],
                        refresh_numeric_authority=lambda **kwargs: refreshed(**kwargs)[3])
                    audit = _ordinary_action_audit(claims, token_digest, actor_id=actor.id,
                        audit_action="numeric_attest", authorization=plan.authorization)
                    audit["managed_resource_restoration"] = plan.descriptor()
                    attempted = True
                    result = coordinator.update(record, desired, record.import_metadata, state,
                        expected_revision=record.state_record.revision, updated_by_user_id=actor.id,
                        operation_kind="character_update_apply", audit_event_type="character_update_applied",
                        audit_actor_user_id=actor.id, audit_metadata=audit, reviewed_source_proof=proof)
                    from .committed_character_publication import load_for_write
                    reopened = load_for_write(current_app.extensions["character_repository"], campaign_slug, character_slug)
                    if (reopened is None or reopened.committed_revision != result.committed_revision
                            or canonical_digest(reopened.definition.to_dict()) != plan.candidate_digest
                            or canonical_digest(reopened.import_metadata.to_dict()) != plan.prior_import_digest
                            or canonical_digest(reopened.state_record.state) != plan.desired_state_digest
                            or reopened.state_record.revision != record.state_record.revision + 1
                            or not _audit_outcome(token_digest, claims, reopened, basis[0])[1]):
                        raise RuntimeError("The saved tracker needs inspection before another action.")
                    # Independent durable witness loading, never the prospective marker.
                    with native_character_source_context(reopened, systems_service=dependencies.get_systems_service(),
                            campaign=campaign, purpose="managed-resource-restoration-readback") as (phase, _service, _pages, _owner):
                        if phase is None:
                            raise RuntimeError("The saved tracker source readback is unavailable.")
                        from .character_source_repair_routes import _authority
                        saved = _authority(reopened.definition.to_dict(), reopened.state_record.state,
                            dependencies, campaign_slug, campaign,
                            load_verified_manual_actions(campaign_slug, character_slug, connection=phase.connection, strict=True),
                            load_verified_numeric_actions(campaign_slug, character_slug, connection=phase.connection, strict=True),
                            state_revision=reopened.state_record.revision, source_read_phase=phase)
                        resource = saved.resource_status("resource", plan.resource_id)
                        if not resource.is_effective or resource.effective != plan.template:
                            raise RuntimeError("The saved tracker authority needs inspection before another action.")
                    record = reopened
                    outcome = "Missing tracker restored and reopened with the reviewed current amount."
        except (BadSignature, SignatureExpired):
            outcome, status = "Review expired or changed. Review again.", 409
        except (SourceRepairError, CharacterStateConflictError, CharacterPublicationError, ValueError) as exc:
            outcome, status = ("Apply needs durable outcome inspection before another action." if attempted else str(exc)), 409
        response = make_response(render_template("character_managed_resource_restoration.html",
            campaign=campaign, character=record.definition, review=review, outcome=outcome,
            features=[row for row in record.definition.features if type(row) is dict
                      and row.get("class_row_id") and row.get("systems_ref")
                      and not row.get("page_ref") and row.get("tracker_ref") in (None, "")],
            active_nav="characters"), status)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    app.add_url_rule("/campaigns/<campaign_slug>/characters/<character_slug>/source-repair/managed-resource",
        endpoint="character_managed_resource_restoration_view",
        view_func=campaign_scope_access_required("characters")(view), methods=("GET", "POST"))
