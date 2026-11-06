"""One reviewed, current-level missing tracker; no acquisition or normalization."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json

from .character_source_repair import SourceRepairError, add_numeric_authorization, numeric_authorization_record
from .character_source_authority import numeric_value_digest as digest

_ISSUER = object()


def _state_tuple(exact):
    return digest({key: getattr(exact, key) for key in (
        "revision", "state_json", "updated_at", "updated_by_user_id")})


@dataclass(frozen=True, slots=True)
class PendingManagedResourceRestoration:
    feature_id: str
    resource_id: str
    class_row_id: str
    current: int
    actor_id: int
    action_id: str
    prior_generation: int
    prior_definition_digest: str
    prior_import_digest: str
    prior_state_digest: str
    prior_state_tuple_digest: str
    candidate_digest: str
    desired_state_digest: str
    source_basis_digest: str
    template_json: str
    authorization_json: str
    _seal: object = field(repr=False, compare=False)

    @property
    def template(self):
        return json.loads(self.template_json)

    @property
    def authorization(self):
        return json.loads(self.authorization_json)

    def descriptor(self):
        return {key: getattr(self, key) for key in self.__slots__ if key != "_seal"}

    def validate_binding(self, prior_record, definition, state, actor_id, *, import_metadata=None):
        from .character_service import build_resource_state
        if (type(self) is not PendingManagedResourceRestoration or self._seal is not _ISSUER
                or type(actor_id) is not int or actor_id != self.actor_id
                or prior_record.committed_revision != self.prior_generation
                or digest(prior_record.definition.to_dict()) != self.prior_definition_digest
                or digest(prior_record.import_metadata.to_dict()) != self.prior_import_digest
                or digest(prior_record.state_record.state) != self.prior_state_digest
                or import_metadata is not None and digest(import_metadata.to_dict()) != self.prior_import_digest):
            raise SourceRepairError("The reviewed tracker no longer matches this Character.")
        payload = definition.to_dict()
        expected = deepcopy(prior_record.definition.to_dict())
        rows = [row for row in expected["features"] if row.get("id") == self.feature_id]
        if len(rows) != 1 or rows[0].get("tracker_ref") not in (None, ""):
            raise SourceRepairError("Only one missing existing feature tracker can be restored.")
        rows[0]["tracker_ref"] = self.resource_id
        expected["resource_templates"].append(self.template)
        expected = add_numeric_authorization(expected, self.authorization)
        expected_state = deepcopy(prior_record.state_record.state)
        expected_state["resources"].append(build_resource_state(self.template))
        if (digest(payload) != self.candidate_digest or digest(payload) != digest(expected)
                or digest(state) != self.desired_state_digest or digest(state) != digest(expected_state)):
            raise SourceRepairError("Tracker restoration must preserve every other Character and play field.")


def prepare_restoration_state(prior_record, definition, state, restoration, actor_id, *,
                              import_metadata=None, exact_state_json=None):
    """Append only the reviewed resource, retaining every opaque existing value."""
    from .character_store import CharacterStateStore, PreparedCharacterState
    from .character_equipment_activation import require_update_activation, native_activation_readiness
    if type(restoration) is not PendingManagedResourceRestoration:
        raise SourceRepairError("A genuine reviewed tracker restoration is required.")
    restoration.validate_binding(prior_record, definition, state, actor_id, import_metadata=import_metadata)
    if "equipment_activation" not in prior_record.state_record.state:
        raise SourceRepairError("Equipment activation needs separate manager repair.")
    require_update_activation(prior_record, definition, state, actor_id=actor_id)
    native_activation_readiness(prior_record, definition, state, final=True)
    exact = CharacterStateStore().get_exact_state(definition.campaign_slug, definition.character_slug)
    if (exact is None or _state_tuple(exact) != restoration.prior_state_tuple_digest
            or digest(exact.state) != restoration.prior_state_digest
            or exact_state_json is not None and exact.state_json != exact_state_json):
        raise SourceRepairError("The exact retained play state changed before tracker restoration.")
    return PreparedCharacterState(deepcopy(state), json.dumps(state, ensure_ascii=False, sort_keys=True))


def _preserved_authority(before, after, resource_id, marker):
    """Compare all interpreted authority outside the explicitly restored owner."""
    target = "resource:" + resource_id
    from .character_source_authority import _numeric_witness_identity, NATIVE_BASELINE_FIELDS
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
    # These identify raw frames, not entitlements. Every interpreted decision
    # is compared below; resource dependency changes outside the target refuse.
    ignored = {"definition_digest", "original_definition_digest", "state_digest",
               "source_snapshot_digest", "resource_statuses", "resource_basis_digests",
               "managed_resource_targets", "managed_pool_owners", "verified_numeric_actions",
               "feature_composition"}
    for name in before.__dataclass_fields__:
        if name not in ignored and digest(plain(getattr(before, name))) != digest(plain(getattr(after, name))):
            raise SourceRepairError("An unrelated benefit or choice needs separate review before tracker restoration.")
    if ([row for row in before.resource_statuses if row.path != target]
            != [row for row in after.resource_statuses if row.path != target]
            or {key: value for key, value in before.resource_basis_digests
                if key != target and key not in NATIVE_BASELINE_FIELDS}
            != {key: value for key, value in after.resource_basis_digests
                if key != target and key not in NATIVE_BASELINE_FIELDS}
            or type(before.managed_resource_targets) is not frozenset
            or type(after.managed_resource_targets) is not frozenset
            or before.managed_resource_targets != after.managed_resource_targets - {resource_id}
            or set(after.verified_numeric_actions) - set(before.verified_numeric_actions) - {_numeric_witness_identity(marker)}
            or set(before.verified_numeric_actions) - set(after.verified_numeric_actions)):
        raise SourceRepairError("An unrelated resource owner changed during tracker restoration.")
    # Native baseline recipes fingerprint the whole feature selection. A new
    # tracker reference can change that fingerprint without changing any output.
    # All field statuses/values and custody were compared above; markers are
    # retained exactly and publication independently refuses transition renewals.
    if ({key for key, _ in before.resource_basis_digests if key in NATIVE_BASELINE_FIELDS}
            != {key for key, _ in after.resource_basis_digests if key in NATIVE_BASELINE_FIELDS}):
        raise SourceRepairError("A native baseline recipe needs separate review.")
    def pools(authority):
        return [row for row in authority.managed_pool_owners
                if json.loads(row).get("template", {}).get("id") != resource_id]
    if pools(before) != pools(after):
        raise SourceRepairError("An unrelated managed pool changed during tracker restoration.")
    old, new = plain(before.feature_composition), plain(after.feature_composition)
    if isinstance(old, dict) and isinstance(new, dict):
        old.pop("selection_json", None)
        new.pop("selection_json", None)
    if old != new:
        raise SourceRepairError("Feature composition needs separate review before tracker restoration.")


def prepare_managed_resource_restoration(record, feature_id, current, actor_id, action_id, *,
                                         systems_service, pages, before_authority, authority_builder):
    """Derive one already attained exact source/class/member tracker at this level."""
    from .character_models import CharacterDefinition
    from .character_feature_trackers import build_managed_resource_tracker_template
    from .managed_resource_registry import resolve_managed_resource_family_and_member, managed_resource_feature_identity
    from .character_source_authority import (_current_managed_pool_owners, _eligible_page_records,
        _qualified_current_managed_templates, numeric_target_owner_digest)
    from .character_equipment_activation import effective_definition
    from .character_service import build_resource_state
    from .character_store import CharacterStateStore
    definition, state = record.definition, record.state_record.state
    if (definition.system != "DND-5E" or type(actor_id) is not int or actor_id < 1
            or type(feature_id) is not str or not feature_id or type(current) is not int
            or not 0 <= current <= 2147483647 or type(action_id) is not str or not 1 <= len(action_id) <= 128
            or type(state.get("resources")) is not list or before_authority is None
            or (before_authority.original_definition_digest or before_authority.definition_digest) != digest(definition.to_dict())
            or before_authority.state_digest != digest(state)
            or before_authority.state_revision != record.state_record.revision):
        raise SourceRepairError("Choose one existing feature and an explicit bounded current amount.")
    def unique(rows, key):
        ids = [row.get(key) if type(row) is dict else None for row in rows]
        return all(type(value) is str and value and value == value.strip() for value in ids) and len(ids) == len(set(ids))
    if not all((unique(definition.features, "id"), unique(definition.resource_templates, "id"),
                unique(state["resources"], "id"), unique(definition.profile.get("classes", []), "row_id"))):
        raise SourceRepairError("Feature, class or resource identities need separate repair.")
    matches = [row for row in definition.features if row["id"] == feature_id]
    if len(matches) != 1:
        raise SourceRepairError("Choose one unique existing feature.")
    feature = matches[0]
    markers = definition.source.get("source_authorizations", [])
    if type(markers) is not list or any(type(row) is not dict for row in markers):
        raise SourceRepairError("Existing numeric authorizations need separate repair.")
    row_id = feature.get("class_row_id")
    owners = [row for row in definition.profile.get("classes", []) if row.get("row_id") == row_id]
    family, member = resolve_managed_resource_family_and_member(feature)
    identity = managed_resource_feature_identity(feature)
    tracker_id = dict((member or {}).get("tracker") or {}).get("id")
    member_tracker_ids = [dict((resolve_managed_resource_family_and_member(row)[1] or {}).get("tracker") or {}).get("id")
                          for row in definition.features]
    if (not family or not member or not identity or not tracker_id or len(owners) != 1
            or feature.get("page_ref") or feature.get("tracker_ref") not in (None, "")
            or before_authority.status_for("feature", feature_id) != "VERIFIED"
            or row_id not in before_authority.verified_class_rows
            or sum(managed_resource_feature_identity(row) == identity for row in definition.features) != 1
            or member_tracker_ids.count(tracker_id) != 1
            or any(row.get("tracker_ref") == tracker_id for row in definition.features)
            or any(row.get("id") == tracker_id for row in [*definition.resource_templates, *state["resources"]])
            or any(row.get("target_id") == "resource:" + tracker_id
                   for row in markers)):
        raise SourceRepairError("This source/class/member tracker is not uniquely missing.")
    owner = owners[0]
    level = owner.get("level")
    if type(level) is not int or not 1 <= level <= 20:
        raise SourceRepairError("The current owning class level is unavailable.")
    scores = {key: before_authority.field_status(f"stats.ability_scores.{key}.score").effective
              for key in ("str", "dex", "con", "int", "wis", "cha")
              if before_authority.field_status(f"stats.ability_scores.{key}.score").is_effective}
    template = build_managed_resource_tracker_template(member, feature, ability_scores=scores,
        current_level=level, display_order=len(definition.resource_templates),
        total_character_level=sum(row["level"] for row in definition.profile["classes"]
                                  if type(row.get("level")) is int))
    if template is None:
        raise SourceRepairError("The managed tracker recipe is unavailable.")
    template.pop("activation_type", None)
    template.update(class_row_id=row_id, initial_current=current)
    candidate = deepcopy(definition.to_dict())
    next(row for row in candidate["features"] if row["id"] == feature_id)["tracker_ref"] = tracker_id
    candidate["resource_templates"].append(template)
    structural = CharacterDefinition.from_dict(candidate)
    structural_authority = authority_builder(candidate, state, ())
    effective, _ = effective_definition(structural, state)
    pools = _current_managed_pool_owners(effective, systems_service=systems_service,
        pages=_eligible_page_records(pages), verified_class_rows=structural_authority.verified_class_rows,
        feature_statuses=structural_authority.statuses, feature_composition=structural_authority.feature_composition)
    qualified = _qualified_current_managed_templates(structural_authority, effective,
        systems_service=systems_service, campaign_page_records=pages).get(tracker_id)
    if (tracker_id not in pools or qualified is None or type(qualified.get("max")) is not int
            or not 0 <= current <= qualified["max"]):
        raise SourceRepairError("The exact attained source owner does not prove this current amount and maximum.")
    candidate["resource_templates"][-1] = qualified
    structural = CharacterDefinition.from_dict(candidate)
    desired_state = deepcopy(state)
    desired_state["resources"].append(build_resource_state(qualified))
    marker = numeric_authorization_record(character_slug=definition.character_slug, target_kind="resource",
        target_id="resource:" + tracker_id, metric="owner_reset", raw_value=qualified,
        action_id=action_id, provenance="manager", owner_digest=numeric_target_owner_digest(
            structural, desired_state, "resource", "resource:" + tracker_id, "owner_reset"))
    candidate = add_numeric_authorization(candidate, marker)
    desired = CharacterDefinition.from_dict(candidate)
    after = authority_builder(candidate, desired_state, (marker,))
    status = after.resource_status("resource", tracker_id)
    if not status.is_effective or status.effective != qualified:
        raise SourceRepairError("The reviewed tracker cannot qualify its exact current capacity.")
    _preserved_authority(before_authority, after, tracker_id, marker)
    exact = CharacterStateStore().get_exact_state(definition.campaign_slug, definition.character_slug)
    if exact is None or exact.revision != record.state_record.revision:
        raise SourceRepairError("Retained Character state is unavailable.")
    basis = digest({"pool": pools[tracker_id], "template": qualified,
                    "snapshot": after.source_snapshot_digest})
    plan = PendingManagedResourceRestoration(feature_id, tracker_id, row_id, current, actor_id, action_id,
        record.committed_revision, digest(definition.to_dict()), digest(record.import_metadata.to_dict()),
        digest(state), _state_tuple(exact), digest(candidate), digest(desired_state), basis,
        json.dumps(qualified, sort_keys=True), json.dumps(marker, sort_keys=True), _ISSUER)
    prepare_restoration_state(record, desired, desired_state, plan, actor_id, import_metadata=record.import_metadata)
    return plan, desired, desired_state, after
