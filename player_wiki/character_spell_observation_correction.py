"""Exact item-only correction of an unconfirmed Wizard book observation.

This is neither spell acquisition nor retirement of a confirmed class choice.
Historical comparison is separate from fresh current item qualification.
"""
from __future__ import annotations

from .character_source_repair import SourceRepairError

_CONFIRMATION = "player_confirmed_item_only_not_spellbook"


def item_only_removal_rows(prior, removed, correction, *, source_level):
    """Pure original-frame validation, also used by the authenticated audit loader."""
    from .character_spell_grants import has_native_grants, publication_identity
    from .character_spell_reconstruction import _class, _digest, _marks, _ref, _rows

    def fail():
        raise SourceRepairError("Item-only correction needs one unconfirmed, unprepared Wizard book observation, "
                                "its separate exact item grant and explicit player confirmation.")

    if (type(source_level) is not int or not 1 <= source_level <= 9
            or type(removed) is not list or len(removed) != 1 or type(removed[0]) is not str
            or type(correction) is not dict
            or set(correction) != {"item_spell_id", "confirmation", "evidence_note"}
            or correction["confirmation"] != _CONFIRMATION
            or type(correction["item_spell_id"]) is not str
            or not correction["item_spell_id"] or correction["item_spell_id"] == removed[0]
            or correction["item_spell_id"] != correction["item_spell_id"].strip()
            or "\x00" in correction["item_spell_id"] or len(correction["item_spell_id"].encode("utf-8")) > 128
            or type(correction["evidence_note"]) is not str
            or not correction["evidence_note"] or correction["evidence_note"] != correction["evidence_note"].strip()
            or "\x00" in correction["evidence_note"] or len(correction["evidence_note"].encode("utf-8")) > 1000
            or has_native_grants(prior)
            or any(key in prior.spellcasting for key in ("native_choice_ledger", "native_grant_projection"))):
        fail()
    cls, rows = _class(prior), _rows(prior)
    if publication_identity(cls.get("systems_ref")) != {
            "entry_key": "dnd-5e|class|phb|wizard", "entry_type": "class", "source_id": "PHB"}:
        fail()
    raw, item = rows.get(removed[0]), rows.get(correction["item_spell_id"])
    if raw is None or item is None:
        fail()
    tokens, prepared = _marks(raw)
    if (raw.get("class_row_id") != cls["row_id"] or prepared or not tokens
            or not tokens <= {"spellbook", "o"}
            or any(raw.get(key) is not None and (type(raw[key]) is not int or raw[key] != source_level)
                   for key in ("level", "spell_level"))
            or any(key in raw for key in ("native_class_choice_state",))
            or any(raw.get(key) for key in ("spell_source_row_id", "spell_source_row_kind", "grant_source_label",
                "authority_original_source_row_id", "authority_original_class_row_id", "is_always_prepared",
                "always_prepared", "is_bonus_known", "base_is_always_prepared", "base_is_bonus_known"))
            or item.get("class_row_id") not in (None, "")
            or item.get("spell_source_row_kind") != "item" or not item.get("spell_source_row_id")
            or any(key in item for key in ("native_class_choice_state",))):
        fail()
    identity = publication_identity(_ref(raw))
    if identity != publication_identity(_ref(item)):
        fail()
    matches = [row for row in rows.values()
               if row.get("systems_ref") and publication_identity(_ref(row)) == identity]
    if len(matches) != 2:
        fail()
    source_rows = prior.spellcasting.get("source_rows", [])
    if type(source_rows) is not list or any(type(row) is not dict for row in source_rows):
        fail()
    sources = [row for row in source_rows if row.get("source_row_id") == item["spell_source_row_id"]]
    source_id = item["spell_source_row_id"]
    if (type(source_id) is not str or source_id != source_id.strip() or "\x00" in source_id
            or len(source_id.encode("utf-8")) > 512
            or len(sources) != 1 or sources[0].get("source_row_kind") != "item"):
        fail()
    for container, key in ((prior.source, "source_authorizations"), (prior.spellcasting, "manual_authorizations")):
        markers = container.get(key, [])
        if type(markers) is not list or any(type(marker) is not dict for marker in markers):
            fail()
        if any(marker.get("target_id") in {raw["id"], f"spell_choice:{raw['id']}"} for marker in markers):
            fail()
    return [{"spell_id": raw["id"], "class_row_id": cls["row_id"], "row_digest": _digest(raw),
        "class_row_digest": _digest(cls), "reason": "player_confirmed_item_only_book_observation", "spell_level": source_level,
        "item_spell_id": item["id"], "item_row_digest": _digest(item),
        "source_row_id": sources[0]["source_row_id"], "source_row_digest": _digest(sources[0]),
        "owner_confirmation": correction["confirmation"], "evidence_note": correction["evidence_note"]}]


def prepare_item_only_removal_rows(prior, service, removed, correction):
    """Fresh exact admitted publication, including its positive spell level."""
    from .character_spell_reconstruction import _ref, _rows
    from .system_policy import DND_5E_SYSTEM_CODE
    rows = _rows(prior)
    if type(removed) is not list or len(removed) != 1 or removed[0] not in rows:
        raise SourceRepairError("Choose the exact erroneous book observation.")
    ref = _ref(rows[removed[0]])
    entry = service.get_entry_for_campaign(prior.campaign_slug, ref["entry_key"])
    if (entry is None or entry.entry_type != "spell" or entry.library_slug != DND_5E_SYSTEM_CODE
            or any(value != getattr(entry, key, None) for key, value in ref.items())):
        raise SourceRepairError("The corrected observation needs its exact admitted spell publication.")
    return item_only_removal_rows(prior, removed, correction, source_level=entry.metadata.get("level"))


def require_current_item_only_grant(definition, authority, removals):
    """Fresh current-source/state check; never called to reinterpret a saved audit."""
    for removal in removals:
        items = [row for row in definition.spellcasting.get("spells", [])
                 if row.get("id") == removal["item_spell_id"]]
        if len(items) != 1:
            raise SourceRepairError("The separate item grant changed during book correction.")
        item = items[0]
        keys = {key for spell_id, key in authority.current_spell_keys if spell_id == item["id"]}
        if (removal["source_row_id"] not in authority.verified_source_rows
                or authority.spell_status(item, definition=definition) != "VERIFIED"
                or not any((removal["source_row_id"], key) in authority.verified_spell_grants for key in keys)):
            raise SourceRepairError("Item-only book correction requires the separate currently qualified item grant.")
