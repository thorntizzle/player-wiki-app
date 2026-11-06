"""Reviewed current class ownership for existing source-backed feature rows.

This does not acquire a feature, reconstruct history, migrate equipment, or
advance a level. Only the registered source-owned scaling contracts are eligible.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json

from .character_source_repair import SourceRepairError
from .systems_feature_values import current_contract, family_spec, source_digest


_ISSUER = object()


def _digest(value):
    return source_digest(value)


def _state_tuple(exact):
    return _digest({key: getattr(exact, key) for key in (
        "revision", "state_json", "updated_at", "updated_by_user_id")})


@dataclass(frozen=True, slots=True)
class PendingFeatureClassAssociation:
    feature_id: str
    class_row_id: str
    actor_id: int
    prior_generation: int
    prior_definition_digest: str
    prior_import_digest: str
    prior_state_digest: str
    prior_state_tuple_digest: str
    candidate_digest: str
    source_basis_digest: str
    _seal: object = field(repr=False, compare=False)

    def descriptor(self):
        return {name: getattr(self, name) for name in self.__slots__ if name != "_seal"}

    def validate_binding(self, prior_record, definition, state, actor_id, *, import_metadata=None):
        from .character_models import CharacterDefinition
        if (type(self) is not PendingFeatureClassAssociation or self._seal is not _ISSUER
                or type(actor_id) is not int or actor_id != self.actor_id
                or prior_record.committed_revision != self.prior_generation
                or _digest(prior_record.definition.to_dict()) != self.prior_definition_digest
                or _digest(prior_record.import_metadata.to_dict()) != self.prior_import_digest
                or _digest(prior_record.state_record.state) != self.prior_state_digest
                or _digest(state) != self.prior_state_digest
                or (import_metadata is not None
                    and _digest(import_metadata.to_dict()) != self.prior_import_digest)):
            raise SourceRepairError("The reviewed class association no longer matches this Character.")
        payload = definition.to_dict() if isinstance(definition, CharacterDefinition) else definition
        expected = deepcopy(prior_record.definition.to_dict())
        matches = [row for row in expected["features"] if row.get("id") == self.feature_id]
        if len(matches) != 1 or matches[0].get("class_row_id") not in (None, ""):
            raise SourceRepairError("Only one missing existing feature association can be repaired.")
        matches[0]["class_row_id"] = self.class_row_id
        if _digest(payload) != self.candidate_digest or _digest(payload) != _digest(expected):
            raise SourceRepairError("Class association repair must preserve every other Character field.")


def prepare_association_state(prior_record, definition, state, association, actor_id, *,
                              import_metadata=None, exact_state_json=None):
    """Retain the actual durable tuple, never normalize legacy play state."""
    from .character_store import CharacterStateStore, PreparedCharacterState
    from .character_equipment_activation import native_activation_readiness
    if type(association) is not PendingFeatureClassAssociation:
        raise SourceRepairError("A genuine reviewed feature association is required.")
    association.validate_binding(prior_record, definition, state, actor_id,
                                 import_metadata=import_metadata)
    native_activation_readiness(prior_record, definition, state, final=True)
    exact = CharacterStateStore().get_exact_state(
        prior_record.definition.campaign_slug, prior_record.definition.character_slug)
    if (exact is None or _state_tuple(exact) != association.prior_state_tuple_digest
            or _digest(exact.state) != association.prior_state_digest
            or (exact_state_json is not None and exact.state_json != exact_state_json)):
        raise SourceRepairError("The exact retained play state changed before association repair.")
    return PreparedCharacterState(deepcopy(state), exact.state_json)


def _unchanged_authority(before, after):
    """A class association cannot silently qualify unrelated benefits or choices."""
    fields = ("grants", "statuses", "field_statuses", "resource_statuses", "warnings",
              "verified_class_rows", "verified_spell_grants", "verified_spell_choices",
              "current_spell_keys", "spell_choice_ledger", "native_grant_view",
              "verified_source_rows", "verified_formula_rows", "active_item_ids",
              "native_grant_owners", "managed_pool_owners", "native_ritual_spell_keys",
              "native_choice_ledger_json", "confirmed_active_spell_choices",
              "confirmed_retired_spell_choices", "reconstructed_spell_roles",
              "native_grant_custody_confirmed", "managed_resource_targets",
              "slot_grant_context_json", "wizard_rule_context_json",
              "equipment_hand_rows", "verified_manual_actions", "verified_numeric_actions",
              "disputed_source_rows", "inert_page_companions", "requested_active_item_ids",
              "unqualified_native_aggregate_adjustments", "spell_property_bases",
              "spell_property_clear_owners")
    def plain(value):
        if hasattr(value, "__dataclass_fields__"):
            return plain(asdict(value))
        if isinstance(value, dict):
            return {key: plain(item) for key, item in value.items()}
        if isinstance(value, (set, frozenset)):
            return sorted((plain(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        return value
    if any(_digest(plain(getattr(before, name, None))) != _digest(plain(getattr(after, name, None)))
           for name in fields):
        raise SourceRepairError("An unrelated benefit or choice needs separate review before association repair.")
    # Baseline dependency fingerprints include the complete feature-owner
    # selection. They must refresh when that selection changes, even when the
    # independently compared numeric owner decisions and values are identical.
    # Other resource dependency fingerprints must remain exact.
    from .character_source_authority import NATIVE_BASELINE_FIELDS
    old_basis, new_basis = dict(before.resource_basis_digests), dict(after.resource_basis_digests)
    if (old_basis.keys() != new_basis.keys()
            or any(old_basis[key] != new_basis[key] for key in old_basis
                   if key not in NATIVE_BASELINE_FIELDS)):
        raise SourceRepairError("A resource dependency needs separate review before association repair.")
    # selection_json is the bound raw owner input, not an entitlement. Compare
    # every interpreted replacement/resource decision independently of it.
    old_composition, new_composition = plain(before.feature_composition), plain(after.feature_composition)
    if isinstance(old_composition, dict) and isinstance(new_composition, dict):
        old_composition.pop("selection_json", None)
        new_composition.pop("selection_json", None)
    if _digest(old_composition) != _digest(new_composition):
        raise SourceRepairError("A feature composition decision needs separate review before association repair.")


def prepare_feature_class_association(record, feature_id, class_row_id, actor_id, *,
                                      systems_service, before_authority, after_authority_builder):
    """Issue one plan from current verified source facts; no data writes."""
    from .character_feature_values import _exact_entry
    from .character_source_authority import numeric_value_digest
    from .character_store import CharacterStateStore
    from .character_feature_composition import CLAIM_FIELD
    from .character_models import CharacterDefinition
    if (type(actor_id) is not int or actor_id < 1 or type(feature_id) is not str
            or type(class_row_id) is not str or not feature_id or not class_row_id
            or record.definition.system != "DND-5E"):
        raise SourceRepairError("Choose one existing feature and its owning class.")
    definition = record.definition
    if before_authority is None:
        raise SourceRepairError("Current Character source authority is unavailable.")
    original = before_authority.original_definition_digest or before_authority.definition_digest
    if (original != numeric_value_digest(definition.to_dict())
            or before_authority.state_digest != numeric_value_digest(record.state_record.state)
            or before_authority.state_revision != record.state_record.revision):
        raise SourceRepairError("Current Character source authority is unavailable.")
    features = [row for row in definition.features if row.get("id") == feature_id]
    classes = [row for row in definition.profile.get("classes", []) if row.get("row_id") == class_row_id]
    if len(features) != 1 or len(classes) != 1:
        raise SourceRepairError("Choose unique existing feature and class rows.")
    feature, owner = features[0], classes[0]
    if (feature.get("class_row_id") not in (None, "") or feature.get("page_ref")
            or feature.get("tracker_ref") not in (None, "")
            or "native_acquisition" in feature or CLAIM_FIELD in feature or owner.get("page_ref")
            or before_authority.status_for("feature", feature_id) != "VERIFIED"
            or class_row_id not in before_authority.verified_class_rows):
        raise SourceRepairError("This existing feature needs a different maintenance path.")
    campaign = definition.campaign_slug
    entry = _exact_entry(systems_service, campaign, feature.get("systems_ref"))
    class_entry = _exact_entry(systems_service, campaign, owner.get("systems_ref"))
    spec = family_spec(entry.entry_key) if entry is not None else None
    contract = current_contract(entry) if spec else None
    level = owner.get("level")
    possible = [row for row in definition.profile.get("classes", [])
                if type(row) is dict and dict(row.get("systems_ref") or {}).get("entry_key") == (spec or {}).get("owner")]
    if (contract is None or class_entry is None or class_entry.entry_key != contract["owner"]
            or len(possible) != 1 or possible[0].get("row_id") != class_row_id
            or type(level) is not int or not contract["level"] <= level <= 20):
        raise SourceRepairError("The exact current source does not establish an attained unique class owner.")
    candidate = deepcopy(definition.to_dict())
    next(row for row in candidate["features"] if row["id"] == feature_id)["class_row_id"] = class_row_id
    desired = CharacterDefinition.from_dict(candidate)
    after = after_authority_builder(candidate)
    if after.status_for("feature", feature_id) != "VERIFIED" or class_row_id not in after.verified_class_rows:
        raise SourceRepairError("The proposed class association is not currently qualified.")
    _unchanged_authority(before_authority, after)
    exact = CharacterStateStore().get_exact_state(campaign, definition.character_slug)
    if exact is None or exact.revision != record.state_record.revision:
        raise SourceRepairError("Retained Character state is unavailable.")
    basis = _digest({"feature_source": {"key": entry.entry_key, "metadata": entry.metadata, "body": entry.body},
                     "class_source": {"key": class_entry.entry_key, "metadata": class_entry.metadata, "body": class_entry.body},
                     "class_row": owner, "snapshot": before_authority.source_snapshot_digest})
    plan = PendingFeatureClassAssociation(feature_id, class_row_id, actor_id, record.committed_revision,
        _digest(definition.to_dict()), _digest(record.import_metadata.to_dict()),
        _digest(record.state_record.state), _state_tuple(exact), _digest(candidate), basis, _ISSUER)
    prepare_association_state(record, desired, record.state_record.state, plan, actor_id,
                               import_metadata=record.import_metadata)
    return plan, desired, after
