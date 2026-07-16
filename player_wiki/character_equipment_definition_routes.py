from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required
from .character_editor import CharacterEditValidationError


@dataclass(frozen=True)
class CharacterEquipmentDefinitionRouteDependencies:
    build_character_item_catalog: Callable[..., object]
    get_systems_service: Callable[..., object]
    format_character_systems_item_weight: Callable[..., str]
    build_character_systems_ref: Callable[..., dict[str, object]]
    run_character_definition_mutation: Callable[..., object]
    load_campaign_context: Callable[..., object]
    list_visible_character_item_page_records: Callable[..., list[object]]
    list_visible_character_page_records: Callable[..., list[object]]
    normalize_character_page_ref: Callable[..., str]
    filter_character_page_records: Callable[..., list[object]]
    character_items_section: str
    apply_equipment_catalog_edit: Callable[..., object]


def register_character_equipment_definition_routes(
    app: Any,
    *,
    dependencies: CharacterEquipmentDefinitionRouteDependencies,
) -> None:
    def character_equipment_add_systems(campaign_slug: str, character_slug: str):
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)

        def _action(record):
            entry_slug = request.form.get("entry_slug", "").strip()
            if not entry_slug:
                raise CharacterEditValidationError("Choose a Systems item to add.")
            entry = dependencies.get_systems_service().get_entry_by_slug_for_campaign(
                campaign_slug, entry_slug
            )
            if entry is None or str(entry.entry_type or "").strip() != "item":
                raise CharacterEditValidationError(
                    "Choose a valid enabled Systems item to add."
                )
            existing_manual_entries = [
                dict(item)
                for item in list(record.definition.equipment_catalog or [])
                if str(item.get("source_kind") or "").strip() == "manual_edit"
            ]
            if any(
                str((item.get("systems_ref") or {}).get("slug") or "").strip()
                == entry.slug
                for item in existing_manual_entries
            ):
                raise CharacterEditValidationError(
                    "That Systems item is already listed in supplemental equipment. "
                    "Update the existing row instead."
                )
            return dependencies.apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=dependencies.get_systems_service(),
                name=entry.title,
                quantity=request.form.get("quantity", "1"),
                weight=dependencies.format_character_systems_item_weight(
                    (entry.metadata or {}).get("weight")
                ),
                notes=request.form.get("notes", ""),
                systems_ref=dependencies.build_character_systems_ref(entry),
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Systems item added to supplemental equipment.",
            action=_action,
        )

    def character_equipment_add_manual(campaign_slug: str, character_slug: str):
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)
        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Custom item added to supplemental equipment.",
            action=lambda record: dependencies.apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=dependencies.get_systems_service(),
                name=request.form.get("name", ""),
                quantity=request.form.get("quantity", "1"),
                weight=request.form.get("weight", ""),
                notes=request.form.get("notes", ""),
            ),
        )

    def character_equipment_add_campaign_item(
        campaign_slug: str, character_slug: str
    ):
        campaign = dependencies.load_campaign_context(campaign_slug)
        campaign_page_records = (
            dependencies.list_visible_character_item_page_records(
                campaign_slug, campaign
            )
        )
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)

        def _action(record):
            selected_page_ref = request.form.get("page_ref", "")
            if not str(selected_page_ref or "").strip():
                raise CharacterEditValidationError(
                    "Choose a valid item article to add."
                )
            return dependencies.apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=dependencies.get_systems_service(),
                campaign_page_records=campaign_page_records,
                name=request.form.get("name", ""),
                quantity=request.form.get("quantity", "1"),
                weight=request.form.get("weight", ""),
                notes=request.form.get("notes", ""),
                page_ref=selected_page_ref,
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Campaign item added to supplemental equipment.",
            action=_action,
        )

    def character_equipment_update(
        campaign_slug: str, character_slug: str, item_id: str
    ):
        campaign = dependencies.load_campaign_context(campaign_slug)
        all_campaign_page_records = (
            dependencies.list_visible_character_page_records(campaign_slug, campaign)
        )
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)

        def _action(record):
            manual_entry = next(
                (
                    dict(item)
                    for item in list(record.definition.equipment_catalog or [])
                    if str(item.get("source_kind") or "").strip() == "manual_edit"
                    and str(item.get("id") or "").strip() == item_id
                ),
                None,
            )
            if manual_entry is None:
                raise CharacterEditValidationError(
                    "Choose a valid supplemental equipment entry to update."
                )
            systems_ref = dict(manual_entry.get("systems_ref") or {})
            include_page_refs = (
                {
                    dependencies.normalize_character_page_ref(
                        manual_entry.get("page_ref")
                    )
                }
                if dependencies.normalize_character_page_ref(
                    manual_entry.get("page_ref")
                )
                else None
            )
            campaign_page_records = dependencies.filter_character_page_records(
                all_campaign_page_records,
                section=dependencies.character_items_section,
                include_page_refs=include_page_refs,
            )
            return dependencies.apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=dependencies.get_systems_service(),
                campaign_page_records=campaign_page_records,
                target_item_id=item_id,
                name=(
                    request.form.get("name", "")
                    if not systems_ref
                    else str(manual_entry.get("name") or "")
                ),
                quantity=request.form.get("quantity", ""),
                weight=(
                    request.form.get("weight", "")
                    if not systems_ref
                    else str(manual_entry.get("weight") or "")
                ),
                notes=request.form.get("notes", ""),
                page_ref=(
                    request.form.get("page_ref", "") if not systems_ref else ""
                ),
                systems_ref=systems_ref or None,
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Supplemental equipment updated.",
            action=_action,
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-systems",
        endpoint="character_equipment_add_systems",
        view_func=scope_required(character_equipment_add_systems),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-manual",
        endpoint="character_equipment_add_manual",
        view_func=scope_required(character_equipment_add_manual),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-campaign-item",
        endpoint="character_equipment_add_campaign_item",
        view_func=scope_required(character_equipment_add_campaign_item),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/update",
        endpoint="character_equipment_update",
        view_func=scope_required(character_equipment_update),
        methods=("POST",),
    )
