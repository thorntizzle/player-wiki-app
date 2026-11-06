"""Manager Review/Apply for a missing current feature-class association."""
from __future__ import annotations

import hashlib
from uuid import uuid4

from flask import abort, current_app, make_response, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .auth import campaign_scope_access_required
from .character_feature_class_association import prepare_feature_class_association
from .character_reconciliation import (
    CharacterPublicationError, PendingReviewedSourceProof,
)
from .character_source_repair import (
    SourceRepairError, load_verified_manual_actions,
    load_verified_numeric_actions,
)
from .character_source_reads import SourceReadOwner, native_character_source_context
from .character_store import CharacterStateConflictError
from .character_update_apply import canonical_digest
from .committed_publication import CommittedSourceConflict, active
from .csrf import CSRF_FIELD_NAME
from .db import get_db
from .systems_feature_values import family_spec


_SALT = "character-feature-class-association-v1"
_TTL = 600


def _fresh_manager(dependencies, actor, campaign_slug):
    """Reauthorize from durable account/membership facts, including in reserve."""
    if dependencies.get_current_auth_source() == "view_as":
        abort(403)
    store = current_app.extensions["auth_store"]
    user = store.get_user_by_id(actor.id)
    member = store.get_membership(actor.id, campaign_slug)
    if (user is None or not user.is_active or user.auth_version != actor.auth_version
            or user.is_admin != actor.is_admin
            or not (user.is_admin or (member is not None and member.role == "dm"))):
        abort(403)
    return {"actor": user.id, "auth_version": user.auth_version, "admin": user.is_admin,
            "membership": None if user.is_admin else [member.id, member.role, member.status,
                                                       member.updated_at.isoformat()]}


def evaluate_association_review(record, feature_id, class_row_id, actor_id, dependencies,
                                campaign, *, manager_facts, source_read_owner=None):
    """One genuine detached source phase; borrowed publication owners stay open."""
    from .character_source_repair_routes import _authority
    owned = source_read_owner is None
    owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
        get_db(), record.definition.campaign_slug, record.definition.character_slug)
    try:
        with native_character_source_context(record, source_read_owner=owner,
                systems_service=dependencies.get_systems_service(), campaign=campaign,
                purpose="feature-class-association-review") as (phase, service, _pages, _owner):
            if phase is None:
                raise SourceRepairError("Current source qualification is unavailable.")
            auth = manager_facts()
            campaign_slug, slug = record.definition.campaign_slug, record.definition.character_slug
            manual = load_verified_manual_actions(campaign_slug, slug, connection=phase.connection, strict=True)
            numeric = load_verified_numeric_actions(campaign_slug, slug, connection=phase.connection, strict=True)

            def authority(payload):
                return _authority(payload, record.state_record.state, dependencies, campaign_slug,
                    campaign, manual, numeric, state_revision=record.state_record.revision,
                    source_read_phase=phase)

            before = authority(record.definition.to_dict())
            plan, desired, after = prepare_feature_class_association(record, feature_id, class_row_id,
                actor_id, systems_service=service, before_authority=before,
                after_authority_builder=authority)
            features = [row for row in desired.features if row.get("id") == feature_id]
            classes = [row for row in desired.profile["classes"] if row.get("row_id") == class_row_id]
            for row in (*features, *classes):
                if not dependencies.can_access_campaign_systems_entry(campaign_slug,
                        row["systems_ref"]["slug"], systems_service=service):
                    abort(403)
            policy = canonical_digest({"plan": plan.descriptor(), "manager": auth,
                "audit_prefix": phase.fact("audit"),
                "source_identity": phase.fact("identity"),
                "snapshot": after.source_snapshot_digest,
                "config_revision": phase.fact("config")[0]["revision"]})
        owner.checkpoint()
        return plan, desired, after, (plan.source_basis_digest, policy)
    finally:
        if owned:
            owner.close()


def register_feature_class_association_route(app, *, dependencies):
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
        review, outcome, status = None, "", 200
        attempted = False

        def evaluate(feature, owner, *, source_read_owner=None):
            return evaluate_association_review(record, feature, owner, actor.id, dependencies,
                campaign, manager_facts=lambda: _fresh_manager(dependencies, actor, campaign_slug),
                source_read_owner=source_read_owner)

        try:
            if request.method == "POST":
                intent = _one("intent")
                fields = ({CSRF_FIELD_NAME, "intent", "feature_id", "class_row_id"} if intent == "review"
                          else {CSRF_FIELD_NAME, "intent", "review_token"} if intent == "apply" else set())
                if not fields or set(request.form) != fields:
                    raise SourceRepairError("The association form is incomplete.")
                # Enforce singular bounded CSRF input too; global CSRF validates its value.
                _one(CSRF_FIELD_NAME, max_bytes=256)
                if intent == "review":
                    plan, desired, _authority_view, basis = evaluate(_one("feature_id"), _one("class_row_id"))
                    owner = SourceReadOwner.owned(get_db(), campaign_slug, character_slug)
                    try:
                        coordinator.check_source_repair_review(record, desired, record.import_metadata,
                            record.state_record.state, actor_id=actor.id,
                            source_read_owner=owner, feature_class_association=plan)
                        owner.checkpoint()
                    finally:
                        owner.close()
                    claims = {"v": 1, "actor": actor.id, "campaign": campaign_slug,
                        "character": character_slug, "action": "feature_class_association",
                        "family": "feature", "target_id": plan.feature_id, "source": plan.class_row_id,
                        "action_id": str(uuid4()), "candidate_digest": canonical_digest(desired.to_dict()),
                        "source_digest": basis[0], "policy_digest": basis[1],
                        "association": plan.descriptor()}
                    review = {"token": serializer.dumps(claims), "feature_id": plan.feature_id,
                              "class_row_id": plan.class_row_id}
                else:
                    token = _one("review_token", max_bytes=8192)
                    claims = serializer.loads(token, max_age=_TTL)
                    if (type(claims) is not dict or claims.get("v") != 1
                            or claims.get("action") != "feature_class_association"
                            or claims.get("actor") != actor.id or claims.get("campaign") != campaign_slug
                            or claims.get("character") != character_slug):
                        raise SourceRepairError("Review is for a different manager or Character.")
                    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                    seen, _current = _audit_outcome(digest, claims, record, claims.get("source_digest"))
                    if seen:
                        raise SourceRepairError("This Review already has a durable outcome. Inspect the Character before another action.")
                    plan, desired, _authority_view, basis = evaluate(claims.get("target_id"), claims.get("source"))
                    if (plan.descriptor() != claims.get("association")
                            or canonical_digest(desired.to_dict()) != claims.get("candidate_digest")
                            or basis != (claims.get("source_digest"), claims.get("policy_digest"))):
                        raise SourceRepairError("The reviewed Character or source changed. Review again.")

                    def refresh(*, source_read_owner=None):
                        current_plan, _desired, _view, current_basis = evaluate(
                            plan.feature_id, plan.class_row_id, source_read_owner=source_read_owner)
                        if current_plan.descriptor() != plan.descriptor():
                            raise SourceRepairError("The reviewed association changed.")
                        return current_basis

                    owner = SourceReadOwner.owned(get_db(), campaign_slug, character_slug)
                    try:
                        authority = coordinator.source_repair_review_authority(record, desired,
                            record.state_record.state, actor_id=actor.id, source_read_owner=owner)
                        proof = PendingReviewedSourceProof.capture(record, desired, record.state_record.state,
                            authority, source_digest=basis[0], policy_digest=basis[1],
                            feature_class_association=plan, refresh_review_basis=refresh)
                        owner.checkpoint()
                    finally:
                        owner.close()
                    audit = _ordinary_action_audit(claims, digest, actor_id=actor.id,
                                                   audit_action="feature_class_association")
                    audit["feature_class_association"] = plan.descriptor()
                    attempted = True
                    result = coordinator.update(record, desired, record.import_metadata, record.state_record.state,
                        expected_revision=record.state_record.revision, updated_by_user_id=actor.id,
                        operation_kind="character_update_apply", audit_event_type="character_update_applied",
                        audit_actor_user_id=actor.id, audit_metadata=audit, reviewed_source_proof=proof)
                    from .committed_character_publication import load_for_write
                    reopened = load_for_write(current_app.extensions["character_repository"], campaign_slug, character_slug)
                    if (reopened is None or reopened.committed_revision != result.committed_revision
                            or canonical_digest(reopened.definition.to_dict()) != claims["candidate_digest"]
                            or canonical_digest(reopened.import_metadata.to_dict()) != plan.prior_import_digest
                            or canonical_digest(reopened.state_record.state) != plan.prior_state_digest
                            or reopened.state_record.revision != record.state_record.revision
                            or not _audit_outcome(digest, claims, reopened, basis[0])[1]):
                        raise RuntimeError("The saved association needs inspection before another action.")
                    record = reopened
                    outcome = "Class association saved and reopened. Existing play state and history were preserved."
        except (BadSignature, SignatureExpired):
            outcome, status = "Review expired or changed. Review again.", 409
        except (SourceRepairError, CharacterStateConflictError, CharacterPublicationError, ValueError) as exc:
            outcome, status = (("Apply needs durable outcome inspection before another action." if attempted else str(exc)), 409)
        # Unexpected/post-commit failures propagate to the ordinary error handler;
        # the caller must inspect durable state and never replay Apply automatically.
        response = make_response(render_template("character_feature_class_association.html",
            campaign=campaign, character=record.definition, review=review, outcome=outcome,
            features=[row for row in record.definition.features if type(row) is dict
                      and row.get("class_row_id") in (None, "")
                      and family_spec(dict(row.get("systems_ref") or {}).get("entry_key"))],
            classes=record.definition.profile.get("classes", []), active_nav="characters"), status)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    app.add_url_rule("/campaigns/<campaign_slug>/characters/<character_slug>/source-repair/class-association",
        endpoint="character_feature_class_association_view",
        view_func=campaign_scope_access_required("characters")(view), methods=("GET", "POST"))
