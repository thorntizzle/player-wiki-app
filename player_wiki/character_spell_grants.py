"""Version one source-feature spell grant contract.

Public wire contract (all mappings are JSON objects, never authority claims):

* ``source.native_acquisitions`` = {schema_version: 1, intent: mapping,
  owners: [owner]}. Owner = {owner_id, acquisition_id, source_ref,
  class_row_id, grant_rule_id, choice_slot_id}. ``source_ref`` identifies an
  exact Systems publication; existing feature IDs remain opaque occurrence IDs.
* ``spellcasting.native_spell_grants`` = {schema_version: 1,
  occurrences: [occurrence], migration_edges: [edge]}. Occurrence = {id,
  owner_id, acquisition_id, source_ref, class_row_id, rule_id, leaf_id,
  spell_ref, source_basis_digest}. Edge = {old_spell_id, grant_ids,
  unresolved_observation_digest}. Edges authenticate custody, not entitlement.
* ``entry.metadata.native_spell_grants`` = {schema_version: 1, basis:
  {owner: source_basis, contexts: [source_basis]}, rules: [{id,
  unlock_level, leaves: [{id, spell_ref, contributions, casting,
  conditions, usage_ref}]}]}. Source basis = {entry_key, metadata_sha256,
  body_sha256}; the owner's metadata hash excludes native_spell_grants.
  Contributions admit independent always_prepared, bonus_known, ritual,
  counts_against_prepared and counts_against_known explicit booleans.
  Missing is UNKNOWN; null/malformed/unsupported is not false. Only empty
  conditions and owning-class casting/existing class slots are automated here.

Identity is owner/acquisition + authored rule/leaf + exact spell publication.
Revisions and payload digests establish currentness, never occurrence identity.
``build_occurrences`` returns (grant_model, acquisition_frame), without writing.
``prepare_feature_grant_migration`` returns (definition, model); it changes only
the two versioned containers and preserves every raw spell observation.
``qualify_native_grants`` returns a GrantView; stored status is never trusted.
``project_native_spellcasting`` consumes that view and existing qualified class/
item adapters. Its spell rows expose grant_origins, casting_paths and
grant_unknown_observations. It never grants effects from raw flags or labels.

Acquisition callers strip the private input key before inserting the validated
AcquisitionContext. They preserve that typed object before string normalization;
only native_acquisition_intent is public. Existing tokens are never replaced.
Confirmed creation/progression/migration audit custody is represented by the
request-local NativeGrantCustody type, never a client/stored VERIFIED boolean.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import secrets
from typing import Any, Mapping

SCHEMA_VERSION = 1
ACQUISITION_FIELD = "native_acquisition_intent"
TRUSTED_ACQUISITION_KEY = "_native_acquisition_context"
CLASS_CHOICE_STATE_FIELD = "native_class_choice_state"
ACQUISITION_MAX_AGE = 600
ACQUISITION_SALT = "character-native-acquisition-v1"
CONTRIBUTIONS = frozenset({"always_prepared", "bonus_known", "ritual",
                           "counts_against_prepared", "counts_against_known"})


class GrantContractError(ValueError):
    """A source, intent or model is outside the complete supported contract."""


def native_class_choice_state(row):
    """Read representation only; neither enum value is an authority witness."""
    if CLASS_CHOICE_STATE_FIELD not in row:
        return None
    value = row[CLASS_CHOICE_STATE_FIELD]
    if (type(value) is not str or value not in {"active", "retired"}
            or type(row.get("id")) is not str or not _text(row.get("id"))
            or type(row.get("class_row_id")) is not str or not _text(row.get("class_row_id"))
            or _text(row.get("spell_source_row_id"))):
        raise GrantContractError("The native class choice decision is malformed or misplaced.")
    if publication_identity(row.get("systems_ref"))["entry_type"] != "spell":
        raise GrantContractError("The native class choice needs its exact spell publication.")
    return value


def native_class_choice_rows(definition):
    """Exact raw identity map, with no name or display-alias selection."""
    rows, identities = {}, {}
    for raw in definition.spellcasting.get("spells", []):
        if not isinstance(raw, dict):
            raise GrantContractError("The stored spell observations are malformed.")
        native_class_choice_state(raw)
        spell_id = raw.get("id")
        if not _text(spell_id) or spell_id in rows:
            raise GrantContractError("The stored spell choice identity is ambiguous.")
        if raw.get("class_row_id") and not raw.get("spell_source_row_id"):
            try:
                ref = publication_identity(raw.get("systems_ref"))
            except ValueError:
                ref = None
            if ref is not None:
                key = (raw["class_row_id"], ref["source_id"], ref["entry_key"])
                previous = identities.get(key)
                if previous is not None and (CLASS_CHOICE_STATE_FIELD in previous or CLASS_CHOICE_STATE_FIELD in raw):
                    raise GrantContractError("The typed class choice has duplicate spell ownership.")
                identities[key] = raw
        rows[spell_id] = raw
    return rows


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AcquisitionContext:
    intent_id: str
    campaign_slug: str
    actor_id: int | None
    mode: str
    prior_revision: int | None
    prior_state_revision: int | None
    prior_definition_digest: str | None
    validated_token: str = field(default="", repr=False, compare=False)
    signed_issued_at: int | None = field(default=None, repr=False, compare=False)
    admitted_at: int | None = field(default=None, repr=False, compare=False)
    admission_validated: bool = field(default=False, repr=False, compare=False)

    def to_dict(self):
        return {"schema_version": 1, "intent_id": self.intent_id,
            "campaign_slug": self.campaign_slug, "system": "DND-5E",
            "actor_id": self.actor_id, "mode": self.mode,
            "prior_revision": self.prior_revision,
            "prior_state_revision": self.prior_state_revision,
            "prior_definition_digest": self.prior_definition_digest}


class NativeGrantCustody(dict):
    """Independently authenticated request-local model custody, not a marker."""

    def __init__(self, definition, *, origin):
        if (not isinstance(origin, tuple) or not origin or origin[0] not in {
                "confirmed_native_creation", "confirmed_native_progression", "confirmed_native_migration"}):
            raise GrantContractError("Only independently confirmed native audit custody is admissible.")
        super().__init__({"native_grant_model_digest": grant_model_digest(definition)})
        self.origin = origin


def is_confirmed_native_grant_custody(witness, definition):
    return (type(witness) is NativeGrantCustody
        and isinstance(witness.origin, tuple) and len(witness.origin) >= 4
        and witness.origin[0] in {"confirmed_native_creation", "confirmed_native_progression",
                                  "confirmed_native_migration"}
        and witness.get("native_grant_model_digest") == grant_model_digest(definition))


def _confirmed_target_grant_custody(custody, definition):
    return any(is_confirmed_native_grant_custody(witness, definition)
        and witness.origin[1:3] == (definition.campaign_slug, definition.character_slug)
        for witness in custody)


@dataclass(frozen=True, slots=True)
class GrantView:
    occurrences: tuple[dict[str, Any], ...] = ()
    diagnostics: tuple[dict[str, Any], ...] = ()
    migration_edges: tuple[dict[str, Any], ...] = ()

    def for_spell(self, spell_id):
        ids = {grant_id for edge in self.migration_edges
               if edge["old_spell_id"] == spell_id for grant_id in edge["grant_ids"]}
        return tuple(row for row in self.occurrences if row["id"] in ids
                     or row["id"] == spell_id or spell_id in row.get("display_spell_ids", [])
                     or grant_display_id(row) == spell_id)


@dataclass(frozen=True, slots=True)
class DraftGrantView:
    """Non-entitling preview facts. Never accepted by SourceAuthority or its loader."""
    occurrences: tuple[dict[str, Any], ...]
    diagnostics: tuple[dict[str, Any], ...]
    migration_edges: tuple[dict[str, Any], ...]
    model_digest: str
    source_digest: str


def has_native_grants(definition):
    return ("native_spell_grants" in dict(definition.spellcasting or {})
            or "native_acquisitions" in dict(definition.source or {}))


def grant_model_digest(definition):
    return canonical_digest({"acquisitions": definition.source.get("native_acquisitions"),
        "grants": definition.spellcasting.get("native_spell_grants")})


def validate_acquisition_context(definition, acquisition_context, *, actor_id=None,
                                  prior_definition=None, prior_custody=()):
    """Validate draft intent/owner facts; returns no witness or active authority."""
    validate_native_grant_model(definition)
    if (not isinstance(acquisition_context, AcquisitionContext)
            or acquisition_context.mode not in {"create", "progression"}
            or acquisition_context.campaign_slug != definition.campaign_slug
            or type(acquisition_context.actor_id) is not int
            or actor_id is not None and actor_id != acquisition_context.actor_id
            or canonical_digest(definition.source["native_acquisitions"]["intent"])
                != canonical_digest(acquisition_context.to_dict())):
        raise GrantContractError("Native grant acquisition intent is unavailable or changed.")
    retained = []
    if acquisition_context.mode == "progression":
        if (prior_definition is None
                or canonical_digest(prior_definition.to_dict()) != acquisition_context.prior_definition_digest
                or not _confirmed_target_grant_custody(prior_custody, prior_definition)):
            raise GrantContractError("Prior native grant custody is unavailable.")
        retained = prior_definition.source["native_acquisitions"]["owners"]
    for owner in definition.source["native_acquisitions"]["owners"]:
        if owner in retained:
            continue
        acquisition_id = feature_acquisition_id(acquisition_context,
            source_ref=owner["source_ref"], class_row_id=owner["class_row_id"],
            grant_rule_id=owner["grant_rule_id"], choice_slot_id=owner["choice_slot_id"])
        if (owner["acquisition_id"] != acquisition_id
                or owner["owner_id"] != owner_occurrence_id(acquisition_id=acquisition_id,
                    source_ref=owner["source_ref"], grant_rule_id=owner["grant_rule_id"],
                    choice_slot_id=owner["choice_slot_id"])):
            raise GrantContractError("A new feature occurrence lost its authenticated acquisition.")
    return None


def inspect_native_grant_proposal(definition, systems_service, *, acquisition_context=None,
        prior_definition=None, prior_custody=(), prior_generation=None,
        prior_definition_digest=None, prior_state_revision=None, actor_id=None):
    """Pure draft inspection, disjoint from every confirmed-witness pipeline.

    New acquisitions require the SAME authenticated submitted intent. Migration
    requires independently authenticated original generation parameters. Caller
    checks audit/generation custody; this function checks exact container rebuild
    and fresh sources without giving the draft any effective entitlement.
    """
    if acquisition_context is not None:
        validate_acquisition_context(definition, acquisition_context, actor_id=actor_id,
            prior_definition=prior_definition, prior_custody=prior_custody)
        retained = (prior_definition.source["native_acquisitions"]["owners"]
                    if prior_definition is not None else ())
        rebuilt, owners = build_occurrences(definition, systems_service,
            acquisition_context=acquisition_context, retained_owners=retained,
            migration_edges=definition.spellcasting["native_spell_grants"]["migration_edges"],
            prior_definition=prior_definition, prior_custody=prior_custody,
            prior_state_revision=prior_state_revision)
    else:
        if prior_definition is None:
            raise GrantContractError("A draft needs authenticated acquisition or original migration custody.")
        original, rebuilt = prepare_feature_grant_migration(prior_definition, systems_service,
            prior_generation=prior_generation, prior_definition_digest=prior_definition_digest,
            prior_state_revision=prior_state_revision)
        owners = original.source["native_acquisitions"]
    if (canonical_digest(rebuilt) != canonical_digest(definition.spellcasting["native_spell_grants"])
            or canonical_digest(owners) != canonical_digest(definition.source["native_acquisitions"])):
        raise GrantContractError("Draft source-feature acquisition facts changed.")
    inspected = _inspect_source_grants(definition, systems_service)
    return DraftGrantView(tuple({**row, "status": "DRAFT" if row["status"] == "SOURCE_SUPPORTED"
                                 else row["status"]} for row in inspected.occurrences),
        inspected.diagnostics, inspected.migration_edges, grant_model_digest(definition),
        canonical_digest(inspected.occurrences))


def build_native_grant_draft(definition, systems_service, *, acquisition_context,
                              prior_definition=None, prior_custody=()):
    """Builder preview names/source facts only; no casting math or entitlement.

    Uses the actual prospective profile/features and the same submitted intent,
    with one occurrence build. It cannot be passed as confirmed custody or as
    an effective GrantView, and never writes the supplied definition.
    """
    from .character_models import CharacterDefinition
    retained = ()
    if prior_definition is not None:
        if not _confirmed_target_grant_custody(prior_custody, prior_definition):
            raise GrantContractError("Prior acquisition custody is unavailable for this preview.")
        retained = prior_definition.source["native_acquisitions"]["owners"]
    model, owners = build_occurrences(definition, systems_service,
        acquisition_context=acquisition_context, retained_owners=retained,
        migration_edges=(prior_definition.spellcasting["native_spell_grants"]["migration_edges"]
                         if prior_definition is not None else ()),
        prior_definition=prior_definition, prior_custody=prior_custody)
    payload = deepcopy(definition.to_dict())
    payload["source"]["native_acquisitions"] = owners
    payload["spellcasting"]["native_spell_grants"] = model
    draft = CharacterDefinition.from_dict(payload)
    validate_acquisition_context(draft, acquisition_context,
        prior_definition=prior_definition, prior_custody=prior_custody)
    inspected = _inspect_source_grants(draft, systems_service, inspect_casting=False)
    return DraftGrantView(tuple({**row, "status": "DRAFT" if row["status"] == "SOURCE_SUPPORTED"
                                 else row["status"]} for row in inspected.occurrences),
        inspected.diagnostics, inspected.migration_edges, grant_model_digest(draft),
        canonical_digest(inspected.occurrences))


def native_grant_spell_ids(definition):
    """Raw display aliases of declared occurrences, never an eligibility claim."""
    model = validate_native_grant_model(definition)
    result = {edge["old_spell_id"] for edge in model["migration_edges"] if edge["grant_ids"]}
    for raw in definition.spellcasting.get("spells", []):
        if not isinstance(raw, dict) or raw.get("spell_source_row_id"):
            continue
        if any(raw.get("class_row_id") == row["class_row_id"]
               and isinstance(raw.get("systems_ref"), dict)
               and raw["systems_ref"].get("entry_key") == row["spell_ref"]["entry_key"]
               for row in model["occurrences"]):
            result.add(raw.get("id"))
    return frozenset(result)


def owner_occurrence_id(*, acquisition_id, source_ref, grant_rule_id, choice_slot_id):
    """Stable identity; callers supply an authenticated acquisition and authored slot."""
    return "feature:" + canonical_digest({"acquisition_id": acquisition_id,
        "source_ref": publication_identity(source_ref), "grant_rule_id": grant_rule_id,
        "choice_slot_id": choice_slot_id})


def publication_identity(source_ref):
    """Publication key includes its library; display title/slug are not identity."""
    if (not isinstance(source_ref, dict)
            or set(source_ref) - {"entry_key", "entry_type", "source_id", "slug", "title", "library_slug"}
            or any(not isinstance(source_ref.get(key), str) or not source_ref[key]
                   for key in ("entry_key", "entry_type", "source_id"))
            or any(not isinstance(value, str) or not value for value in source_ref.values())):
        raise GrantContractError("An exact publication reference is required.")
    return {key: source_ref[key] for key in ("entry_key", "entry_type", "source_id")}


def feature_acquisition_id(acquisition_context, *, source_ref, grant_rule_id,
                           choice_slot_id, class_row_id):
    if not isinstance(acquisition_context, AcquisitionContext):
        raise GrantContractError("An authenticated acquisition context is required.")
    return "acquisition:" + canonical_digest({"intent_id": acquisition_context.intent_id,
        "campaign_slug": acquisition_context.campaign_slug,
        "class_row_id": class_row_id, "source_ref": publication_identity(source_ref),
        "grant_rule_id": grant_rule_id, "choice_slot_id": choice_slot_id})


def validate_feature_grant_migration_custody(prior_definition, candidate, *,
        prior_generation, prior_definition_digest, prior_state_revision):
    """Historical custody only; current source qualification is a separate step."""
    return _validate_feature_grant_migration_custody(prior_definition, candidate,
        prior_generation, prior_definition_digest, prior_state_revision)


def occurrence_id(owner_id, acquisition_id, rule_id, leaf_id, spell_entry_key):
    return "spell-grant:" + canonical_digest([owner_id, acquisition_id, rule_id,
                                             leaf_id, spell_entry_key])


def grant_display_id(grant):
    aliases = grant.get("display_spell_ids", [])
    return (aliases[0] if len(aliases) == 1 else "spell-view:" + canonical_digest([
        grant.get("class_row_id"), grant.get("spell_ref", {}).get("entry_key")]))


def source_contract_basis(entry):
    """Full canonical source input hashes, excluding only the self-referential curation."""
    metadata = deepcopy(dict(entry.metadata or {}))
    metadata.pop("native_spell_grants", None)
    return {"entry_key": entry.entry_key, "metadata_sha256": canonical_digest(metadata),
            "body_sha256": canonical_digest(entry.body)}


def validate_native_grant_model(definition):
    """Return a deep-copied strict model; malformed presence never means legacy."""
    model = definition.spellcasting.get("native_spell_grants")
    acquisitions = definition.source.get("native_acquisitions")
    if (not isinstance(model, dict) or set(model) != {"schema_version", "occurrences", "migration_edges"}
            or type(model.get("schema_version")) is not int or model["schema_version"] != 1
            or not isinstance(acquisitions, dict)
            or set(acquisitions) != {"schema_version", "intent", "owners"}
            or type(acquisitions.get("schema_version")) is not int or acquisitions["schema_version"] != 1
            or not isinstance(acquisitions["intent"], dict)
            or type(acquisitions["owners"]) is not list
            or type(model["occurrences"]) is not list or type(model["migration_edges"]) is not list
            or len(model["occurrences"]) > 256 or len(acquisitions["owners"]) > 256
            or len(model["migration_edges"]) > 256):
        raise GrantContractError("Native grant model is incomplete or unsupported.")
    owner_fields = {"owner_id", "acquisition_id", "source_ref", "class_row_id",
                    "grant_rule_id", "choice_slot_id"}
    owners = {}
    for owner in acquisitions["owners"]:
        if (not isinstance(owner, dict) or set(owner) != owner_fields
                or any(not _text(owner[key]) for key in owner_fields - {"source_ref"})
                or owner["owner_id"] in owners):
            raise GrantContractError("Native feature acquisition ownership is ambiguous.")
        publication_identity(owner["source_ref"])
        owners[owner["owner_id"]] = owner
    occurrences, ids = {}, set()
    fields = {"id", "owner_id", "acquisition_id", "source_ref", "class_row_id",
              "rule_id", "leaf_id", "spell_ref", "source_basis_digest"}
    for row in model["occurrences"]:
        if (not isinstance(row, dict) or set(row) != fields
                or any(not _text(row[key]) for key in fields - {"source_ref", "spell_ref", "source_basis_digest"})
                or not _sha(row["source_basis_digest"]) or row["id"] in ids
                or row["owner_id"] not in owners):
            raise GrantContractError("Native grant occurrence is malformed or ambiguous.")
        owner = owners[row["owner_id"]]
        spell_ref = publication_identity(row["spell_ref"])
        if (spell_ref["entry_type"] != "spell" or publication_identity(row["source_ref"])
                != publication_identity(owner["source_ref"])
                or row["class_row_id"] != owner["class_row_id"]
                or row["acquisition_id"] != owner["acquisition_id"]
                or row["id"] != occurrence_id(row["owner_id"], row["acquisition_id"],
                    row["rule_id"], row["leaf_id"], spell_ref["entry_key"])):
            raise GrantContractError("Native grant identity does not match its acquisition.")
        ids.add(row["id"])
        occurrences[row["id"]] = row
    edges = set()
    spells = {row.get("id"): row for row in definition.spellcasting.get("spells", [])
              if isinstance(row, dict)}
    for edge in model["migration_edges"]:
        if (not isinstance(edge, dict) or set(edge) != {"old_spell_id", "grant_ids", "unresolved_observation_digest"}
                or not _text(edge["old_spell_id"]) or edge["old_spell_id"] in edges
                or type(edge["grant_ids"]) is not list
                or len(set(edge["grant_ids"])) != len(edge["grant_ids"])
                or any(grant_id not in ids for grant_id in edge["grant_ids"])
                or not _sha(edge["unresolved_observation_digest"])):
            raise GrantContractError("Native migration observation edges are malformed.")
        # Removed targets can survive only as historical edges; publication's
        # separately signed removal validates that semantic delta.
        raw = spells.get(edge["old_spell_id"])
        # This digest authenticates the original migration observation. Later
        # explicitly reviewed preparation changes do not rewrite that history.
        for grant_id in edge["grant_ids"]:
            row = occurrences[grant_id]
            if raw is not None and (raw.get("class_row_id") != row["class_row_id"]
                    or raw.get("spell_source_row_id")
                    or publication_identity(raw.get("systems_ref")) != publication_identity(row["spell_ref"])):
                raise GrantContractError("Migration changed the spell publication or owner.")
        edges.add(edge["old_spell_id"])
    return deepcopy(model)


def build_occurrences(definition, systems_service, *, acquisition_context,
                      retained_owners=(), migration_edges=(), prior_definition=None,
                      prior_custody=(), prior_state_revision=None):
    """Return (model, acquisitions); no definition mutation or custody assertion.

    Feature payloads carry native_acquisition={grant_rule_id,choice_slot_id}.
    Fixed class/subclass progression uses its exact entry_key as authored rule
    and slot. Repeated/optional acquisitions MUST supply an authored slot; a UI
    index/name is never accepted as an implicit slot. Existing authenticated
    owner records require the actual prior definition and confirmed target-bound
    custody. A migration mode label cannot authorize an original-frame binding;
    only prepare_feature_grant_migration enters that private path.
    """
    return _build_occurrences(definition, systems_service, acquisition_context,
        retained_owners, migration_edges, prior_definition=prior_definition,
        prior_custody=prior_custody, prior_state_revision=prior_state_revision)


def prepare_feature_grant_migration(definition, systems_service, *, prior_generation,
                                    prior_definition_digest, prior_state_revision):
    """Return (candidate, model), rebuilt from the original authenticated frame.

    All attained source leaves participate, not just four selected spell IDs.
    Raw rows/flags/preparation remain unchanged. The caller independently proves
    the original generation and includes the two-container digest in proof4.
    """
    return _prepare_feature_grant_migration(definition, systems_service,
        prior_generation, prior_definition_digest, prior_state_revision)


def qualify_native_grants(definition, systems_service, *, custody=()):
    """Fresh source/owner qualification plus separately authenticated model custody."""
    return _qualify_native_grants(definition, systems_service, custody)


def omit_redundant_native_spell_outputs(candidate, *, prior_definition, contributors, systems_service):
    """Omit only fresh automatic output completely replaced by current leaves.

    ``contributors`` is the actual producer's request-local, pre-merge partition,
    never persisted or accepted as custody. Every write to a spell key participates;
    ordinary/unsupported contributors prevent omission. Historical rows, markers,
    migration observations and player preparation are outside this operation.
    The returned definition is detached; neither input nor the model is mutated.
    """
    from .character_models import CharacterDefinition
    payload = deepcopy(candidate.to_dict())
    result = CharacterDefinition.from_dict(payload)
    if not has_native_grants(candidate) or contributors is None:
        return result
    model = validate_native_grant_model(candidate)
    intent = candidate.source["native_acquisitions"]["intent"]
    if (not isinstance(contributors, list) or systems_service is None
            or intent.get("mode") not in {"create", "progression"}
            or intent.get("campaign_slug") != candidate.campaign_slug
            or type(intent.get("actor_id")) is not int or intent["actor_id"] < 1
            or intent.get("mode") == "create" and prior_definition is not None
            or intent.get("mode") == "progression" and (prior_definition is None
                or intent.get("prior_definition_digest") != canonical_digest(prior_definition.to_dict()))):
        raise GrantContractError("Automatic output replacement needs its actual producer and original frame.")

    def key(raw):
        if (not isinstance(raw, dict) or type(raw.get("class_row_id")) is not str
                or not _text(raw["class_row_id"]) or raw.get("spell_source_row_id")):
            return None
        try:
            ref = publication_identity(raw.get("systems_ref"))
        except GrantContractError:
            return None
        return (raw["class_row_id"], ref["source_id"], ref["entry_key"]) if ref["entry_type"] == "spell" else None

    original_rows, original_markers, original_edges = [], [], []
    if prior_definition is not None:
        if (prior_definition.campaign_slug != candidate.campaign_slug
                or prior_definition.character_slug != candidate.character_slug
                or not has_native_grants(prior_definition)):
            raise GrantContractError("Automatic output replacement lost its actual prior owner.")
        original_model = validate_native_grant_model(prior_definition)
        original_rows = prior_definition.spellcasting.get("spells", [])
        original_markers = prior_definition.source.get("source_authorizations", [])
        original_edges = original_model["migration_edges"]
    rows = candidate.spellcasting.get("spells", [])
    if (not isinstance(rows, list) or not isinstance(original_rows, list)
            or not isinstance(original_markers, list)
            or any(not isinstance(row, dict) or type(row.get("id")) is not str
                   or not _text(row["id"]) for row in [*rows, *original_rows])
            or len({row["id"] for row in rows}) != len(rows)
            or len({row["id"] for row in original_rows}) != len(original_rows)
            or any(not isinstance(marker, dict) for marker in original_markers)):
        raise GrantContractError("The complete original automatic-output inventory is unavailable.")
    original_ids = {row["id"] for row in original_rows}
    if not original_ids <= {row["id"] for row in rows}:
        raise GrantContractError("Automatic output replacement cannot discard original spell observations.")
    can_omit = not any(marker.get("target_kind") == "spell_choice" and (
            type(marker.get("target_id")) is not str
            or marker["target_id"].removeprefix("spell_choice:") not in original_ids)
            for marker in original_markers)
    original_keys = {key(row) for row in original_rows if key(row) is not None}
    unresolved_owners = {row["class_row_id"] for row in original_rows
        if not row.get("spell_source_row_id") and key(row) is None
        and _text(row.get("class_row_id"))}
    if prior_definition is not None:
        from .character_profile import profile_class_rows
        profiles = profile_class_rows(prior_definition.profile)
        profile_ids = {row["row_id"] for row in profiles if _text(row.get("row_id"))}
        obligations = [row for row in original_rows if not row.get("spell_source_row_id")]
        obligations += original_model["occurrences"]
        obligations += prior_definition.source["native_acquisitions"]["owners"]
        if (len(profile_ids) != len(profiles)
                or any(not _text(row.get("class_row_id"))
                    or row["class_row_id"] not in profile_ids for row in obligations)):
            can_omit = False
    edge_ids = {edge["old_spell_id"] for edge in [*original_edges, *model["migration_edges"]]}
    records = {}
    for record in contributors:
        if not isinstance(record, dict) or type(record.get("was_suppressed")) is not bool:
            raise GrantContractError("The automatic-output contributor partition is incomplete.")
        emitted = record.get("payload")
        if (not record["was_suppressed"] and isinstance(emitted, dict)
                and _text(emitted.get("spell_source_row_id"))):
            continue  # Item/innate/source-row packages are outside this operation.
        identity = key({"class_row_id": record.get("class_row_id"), "systems_ref": record.get("spell_ref")})
        if identity is None:
            raise GrantContractError("An automatic-output contributor lost its exact spell owner.")
        records.setdefault(identity, []).append(record)

    # Creation has not derived class_rows/slot_lanes yet. Check the same source
    # adapters directly here; the later effective view still checks real lanes.
    inspected = _inspect_source_grants(candidate, systems_service, inspect_casting=False)
    from .character_profile import profile_class_rows
    from .character_builder_derivation import _spellcasting_ability_name_for_class
    from .character_builder_derivation import _spell_slot_progression_for_class_level
    available = []
    for occurrence in inspected.occurrences:
        if occurrence.get("status") != "SOURCE_SUPPORTED":
            continue
        owner = _exact_entry(systems_service, candidate.campaign_slug, occurrence["source_ref"])
        rules, basis = _source_rules(owner, systems_service, candidate.campaign_slug)
        leaves = [leaf for rule in rules for leaf in rule["leaves"]
            if rule["id"] == occurrence["rule_id"] and leaf["id"] == occurrence["leaf_id"]]
        if len(leaves) != 1 or basis != occurrence["source_basis_digest"]:
            raise GrantContractError("The automatic replacement source changed during inspection.")
        leaf = leaves[0]
        if leaf["casting"] == {"kind": "owning_class"}:
            profiles = [row for row in profile_class_rows(candidate.profile)
                if row.get("row_id") == occurrence["class_row_id"]]
            if len(profiles) != 1 or type(profiles[0].get("level")) is not int:
                continue
            profile = profiles[0]
            cls = _exact_entry(systems_service, candidate.campaign_slug, profile.get("systems_ref"), "class")
            subclass = (_exact_entry(systems_service, candidate.campaign_slug, profile["subclass_ref"], "subclass")
                        if profile.get("subclass_ref") else None)
            if subclass is not None and (subclass.metadata.get("class_name") != cls.title
                    or subclass.metadata.get("class_source") != cls.source_id):
                continue
            options = dict(selected_class=cls, selected_subclass=subclass)
            if not _spellcasting_ability_name_for_class(cls.title, row_level=profile["level"], **options):
                continue
            if leaf["usage_ref"] == {"kind": "class_slots"}:
                slots = _spell_slot_progression_for_class_level(cls.title, profile["level"], **options)
                if not any(type(slot.get("level")) is int and type(slot.get("max_slots")) is int
                           and slot["level"] > 0 and slot["max_slots"] > 0 for slot in slots):
                    continue
        # The owner's existing curated contract authenticates each full context.
        refs = {_ref(owner)["entry_key"]: _ref(owner)}
        for context in owner.metadata["native_spell_grants"]["basis"]["contexts"]:
            entry = systems_service.get_entry_for_campaign(candidate.campaign_slug, context["entry_key"])
            if (entry is None or canonical_digest(entry.metadata) != context["metadata_sha256"]
                    or canonical_digest(entry.body) != context["body_sha256"]):
                raise GrantContractError("The automatic replacement context changed during inspection.")
            refs[entry.entry_key] = _ref(entry)
        available.append((occurrence, leaf, refs))

    safe_fields = {"id", "name", "casting_time", "range", "duration", "components", "save_or_hit",
        "source", "reference", "mark", "is_always_prepared", "is_bonus_known", "is_ritual",
        "systems_ref", "class_row_id"}
    flags = {"is_always_prepared", "is_bonus_known", "is_ritual"}

    def covered_contribution(record, identity):
        """The same positive source closure governs suppression and omission."""
        semantics, emitted = record.get("semantics"), record.get("payload")
        if (set(record) != {"class_row_id", "spell_ref", "origin_kind", "source_ref", "semantics", "payload", "was_suppressed"}
                or type(record["was_suppressed"]) is not bool
                or record.get("origin_kind") != "automatic_class" or key(emitted) != identity
                or set(emitted) - safe_fields or not isinstance(semantics, dict)
                or any(type(emitted.get(flag)) is not bool for flag in flags)
                or set(semantics) != {"contributions", "casting", "usage_ref", "conditions"}
                or not isinstance(semantics["contributions"], dict) or not semantics["contributions"]
                or set(semantics["contributions"]) - CONTRIBUTIONS
                or any(type(value) is not bool for value in semantics["contributions"].values())
                or semantics["conditions"] != []
                or semantics["casting"] not in (None, {"kind": "owning_class"})
                or semantics["usage_ref"] not in (None, {"kind": "class_slots"})):
            return None
        if any(emitted[flag] is True and semantics["contributions"].get(field) is not True
                for flag, field in (("is_always_prepared", "always_prepared"), ("is_bonus_known", "bonus_known"))):
            return None
        try:
            source = _exact_entry(systems_service, candidate.campaign_slug, record["source_ref"])
            spell = _exact_entry(systems_service, candidate.campaign_slug, record["spell_ref"], "spell")
        except GrantContractError:
            return None
        if (emitted["is_ritual"] is True and spell.metadata.get("ritual") is not True
                and semantics["contributions"].get("ritual") is not True):
            # A publication's ritual tag does not grant a ritual casting path.
            return None
        matched = [leaf for occurrence, leaf, refs in available
            if (occurrence["class_row_id"], occurrence["spell_ref"]["source_id"], occurrence["spell_ref"]["entry_key"]) == identity
            and refs.get(source.entry_key) == _ref(source)
            and all(leaf[field] == semantics[field] for field in ("casting", "usage_ref", "conditions"))
            and all(leaf["contributions"].get(field) is value
                for field, value in semantics["contributions"].items())]
        return emitted if matched else None

    # An early native-owner skip is already an omission. Audit its complete
    # contribution even if no raw row exists or an ordinary sibling stays raw.
    for identity, group in records.items():
        for record in group:
            if record["was_suppressed"] and covered_contribution(record, identity) is None:
                raise GrantContractError("A suppressed automatic spell contribution lacks complete native replacement.")
    if not can_omit:
        return result  # Retain fresh output when original absence is unresolved.
    outside = deepcopy(payload)
    outside["spellcasting"]["spells"] = []

    def referenced(value, spell_id):
        if isinstance(value, dict):
            return any(referenced(child, spell_id) for child in value.values())
        if isinstance(value, list):
            return any(referenced(child, spell_id) for child in value)
        return type(value) is str and value in {spell_id, f"spell_choice:{spell_id}"}

    omitted = set()
    for row in rows:
        identity = key(row)
        group = records.get(identity, [])
        if (identity is None or not group or row["id"] in original_ids or identity in original_keys
                or row.get("class_row_id") in unresolved_owners or row["id"] in edge_ids
                or CLASS_CHOICE_STATE_FIELD in row or set(row) - safe_fields
                or referenced(outside, row["id"])):
            continue
        complete = True
        supplied = []
        for record in group:
            emitted = covered_contribution(record, identity)
            if emitted is None:
                complete = False
                break
            supplied.append(emitted)
        if not complete:
            continue
        # Cover the actual merged output too; custom/player facts never vanish
        # because a compatible automatic sibling happens to exist.
        if any(type(row.get(flag)) is not bool or any(type(part.get(flag)) is not bool for part in supplied)
                or row[flag] and not any(part[flag] for part in supplied) for flag in flags):
            continue
        marks = {part.strip() for emitted in supplied for part in str(emitted.get("mark") or "").split("+") if part.strip()}
        if not {part.strip() for part in str(row.get("mark") or "").split("+") if part.strip()} <= marks:
            continue
        if any(not any(field in emitted and emitted[field] == value for emitted in supplied)
                for field, value in row.items() if field not in {*flags, "id", "mark", "systems_ref"}):
            continue
        omitted.add(row["id"])
    payload["spellcasting"]["spells"] = [row for row in payload["spellcasting"]["spells"] if row["id"] not in omitted]
    result = CharacterDefinition.from_dict(payload)
    if validate_native_grant_model(result) != model:
        raise GrantContractError("Automatic output replacement changed its native source model.")
    return result


def project_native_spellcasting(definition, view, *, qualified_class_spells=(),
                                qualified_item_spells=(), confirmed_retired_spell_choices=(), choice_ledger=None):
    """One effective view. Adapters are ALREADY qualified, never raw fallbacks.

    Rows carry native_grant_projection=True, grant_fixed, grant_origins,
    casting_paths, grant_unknown_observations, grant_counts_against_prepared and
    grant_counts_against_known. Unknown count contributions are None; callers
    must not coerce them to a count exemption. AP/BK display bits describe only
    positive qualified contributions, not absence of other historical origins.
    """
    return _project_native_spellcasting(definition, view, qualified_class_spells,
                                        qualified_item_spells, confirmed_retired_spell_choices, choice_ledger)


def resolve_acquisition_intent(values, *, campaign_slug, actor_id, mode,
                               prior_record=None, allow_issue=False):
    """Validate one raw scalar token, or explicitly issue an initial GET intent."""
    from flask import current_app
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
    if mode == "level_up":
        mode = "progression"
    if (mode not in {"create", "progression"} or type(actor_id) is not int or actor_id < 1
            or not isinstance(campaign_slug, str) or not campaign_slug
            or type(allow_issue) is not bool):
        raise GrantContractError("Native acquisition context is unavailable.")
    prior_revision = prior_state_revision = prior_digest = None
    if mode == "progression":
        if prior_record is None:
            raise GrantContractError("Current progression custody is unavailable.")
        prior_revision = prior_record.committed_revision
        prior_state_revision = prior_record.state_record.revision
        prior_digest = canonical_digest(prior_record.definition.to_dict())
        if (type(prior_revision) is not int or prior_revision < 1
                or type(prior_state_revision) is not int or prior_state_revision < 1
                or prior_record.definition.campaign_slug != campaign_slug):
            raise GrantContractError("Current progression custody is unavailable.")
    elif prior_record is not None:
        raise GrantContractError("Creation cannot borrow progression custody.")
    # Observe the exact clock used by the existing successful age check.
    # Signature format, key derivation, clock and validity policy stay unchanged.
    from itsdangerous import TimestampSigner
    admission_clock = []
    class _AdmissionObservationSigner(TimestampSigner):
        def get_timestamp(self):
            observed = super().get_timestamp()
            admission_clock.append(observed)
            return observed
    signer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"],
        salt=ACQUISITION_SALT, signer=_AdmissionObservationSigner)
    present = ACQUISITION_FIELD in values
    if hasattr(values, "getlist") and present:
        supplied = values.getlist(ACQUISITION_FIELD)
        if len(supplied) != 1:
            raise GrantContractError("Choose one native acquisition intent.")
        token = supplied[0]
    else:
        token = values.get(ACQUISITION_FIELD)
    expected = AcquisitionContext("", campaign_slug, actor_id, mode, prior_revision,
        prior_state_revision, prior_digest).to_dict()
    if present:
        if not isinstance(token, str) or not token or len(token.encode("utf-8")) > 8192:
            raise GrantContractError("Native acquisition intent is malformed.")
        try:
            payload, signed_at = signer.loads(token, max_age=ACQUISITION_MAX_AGE,
                                              return_timestamp=True)
        except (BadSignature, SignatureExpired, TypeError, ValueError) as exc:
            raise GrantContractError("Native acquisition intent expired or changed.") from exc
        if (not isinstance(payload, dict) or set(payload) != set(expected)
                or not isinstance(payload.get("intent_id"), str)
                or len(payload["intent_id"]) != 64
                or any(payload[key] != value or type(payload[key]) is not type(value)
                       for key, value in expected.items() if key != "intent_id")):
            raise GrantContractError("Native acquisition intent no longer matches this character.")
    elif allow_issue:
        payload = {**expected, "intent_id": secrets.token_hex(32)}
        token = signer.dumps(payload)
        payload, signed_at = signer.loads(token, max_age=ACQUISITION_MAX_AGE,
                                          return_timestamp=True)
    else:
        raise GrantContractError("Refresh the native builder to obtain its acquisition intent.")
    if not admission_clock:
        raise GrantContractError("The successful intent admission clock is unavailable.")
    signed_issued_at = int(signed_at.timestamp())
    admitted_at = admission_clock[-1]
    if (type(admitted_at) is not int or type(signed_issued_at) is not int
            or not 0 <= admitted_at - signed_issued_at <= ACQUISITION_MAX_AGE):
        raise GrantContractError("The acquisition was not admitted within ordinary validity.")
    return token, AcquisitionContext(payload["intent_id"], campaign_slug, actor_id, mode,
        prior_revision, prior_state_revision, prior_digest, validated_token=token,
        signed_issued_at=signed_issued_at, admitted_at=admitted_at,
        admission_validated=True)


def _ref(entry):
    return {"entry_key": entry.entry_key, "entry_type": entry.entry_type,
            "source_id": entry.source_id}


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _text(value):
    return isinstance(value, str) and bool(value) and value == value.strip() and len(value) <= 512


def _exact_entry(service, campaign, ref, kind=None):
    identity = publication_identity(ref)
    entry = service.get_entry_for_campaign(campaign, identity["entry_key"])
    if (entry is None or _ref(entry) != identity or kind is not None and entry.entry_type != kind
            or any(key in ref and ref[key] != getattr(entry, key, None)
                   for key in ("slug", "title", "library_slug"))):
        raise GrantContractError("An exact current source publication is unavailable.")
    return entry


def _source_rules(entry, service, campaign):
    from .character_source_reads import phase_of, freeze, BuilderPhaseReader, SourceReadConflict
    if isinstance(service, BuilderPhaseReader):
        raise SourceReadConflict("A builder cache adapter cannot qualify source grants.")
    phase = phase_of(service)
    if phase is not None:
        actual = service.get_entry_for_campaign(campaign, entry.entry_key)
        if actual is None or freeze(actual) != freeze(entry):
            raise GrantContractError("Native grant publication differs from captured source facts.")
        return phase.resolve("native-source-rules", (campaign, entry),
                             lambda: _uncached_source_rules(entry, service, campaign),
                             domain_errors=(GrantContractError,))
    return _uncached_source_rules(entry, service, campaign)


def _uncached_source_rules(entry, service, campaign):
    raw = entry.metadata.get("native_spell_grants")
    if (not isinstance(raw, dict) or set(raw) != {"schema_version", "basis", "rules"}
            or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1
            or not isinstance(raw["basis"], dict) or set(raw["basis"]) != {"owner", "contexts"}
            or raw["basis"]["owner"] != source_contract_basis(entry)
            or type(raw["basis"]["contexts"]) is not list
            or len(raw["basis"]["contexts"]) > 32
            or type(raw["rules"]) is not list or not 1 <= len(raw["rules"]) <= 64):
        raise GrantContractError("Native fixed grants lack their complete authenticated source basis.")
    seen_contexts = {entry.entry_key}
    for basis in raw["basis"]["contexts"]:
        if (not isinstance(basis, dict) or set(basis) != {"entry_key", "metadata_sha256", "body_sha256"}
                or not _text(basis["entry_key"]) or basis["entry_key"] in seen_contexts
                or not _sha(basis["metadata_sha256"]) or not _sha(basis["body_sha256"])):
            raise GrantContractError("Native grant context is ambiguous.")
        context = service.get_entry_for_campaign(campaign, basis["entry_key"])
        if (context is None or canonical_digest(context.metadata) != basis["metadata_sha256"]
                or canonical_digest(context.body) != basis["body_sha256"]):
            raise GrantContractError("Native grant context changed or is unavailable.")
        seen_contexts.add(context.entry_key)
    rules, seen = [], set()
    for rule in raw["rules"]:
        if (not isinstance(rule, dict) or set(rule) != {"id", "unlock_level", "leaves"}
                or not _text(rule["id"]) or rule["id"] in seen
                or type(rule["unlock_level"]) is not int or not 1 <= rule["unlock_level"] <= 20
                or type(rule["leaves"]) is not list or not 1 <= len(rule["leaves"]) <= 256):
            raise GrantContractError("Native fixed grant rule is malformed.")
        seen.add(rule["id"])
        leaves = set()
        for leaf in rule["leaves"]:
            if (not isinstance(leaf, dict)
                    or set(leaf) != {"id", "spell_ref", "contributions", "casting", "conditions", "usage_ref"}
                    or not _text(leaf["id"]) or leaf["id"] in leaves
                    or not isinstance(leaf["contributions"], dict)
                    or not leaf["contributions"] or set(leaf["contributions"]) - CONTRIBUTIONS
                    or any(type(value) is not bool for value in leaf["contributions"].values())):
                raise GrantContractError("Native grant leaf or independent contribution is malformed.")
            publication_identity(leaf["spell_ref"])
            if leaf["spell_ref"]["entry_type"] != "spell":
                raise GrantContractError("A native grant must name an exact spell publication.")
            # Unsupported structures remain explicit refusal, never dropped clauses.
            if (type(leaf["conditions"]) is not list
                    or leaf["casting"] is not None and type(leaf["casting"]) is not dict
                    or leaf["usage_ref"] is not None and type(leaf["usage_ref"]) is not dict):
                raise GrantContractError("Native grant condition/usage declaration is malformed.")
            leaves.add(leaf["id"])
        rules.append(rule)
    return rules, canonical_digest(raw)


def _unique_raw_feature(definition, feature_id):
    # Uniqueness includes nongrant and unattained observations, not just owners.
    if not _text(feature_id):
        return None
    matches = [row for row in definition.features
               if isinstance(row, dict) and row.get("id") == feature_id]
    return matches[0] if len(matches) == 1 else None


def _feature_publication_matches(feature, entry):
    try:
        ref = feature.get("systems_ref")
        return (publication_identity(ref) == _ref(entry)
            and all(key not in ref or ref[key] == getattr(entry, key, None)
                    for key in ("slug", "title", "library_slug")))
    except (GrantContractError, TypeError, ValueError):
        return False


def _same_feature_association(prior, current):
    # Tracker/activation derivation has its own owner. It cannot establish or
    # destroy this exact retained source/opaque-ID/owner-absence association.
    fields = ("id", "systems_ref", "class_row_id", "native_acquisition")
    return canonical_digest({key: prior[key] for key in fields if key in prior}) == canonical_digest(
        {key: current[key] for key in fields if key in current})


def _confirmed_retained_prior(definition, context, retained, migration_edges,
                              prior_definition, prior_custody, actual_state_revision):
    if prior_definition is None:
        if retained or prior_custody or actual_state_revision is not None:
            raise GrantContractError("Retained owners need their actual confirmed prior frame.")
        return None
    if (context.mode != "progression"
            or definition.campaign_slug != prior_definition.campaign_slug
            or definition.character_slug != prior_definition.character_slug
            or context.prior_definition_digest != canonical_digest(prior_definition.to_dict())
            or type(context.prior_revision) is not int or context.prior_revision < 1
            or type(context.prior_state_revision) is not int or context.prior_state_revision < 1
            or not _confirmed_target_grant_custody(prior_custody, prior_definition)):
        raise GrantContractError("Retained feature association has no authenticated original target.")
    # Display drafts have no independent actual-state witness. The real caller
    # passes its observed revision; never manufacture one from the context.
    if actual_state_revision is not None and (type(actual_state_revision) is not int
            or actual_state_revision != context.prior_state_revision):
        raise GrantContractError("Retained feature association changed its actual state revision.")
    prior_model = validate_native_grant_model(prior_definition)
    if (canonical_digest(list(retained)) != canonical_digest(prior_definition.source["native_acquisitions"]["owners"])
            or canonical_digest(list(migration_edges)) != canonical_digest(prior_model["migration_edges"])):
        raise GrantContractError("Retained owner or observation custody differs from the actual prior model.")
    return prior_definition


def _fixed_feature_associations(definition, service, found, *, original=False, prior=None):
    """Associate raw fixed rows only under original or confirmed retained custody.

    The source map independently owns automatic grants. This map never changes
    a raw dictionary, supplies elective custody or adds a canonical source node.
    New selected elective inputs still receive their strict owner check here.
    """
    from .character_profile import profile_class_rows
    profile_ids = {row["row_id"] for row in profile_class_rows(definition.profile)}
    associations = {}
    for feature in definition.features:
        if not isinstance(feature, dict) or not feature.get("systems_ref"):
            continue
        try:
            entry = _exact_entry(service, definition.campaign_slug, feature["systems_ref"])
        except GrantContractError:
            continue  # Unqualified observations cannot veto independent sources.
        if "native_spell_grants" not in entry.metadata:
            continue
        old = _unique_raw_feature(prior, feature.get("id")) if prior is not None else None
        retained_raw = old is not None and _same_feature_association(old, feature)
        if entry.entry_type in {"feat", "feature", "optionalfeature"}:
            if (not _text(feature.get("class_row_id")) or feature["class_row_id"] not in profile_ids
                    or _unique_raw_feature(definition, feature.get("id")) is not feature):
                if original or retained_raw:
                    continue  # No historical elective acquisition is inferred.
                raise GrantContractError("A new selected grant feature needs its unique explicit class owner.")
            continue
        if entry.entry_type not in {"classfeature", "subclassfeature"}:
            continue
        if (_unique_raw_feature(definition, feature.get("id")) is not feature
                and not original and not retained_raw):
            raise GrantContractError("A new fixed feature needs its unique exact feature identity.")
        attained = {key[0] for key in found if len(key) == 2 and key[1] == entry.entry_key}
        if "class_row_id" in feature:
            row_id = feature["class_row_id"]
            if not _text(row_id) or row_id not in profile_ids or attained and row_id not in attained:
                raise GrantContractError("An explicit fixed-feature owner is invalid or conflicting.")
            if row_id not in attained:
                if original or retained_raw:
                    continue  # Preserve an unattained observation without a grant.
                raise GrantContractError("The fixed feature is outside the attained source chain.")
        elif original:
            if len(attained) != 1:
                continue  # No arbitrary first owner or historical ID adoption.
            row_id = next(iter(attained))
        elif retained_raw:
            owners = [owner for owner in prior.source["native_acquisitions"]["owners"]
                      if owner["owner_id"] == feature.get("id")
                      and publication_identity(owner["source_ref"]) == _ref(entry)]
            if len(owners) != 1 or len(attained) != 1 or owners[0]["class_row_id"] not in attained:
                continue  # The old observation does not acquire a new association.
            row_id = owners[0]["class_row_id"]
        else:
            raise GrantContractError("A new fixed feature needs its explicit class-row owner.")
        if _unique_raw_feature(definition, feature.get("id")) is feature:
            associations[feature["id"]] = row_id
    return associations


def _attained_owners(definition, service):
    from .character_profile import profile_class_rows
    rows = profile_class_rows(definition.profile)
    if len({row.get("row_id") for row in rows}) != len(rows):
        raise GrantContractError("Casting class ownership is ambiguous.")
    found = {}
    collector = getattr(service, "collect_attained_deterministic_feature_entries", None)
    if not callable(collector):
        raise GrantContractError("Current attained source features are unavailable.")
    for row in rows:
        level, row_id = row.get("level"), row.get("row_id")
        if not _text(row_id) or type(level) is not int or not 1 <= level <= 20:
            raise GrantContractError("Current class attainment is unavailable.")
        cls = _exact_entry(service, definition.campaign_slug, row.get("systems_ref"), "class")
        parents = [cls]
        if row.get("subclass_ref"):
            subclass = _exact_entry(service, definition.campaign_slug, row["subclass_ref"], "subclass")
            if (subclass.metadata.get("class_name") != cls.title
                    or subclass.metadata.get("class_source") != cls.source_id):
                raise GrantContractError("Current subclass parent changed.")
            parents.append(subclass)
        for parent in parents:
            # This bounded Armor Model adapter declares no spell grant. An
            # unproved elective branch must not become an automatic origin.
            for entry in collector(definition.campaign_slug, parent, attained_level=level,
                                   selected_feature_branches={}):
                found[(row_id, entry.entry_key)] = (entry, level)
    # Selected feats/features additionally need their committed acquisition custody.
    for feature in definition.features:
        if not isinstance(feature, dict) or not feature.get("systems_ref"):
            continue
        try:
            entry = _exact_entry(service, definition.campaign_slug, feature["systems_ref"])
        except GrantContractError:
            # This unqualified historical feature supplies no grant. It must
            # not erase an independently qualified attained feature origin.
            continue
        if "native_spell_grants" not in entry.metadata:
            continue
        row_id = feature.get("class_row_id")
        if entry.entry_type in {"classfeature", "subclassfeature"}:
            # Canonical fixed ownership comes only from the selected source
            # chain above. Raw historical association is a separate proof.
            continue
        elif entry.entry_type in {"feat", "feature", "optionalfeature"}:
            if not _text(row_id) or not _text(feature.get("id")):
                continue
            matches = [row for row in rows if row.get("row_id") == row_id]
            if len(matches) != 1 or _unique_raw_feature(definition, feature["id"]) is not feature:
                continue  # An unproved elective cannot erase an attained fixed origin.
            found[(row_id, entry.entry_key, feature.get("id"))] = (entry, matches[0]["level"])
    from .character_feature_composition import resolve_feature_composition
    composition = resolve_feature_composition(definition, service)
    return {key: value for key, value in found.items()
            if (key[0], key[1]) not in composition.disabled_owners}


def _owner_rule_supported(owner, entry, definition, service, found, owners):
    """Recheck the granting rule, not a stored/UI choice-slot assertion.

    Fixed progression is source-attained. The existing typed ``feats`` one-slot
    contract can additionally prove a selected feat acquisition. A prose/title
    ASI/optional group without that typed branch remains unsupported here; it
    does not prevent ordinary nongrant authoring.
    """
    if entry.entry_type in {"classfeature", "subclassfeature"}:
        return (owner["grant_rule_id"] == entry.entry_key
                and owner["choice_slot_id"] == entry.entry_key)
    if owner["choice_slot_id"] != "feat" or owner["grant_rule_id"] == entry.entry_key:
        return False
    parent = service.get_entry_for_campaign(definition.campaign_slug, owner["grant_rule_id"])
    if parent is None:
        return False
    slots = parent.metadata.get("feats")
    if (type(slots) is not list or len(slots) != 1 or type(slots[0]) is not dict
            or set(slots[0]) != {"any"} or type(slots[0]["any"]) is not int
            or slots[0]["any"] != 1):
        return False
    if parent.entry_type in {"race", "subrace"}:
        selected = definition.profile.get("species_ref")
        if not isinstance(selected, dict) or publication_identity(selected) != _ref(parent):
            return False
    elif parent.entry_type in {"classfeature", "subclassfeature"}:
        if (owner["class_row_id"], parent.entry_key) not in found:
            return False
    else:
        return False
    return sum(candidate["grant_rule_id"] == owner["grant_rule_id"]
               and candidate["choice_slot_id"] == owner["choice_slot_id"]
               and candidate["class_row_id"] == owner["class_row_id"]
               for candidate in owners) == 1


def _build_occurrences(definition, service, context, retained_owners, migration_edges, *,
                       prior_definition=None, prior_custody=(), prior_state_revision=None,
                       original_migration=None, source_facts=None, fixed_associations=None):
    if not isinstance(context, AcquisitionContext) or context.campaign_slug != definition.campaign_slug:
        raise GrantContractError("Native grants require their authenticated acquisition context.")
    original = original_migration is definition
    if context.mode == "migration":
        if (not original or retained_owners or prior_definition is not None or prior_custody
                or canonical_digest(definition.to_dict()) != context.prior_definition_digest):
            raise GrantContractError("First migration needs the actual original-frame producer.")
        prior = None
    else:
        if original_migration is not None:
            raise GrantContractError("Original migration custody cannot authorize new acquisition.")
        prior = _confirmed_retained_prior(definition, context, retained_owners, migration_edges,
            prior_definition, prior_custody, prior_state_revision)
    found = _attained_owners(definition, service) if source_facts is None else source_facts
    associations = (_fixed_feature_associations(definition, service, found, original=original, prior=prior)
                    if fixed_associations is None else fixed_associations)
    retained = list(retained_owners)
    owners, occurrences = [], []
    for key, (entry, level) in sorted(found.items()):
        if "native_spell_grants" not in entry.metadata:
            continue
        if context.mode == "migration" and entry.entry_type not in {"classfeature", "subclassfeature"}:
            # Original-row custody does not prove an elective choice, award or
            # ownership adoption. Keep its raw data and observation unresolved.
            continue
        row_id = key[0]
        rules, basis = _source_rules(entry, service, definition.campaign_slug)
        matches = [owner for owner in retained if owner.get("class_row_id") == row_id
                   and publication_identity(owner.get("source_ref")) == _ref(entry)
                   and (len(key) == 2 or owner.get("owner_id") == key[2])]
        if len(matches) > 1:
            raise GrantContractError("Retained feature occurrence is ambiguous.")
        if matches:
            owner = deepcopy(matches[0])
            _confirmed_fixed_owner_association(definition, owner, entry, found)
        else:
            feature_matches = [feature for feature in definition.features
                if isinstance(feature, dict) and _text(feature.get("id"))
                and (associations.get(feature.get("id")) == row_id
                     if entry.entry_type in {"classfeature", "subclassfeature"}
                     else feature.get("class_row_id") == row_id)
                and _feature_publication_matches(feature, entry)
                and (len(key) == 2 or feature.get("id") == key[2])]
            authored = (feature_matches[0].get("native_acquisition")
                        if len(feature_matches) == 1 else None)
            if entry.entry_type in {"classfeature", "subclassfeature"}:
                # A raw historical slot is not authority for an automatic rule.
                authored = {"grant_rule_id": entry.entry_key, "choice_slot_id": entry.entry_key}
            if (not isinstance(authored, dict) or set(authored) != {"grant_rule_id", "choice_slot_id"}
                    or not all(_text(value) for value in authored.values())):
                # The missing authored slot withholds this grant family only.
                # Ordinary nongrant creation and independently qualified owners
                # remain usable. The raw selection remains a review observation.
                continue
            acquisition_id = feature_acquisition_id(context, source_ref=_ref(entry),
                class_row_id=row_id, **authored)
            owner_id = owner_occurrence_id(acquisition_id=acquisition_id,
                source_ref=_ref(entry), **authored)
            owner = {"owner_id": owner_id, "acquisition_id": acquisition_id,
                "source_ref": _ref(entry), "class_row_id": row_id, **authored}
        owners.append(owner)
        for rule in rules:
            if rule["unlock_level"] > level:
                continue
            for leaf in rule["leaves"]:
                spell = _exact_entry(service, definition.campaign_slug, leaf["spell_ref"], "spell")
                if type(spell.metadata.get("level")) is not int or not 0 <= spell.metadata["level"] <= 9:
                    raise GrantContractError("The exact granted spell level is unavailable.")
                occurrences.append({"id": occurrence_id(owner["owner_id"], owner["acquisition_id"],
                    rule["id"], leaf["id"], spell.entry_key),
                    "owner_id": owner["owner_id"], "acquisition_id": owner["acquisition_id"],
                    "source_ref": _ref(entry), "class_row_id": row_id,
                    "rule_id": rule["id"], "leaf_id": leaf["id"], "spell_ref": _ref(spell),
                    "source_basis_digest": basis})
    if len(occurrences) > 256 or len({row["id"] for row in occurrences}) != len(occurrences):
        raise GrantContractError("Native spell grant identity is ambiguous or exceeds bounds.")
    return ({"schema_version": 1, "occurrences": occurrences,
             "migration_edges": deepcopy(list(migration_edges))},
            {"schema_version": 1, "intent": context.to_dict(), "owners": owners})


def _migration_context(definition, generation, prior_digest, state_revision):
    if (type(generation) is not int or generation < 1 or not _sha(prior_digest)
            or type(state_revision) is not int or state_revision < 1
            or canonical_digest(definition.to_dict()) != prior_digest):
        raise GrantContractError("Migration requires the exact original committed generation.")
    return AcquisitionContext(canonical_digest({"campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "prior_generation": generation,
        "prior_definition_digest": prior_digest, "prior_state_revision": state_revision}),
        definition.campaign_slug, None, "migration", generation, state_revision, prior_digest)


def _prepare_feature_grant_migration(definition, service, generation, prior_digest, state_revision):
    from .character_models import CharacterDefinition
    if has_native_grants(definition):
        raise GrantContractError("This character already has a versioned native grant model.")
    context = _migration_context(definition, generation, prior_digest, state_revision)
    found = _attained_owners(definition, service)
    associations = _fixed_feature_associations(definition, service, found, original=True)
    model, acquisitions = _build_occurrences(definition, service, context, (), (),
        original_migration=definition, source_facts=found, fixed_associations=associations)
    # Opaque retained feature IDs may become occurrence IDs only inside this
    # authenticated-original migration. Do not rename their stored feature rows.
    mapping = {}
    for owner in acquisitions["owners"]:
        matches = [feature for feature in definition.features if isinstance(feature, dict)
            and _text(feature.get("id"))
            and associations.get(feature.get("id")) == owner["class_row_id"]
            and publication_identity(feature.get("systems_ref")) == publication_identity(owner["source_ref"])]
        if len(matches) == 1 and _unique_raw_feature(definition, matches[0].get("id")) is matches[0]:
            old_id = owner["owner_id"]
            owner["owner_id"] = matches[0]["id"]
            mapping[old_id] = owner["owner_id"]
    for row in model["occurrences"]:
        row["owner_id"] = mapping.get(row["owner_id"], row["owner_id"])
        row["id"] = occurrence_id(row["owner_id"], row["acquisition_id"], row["rule_id"],
                                  row["leaf_id"], row["spell_ref"]["entry_key"])
    raw_spells = definition.spellcasting.get("spells")
    if type(raw_spells) is not list or len(raw_spells) > 256:
        raise GrantContractError("Original spell observations are unavailable.")
    ids = set()
    for raw in raw_spells:
        if not isinstance(raw, dict) or not _text(raw.get("id")) or raw["id"] in ids:
            raise GrantContractError("Original spell observation identity is ambiguous.")
        ids.add(raw["id"])
        grants = [row["id"] for row in model["occurrences"]
            if not raw.get("spell_source_row_id")
            and raw.get("class_row_id") == row["class_row_id"]
            and isinstance(raw.get("systems_ref"), dict)
            and raw["systems_ref"].get("entry_key") == row["spell_ref"]["entry_key"]]
        model["migration_edges"].append({"old_spell_id": raw["id"], "grant_ids": sorted(grants),
            "unresolved_observation_digest": canonical_digest(raw)})
    payload = deepcopy(definition.to_dict())
    payload["source"]["native_acquisitions"] = acquisitions
    payload["spellcasting"]["native_spell_grants"] = model
    candidate = CharacterDefinition.from_dict(payload)
    validate_native_grant_model(candidate)
    return candidate, deepcopy(model)


def _validate_feature_grant_migration_custody(prior, candidate, generation, prior_digest, state_revision):
    if has_native_grants(prior):
        raise GrantContractError("An existing canonical model cannot be recast as a first legacy migration.")
    context = _migration_context(prior, generation, prior_digest, state_revision)
    model = validate_native_grant_model(candidate)
    if any(owner["source_ref"]["entry_type"] not in {"classfeature", "subclassfeature"}
           for owner in candidate.source["native_acquisitions"]["owners"]):
        raise GrantContractError("First migration cannot authenticate an elective acquisition from a historical row.")
    if canonical_digest(candidate.source["native_acquisitions"]["intent"]) != canonical_digest(context.to_dict()):
        raise GrantContractError("Migration acquisition custody changed.")
    from .character_profile import profile_class_rows
    profiles = profile_class_rows(prior.profile)
    owners = candidate.source["native_acquisitions"]["owners"]
    for owner in owners:
        ref = publication_identity(owner["source_ref"])
        row_id = owner["class_row_id"]
        if owner["grant_rule_id"] != ref["entry_key"] or owner["choice_slot_id"] != ref["entry_key"]:
            raise GrantContractError("Migration fixed rule and slot must be their exact source publication.")
        if len([row for row in profiles if row.get("row_id") == row_id]) != 1:
            raise GrantContractError("Migration lost its original profile class-row identity.")
        expected_acquisition = feature_acquisition_id(context, source_ref=ref,
            class_row_id=row_id, grant_rule_id=owner["grant_rule_id"], choice_slot_id=owner["choice_slot_id"])
        if owner["acquisition_id"] != expected_acquisition:
            raise GrantContractError("Migration acquisition is not deterministic from its original frame.")
        automatic_id = owner_occurrence_id(acquisition_id=expected_acquisition,
            source_ref=ref, grant_rule_id=owner["grant_rule_id"], choice_slot_id=owner["choice_slot_id"])
        if owner["owner_id"] == automatic_id:
            continue  # No historical raw association is claimed by this identity.
        raw = _unique_raw_feature(prior, owner["owner_id"])
        if raw is None or publication_identity(raw.get("systems_ref")) != ref:
            raise GrantContractError("Migration opaque owner has no unique original feature publication.")
        if "class_row_id" in raw:
            if not _text(raw["class_row_id"]) or raw["class_row_id"] != row_id:
                raise GrantContractError("Migration changed an explicit original feature owner.")
        elif len({item["class_row_id"] for item in owners
                  if publication_identity(item["source_ref"]) == ref}) != 1:
            raise GrantContractError("Migration cannot assign an ambiguous absent original owner.")
        matches = []
        for feature in prior.features:
            if not isinstance(feature, dict):
                continue
            try:
                same = publication_identity(feature.get("systems_ref")) == ref
            except GrantContractError:
                same = False
            if same and ("class_row_id" not in feature or feature["class_row_id"] == row_id):
                matches.append(feature)
        if len(matches) != 1 or matches[0] is not raw:
            raise GrantContractError("Migration opaque feature association is ambiguous.")
    before, after = deepcopy(prior.to_dict()), deepcopy(candidate.to_dict())
    after["source"].pop("native_acquisitions", None)
    after["spellcasting"].pop("native_spell_grants", None)
    # New numeric attestations are independently validated by the publication
    # proof; they are not source-feature ownership and cannot alter observations.
    if "source_authorizations" in before["source"]:
        after["source"]["source_authorizations"] = deepcopy(before["source"]["source_authorizations"])
    else:
        after["source"].pop("source_authorizations", None)
    if canonical_digest(before) != canonical_digest(after):
        raise GrantContractError("Migration changed original character observations.")
    raw_spells = prior.spellcasting.get("spells")
    if (type(raw_spells) is not list or len(raw_spells) > 256
            or any(not isinstance(raw, dict) or not _text(raw.get("id")) for raw in raw_spells)):
        raise GrantContractError("Original migration spell observations are malformed.")
    originals = {raw["id"]: raw for raw in raw_spells}
    if len(originals) != len(raw_spells):
        raise GrantContractError("Original migration spell observation identity is ambiguous.")
    if ({edge["old_spell_id"] for edge in model["migration_edges"]} != set(originals)
            or any(edge["unresolved_observation_digest"] != canonical_digest(originals[edge["old_spell_id"]])
                   for edge in model["migration_edges"])):
        raise GrantContractError("Migration did not retain every original spell observation.")


def _confirmed_fixed_owner_association(definition, owner, entry, found):
    """Check an admitted model's raw association against fresh exact attainment.

    Called only after genuine target-bound custody. It neither resolves an
    unproved candidate association nor writes ownership into a historical row.
    """
    if entry.entry_type not in {"classfeature", "subclassfeature"}:
        return
    automatic_id = owner_occurrence_id(acquisition_id=owner["acquisition_id"],
        source_ref=owner["source_ref"], grant_rule_id=owner["grant_rule_id"], choice_slot_id=owner["choice_slot_id"])
    if owner["owner_id"] == automatic_id:
        return
    raw = _unique_raw_feature(definition, owner["owner_id"])
    if raw is None or not _feature_publication_matches(raw, entry):
        raise GrantContractError("Confirmed opaque owner has no unique exact retained feature.")
    if "class_row_id" in raw:
        if not _text(raw["class_row_id"]) or raw["class_row_id"] != owner["class_row_id"]:
            raise GrantContractError("Confirmed feature has an explicit conflicting owner.")
    else:
        attained = {key[0] for key in found if len(key) == 2 and key[1] == entry.entry_key}
        if attained != {owner["class_row_id"]}:
            raise GrantContractError("Confirmed historical association no longer has a unique attained owner.")


def _qualify_native_grants(definition, service, custody):
    authenticated = _confirmed_target_grant_custody(custody, definition)
    try:
        model = validate_native_grant_model(definition)
    except (GrantContractError, TypeError, ValueError) as exc:
        return GrantView(diagnostics=({"status": "UNPROVED", "reason": str(exc)},))
    try:
        found = _attained_owners(definition, service)
    except (GrantContractError, TypeError, ValueError) as exc:
        return GrantView(diagnostics=({"status": "UNPROVED", "reason": str(exc)},),
                         migration_edges=tuple(model["migration_edges"]))
    inspected = _inspect_source_grants(definition, service, _found=found)
    owners = {owner["owner_id"]: owner for owner in definition.source["native_acquisitions"]["owners"]}
    rows, diagnostics = [], list(inspected.diagnostics)
    for original in inspected.occurrences:
        row = {**original, "status": "UNPROVED", "contributions": {}, "casting_path": None}
        if not authenticated:
            row["reason"] = "Grant model has no independently confirmed custody."
        elif original["status"] == "SOURCE_SUPPORTED":
            owner = owners[row["owner_id"]]
            try:
                if owner["source_ref"]["entry_type"] in {"classfeature", "subclassfeature"}:
                    entry = found[(owner["class_row_id"], owner["source_ref"]["entry_key"])][0]
                    _confirmed_fixed_owner_association(definition, owner, entry, found)
                row.update(status="VERIFIED", contributions=original["contributions"], casting_path=original.get("casting_path"))
            except (GrantContractError, KeyError, TypeError, ValueError) as exc:
                row["reason"] = str(exc)
                diagnostics.append({"id": row["id"], "status": "UNPROVED", "reason": str(exc)})
        rows.append(row)
    return GrantView(tuple(rows), tuple(diagnostics), inspected.migration_edges)


def _inspect_source_grants(definition, service, *, inspect_casting=True, _found=None):
    """Canonical current source facts only, never historical association custody."""
    try:
        model = validate_native_grant_model(definition)
    except (GrantContractError, TypeError, ValueError) as exc:
        return GrantView(diagnostics=({"status": "UNPROVED", "reason": str(exc)},))
    try:
        found = _attained_owners(definition, service) if _found is None else _found
    except (GrantContractError, TypeError, ValueError) as exc:
        return GrantView(diagnostics=({"status": "UNPROVED", "reason": str(exc)},),
                         migration_edges=tuple(model["migration_edges"]))
    owners = {owner["owner_id"]: owner for owner in definition.source["native_acquisitions"]["owners"]}
    rows, diagnostics = [], []
    if definition.source["native_acquisitions"]["intent"].get("mode") == "migration":
        for key, (entry, _level) in found.items():
            if (entry.entry_type in {"classfeature", "subclassfeature"}
                    or "native_spell_grants" not in entry.metadata):
                continue
            represented = any(owner["class_row_id"] == key[0]
                and publication_identity(owner["source_ref"]) == _ref(entry)
                and (len(key) == 2 or owner["owner_id"] == key[2])
                for owner in owners.values())
            if not represented:
                diagnostics.append({"source_ref": _ref(entry), "class_row_id": key[0],
                    "status": "UNPROVED", "reason":
                    "Historical linked elective feature has no independently authenticated acquisition; raw observations are retained."})
    for occurrence in model["occurrences"]:
        row = deepcopy(occurrence)
        row.update(status="UNPROVED", reason="Grant model has no independently confirmed custody.",
                   contributions={}, casting_path=None)
        try:
            owner = owners[row["owner_id"]]
            candidates = [pair for key, pair in found.items() if key[0] == owner["class_row_id"]
                and key[1] == owner["source_ref"]["entry_key"]
                and (len(key) == 2 or key[2] == owner["owner_id"])]
            if len(candidates) != 1:
                raise GrantContractError("Current feature ownership or attainment changed.")
            entry, level = candidates[0]
            if publication_identity(owner["source_ref"]) != _ref(entry):
                raise GrantContractError("The exact current granting publication changed.")
            if not _owner_rule_supported(owner, entry, definition, service, found, tuple(owners.values())):
                raise GrantContractError("The actual source does not prove this granting rule and unique choice slot.")
            rules, basis = _source_rules(entry, service, definition.campaign_slug)
            matches = [(rule, leaf) for rule in rules for leaf in rule["leaves"]
                if rule["id"] == row["rule_id"] and leaf["id"] == row["leaf_id"]]
            if len(matches) != 1 or basis != row["source_basis_digest"]:
                raise GrantContractError("The authored rule or current source basis changed.")
            rule, leaf = matches[0]
            spell = _exact_entry(service, definition.campaign_slug, row["spell_ref"], "spell")
            if (publication_identity(leaf["spell_ref"]) != _ref(spell)
                    or rule["unlock_level"] > level or type(spell.metadata.get("level")) is not int
                    or not 0 <= spell.metadata["level"] <= 9):
                raise GrantContractError("The spell publication or unlock is not qualified.")
            if (leaf["conditions"] or leaf["casting"] not in ({"kind": "owning_class"}, None)
                    or leaf["usage_ref"] not in ({"kind": "class_slots"}, None)):
                raise GrantContractError("Dependent conditions or usage remain unsupported.")
            row.update(status="SOURCE_SUPPORTED", reason="Current source-feature grant facts are supported.",
                contributions=deepcopy(leaf["contributions"]))
            if inspect_casting and leaf["casting"] == {"kind": "owning_class"}:
                classes = [cls for cls in definition.spellcasting.get("class_rows", [])
                    if isinstance(cls, dict) and cls.get("class_row_id") == row["class_row_id"]]
                if len(classes) != 1:
                    raise GrantContractError("The existing casting class lane is unavailable.")
                cls = classes[0]
                from .character_profile import profile_class_rows
                from .character_builder_derivation import _spellcasting_ability_name_for_class
                profiles = [profile for profile in profile_class_rows(definition.profile)
                            if profile.get("row_id") == row["class_row_id"]]
                if len(profiles) != 1:
                    raise GrantContractError("The casting class owner is ambiguous.")
                profile = profiles[0]
                current_class = _exact_entry(service, definition.campaign_slug, profile.get("systems_ref"), "class")
                current_subclass = (_exact_entry(service, definition.campaign_slug,
                    profile["subclass_ref"], "subclass") if profile.get("subclass_ref") else None)
                ability = _spellcasting_ability_name_for_class(current_class.title,
                    selected_class=current_class, selected_subclass=current_subclass,
                    row_level=profile["level"])
                if not ability or cls.get("spellcasting_ability") != ability:
                    raise GrantContractError("Current casting ability is not source-qualified.")
                lane = None
                if leaf["usage_ref"]:
                    lanes = [candidate for candidate in definition.spellcasting.get("slot_lanes", [])
                        if isinstance(candidate, dict) and candidate.get("id") == cls.get("slot_lane_id")
                        and row["class_row_id"] in candidate.get("row_ids", [])]
                    if len(lanes) != 1:
                        raise GrantContractError("Existing casting resource ownership is unavailable.")
                    lane = lanes[0]["id"]
                row["casting_path"] = {"id": row["id"], "owner_id": row["owner_id"],
                    "class_row_id": row["class_row_id"], "ability": ability,
                    "slot_lane_id": lane,
                    "conditions": [], "usage_ref": deepcopy(leaf["usage_ref"])}
            row["spell_name"] = spell.title
            row["spell_level"] = spell.metadata["level"]
            row["spell_has_ritual_tag"] = spell.metadata.get("ritual") is True
            from .character_builder_spells import _build_spell_payload
            display_payload = _build_spell_payload(spell.title, spell)
            row["spell_display"] = {field: deepcopy(display_payload[field]) for field in (
                "name", "casting_time", "range", "duration", "components", "save_or_hit", "source", "reference")}
            from .character_spell_properties import inferred_cantrip_properties
            try:
                properties, property_diagnostics = inferred_cantrip_properties(
                    entry, spell, str(entry.metadata.get("class_name") or ""))
            except (ValueError, TypeError, KeyError, RecursionError):
                properties, property_diagnostics = None, ["unmodeled_cantrip_property_source_shape"]
            row["spell_properties"] = properties
            row["spell_property_label"] = entry.title
            row["spell_property_diagnostics"] = property_diagnostics
            display = [raw["id"] for raw in definition.spellcasting.get("spells", [])
                if isinstance(raw, dict) and raw.get("id") and not raw.get("spell_source_row_id")
                and raw.get("class_row_id") == row["class_row_id"]
                and isinstance(raw.get("systems_ref"), dict)
                and raw["systems_ref"].get("entry_key") == spell.entry_key]
            if len(display) > 1:
                raise GrantContractError("Historical spell display ownership is ambiguous.")
            row["display_spell_ids"] = display
        except (GrantContractError, KeyError, TypeError, ValueError) as exc:
            row.update(status="UNPROVED", reason=str(exc), contributions={}, casting_path=None)
            diagnostics.append({"id": row["id"], "status": "UNPROVED", "reason": str(exc)})
        rows.append(row)
    return GrantView(tuple(rows), tuple(diagnostics), tuple(model["migration_edges"]))


def _project_native_spellcasting(definition, view, class_spells, item_spells, retired_choices=(), choice_ledger=None):
    if not isinstance(view, GrantView):
        raise GrantContractError("Only confirmed qualification may supply an effective spell projection.")
    result = deepcopy(definition.spellcasting)
    result["native_grant_projection"] = True
    raw = {row["id"]: row for row in definition.spellcasting.get("spells", [])
           if isinstance(row, dict) and row.get("id")}
    projected = {}
    for supplied in (*tuple(class_spells), *tuple(item_spells)):
        row = deepcopy(supplied)
        if not isinstance(row, dict) or not row.get("id"):
            continue
        row.update(native_grant_projection=True, grant_origins=[], casting_paths=[],
            grant_unknown_observations=[], grant_fixed=bool(row.get("is_always_prepared") is True
                or row.get("is_bonus_known") is True),
            grant_counts_against_prepared=not bool(row.get("is_always_prepared") is True),
            grant_counts_against_known=not bool(row.get("is_bonus_known") is True))
        row["grant_class_choice_counted"] = bool(not row.get("spell_source_row_id")
                                                and row["grant_counts_against_known"])
        row["grant_class_choice_state"] = "active" if row["grant_class_choice_counted"] else None
        projected[row["id"]] = row
    for grant in view.occurrences:
        matching_edges = [edge for edge in view.migration_edges if grant["id"] in edge["grant_ids"]]
        if len(matching_edges) > 1:
            # Do not select one conflicting historical preparation observation.
            continue
        old_id = (matching_edges[0]["old_spell_id"] if matching_edges else
                  next(iter(grant.get("display_spell_ids", [])), None))
        display_id = old_id or grant_display_id(grant)
        if grant["status"] != "VERIFIED":
            continue
        contributions = grant["contributions"]
        if not any(contributions.get(field) is True for field in ("always_prepared", "bonus_known", "ritual")):
            continue
        row = projected.get(display_id)
        if row is None:
            row = deepcopy(raw.get(old_id, {}))
            row.update(id=display_id, systems_ref=deepcopy(grant["spell_ref"]),
                class_row_id=grant["class_row_id"], native_grant_projection=True,
                is_always_prepared=False, is_bonus_known=False, is_ritual=False,
                grant_origins=[], casting_paths=[], grant_unknown_observations=[],
                grant_counts_against_prepared=None, grant_counts_against_known=None,
                authority_status="VERIFIED", name=grant["spell_name"],
                level=grant["spell_level"], spell_level=grant["spell_level"])
            row.pop("source", None)
            row.pop("always_prepared", None)
            for alias in ("ritual", "isRitual", "base_is_ritual", "base_ritual"):
                row.pop(alias, None)
            row.setdefault("name", grant["spell_ref"]["entry_key"].rsplit("|", 1)[-1])
            projected[display_id] = row
        row["grant_origins"].append(deepcopy(grant))
        for field, value in grant.get("spell_display", {}).items():
            row.setdefault(field, deepcopy(value))
        row["grant_spell_has_ritual_tag"] = bool(row.get("grant_spell_has_ritual_tag")
            or grant.get("spell_has_ritual_tag") is True)
        if grant.get("casting_path") is not None:
            row["casting_paths"].append(deepcopy(grant["casting_path"]))
        for field in ("always_prepared", "bonus_known", "ritual"):
            if contributions.get(field) is True:
                row[f"is_{field}"] = True
        row["grant_fixed"] = True
        for field in ("prepared", "known"):
            key = f"counts_against_{field}"
            if key in contributions:
                projected_key = f"grant_{key}"
                current = row[projected_key]
                if field == "known" and row.get("grant_class_choice_counted") is True:
                    # A distinct class learning choice keeps its slot until an
                    # explicit ordinary choice edit retires it. A second free
                    # feature origin does not refund or duplicate that choice.
                    row[projected_key] = True
                elif contributions[key] is False and contributions.get(
                        "always_prepared" if field == "prepared" else "bonus_known") is not True:
                    # A count exemption is scoped to its supported preparation/
                    # learning path. Ritual access alone does not waive an
                    # independent class preparation, for example.
                    row[projected_key] = True if current is True else None
                else:
                    row[projected_key] = contributions[key] if current is None else current or contributions[key]
    for edge in view.migration_edges:
        old_id = edge["old_spell_id"]
        if old_id in projected:
            projected[old_id]["grant_unknown_observations"].append({
                "old_spell_id": old_id, "status": "UNKNOWN",
                "observation_digest": edge["unresolved_observation_digest"]})
        elif old_id in raw:
            row = deepcopy(raw[old_id])
            row.update(native_grant_projection=True, grant_fixed=False, grant_origins=[],
                casting_paths=[], is_always_prepared=False, is_bonus_known=False,
                grant_counts_against_prepared=None, grant_counts_against_known=None,
                authority_status="NEEDS_REPAIR", grant_unknown_observations=[{
                    "old_spell_id": old_id, "status": "UNKNOWN",
                    "observation_digest": edge["unresolved_observation_digest"]}])
            row.pop("always_prepared", None)
            row.pop("source", None)
            row["is_ritual"] = False
            for alias in ("ritual", "isRitual", "base_is_ritual", "base_ritual"):
                row.pop(alias, None)
            row["mark"] = ""
            projected[old_id] = row
    for old_id, original in raw.items():
        if old_id in projected:
            continue
        row = deepcopy(original)
        row.update(native_grant_projection=True, grant_fixed=False, grant_origins=[],
            casting_paths=[], is_always_prepared=False, is_bonus_known=False,
            grant_counts_against_prepared=None, grant_counts_against_known=None,
            authority_status="NEEDS_REPAIR", grant_unknown_observations=[{
                "old_spell_id": old_id, "status": "UNKNOWN",
                "observation_digest": canonical_digest(original)}])
        row.pop("always_prepared", None)
        row.pop("source", None)
        row["is_ritual"] = False
        for alias in ("ritual", "isRitual", "base_is_ritual", "base_ritual"):
            row.pop(alias, None)
        row["mark"] = ""
        projected[old_id] = row
    for spell_id, row in projected.items():
        original = raw.get(spell_id, {})
        try:
            decision = native_class_choice_state(original)
        except ValueError:
            decision = "UNKNOWN"
        if decision is not None and not row.get("grant_class_choice_counted"):
            if decision == "retired" and spell_id in retired_choices:
                row["grant_class_choice_state"] = "retired"
            else:
                row["grant_class_choice_state"] = "UNKNOWN"
                row["grant_counts_against_known"] = None
        row.setdefault("grant_class_choice_counted", False)
        row.setdefault("grant_class_choice_state", None)
        row["grant_class_choice_can_remove"] = bool(row["grant_class_choice_counted"]
            and row.get("authority_status") == "VERIFIED" and not row.get("spell_source_row_id"))
        row["grant_class_choice_can_select"] = bool(not row["grant_class_choice_counted"]
            and row.get("grant_origins") and row.get("authority_status") == "VERIFIED"
            and (decision is None or row["grant_class_choice_state"] == "retired"))
    if isinstance(choice_ledger, dict):
        # Historical obligation, current benefit and capacity are independent.
        # This is only the server's output projection; strict writers rebuild it.
        choices = {row["spell_id"]: row for row in choice_ledger.get("choices", [])}
        pools = choice_ledger.get("pools", [])
        for spell_id, row in projected.items():
            row["grant_ordinary_spellbook"] = False
            row["grant_ordinary_prepared"] = None
            facts = choices.get(spell_id)
            if facts is None:
                continue
            # A historical observation remains in the migration model. Only
            # a currently usable independently confirmed role resolves its
            # effective uncertainty; neither the raw row nor model is rewritten.
            if facts["current_usable"] and (facts.get("current_reconstruction_role")
                    in {"cantrip", "prepared", "known", "book", "available", "automatic"}
                    or facts["ordinary_counted"] or facts.get("class_list_available") is True):
                row["grant_unknown_observations"] = []
            row["grant_class_choice_state"] = facts["historical_state"]
            row["grant_class_choice_counted"] = facts["ordinary_counted"]
            row["grant_counts_against_known"] = facts["counts_against_known"]
            row["grant_counts_against_prepared"] = facts["counts_against_prepared"]
            row["grant_ordinary_spellbook"] = bool(facts.get("pool") == "spellbook"
                and facts.get("historical_state") == "active" and facts.get("ordinary_counted") is True
                and facts.get("current_usable") is True)
            if row["grant_ordinary_spellbook"]:
                row["grant_ordinary_prepared"] = facts.get("ordinary_prepared")
            row["grant_class_choice_can_remove"] = bool(facts["ordinary_counted"] and facts["current_usable"]
                and facts.get("spell_level") != 0 and facts.get("pool") in {"known", "spellbook"})
            relevant = [pool for pool in pools if pool["class_row_id"] == facts["class_row_id"]
                and pool["kind"] == facts["pool"]]
            virtual_birth = bool(facts["historical_state"] == "fixed" and spell_id not in raw
                and choice_ledger.get("inventory_complete") is True and facts["current_usable"]
                and not any(edge["old_spell_id"] == spell_id for edge in view.migration_edges))
            row["grant_class_choice_can_select"] = bool((virtual_birth or facts["historical_state"] == "retired"
                and facts.get("ordinary_eligible") is True) and len(relevant) == 1 and relevant[0]["status"] == "KNOWN"
                and (relevant[0]["remaining"] is None or relevant[0]["remaining"] > 0))
            if not facts["current_usable"]:
                # Retirement/history can retain a raw prepared observation, but
                # only current ordinary or independent feature origins entitle it.
                row["authority_status"] = "NEEDS_REPAIR"
                row["grant_fixed"] = False
                row["casting_paths"] = []
                row["is_always_prepared"] = False
                row["is_bonus_known"] = False
                row["is_ritual"] = False
            if spell_id in raw:
                # Display grouping must not rewrite retained observations.
                for field in ("mark", "prepared", "is_prepared"):
                    if field in raw[spell_id]:
                        row[field] = deepcopy(raw[spell_id][field])
                    else:
                        row.pop(field, None)
        result["native_choice_ledger"] = deepcopy(choice_ledger)
    result["spells"] = list(projected.values())
    result["native_grant_diagnostics"] = deepcopy(list(view.diagnostics))
    return result
