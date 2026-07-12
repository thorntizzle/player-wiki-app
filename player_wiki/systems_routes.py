from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, render_template, request

from .auth import (
    campaign_scope_access_required,
    campaign_systems_entry_access_required,
    campaign_systems_source_access_required,
)


systems = Blueprint("systems", __name__)


@dataclass(frozen=True)
class SystemsRouteDependencies:
    build_index_context: Callable[..., dict[str, object]]
    build_source_context: Callable[..., dict[str, object]]
    build_source_category_context: Callable[..., dict[str, object]]
    build_entry_context: Callable[..., dict[str, object]]


def _dependencies() -> SystemsRouteDependencies:
    return current_app.extensions["systems_route_dependencies"]


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


@systems.record_once
def _register_legacy_endpoints(state: Any) -> None:
    """Register supported bare endpoint IDs without Blueprint aliases."""

    registrations = (
        (
            "/campaigns/<campaign_slug>/systems",
            "campaign_systems_index",
            campaign_systems_index,
        ),
        (
            "/campaigns/<campaign_slug>/systems/search",
            "campaign_systems_search",
            campaign_systems_search,
        ),
        (
            "/campaigns/<campaign_slug>/systems/sources/<source_id>",
            "campaign_systems_source_detail",
            campaign_systems_source_detail,
        ),
        (
            "/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>",
            "campaign_systems_source_type_detail",
            campaign_systems_source_type_detail,
        ),
        (
            "/campaigns/<campaign_slug>/systems/entries/<entry_slug>",
            "campaign_systems_entry_detail",
            campaign_systems_entry_detail,
        ),
    )
    for rule, endpoint, view_func in registrations:
        state.app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=("GET",))


def register_systems_routes(
    app: Any,
    *,
    build_index_context: Callable[..., dict[str, object]],
    build_source_context: Callable[..., dict[str, object]],
    build_source_category_context: Callable[..., dict[str, object]],
    build_entry_context: Callable[..., dict[str, object]],
) -> None:
    app.extensions["systems_route_dependencies"] = SystemsRouteDependencies(
        build_index_context=build_index_context,
        build_source_context=build_source_context,
        build_source_category_context=build_source_category_context,
        build_entry_context=build_entry_context,
    )
    app.register_blueprint(systems)
