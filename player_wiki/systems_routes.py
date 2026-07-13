from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .auth import (
    can_edit_shared_systems_entries,
    can_manage_campaign_systems,
    campaign_scope_access_required,
    campaign_systems_entry_access_required,
    campaign_systems_source_access_required,
    get_auth_store,
    get_current_user,
    login_required,
)
from .repository import normalize_lookup
from .systems_labels import SYSTEMS_ENTRY_TYPE_LABELS
from .systems_service import SystemsPolicyValidationError


systems = Blueprint("systems", __name__)


@dataclass(frozen=True)
class SystemsRouteDependencies:
    build_index_context: Callable[..., dict[str, object]]
    build_source_context: Callable[..., dict[str, object]]
    build_source_category_context: Callable[..., dict[str, object]]
    build_entry_context: Callable[..., dict[str, object]]
    load_campaign: Callable[[str], Any]
    get_service: Callable[[], Any]
    build_control_context: Callable[[str], dict[str, object]]
    build_dm_content_context: Callable[..., dict[str, object]]
    redirect_to_dm_content: Callable[..., Any]
    custom_entry_dom_id: Callable[[Any], str]


@dataclass(frozen=True)
class SystemsSourcePolicyUpdateInput:
    source_id: str
    is_enabled: bool
    default_visibility: str


@dataclass(frozen=True)
class SystemsSourcePolicyFormInput:
    return_to_dm_content_systems: bool
    acknowledge_proprietary: bool
    updates: tuple[SystemsSourcePolicyUpdateInput, ...]


@dataclass(frozen=True)
class SystemsEntryOverrideFormInput:
    return_to_dm_content_systems: bool
    entry_key: str
    visibility_override: str | None
    is_enabled_override: bool | None


@dataclass(frozen=True)
class SystemsCustomEntryFormInput:
    had_form_fields: bool
    return_to_dm_content_systems: bool
    title: str
    slug_leaf: str
    entry_type: str
    visibility: str
    provenance: str
    search_metadata: str
    body_markdown: str

    def as_form_data(self) -> dict[str, str]:
        if not self.had_form_fields:
            return {}
        return {
            "return_to": (
                "dm-content-systems" if self.return_to_dm_content_systems else ""
            ),
            "custom_entry_title": self.title,
            "custom_entry_slug": self.slug_leaf,
            "custom_entry_type": self.entry_type,
            "custom_entry_visibility": self.visibility,
            "custom_entry_provenance": self.provenance,
            "custom_entry_search_metadata": self.search_metadata,
            "custom_entry_body_markdown": self.body_markdown,
        }


def _dependencies() -> SystemsRouteDependencies:
    return current_app.extensions["systems_route_dependencies"]


def _format_shared_entry_json_field(value: Any) -> str:
    if not value:
        return "{}"
    return json.dumps(value, indent=2, sort_keys=True)


def _build_shared_entry_form(
    *,
    entry: Any = None,
    form_data: Any = None,
) -> dict[str, object]:
    data = form_data if form_data is not None else {}
    if data:
        return {
            "title": str(data.get("shared_entry_title") or ""),
            "source_page": str(data.get("shared_entry_source_page") or ""),
            "source_path": str(data.get("shared_entry_source_path") or ""),
            "search_text": str(data.get("shared_entry_search_text") or ""),
            "player_safe_default": data.get("shared_entry_player_safe_default") == "1",
            "dm_heavy": data.get("shared_entry_dm_heavy") == "1",
            "metadata_json": str(data.get("shared_entry_metadata_json") or "{}"),
            "body_json": str(data.get("shared_entry_body_json") or "{}"),
            "rendered_html": str(data.get("shared_entry_rendered_html") or ""),
            "mechanics_impact_acknowledged": (
                data.get("shared_entry_mechanics_impact_acknowledged") == "1"
            ),
        }
    if entry is not None:
        return {
            "title": entry.title,
            "source_page": entry.source_page,
            "source_path": entry.source_path,
            "search_text": entry.search_text,
            "player_safe_default": bool(entry.player_safe_default),
            "dm_heavy": bool(entry.dm_heavy),
            "metadata_json": _format_shared_entry_json_field(entry.metadata),
            "body_json": _format_shared_entry_json_field(entry.body),
            "rendered_html": entry.rendered_html,
            "mechanics_impact_acknowledged": False,
        }
    return {
        "title": "",
        "source_page": "",
        "source_path": "",
        "search_text": "",
        "player_safe_default": False,
        "dm_heavy": False,
        "metadata_json": "{}",
        "body_json": "{}",
        "rendered_html": "",
        "mechanics_impact_acknowledged": False,
    }


def _build_shared_entry_original_source_identity(entry: Any) -> dict[str, object]:
    return {
        "library_slug": entry.library_slug,
        "source_id": entry.source_id,
        "entry_key": entry.entry_key,
        "entry_slug": entry.slug,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "source_page": entry.source_page,
        "source_path": entry.source_path,
    }


def _list_shared_entry_changed_fields(before_entry: Any, after_entry: Any) -> list[str]:
    comparable_fields = {
        "title": (before_entry.title, after_entry.title),
        "source_page": (before_entry.source_page, after_entry.source_page),
        "source_path": (before_entry.source_path, after_entry.source_path),
        "search_text": (before_entry.search_text, after_entry.search_text),
        "player_safe_default": (
            bool(before_entry.player_safe_default),
            bool(after_entry.player_safe_default),
        ),
        "dm_heavy": (bool(before_entry.dm_heavy), bool(after_entry.dm_heavy)),
        "metadata": (dict(before_entry.metadata or {}), dict(after_entry.metadata or {})),
        "body": (dict(before_entry.body or {}), dict(after_entry.body or {})),
        "rendered_html": (before_entry.rendered_html, after_entry.rendered_html),
    }
    return [
        field
        for field, (before_value, after_value) in comparable_fields.items()
        if before_value != after_value
    ]


def _parse_shared_entry_json_field(
    raw_value: str,
    *,
    field_label: str,
) -> dict[str, object]:
    cleaned_value = str(raw_value or "").strip()
    if not cleaned_value:
        return {}
    try:
        parsed = json.loads(cleaned_value)
    except json.JSONDecodeError as exc:
        raise SystemsPolicyValidationError(
            f"{field_label} must be valid JSON."
        ) from exc
    if not isinstance(parsed, dict):
        raise SystemsPolicyValidationError(f"{field_label} must be a JSON object.")
    return parsed


@login_required
def campaign_systems_control_panel_update_shared_core_permission(
    campaign_slug: str,
):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    user = get_current_user()
    if user is None or not user.is_admin:
        abort(403)

    return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
    allow_dm_edits = request.form.get("allow_dm_shared_core_entry_edits") == "1"
    try:
        policy = dependencies.get_service().update_campaign_shared_core_entry_edit_permission(
            campaign_slug,
            allow_dm_shared_core_entry_edits=allow_dm_edits,
            actor_user_id=user.id,
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        if return_to_dm_content_systems:
            return render_template(
                "dm_content.html",
                **dependencies.build_dm_content_context(
                    campaign_slug,
                    dm_content_subpage="systems",
                ),
            ), 400
        return render_template(
            "campaign_systems_control_panel.html",
            **dependencies.build_control_context(campaign_slug),
        ), 400

    get_auth_store().write_audit_event(
        event_type="campaign_systems_shared_core_edit_permission_updated",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "library_slug": policy.library_slug,
            "allow_dm_shared_core_entry_edits": policy.allow_dm_shared_core_entry_edits,
            "source": "campaign_systems_control_panel",
        },
    )
    flash(
        (
            "Campaign DMs can now edit shared/core Systems entries."
            if policy.allow_dm_shared_core_entry_edits
            else "Campaign DMs can no longer edit shared/core Systems entries."
        ),
        "success",
    )
    if return_to_dm_content_systems:
        return dependencies.redirect_to_dm_content(
            campaign_slug,
            subpage="systems",
            anchor="systems-shared-core-permission",
        )
    return redirect(
        url_for(
            "campaign_systems_control_panel_view",
            campaign_slug=campaign_slug,
            _anchor="systems-shared-core-permission",
        )
    )


def _get_shared_entry_for_edit(campaign_slug: str, entry_slug: str):
    systems_service = _dependencies().get_service()
    entry = systems_service.get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
    if entry is None:
        abort(404)
    source_state = systems_service.get_campaign_source_state(
        campaign_slug,
        entry.source_id,
    )
    if source_state is None or systems_service.is_campaign_custom_entry(
        campaign_slug,
        entry,
    ):
        abort(404)
    return entry


def _render_shared_entry_editor(
    campaign_slug: str,
    entry: Any,
    *,
    form_data: Any = None,
    status_code: int = 200,
):
    dependencies = _dependencies()
    campaign = dependencies.load_campaign(campaign_slug)
    systems_service = dependencies.get_service()
    source_state = systems_service.get_campaign_source_state(
        campaign_slug,
        entry.source_id,
    )
    if source_state is None:
        abort(404)
    return render_template(
        "systems_shared_entry_edit.html",
        campaign=campaign,
        entry=entry,
        source_state=source_state,
        entry_type_label=SYSTEMS_ENTRY_TYPE_LABELS.get(
            entry.entry_type,
            entry.entry_type.replace("_", " ").title(),
        ),
        shared_systems_entry_form=_build_shared_entry_form(
            entry=entry,
            form_data=form_data,
        ),
        shared_systems_entry_mechanics_warning=(
            systems_service.build_shared_core_entry_mechanics_impact_warning(entry)
        ),
        active_nav="systems",
    ), status_code


@login_required
def campaign_systems_control_panel_edit_shared_entry(
    campaign_slug: str,
    entry_slug: str,
):
    _dependencies().load_campaign(campaign_slug)
    if not can_edit_shared_systems_entries(campaign_slug):
        abort(403)
    entry = _get_shared_entry_for_edit(campaign_slug, entry_slug)
    return _render_shared_entry_editor(campaign_slug, entry)


@login_required
def campaign_systems_control_panel_update_shared_entry(
    campaign_slug: str,
    entry_slug: str,
):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_edit_shared_systems_entries(campaign_slug):
        abort(403)
    user = get_current_user()
    if user is None:
        abort(403)
    entry = _get_shared_entry_for_edit(campaign_slug, entry_slug)
    systems_service = dependencies.get_service()
    mechanics_warning = systems_service.build_shared_core_entry_mechanics_impact_warning(
        entry
    )
    if (
        mechanics_warning is not None
        and request.form.get("shared_entry_mechanics_impact_acknowledged") != "1"
    ):
        flash(
            "Review and acknowledge the mechanics impact warning before saving this shared/core Systems entry.",
            "error",
        )
        return _render_shared_entry_editor(
            campaign_slug,
            entry,
            form_data=request.form,
            status_code=400,
        )
    original_source_identity = _build_shared_entry_original_source_identity(entry)
    try:
        metadata = _parse_shared_entry_json_field(
            request.form.get("shared_entry_metadata_json", ""),
            field_label="Metadata JSON",
        )
        body = _parse_shared_entry_json_field(
            request.form.get("shared_entry_body_json", ""),
            field_label="Body JSON",
        )
        updated_entry = systems_service.update_shared_core_entry(
            campaign_slug,
            entry_slug,
            title=request.form.get("shared_entry_title", ""),
            source_page=request.form.get("shared_entry_source_page", ""),
            source_path=request.form.get("shared_entry_source_path", ""),
            search_text=request.form.get("shared_entry_search_text", ""),
            player_safe_default=(
                request.form.get("shared_entry_player_safe_default") == "1"
            ),
            dm_heavy=request.form.get("shared_entry_dm_heavy") == "1",
            metadata=metadata,
            body=body,
            rendered_html=request.form.get("shared_entry_rendered_html", ""),
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        return _render_shared_entry_editor(
            campaign_slug,
            entry,
            form_data=request.form,
            status_code=400,
        )

    edited_fields = _list_shared_entry_changed_fields(entry, updated_entry)
    audit_metadata = {
        "campaign_slug": campaign_slug,
        "library_slug": updated_entry.library_slug,
        "source_id": updated_entry.source_id,
        "entry_key": updated_entry.entry_key,
        "entry_slug": updated_entry.slug,
        "source": "campaign_systems_shared_entry_editor",
        "original_source_identity": original_source_identity,
        "edited_fields": edited_fields,
    }
    systems_service.store.record_shared_entry_edit_event(
        campaign_slug=campaign_slug,
        library_slug=updated_entry.library_slug,
        source_id=updated_entry.source_id,
        entry_key=updated_entry.entry_key,
        entry_slug=updated_entry.slug,
        original_source_identity=original_source_identity,
        edited_fields=edited_fields,
        actor_user_id=user.id,
        audit_event_type="campaign_systems_shared_entry_updated",
        audit_metadata=audit_metadata,
    )
    get_auth_store().write_audit_event(
        event_type="campaign_systems_shared_entry_updated",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata=audit_metadata,
    )
    flash(f"Saved shared/core Systems entry {updated_entry.title}.", "success")
    return redirect(
        url_for(
            "campaign_systems_entry_detail",
            campaign_slug=campaign_slug,
            entry_slug=updated_entry.slug,
            _anchor="systems-entry-management",
        )
    )


def _parse_source_policy_form(source_states: list[Any]) -> SystemsSourcePolicyFormInput:
    updates = []
    for state in source_states:
        source_id = state.source.source_id
        updates.append(
            SystemsSourcePolicyUpdateInput(
                source_id=source_id,
                is_enabled=request.form.get(f"source_{source_id}_enabled") == "1",
                default_visibility=request.form.get(
                    f"source_{source_id}_visibility",
                    state.default_visibility,
                ),
            )
        )
    return SystemsSourcePolicyFormInput(
        return_to_dm_content_systems=request.form.get("return_to") == "dm-content-systems",
        acknowledge_proprietary=request.form.get("acknowledge_proprietary") == "yes",
        updates=tuple(updates),
    )


def _parse_entry_override_form() -> SystemsEntryOverrideFormInput:
    raw_enabled_override = normalize_lookup(request.form.get("is_enabled_override", ""))
    enabled_override = None
    if raw_enabled_override == "enabled":
        enabled_override = True
    elif raw_enabled_override == "disabled":
        enabled_override = False
    return SystemsEntryOverrideFormInput(
        return_to_dm_content_systems=request.form.get("return_to") == "dm-content-systems",
        entry_key=request.form.get("entry_key", ""),
        visibility_override=request.form.get("visibility_override", "").strip() or None,
        is_enabled_override=enabled_override,
    )


def _parse_custom_entry_form() -> SystemsCustomEntryFormInput:
    return SystemsCustomEntryFormInput(
        had_form_fields=bool(request.form),
        return_to_dm_content_systems=request.form.get("return_to") == "dm-content-systems",
        title=request.form.get("custom_entry_title", ""),
        slug_leaf=request.form.get("custom_entry_slug", ""),
        entry_type=request.form.get("custom_entry_type", ""),
        visibility=request.form.get("custom_entry_visibility", ""),
        provenance=request.form.get("custom_entry_provenance", ""),
        search_metadata=request.form.get("custom_entry_search_metadata", ""),
        body_markdown=request.form.get("custom_entry_body_markdown", ""),
    )


def _render_custom_entry_management(
    campaign_slug: str,
    *,
    return_to_dm_content_systems: bool,
    edit_entry: Any = None,
    form_data: Any = None,
    status_code: int = 200,
):
    dependencies = _dependencies()
    if return_to_dm_content_systems:
        return render_template(
            "dm_content.html",
            **dependencies.build_dm_content_context(
                campaign_slug,
                dm_content_subpage="systems",
                custom_systems_edit_entry=edit_entry,
                custom_systems_entry_form_data=form_data,
            ),
        ), status_code
    return render_template(
        "campaign_systems_control_panel.html",
        **dependencies.build_control_context(
            campaign_slug,
            custom_systems_edit_entry=edit_entry,
            custom_systems_entry_form_data=form_data,
        ),
    ), status_code


def _redirect_after_custom_entry(
    campaign_slug: str,
    *,
    return_to_dm_content_systems: bool,
    anchor: str = "systems-custom-entries",
):
    if return_to_dm_content_systems:
        return _dependencies().redirect_to_dm_content(
            campaign_slug,
            subpage="systems",
            anchor=anchor,
        )
    return redirect(
        url_for(
            "campaign_systems_control_panel_view",
            campaign_slug=campaign_slug,
            _anchor=anchor,
        )
    )


@campaign_scope_access_required("systems")
def campaign_systems_index(campaign_slug: str):
    query = request.args.get("q", "").strip()
    reference_query = request.args.get("reference_q", "").strip()
    context = _dependencies().build_index_context(
        campaign_slug,
        query=query,
        reference_query=reference_query,
    )
    return render_template("systems_index.html", **context)


@campaign_scope_access_required("systems")
def campaign_systems_search(campaign_slug: str):
    query = request.args.get("q", "").strip()
    reference_query = request.args.get("reference_q", "").strip()
    context = _dependencies().build_index_context(
        campaign_slug,
        query=query,
        reference_query=reference_query,
    )
    return render_template("systems_index.html", **context)


@campaign_systems_source_access_required
def campaign_systems_source_detail(campaign_slug: str, source_id: str):
    reference_query = request.args.get("reference_q", "").strip()
    context = _dependencies().build_source_context(
        campaign_slug,
        source_id,
        reference_query=reference_query,
    )
    return render_template("systems_source_detail.html", **context)


@campaign_systems_source_access_required
def campaign_systems_source_type_detail(campaign_slug: str, source_id: str, entry_type: str):
    query = request.args.get("q", "").strip()
    context = _dependencies().build_source_category_context(
        campaign_slug,
        source_id,
        entry_type,
        query=query,
    )
    return render_template("systems_source_type_detail.html", **context)


@campaign_systems_entry_access_required
def campaign_systems_entry_detail(campaign_slug: str, entry_slug: str):
    context = _dependencies().build_entry_context(campaign_slug, entry_slug)
    return render_template("systems_entry_detail.html", **context)


@login_required
def campaign_systems_control_panel_update_sources(campaign_slug: str):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    systems_service = dependencies.get_service()
    form = _parse_source_policy_form(
        systems_service.list_campaign_source_states(campaign_slug)
    )
    try:
        changed_sources = systems_service.update_campaign_sources(
            campaign_slug,
            updates=[
                {
                    "source_id": update.source_id,
                    "is_enabled": update.is_enabled,
                    "default_visibility": update.default_visibility,
                }
                for update in form.updates
            ],
            actor_user_id=user.id,
            acknowledge_proprietary=form.acknowledge_proprietary,
            can_set_private=bool(user.is_admin),
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        if form.return_to_dm_content_systems:
            return render_template(
                "dm_content.html",
                **dependencies.build_dm_content_context(
                    campaign_slug,
                    dm_content_subpage="systems",
                ),
            ), 400
        return render_template(
            "campaign_systems_control_panel.html",
            **dependencies.build_control_context(campaign_slug),
        ), 400

    if changed_sources:
        auth_store = get_auth_store()
        for source in changed_sources:
            state = systems_service.get_campaign_source_state(campaign_slug, source.source_id)
            if state is None:
                continue
            auth_store.write_audit_event(
                event_type="campaign_systems_source_updated",
                actor_user_id=user.id,
                campaign_slug=campaign_slug,
                metadata={
                    "library_slug": source.library_slug,
                    "source_id": source.source_id,
                    "visibility": state.default_visibility,
                    "is_enabled": state.is_enabled,
                    "source": "campaign_systems_control_panel",
                },
            )
        flash(
            f"Updated systems sources: {', '.join(source.source_id for source in changed_sources)}.",
            "success",
        )
    else:
        flash("Systems source settings already matched those values.", "success")

    if form.return_to_dm_content_systems:
        return dependencies.redirect_to_dm_content(
            campaign_slug,
            subpage="systems",
            anchor="systems-source-enablement",
        )
    return redirect(url_for("campaign_systems_control_panel_view", campaign_slug=campaign_slug))


@login_required
def campaign_systems_control_panel_update_override(campaign_slug: str):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    form = _parse_entry_override_form()
    try:
        override = dependencies.get_service().update_campaign_entry_override(
            campaign_slug,
            entry_key=form.entry_key,
            visibility_override=form.visibility_override,
            is_enabled_override=form.is_enabled_override,
            actor_user_id=user.id,
            can_set_private=bool(user.is_admin),
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        if form.return_to_dm_content_systems:
            return render_template(
                "dm_content.html",
                **dependencies.build_dm_content_context(
                    campaign_slug,
                    dm_content_subpage="systems",
                ),
            ), 400
        return render_template(
            "campaign_systems_control_panel.html",
            **dependencies.build_control_context(campaign_slug),
        ), 400

    get_auth_store().write_audit_event(
        event_type="campaign_systems_entry_override_updated",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "entry_key": override.entry_key,
            "visibility": override.visibility_override or "inherit",
            "source": "campaign_systems_control_panel",
        },
    )
    flash("Saved systems entry override.", "success")
    if form.return_to_dm_content_systems:
        return dependencies.redirect_to_dm_content(
            campaign_slug,
            subpage="systems",
            anchor="systems-entry-overrides",
        )
    return redirect(url_for("campaign_systems_control_panel_view", campaign_slug=campaign_slug))


@login_required
def campaign_systems_control_panel_create_custom_entry(campaign_slug: str):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    form = _parse_custom_entry_form()
    try:
        entry = dependencies.get_service().create_custom_campaign_entry(
            campaign_slug,
            title=form.title,
            entry_type=form.entry_type,
            slug_leaf=form.slug_leaf,
            provenance=form.provenance,
            visibility=form.visibility,
            search_metadata=form.search_metadata,
            body_markdown=form.body_markdown,
            actor_user_id=user.id,
            can_set_private=bool(user.is_admin),
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        return _render_custom_entry_management(
            campaign_slug,
            return_to_dm_content_systems=form.return_to_dm_content_systems,
            form_data=form.as_form_data(),
            status_code=400,
        )

    get_auth_store().write_audit_event(
        event_type="campaign_systems_custom_entry_created",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "entry_key": entry.entry_key,
            "entry_slug": entry.slug,
            "entry_type": entry.entry_type,
            "source": "campaign_systems_control_panel",
        },
    )
    flash(f"Custom Systems entry {entry.title} saved.", "success")
    return _redirect_after_custom_entry(
        campaign_slug,
        return_to_dm_content_systems=form.return_to_dm_content_systems,
        anchor=f"systems-custom-entry-{dependencies.custom_entry_dom_id(entry)}",
    )


@login_required
def campaign_systems_control_panel_edit_custom_entry(campaign_slug: str, entry_slug: str):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    entry = dependencies.get_service().get_custom_campaign_entry_by_slug(
        campaign_slug,
        entry_slug,
    )
    if entry is None:
        abort(404)
    return _render_custom_entry_management(
        campaign_slug,
        return_to_dm_content_systems=request.args.get("return_to") == "dm-content-systems",
        edit_entry=entry,
    )


@login_required
def campaign_systems_control_panel_update_custom_entry(
    campaign_slug: str,
    entry_slug: str,
):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    systems_service = dependencies.get_service()
    edit_entry = systems_service.get_custom_campaign_entry_by_slug(campaign_slug, entry_slug)
    if edit_entry is None:
        abort(404)

    form = _parse_custom_entry_form()
    try:
        entry = systems_service.update_custom_campaign_entry(
            campaign_slug,
            entry_slug,
            title=form.title,
            entry_type=form.entry_type,
            provenance=form.provenance,
            visibility=form.visibility,
            search_metadata=form.search_metadata,
            body_markdown=form.body_markdown,
            actor_user_id=user.id,
            can_set_private=bool(user.is_admin),
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        return _render_custom_entry_management(
            campaign_slug,
            return_to_dm_content_systems=form.return_to_dm_content_systems,
            edit_entry=edit_entry,
            form_data=form.as_form_data(),
            status_code=400,
        )

    get_auth_store().write_audit_event(
        event_type="campaign_systems_custom_entry_updated",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "entry_key": entry.entry_key,
            "entry_slug": entry.slug,
            "entry_type": entry.entry_type,
            "source": "campaign_systems_control_panel",
        },
    )
    flash(f"Custom Systems entry {entry.title} updated.", "success")
    return _redirect_after_custom_entry(
        campaign_slug,
        return_to_dm_content_systems=form.return_to_dm_content_systems,
        anchor=f"systems-custom-entry-{dependencies.custom_entry_dom_id(entry)}",
    )


@login_required
def campaign_systems_control_panel_archive_custom_entry(
    campaign_slug: str,
    entry_slug: str,
):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
    try:
        entry = dependencies.get_service().archive_custom_campaign_entry(
            campaign_slug,
            entry_slug,
            actor_user_id=user.id,
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        return _redirect_after_custom_entry(
            campaign_slug,
            return_to_dm_content_systems=return_to_dm_content_systems,
        )

    get_auth_store().write_audit_event(
        event_type="campaign_systems_custom_entry_archived",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "entry_key": entry.entry_key,
            "entry_slug": entry.slug,
            "source": "campaign_systems_control_panel",
        },
    )
    flash(f"Archived custom Systems entry {entry.title}.", "success")
    return _redirect_after_custom_entry(
        campaign_slug,
        return_to_dm_content_systems=return_to_dm_content_systems,
        anchor=f"systems-custom-entry-{dependencies.custom_entry_dom_id(entry)}",
    )


@login_required
def campaign_systems_control_panel_restore_custom_entry(
    campaign_slug: str,
    entry_slug: str,
):
    dependencies = _dependencies()
    dependencies.load_campaign(campaign_slug)
    if not can_manage_campaign_systems(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
    try:
        entry = dependencies.get_service().restore_custom_campaign_entry(
            campaign_slug,
            entry_slug,
            actor_user_id=user.id,
        )
    except SystemsPolicyValidationError as exc:
        flash(str(exc), "error")
        return _redirect_after_custom_entry(
            campaign_slug,
            return_to_dm_content_systems=return_to_dm_content_systems,
        )

    get_auth_store().write_audit_event(
        event_type="campaign_systems_custom_entry_restored",
        actor_user_id=user.id,
        campaign_slug=campaign_slug,
        metadata={
            "entry_key": entry.entry_key,
            "entry_slug": entry.slug,
            "source": "campaign_systems_control_panel",
        },
    )
    flash(f"Restored custom Systems entry {entry.title}.", "success")
    return _redirect_after_custom_entry(
        campaign_slug,
        return_to_dm_content_systems=return_to_dm_content_systems,
        anchor=f"systems-custom-entry-{dependencies.custom_entry_dom_id(entry)}",
    )


@systems.record_once
def _register_legacy_endpoints(state: Any) -> None:
    """Register supported bare endpoint IDs without Blueprint aliases."""

    registrations = (
        (
            "/campaigns/<campaign_slug>/systems",
            "campaign_systems_index",
            campaign_systems_index,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/search",
            "campaign_systems_search",
            campaign_systems_search,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/sources/<source_id>",
            "campaign_systems_source_detail",
            campaign_systems_source_detail,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>",
            "campaign_systems_source_type_detail",
            campaign_systems_source_type_detail,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/entries/<entry_slug>",
            "campaign_systems_entry_detail",
            campaign_systems_entry_detail,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/sources",
            "campaign_systems_control_panel_update_sources",
            campaign_systems_control_panel_update_sources,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/overrides",
            "campaign_systems_control_panel_update_override",
            campaign_systems_control_panel_update_override,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/shared-core-permission",
            "campaign_systems_control_panel_update_shared_core_permission",
            campaign_systems_control_panel_update_shared_core_permission,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/shared-entries/<entry_slug>/edit",
            "campaign_systems_control_panel_edit_shared_entry",
            campaign_systems_control_panel_edit_shared_entry,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/shared-entries/<entry_slug>",
            "campaign_systems_control_panel_update_shared_entry",
            campaign_systems_control_panel_update_shared_entry,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries",
            "campaign_systems_control_panel_create_custom_entry",
            campaign_systems_control_panel_create_custom_entry,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/edit",
            "campaign_systems_control_panel_edit_custom_entry",
            campaign_systems_control_panel_edit_custom_entry,
            ("GET",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>",
            "campaign_systems_control_panel_update_custom_entry",
            campaign_systems_control_panel_update_custom_entry,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/archive",
            "campaign_systems_control_panel_archive_custom_entry",
            campaign_systems_control_panel_archive_custom_entry,
            ("POST",),
        ),
        (
            "/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/restore",
            "campaign_systems_control_panel_restore_custom_entry",
            campaign_systems_control_panel_restore_custom_entry,
            ("POST",),
        ),
    )
    for rule, endpoint, view_func, methods in registrations:
        state.app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)


def register_systems_routes(
    app: Any,
    *,
    build_index_context: Callable[..., dict[str, object]],
    build_source_context: Callable[..., dict[str, object]],
    build_source_category_context: Callable[..., dict[str, object]],
    build_entry_context: Callable[..., dict[str, object]],
    load_campaign: Callable[[str], Any],
    get_service: Callable[[], Any],
    build_control_context: Callable[[str], dict[str, object]],
    build_dm_content_context: Callable[..., dict[str, object]],
    redirect_to_dm_content: Callable[..., Any],
    custom_entry_dom_id: Callable[[Any], str],
) -> None:
    app.extensions["systems_route_dependencies"] = SystemsRouteDependencies(
        build_index_context=build_index_context,
        build_source_context=build_source_context,
        build_source_category_context=build_source_category_context,
        build_entry_context=build_entry_context,
        load_campaign=load_campaign,
        get_service=get_service,
        build_control_context=build_control_context,
        build_dm_content_context=build_dm_content_context,
        redirect_to_dm_content=redirect_to_dm_content,
        custom_entry_dom_id=custom_entry_dom_id,
    )
    app.register_blueprint(systems)
