"""Manager-only exact source repair and manual authorization preview."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping
from uuid import uuid4

from flask import abort, current_app, make_response, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

from .auth import campaign_scope_access_required, get_effective_campaign_systems_entry_visibility, get_repository
from .character_models import CharacterDefinition
from .character_reconciliation import CharacterPublicationConflict, PendingReviewedSourceProof
from .character_source_repair import (
    MANUAL_METRICS, MANUAL_TARGETS, SourceRepairError,
    add_manual_authorization, add_numeric_authorization, eligible_repair_targets,
    load_verified_manual_actions, load_verified_numeric_actions,
    manual_authorization_record, numeric_authorization_record, repair_definition,
)
from .character_source_authority import numeric_target_owner_digest
from .character_store import CharacterStateConflictError
from .character_update_apply import canonical_digest
from .csrf import CSRF_FIELD_NAME
from .committed_publication import CommittedSourceConflict, active
from .db import get_db


_SALT = "character-source-repair-review-v1"
_TTL = 600
_SYSTEMS_TYPES = ("item", "spell", "classfeature", "subclassfeature", "feat", "optionalfeature", "feature")
_FORM_FIELDS = frozenset({CSRF_FIELD_NAME, "intent", "action", "family", "target_id", "source", "metric", "target_kind", "confirm_value", "confirmed_score", "confirmed_fixed_bonus"})
_APPLY_FIELDS = frozenset({CSRF_FIELD_NAME, "intent", "review_token"})


def _token_serializer() -> URLSafeTimedSerializer:
    secret = current_app.secret_key
    if not secret:
        raise SourceRepairError("Manager review signing is unavailable.")
    return URLSafeTimedSerializer(secret, salt=_SALT)


def _one(name: str) -> str:
    values = request.form.getlist(name)
    if len(values) != 1:
        raise SourceRepairError("Review form is incomplete.")
    value = str(values[0]).strip()
    if len(value.encode("utf-8")) > 1600:
        raise SourceRepairError("Review form value is too long.")
    return value


def _sources(dependencies: Any, campaign_slug: str, campaign: object) -> tuple[dict[str, Any], ...]:
    page_records = tuple(dependencies.list_visible_character_page_records(campaign_slug, campaign))
    service = dependencies.get_systems_service()
    entries: list[object] = []
    for entry_type in _SYSTEMS_TYPES:
        entries.extend(dependencies.list_enabled_systems_entries(service, campaign_slug, entry_type))
    choices: list[dict[str, Any]] = []
    for entry in entries:
        key = str(getattr(entry, "entry_key", "") or "").strip()
        kind = str(getattr(entry, "entry_type", "") or "").strip().casefold()
        slug = str(getattr(entry, "slug", "") or "").strip()
        if not key or not slug or len(key.encode("utf-8")) > 512:
            continue
        if not dependencies.can_access_campaign_systems_entry(campaign_slug, slug):
            continue
        if kind == "item" and not dependencies.systems_item_is_approved(entry):
            continue
        family = "item" if kind == "item" else "spell" if kind == "spell" else "feature"
        choices.append({
            "family": family, "kind": "systems_entry", "value": key,
            "label": str(getattr(entry, "title", "") or key)[:160],
            "record": entry,
            "visibility": get_effective_campaign_systems_entry_visibility(campaign_slug, slug),
        })
    for record in page_records:
        ref = str(getattr(record, "page_ref", "") or "").strip()
        page = getattr(record, "page", None)
        section = str(getattr(page, "section", "") or "").strip()
        if not ref or len(ref.encode("utf-8")) > 512:
            continue
        if section == "Items":
            family = "item"
            option = dict(dependencies.build_campaign_page_character_option(record, default_kind="item") or {})
            allowed = dependencies.campaign_page_option_allowed(
                record, field_kind="campaign_page_item", campaign_option=option,
            )
        elif section == "Mechanics":
            family = "feature"
            option = dict(dependencies.build_campaign_page_character_option(record, default_kind="feature") or {})
            allowed = dependencies.campaign_page_option_allowed(
                record, field_kind="campaign_page_feature", campaign_option=option,
            )
        elif section == "Spells":
            family = "spell"
            option = None
            allowed = True
        else:
            continue
        if not allowed:
            continue
        choices.append({
            "family": family, "kind": "campaign_page", "value": ref,
            "label": str(getattr(page, "title", "") or ref)[:160],
            "record": record, "option": option,
        })
        if section == "Mechanics":
            # Current policy also permits an exact Mechanics page for spell
            # availability; this does not import arbitrary page effect fields.
            choices.append({
                "family": "spell", "kind": "campaign_page", "value": ref,
                "label": str(getattr(page, "title", "") or ref)[:160],
                "record": record, "option": None,
            })
    # Duplicate exact keys are a conflict. Catalog iteration order never chooses.
    counts: dict[tuple[str, str, str], int] = {}
    for choice in choices:
        identity = (choice["family"], choice["kind"], choice["value"])
        counts[identity] = counts.get(identity, 0) + 1
    return tuple(choice for choice in choices if counts[(choice["family"], choice["kind"], choice["value"])] == 1)


def _source_digest(choices: tuple[dict[str, Any], ...]) -> str:
    rows = []
    for choice in choices:
        record = choice["record"]
        rows.append({
            "family": choice["family"], "kind": choice["kind"],
            "value": choice["value"], "label": choice["label"],
            "metadata": dict(getattr(record, "metadata", {}) or {}),
            "body": str(getattr(record, "body_markdown", None) or getattr(record, "body", None) or ""),
            "updated_at": str(getattr(record, "updated_at", "") or ""),
            "section": str(getattr(getattr(record, "page", None), "section", "") or ""),
            "published": getattr(getattr(record, "page", None), "published", None),
            "reveal_after_session": getattr(getattr(record, "page", None), "reveal_after_session", None),
            "committed_revision": getattr(getattr(record, "page", None), "committed_revision", None),
            "committed_config_revision": getattr(getattr(record, "page", None), "committed_config_revision", None),
            "visibility": choice.get("visibility"),
            "option": choice.get("option"),
        })
    return canonical_digest(rows)


def _source_option(choice: Mapping[str, Any]) -> str:
    return canonical_digest({"family": choice["family"], "kind": choice["kind"], "value": choice["value"]})


def _authority(definition: Mapping[str, Any], state: Mapping[str, Any],
               dependencies: Any, campaign_slug: str, campaign: object,
               witnesses: tuple[Mapping[str, Any], ...],
               numeric_witnesses: tuple[Mapping[str, Any], ...] = (),
               *, state_revision: int):
    from .character_source_authority import build_reconciled_source_authority
    return build_reconciled_source_authority(
        definition=CharacterDefinition.from_dict(dict(definition)), state=dict(state),
        systems_service=dependencies.get_systems_service(),
        campaign_page_records=list(dependencies.list_visible_character_page_records(campaign_slug, campaign)),
        verified_manual_actions=tuple(witnesses),
        verified_numeric_actions=tuple(numeric_witnesses),
        state_revision=state_revision,
    )


def _status(authority: object, family: str, target_id: str) -> str:
    value = authority.status_for(family, target_id)
    return str(getattr(value, "value", value) or "")


def _grant_labels(authority: object) -> dict[tuple[str, str, str, str, str], str]:
    labels: dict[tuple[str, str, str, str, str], str] = {}
    for grant in authority.grants:
        try:
            payload = json.loads(grant.payload_json)
            field, value = next(iter(payload.items()))
            detail = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError, StopIteration):
            field, detail = grant.effect_id, "current source effect"
        if len(detail) > 240:
            detail = detail[:237] + "..."
        labels[grant.grant_id] = (
            f"{grant.kind.title()} {grant.instance_id} from {grant.source_key}: "
            f"{field.replace('_', ' ')} {detail}"
        )
    return labels


def _effect_delta(before: object, after: object) -> dict[str, list[str]]:
    previous = _grant_labels(before)
    current = _grant_labels(after)
    changed = {key for key in previous.keys() & current.keys() if previous[key] != current[key]}
    return {
        "gained": [current[key] for key in sorted((current.keys() - previous.keys()) | changed)],
        "lost": [previous[key] for key in sorted((previous.keys() - current.keys()) | changed)],
    }


def _repair_is_verified(authority: object, candidate: Mapping[str, Any], family: str, target_id: str) -> bool:
    if _status(authority, family, target_id) != "VERIFIED":
        return False
    if family != "spell":
        return True
    spells = list((candidate.get("spellcasting") or {}).get("spells") or [])
    matching = [row for row in spells if isinstance(row, dict) and str(row.get("id") or "").strip() == target_id]
    if len(matching) != 1:
        return False
    definition = CharacterDefinition.from_dict(dict(candidate))
    return authority.spell_status(matching[0], definition=definition) == "VERIFIED"


def _manual_targets(definition: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    spellcasting = definition.get("spellcasting") or {}
    if not isinstance(spellcasting, Mapping):
        return ()
    targets: list[dict[str, str]] = []
    for kind, key, field in (("spell", "spells", "id"), ("source_row", "source_rows", "source_row_id")):
        rows = spellcasting.get(key) or []
        if not isinstance(rows, list):
            continue
        counts: dict[str, int] = {}
        for row in rows:
            if isinstance(row, Mapping):
                identity = str(row.get(field) or "").strip()
                if identity:
                    counts[identity] = counts.get(identity, 0) + 1
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            identity = str(row.get(field) or "").strip()
            if identity and counts[identity] == 1 and len(identity.encode("utf-8")) <= 512:
                targets.append({"kind": kind, "id": identity,
                                "label": str(row.get("name") or row.get("title") or identity)[:160]})
    return tuple(targets)


def _numeric_values(definition: Mapping[str, Any], state: Mapping[str, Any]) -> dict[tuple[str, str, str], Any]:
    from .character_source_authority import numeric_target_values
    return numeric_target_values(CharacterDefinition.from_dict(dict(definition)), dict(state))


def _numeric_target_choices(definition: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    values = _numeric_values(definition, state)
    # A dictionary cannot represent duplicate owners. Reject those identities
    # before a manager can attest one arbitrary matching row.
    counts: dict[tuple[str, str, str], int] = {}
    for row in list(definition.get("skills") or []):
        if isinstance(row, Mapping) and str(row.get("name") or "").strip():
            key = ("proficiency", f"skills.{str(row['name']).strip().casefold()}", "grant")
            counts[key] = counts.get(key, 0) + 1
    for family, rows in dict(definition.get("proficiencies") or {}).items():
        for value in list(rows or []):
            if str(value or "").strip():
                key = ("proficiency", f"proficiencies.{family}.{str(value).strip().casefold()}", "grant")
                counts[key] = counts.get(key, 0) + 1
    for row in list(definition.get("resource_templates") or []):
        if isinstance(row, Mapping) and str(row.get("id") or "").strip():
            key = ("resource", f"resource:{str(row['id']).strip()}", "owner_reset")
            counts[key] = counts.get(key, 0) + 1
    for row in list(state.get("spell_slots") or []):
        if isinstance(row, Mapping) and str(row.get("slot_lane_id") or "").strip() and type(row.get("level")) is int:
            key = ("resource", f"spell_slot:{str(row['slot_lane_id']).strip()}:{row['level']}", "owner_reset")
            counts[key] = counts.get(key, 0) + 1
    for row in list(dict(state.get("hit_dice") or {}).get("pools") or []):
        if isinstance(row, Mapping) and type(row.get("faces")) is int:
            key = ("resource", f"hit_die:{row['faces']}", "owner_reset")
            counts[key] = counts.get(key, 0) + 1
    choices = []
    for key, value in sorted(values.items()):
        if key[0] in {"spell_metric", "spell_choice"} or value is None or counts.get(key, 1) != 1:
            continue
        kind, target_id, metric = key
        if len(target_id.encode("utf-8")) > 512:
            continue
        choices.append({"kind": kind, "id": target_id, "metric": metric,
                        "label": f"{target_id} ({metric})"})
    # Missing or unresolved ability inputs can be replaced by a separately
    # entered and explicitly confirmed base score.
    for key in ("str", "dex", "con", "int", "wis", "cha"):
        identity = ("field", f"stats.ability_scores.{key}.score", "base")
        if identity not in values:
            choices.append({"kind": identity[0], "id": identity[1], "metric": identity[2],
                            "label": f"{identity[1]} (confirm new base)"})
    return tuple(choices)


def _numeric_candidate(
    definition: Mapping[str, Any], state: Mapping[str, Any], *,
    target_kind: str, target_id: str, metric: str, action_id: str,
    confirmed_score: int | None = None, confirmed_fixed_bonus: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    choices = _numeric_target_choices(definition, state)
    if not any(row["kind"] == target_kind and row["id"] == target_id and row["metric"] == metric for row in choices):
        raise SourceRepairError("The selected numeric owner is missing or ambiguous.")
    candidate = deepcopy(dict(definition))
    if metric == "base":
        parts = target_id.split(".")
        if len(parts) != 4 or parts[:2] != ["stats", "ability_scores"] or parts[2] not in {"str", "dex", "con", "int", "wis", "cha"} or parts[3] != "score":
            raise SourceRepairError("Only an exact ability base can be confirmed here.")
        if (type(confirmed_score) is not int or not 0 <= confirmed_score <= 30
                or type(confirmed_fixed_bonus) is not int or not -30 <= confirmed_fixed_bonus <= 30):
            raise SourceRepairError("Enter a bounded confirmed base and fixed bonus.")
        stats = deepcopy(dict(candidate.get("stats") or {}))
        inputs = deepcopy(dict(stats.get("ability_inputs") or {}))
        if inputs.get("version") not in (None, 1):
            raise SourceRepairError("Ability input version needs separate repair.")
        scores = deepcopy(dict(inputs.get("scores") or {}))
        scores[parts[2]] = {
            "stage": "base", "score": confirmed_score,
            "fixed_bonus": confirmed_fixed_bonus,
            "provenance": "manager_confirmed",
        }
        stats["ability_inputs"] = {"version": 1, "scores": scores}
        candidate["stats"] = stats
    values = _numeric_values(candidate, state)
    key = (target_kind, target_id, metric)
    if key not in values or values[key] is None:
        raise SourceRepairError("The exact raw value is unavailable for attestation.")
    authorization = numeric_authorization_record(
        character_slug=str(candidate.get("character_slug") or ""),
        target_kind=target_kind, target_id=target_id, metric=metric,
        raw_value=values[key], action_id=action_id, provenance="manager",
        owner_digest=numeric_target_owner_digest(
            CharacterDefinition.from_dict(candidate), state, target_kind, target_id, metric),
    )
    return add_numeric_authorization(candidate, authorization), authorization


def _numeric_status_delta(before: object, after: object) -> list[dict[str, str]]:
    old = {row.path: row for row in (*before.field_statuses, *before.resource_statuses)}
    new = {row.path: row for row in (*after.field_statuses, *after.resource_statuses)}
    changed = []
    for path in sorted(old.keys() | new.keys()):
        left, right = old.get(path), new.get(path)
        if left is None or right is None or (left.status, left.effective) != (right.status, right.effective):
            changed.append({
                "path": path,
                "before": str(getattr(left, "status", "absent")),
                "after": str(getattr(right, "status", "absent")),
                "raw": str(getattr(right, "raw", None))[:240],
                "effective": str(getattr(right, "effective", None))[:240],
            })
    return changed


def _audit_seen(review_digest: str, campaign_slug: str, character_slug: str) -> bool:
    rows = get_db().execute(
        """SELECT metadata_json FROM auth_audit_log
           WHERE event_type = 'character_update_applied'
             AND campaign_slug = ? AND character_slug = ?""",
        (campaign_slug, character_slug),
    ).fetchall()
    import json
    for row in rows:
        try:
            if json.loads(row["metadata_json"] or "{}").get("review_digest") == review_digest:
                return True
        except (TypeError, ValueError):
            continue
    return False


def register_character_source_repair_route(app: Any, *, dependencies: Any) -> None:
    def blocked_response(campaign: Any, issues: tuple[dict[str, Any], ...]):
        response = make_response(render_template(
            "character_source_repair.html", campaign=campaign, character=None,
            manager_generation={"revision": None, "issues": issues,
                                "import_choice_required": any(
                                    issue.get("import_choice_required") for issue in issues)},
            blocked=True, active_nav="characters",
        ), 409)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def manager_issues(campaign_slug: str, character_slug: str) -> tuple[dict[str, Any], ...]:
        from .committed_character_publication import character_repairs

        try:
            rows = (issue for issue in character_repairs(campaign_slug)
                    if issue.get("character_slug") == character_slug)
            issues = []
            for issue in rows:
                reason = str(issue.get("reason") or "")
                mirror_drift = reason in {
                    "character_pair_mirror_missing_or_modified",
                    "character_pair_mirror_conflict",
                    "character_pair_mirror_unavailable",
                    "character_mirror_root_unsafe",
                    "unadmitted_file_only_draft",
                }
                issues.append({
                    "reason": reason,
                    "journal_kind": str(issue.get("journal_kind") or ""),
                    "journal_state": str(issue.get("journal_state") or ""),
                    "definition_mirror": str(issue.get("definition_mirror") or ""),
                    "import_mirror": str(issue.get("import_mirror") or ""),
                    "mirror_last_replay_state": str(issue.get("mirror_last_replay_state") or ""),
                    "affected_action": (
                        "repair_blocked_operation" if "journal" in reason else
                        "inspect_last_replay_status" if reason == "character_pair_last_replay_conflict" else
                        "resolve_mirror_or_import_choice" if mirror_drift else
                        "repair_committed_proof"
                    ),
                    "safe_retry": "inspect_and_refresh_before_retry",
                    "import_choice_required": mirror_drift,
                })
            return tuple(issues)
        except (CommittedSourceConflict, OSError, TypeError, ValueError):
            return ({"reason": "mirror_health_unavailable", "affected_action": "repair_committed_proof",
                     "safe_retry": "inspect_and_refresh_before_retry",
                     "import_choice_required": False},)

    def view(campaign_slug: str, character_slug: str):
        try:
            if not active():
                abort(404)
        except CommittedSourceConflict:
            abort(404)
        if not dependencies.can_manage_campaign_session(campaign_slug) or dependencies.get_current_auth_source() == "view_as":
            abort(403)
        actor = dependencies.get_authenticated_user()
        actor_id = getattr(actor, "id", None)
        if isinstance(actor_id, bool) or not isinstance(actor_id, int) or actor_id < 1:
            abort(403)
        blocked = False
        try:
            context = dependencies.load_character_apply_context(campaign_slug, character_slug)
        except (CommittedSourceConflict, OSError, TypeError, ValueError):
            context = None
            blocked = True
        if context is None:
            campaign = get_repository().get_campaign(campaign_slug)
            if campaign is None or not dependencies.is_dnd_5e_system(getattr(campaign, "system", "")):
                abort(404)
            issues = manager_issues(campaign_slug, character_slug)
            if not blocked and not issues:
                abort(404)
            return blocked_response(campaign, issues)
        campaign, record = context
        if not (dependencies.is_dnd_5e_system(getattr(campaign, "system", ""))
                and dependencies.is_dnd_5e_system(record.definition.system)):
            abort(404)

        issues = manager_issues(campaign_slug, character_slug)
        if any(issue.get("journal_kind") for issue in issues):
            return blocked_response(campaign, issues)
        manager_generation = {
            "revision": record.committed_revision,
            "issues": issues,
            "import_choice_required": any(
                issue.get("import_choice_required") for issue in issues
            ),
        }

        definition = dict(record.definition.to_dict())
        state = dict(record.state_record.state or {})
        choices = _sources(dependencies, campaign_slug, campaign)
        source_digest = _source_digest(choices)
        witnesses = load_verified_manual_actions(campaign_slug, character_slug)
        numeric_witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
        targets = eligible_repair_targets(definition)
        manual_targets = _manual_targets(definition)
        numeric_targets = _numeric_target_choices(definition, state)
        review = None
        outcome = None
        status_code = 200
        if request.method == "POST":
            try:
                intent = _one("intent")
                if intent == "apply":
                    if set(request.form) != _APPLY_FIELDS:
                        abort(400)
                    token = _one("review_token")
                    if len(token.encode("utf-8")) > 8192:
                        raise SourceRepairError("Review token is too large.")
                    try:
                        claims = _token_serializer().loads(token, max_age=_TTL)
                    except (BadSignature, SignatureExpired) as exc:
                        raise SourceRepairError("Review expired or changed. Refresh and review again.") from exc
                    if not isinstance(claims, dict) or claims.get("v") != 1 or claims.get("actor") != actor_id or claims.get("campaign") != campaign_slug or claims.get("character") != character_slug:
                        raise SourceRepairError("Review is for a different manager or Character.")
                    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                    if _audit_seen(digest, campaign_slug, character_slug):
                        if canonical_digest(definition) != claims.get("candidate_digest"):
                            raise SourceRepairError("This reviewed action was applied, but the Character changed again. Refresh before another action.")
                        display_choices = tuple({"family": choice["family"], "value": _source_option(choice),
                                                 "label": choice["label"], "identity": choice["value"]} for choice in choices)
                        response = make_response(render_template(
                            "character_source_repair.html", campaign=campaign,
                            character=record.definition, targets=targets,
                            manager_generation=manager_generation,
                            manual_targets=manual_targets, numeric_targets=numeric_targets,
                            sources=display_choices, metrics=sorted(MANUAL_METRICS),
                            review=None, outcome="This reviewed manager action was already applied and confirmed.",
                            active_nav="characters",
                        ), 200)
                        response.headers["Cache-Control"] = "private, no-store"
                        return response
                    if (claims.get("definition_digest") != canonical_digest(definition)
                            or claims.get("state_revision") != record.state_record.revision
                            or claims.get("state_digest") != canonical_digest(state)
                            or claims.get("import_digest") != canonical_digest(record.import_metadata.to_dict())
                            or claims.get("source_digest") != source_digest):
                        raise SourceRepairError("Character or source changed. Refresh and review again.")
                    action = claims.get("action")
                    if action == "relink":
                        selected = [choice for choice in choices if _source_option(choice) == claims.get("source") and choice["family"] == claims.get("family")]
                        if len(selected) != 1:
                            raise SourceRepairError("The exact source is no longer eligible.")
                        choice = selected[0]
                        candidate = repair_definition(
                            definition, family=choice["family"], target_id=claims.get("target_id"),
                            source_kind=choice["kind"], source_value=choice["value"],
                            source_record=choice["record"], campaign_option=choice.get("option"),
                        )
                        before_authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses, state_revision=record.state_record.revision)
                        after_authority = _authority(candidate, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses, state_revision=record.state_record.revision)
                        if not _repair_is_verified(after_authority, candidate, choice["family"], claims["target_id"]):
                            raise SourceRepairError("The selected source needs attention and cannot be applied.")
                        expected_delta = _effect_delta(before_authority, after_authority)
                        audit_action = "source_relink"
                        audit_record = None
                    elif action == "manual_authorize":
                        authorization = claims.get("authorization")
                        if not isinstance(authorization, dict) or authorization.get("character_slug") != character_slug:
                            raise SourceRepairError("Manual authorization changed.")
                        candidate = add_manual_authorization(definition, authorization)
                        expected_delta = {"manual": [f"{authorization['target_kind']}:{authorization['target_id']}:{authorization['metric']}"]}
                        audit_action = "manual_authorize"
                        audit_record = authorization
                    elif action == "numeric_attest":
                        authorization = claims.get("authorization")
                        if not isinstance(authorization, dict) or authorization.get("character_slug") != character_slug:
                            raise SourceRepairError("Numeric authorization changed.")
                        candidate, rebuilt = _numeric_candidate(
                            definition, state,
                            target_kind=authorization.get("target_kind"),
                            target_id=authorization.get("target_id"),
                            metric=authorization.get("metric"),
                            action_id=authorization.get("action_id"),
                            confirmed_score=claims.get("confirmed_score"),
                            confirmed_fixed_bonus=claims.get("confirmed_fixed_bonus"),
                        )
                        if rebuilt != authorization:
                            raise SourceRepairError("The confirmed value changed.")
                        before_authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses, state_revision=record.state_record.revision)
                        after_authority = _authority(candidate, state, dependencies, campaign_slug, campaign, witnesses, (*numeric_witnesses, authorization), state_revision=record.state_record.revision)
                        expected_delta = {
                            "gained": _effect_delta(before_authority, after_authority)["gained"],
                            "lost": _effect_delta(before_authority, after_authority)["lost"],
                            "statuses": _numeric_status_delta(before_authority, after_authority),
                        }
                        audit_action = "numeric_attest"
                        audit_record = None
                    else:
                        raise SourceRepairError("Unsupported manager action.")
                    if canonical_digest(candidate) != claims.get("candidate_digest") or expected_delta != claims.get("effect_delta"):
                        raise SourceRepairError("The reviewed effects changed. Refresh and review again.")
                    if _source_digest(_sources(dependencies, campaign_slug, campaign)) != source_digest:
                        raise SourceRepairError("Current source policy changed before apply. Refresh and review again.")
                    desired = CharacterDefinition.from_dict(candidate)
                    coordinator = dependencies.character_update_apply_engine.coordinator
                    authority_provider = coordinator.numeric_authority_provider
                    if not callable(authority_provider):
                        raise SourceRepairError("Current Character source authority is unavailable.")
                    reviewed_authority = authority_provider(record, desired)
                    if reviewed_authority is None:
                        raise SourceRepairError("Current Character source authority is unavailable.")

                    def refresh_review_basis() -> tuple[str, str]:
                        current_choices = _sources(dependencies, campaign_slug, campaign)
                        current_source_digest = _source_digest(current_choices)
                        if action == "relink":
                            current_selected = [row for row in current_choices
                                                if row["family"] == claims["family"]
                                                and _source_option(row) == claims["source"]]
                            if len(current_selected) != 1:
                                raise SourceRepairError("The exact source is no longer eligible.")
                            current_choice = current_selected[0]
                            current_candidate = repair_definition(
                                definition, family=current_choice["family"],
                                target_id=claims["target_id"],
                                source_kind=current_choice["kind"],
                                source_value=current_choice["value"],
                                source_record=current_choice["record"],
                                campaign_option=current_choice.get("option"),
                            )
                            current_before = _authority(
                                definition, state, dependencies, campaign_slug, campaign,
                                witnesses, numeric_witnesses,
                                state_revision=record.state_record.revision,
                            )
                            current_after = _authority(
                                current_candidate, state, dependencies, campaign_slug,
                                campaign, witnesses, numeric_witnesses,
                                state_revision=record.state_record.revision,
                            )
                            if not _repair_is_verified(current_after, current_candidate,
                                                       current_choice["family"], claims["target_id"]):
                                raise SourceRepairError("The selected source is no longer verified.")
                            current_delta = _effect_delta(current_before, current_after)
                        elif action == "manual_authorize":
                            current_candidate = add_manual_authorization(definition, authorization)
                            current_delta = expected_delta
                        else:
                            current_candidate, current_authorization = _numeric_candidate(
                                definition, state,
                                target_kind=authorization.get("target_kind"),
                                target_id=authorization.get("target_id"),
                                metric=authorization.get("metric"),
                                action_id=authorization.get("action_id"),
                                confirmed_score=claims.get("confirmed_score"),
                                confirmed_fixed_bonus=claims.get("confirmed_fixed_bonus"),
                            )
                            if current_authorization != authorization:
                                raise SourceRepairError("The confirmed value changed.")
                            current_before = _authority(
                                definition, state, dependencies, campaign_slug, campaign,
                                witnesses, numeric_witnesses,
                                state_revision=record.state_record.revision,
                            )
                            current_after = _authority(
                                current_candidate, state, dependencies, campaign_slug,
                                campaign, witnesses, (*numeric_witnesses, authorization),
                                state_revision=record.state_record.revision,
                            )
                            current_grants = _effect_delta(current_before, current_after)
                            current_delta = {**current_grants,
                                             "statuses": _numeric_status_delta(current_before, current_after)}
                        return current_source_digest, canonical_digest({
                            "candidate": current_candidate, "effect_delta": current_delta,
                        })

                    reviewed_basis = canonical_digest({
                        "candidate": candidate, "effect_delta": expected_delta,
                    })
                    reviewed_source_proof = PendingReviewedSourceProof.capture(
                        record, desired, state, reviewed_authority,
                        source_digest=source_digest, policy_digest=reviewed_basis,
                        refresh_review_basis=refresh_review_basis,
                    )
                    result = dependencies.character_update_apply_engine.coordinator.update(
                        record, desired, record.import_metadata, state,
                        expected_revision=record.state_record.revision,
                        updated_by_user_id=actor_id,
                        operation_kind="character_update_apply",
                        audit_event_type="character_update_applied",
                        audit_actor_user_id=actor_id,
                        audit_metadata={
                            "source": "character_source_repair",
                            "manager_action": audit_action,
                            "review_digest": digest,
                            "action_id": (
                                audit_record["action_id"] if audit_record else
                                authorization["action_id"] if audit_action == "numeric_attest" else
                                claims.get("action_id")
                            ),
                            "manual_authorization": audit_record,
                            "numeric_authorization": authorization if audit_action == "numeric_attest" else None,
                            "numeric_actor_id": actor_id if audit_action == "numeric_attest" else None,
                            "manual_actor_id": actor_id if audit_record else None,
                            "manual_authorized_at": claims.get("authorized_at") if audit_record else None,
                            "candidate_digest": claims["candidate_digest"],
                        },
                        reviewed_source_proof=reviewed_source_proof,
                    )
                    if (canonical_digest(result.definition.to_dict()) != claims["candidate_digest"]
                            or not _audit_seen(digest, campaign_slug, character_slug)):
                        outcome = "The update outcome needs inspection before another action."
                        status_code = 503
                    else:
                        outcome = "Manager action applied and confirmed by durable readback."
                    record = result
                elif intent == "review":
                    if set(request.form) - _FORM_FIELDS or any(len(request.form.getlist(key)) != 1 for key in request.form):
                        abort(400)
                    action = _one("action")
                    if action == "relink":
                        family = _one("family")
                        target_id = _one("target_id")
                        source_value = _one("source")
                        if not any(row["family"] == family and row["target_id"] == target_id for row in targets):
                            raise SourceRepairError("Choose one exact Character instance.")
                        selected = [choice for choice in choices if choice["family"] == family and _source_option(choice) == source_value]
                        if len(selected) != 1:
                            raise SourceRepairError("Choose one exact current source.")
                        choice = selected[0]
                        candidate = repair_definition(
                            definition, family=family, target_id=target_id,
                            source_kind=choice["kind"], source_value=choice["value"],
                            source_record=choice["record"], campaign_option=choice.get("option"),
                        )
                        before_authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses, state_revision=record.state_record.revision)
                        after_authority = _authority(candidate, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses, state_revision=record.state_record.revision)
                        if not _repair_is_verified(after_authority, candidate, family, target_id):
                            raise SourceRepairError("The selected source has a conflict or remains unverified. Choose another exact source.")
                        delta = _effect_delta(before_authority, after_authority)
                        extra = {"family": family, "target_id": target_id, "source": source_value, "action_id": uuid4().hex}
                        summary = f"Relink {family} {target_id} to {choice['label']}"
                    elif action == "manual_authorize":
                        kind, target_id, metric = _one("target_kind"), _one("target_id"), _one("metric")
                        if kind not in MANUAL_TARGETS or metric not in MANUAL_METRICS or not any(row["kind"] == kind and row["id"] == target_id for row in manual_targets):
                            raise SourceRepairError("Choose one exact manual metric target.")
                        authorization = manual_authorization_record(
                            character_slug=character_slug, target_kind=kind,
                            target_id=target_id, metric=metric,
                            action_id=uuid4().hex,
                            definition=record.definition,
                        )
                        candidate = add_manual_authorization(definition, authorization)
                        delta = {"manual": [f"{kind}:{target_id}:{metric}"]}
                        extra = {"authorization": authorization,
                                 "authorized_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                        summary = f"Authorize {metric.replace('_', ' ')} manually for {target_id}"
                    elif action == "numeric_attest":
                        if _one("confirm_value") != "yes":
                            raise SourceRepairError("Confirm the exact raw value or entered ability base before review.")
                        kind, target_id, metric = _one("target_kind"), _one("target_id"), _one("metric")
                        if not any(row["kind"] == kind and row["id"] == target_id and row["metric"] == metric for row in numeric_targets):
                            raise SourceRepairError("Choose one exact numeric owner.")
                        confirmed_score = confirmed_fixed_bonus = None
                        if metric == "base":
                            try:
                                confirmed_score = int(_one("confirmed_score"))
                                confirmed_fixed_bonus = int(_one("confirmed_fixed_bonus"))
                            except ValueError as exc:
                                raise SourceRepairError("Enter a confirmed base score and fixed bonus.") from exc
                        action_id = uuid4().hex
                        candidate, authorization = _numeric_candidate(
                            definition, state, target_kind=kind, target_id=target_id,
                            metric=metric, action_id=action_id,
                            confirmed_score=confirmed_score,
                            confirmed_fixed_bonus=confirmed_fixed_bonus,
                        )
                        before_authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses, state_revision=record.state_record.revision)
                        after_authority = _authority(candidate, state, dependencies, campaign_slug, campaign, witnesses, (*numeric_witnesses, authorization), state_revision=record.state_record.revision)
                        grant_delta = _effect_delta(before_authority, after_authority)
                        delta = {**grant_delta, "statuses": _numeric_status_delta(before_authority, after_authority)}
                        if not any(row["path"] == target_id and row["after"] in {"MANUAL", "VERIFIED"} for row in delta["statuses"]):
                            raise SourceRepairError("This attestation did not prove the selected current value.")
                        extra = {"authorization": authorization,
                                 "confirmed_score": confirmed_score,
                                 "confirmed_fixed_bonus": confirmed_fixed_bonus}
                        summary = f"Attest {target_id} ({metric}) from an independent manager confirmation"
                    else:
                        raise SourceRepairError("Unsupported manager action.")
                    if canonical_digest(candidate) == canonical_digest(definition):
                        raise SourceRepairError("The selected action does not change the Character.")
                    claims = {
                        "v": 1, "actor": actor_id, "campaign": campaign_slug, "character": character_slug,
                        "action": action, **extra,
                        "definition_digest": canonical_digest(definition),
                        "import_digest": canonical_digest(record.import_metadata.to_dict()),
                        "state_revision": record.state_record.revision,
                        "state_digest": canonical_digest(state),
                        "source_digest": source_digest,
                        "candidate_digest": canonical_digest(candidate),
                        "effect_delta": delta,
                    }
                    token = _token_serializer().dumps(claims)
                    if len(token.encode("utf-8")) > 8192:
                        raise SourceRepairError("Review is too large.")
                    review = {"summary": summary, "effects": delta, "token": token}
                else:
                    abort(400)
            except HTTPException:
                raise
            except (SourceRepairError, CharacterStateConflictError, CharacterPublicationConflict) as exc:
                outcome = str(exc) or "The reviewed Character changed. Refresh and review again."
                status_code = 409
            except Exception:
                outcome = "The manager action could not be confirmed. Inspect the Character before retrying."
                status_code = 503

        display_choices = tuple({"family": choice["family"], "value": _source_option(choice),
                                 "label": choice["label"], "identity": choice["value"]} for choice in choices)
        response = make_response(render_template(
            "character_source_repair.html", campaign=campaign, character=record.definition,
            manager_generation=manager_generation,
            targets=targets, manual_targets=manual_targets,
            numeric_targets=numeric_targets, sources=display_choices,
            metrics=sorted(MANUAL_METRICS), review=review,
            outcome=outcome, active_nav="characters",
        ), status_code)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/source-repair",
        endpoint="character_source_repair_view",
        view_func=campaign_scope_access_required("characters")(view),
        methods=("GET", "POST"),
    )
