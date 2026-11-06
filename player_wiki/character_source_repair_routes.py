"""Manager-only exact source repair and manual authorization preview."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping
from uuid import uuid4

from flask import abort, current_app, make_response, render_template, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import BadRequest, HTTPException

from .auth import campaign_scope_access_required, get_effective_campaign_systems_entry_visibility, get_repository
from .character_models import CharacterDefinition
from .character_equipment_activation import ActivationPrerequisiteError, require_update_activation
from .character_service import CharacterStateValidationError
from .character_reconciliation import CharacterPublicationConflict, CharacterPublicationError, PendingReviewedSourceProof
from .character_source_repair import (
    MANUAL_METRICS, MANUAL_TARGETS, SourceRepairError,
    action_witness_comparison, add_manual_authorization, add_numeric_authorization, eligible_repair_targets,
    load_verified_manual_actions, load_verified_numeric_actions,
    manual_authorization_record, numeric_authorization_record, repair_definition,
)
from .character_source_authority import numeric_target_owner_digest
from .character_store import CharacterStateConflictError
from .character_update_apply import canonical_digest
from .csrf import CSRF_FIELD_NAME
from .committed_publication import CommittedSourceConflict, active
from .db import get_db, SourceReadConnectionFatal
from .item_spell_support import parse_item_spell_support


_SALT = "character-source-repair-review-v1"
_TTL = 600
_SYSTEMS_TYPES = ("item", "spell", "classfeature", "subclassfeature", "feat", "optionalfeature", "feature")
_FORM_FIELDS = frozenset({CSRF_FIELD_NAME, "intent", "action", "family", "target_id", "source", "metric", "target_kind", "confirm_value", "confirmed_score", "confirmed_fixed_bonus", "confirmed_skill_level", "spell_origin_mode", "automatic_spell_ids", "remove_spell_id", "confirm_spell_removal", "confirm_current_spells", "item_only_spell_id", "item_only_grant_id", "confirm_item_only", "item_only_evidence"})
_APPLY_FIELDS = frozenset({CSRF_FIELD_NAME, "intent", "review_token"})
_SKILL_LEVELS = ("none", "half_proficient", "proficient", "expertise")
_SKILL_PASSIVES = {"investigation": "passive_investigation", "insight": "passive_insight", "perception": "passive_perception"}


def _ordinary_action_audit(claims, review_digest, *, actor_id, audit_action,
                           audit_record=None, authorization=None, authorization_batch=()):
    """Use the same ordinary action payload for Review bounds and actual Apply."""
    return {
        "source": "character_source_repair",
        "manager_action": audit_action,
        "review_digest": review_digest,
        "action_id": (audit_record["action_id"] if audit_record else
                      authorization["action_id"] if audit_action == "numeric_attest" else
                      claims.get("action_id")),
        "manual_authorization": audit_record,
        "numeric_authorization": authorization if audit_action == "numeric_attest" else None,
        "numeric_authorizations": list(authorization_batch) if (
            audit_action == "numeric_attest" and claims.get("confirmed_skill_level") is not None
        ) else None,
        "native_requalification": None,
        "confirmed_skill_level": claims.get("confirmed_skill_level"),
        "numeric_actor_id": actor_id if audit_action == "numeric_attest" else None,
        "manual_actor_id": actor_id if audit_record else None,
        "manual_authorized_at": claims.get("authorized_at") if audit_record else None,
        "candidate_digest": claims["candidate_digest"],
        "review_action": claims["action"],
        "review_family": claims.get("family"),
        "review_target_id": claims.get("target_id"),
        "review_source": claims.get("source"),
        "review_source_digest": claims["source_digest"],
        **({"same_physical_mapping": claims["same_physical_mapping"]} if claims.get("same_physical_mapping") is not None else {}),
    }

def _malformed_item_spell_target(choice: Mapping[str, Any]) -> bool:
    if choice.get("family") != "item" or choice.get("kind") != "systems_entry":
        return False
    record = choice.get("record")
    metadata = dict(getattr(record, "metadata", {}) or {})
    body = dict(getattr(record, "body", {}) or {})
    for blocks in (metadata.get("spell_support"), body.get("spell_support")):
        if blocks in (None, "", [], {}):
            continue
        parsed = parse_item_spell_support(blocks)
        if parsed.diagnostics or any(row.invalid for row in parsed.records):
            return True
    return False


def _require_repairable_item_target(choice: Mapping[str, Any]) -> None:
    if _malformed_item_spell_target(choice):
        raise SourceRepairError("That item spell rule needs repair before relinking a Character.")


def _retire_relinked_item_claims(before: Mapping[str, Any], after: dict[str, Any],
                                target_id: str) -> dict[str, Any]:
    """Drop claims owned by the old exact item source before review and apply."""
    old_rows = [row for row in before.get("equipment_catalog") or []
                if isinstance(row, dict) and row.get("id") == target_id]
    new_rows = [row for row in after.get("equipment_catalog") or []
                if isinstance(row, dict) and row.get("id") == target_id]
    if len(old_rows) != 1 or len(new_rows) != 1:
        raise SourceRepairError("The item owner identity needs manager repair.")
    old_ref = old_rows[0].get("systems_ref")
    if old_ref == new_rows[0].get("systems_ref"):
        return after
    if not isinstance(old_ref, dict) or not old_ref:
        return after
    from .character_builder_equipment import _resolve_item_support_metadata
    catalog = current_app.extensions["systems_service"]
    from .character_assets import build_character_item_catalog
    item_catalog = build_character_item_catalog(
        catalog, current_app.extensions["campaign_page_store"],
        str(before.get("campaign_slug") or ""),
    )
    metadata = _resolve_item_support_metadata(old_rows[0], item_catalog)
    parsed = parse_item_spell_support(metadata.get("spell_support"))
    if parsed.diagnostics or any(row.invalid for row in parsed.records):
        raise SourceRepairError("The old item spell source needs manager repair.")
    source_ids = {row.source_row_id for row in parsed.records if row.source_row_id}
    source_ids.update(source_id for _, source_id, _, _ in parsed.source_declarations
                      if source_id)
    compatible = set()
    for row in after.get("equipment_catalog") or []:
        if isinstance(row, dict) and row.get("id") != target_id \
                and row.get("systems_ref") == old_ref:
            compatible.add(str(row.get("id") or ""))
    if "" in compatible:
        raise SourceRepairError("The surviving item owner identity needs manager repair.")
    result = deepcopy(after)
    for item in result.get("equipment_catalog") or []:
        if isinstance(item, dict) and item.get("id") == target_id:
            item["is_attuned"] = False
            item["charges_current"] = None
            item["charges_max"] = None
    spellcasting = dict(result.get("spellcasting") or {})
    kept = []
    for raw in spellcasting.get("spells") or []:
        if not isinstance(raw, dict):
            kept.append(raw)
            continue
        row = dict(raw)
        source_id = str(row.get("spell_source_row_id") or "").strip()
        item_spell = (row.get("spell_grant_origin") == "item_effect"
                      or row.get("spell_source_row_kind") == "item")
        owners = row.get("item_owner_ids")
        if not item_spell or (source_id not in source_ids
                              and not (isinstance(owners, list) and target_id in owners)):
            kept.append(row)
            continue
        if not isinstance(owners, list) or not owners:
            raise SourceRepairError("Legacy item spell ownership needs manager repair.")
        if any(owner != target_id and owner not in compatible for owner in owners):
            raise SourceRepairError("Item spell owner identity needs manager repair.")
        remaining = [owner for owner in owners if owner != target_id]
        if remaining:
            row["item_owner_ids"] = remaining
            kept.append(row)
    spellcasting["spells"] = kept
    surviving_sources = {
        str(row.get("spell_source_row_id") or "").strip()
        for row in kept if isinstance(row, dict)
        and isinstance(row.get("item_owner_ids"), list)
        and set(row["item_owner_ids"]).intersection(compatible)
    }
    spellcasting["source_rows"] = [
        row for row in spellcasting.get("source_rows") or []
        if not isinstance(row, dict)
        or str(row.get("source_row_id") or "").strip()
        not in (source_ids - surviving_sources)
    ]
    result["spellcasting"] = spellcasting
    retired_sources = source_ids - surviving_sources
    if retired_sources:
        source = dict(result.get("source") or {})
        source["source_authorizations"] = [
            marker for marker in source.get("source_authorizations") or []
            if not (isinstance(marker, dict) and any(
                str(marker.get("target_id") or "").startswith(
                    f"spell_metric:source:{source_id}:")
                for source_id in retired_sources))
        ]
        result["source"] = source
    attacks = []
    for raw in result.get("attacks") or []:
        if not isinstance(raw, dict):
            attacks.append(raw)
            continue
        attack = dict(raw)
        refs = attack.get("equipment_refs", attack.get("equipment_ref"))
        refs = list(refs) if isinstance(refs, (list, tuple)) else [refs] if refs else []
        if target_id in refs:
            refs = [ref for ref in refs if ref != target_id]
            if not refs:
                continue
            attack["equipment_refs"] = refs
            attack.pop("equipment_ref", None)
        attacks.append(attack)
    result["attacks"] = attacks
    return result


def _relinked_item_state(before: Mapping[str, Any], after: Mapping[str, Any],
                         state: Mapping[str, Any], target_id: str) -> dict[str, Any]:
    old_rows = [row for row in before.get("equipment_catalog") or []
                if isinstance(row, dict) and row.get("id") == target_id]
    new_rows = [row for row in after.get("equipment_catalog") or []
                if isinstance(row, dict) and row.get("id") == target_id]
    if len(old_rows) != 1 or len(new_rows) != 1:
        raise SourceRepairError("The item owner identity needs manager repair.")
    if old_rows[0].get("systems_ref") == new_rows[0].get("systems_ref"):
        return deepcopy(dict(state))
    result = deepcopy(dict(state))
    matches = [row for row in result.get("inventory") or []
               if isinstance(row, dict)
               and str(row.get("catalog_ref") or row.get("id") or "").strip() == target_id]
    if len(matches) != 1:
        raise SourceRepairError("The item inventory identity needs manager repair.")
    matches[0]["is_attuned"] = False
    matches[0]["charges_current"] = None
    matches[0]["charges_max"] = None
    from .character_service import _normalize_attunement_state
    result["attunement"] = _normalize_attunement_state(
        result.get("attunement"), result.get("inventory") or [],
    )
    return result


def _token_serializer() -> URLSafeTimedSerializer:
    secret = current_app.secret_key
    if not secret:
        raise SourceRepairError("Manager review signing is unavailable.")
    return URLSafeTimedSerializer(secret, salt=_SALT)


def _one(name: str, *, max_bytes: int = 1600) -> str:
    values = request.form.getlist(name)
    if len(values) != 1:
        raise SourceRepairError("Review form is incomplete.")
    value = str(values[0]).strip()
    if len(value.encode("utf-8")) > max_bytes:
        raise SourceRepairError("Review form value is too long.")
    return value


def _spell_origin_request():
    item_fields = ("item_only_spell_id", "item_only_grant_id", "confirm_item_only", "item_only_evidence")
    fields = ("spell_origin_mode", "automatic_spell_ids", "remove_spell_id", "confirm_spell_removal", "confirm_current_spells", *item_fields)
    values = {name: _one(name, max_bytes=2200) if name in request.form else "" for name in fields}
    if not any(values.values()):
        return None
    if (values["spell_origin_mode"] != "yes" or values["confirm_spell_removal"] not in {"", "yes"}
            or values["confirm_current_spells"] not in {"", "yes"}):
        raise SourceRepairError("Explicitly select spell-origin correction and confirm any unsupported removal.")
    automatic = [value.strip() for value in values["automatic_spell_ids"].split(",")] if values["automatic_spell_ids"] else []
    result = {"automatic_ids": automatic,
              "remove_ids": [values["remove_spell_id"]] if values["remove_spell_id"] else [],
              "confirm_removal": values["confirm_spell_removal"] == "yes"}
    if values["confirm_current_spells"] == "yes":
        result["confirm_current_spells"] = True
    if any(values[field] for field in item_fields):
        if (values["confirm_item_only"] != "yes" or not values["item_only_spell_id"]
                or not values["item_only_grant_id"] or not values["item_only_evidence"]
                or values["remove_spell_id"] or automatic or values["confirm_spell_removal"] != "yes"
                or values["confirm_current_spells"] != "yes"):
            raise SourceRepairError("Confirm the player-evidenced item-only correction and complete current checkpoint, "
                                    "with one book observation, its separate item grant and no other correction targets.")
        result["remove_ids"] = [values["item_only_spell_id"]]
        result["item_only_correction"] = {"item_spell_id": values["item_only_grant_id"],
            "confirmation": "player_confirmed_item_only_not_spellbook", "evidence_note": values["item_only_evidence"]}
    return result


def _sources(dependencies: Any, campaign_slug: str, campaign: object, *, source_read_phase=None) -> tuple[dict[str, Any], ...]:
    page_records = tuple(source_read_phase.character_pages() if source_read_phase is not None else dependencies.list_visible_character_page_records(campaign_slug, campaign))
    service = source_read_phase.systems_view() if source_read_phase is not None else dependencies.get_systems_service()
    # Preserve the ordinary initialization/repair opportunity once, then keep
    # this full catalogue on the existing request-scoped Character read view.
    # Exact entry/source/override checks and revision barriers remain active.
    service.get_campaign_library(campaign_slug)
    service = service.character_read_view()
    service.bind_campaign_for_request(campaign_slug, campaign)
    entries: list[object] = []
    for entry_type in _SYSTEMS_TYPES:
        from .character_source_reads import builder_source_reader
        entries.extend(dependencies.list_enabled_systems_entries(builder_source_reader(service), campaign_slug, entry_type))
    choices: list[dict[str, Any]] = []
    for entry in entries:
        key = str(getattr(entry, "entry_key", "") or "").strip()
        kind = str(getattr(entry, "entry_type", "") or "").strip().casefold()
        slug = str(getattr(entry, "slug", "") or "").strip()
        if not key or not slug or len(key.encode("utf-8")) > 512:
            continue
        if not dependencies.can_access_campaign_systems_entry(campaign_slug, slug, systems_service=service):
            continue
        if kind == "item" and not dependencies.systems_item_is_approved(entry):
            continue
        family = "item" if kind == "item" else "spell" if kind == "spell" else "feature"
        choices.append({
            "family": family, "kind": "systems_entry", "value": key,
            "label": (str(getattr(entry, "title", "") or key)[:145]
                      + (" — Needs repair" if kind == "item" and _malformed_item_spell_target({
                          "family": family, "kind": "systems_entry", "record": entry,
                      }) else "")),
            "record": entry,
            "visibility": get_effective_campaign_systems_entry_visibility(
                campaign_slug, slug, systems_service=service,
            ),
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


def _character_source_service(dependencies, campaign_slug, campaign, *, source_read_phase=None):
    if source_read_phase is not None:
        return source_read_phase.systems_view()
    service = dependencies.get_systems_service()
    view = getattr(service, "character_read_view", None)
    if callable(view):
        service = view()
        service.bind_campaign_for_request(campaign_slug, campaign)
    return service


@contextmanager
def _relink_authority_phase(record, same_physical_mapping, dependencies, campaign, *, ordinary_item=False):
    """Item evaluation uses publication's service shape and an owned read."""
    if same_physical_mapping is None and not ordinary_item:
        yield None
        return
    from .character_source_reads import SourceReadOwner, native_character_source_context
    owner = SourceReadOwner.owned(get_db(), record.definition.campaign_slug,
                                 record.definition.character_slug)
    try:
        with native_character_source_context(record, source_read_owner=owner,
                systems_service=dependencies.get_systems_service(), campaign=campaign,
                purpose="item-relink-evaluation") as (phase, _service, _pages, _owner):
            if phase is None:
                raise SourceRepairError("Item source evaluation requires a current source snapshot.")
            yield phase
        owner.checkpoint()
    finally:
        owner.close()


def _authority(definition: Mapping[str, Any], state: Mapping[str, Any],
               dependencies: Any, campaign_slug: str, campaign: object,
               witnesses: tuple[Mapping[str, Any], ...],
               numeric_witnesses: tuple[Mapping[str, Any], ...] = (),
               *, state_revision: int, source_read_phase=None, prospective_spell_checkpoint=None):
    from .character_source_authority import build_reconciled_source_authority
    candidate = CharacterDefinition.from_dict(dict(definition))
    checkpoint_kwargs = {}
    if prospective_spell_checkpoint is not None:
        from .character_spell_reconstruction import PendingSpellCheckpoint
        if (type(prospective_spell_checkpoint) is not PendingSpellCheckpoint
                or not prospective_spell_checkpoint.matches_definition(candidate)):
            raise SourceRepairError("The current spell confirmation does not match this projection.")
        checkpoint_kwargs["prospective_spell_checkpoint"] = prospective_spell_checkpoint
    return build_reconciled_source_authority(
        definition=candidate, state=dict(state),
        systems_service=_character_source_service(dependencies, campaign_slug, campaign, source_read_phase=source_read_phase),
        campaign_page_records=(source_read_phase.character_pages() if source_read_phase is not None else list(dependencies.list_visible_character_page_records(campaign_slug, campaign))),
        verified_manual_actions=tuple(witnesses),
        verified_numeric_actions=tuple(numeric_witnesses),
        state_revision=state_revision,
        **checkpoint_kwargs,
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


def _repair_link_review(before: Mapping[str, Any], after: Mapping[str, Any],
                        family: str, target_id: str) -> dict[str, Any]:
    previous = [row for row in _repair_rows_for_review(before, family)
                if str(row.get("id") or "").strip() == target_id]
    current = [row for row in _repair_rows_for_review(after, family)
               if str(row.get("id") or "").strip() == target_id]
    if len(previous) != 1 or len(current) != 1:
        raise SourceRepairError("The Character target has no unique instance identity.")

    def roles(row: Mapping[str, Any]) -> dict[str, str]:
        systems = dict(row.get("systems_ref") or {})
        page = row.get("page_ref")
        if isinstance(page, dict):
            page = page.get("page_ref") or page.get("slug") or page.get("page_slug")
        return {
            "systems": str(systems.get("entry_key") or systems.get("slug") or "").strip(),
            "page": str(page or "").strip(),
        }

    old, new = roles(previous[0]), roles(current[0])
    return {
        "systems": new["systems"],
        "page": new["page"],
        "page_role": "Items context" if new["systems"] and new["page"] else "Items mechanics",
        "changes": [
            f"{label}: {old[key] or 'none'} → {new[key] or 'none'}"
            for key, label in (("systems", "Systems mechanics link"), ("page", "Items page link"))
            if old[key] != new[key]
        ],
    }


def _repair_rows_for_review(definition: Mapping[str, Any], family: str) -> list[dict[str, Any]]:
    if family == "item":
        rows = definition.get("equipment_catalog") or []
    elif family == "feature":
        rows = definition.get("features") or []
    else:
        rows = dict(definition.get("spellcasting") or {}).get("spells") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _repair_context_proof_digest(candidate: Mapping[str, Any], family: str,
                                 target_id: str, *, connection: Any) -> str:
    if family != "item":
        return ""
    rows = _repair_rows_for_review(candidate, family)
    matching = [(index, row) for index, row in enumerate(rows)
                if str(row.get("id") or "").strip() == target_id]
    if len(matching) != 1:
        raise SourceRepairError("The Character item identity changed.")
    index, row = matching[0]
    if not row.get("page_ref") or not row.get("systems_ref"):
        return ""
    from .committed_character_publication import (
        _create_source_proof, _exact_page_link, _exact_systems_link,
    )

    owner = f"definition.equipment_catalog[{index}]"
    try:
        proof = _create_source_proof(
            str(candidate.get("campaign_slug") or ""),
            (_exact_page_link(row["page_ref"], owner + ".page_ref", "item_context"),),
            (_exact_systems_link(row["systems_ref"], owner + ".systems_ref", "item"),),
            connection=connection,
        )
    except CommittedSourceConflict as exc:
        raise SourceRepairError("The Items context or Systems mechanics changed. Refresh and review again.") from exc
    return canonical_digest({
        "config_revision": proof.config_revision,
        "current_session": proof.current_session,
        "systems_token": proof.systems_token,
        "library_slug": proof.library_slug,
        "pages": proof.pages,
        "entries": proof.entries,
    })


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
    confirmed_skill_level: str | None = None, skill_authority: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    choices = _numeric_target_choices(definition, state)
    if not any(row["kind"] == target_kind and row["id"] == target_id and row["metric"] == metric for row in choices):
        raise SourceRepairError("The selected numeric owner is missing or ambiguous.")
    candidate = deepcopy(dict(definition))
    dependent_passive = None
    if confirmed_skill_level is not None:
        candidate, dependent_passive = _correct_skill_choice(
            definition, target_kind=target_kind, target_id=target_id, metric=metric,
            confirmed_level=confirmed_skill_level, authority=skill_authority,
        )
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
    candidate = add_numeric_authorization(candidate, authorization)
    if dependent_passive is not None:
        values = _numeric_values(candidate, state)
        key = ("field", f"stats.{dependent_passive}", "final")
        companion = numeric_authorization_record(
            character_slug=str(candidate.get("character_slug") or ""),
            target_kind=key[0], target_id=key[1], metric=key[2], raw_value=values[key],
            action_id=action_id, provenance="manager", owner_digest=numeric_target_owner_digest(
                CharacterDefinition.from_dict(candidate), dict(state), *key),
        )
        candidate = add_numeric_authorization(candidate, companion)
    return candidate, authorization


def _correct_skill_choice(
    definition: Mapping[str, Any], *, target_kind: str, target_id: str, metric: str,
    confirmed_level: str, authority: Any,
) -> tuple[dict[str, Any], str | None]:
    """Change one owned choice using current qualified inputs and source effects."""
    from .character_builder_constants import ABILITY_KEYS, SKILL_ABILITY_KEYS, SKILL_LABELS
    from .character_builder_derivation import (
        _build_skills_payload_from_levels, _derive_definition_skills,
        _effect_passive_bonus, _campaign_option_payloads_from_definition,
    )
    from .character_builder_equipment import _extract_character_effect_keys
    from .character_campaign_options import collect_campaign_option_stat_adjustments
    from .character_adjustments import apply_stat_adjustments
    from .repository import normalize_lookup

    if (target_kind != "proficiency" or metric != "grant" or confirmed_level not in _SKILL_LEVELS
            or not isinstance(target_id, str) or not target_id.startswith("skills.") or authority is None):
        raise SourceRepairError("Confirm one recognized skill proficiency level for an existing skill grant.")
    original = CharacterDefinition.from_dict(deepcopy(dict(definition)))
    matches = [(index, row) for index, row in enumerate(original.skills)
               if isinstance(row, dict) and f"skills.{str(row.get('name') or '').strip().casefold()}" == target_id]
    if len(matches) != 1:
        raise SourceRepairError("The selected skill is missing or ambiguous.")
    index, prior_row = matches[0]
    skill = normalize_lookup(str(prior_row.get("name") or ""))
    if (skill not in SKILL_LABELS or target_id != f"skills.{SKILL_LABELS[skill].casefold()}"
            or not authority.field_status(target_id).is_effective):
        raise SourceRepairError("The selected skill needs current source ownership before correction.")
    ability = SKILL_ABILITY_KEYS[skill]
    if any(authority.status_for("feature", str(row.get("id") or "").strip()) != "VERIFIED"
           for row in original.features if isinstance(row, dict)):
        raise SourceRepairError("Current feature sources need repair before correcting skill choices.")
    score = authority.field_status(f"stats.ability_scores.{ability}.score")
    proficiency = authority.field_status("stats.proficiency_bonus")
    if (not score.is_effective or type(score.effective) is not int
            or not proficiency.is_effective or type(proficiency.effective) is not int):
        raise SourceRepairError("The skill's current ability or proficiency bonus needs source repair.")
    qualified = authority.effective_definition(original)
    abilities = {key: 10 for key in ABILITY_KEYS}
    abilities[ability] = score.effective
    seeded = next(row for row in _build_skills_payload_from_levels(
        abilities, {skill: confirmed_level}, proficiency.effective,
    ) if normalize_lookup(row["name"]) == skill)
    # Do not infer a chosen proficiency back from its stale saved bonus.
    payload = qualified.to_dict()
    payload["skills"] = [seeded]
    derived = next(row for row in _derive_definition_skills(
        CharacterDefinition.from_dict(payload), ability_scores=abilities,
        proficiency_bonus=proficiency.effective, source_authority=authority,
    ) if normalize_lookup(row["name"]) == skill)
    result = deepcopy(dict(definition))
    result["skills"][index] = {**prior_row, "proficiency_level": derived["proficiency_level"], "bonus": derived["bonus"]}
    passive = _SKILL_PASSIVES.get(skill)
    if passive is not None:
        # The existing numeric contract has no independent owner for a saved
        # manual passive adjustment. A skill-choice confirmation cannot attest
        # that separate input merely by carrying it into a fresh final witness.
        manual = dict(original.stats or {}).get("manual_adjustments")
        if manual not in (None, {}) and not isinstance(manual, dict):
            raise SourceRepairError("The dependent passive adjustment needs separate manager repair.")
        if isinstance(manual, dict) and manual.get(passive) not in (None, 0, "0", ""):
            raise SourceRepairError("The dependent passive adjustment needs separate manager repair.")
        passive_stats = {passive: 10 + derived["bonus"] + _effect_passive_bonus(
            _extract_character_effect_keys(list(qualified.features or [])), skill_name=SKILL_LABELS[skill],
        )}
        passive_stats = apply_stat_adjustments(passive_stats, collect_campaign_option_stat_adjustments(
            _campaign_option_payloads_from_definition(qualified),
        ))
        result["stats"][passive] = passive_stats[passive]
    return result, passive


def _numeric_action_batch(candidate: Mapping[str, Any], primary: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows = tuple(dict(row) for row in dict(candidate.get("source") or {}).get("source_authorizations") or []
                 if isinstance(row, Mapping) and row.get("action_id") == primary.get("action_id")
                 and row.get("provenance") == "manager")
    if not 1 <= len(rows) <= 2 or primary not in rows:
        raise SourceRepairError("The reviewed numeric authorization batch changed.")
    return rows


def _skill_correction_authority(
    definition: Mapping[str, Any], state: Mapping[str, Any], dependencies: Any,
    campaign_slug: str, campaign: object, witnesses: tuple[Any, ...], numeric_witnesses: tuple[Any, ...],
    *, state_revision: int, confirmed_skill_level: str | None,
) -> Any | None:
    if confirmed_skill_level is None:
        return None
    authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses,
                           numeric_witnesses, state_revision=state_revision)
    return authority.bind_current_numbers(
        CharacterDefinition.from_dict(deepcopy(dict(definition))), deepcopy(dict(state)),
        systems_service=dependencies.get_systems_service(),
        campaign_page_records=list(dependencies.list_visible_character_page_records(campaign_slug, campaign)),
    )


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


def _audit_outcome(review_digest: str, claims: dict[str, Any], record: Any,
                   source_digest: str) -> tuple[bool, bool]:
    """Distinguish a historical token from its exact current committed outcome."""
    rows = get_db().execute(
        """SELECT actor_user_id,metadata_json FROM auth_audit_log
           WHERE event_type = 'character_update_applied'
             AND campaign_slug = ? AND character_slug = ?""",
        (claims["campaign"], claims["character"]),
    ).fetchall()
    matching = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
            if metadata.get("review_digest") == review_digest:
                matching.append((row["actor_user_id"], metadata))
        except (TypeError, ValueError):
            continue
    if not matching:
        return False, False
    if len(matching) != 1:
        return True, False
    actor, metadata = matching[0]
    action = claims.get("action")
    expected_action = {"relink": "source_relink", "manual_authorize": "manual_authorize",
                       "numeric_attest": "numeric_attest", "native_requalify": "native_requalify",
                       "feature_class_association": "feature_class_association",
                       "managed_resource_restoration": "numeric_attest"}.get(action)
    current = (
        actor == claims.get("actor")
        and metadata.get("source") == "character_source_repair"
        and metadata.get("manager_action") == expected_action
        and metadata.get("candidate_digest") == claims.get("candidate_digest")
        and metadata.get("review_action") == action
        and metadata.get("review_family") == claims.get("family")
        and metadata.get("review_target_id") == claims.get("target_id")
        and metadata.get("review_source") == claims.get("source")
        and metadata.get("review_source_digest") == claims.get("source_digest")
        and (claims.get("same_physical_mapping") is None or (
            metadata.get("same_physical_mapping") == claims["same_physical_mapping"]
            and metadata.get("action_id") == claims.get("action_id")))
        and source_digest == claims.get("source_digest")
        and metadata.get("published_revision") == record.committed_revision
        and metadata.get("published_state_revision") == record.state_record.revision
        and metadata.get("published_definition_digest") == canonical_digest(
            record.definition.to_dict())
    )
    return True, current


def _ordinary_relink_candidate(record, choice, target_id, actor_id, dependencies, *,
                               source_read_owner=None, source_read_phase=None):
    definition = record.definition.to_dict()
    candidate = repair_definition(definition, family=choice["family"], target_id=target_id,
        source_kind=choice["kind"], source_value=choice["value"], source_record=choice["record"],
        campaign_option=choice.get("option"), connection=get_db())
    state = deepcopy(record.state_record.state)
    if choice["family"] == "item":
        candidate = _retire_relinked_item_claims(definition, candidate, target_id)
        state = _relinked_item_state(definition, candidate, state, target_id)
        normalized, state = dependencies.character_update_apply_engine.coordinator.prepare_source_repair_item_transition(
            record, CharacterDefinition.from_dict(candidate), state,
            actor_id=actor_id, source_read_owner=source_read_owner,
            source_read_phase=source_read_phase,
        )
        candidate = normalized.to_dict()
    return candidate, state


def _prepare_relink_candidate(record, choice, target_id, actor_id, action_id, dependencies, campaign,
                              *, source_read_owner=None, source_read_phase=None):
    from .character_reconstruction_items import PendingSamePhysicalItemMapping
    from .character_source_reads import SourceReadOwner, native_character_source_context
    mapping = None
    originals = [row for row in record.definition.equipment_catalog
                 if isinstance(row, dict) and row.get("id") == target_id]
    page_only = (len(originals) == 1 and originals[0].get("page_ref")
                 and not originals[0].get("systems_ref"))
    if choice["family"] == "item" and choice["kind"] == "systems_entry" and page_only:
        if source_read_phase is not None:
            mapping = PendingSamePhysicalItemMapping.prepare(record, target_id, choice["value"],
                actor_id=actor_id, action_id=action_id, service=source_read_phase.systems_view(),
                pages=source_read_phase.character_pages())
        else:
            owned = source_read_owner is None
            owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
                get_db(), record.definition.campaign_slug, record.definition.character_slug)
            try:
                with native_character_source_context(record, source_read_owner=owner,
                        systems_service=dependencies.get_systems_service(), campaign=campaign,
                        purpose="same-physical-item-proposal") as (_phase, service, pages, _owner):
                    if _phase is None:
                        raise SourceRepairError("Same-physical adoption requires an initialized current source view.")
                    mapping = PendingSamePhysicalItemMapping.prepare(record, target_id, choice["value"],
                        actor_id=actor_id, action_id=action_id, service=service, pages=pages)
                owner.checkpoint()
            finally:
                if owned:
                    owner.close()
    if mapping is not None:
        return mapping.candidate(record), deepcopy(record.state_record.state), mapping
    candidate, state = _ordinary_relink_candidate(
        record, choice, target_id, actor_id, dependencies, source_read_owner=source_read_owner,
        source_read_phase=source_read_phase,
    )
    return candidate, state, None


def _ordinary_item_relink_basis(record, claims, actor_id, dependencies, campaign,
                                witnesses, numeric_witnesses, *, source_read_owner=None):
    """Rebuild one refresh; only immutable external facts share its lifetime."""
    from .character_source_reads import SourceReadOwner, native_character_source_context
    owned = source_read_owner is None
    owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
        get_db(), record.definition.campaign_slug, record.definition.character_slug)
    try:
        with native_character_source_context(record, source_read_owner=owner,
                systems_service=dependencies.get_systems_service(), campaign=campaign,
                purpose="ordinary-item-review-refresh") as (phase, _service, _pages, _owner):
            if phase is None:
                raise SourceRepairError("Item source refresh requires a current source snapshot.")
            current_choices = _sources(dependencies, record.definition.campaign_slug, campaign,
                                       source_read_phase=phase)
            selected = [row for row in current_choices if row["family"] == "item"
                        and _source_option(row) == claims["source"]]
            if len(selected) != 1:
                raise SourceRepairError("The exact source is no longer eligible.")
            choice = selected[0]
            _require_repairable_item_target(choice)
            candidate, state = _ordinary_relink_candidate(
                record, choice, claims["target_id"], actor_id, dependencies,
                source_read_owner=owner, source_read_phase=phase)
            before = _authority(record.definition.to_dict(), record.state_record.state,
                dependencies, record.definition.campaign_slug, campaign, witnesses, numeric_witnesses,
                state_revision=record.state_record.revision, source_read_phase=phase)
            after = _authority(candidate, state, dependencies, record.definition.campaign_slug, campaign,
                witnesses, numeric_witnesses, state_revision=record.state_record.revision,
                source_read_phase=phase)
            if not _repair_is_verified(after, candidate, "item", claims["target_id"]):
                raise SourceRepairError("The selected source is no longer verified.")
            context_digest = _repair_context_proof_digest(candidate, "item", claims["target_id"], connection=get_db())
            basis = _source_digest(current_choices), canonical_digest({
                "candidate": candidate, "effect_delta": _effect_delta(before, after),
                "context_proof_digest": context_digest,
            })
        owner.checkpoint()
        return basis
    finally:
        if owned:
            owner.close()


def _confirmed_item_relink_row(candidate: Mapping[str, Any],
                               published: Mapping[str, Any], target_id: str) -> bool:
    """Compare the reviewed row after only the publisher's exact clear-set."""
    expected = [row for row in candidate.get("equipment_catalog") or []
                if isinstance(row, dict) and row.get("id") == target_id]
    actual = [row for row in published.get("equipment_catalog") or []
              if isinstance(row, dict) and row.get("id") == target_id]
    if len(expected) != 1 or len(actual) != 1:
        return False
    row = deepcopy(expected[0])
    cleared = dict(published.get("source") or {}).get("item_transition_cleared_charges")
    if cleared == [target_id]:
        row.update(is_attuned=False, charges_current=None, charges_max=None)
    return canonical_digest(row) == canonical_digest(actual[0])


def register_character_source_repair_route(app: Any, *, dependencies: Any) -> None:
    from .character_feature_class_association_routes import register_feature_class_association_route
    register_feature_class_association_route(app, dependencies=dependencies)
    from .character_managed_resource_restoration_routes import register_managed_resource_restoration_route
    register_managed_resource_restoration_route(app, dependencies=dependencies)
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
        early_claims = None
        native_admission = None
        route_source_owner = None
        early_error = None
        try:
            if request.method == "POST":
                try:
                    intent = _one("intent")
                    if intent == "apply":
                        if set(request.form) != _APPLY_FIELDS:
                            raise BadRequest()
                        token = _one("review_token", max_bytes=8192)
                        try:
                            early_claims, native_admission = PendingReviewedSourceProof.admit_native_request(
                                token, actor_id, campaign_slug, character_slug)
                        except (BadSignature, SignatureExpired) as exc:
                            raise SourceRepairError("Review expired or changed. Refresh and review again.") from exc
                        if (not isinstance(early_claims, dict) or early_claims.get("v") != 1
                                or early_claims.get("actor") != actor_id
                                or early_claims.get("campaign") != campaign_slug
                                or early_claims.get("character") != character_slug):
                            raise SourceRepairError("Review is for a different manager or Character.")
                except Exception as exc:
                    # Context/existence and journal-health responses retain their
                    # original precedence, including malformed forms and tokens.
                    early_error = exc
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
            # Equality baselines are detached; authority retains the original typed witnesses.
            manual_comparison = action_witness_comparison(witnesses)
            numeric_comparison = action_witness_comparison(numeric_witnesses)
            targets = eligible_repair_targets(definition)
            manual_targets = _manual_targets(definition)
            numeric_targets = _numeric_target_choices(definition, state)
            def source_owner(explicit=None):
                nonlocal route_source_owner
                if explicit is not None:
                    return explicit
                if route_source_owner is None:
                    from .character_source_reads import SourceReadOwner
                    route_source_owner = SourceReadOwner.owned(get_db(), campaign_slug, character_slug)
                return route_source_owner

            def prepare_native(action_id, spell_origin_request=None, *, source_read_owner=None):
                from .character_native_requalification import prepare_native_requalification
                from .character_source_reads import native_character_source_context
                owner = source_owner(source_read_owner)
                service = dependencies.get_systems_service().character_read_view()
                with native_character_source_context(record, source_read_owner=owner,
                        systems_service=service, campaign=campaign,
                        purpose="native-producer-inputs") as (_phase, _service, pages, _owner):
                    source_pages = list(pages)
                return prepare_native_requalification(
                    record=record, systems_service=service,
                    campaign_page_records=source_pages,
                    action_id=action_id, actor_id=actor_id, connection=get_db(),
                    spell_origin_request=spell_origin_request,
                    source_read_owner=owner, campaign=campaign,
                )

            def native_delta(result, *, source_read_phase=None):
                before = _authority(definition, state, dependencies, campaign_slug, campaign,
                                    witnesses, numeric_witnesses, state_revision=record.state_record.revision, source_read_phase=source_read_phase)
                after = native_authority(result, source_read_phase=source_read_phase)
                return {**_effect_delta(before, after),
                        "statuses": _numeric_status_delta(before, after)}

            def native_state(result, *, source_read_phase=None):
                from .character_native_requalification import native_requalification_state
                return native_requalification_state(record, result, actor_id, source_read_phase=source_read_phase)

            def native_readiness(result, *, source_read_phase=None):
                from .character_equipment_activation import activation_frame_digest
                desired_state = native_state(result, source_read_phase=source_read_phase)
                authority = native_authority(result, source_read_phase=source_read_phase)
                if ("equipment_activation" not in state
                        or result.provenance.get("spell_origin_plan") is not None):
                    from .character_reconstruction_state import prepare_exact_reconstruction_state
                    prepared = prepare_exact_reconstruction_state(record, result.candidate, desired_state,
                        authority, actor_id=actor_id, native_result=result)
                else:
                    # Valid-marker no-plan renewals use ordinary preparation. Any
                    # UNKNOWN normalization refuses before a positive signed Review.
                    from .character_service import CharacterStateValidationError
                    try:
                        prepared = dependencies.character_update_apply_engine.coordinator.state_store.prepare_initial_state(
                            result.candidate, desired_state, source_authority=authority, previous_state=state)
                    except CharacterStateValidationError as exc:
                        raise SourceRepairError("Native desired state needs ordinary manager validation.") from exc
                if activation_frame_digest(prepared.validated_state) != activation_frame_digest(desired_state):
                    raise SourceRepairError("Native preparation cannot preserve the complete reviewed state.")
                return desired_state

            def native_authority(result, *, source_read_phase=None):
                from .character_spell_reconstruction import PendingSpellCheckpoint
                checkpoint = result.spell_checkpoint
                if checkpoint is not None and (type(checkpoint) is not PendingSpellCheckpoint
                        or not checkpoint.matches_definition(result.candidate)
                        or result.provenance.get("schema_version") not in {5, 6}
                        or result.provenance.get("spell_origin_plan", {}).get("current_checkpoint") != checkpoint.checkpoint):
                    raise SourceRepairError("The current spell confirmation changed before projection.")
                bases = result.provenance.get("renewed_source_bases", {})
                prospective = tuple({"authorization": marker, "source_basis_digest": bases[marker["target_id"]]}
                                    if marker.get("provenance") == "native_requalification" else marker
                                    for marker in result.authorizations)
                return _authority(result.candidate.to_dict(), native_state(result, source_read_phase=source_read_phase), dependencies,
                                  campaign_slug, campaign, witnesses,
                                  (*numeric_witnesses, *prospective),
                                  state_revision=record.state_record.revision, source_read_phase=source_read_phase,
                                  prospective_spell_checkpoint=checkpoint)

            def native_grant_review(result, *, source_read_phase=None):
                from .character_spell_grants import inspect_native_grant_proposal
                draft = inspect_native_grant_proposal(result.candidate,
                    _character_source_service(dependencies, campaign_slug, campaign, source_read_phase=source_read_phase),
                    prior_definition=record.definition, prior_generation=record.committed_revision,
                    prior_definition_digest=canonical_digest(record.definition.to_dict()),
                    prior_state_revision=record.state_record.revision)
                if draft.source_digest != result.provenance["spell_origin_plan"]["proposal_source_digest"]:
                    raise SourceRepairError("Proposed feature-grant source facts changed before review.")
                return [{"id": row["id"], "owner_id": row["owner_id"],
                         "rule_id": row["rule_id"], "leaf_id": row["leaf_id"],
                         "spell": row["spell_ref"]["entry_key"], "status": row["status"],
                         "reason": row["reason"], "contributions": deepcopy(row.get("contributions", {}))}
                        for row in draft.occurrences]

            def bind_route_inputs(phase):
                from .character_source_reads import SourceReadConflict
                if phase is None:
                    return
                current_choices = _sources(dependencies, campaign_slug, phase.campaign(), source_read_phase=phase)
                if (_source_digest(current_choices) != source_digest
                        or action_witness_comparison(load_verified_manual_actions(campaign_slug, character_slug, connection=phase.connection)) != manual_comparison
                        or action_witness_comparison(load_verified_numeric_actions(campaign_slug, character_slug, connection=phase.connection)) != numeric_comparison):
                    raise SourceReadConflict("Supplied native source choices or witnesses changed.")

            def native_evaluation(result, *, source_read_owner=None):
                from .character_source_reads import native_character_source_context
                owner = source_owner(source_read_owner)
                service = _character_source_service(dependencies, campaign_slug, campaign)
                with native_character_source_context(record, source_read_owner=owner,
                        systems_service=service, campaign=campaign, purpose="native-route-evaluation") as (phase, _service, _pages, _owner):
                    bind_route_inputs(phase)
                    ready = native_readiness(result, source_read_phase=phase)
                    return ready, native_delta(result, source_read_phase=phase)

            def native_authority_guarded(result, *, source_read_owner=None):
                from .character_source_reads import native_character_source_context
                with native_character_source_context(record, source_read_owner=source_owner(source_read_owner),
                        systems_service=_character_source_service(dependencies, campaign_slug, campaign),
                        campaign=campaign, purpose="native-authority-callback") as (phase, _service, _pages, _owner):
                    bind_route_inputs(phase)
                    return native_authority(result, source_read_phase=phase)

            def native_grant_review_guarded(result, *, source_read_owner=None):
                from .character_source_reads import native_character_source_context
                with native_character_source_context(record, source_read_owner=source_owner(source_read_owner),
                        systems_service=_character_source_service(dependencies, campaign_slug, campaign),
                        campaign=campaign, purpose="native-grant-review") as (phase, _service, _pages, _owner):
                    bind_route_inputs(phase)
                    return native_grant_review(result, source_read_phase=phase)

            def native_audit(result, claims, review_digest):
                from .character_reconciliation import CharacterPublicationError
                from .committed_character_publication import prepare_native_requalification_audit
                payload = {"source": "character_source_repair", "manager_action": "native_requalify",
                    "review_digest": review_digest, "action_id": claims["action_id"],
                    "manual_authorization": None, "numeric_authorization": None,
                    "numeric_authorizations": list(result.authorizations), "native_requalification": result.provenance,
                    "confirmed_skill_level": None, "numeric_actor_id": actor_id,
                    "manual_actor_id": None, "manual_authorized_at": None,
                    "candidate_digest": claims["candidate_digest"], "review_action": "native_requalify",
                    "review_family": None, "review_target_id": None, "review_source": None,
                    "review_source_digest": claims["source_digest"]}
                try:
                    prepared = prepare_native_requalification_audit(
                        dependencies.character_update_apply_engine.coordinator,
                        record, result.candidate, native_state(result), payload, actor_id, connection=get_db())
                except CharacterPublicationError as exc:
                    raise SourceRepairError(str(exc)) from exc
                return json.loads(prepared[3]), len(prepared[3].encode("utf-8"))
            review = None
            activation_repair_required = False
            outcome = None
            status_code = 200
            if request.method == "POST":
                try:
                    intent = _one("intent")
                    if early_error is not None and intent != "apply":
                        raise early_error
                    if intent == "apply":
                        if set(request.form) != _APPLY_FIELDS:
                            abort(400)
                        token = _one("review_token", max_bytes=8192)
                        if len(token.encode("utf-8")) > 8192:
                            raise SourceRepairError("Review token is too large.")
                        try:
                            if early_error is not None:
                                raise early_error
                            if native_admission is not None:
                                claims = early_claims
                            else:
                                claims, native_admission = PendingReviewedSourceProof.admit_manager_review(record, token, actor_id)
                        except (BadSignature, SignatureExpired) as exc:
                            raise SourceRepairError("Review expired or changed. Refresh and review again.") from exc
                        if not isinstance(claims, dict) or claims.get("v") != 1 or claims.get("actor") != actor_id or claims.get("campaign") != campaign_slug or claims.get("character") != character_slug:
                            raise SourceRepairError("Review is for a different manager or Character.")
                        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                        applied, current = _audit_outcome(digest, claims, record, source_digest)
                        if applied:
                            if not current:
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
                        if native_admission is not None:
                            # Only an exact same-request native seal can move past
                            # normal age. Bind actual saved facts once, after the
                            # existing already-applied read-only outcome check.
                            claims, native_admission = PendingReviewedSourceProof.admit_manager_review(
                                record, token, actor_id, native_review_admission=native_admission)
                        action = claims.get("action")
                        transition_state = state
                        native_result = None
                        authorization = None
                        authorization_batch = ()
                        same_physical_mapping = None
                        if action == "relink":
                            selected = [choice for choice in choices if _source_option(choice) == claims.get("source") and choice["family"] == claims.get("family")]
                            if len(selected) != 1:
                                raise SourceRepairError("The exact source is no longer eligible.")
                            choice = selected[0]
                            _require_repairable_item_target(choice)
                            candidate, transition_state, same_physical_mapping = _prepare_relink_candidate(
                                record, choice, claims["target_id"], actor_id, claims["action_id"], dependencies, campaign)
                            if (same_physical_mapping.descriptor() if same_physical_mapping is not None else None) != claims.get("same_physical_mapping"):
                                raise SourceRepairError("The exact physical source mapping changed since Review.")
                            with _relink_authority_phase(record, same_physical_mapping, dependencies, campaign,
                                    ordinary_item=choice["family"] == "item") as phase:
                                before_authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision, source_read_phase=phase)
                                after_authority = _authority(candidate, transition_state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision, source_read_phase=phase)
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
                        elif action == "native_requalify":
                            native_result = prepare_native(claims.get("action_id"), claims.get("spell_origin_request"))
                            candidate = native_result.candidate.to_dict()
                            transition_state, expected_delta = native_evaluation(native_result)
                            authorization_batch = native_result.authorizations
                            if canonical_digest({"provenance": native_result.provenance,
                                                 "authorizations": authorization_batch,
                                                 "state": transition_state}) != claims.get("native_proof_digest"):
                                raise SourceRepairError("The retained native inputs or current sources changed.")
                            audit_action = "native_requalify"
                            audit_record = None
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
                                confirmed_skill_level=claims.get("confirmed_skill_level"),
                                skill_authority=_skill_correction_authority(
                                    definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision,
                                    confirmed_skill_level=claims.get("confirmed_skill_level"),
                                ),
                            )
                            authorization_batch = _numeric_action_batch(candidate, rebuilt)
                            if (rebuilt != authorization
                                    or list(authorization_batch) != claims.get("authorizations", [authorization])):
                                raise SourceRepairError("The confirmed value changed.")
                            before_authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses, state_revision=record.state_record.revision)
                            after_authority = _authority(candidate, state, dependencies, campaign_slug, campaign, witnesses, (*numeric_witnesses, *authorization_batch), state_revision=record.state_record.revision)
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
                        if action == "relink" and _repair_context_proof_digest(
                                candidate, choice["family"], claims["target_id"],
                                connection=get_db()) != claims.get("context_proof_digest", ""):
                            raise SourceRepairError("The Items context changed. Refresh and review again.")
                        if native_result is not None:
                            from .character_source_reads import native_character_source_context
                            with native_character_source_context(record,
                                    source_read_owner=source_owner(), campaign=campaign,
                                    purpose="native-apply-source-policy") as (source_phase, _service, _pages, _owner):
                                current_choices = _sources(dependencies, campaign_slug, campaign,
                                                           source_read_phase=source_phase)
                        else:
                            current_choices = _sources(dependencies, campaign_slug, campaign)
                        if _source_digest(current_choices) != source_digest:
                            raise SourceRepairError("Current source policy changed before apply. Refresh and review again.")
                        desired = CharacterDefinition.from_dict(candidate)
                        coordinator = dependencies.character_update_apply_engine.coordinator
                        authority_provider = coordinator.numeric_authority_provider
                        if not callable(authority_provider):
                            raise SourceRepairError("Current Character source authority is unavailable.")
                        reviewed_authority = (native_authority_guarded(native_result) if native_result is not None
                            else coordinator.source_repair_review_authority(record, desired, transition_state,
                                actor_id=actor_id, same_physical_mapping=same_physical_mapping,
                                source_read_owner=(source_owner() if action == "relink"
                                    and claims.get("family") == "item" and same_physical_mapping is None else None)))
                        if reviewed_authority is None:
                            raise SourceRepairError("Current Character source authority is unavailable.")

                        def refresh_review_basis(*, source_read_owner=None) -> tuple[Any, ...]:
                            if action == "relink" and claims.get("family") == "item" and same_physical_mapping is None:
                                return _ordinary_item_relink_basis(record, claims, actor_id, dependencies, campaign,
                                    witnesses, numeric_witnesses, source_read_owner=source_read_owner)
                            if same_physical_mapping is not None:
                                from .character_source_reads import SourceReadOwner, native_character_source_context
                                owned = source_read_owner is None
                                mapping_owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
                                    get_db(), campaign_slug, character_slug)
                                try:
                                    with native_character_source_context(record, source_read_owner=mapping_owner,
                                            systems_service=dependencies.get_systems_service(), campaign=campaign,
                                            purpose="same-physical-item-refresh") as (phase, _service, _pages, _owner):
                                        if phase is None:
                                            raise SourceRepairError("Same-physical adoption requires a current source snapshot.")
                                        current_choices = _sources(dependencies, campaign_slug, campaign, source_read_phase=phase)
                                        current_selected = [row for row in current_choices if row["family"] == "item"
                                            and _source_option(row) == claims["source"]]
                                        if len(current_selected) != 1:
                                            raise SourceRepairError("The exact physical source is unavailable.")
                                        current_candidate, current_state, current_mapping = _prepare_relink_candidate(
                                            record, current_selected[0], claims["target_id"], actor_id, claims["action_id"],
                                            dependencies, campaign, source_read_owner=mapping_owner, source_read_phase=phase)
                                        if current_mapping is None or current_mapping.descriptor() != claims.get("same_physical_mapping"):
                                            raise SourceRepairError("The exact physical source relation changed.")
                                        current_before = _authority(definition, state, dependencies, campaign_slug, campaign,
                                            witnesses, numeric_witnesses, state_revision=record.state_record.revision, source_read_phase=phase)
                                        current_after = _authority(current_candidate, current_state, dependencies, campaign_slug, campaign,
                                            witnesses, numeric_witnesses, state_revision=record.state_record.revision, source_read_phase=phase)
                                        current_delta = _effect_delta(current_before, current_after)
                                        if not _repair_is_verified(current_after, current_candidate, "item", claims["target_id"]):
                                            raise SourceRepairError("The current physical source is not qualified.")
                                        context_digest = _repair_context_proof_digest(current_candidate, "item", claims["target_id"], connection=get_db())
                                        basis = _source_digest(current_choices), canonical_digest({"candidate": current_candidate,
                                            "effect_delta": current_delta, "context_proof_digest": context_digest,
                                            "same_physical_mapping": current_mapping.descriptor()})
                                    mapping_owner.checkpoint()
                                    return basis
                                finally:
                                    if owned:
                                        mapping_owner.close()
                            if action == "native_requalify":
                                # Finish enumeration before the producer starts its own
                                # phase. In a reservation this view borrows the explicit
                                # owner and cannot initialize a library or commit.
                                from .character_source_reads import native_character_source_context
                                with native_character_source_context(record,
                                        source_read_owner=source_read_owner,
                                        campaign=campaign, purpose="native-refresh-choices") as (source_phase, _service, _pages, _owner):
                                    current_choices = _sources(dependencies, campaign_slug, campaign,
                                                               source_read_phase=source_phase)
                            else:
                                current_choices = _sources(dependencies, campaign_slug, campaign)
                            current_source_digest = _source_digest(current_choices)
                            if action == "relink":
                                current_selected = [row for row in current_choices
                                                    if row["family"] == claims["family"]
                                                    and _source_option(row) == claims["source"]]
                                if len(current_selected) != 1:
                                    raise SourceRepairError("The exact source is no longer eligible.")
                                current_choice = current_selected[0]
                                _require_repairable_item_target(current_choice)
                                current_candidate, current_transition_state = _ordinary_relink_candidate(
                                    record, current_choice, claims["target_id"], actor_id, dependencies,
                                    source_read_owner=source_read_owner,
                                )
                                current_before = _authority(
                                    definition, state, dependencies, campaign_slug, campaign,
                                    witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision,
                                )
                                current_after = _authority(
                                    current_candidate, current_transition_state, dependencies, campaign_slug,
                                    campaign, witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision,
                                )
                                if not _repair_is_verified(current_after, current_candidate,
                                                           current_choice["family"], claims["target_id"]):
                                    raise SourceRepairError("The selected source is no longer verified.")
                                current_delta = _effect_delta(current_before, current_after)
                                current_context_digest = _repair_context_proof_digest(
                                    current_candidate, current_choice["family"],
                                    claims["target_id"], connection=get_db(),
                                )
                            elif action == "native_requalify":
                                current_native = prepare_native(claims["action_id"], claims.get("spell_origin_request"), source_read_owner=source_read_owner)
                                current_candidate = current_native.candidate.to_dict()
                                if canonical_digest({"provenance": current_native.provenance,
                                                     "authorizations": current_native.authorizations,
                                                     "state": native_state(current_native)}) != claims["native_proof_digest"]:
                                    raise SourceRepairError("The retained native inputs or current sources changed.")
                                _current_state, current_delta = native_evaluation(current_native, source_read_owner=source_read_owner)
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
                                    confirmed_skill_level=claims.get("confirmed_skill_level"),
                                    skill_authority=_skill_correction_authority(
                                        definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses,
                                        state_revision=record.state_record.revision,
                                        confirmed_skill_level=claims.get("confirmed_skill_level"),
                                    ),
                                )
                                current_batch = _numeric_action_batch(current_candidate, current_authorization)
                                if (current_authorization != authorization
                                        or list(current_batch) != claims.get("authorizations", [authorization])):
                                    raise SourceRepairError("The confirmed value changed.")
                                current_before = _authority(
                                    definition, state, dependencies, campaign_slug, campaign,
                                    witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision,
                                )
                                current_after = _authority(
                                    current_candidate, state, dependencies, campaign_slug,
                                    campaign, witnesses, (*numeric_witnesses, *current_batch),
                                    state_revision=record.state_record.revision,
                                )
                                current_grants = _effect_delta(current_before, current_after)
                                current_delta = {**current_grants,
                                                 "statuses": _numeric_status_delta(current_before, current_after)}
                            basis = current_source_digest, canonical_digest({
                                "candidate": current_candidate, "effect_delta": current_delta,
                                "context_proof_digest": current_context_digest if action == "relink" else "",
                            })
                            return (*basis, current_native) if action == "native_requalify" else basis

                        reviewed_basis = canonical_digest({
                            "candidate": candidate, "effect_delta": expected_delta,
                            "context_proof_digest": claims.get("context_proof_digest", "") if action == "relink" else "",
                            **({"same_physical_mapping": same_physical_mapping.descriptor()} if same_physical_mapping is not None else {}),
                        })
                        reviewed_source_proof = PendingReviewedSourceProof.capture(
                            record, desired, transition_state, reviewed_authority,
                            source_digest=source_digest, policy_digest=reviewed_basis,
                            replacement_relink_target=(claims["target_id"] if action == "relink" and claims["family"] == "feature" else ""),
                            same_physical_mapping=same_physical_mapping,
                            refresh_review_basis=refresh_review_basis,
                            refresh_numeric_authority=(lambda *, source_read_owner=None: native_authority_guarded(prepare_native(
                                claims["action_id"], claims.get("spell_origin_request"), source_read_owner=source_read_owner), source_read_owner=source_read_owner))
                                if native_result is not None else None,
                            native_requalification_markers=tuple(authorization_batch) if native_result is not None else (),
                            native_spell_origin_plan=(native_result.provenance.get("spell_origin_plan")
                                if native_result is not None else None),
                            native_actor_id=actor_id if native_result is not None else None,
                            native_result=native_result,
                            native_action_id=claims["action_id"] if native_result is not None else "",
                            native_proof_digest=claims["native_proof_digest"] if native_result is not None else "",
                            native_review_token=token if native_result is not None else "",
                            native_review_admission=native_admission if native_result is not None else None,
                            source_read_owner=source_owner() if native_result is not None else None,
                        )
                        result = dependencies.character_update_apply_engine.coordinator.update(
                            record, desired, record.import_metadata, transition_state,
                            expected_revision=record.state_record.revision,
                            updated_by_user_id=actor_id,
                            operation_kind="character_update_apply",
                            audit_event_type="character_update_applied",
                            audit_actor_user_id=actor_id,
                            audit_metadata=(native_audit(native_result, claims, digest)[0] if native_result is not None else
                                _ordinary_action_audit(claims, digest, actor_id=actor_id,
                                    audit_action=audit_action, audit_record=audit_record,
                                    authorization=authorization, authorization_batch=authorization_batch)),
                            reviewed_source_proof=reviewed_source_proof,
                        )
                        if native_result is not None:
                            from .committed_character_publication import load_for_write
                            reopened = load_for_write(current_app.extensions["character_repository"], campaign_slug, character_slug)
                            if (reopened is None or reopened.committed_revision != result.committed_revision
                                    or reopened.state_record.revision != result.state_record.revision
                                    or canonical_digest(reopened.definition.to_dict()) != canonical_digest(result.definition.to_dict())
                                    or canonical_digest(reopened.import_metadata.to_dict()) != canonical_digest(result.import_metadata.to_dict())
                                    or canonical_digest(reopened.state_record.state) != canonical_digest(transition_state)):
                                raise RuntimeError("The saved native update needs inspection before another action.")
                            # Subsequent confirmation uses independently decoded
                            # committed bytes and state, never the prepared object.
                            result = reopened
                        published_candidate = result.definition.to_dict()
                        if action == "relink" and claims.get("family") == "item":
                            confirmed_candidate = _confirmed_item_relink_row(
                                candidate, published_candidate, claims["target_id"],
                            )
                        else:
                            confirmed_candidate = (canonical_digest(published_candidate)
                                                   == claims["candidate_digest"])
                        _, confirmed_audit = _audit_outcome(
                            digest, claims, result, source_digest,
                        )
                        if same_physical_mapping is not None:
                            confirmed_candidate = bool(confirmed_candidate
                                and canonical_digest(published_candidate) == canonical_digest(candidate)
                                and canonical_digest(result.state_record.state) == canonical_digest(state))
                        if confirmed_candidate and confirmed_audit and action == "native_requalify":
                            saved_witnesses = load_verified_numeric_actions(
                                campaign_slug, character_slug, strict=True,
                            )
                            if native_result.provenance.get("schema_version") in {4, 5, 6}:
                                from .character_spell_grants import grant_model_digest, qualify_native_grants
                                saved_view = qualify_native_grants(result.definition,
                                    _character_source_service(dependencies, campaign_slug, campaign),
                                    custody=saved_witnesses)
                                confirmed_candidate = (
                                    grant_model_digest(result.definition)
                                    == native_result.provenance["spell_origin_plan"]["grant_model_digest"]
                                    and {row["id"] for row in saved_view.occurrences if row.get("status") == "VERIFIED"}
                                    == set(native_result.provenance["spell_origin_plan"]["supported_grant_ids"]))
                            if native_result.provenance.get("schema_version") in {5, 6}:
                                from .character_spell_reconstruction import NativeSpellReconstructionFact, validate_saved_spell_checkpoint
                                checkpoint = native_result.provenance["spell_origin_plan"]["current_checkpoint"]
                                validate_saved_spell_checkpoint(record.definition, result.definition, checkpoint)
                                saved_rows = {row["id"]: row for row in result.definition.spellcasting.get("spells", [])}
                                confirmed_candidate = confirmed_candidate and all(
                                    any(type(witness) is NativeSpellReconstructionFact
                                        and witness.matches(saved_rows[entry["spell_id"]])
                                        and witness.get("role") == entry["role"]
                                        and witness.get("spell_level") == entry["spell_level"]
                                        and witness.origin[:2] == (campaign_slug, character_slug)
                                        and witness.origin[3:] == (actor_id, result.committed_revision)
                                        for witness in saved_witnesses)
                                    for entry in checkpoint["entries"])
                            readback_authority = _authority(
                                published_candidate, result.state_record.state, dependencies, campaign_slug, campaign,
                                load_verified_manual_actions(campaign_slug, character_slug, strict=True),
                                saved_witnesses, state_revision=result.state_record.revision,
                            ).bind_current_numbers(
                                result.definition, result.state_record.state,
                                systems_service=_character_source_service(dependencies, campaign_slug, campaign),
                                campaign_page_records=list(dependencies.list_visible_character_page_records(campaign_slug, campaign)),
                            )
                            confirmed_candidate = confirmed_candidate and all(
                                any(marker == witness.get("authorization", witness)
                                    for witness in saved_witnesses if isinstance(witness, dict))
                                and (readback_authority.resource_status(*marker["target_id"].split(":", 1)).is_effective
                                     if marker["target_kind"] == "resource" else
                                     marker["target_id"].removeprefix("spell_choice:") in readback_authority.verified_spell_choices
                                     if marker["target_kind"] == "spell_choice" else
                                     marker["target_id"] in readback_authority.verified_formula_rows
                                     if marker["target_kind"] == "spell_metric" else
                                     readback_authority.field_status(marker["target_id"]).is_effective)
                                for marker in authorization_batch
                            )
                            if native_result.provenance.get("schema_version") in {5, 6}:
                                pools = [pool for pool in readback_authority.spell_choice_ledger["pools"]
                                         if pool["class_row_id"] == checkpoint["class_row"]["row_id"]]
                                confirmed_candidate = confirmed_candidate and bool(pools) and all(
                                    pool["status"] == "KNOWN" and (pool["remaining"] is None or pool["remaining"] >= 0)
                                    for pool in pools)
                        if confirmed_candidate and confirmed_audit and claims.get("confirmed_skill_level") is not None:
                            readback_authority = _authority(
                                published_candidate, result.state_record.state, dependencies, campaign_slug, campaign,
                                load_verified_manual_actions(campaign_slug, character_slug),
                                load_verified_numeric_actions(campaign_slug, character_slug),
                                state_revision=result.state_record.revision,
                            )
                            readback_values = _numeric_values(published_candidate, result.state_record.state)
                            confirmed_candidate = all(
                                readback_authority.field_status(marker["target_id"]).is_effective
                                and readback_authority.field_status(marker["target_id"]).effective
                                == readback_values[(marker["target_kind"], marker["target_id"], marker["metric"])]
                                for marker in authorization_batch
                            )
                        if not confirmed_candidate or not confirmed_audit:
                            outcome = "The update outcome needs inspection before another action."
                            status_code = 503
                        else:
                            outcome = "Manager action applied and confirmed by durable readback."
                        record = result
                    elif intent == "review":
                        if set(request.form) - _FORM_FIELDS or any(len(request.form.getlist(key)) != 1 for key in request.form):
                            abort(400)
                        action = _one("action")
                        authorization = None
                        authorization_batch = ()
                        audit_record = None
                        reviewed_transition_state = state
                        same_physical_mapping = None
                        if action in {"relink", "manual_authorize", "numeric_attest"}:
                            require_update_activation(record, record.definition, state, actor_id=actor_id)
                        if action != "native_requalify" and any(name in request.form for name in (
                                "spell_origin_mode", "automatic_spell_ids", "remove_spell_id", "confirm_spell_removal", "confirm_current_spells",
                                "item_only_spell_id", "item_only_grant_id", "confirm_item_only", "item_only_evidence")):
                            raise SourceRepairError("Spell-origin correction is available only in native requalification.")
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
                            _require_repairable_item_target(choice)
                            relink_action_id = uuid4().hex
                            candidate, reviewed_transition_state, same_physical_mapping = _prepare_relink_candidate(
                                record, choice, target_id, actor_id, relink_action_id, dependencies, campaign)
                            with _relink_authority_phase(record, same_physical_mapping, dependencies, campaign,
                                    ordinary_item=family == "item") as phase:
                                before_authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision, source_read_phase=phase)
                                after_authority = _authority(candidate, reviewed_transition_state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision, source_read_phase=phase)
                                if not _repair_is_verified(after_authority, candidate, family, target_id):
                                    raise SourceRepairError("The selected source has a conflict or remains unverified. Choose another exact source.")
                                delta = _effect_delta(before_authority, after_authority)
                            extra = {"family": family, "target_id": target_id, "source": source_value, "action_id": relink_action_id}
                            if same_physical_mapping is not None:
                                extra["same_physical_mapping"] = same_physical_mapping.descriptor()
                            audit_action = "source_relink"
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
                            audit_action = "manual_authorize"
                            audit_record = authorization
                            candidate = add_manual_authorization(definition, authorization)
                            delta = {"manual": [f"{kind}:{target_id}:{metric}"]}
                            extra = {"authorization": authorization,
                                     "authorized_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                            summary = f"Authorize {metric.replace('_', ' ')} manually for {target_id}"
                        elif action == "native_requalify":
                            if _one("confirm_value") != "yes":
                                raise SourceRepairError("Confirm review of the retained native inputs and current sources.")
                            action_id = uuid4().hex
                            native_result = prepare_native(action_id, _spell_origin_request())
                            candidate = native_result.candidate.to_dict()
                            _review_state, delta = native_evaluation(native_result)
                            extra = {"action_id": action_id,
                                     "native_proof_digest": canonical_digest({"provenance": native_result.provenance,
                                                                             "authorizations": native_result.authorizations,
                                                                             "state": native_state(native_result)})}
                            if "spell_origin_plan" in native_result.provenance:
                                extra["spell_origin_request"] = native_result.provenance["spell_origin_plan"]["request"]
                            summary = ("Confirm current spell roles, migrate feature grants, and preserve play state"
                                       if native_result.provenance.get("schema_version") in {5, 6} else
                                       "Migrate source-feature spell grants, preserve historical observations, and revalidate native values"
                                       if "spell_origin_plan" in native_result.provenance else
                                       "Revalidate retained native choices against current sources and derive current values")
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
                            confirmed_skill_level = str(request.form.get("confirmed_skill_level") or "").strip() or None
                            candidate, authorization = _numeric_candidate(
                                definition, state, target_kind=kind, target_id=target_id,
                                metric=metric, action_id=action_id,
                                confirmed_score=confirmed_score,
                                confirmed_fixed_bonus=confirmed_fixed_bonus,
                                confirmed_skill_level=confirmed_skill_level,
                                skill_authority=_skill_correction_authority(
                                    definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses,
                                    state_revision=record.state_record.revision,
                                    confirmed_skill_level=confirmed_skill_level,
                                ),
                            )
                            audit_action = "numeric_attest"
                            authorization_batch = _numeric_action_batch(candidate, authorization)
                            before_authority = _authority(definition, state, dependencies, campaign_slug, campaign, witnesses, numeric_witnesses, state_revision=record.state_record.revision)
                            after_authority = _authority(candidate, state, dependencies, campaign_slug, campaign, witnesses, (*numeric_witnesses, *authorization_batch), state_revision=record.state_record.revision)
                            grant_delta = _effect_delta(before_authority, after_authority)
                            delta = {**grant_delta, "statuses": _numeric_status_delta(before_authority, after_authority)}
                            if not any(row["path"] == target_id and row["after"] in {"MANUAL", "VERIFIED"} for row in delta["statuses"]):
                                raise SourceRepairError("This attestation did not prove the selected current value.")
                            extra = {"authorization": authorization,
                                     "authorizations": list(authorization_batch),
                                     "target_id": target_id, "target_kind": kind, "metric": metric,
                                     "confirmed_score": confirmed_score,
                                     "confirmed_fixed_bonus": confirmed_fixed_bonus,
                                     "confirmed_skill_level": confirmed_skill_level}
                            summary = (f"Correct {target_id} to {confirmed_skill_level.replace('_', ' ')} and derive its current bonus"
                                       if confirmed_skill_level is not None else
                                       f"Attest {target_id} ({metric}) from an independent manager confirmation")
                        else:
                            raise SourceRepairError("Unsupported manager action.")
                        if canonical_digest(candidate) == canonical_digest(definition):
                            raise SourceRepairError("The selected action does not change the Character.")
                        if action != "native_requalify":
                            dependencies.character_update_apply_engine.coordinator.check_source_repair_review(
                                record, CharacterDefinition.from_dict(candidate), record.import_metadata,
                                reviewed_transition_state, actor_id=actor_id,
                                replacement_relink_target=(target_id if action == "relink" and family == "feature" else ""),
                                same_physical_mapping=same_physical_mapping,
                                source_read_owner=(source_owner() if action == "relink" and family == "item"
                                    and same_physical_mapping is None else None))
                        context_proof_digest = (
                            _repair_context_proof_digest(candidate, family, target_id, connection=get_db())
                            if action == "relink" else ""
                        )
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
                            "context_proof_digest": context_proof_digest,
                        }
                        if action == "native_requalify":
                            source_owner().checkpoint()
                        token = _token_serializer().dumps(claims)
                        if len(token.encode("utf-8")) > 8192:
                            raise SourceRepairError("Review is too large.")
                        if action == "native_requalify":
                            _, native_audit_bytes = native_audit(
                                native_result, claims, hashlib.sha256(token.encode("utf-8")).hexdigest())
                        else:
                            dependencies.character_update_apply_engine.coordinator._prepare_update_audit(
                                operation_kind="character_update_apply",
                                audit_event_type="character_update_applied", audit_actor_user_id=actor_id,
                                audit_target_user_id=None,
                                audit_metadata=_ordinary_action_audit(claims,
                                    hashlib.sha256(token.encode("utf-8")).hexdigest(),
                                    actor_id=actor_id, audit_action=audit_action, audit_record=audit_record,
                                    authorization=authorization, authorization_batch=authorization_batch))
                        review = {"summary": summary, "effects": delta, "token": token}
                        if action == "native_requalify":
                            from .character_native_requalification import retained_requalification_inputs
                            from .character_source_authority import numeric_target_values
                            values = numeric_target_values(record.definition, state)
                            retained = []
                            for origin in retained_requalification_inputs(native_result.provenance):
                                key = (origin["target_kind"], origin["target_id"], origin["metric"])
                                value = values.get(key)
                                if key[2] == "base":
                                    value = f"{value.get('score')} ({value.get('stage')}; fixed bonus {value.get('fixed_bonus', 0)})"
                                elif key[1].startswith("skills."):
                                    value = value.get("proficiency_level")
                                retained.append({"target": key[1], "value": value,
                                                 "audit": origin["audit_id"], "generation": origin["generation"]["revision"]})
                            lineage = native_result.provenance["native_lineage"]
                            prior_audit = get_db().execute("SELECT metadata_json FROM auth_audit_log WHERE id=?", (lineage["audit_id"],)).fetchone()
                            prior_metadata = json.loads(prior_audit["metadata_json"])
                            source_links = []
                            for subject in ("species", "background"):
                                ref = dict(record.definition.profile.get(subject + "_ref") or {})
                                source_links.append(f"{subject.title()}: {ref.get('entry_key', '')}")
                            for row in [*record.definition.profile.get("classes", []), *record.definition.features, *record.definition.equipment_catalog]:
                                ref = dict(row.get("systems_ref") or {})
                                if ref.get("entry_key"):
                                    source_links.append(f"{row.get('name') or ref.get('title')}: {ref['entry_key']}")
                                elif row.get("page_ref"):
                                    source_links.append(f"{row.get('name')}: {row['page_ref']}")
                            review["native"] = {"inputs": retained, "sources": source_links,
                                                "audit_bytes": native_audit_bytes,
                                                "prior_source": prior_metadata.get("source_snapshot_digest", "retained native audit"),
                                                "current_source": native_result.provenance["source_snapshot_digest"],
                                                "background_tools": native_result.provenance["background_tools"],
                                                "capacities": [
                                                    {"label": template["label"], "current": row.get("current"),
                                                     "before": row.get("max"), "after": template["max"]}
                                                    for template in native_result.candidate.resource_templates
                                                    for row in state.get("resources", []) if row.get("id") == template["id"]
                                                ]}
                            if native_result.provenance.get("schema_version") == 6:
                                review["native"]["current_resource_inputs"] = deepcopy(native_result.provenance["current_resource_inputs"])
                            if "spell_origin_plan" in native_result.provenance:
                                review["native"]["spell_origins"] = native_result.provenance["spell_origin_plan"]
                                if native_result.provenance["schema_version"] in {4, 5, 6}:
                                    review["native"]["feature_grants"] = native_grant_review_guarded(native_result)
                                if native_result.provenance["schema_version"] in {5, 6}:
                                    checkpoint = native_result.provenance["spell_origin_plan"]["current_checkpoint"]
                                    review["native"]["current_spell_mode"] = checkpoint["mode"]
                                    from .character_spell_reconstruction import _marks as checkpoint_marks
                                    prepared_spells = {row["id"]: checkpoint_marks(row)[1]
                                                       for row in native_result.candidate.spellcasting.get("spells", [])}
                                    spell_names = {row["id"]: row.get("name", row["id"])
                                                   for row in native_result.candidate.spellcasting.get("spells", [])}
                                    review["native"]["current_spells"] = [
                                        {**entry, "name": spell_names[entry["spell_id"]],
                                         "prepared": prepared_spells[entry["spell_id"]]}
                                        for entry in checkpoint["entries"]]
                        if action == "relink" and family == "item":
                            review["links"] = _repair_link_review(definition, candidate, family, target_id)
                        if action == "native_requalify":
                            source_owner().checkpoint()
                    else:
                        abort(400)
                except SourceReadConnectionFatal:
                    raise
                except HTTPException:
                    raise
                except (SourceRepairError, CharacterStateConflictError, CharacterPublicationError, ActivationPrerequisiteError, CharacterStateValidationError) as exc:
                    review = None
                    activation_repair_required = isinstance(exc, ActivationPrerequisiteError)
                    outcome = str(exc) or "The reviewed Character changed. Refresh and review again."
                    status_code = 409
                    # Keep the original conflict and explicit cause available to
                    # the same optional private observer used for unexpected errors.
                    try:
                        observer = current_app.extensions.get("character_source_repair_failure_observer")
                        if callable(observer):
                            observer(exc)
                    except BaseException:
                        pass
                except Exception as exc:
                    # Optional private diagnostics cannot replace the original refusal.
                    # The observer owns bounded, nonsecret evidence; nothing is rendered.
                    try:
                        observer = current_app.extensions.get("character_source_repair_failure_observer")
                        if callable(observer):
                            observer(exc)
                    except BaseException:
                        pass
                    review = None
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
                outcome=outcome, activation_repair_required=activation_repair_required, active_nav="characters",
            ), status_code)
            response.headers["Cache-Control"] = "private, no-store"
            return response
        finally:
            if route_source_owner is not None:
                route_source_owner.close()
            if native_admission is not None:
                # Close the original shared lifetime on every route exit,
                # including partial capture, blocked context and idempotent
                # confirmation. Coordinator exit already closes a mutation;
                # independent saved-fact readback needs no live pending proof.
                native_admission.discard_native_admission()

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/source-repair",
        endpoint="character_source_repair_view",
        view_func=campaign_scope_access_required("characters")(view),
        methods=("GET", "POST"),
    )
