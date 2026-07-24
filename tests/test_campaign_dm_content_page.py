from __future__ import annotations

from tests.helpers.systems_import_helpers import (
    _build_malformed_utf8_systems_import_archive,
    _build_systems_import_archive,
    _build_unsafe_systems_import_archive,
)
from html.parser import HTMLParser
from io import BytesIO
import logging
from pathlib import Path
import sqlite3
from uuid import uuid4
import zipfile

import pytest
import yaml

from player_wiki.app import create_app
from player_wiki import systems_routes
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.campaign_visibility import VISIBILITY_DM, VISIBILITY_PLAYERS
from player_wiki.config import Config
from player_wiki.db import init_database
from player_wiki.auth_store import AuthStore
from player_wiki.system_policy import XIANXIA_SYSTEM_CODE
from player_wiki.systems_importer import SUPPORTED_ENTRY_TYPES
from player_wiki.systems_ingest import SystemsArchiveLimits
from tests.sample_data import build_test_campaigns_dir

TEST_STATBLOCK_MARKDOWN = b"""AT-A-GLANCE (Quick Reference)
--------------------------------------------------------------------------------
Name: Imperial Signal Operative
Creature Type: Humanoid (aven)
Role/Archetype: Support Caster
Challenge Rating: CR 3
Proficiency Bonus: +2
Speed: 30 ft., fly 40 ft.

STATBLOCK (5e Format)
--------------------------------------------------------------------------------
Armor Class 15 (studded leather)
Hit Points 55 (10d8 + 10)
Speed 30 ft., fly 40 ft.

STR 10 (+0)  DEX 14 (+2)  CON 12 (+1)  INT 16 (+3)  WIS 14 (+2)  CHA 11 (+0)
"""

TEST_UNGROUPED_STATBLOCK_MARKDOWN = b"""AT-A-GLANCE (Quick Reference)
--------------------------------------------------------------------------------
Name: Dock Runner
Creature Type: Humanoid
Role/Archetype: Scout
Challenge Rating: CR 1
Proficiency Bonus: +2
Speed: 30 ft.

STATBLOCK (5e Format)
--------------------------------------------------------------------------------
Armor Class 13 (leather armor)
Hit Points 22 (5d8)
Speed 30 ft.

STR 10 (+0)  DEX 14 (+2)  CON 10 (+0)  INT 11 (+0)  WIS 12 (+1)  CHA 10 (+0)
"""

UPDATED_STATBLOCK_MARKDOWN = """# Imperial Signal Lieutenant

Armor Class 16 (studded leather, shield)
Hit Points 64 (12d8 + 12)
Speed 30 ft., fly 45 ft.

STR 10 (+0)  DEX 16 (+3)  CON 12 (+1)  INT 16 (+3)  WIS 14 (+2)  CHA 11 (+0)
"""

TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\x8f\x9b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

SYSTEMS_MANAGEMENT_LANES = {
    "systems-source-enablement": "Source Enablement",
    "systems-shared-core-permission": "Shared/Core Editing",
    "systems-entry-overrides": "Entry Overrides",
    "systems-custom-entries": "Custom Entries",
    "systems-shared-imports": "Shared Source Imports",
    "systems-import-history": "Import-Run History",
}

SYSTEMS_SETUP_NEEDED_TASK_ORDER = (
    "systems-source-enablement",
    "systems-entry-overrides",
    "systems-custom-entries",
    "systems-shared-core-permission",
    "systems-shared-imports",
    "systems-import-history",
)

SYSTEMS_SETUP_COMPLETE_TASK_ORDER = (
    "systems-entry-overrides",
    "systems-custom-entries",
    "systems-source-enablement",
    "systems-shared-core-permission",
    "systems-shared-imports",
    "systems-import-history",
)

SYSTEMS_MANAGEMENT_SUMMARIES = {
    lane_id: f"Show or hide {heading}"
    for lane_id, heading in SYSTEMS_MANAGEMENT_LANES.items()
}

SYSTEMS_ALWAYS_OPEN_LANES = set(SYSTEMS_MANAGEMENT_LANES) - {
    "systems-source-enablement",
    "systems-entry-overrides",
    "systems-custom-entries",
    "systems-shared-imports",
    "systems-import-history",
}
SYSTEMS_SOURCE_OPEN_LANES = SYSTEMS_ALWAYS_OPEN_LANES | {
    "systems-source-enablement"
}
SYSTEMS_ENTRY_OVERRIDE_OPEN_LANES = SYSTEMS_ALWAYS_OPEN_LANES | {
    "systems-entry-overrides"
}
SYSTEMS_CUSTOM_ENTRY_OPEN_LANES = SYSTEMS_ALWAYS_OPEN_LANES | {
    "systems-custom-entries"
}
SYSTEMS_IMPORT_VALIDATION_OPEN_LANES = SYSTEMS_ALWAYS_OPEN_LANES | {
    "systems-shared-imports"
}
SYSTEMS_ENTRY_OVERRIDE_AND_CUSTOM_ENTRY_OPEN_LANES = (
    SYSTEMS_ENTRY_OVERRIDE_OPEN_LANES | SYSTEMS_CUSTOM_ENTRY_OPEN_LANES
)


class _SystemsManagementLaneParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._details_stack: list[str | None] = []
        self._heading_lane: str | None = None
        self._heading_parts: list[str] = []
        self._summary_lane: str | None = None
        self._summary_parts: list[str] = []
        self._task_nav_stack: list[bool] = []
        self._task_link_href: str | None = None
        self._task_link_parts: list[str] = []
        self.inventory: dict[str, str] = {}
        self.open_lanes: set[str] = set()
        self.summaries: dict[str, str] = {}
        self.task_nav_count = 0
        self.task_links: list[tuple[str, str]] = []
        self.native_disclosure_aria: list[tuple[str, str]] = []
        self.source_checkbox_checked: dict[str, bool] = {}
        self.source_selected_visibility: dict[str, str] = {}
        self.entry_override_form_entry_key = ""
        self.entry_override_selected_visibility = ""
        self.entry_override_selected_enablement = ""
        self.hidden_return_values: list[str] = []
        self._source_visibility_select: str | None = None
        self._entry_override_select: str | None = None
        self._entry_override_select_seen = False
        self.form_actions: dict[str, list[str]] = {
            lane_id: [] for lane_id in SYSTEMS_MANAGEMENT_LANES
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "nav":
            is_task_nav = attributes.get("aria-label") == "Systems management tasks"
            self._task_nav_stack.append(is_task_nav)
            if is_task_nav:
                self.task_nav_count += 1
        elif tag == "details":
            lane_id = attributes.get("id")
            lane_id = lane_id if lane_id in SYSTEMS_MANAGEMENT_LANES else None
            self._details_stack.append(lane_id)
            if lane_id is not None and "open" in attributes:
                self.open_lanes.add(lane_id)
            for name, value in attrs:
                if name.startswith("aria-"):
                    self.native_disclosure_aria.append((name, value or ""))
        elif tag == "summary":
            if self._details_stack and self._details_stack[-1] is not None:
                self._summary_lane = self._details_stack[-1]
                self._summary_parts = []
            for name, value in attrs:
                if name.startswith("aria-"):
                    self.native_disclosure_aria.append((name, value or ""))
        elif tag == "h2" and self._details_stack and self._details_stack[-1] is not None:
            self._heading_lane = self._details_stack[-1]
            self._heading_parts = []
        elif tag == "a" and any(self._task_nav_stack):
            self._task_link_href = attributes.get("href")
            self._task_link_parts = []
        elif tag == "form":
            for lane_id in reversed(self._details_stack):
                if lane_id is not None:
                    self.form_actions[lane_id].append(attributes.get("action", ""))
                    break
        elif tag == "input":
            name = attributes.get("name") or ""
            if name.startswith("source_") and name.endswith("_enabled"):
                source_id = name.removeprefix("source_").removesuffix("_enabled")
                self.source_checkbox_checked[source_id] = "checked" in attributes
            elif name == "return_to":
                self.hidden_return_values.append(attributes.get("value") or "")
            elif name == "entry_key":
                self.entry_override_form_entry_key = attributes.get("value") or ""
        elif tag == "select":
            name = attributes.get("name") or ""
            if name.startswith("source_") and name.endswith("_visibility"):
                self._source_visibility_select = (
                    name.removeprefix("source_").removesuffix("_visibility")
                )
            elif name in {"visibility_override", "is_enabled_override"}:
                self._entry_override_select = name
                self._entry_override_select_seen = False
        elif (
            tag == "option"
            and self._source_visibility_select is not None
            and "selected" in attributes
        ):
            self.source_selected_visibility[self._source_visibility_select] = (
                attributes.get("value") or ""
            )
        elif tag == "option" and self._entry_override_select is not None:
            option_value = attributes.get("value") or ""
            if self._entry_override_select == "visibility_override":
                if not self._entry_override_select_seen or "selected" in attributes:
                    self.entry_override_selected_visibility = option_value
            elif not self._entry_override_select_seen or "selected" in attributes:
                self.entry_override_selected_enablement = option_value
            self._entry_override_select_seen = True

    def handle_data(self, data: str) -> None:
        if self._heading_lane is not None:
            self._heading_parts.append(data)
        if self._summary_lane is not None:
            self._summary_parts.append(data)
        if self._task_link_href is not None:
            self._task_link_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._heading_lane is not None:
            self.inventory[self._heading_lane] = " ".join(
                "".join(self._heading_parts).split()
            )
            self._heading_lane = None
            self._heading_parts = []
        elif tag == "summary" and self._summary_lane is not None:
            self.summaries[self._summary_lane] = " ".join(
                "".join(self._summary_parts).split()
            )
            self._summary_lane = None
            self._summary_parts = []
        elif tag == "a" and self._task_link_href is not None:
            self.task_links.append(
                (
                    self._task_link_href,
                    " ".join("".join(self._task_link_parts).split()),
                )
            )
            self._task_link_href = None
            self._task_link_parts = []
        elif tag == "details" and self._details_stack:
            self._details_stack.pop()
        elif tag == "nav" and self._task_nav_stack:
            self._task_nav_stack.pop()
        elif tag == "select":
            self._source_visibility_select = None
            self._entry_override_select = None
            self._entry_override_select_seen = False


def _list_statblocks(app):
    with app.app_context():
        return app.extensions["campaign_dm_content_service"].list_statblocks("linden-pass")


def _list_condition_definitions(app):
    with app.app_context():
        return app.extensions["campaign_dm_content_service"].list_condition_definitions("linden-pass")


def _list_session_articles(app):
    with app.app_context():
        return app.extensions["campaign_session_service"].list_articles("linden-pass")


def _list_combatants(app):
    with app.app_context():
        return app.extensions["campaign_combat_service"].list_combatants("linden-pass")


def _list_conditions(app, combatant_id: int):
    with app.app_context():
        return app.extensions["campaign_combat_service"].list_conditions_by_combatant(
            "linden-pass"
        ).get(combatant_id, [])


def _build_systems_source_form(app) -> dict[str, str]:
    with app.app_context():
        rows = app.extensions["systems_service"].list_campaign_source_states("linden-pass")

    data: dict[str, str] = {}
    for row in rows:
        if row.is_enabled:
            data[f"source_{row.source.source_id}_enabled"] = "1"
        data[f"source_{row.source.source_id}_visibility"] = row.default_visibility
    return data


def _seed_entry_override_entry(
    app,
    *,
    source_id: str = "ENTRY-OVERRIDE-TEST",
    source_title: str = "Entry Override Test Source",
    license_class: str = "open_license",
    source_enabled: bool = True,
    source_visibility: str = VISIBILITY_PLAYERS,
    entry_slug: str = "entry-override-test",
    entry_title: str = "Entry Override Test",
) -> str:
    entry_key = (
        f"dnd-5e|rule|{source_id.casefold()}|{entry_slug}"
    )
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            source_id,
            title=source_title,
            license_class=license_class,
            public_visibility_allowed=license_class != "proprietary_private",
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=source_enabled,
            default_visibility=source_visibility,
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": entry_key,
                    "entry_type": "rule",
                    "slug": entry_slug,
                    "title": entry_title,
                    "search_text": entry_title.casefold(),
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {},
                }
            ],
            entry_types=["rule"],
        )
    return entry_key


def _seed_persisted_entry_override_matrix(app) -> tuple[str, str, str]:
    private_key = _seed_entry_override_entry(
        app,
        source_id="A-PRIVATE-OVERRIDE",
        source_title="Private Proprietary Override Source",
        license_class="proprietary_private",
        source_enabled=False,
        source_visibility=VISIBILITY_DM,
        entry_slug="private-disabled-override",
        entry_title="Private Disabled Override",
    )
    shared_key = _seed_entry_override_entry(
        app,
        source_id="B-SHARED-OVERRIDE",
        source_title="Shared Override Source",
        entry_slug="shared-enabled-override",
        entry_title="Shared Enabled Override",
    )
    custom_key = _seed_entry_override_entry(
        app,
        source_id="CUSTOM-LINDEN-PASS",
        source_title="Linden Pass Custom Systems",
        license_class="custom_campaign",
        source_visibility=VISIBILITY_DM,
        entry_slug="custom-inherited-override",
        entry_title="Custom Inherited Override",
    )
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=private_key,
            visibility_override="private",
            is_enabled_override=False,
        )
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=shared_key,
            visibility_override=VISIBILITY_PLAYERS,
            is_enabled_override=True,
        )
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=custom_key,
            visibility_override=None,
            is_enabled_override=None,
        )
    return private_key, shared_key, custom_key


def _find_combatant(app, *, name: str):
    for combatant in _list_combatants(app):
        if combatant.display_name == name:
            return combatant
    return None


def test_dm_can_open_dm_content_page_and_players_cannot_by_default(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    dm_page = client.get("/campaigns/linden-pass/dm-content")
    systems_page = client.get("/campaigns/linden-pass/dm-content/systems")
    staged_articles_page = client.get("/campaigns/linden-pass/dm-content/staged-articles")
    conditions_page = client.get("/campaigns/linden-pass/dm-content/conditions")

    assert campaign.status_code == 200
    campaign_html = campaign.get_data(as_text=True)
    assert "DM Content" in campaign_html
    assert 'href="/campaigns/linden-pass/dm-content"' in campaign_html

    assert dm_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    assert "Statblock library" in dm_html
    assert "Systems" in dm_html
    assert "Staged Articles" in dm_html
    assert "Conditions" in dm_html
    assert 'name="statblock_file"' in dm_html
    assert '/campaigns/linden-pass/dm-content/systems' in dm_html
    assert '/campaigns/linden-pass/dm-content/staged-articles' in dm_html
    assert '/campaigns/linden-pass/dm-content/conditions' in dm_html

    assert systems_page.status_code == 200
    systems_html = systems_page.get_data(as_text=True)
    assert "Source Enablement" in systems_html
    assert "Entry Overrides" in systems_html
    assert "Custom Entries" in systems_html
    assert "Import-Run History" in systems_html

    assert staged_articles_page.status_code == 200
    staged_html = staged_articles_page.get_data(as_text=True)
    assert "Stage session articles" in staged_html
    assert "Session reveal queue" in staged_html
    assert 'action="/campaigns/linden-pass/dm-content/staged-articles"' in staged_html

    assert conditions_page.status_code == 200
    assert "Custom conditions" in conditions_page.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    player_campaign = client.get("/campaigns/linden-pass")
    player_page = client.get("/campaigns/linden-pass/dm-content")

    assert 'href="/campaigns/linden-pass/dm-content"' not in player_campaign.get_data(as_text=True)
    assert player_page.status_code == 404


@pytest.mark.parametrize(
    "path",
    (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    ),
)
def test_flask_systems_management_hosts_expose_the_same_semantic_six_lane_inventory(
    client,
    sign_in,
    users,
    path,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(path)

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    parser = _SystemsManagementLaneParser()
    parser.feed(body)

    assert parser.inventory == SYSTEMS_MANAGEMENT_LANES
    assert parser.task_nav_count == 1
    assert tuple(
        href.removeprefix("#") for href, _label in parser.task_links
    ) == SYSTEMS_SETUP_COMPLETE_TASK_ORDER
    assert dict(
        (href.removeprefix("#"), label) for href, label in parser.task_links
    ) == SYSTEMS_MANAGEMENT_LANES
    assert parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES
    assert parser.summaries == SYSTEMS_MANAGEMENT_SUMMARIES
    assert parser.native_disclosure_aria == []
    assert parser.form_actions["systems-source-enablement"] == [
        "/campaigns/linden-pass/systems/control-panel/sources"
    ]
    assert parser.form_actions["systems-entry-overrides"] == [
        "/campaigns/linden-pass/systems/control-panel/overrides"
    ]
    assert parser.form_actions["systems-custom-entries"] == [
        "/campaigns/linden-pass/systems/control-panel/custom-entries"
    ]
    assert "Proprietary-source acknowledgement:" in body
    assert "Proprietary - private campaign use" in body
    assert "This source is restricted from public visibility by policy." in body
    assert (
        "I understand proprietary systems sources are for private campaign use "
        "only and must not be made public or redistributed."
    ) in " ".join(body.split())
    assert "source_path" not in body
    assert "audit_state" not in body
    assert "storage_state" not in body
    assert "Campaign Item Mechanics" not in body
    assert "/systems/item-mechanics/import" not in body


def test_systems_management_partial_is_shared_by_exactly_two_hosts_and_keeps_native_structure():
    templates_root = Path(__file__).parents[1] / "player_wiki" / "templates"
    include_marker = '{% include "_systems_management_panel.html" %}'
    include_hosts = sorted(
        path.name
        for path in templates_root.glob("*.html")
        if include_marker in path.read_text(encoding="utf-8")
    )
    partial = (templates_root / "_systems_management_panel.html").read_text(
        encoding="utf-8"
    )

    assert include_hosts == [
        "campaign_systems_control_panel.html",
        "dm_content.html",
    ]
    for host_name in include_hosts:
        host_source = (templates_root / host_name).read_text(encoding="utf-8")
        assert 'href="#systems-' not in host_source
    assert partial.count('aria-label="Systems management tasks"') == 1
    assert partial.count('class="card systems-management-lane"') == 6
    assert partial.count(" open>") == 1
    assert (
        'id="systems-source-enablement"{% if '
        "systems_source_enablement_setup_needed or "
        "systems_source_enablement_validation_active %} open{% endif %}>"
    ) in partial
    assert (
        'id="systems-entry-overrides"{% if '
        "systems_entry_overrides_open %} open{% endif %}>"
    ) in partial
    assert "{% set systems_custom_entries_open = (" in partial
    assert "custom_systems_edit_entry" in partial
    assert "custom_entry_count" in partial
    assert 'request.method == "POST"' in partial
    assert "campaign_systems_control_panel_create_custom_entry" in partial
    assert "campaign_systems_control_panel_update_custom_entry" in partial
    assert (
        'id="systems-custom-entries"{% if systems_custom_entries_open %} '
        "open{% endif %}>"
    ) in partial
    assert (
        'id="systems-shared-imports"{% if can_import_shared_systems and '
        'request.method == "POST" and request.endpoint == '
        '"campaign_systems_control_panel_import_dnd5e" %} open{% endif %}>'
    ) in partial
    assert partial.count("<summary>Show or hide ") == 6
    assert partial.count("<h2>") == 6
    assert "<section class=\"card\" id=\"systems-" not in partial
    assert 'aria-expanded=' not in partial
    assert 'aria-controls=' not in partial
    entry_override_markup = partial[
        partial.index('id="systems-entry-overrides"'):
        partial.index('id="systems-custom-entries"')
    ]
    assert entry_override_markup.count("{{ csrf_input() }}") == 1
    assert (
        '<form method="post" '
        "action=\"{{ url_for('campaign_systems_control_panel_update_override', "
        'campaign_slug=campaign.slug) }}" class="stack-form">'
    ) in entry_override_markup
    assert "Delete entry override" not in entry_override_markup
    assert "Remove entry override" not in entry_override_markup
    assert "Reset entry override" not in entry_override_markup
    assert "visibility_override" in entry_override_markup
    assert "is_enabled_override" in entry_override_markup
    assert (
        '<details class="feature-detail">\n'
        "              <summary>Review imported files and entry counts</summary>"
    ) in partial
    assert '<details class="feature-detail" open>' not in partial
    assert "systems_import_archive" in partial
    shared_import_markup = partial[
        partial.index('id="systems-shared-imports"'):
        partial.index('id="systems-import-history"')
    ]
    assert 'id="systems-shared-imports" open>' not in shared_import_markup
    assert "import_run_count" not in shared_import_markup
    assert 'id="systems-import-history">' in partial
    assert 'id="systems-import-history" open>' not in partial
    assert "systems-custom-entry-editor" in partial
    assert "systems/item-mechanics/import" not in partial
    assert "request.args" not in partial
    assert "fragment" not in partial
    assert "Campaign Item Mechanics" not in partial
    assert "Delete custom" not in partial
    assert "atomic" not in partial
    assert "rollback" not in partial
    assert "retry" not in partial
    assert "recovery" not in partial


@pytest.mark.parametrize(
    "path",
    (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    ),
)
def test_entry_override_disclosure_uses_only_persisted_prefill_or_internal_validation_state(
    client,
    sign_in,
    users,
    path,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    for query_string in (
        {},
        {"entry_key": "   "},
        {"systems_entry_override_validation_active": "1"},
        {
            "entry_key": "   ",
            "systems_entry_override_validation_active": "true",
        },
    ):
        response = client.get(path, query_string=query_string)
        assert response.status_code == 200
        parser = _SystemsManagementLaneParser()
        parser.feed(response.get_data(as_text=True))
        assert parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES
        assert parser.entry_override_form_entry_key == ""
        assert parser.entry_override_selected_visibility == ""
        assert parser.entry_override_selected_enablement == ""

    prefill_key = 'spell::<flare>&"quoted"'
    prefill_response = client.get(
        path,
        query_string={
            "entry_key": prefill_key,
            "systems_entry_override_validation_active": "0",
        },
    )
    assert prefill_response.status_code == 200
    prefill_body = prefill_response.get_data(as_text=True)
    prefill_parser = _SystemsManagementLaneParser()
    prefill_parser.feed(prefill_body)
    assert prefill_parser.open_lanes == SYSTEMS_ENTRY_OVERRIDE_OPEN_LANES
    assert prefill_parser.entry_override_form_entry_key == prefill_key
    assert prefill_parser.entry_override_selected_visibility == ""
    assert prefill_parser.entry_override_selected_enablement == ""
    assert prefill_key not in prefill_body
    assert "spell::&lt;flare&gt;&amp;&#34;quoted&#34;" in prefill_body


@pytest.mark.parametrize(
    "path",
    (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    ),
)
def test_custom_entry_disclosure_opens_only_for_existing_custom_workflow_state(
    client,
    sign_in,
    users,
    path,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    return_to = "dm-content-systems" if path.endswith("/dm-content/systems") else ""
    return_data = {"return_to": return_to} if return_to else {}
    entry_slug = "custom-linden-pass-disclosure-custom-entry"
    entry_anchor = f"#systems-custom-entry-{entry_slug}"

    for query_string in (
        {},
        {"systems_custom_entry_validation_active": "1"},
        {"custom_entry_title": "untrusted-query-prefill"},
    ):
        response = client.get(path, query_string=query_string)
        assert response.status_code == 200
        parser = _SystemsManagementLaneParser()
        parser.feed(response.get_data(as_text=True))
        assert parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES

    validation_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data=return_data,
        follow_redirects=False,
    )
    assert validation_response.status_code == 400
    validation_body = validation_response.get_data(as_text=True)
    validation_parser = _SystemsManagementLaneParser()
    validation_parser.feed(validation_body)
    assert validation_parser.open_lanes == SYSTEMS_CUSTOM_ENTRY_OPEN_LANES
    assert "Choose a URL slug or title before saving a custom Systems entry." in validation_body

    idle_response = client.get(path)
    idle_parser = _SystemsManagementLaneParser()
    idle_parser.feed(idle_response.get_data(as_text=True))
    assert idle_parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES

    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            **return_data,
            "custom_entry_title": "Disclosure Custom Entry",
            "custom_entry_slug": "disclosure-custom-entry",
            "custom_entry_type": "rule",
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": "Custom disclosure body.",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"] == f"{path}{entry_anchor}"
    prg_response = client.get(create_response.headers["Location"])
    prg_parser = _SystemsManagementLaneParser()
    prg_parser.feed(prg_response.get_data(as_text=True))
    assert (
        prg_parser.open_lanes
        == SYSTEMS_ENTRY_OVERRIDE_AND_CUSTOM_ENTRY_OPEN_LANES
    )

    edit_response = client.get(
        f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}/edit",
        query_string=return_data,
    )
    assert edit_response.status_code == 200
    edit_parser = _SystemsManagementLaneParser()
    edit_parser.feed(edit_response.get_data(as_text=True))
    assert (
        edit_parser.open_lanes
        == SYSTEMS_ENTRY_OVERRIDE_AND_CUSTOM_ENTRY_OPEN_LANES
    )

    archive_response = client.post(
        f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}/archive",
        data=return_data,
        follow_redirects=False,
    )
    assert archive_response.status_code == 302
    assert archive_response.headers["Location"] == f"{path}{entry_anchor}"
    archive_parser = _SystemsManagementLaneParser()
    archive_parser.feed(client.get(archive_response.headers["Location"]).get_data(as_text=True))
    assert (
        archive_parser.open_lanes
        == SYSTEMS_ENTRY_OVERRIDE_AND_CUSTOM_ENTRY_OPEN_LANES
    )

    restore_response = client.post(
        f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}/restore",
        data=return_data,
        follow_redirects=False,
    )
    assert restore_response.status_code == 302
    assert restore_response.headers["Location"] == f"{path}{entry_anchor}"
    restore_parser = _SystemsManagementLaneParser()
    restore_parser.feed(client.get(restore_response.headers["Location"]).get_data(as_text=True))
    assert (
        restore_parser.open_lanes
        == SYSTEMS_ENTRY_OVERRIDE_AND_CUSTOM_ENTRY_OPEN_LANES
    )


@pytest.mark.parametrize(
    "path",
    (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    ),
)
def test_any_persisted_shared_custom_private_disabled_or_inherited_override_opens_lane(
    app,
    client,
    sign_in,
    users,
    path,
):
    private_key, shared_key, custom_key = _seed_persisted_entry_override_matrix(
        app
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(path)

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    parser = _SystemsManagementLaneParser()
    parser.feed(body)
    assert parser.open_lanes == SYSTEMS_ENTRY_OVERRIDE_AND_CUSTOM_ENTRY_OPEN_LANES
    assert "3 saved overrides" in body
    assert body.index(private_key) < body.index(shared_key) < body.index(custom_key)
    assert "Private Disabled Override" in body
    assert "Private Proprietary Override Source (A-PRIVATE-OVERRIDE)" in body
    assert '<span class="meta-badge">Private</span>' in body
    assert '<span class="meta-badge">Disabled</span>' in body
    assert "Shared Enabled Override" in body
    assert "Shared Override Source (B-SHARED-OVERRIDE)" in body
    assert '<span class="meta-badge">Players</span>' in body
    assert '<span class="meta-badge">Enabled</span>' in body
    assert "Custom Inherited Override" in body
    assert "Linden Pass Custom Systems (CUSTOM-LINDEN-PASS)" in body
    assert '<span class="meta-badge">Inherit source default</span>' in body
    assert '<span class="meta-badge">Inherit source enablement</span>' in body
    assert "Delete entry override" not in body
    assert "Remove entry override" not in body
    assert "Reset entry override" not in body
    assert "source_path" not in body
    assert "audit_state" not in body
    assert "storage_state" not in body
    assert "Campaign Item Mechanics" not in body


@pytest.mark.parametrize(
    ("return_to", "expected_location"),
    (
        ("", "/campaigns/linden-pass/systems/control-panel"),
        (
            "dm-content-systems",
            (
                "/campaigns/linden-pass/dm-content/systems"
                "#systems-entry-overrides"
            ),
        ),
    ),
)
def test_entry_override_validation_success_repeat_and_inheritance_prg_contract(
    app,
    client,
    sign_in,
    users,
    return_to,
    expected_location,
):
    entry_key = _seed_entry_override_entry(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    form_data = {
        "entry_key": entry_key,
        "visibility_override": VISIBILITY_DM,
        "is_enabled_override": "disabled",
    }
    if return_to:
        form_data["return_to"] = return_to

    for expected_audit_count in (1, 2):
        response = client.post(
            "/campaigns/linden-pass/systems/control-panel/overrides",
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"] == expected_location
        followed = client.get(response.headers["Location"])
        parser = _SystemsManagementLaneParser()
        parser.feed(followed.get_data(as_text=True))
        assert parser.open_lanes == SYSTEMS_ENTRY_OVERRIDE_OPEN_LANES
        assert "1 saved override" in followed.get_data(as_text=True)
        assert "DM" in followed.get_data(as_text=True)
        assert "Disabled" in followed.get_data(as_text=True)
        with app.app_context():
            events = AuthStore().list_recent_audit_events(
                event_type="campaign_systems_entry_override_updated",
                campaign_slug="linden-pass",
            )
            assert len(events) == expected_audit_count

    inheritance_form = {
        "entry_key": entry_key,
        "visibility_override": "",
        "is_enabled_override": "",
    }
    if return_to:
        inheritance_form["return_to"] = return_to
    inheritance_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/overrides",
        data=inheritance_form,
        follow_redirects=False,
    )
    assert inheritance_response.status_code == 302
    assert inheritance_response.headers["Location"] == expected_location

    inheritance_page = client.get(inheritance_response.headers["Location"])
    inheritance_body = inheritance_page.get_data(as_text=True)
    inheritance_parser = _SystemsManagementLaneParser()
    inheritance_parser.feed(inheritance_body)
    assert inheritance_parser.open_lanes == SYSTEMS_ENTRY_OVERRIDE_OPEN_LANES
    assert "1 saved override" in inheritance_body
    assert "Inherit source default" in inheritance_body
    assert "Inherit source enablement" in inheritance_body
    assert "Delete entry override" not in inheritance_body
    assert "Remove entry override" not in inheritance_body
    assert "Reset entry override" not in inheritance_body
    with app.app_context():
        persisted = app.extensions[
            "systems_store"
        ].get_campaign_entry_override("linden-pass", entry_key)
        assert persisted is not None
        assert persisted.visibility_override is None
        assert persisted.is_enabled_override is None
        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_entry_override_updated",
            campaign_slug="linden-pass",
        )
        assert len(events) == 3


@pytest.mark.parametrize(
    ("return_to", "expected_hidden_return"),
    (
        ("", None),
        ("dm-content-systems", "dm-content-systems"),
    ),
)
def test_entry_override_validation_400_opens_only_internal_flag_and_loses_invalid_fields(
    app,
    client,
    sign_in,
    users,
    return_to,
    expected_hidden_return,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    invalid_entry_key = '<missing-entry>&"not-retained"'
    data = {
        "entry_key": invalid_entry_key,
        "visibility_override": "outsiders",
        "is_enabled_override": "unexpected",
    }
    if return_to:
        data["return_to"] = return_to

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/overrides",
        data=data,
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    parser = _SystemsManagementLaneParser()
    parser.feed(body)
    assert parser.open_lanes == SYSTEMS_ENTRY_OVERRIDE_OPEN_LANES
    assert parser.entry_override_form_entry_key == ""
    assert parser.entry_override_selected_visibility == ""
    assert parser.entry_override_selected_enablement == ""
    assert invalid_entry_key not in body
    assert "outsiders" not in body
    assert "unexpected" not in body
    assert "Choose a valid systems entry before saving an override." in body
    if expected_hidden_return is None:
        assert parser.hidden_return_values == []
    else:
        assert parser.hidden_return_values
        assert set(parser.hidden_return_values) == {expected_hidden_return}
    with app.app_context():
        store = app.extensions["systems_store"]
        library_slug = app.extensions[
            "systems_service"
        ].get_campaign_library_slug("linden-pass")
        assert store.list_campaign_entry_overrides(
            "linden-pass",
            library_slug,
        ) == []
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_entry_override_updated",
            campaign_slug="linden-pass",
        )


def test_entry_override_write_and_audit_failures_recover_from_durable_outcome(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    write_failure_key = _seed_entry_override_entry(
        app,
        source_id="OVERRIDE-WRITE-FAILURE",
        entry_slug="override-write-failure",
        entry_title="Override Write Failure",
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])
    store = app.extensions["systems_store"]
    original_override_write = store.upsert_campaign_entry_override

    def fail_override_write(*args, **kwargs):
        raise RuntimeError("override write unavailable")

    monkeypatch.setattr(
        store,
        "upsert_campaign_entry_override",
        fail_override_write,
    )
    with pytest.raises(RuntimeError, match="override write unavailable"):
        client.post(
            "/campaigns/linden-pass/systems/control-panel/overrides",
            data={
                "entry_key": write_failure_key,
                "visibility_override": VISIBILITY_DM,
                "is_enabled_override": "disabled",
            },
        )
    monkeypatch.setattr(
        store,
        "upsert_campaign_entry_override",
        original_override_write,
    )
    with app.app_context():
        assert store.get_campaign_entry_override(
            "linden-pass",
            write_failure_key,
        ) is None
    for host_path in (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    ):
        collapsed_parser = _SystemsManagementLaneParser()
        collapsed_parser.feed(client.get(host_path).get_data(as_text=True))
        assert collapsed_parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES

    audit_failure_key = _seed_entry_override_entry(
        app,
        source_id="OVERRIDE-AUDIT-FAILURE",
        entry_slug="override-audit-failure",
        entry_title="Override Audit Failure",
    )
    auth_store = app.extensions["auth_store"]
    original_audit_write = auth_store.write_audit_event

    def fail_override_audit(*args, **kwargs):
        raise RuntimeError("override audit unavailable")

    monkeypatch.setattr(auth_store, "write_audit_event", fail_override_audit)
    with pytest.raises(RuntimeError, match="override audit unavailable"):
        client.post(
            "/campaigns/linden-pass/systems/control-panel/overrides",
            data={
                "entry_key": audit_failure_key,
                "visibility_override": VISIBILITY_DM,
                "is_enabled_override": "disabled",
            },
        )
    monkeypatch.setattr(auth_store, "write_audit_event", original_audit_write)

    with app.app_context():
        durable_override = store.get_campaign_entry_override(
            "linden-pass",
            audit_failure_key,
        )
        assert durable_override is not None
        assert durable_override.visibility_override == VISIBILITY_DM
        assert durable_override.is_enabled_override is False
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_entry_override_updated",
            campaign_slug="linden-pass",
        )
    for host_path in (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    ):
        open_parser = _SystemsManagementLaneParser()
        open_parser.feed(client.get(host_path).get_data(as_text=True))
        assert open_parser.open_lanes == SYSTEMS_ENTRY_OVERRIDE_OPEN_LANES


def test_systems_management_task_order_uses_only_effective_source_enablement(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    paths = (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    )

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        source_states = service.list_campaign_source_states("linden-pass")
        assert source_states
        for index, state in enumerate(source_states):
            store.upsert_campaign_enabled_source(
                "linden-pass",
                library_slug=library_slug,
                source_id=state.source.source_id,
                is_enabled=index == 0,
                default_visibility=state.default_visibility,
            )

    for path in paths:
        parser = _SystemsManagementLaneParser()
        parser.feed(client.get(path).get_data(as_text=True))
        assert tuple(
            href.removeprefix("#") for href, _label in parser.task_links
        ) == SYSTEMS_SETUP_COMPLETE_TASK_ORDER
        assert parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES

    with app.app_context():
        source_states = service.list_campaign_source_states("linden-pass")
        for state in source_states:
            store.upsert_campaign_enabled_source(
                "linden-pass",
                library_slug=library_slug,
                source_id=state.source.source_id,
                is_enabled=False,
                default_visibility=state.default_visibility,
            )
        configured_but_disabled_states = service.list_campaign_source_states(
            "linden-pass"
        )
        assert all(
            state.is_configured and not state.is_enabled
            for state in configured_but_disabled_states
        )
        assert any(
            service.count_entries_for_source(
                "linden-pass",
                state.source.source_id,
            )
            > 0
            for state in configured_but_disabled_states
        )

    for path in paths:
        parser = _SystemsManagementLaneParser()
        parser.feed(client.get(path).get_data(as_text=True))
        assert tuple(
            href.removeprefix("#") for href, _label in parser.task_links
        ) == SYSTEMS_SETUP_NEEDED_TASK_ORDER
        assert parser.open_lanes == SYSTEMS_SOURCE_OPEN_LANES

    with app.app_context():
        source_states = service.list_campaign_source_states("linden-pass")
        zero_count_state = next(
            state
            for state in source_states
            if service.count_entries_for_source(
                "linden-pass",
                state.source.source_id,
            )
            == 0
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=zero_count_state.source.source_id,
            is_enabled=True,
            default_visibility=zero_count_state.default_visibility,
        )
        mixed_states = service.list_campaign_source_states("linden-pass")
        assert any(state.is_enabled for state in mixed_states)
        assert any(not state.is_enabled for state in mixed_states)

    for path in paths:
        parser = _SystemsManagementLaneParser()
        parser.feed(client.get(path).get_data(as_text=True))
        assert parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES


def test_systems_source_enablement_setup_truth_covers_empty_dnd_and_xianxia_defaults(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    paths = (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    )

    with app.app_context():
        service = app.extensions["systems_service"]
        dnd_states = service.list_campaign_source_states("linden-pass")
        assert dnd_states
        assert all(not state.is_configured for state in dnd_states)
        assert any(state.is_enabled for state in dnd_states)
        assert "UNKNOWN-SOURCE" not in {
            state.source.source_id for state in dnd_states
        }

    for path in paths:
        parser = _SystemsManagementLaneParser()
        parser.feed(client.get(path).get_data(as_text=True))
        assert parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES

    campaign_path = (
        app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    )
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = XIANXIA_SYSTEM_CODE
    payload["systems_library"] = XIANXIA_SYSTEM_CODE
    payload.pop("systems_sources", None)
    campaign_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    with app.app_context():
        app.extensions["repository_store"].refresh()
        xianxia_states = service.list_campaign_source_states("linden-pass")
        assert xianxia_states
        assert all(not state.is_configured for state in xianxia_states)
        assert all(not state.is_enabled for state in xianxia_states)
        assert {state.source.source_id for state in xianxia_states} == {
            "XIANXIA-HOMEBREW"
        }

    for path in paths:
        parser = _SystemsManagementLaneParser()
        parser.feed(client.get(path).get_data(as_text=True))
        assert parser.open_lanes == SYSTEMS_SOURCE_OPEN_LANES

    monkeypatch.setattr(service, "list_campaign_source_states", lambda _slug: [])
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        parser = _SystemsManagementLaneParser()
        parser.feed(response.get_data(as_text=True))
        assert parser.open_lanes == SYSTEMS_SOURCE_OPEN_LANES


@pytest.mark.parametrize(
    ("return_to", "expected_hidden_return"),
    (
        ("", None),
        ("dm-content-systems", "dm-content-systems"),
    ),
)
def test_source_validation_400_opens_only_via_explicit_rerender_flag_and_loses_invalid_values(
    app,
    client,
    sign_in,
    users,
    return_to,
    expected_hidden_return,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        phb_state = service.get_campaign_source_state("linden-pass", "PHB")
        assert phb_state is not None
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id="PHB",
            is_enabled=False,
            default_visibility=VISIBILITY_PLAYERS,
        )

    host_path = (
        "/campaigns/linden-pass/dm-content/systems"
        if return_to
        else "/campaigns/linden-pass/systems/control-panel"
    )
    ordinary_response = client.get(
        f"{host_path}?systems_source_enablement_validation_active=1"
    )
    ordinary_parser = _SystemsManagementLaneParser()
    ordinary_parser.feed(ordinary_response.get_data(as_text=True))
    assert ordinary_parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES

    form_data = _build_systems_source_form(app)
    form_data["source_PHB_enabled"] = "1"
    form_data["source_PHB_visibility"] = "public"
    if return_to:
        form_data["return_to"] = return_to
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "cannot be made public" in body
    parser = _SystemsManagementLaneParser()
    parser.feed(body)
    assert parser.open_lanes == SYSTEMS_SOURCE_OPEN_LANES
    assert parser.source_checkbox_checked["PHB"] is False
    assert parser.source_selected_visibility["PHB"] == VISIBILITY_PLAYERS
    if expected_hidden_return is None:
        assert parser.hidden_return_values == []
    else:
        assert parser.hidden_return_values
        assert set(parser.hidden_return_values) == {expected_hidden_return}

    with app.app_context():
        persisted = service.get_campaign_source_state("linden-pass", "PHB")
        assert persisted is not None
        assert persisted.is_enabled is False
        assert persisted.default_visibility == VISIBILITY_PLAYERS


@pytest.mark.parametrize(
    ("return_to", "expected_location"),
    (
        (
            "",
            "/campaigns/linden-pass/systems/control-panel",
        ),
        (
            "dm-content-systems",
            (
                "/campaigns/linden-pass/dm-content/systems"
                "#systems-source-enablement"
            ),
        ),
    ),
)
def test_source_success_and_no_change_prg_targets_preserve_state_derived_disclosure(
    app,
    client,
    sign_in,
    users,
    return_to,
    expected_location,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    changed_form = _build_systems_source_form(app)
    changed_form["source_XGE_visibility"] = VISIBILITY_DM
    if return_to:
        changed_form["return_to"] = return_to

    changed_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=changed_form,
        follow_redirects=False,
    )
    assert changed_response.status_code == 302
    assert changed_response.headers["Location"] == expected_location

    followed = client.get(changed_response.headers["Location"])
    parser = _SystemsManagementLaneParser()
    parser.feed(followed.get_data(as_text=True))
    assert parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES

    unchanged_form = _build_systems_source_form(app)
    if return_to:
        unchanged_form["return_to"] = return_to
    unchanged_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=unchanged_form,
        follow_redirects=False,
    )
    assert unchanged_response.status_code == 302
    assert unchanged_response.headers["Location"] == expected_location

    followed_unchanged = client.get(unchanged_response.headers["Location"])
    unchanged_parser = _SystemsManagementLaneParser()
    unchanged_parser.feed(followed_unchanged.get_data(as_text=True))
    assert unchanged_parser.open_lanes == SYSTEMS_ALWAYS_OPEN_LANES


@pytest.mark.parametrize(
    ("actor", "view_as", "is_allowed"),
    (
        (None, None, False),
        ("party", None, False),
        ("admin", "party", False),
        ("dm", None, True),
        ("admin", "dm", True),
        ("admin", None, True),
    ),
)
@pytest.mark.parametrize(
    "path",
    (
        "/campaigns/linden-pass/systems/control-panel",
        "/campaigns/linden-pass/dm-content/systems",
    ),
)
def test_systems_management_hosts_preserve_effective_actor_dom_privacy(
    app,
    client,
    sign_in,
    users,
    actor,
    view_as,
    is_allowed,
    path,
):
    private_key, _shared_key, _custom_key = (
        _seed_persisted_entry_override_matrix(app)
    )
    if actor is not None:
        sign_in(users[actor]["email"], users[actor]["password"])
        with client.session_transaction() as browser_session:
            if view_as is None:
                browser_session.pop(VIEW_AS_SESSION_KEY, None)
            else:
                browser_session[VIEW_AS_SESSION_KEY] = users[view_as]["id"]

    response = client.get(path, follow_redirects=False)
    body = response.get_data(as_text=True)
    private_markers = (
        'aria-label="Systems management tasks"',
        "Show or hide Source Enablement",
        'name="source_',
        " imported entries",
        "custom campaign entries",
        "recent shared-library run",
        'name="systems_import_archive"',
        'action="/campaigns/linden-pass/systems/control-panel/shared-core-permission"',
        '<option value="private">',
        private_key,
        "A-PRIVATE-OVERRIDE",
    )

    if not is_allowed:
        assert response.status_code in {302, 403, 404}
        for marker in private_markers:
            assert marker not in body
        return

    assert response.status_code == 200
    parser = _SystemsManagementLaneParser()
    parser.feed(body)
    assert parser.task_nav_count == 1
    assert parser.inventory == SYSTEMS_MANAGEMENT_LANES
    assert parser.open_lanes == SYSTEMS_ENTRY_OVERRIDE_AND_CUSTOM_ENTRY_OPEN_LANES
    assert private_key in body
    assert "Private Proprietary Override Source (A-PRIVATE-OVERRIDE)" in body
    assert "source_path" not in body
    assert "audit_state" not in body
    assert "storage_state" not in body
    if actor == "admin" and view_as is None:
        assert 'name="systems_import_archive"' in body
        assert (
            'action="/campaigns/linden-pass/systems/control-panel/'
            'shared-core-permission"'
        ) in body
        assert '<option value="private">' in body
    else:
        assert 'name="systems_import_archive"' not in body
        assert (
            'action="/campaigns/linden-pass/systems/control-panel/'
            'shared-core-permission"'
        ) not in body
        assert '<option value="private">' not in body


@pytest.mark.parametrize("return_to", ("", "dm-content-systems"))
def test_entry_override_post_view_as_player_is_denied_before_csrf_and_controller(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    return_to,
):
    entry_key = _seed_entry_override_entry(app)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    controller_calls = []

    def unexpected_override_update(*args, **kwargs):
        controller_calls.append((args, kwargs))
        raise AssertionError("override controller must not run")

    monkeypatch.setattr(
        app.extensions["systems_service"],
        "update_campaign_entry_override",
        unexpected_override_update,
    )
    data = {
        "entry_key": entry_key,
        "visibility_override": VISIBILITY_DM,
        "is_enabled_override": "disabled",
    }
    if return_to:
        data["return_to"] = return_to
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/overrides",
        data=data,
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert "Refresh the page and try again." not in response.get_data(as_text=True)
    assert controller_calls == []
    with app.app_context():
        assert app.extensions[
            "systems_store"
        ].get_campaign_entry_override("linden-pass", entry_key) is None


@pytest.mark.parametrize("return_to", ("", "dm-content-systems"))
def test_source_post_view_as_player_is_denied_before_csrf_and_controller(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    return_to,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    controller_calls = []

    def unexpected_source_update(*args, **kwargs):
        controller_calls.append((args, kwargs))
        raise AssertionError("source controller must not run")

    monkeypatch.setattr(
        app.extensions["systems_service"],
        "update_campaign_sources",
        unexpected_source_update,
    )
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data={"return_to": return_to} if return_to else {},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert "Refresh the page and try again." not in response.get_data(as_text=True)
    assert controller_calls == []


def test_dm_content_systems_page_separates_systems_lanes_and_returns_after_source_update(
    app, client, sign_in, users
):
    source_id = f"CSTM-{uuid4().hex[:8].upper()}"
    entry_key = f"dnd-5e|spell|{source_id.lower()}|harbor-spark"

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            source_id,
            title="Harbor Custom Systems",
            license_class="custom_campaign",
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="dm",
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": entry_key,
                    "entry_type": "spell",
                    "slug": "harbor-spark",
                    "title": "Harbor Spark",
                    "search_text": "harbor spark",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {},
                }
            ],
            entry_types=["spell"],
        )
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=entry_key,
            visibility_override="dm",
            is_enabled_override=False,
        )
        import_run = store.create_import_run(
            library_slug=library_slug,
            source_id="MM",
            import_version="browser-review",
            source_path=r"C:\private\source\mm.zip",
            summary={},
        )
        store.complete_import_run(
            import_run.id,
            summary={
                "imported_count": 42,
                "imported_by_type": {"monster": 42},
                "source_files": ["data/bestiary/bestiary-mm.json"],
            },
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    page = client.get("/campaigns/linden-pass/dm-content/systems")

    assert page.status_code == 200
    body = page.get_data(as_text=True)
    parser = _SystemsManagementLaneParser()
    parser.feed(body)
    assert parser.open_lanes == SYSTEMS_ENTRY_OVERRIDE_AND_CUSTOM_ENTRY_OPEN_LANES
    assert "Source Enablement" in body
    assert "Entry Overrides" in body
    assert "Custom Entries" in body
    assert "Import-Run History" in body
    assert "Harbor Custom Systems" in body
    assert "Harbor Spark" in body
    assert "MM import #" in body
    assert "42 entries" in body
    assert r"C:\private\source\mm.zip" not in body
    assert 'name="return_to" value="dm-content-systems"' in body

    form_data = _build_systems_source_form(app)
    form_data["return_to"] = "dm-content-systems"
    form_data[f"source_{source_id}_visibility"] = "players"
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == (
        "/campaigns/linden-pass/dm-content/systems"
        "#systems-source-enablement"
    )

    with app.app_context():
        state = app.extensions["systems_service"].get_campaign_source_state("linden-pass", source_id)
        assert state is not None
        assert state.default_visibility == "players"


def test_admin_can_import_dnd5e_systems_source_from_dm_content_systems(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_page = client.get("/campaigns/linden-pass/dm-content/systems")
    dm_body = dm_page.get_data(as_text=True)
    assert dm_page.status_code == 200
    assert "Shared Source Imports" in dm_body
    assert "Shared-source ZIP imports are limited to app admins" in dm_body
    assert 'name="systems_import_archive"' not in dm_body

    blocked_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={"source_ids": ["MM"]},
        follow_redirects=False,
    )
    assert blocked_response.status_code == 403

    sign_in(users["admin"]["email"], users["admin"]["password"])
    admin_page = client.get("/campaigns/linden-pass/dm-content/systems")
    admin_body = admin_page.get_data(as_text=True)
    assert admin_page.status_code == 200
    assert 'name="systems_import_archive"' in admin_body
    assert 'action="/campaigns/linden-pass/systems/control-panel/imports/dnd5e"' in admin_body
    assert "Import selected sources" in admin_body

    archive_bytes = _build_systems_import_archive()
    app.config["SYSTEMS_ARCHIVE_LIMITS"] = SystemsArchiveLimits(
        max_raw_bytes=len(archive_bytes)
    )
    import_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "return_to": "dm-content-systems",
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "import_version": "browser-mm-import",
            "systems_import_archive": (BytesIO(archive_bytes), "browser-mm-import.zip"),
        },
        follow_redirects=False,
    )

    assert import_response.status_code == 302
    assert "/campaigns/linden-pass/dm-content/systems" in import_response.headers["Location"]
    assert "#systems-import-history" in import_response.headers["Location"]

    with app.app_context():
        store = app.extensions["systems_store"]
        entries = store.list_entries_for_source("DND-5E", "MM", entry_type="monster", limit=None)
        assert any(entry.title == "Goblin" for entry in entries)
        import_run = store.list_import_runs(library_slug="DND-5E", source_id="MM", limit=1)[0]
        assert import_run.status == "completed"
        assert import_run.import_version == "browser-mm-import"
        assert import_run.source_path == "browser-upload:browser-mm-import.zip"
        assert import_run.started_by_user_id == users["admin"]["id"]
        assert import_run.summary["imported_count"] == 1
        assert import_run.summary["imported_by_type"] == {"monster": 1}
        assert import_run.summary["source_files"] == ["data/bestiary/bestiary-mm.json"]
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("import_run_ids") == [import_run.id] for event in events)

    review_page = client.get("/campaigns/linden-pass/dm-content/systems")
    review_body = review_page.get_data(as_text=True)
    assert review_page.status_code == 200
    review_parser = _SystemsManagementLaneParser()
    review_parser.feed(review_body)
    assert "systems-import-history" not in review_parser.open_lanes
    assert "MM import #" in review_body
    assert "browser-mm-import" in review_body
    assert "1 entries" in review_body
    assert "Monsters: 1" in review_body
    assert "data/bestiary/bestiary-mm.json" in review_body
    assert "browser-upload:browser-mm-import.zip" not in review_body


def test_browser_systems_import_rejects_actual_plus_one_when_length_hint_is_missing(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    archive_bytes = _build_systems_import_archive()
    app.config["SYSTEMS_ARCHIVE_LIMITS"] = SystemsArchiveLimits(
        max_raw_bytes=len(archive_bytes)
    )
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "return_to": "dm-content-systems",
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "systems_import_archive": (
                BytesIO(archive_bytes + b"x"),
                "oversized-browser-import.zip",
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "at or under 64 MiB" in response.get_data(as_text=True)
    assert "oversized-browser-import.zip" not in response.get_data(as_text=True)
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert events == []


def test_browser_systems_import_rejects_malformed_utf8_without_leak_mutation_or_residue(
    app,
    client,
    sign_in,
    users,
    tmp_path,
    monkeypatch,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    temp_root = tmp_path / "systems-temp"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "return_to": "dm-content-systems",
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "systems_import_archive": (
                BytesIO(_build_malformed_utf8_systems_import_archive()),
                "ATTACKER-SENTINEL.zip",
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    response_text = response.get_data(as_text=True)
    assert "Import archive must be a valid supported ZIP file." in response_text
    assert "ATTACKER-SENTINEL" not in response_text
    assert "codec" not in response_text
    assert "position 0" not in response_text
    assert "can't decode" not in response_text
    with app.app_context():
        store = app.extensions["systems_store"]
        assert store.list_import_runs(library_slug="DND-5E") == []
        assert store.list_entries_for_source("DND-5E", "MM", entry_type="monster", limit=None) == []
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert events == []
    assert not temp_root.exists() or list(temp_root.iterdir()) == []


@pytest.mark.parametrize("actor", ["outsider", "party", "dm"])
def test_browser_systems_import_keeps_campaign_admin_authority_contract(
    client,
    sign_in,
    users,
    actor,
):
    route = "/campaigns/linden-pass/systems/control-panel/imports/dnd5e"
    sign_in(users[actor]["email"], users[actor]["password"])
    denied = client.post(route, data={"source_ids": ["MM"]}, follow_redirects=False)
    assert denied.status_code == 403


def test_browser_systems_import_anonymous_redirects_to_sign_in(client):
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/sign-in" in response.headers["Location"]


def test_browser_systems_import_view_as_denial_precedes_csrf_and_controller(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]

    monkeypatch.setattr(
        systems_routes,
        "_dependencies",
        lambda: (_ for _ in ()).throw(AssertionError("controller must not execute")),
    )
    route = "/campaigns/linden-pass/systems/control-panel/imports/dnd5e"
    view_as_denied = client.post(route, data={"source_ids": ["MM"]})
    assert view_as_denied.status_code == 403

    with client.session_transaction() as browser_session:
        browser_session.pop(VIEW_AS_SESSION_KEY, None)
    csrf_denied = client.post(route, data={"source_ids": ["MM"]})
    assert csrf_denied.status_code == 400
    assert "Refresh the page and try again." in csrf_denied.get_data(as_text=True)


@pytest.mark.parametrize("return_to_dm_content", [False, True])
def test_browser_systems_import_validation_retains_scalar_and_list_form_fields(
    client,
    sign_in,
    users,
    return_to_dm_content,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    data = {
        "source_ids": [" mm ", "MM"],
        "entry_types": [" Monster ", "monster"],
        "import_version": " retained-browser-label ",
    }
    if return_to_dm_content:
        data["return_to"] = "dm-content-systems"

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data=data,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "Choose a ZIP archive to import." in body
    parser = _SystemsManagementLaneParser()
    parser.feed(body)
    assert parser.open_lanes == SYSTEMS_IMPORT_VALIDATION_OPEN_LANES
    assert 'name="import_version" value="retained-browser-label"' in body
    assert 'name="source_ids" value="MM" checked' in body
    assert 'name="entry_types" value="monster" checked' in body
    assert 'name="systems_import_archive"' in body
    assert 'name="systems_import_archive" value=' not in body
    assert 'value="retained-browser-label"' in body
    if return_to_dm_content:
        assert 'name="return_to" value="dm-content-systems"' in body
        assert "DM Content" in body
    else:
        assert "Systems control panel" in body


def test_browser_systems_import_normalizes_lists_and_defaults_version_from_basename(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    archive_bytes = _build_systems_import_archive()
    with app.app_context():
        combat_revision_before = app.extensions[
            "campaign_combat_service"
        ].get_live_revision("linden-pass")
        repository_store = app.extensions["repository_store"]
    monkeypatch.setattr(
        repository_store,
        "refresh",
        lambda: (_ for _ in ()).throw(AssertionError("repository refresh is not part of import")),
    )

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "source_ids": [" mm ", "MM"],
            "entry_types": [" Monster ", "monster"],
            "import_version": "",
            "systems_import_archive": (
                BytesIO(archive_bytes),
                "nested\\browser-mm-import.zip",
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/systems/control-panel#systems-import-history"
    )
    with app.app_context():
        run = app.extensions["systems_store"].list_import_runs(
            library_slug="DND-5E",
            source_id="MM",
            limit=1,
        )[0]
        assert run.import_version == "browser-mm-import"
        assert run.source_path == "browser-upload:browser-mm-import.zip"
        assert run.summary["entry_types"] == ["monster"]
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert len(events) == 1
        assert events[0].actor_user_id == users["admin"]["id"]
        assert events[0].metadata == {
            "library_slug": "DND-5E",
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "import_run_ids": [run.id],
            "archive_filename": "browser-mm-import.zip",
            "source": "campaign_systems_control_panel",
        }
        assert (
            app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
            == combat_revision_before
        )
    with client.session_transaction() as browser_session:
        assert (
            "success",
            "Imported DND-5E Systems sources: MM (1 entries).",
        ) in browser_session.get("_flashes", [])


def test_browser_systems_import_without_entry_types_uses_all_canonical_types(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "source_ids": ["MM"],
            "systems_import_archive": (
                BytesIO(_build_systems_import_archive()),
                "all-types.zip",
            ),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        run = app.extensions["systems_store"].list_import_runs(
            library_slug="DND-5E",
            source_id="MM",
            limit=1,
        )[0]
        assert run.summary["entry_types"] == list(SUPPORTED_ENTRY_TYPES)
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert events[0].metadata["entry_types"] == ["all"]


@pytest.mark.parametrize(
    ("source_ids", "entry_types", "message"),
    [
        ([], ["monster"], "Choose at least one DND-5E source to import."),
        (["RULES"], ["monster"], "Unsupported source IDs: RULES."),
        (["CUSTOM-LINDEN-PASS"], ["monster"], "Unsupported source IDs: CUSTOM-LINDEN-PASS."),
        (["NOPE"], ["monster"], "Unsupported source IDs: NOPE."),
        (["MM"], ["not-a-family"], "Unsupported entry types: not-a-family."),
    ],
)
def test_browser_systems_import_rejects_unsupported_sources_and_entry_types_before_upload(
    app,
    client,
    sign_in,
    users,
    source_ids,
    entry_types,
    message,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={"source_ids": source_ids, "entry_types": entry_types},
    )
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


@pytest.mark.parametrize(
    ("archive_bytes", "filename", "message"),
    [
        (None, None, "Choose a ZIP archive to import."),
        (b"not-a-zip", "source.txt", "must be uploaded as a .zip archive"),
        (b"", "empty.zip", "Choose a non-empty ZIP archive to import."),
        (
            _build_unsafe_systems_import_archive(),
            "unsafe.zip",
            "parent-relative",
        ),
    ],
)
def test_browser_systems_import_keeps_archive_validation_outcomes(
    app,
    client,
    sign_in,
    users,
    archive_bytes,
    filename,
    message,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    data = {"source_ids": ["MM"], "entry_types": ["monster"]}
    if archive_bytes is not None:
        data["systems_import_archive"] = (BytesIO(archive_bytes), filename)
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data=data,
    )
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert message in body
    parser = _SystemsManagementLaneParser()
    parser.feed(body)
    assert parser.open_lanes == SYSTEMS_IMPORT_VALIDATION_OPEN_LANES
    assert filename is None or filename not in body
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


def test_browser_systems_import_keeps_submitted_source_order_and_earlier_durable_results(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    calls: list[str] = []
    original_import_source = systems_routes.Dnd5eSystemsImporter.import_source

    def import_source_then_fail(self, source_id, **kwargs):
        calls.append(source_id)
        if source_id == "PHB":
            raise RuntimeError("later source unavailable")
        return original_import_source(self, source_id, **kwargs)

    monkeypatch.setattr(
        systems_routes.Dnd5eSystemsImporter,
        "import_source",
        import_source_then_fail,
    )
    sign_in(users["admin"]["email"], users["admin"]["password"])

    with pytest.raises(RuntimeError, match="later source unavailable"):
        client.post(
            "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
            data={
                "source_ids": [" mm ", "PHB", "MM"],
                "entry_types": ["monster"],
                "systems_import_archive": (
                    BytesIO(_build_systems_import_archive()),
                    "ordered-import.zip",
                ),
            },
        )

    assert calls == ["MM", "PHB"]
    with app.app_context():
        store = app.extensions["systems_store"]
        mm_runs = store.list_import_runs(library_slug="DND-5E", source_id="MM")
        phb_runs = store.list_import_runs(library_slug="DND-5E", source_id="PHB")
        assert len(mm_runs) == 1
        assert mm_runs[0].status == "completed"
        assert phb_runs == []
        assert any(
            entry.title == "Goblin"
            for entry in store.list_entries_for_source(
                "DND-5E",
                "MM",
                entry_type="monster",
                limit=None,
            )
        )
        assert AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        ) == []


def test_browser_systems_import_success_preserves_normalized_first_submitted_source_order(
    app,
    client,
    sign_in,
    users,
):
    archive_buffer = BytesIO(_build_systems_import_archive())
    with zipfile.ZipFile(archive_buffer, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data/bestiary/bestiary-phb.json", '{"monster": []}')

    sign_in(users["admin"]["email"], users["admin"]["password"])
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "source_ids": [" phb ", "MM", "PHB"],
            "entry_types": ["monster"],
            "systems_import_archive": (
                BytesIO(archive_buffer.getvalue()),
                "ordered-success.zip",
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        store = app.extensions["systems_store"]
        phb_run = store.list_import_runs(
            library_slug="DND-5E",
            source_id="PHB",
            limit=1,
        )[0]
        mm_run = store.list_import_runs(
            library_slug="DND-5E",
            source_id="MM",
            limit=1,
        )[0]
        assert phb_run.status == "completed"
        assert mm_run.status == "completed"
        assert phb_run.id < mm_run.id
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert len(events) == 1
        assert events[0].metadata["source_ids"] == ["PHB", "MM"]
        assert events[0].metadata["import_run_ids"] == [phb_run.id, mm_run.id]
    with client.session_transaction() as browser_session:
        assert (
            "success",
            "Imported DND-5E Systems sources: PHB (0 entries), MM (1 entries).",
        ) in browser_session.get("_flashes", [])


def test_browser_systems_import_rejects_xianxia_before_archive_or_import_run(
    app,
    client,
    sign_in,
    users,
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with app.app_context():
        app.extensions["repository_store"].refresh()

    sign_in(users["admin"]["email"], users["admin"]["password"])
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={"source_ids": ["MM"]},
    )

    assert response.status_code == 400
    assert "only available for DND-5E Systems libraries" in response.get_data(as_text=True)
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="xianxia") == []


def test_browser_systems_import_remains_in_the_ordinary_request_trail(
    app,
    client,
    sign_in,
    users,
    caplog,
):
    app.config["REQUEST_TRAIL_ENABLED"] = True
    caplog.set_level(logging.INFO, logger=app.logger.name)
    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={"source_ids": ["MM"]},
    )

    assert response.status_code == 400
    starts = [
        record.message
        for record in caplog.records
        if record.message.startswith("request_trail_start ")
        and '"endpoint": "campaign_systems_control_panel_import_dnd5e"' in record.message
    ]
    assert len(starts) == 1


@pytest.mark.parametrize(
    ("fault", "expected_run_status", "replacement_is_durable", "message"),
    [
        ("builtin_seed", None, False, "builtin seed unavailable"),
        ("create_run", None, False, "import run unavailable"),
        ("replace", "failed", False, "replacement unavailable"),
        ("complete_run", "failed", True, "completion unavailable"),
        ("fail_run", "started", False, "failed-run update unavailable"),
        ("audit", "completed", True, "audit unavailable"),
    ],
)
def test_browser_systems_import_preserves_fault_boundary_partial_failure_contracts(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    fault,
    expected_run_status,
    replacement_is_durable,
    message,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        auth_store = app.extensions["auth_store"]
        repository_store = app.extensions["repository_store"]
        original_ensure_builtin_library_seeded = service.ensure_builtin_library_seeded
        phb_before = [
            entry.entry_key
            for entry in store.list_entries_for_source("DND-5E", "PHB", limit=None)
        ]
        mm_policy_before = service.get_campaign_source_state("linden-pass", "MM")

    monkeypatch.setattr(
        repository_store,
        "refresh",
        lambda: (_ for _ in ()).throw(AssertionError("repository refresh is not part of import")),
    )

    def raise_fault(*_args, **_kwargs):
        raise RuntimeError(message)

    if fault == "builtin_seed":
        monkeypatch.setattr(service, "ensure_builtin_library_seeded", raise_fault)
    elif fault == "create_run":
        monkeypatch.setattr(store, "create_import_run", raise_fault)
    elif fault == "replace":
        monkeypatch.setattr(store, "replace_entries_for_source", raise_fault)
    elif fault == "complete_run":
        monkeypatch.setattr(store, "complete_import_run", raise_fault)
    elif fault == "fail_run":
        monkeypatch.setattr(
            store,
            "replace_entries_for_source",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("replacement unavailable")
            ),
        )
        monkeypatch.setattr(store, "fail_import_run", raise_fault)
    elif fault == "audit":
        monkeypatch.setattr(auth_store, "write_audit_event", raise_fault)
    else:  # pragma: no cover - the parameter table is exhaustive
        raise AssertionError(f"Unknown fault boundary: {fault}")

    with pytest.raises(RuntimeError, match=message):
        client.post(
            "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
            data={
                "source_ids": ["MM"],
                "entry_types": ["monster"],
                "systems_import_archive": (
                    BytesIO(_build_systems_import_archive()),
                    "fault-boundary.zip",
                ),
            },
        )
    if fault == "builtin_seed":
        monkeypatch.setattr(
            service,
            "ensure_builtin_library_seeded",
            original_ensure_builtin_library_seeded,
        )

    with app.app_context():
        runs = store.list_import_runs(library_slug="DND-5E", source_id="MM")
        if expected_run_status is None:
            assert runs == []
        else:
            assert len(runs) == 1
            assert runs[0].status == expected_run_status

        mm_entries = store.list_entries_for_source(
            "DND-5E",
            "MM",
            entry_type="monster",
            limit=None,
        )
        assert any(entry.title == "Goblin" for entry in mm_entries) is replacement_is_durable
        assert [
            entry.entry_key
            for entry in store.list_entries_for_source("DND-5E", "PHB", limit=None)
        ] == phb_before
        mm_policy_after = service.get_campaign_source_state("linden-pass", "MM")
        assert mm_policy_after.is_enabled == mm_policy_before.is_enabled
        assert mm_policy_after.default_visibility == mm_policy_before.default_visibility
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert events == []


def test_dm_content_systems_page_can_create_edit_archive_and_restore_custom_entries(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "Harbor Spark",
            "custom_entry_slug": "harbor-spark",
            "custom_entry_type": "spell",
            "custom_entry_visibility": "players",
            "custom_entry_provenance": "Linden Pass table notes",
            "custom_entry_search_metadata": "storm dock signal",
            "custom_entry_body_markdown": "## Effect\nLightning gathers around the harbor bells.",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert "/campaigns/linden-pass/dm-content/systems" in create_response.headers["Location"]
    assert "#systems-custom-entry-custom-linden-pass-harbor-spark" in create_response.headers["Location"]

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", "custom-linden-pass-harbor-spark")
        assert entry is not None
        assert entry.title == "Harbor Spark"
        assert entry.entry_type == "spell"
        assert entry.source_id == "CUSTOM-LINDEN-PASS"
        assert entry.source_path == "Linden Pass table notes"
        assert "storm dock signal" in entry.search_text
        assert "<h2>Effect</h2>" in entry.rendered_html
        source_state = service.get_campaign_source_state("linden-pass", "CUSTOM-LINDEN-PASS")
        assert source_state is not None
        assert source_state.default_visibility == VISIBILITY_PLAYERS
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == "players"
        assert override.is_enabled_override is None
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is True

    detail_response = client.get("/campaigns/linden-pass/systems/entries/custom-linden-pass-harbor-spark")
    detail_body = detail_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert "Harbor Spark" in detail_body
    assert "Lightning gathers around the harbor bells." in detail_body

    edit_response = client.get(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/custom-linden-pass-harbor-spark/edit"
        "?return_to=dm-content-systems"
    )
    edit_body = edit_response.get_data(as_text=True)
    assert edit_response.status_code == 200
    assert 'value="Harbor Spark"' in edit_body
    assert 'name="return_to" value="dm-content-systems"' in edit_body

    update_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/custom-linden-pass-harbor-spark",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "Harbor Spark Revised",
            "custom_entry_type": "rule",
            "custom_entry_visibility": "dm",
            "custom_entry_provenance": "Revised table notes",
            "custom_entry_search_metadata": "updated signal",
            "custom_entry_body_markdown": "Updated custom body.",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", "custom-linden-pass-harbor-spark")
        assert entry is not None
        assert entry.title == "Harbor Spark Revised"
        assert entry.entry_type == "rule"
        assert entry.source_path == "Revised table notes"
        assert "updated signal" in entry.search_text
        assert "Updated custom body." in entry.rendered_html
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == "dm"
        original_entry_id = entry.id
        original_entry_key = entry.entry_key

    archive_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/custom-linden-pass-harbor-spark/archive",
        data={"return_to": "dm-content-systems"},
        follow_redirects=False,
    )

    assert archive_response.status_code == 302
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", "custom-linden-pass-harbor-spark")
        assert entry is not None
        assert entry.id == original_entry_id
        assert entry.entry_key == original_entry_key
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == "dm"
        assert override.is_enabled_override is False
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is False

    restore_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/custom-linden-pass-harbor-spark/restore",
        data={"return_to": "dm-content-systems"},
        follow_redirects=False,
    )

    assert restore_response.status_code == 302
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", "custom-linden-pass-harbor-spark")
        assert entry is not None
        assert entry.id == original_entry_id
        assert entry.entry_key == original_entry_key
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == "dm"
        assert override.is_enabled_override is None
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is True


def test_custom_entry_validation_rerenders_dm_content_with_submitted_form_values(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "",
            "custom_entry_slug": "",
            "custom_entry_type": "spell",
            "custom_entry_visibility": VISIBILITY_DM,
            "custom_entry_provenance": "Retained table provenance",
            "custom_entry_search_metadata": "retained search terms",
            "custom_entry_body_markdown": "Retained invalid custom body.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Choose a URL slug or title before saving a custom Systems entry." in body
    assert 'name="return_to" value="dm-content-systems"' in body
    assert '<option value="spell" selected' in body
    assert '<option value="dm" selected' in body
    assert "Retained table provenance" in body
    assert "retained search terms" in body
    assert "Retained invalid custom body." in body

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        source = store.get_source(library_slug, "CUSTOM-LINDEN-PASS")
        policy = store.get_campaign_policy("linden-pass")
        enabled_source = store.get_campaign_enabled_source(
            "linden-pass",
            "CUSTOM-LINDEN-PASS",
        )
        assert source is not None
        assert policy is not None and policy.updated_by_user_id == users["dm"]["id"]
        assert enabled_source is not None
        assert enabled_source.updated_by_user_id == users["dm"]["id"]
        assert service.get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-retained-invalid-custom-body",
        ) is None
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_custom_entry_created",
            campaign_slug="linden-pass",
        )


def test_xianxia_empty_custom_entry_create_rerenders_default_form_values(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with app.app_context():
        app.extensions["repository_store"].refresh()
        app.extensions["systems_service"].ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Choose a URL slug or title before saving a custom Systems entry." in body
    assert '<option value="rule" selected' in body
    custom_visibility_index = body.index('select name="custom_entry_visibility"')
    custom_visibility_block = body[custom_visibility_index: custom_visibility_index + 500]
    assert '<option value="dm" selected' in custom_visibility_block
    assert '<option value="players" selected' not in custom_visibility_block


def test_empty_custom_entry_update_rerenders_existing_fields_and_fixed_slug(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Existing Spark",
            "custom_entry_slug": "existing-spark",
            "custom_entry_type": "spell",
            "custom_entry_visibility": VISIBILITY_DM,
            "custom_entry_provenance": "Existing provenance",
            "custom_entry_search_metadata": "existing search metadata",
            "custom_entry_body_markdown": "Existing body markdown.",
        },
    )
    assert create_response.status_code == 302

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/"
        "custom-linden-pass-existing-spark",
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Custom Systems entries need a title." in body
    assert 'value="Existing Spark"' in body
    assert 'value="custom-linden-pass-existing-spark" disabled' in body
    assert 'name="custom_entry_slug"' not in body
    assert '<option value="spell" selected' in body
    custom_visibility_index = body.index('select name="custom_entry_visibility"')
    custom_visibility_block = body[custom_visibility_index: custom_visibility_index + 500]
    assert '<option value="dm" selected' in custom_visibility_block
    assert "Existing provenance" in body
    assert "existing search metadata" in body
    assert "Existing body markdown." in body

    with app.app_context():
        entry = app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-existing-spark",
        )
        assert entry is not None
        assert entry.title == "Existing Spark"
        assert entry.entry_type == "spell"


@pytest.mark.parametrize("visibility_field", [{}, {"custom_entry_visibility": "outsiders"}])
def test_custom_entry_direct_missing_or_invalid_visibility_falls_back_to_players(
    app, client, sign_in, users, visibility_field
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    slug_leaf = f"visibility-{uuid4().hex[:8]}"
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Visibility Fallback",
            "custom_entry_slug": slug_leaf,
            "custom_entry_type": "rule",
            "custom_entry_body_markdown": "Visibility fallback body.",
            **visibility_field,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug(
            "linden-pass",
            f"custom-linden-pass-{slug_leaf}",
        )
        assert entry is not None
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == VISIBILITY_PLAYERS


@pytest.mark.parametrize("entry_type_field", [{}, {"custom_entry_type": "!!!"}])
def test_custom_entry_direct_missing_or_invalid_entry_type_rerenders_400(
    app, client, sign_in, users, entry_type_field
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    slug_leaf = f"invalid-type-{uuid4().hex[:8]}"
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Invalid Type",
            "custom_entry_slug": slug_leaf,
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": "Invalid type body.",
            **entry_type_field,
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Choose an entry type before saving this custom Systems entry." in response.get_data(
        as_text=True
    )
    with app.app_context():
        assert app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
            "linden-pass",
            f"custom-linden-pass-{slug_leaf}",
        ) is None


def test_custom_entry_markdown_is_sanitized_once_at_the_service_boundary(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Sanitized Spark",
            "custom_entry_slug": "sanitized-spark",
            "custom_entry_type": "rule",
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": (
                "## Safe heading\n\n"
                "<script>alert(1)</script>\n\n"
                "Inline `<b>literal</b>`.\n\n"
                "[unsafe](javascript:alert(2))"
            ),
        },
    )

    assert response.status_code == 302
    with app.app_context():
        entry = app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-sanitized-spark",
        )
        assert entry is not None
        stored_markdown = entry.body["markdown"]
        assert stored_markdown == entry.metadata["body_markdown"]
        assert "## Safe heading" in stored_markdown
        assert "`<b>literal</b>`" in stored_markdown
        assert "<script" not in stored_markdown.casefold()
        assert "<h2>Safe heading</h2>" in entry.rendered_html
        assert "&lt;b&gt;literal&lt;/b&gt;" in entry.rendered_html
        assert "<script" not in entry.rendered_html.casefold()
        assert "javascript:" not in entry.rendered_html.casefold()


def test_custom_entry_control_panel_surface_preserves_edit_and_prg_anchors(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Control Spark",
            "custom_entry_slug": "control-spark",
            "custom_entry_type": "rule",
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": "Control surface body.",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/systems/control-panel"
        "#systems-custom-entry-custom-linden-pass-control-spark"
    )

    edit_response = client.get(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/"
        "custom-linden-pass-control-spark/edit"
    )
    assert edit_response.status_code == 200
    edit_body = edit_response.get_data(as_text=True)
    assert "Systems Settings" in edit_body
    assert 'value="Control Spark"' in edit_body
    assert 'name="return_to" value="dm-content-systems"' not in edit_body

    update_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/"
        "custom-linden-pass-control-spark",
        data={
            "custom_entry_title": "Control Spark Updated",
            "custom_entry_type": "rule",
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": "Updated control surface body.",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302
    assert update_response.headers["Location"].endswith(
        "/campaigns/linden-pass/systems/control-panel"
        "#systems-custom-entry-custom-linden-pass-control-spark"
    )


def test_missing_custom_entry_edit_update_archive_and_restore_keep_legacy_failures(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    base_path = "/campaigns/linden-pass/systems/control-panel/custom-entries/missing-entry"
    assert client.get(f"{base_path}/edit").status_code == 404
    assert client.post(base_path).status_code == 404
    for action in ("archive", "restore"):
        response = client.post(
            f"{base_path}/{action}",
            data={"return_to": "dm-content-systems"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/campaigns/linden-pass/dm-content/systems" in response.headers["Location"]
        assert "#systems-custom-entries" in response.headers["Location"]


@pytest.mark.parametrize("operation", ["create", "update", "archive", "restore"])
def test_custom_entry_mutation_remains_durable_when_post_commit_audit_fails(
    app, client, sign_in, users, monkeypatch, operation
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    entry_slug = "custom-linden-pass-fault-seed"
    base_form = {
        "return_to": "dm-content-systems",
        "custom_entry_title": "Fault Seed",
        "custom_entry_slug": "fault-seed",
        "custom_entry_type": "rule",
        "custom_entry_visibility": VISIBILITY_PLAYERS,
        "custom_entry_provenance": "Fault characterization",
        "custom_entry_search_metadata": "fault seed",
        "custom_entry_body_markdown": "Fault seed body.",
    }

    if operation != "create":
        seed_response = client.post(
            "/campaigns/linden-pass/systems/control-panel/custom-entries",
            data=base_form,
        )
        assert seed_response.status_code == 302
    if operation == "restore":
        archive_response = client.post(
            f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}/archive",
        )
        assert archive_response.status_code == 302

    def fail_audit(**_kwargs):
        raise RuntimeError("custom entry audit unavailable")

    monkeypatch.setattr(app.extensions["auth_store"], "write_audit_event", fail_audit)
    if operation == "create":
        path = "/campaigns/linden-pass/systems/control-panel/custom-entries"
        data = base_form
    elif operation == "update":
        path = f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}"
        data = {
            **base_form,
            "custom_entry_title": "Fault Seed Updated",
            "custom_entry_body_markdown": "Updated before audit failure.",
        }
    else:
        path = (
            f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}/"
            f"{operation}"
        )
        data = {"return_to": "dm-content-systems"}

    with pytest.raises(RuntimeError, match="custom entry audit unavailable"):
        client.post(path, data=data)

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", entry_slug)
        assert entry is not None
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        if operation == "update":
            assert entry.title == "Fault Seed Updated"
            assert "Updated before audit failure." in entry.rendered_html
        elif operation == "archive":
            assert override.is_enabled_override is False
        elif operation == "restore":
            assert override.is_enabled_override is None


def test_xianxia_dm_content_systems_page_can_create_custom_martial_art_entries(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        app.extensions["systems_service"].ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    management_page = client.get("/campaigns/linden-pass/dm-content/systems")
    management_body = management_page.get_data(as_text=True)

    assert management_page.status_code == 200
    assert '<option value="martial_art"' in management_body
    assert "Martial Arts" in management_body
    custom_visibility_index = management_body.index('select name="custom_entry_visibility"')
    custom_visibility_block = management_body[custom_visibility_index: custom_visibility_index + 500]
    assert '<option value="dm" selected' in custom_visibility_block
    assert '<option value="players" selected' not in custom_visibility_block

    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "Jade Meteor Palm",
            "custom_entry_slug": "jade-meteor-palm",
            "custom_entry_type": "martial_art",
            "custom_entry_visibility": VISIBILITY_DM,
            "custom_entry_provenance": "GM table custom art",
            "custom_entry_search_metadata": "starter option jade meteor",
            "custom_entry_body_markdown": (
                "## Ranks\n"
                "Initiate: Jade energy gathers in the palm.\n\n"
                "Novice: The strike falls like a meteor."
            ),
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert "/campaigns/linden-pass/dm-content/systems" in create_response.headers["Location"]
    assert "#systems-custom-entry-custom-linden-pass-jade-meteor-palm" in create_response.headers["Location"]

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-jade-meteor-palm",
        )
        assert entry is not None
        assert entry.entry_type == "martial_art"
        assert entry.source_id == "CUSTOM-LINDEN-PASS"
        assert entry.metadata["xianxia_entry_facets"] == ["martial_art"]
        assert entry.metadata["xianxia_entry_facet_labels"] == ["Martial Art"]
        assert entry.metadata["catalog_role"] == "parent"
        assert entry.metadata["xianxia_custom_martial_art"] is True
        assert entry.metadata["rank_records_status"] == "gm_authored_custom_markdown"
        assert entry.body["xianxia_martial_art"]["catalog_role"] == "parent"
        assert entry.body["xianxia_martial_art"]["rank_records"] == []
        assert entry.body["xianxia_martial_art"]["parent_note"].startswith(
            "GM-created custom Martial Art"
        )
        source_state = service.get_campaign_source_state("linden-pass", "CUSTOM-LINDEN-PASS")
        assert source_state is not None
        assert source_state.default_visibility == VISIBILITY_DM
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == VISIBILITY_DM
        assert override.is_enabled_override is None
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is True

    category_response = client.get(
        "/campaigns/linden-pass/systems/sources/CUSTOM-LINDEN-PASS/types/martial_art"
    )
    category_body = category_response.get_data(as_text=True)
    assert category_response.status_code == 200
    assert "Echoes of the Alloy Coast Custom Systems: Martial Arts" in category_body
    assert "Jade Meteor Palm" in category_body
    assert "Showing all 1 martial arts in this source." in category_body

    search_response = client.get("/campaigns/linden-pass/systems?q=meteor")
    search_body = search_response.get_data(as_text=True)
    assert search_response.status_code == 200
    assert "Jade Meteor Palm" in search_body
    assert "CUSTOM-LINDEN-PASS" in search_body

    detail_response = client.get(
        "/campaigns/linden-pass/systems/entries/custom-linden-pass-jade-meteor-palm"
    )
    detail_body = detail_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert "Jade Meteor Palm" in detail_body
    assert "Campaign-owned custom entry." in detail_body
    assert "Jade energy gathers in the palm." in detail_body


def test_dm_can_upload_statblock_and_use_it_to_seed_an_npc_combatant(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "imperial-signal-operative-statblock.md")},
        follow_redirects=True,
    )

    assert upload.status_code == 200
    upload_html = upload.get_data(as_text=True)
    assert "Statblock saved to DM Content." in upload_html
    assert "Imperial Signal Operative" in upload_html
    statblocks = _list_statblocks(app)
    assert len(statblocks) == 1
    assert statblocks[0].title == "Imperial Signal Operative"
    assert statblocks[0].max_hp == 55
    assert statblocks[0].movement_total == 40
    assert statblocks[0].initiative_bonus == 2

    combat_page = client.get("/campaigns/linden-pass/combat/dm?view=controls")
    combat_html = combat_page.get_data(as_text=True)
    assert combat_page.status_code == 200
    assert "Add NPC from DM Content" in combat_html
    assert "Imperial Signal Operative" in combat_html

    add_to_combat = client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": str(statblocks[0].id)},
        follow_redirects=False,
    )
    assert add_to_combat.status_code == 302

    combatant = _find_combatant(app, name="Imperial Signal Operative")
    assert combatant is not None
    assert combatant.max_hp == 55
    assert combatant.current_hp == 55
    assert combatant.movement_total == 40
    assert combatant.initiative_bonus == 2
    assert combatant.dexterity_modifier == 2
    assert combatant.turn_value == 2


def test_dm_statblocks_page_groups_subsectioned_entries_like_wiki_sections(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    grouped_upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={
            "subsection": "Malverine Minions",
            "statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "imperial-signal-operative-statblock.md"),
        },
        follow_redirects=True,
    )

    assert grouped_upload.status_code == 200
    grouped_html = grouped_upload.get_data(as_text=True)
    assert "Malverine Minions" in grouped_html
    assert "1 statblock" in grouped_html
    assert 'data-subsection-controls' in grouped_html

    ungrouped_upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={
            "statblock_file": (BytesIO(TEST_UNGROUPED_STATBLOCK_MARKDOWN), "dock-runner-statblock.md"),
        },
        follow_redirects=True,
    )

    assert ungrouped_upload.status_code == 200

    statblocks = _list_statblocks(app)
    statblock_subsections = {statblock.title: statblock.subsection for statblock in statblocks}
    assert statblock_subsections == {
        "Dock Runner": "",
        "Imperial Signal Operative": "Malverine Minions",
    }

    dm_page = client.get("/campaigns/linden-pass/dm-content")

    assert dm_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    assert "Dock Runner" in dm_html
    assert "Imperial Signal Operative" in dm_html
    assert "Malverine Minions" in dm_html
    assert "1 statblock" in dm_html


def test_dm_can_update_statblock_source_and_combat_parser_fields(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "imperial-signal-operative-statblock.md")},
        follow_redirects=True,
    )
    assert upload.status_code == 200

    statblock = _list_statblocks(app)[0]
    update = client.post(
        f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}",
        data={
            "subsection": "Signal Officers",
            "body_markdown": UPDATED_STATBLOCK_MARKDOWN,
        },
        follow_redirects=True,
    )

    assert update.status_code == 200
    update_html = update.get_data(as_text=True)
    assert "Statblock Imperial Signal Lieutenant updated." in update_html
    assert "Parsed combat fields: AC 16, HP 64, Speed 30 ft., fly 45 ft. (45 ft. movement), Init +3." in update_html
    assert "Signal Officers" in update_html
    assert 'name="body_markdown"' in update_html
    assert "Hit Points 64" in update_html

    statblocks = _list_statblocks(app)
    assert len(statblocks) == 1
    updated_statblock = statblocks[0]
    assert updated_statblock.title == "Imperial Signal Lieutenant"
    assert updated_statblock.subsection == "Signal Officers"
    assert updated_statblock.max_hp == 64
    assert updated_statblock.movement_total == 45
    assert updated_statblock.initiative_bonus == 3

    add_to_combat = client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": str(updated_statblock.id)},
        follow_redirects=False,
    )
    assert add_to_combat.status_code == 302

    combatant = _find_combatant(app, name="Imperial Signal Lieutenant")
    assert combatant is not None
    assert combatant.max_hp == 64
    assert combatant.current_hp == 64
    assert combatant.movement_total == 45
    assert combatant.initiative_bonus == 3
    assert combatant.dexterity_modifier == 3
    assert combatant.turn_value == 3


def test_dm_statblock_update_keeps_submitted_body_visible_after_parser_error(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "imperial-signal-operative-statblock.md")},
        follow_redirects=True,
    )
    assert upload.status_code == 200

    statblock = _list_statblocks(app)[0]
    update = client.post(
        f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}",
        data={
            "subsection": "Broken Drafts",
            "body_markdown": "# Broken Draft\n\nArmor Class 12\nSpeed 30 ft.\n",
        },
        follow_redirects=False,
    )

    assert update.status_code == 400
    update_html = update.get_data(as_text=True)
    assert "The uploaded statblock needs a Hit Points value." in update_html
    assert "Broken Drafts" in update_html
    assert "Broken Draft" in update_html

    unchanged = _list_statblocks(app)[0]
    assert unchanged.title == "Imperial Signal Operative"
    assert unchanged.max_hp == 55


def test_dm_statblock_update_remains_durable_when_post_commit_audit_fails(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "operative.md")},
    )
    statblock = _list_statblocks(app)[0]

    def fail_audit(**_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(app.extensions["auth_store"], "write_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.post(
            f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}",
            data={"subsection": "Signal Officers", "body_markdown": UPDATED_STATBLOCK_MARKDOWN},
        )

    updated = _list_statblocks(app)[0]
    assert updated.title == "Imperial Signal Lieutenant"
    assert updated.subsection == "Signal Officers"
    assert updated.max_hp == 64


def test_init_db_backfills_existing_linden_pass_statblocks_into_malverine_minions_group(
    tmp_path, monkeypatch
):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)

    db_path = tmp_path / "legacy-player-wiki.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE campaign_dm_statblocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_slug TEXT NOT NULL,
            title TEXT NOT NULL,
            body_markdown TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            armor_class INTEGER,
            max_hp INTEGER NOT NULL DEFAULT 0,
            speed_text TEXT NOT NULL DEFAULT '',
            movement_total INTEGER NOT NULL DEFAULT 0,
            initiative_bonus INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by_user_id INTEGER,
            updated_by_user_id INTEGER
        );

        INSERT INTO campaign_dm_statblocks (
            campaign_slug,
            title,
            body_markdown,
            source_filename,
            armor_class,
            max_hp,
            speed_text,
            movement_total,
            initiative_bonus,
            created_at,
            updated_at
        )
        VALUES
            (
                'linden-pass',
                'Eyestitched Watcher',
                'Armor Class 14\nHit Points 27\nSpeed 30 ft.',
                'Eyestitched Watcher - Powered-Up Statblock.md',
                14,
                27,
                '30 ft.',
                30,
                2,
                '2026-04-22T12:00:00Z',
                '2026-04-22T12:00:00Z'
            ),
            (
                'linden-pass',
                'Dock Runner',
                'Armor Class 13\nHit Points 22\nSpeed 30 ft.',
                'dock-runner-statblock.md',
                13,
                22,
                '30 ft.',
                30,
                2,
                '2026-04-22T12:00:00Z',
                '2026-04-22T12:00:00Z'
            );
        """
    )
    connection.commit()
    connection.close()

    app = create_app()
    app.config.update(TESTING=True, DB_PATH=db_path)

    with app.app_context():
        init_database()

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT title, subsection
        FROM campaign_dm_statblocks
        ORDER BY id ASC
        """
    ).fetchall()
    connection.close()

    assert [dict(row) for row in rows] == [
        {"title": "Eyestitched Watcher", "subsection": "Malverine Minions"},
        {"title": "Dock Runner", "subsection": ""},
    ]


def test_custom_conditions_flow_from_dm_content_into_combat_picker_and_can_be_deleted(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_condition = client.post(
        "/campaigns/linden-pass/dm-content/conditions",
        data={
            "name": "Marked for Judgment",
            "description_markdown": "The target has disadvantage on Deception checks against inquisitors.",
        },
        follow_redirects=True,
    )

    assert create_condition.status_code == 200
    create_html = create_condition.get_data(as_text=True)
    assert "Custom condition saved to DM Content." in create_html
    assert "Marked for Judgment" in create_html

    definitions = _list_condition_definitions(app)
    assert len(definitions) == 1
    assert definitions[0].name == "Marked for Judgment"

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Tide Witness",
            "turn_value": 10,
            "current_hp": 20,
            "max_hp": 20,
            "movement_total": 30,
        },
        follow_redirects=False,
    )
    combatant = _find_combatant(app, name="Tide Witness")
    assert combatant is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/conditions",
        data={"condition_name": "Marked for Judgment", "duration_text": "Until next dawn"},
        follow_redirects=False,
    )
    active_condition = _list_conditions(app, combatant.id)[0]
    with app.app_context():
        revision_after_active_condition = app.extensions[
            "campaign_combat_service"
        ].get_live_revision("linden-pass")

    update_condition = client.post(
        f"/campaigns/linden-pass/dm-content/conditions/{definitions[0].id}",
        data={
            "name": "Judged by the Tide",
            "description_markdown": "The target leaves glowing footprints until the next dawn.",
        },
        follow_redirects=True,
    )

    assert update_condition.status_code == 200
    update_html = update_condition.get_data(as_text=True)
    assert "Custom condition Judged by the Tide updated." in update_html
    assert "Judged by the Tide" in update_html
    assert "leaves glowing footprints" in update_html
    assert 'action="/campaigns/linden-pass/dm-content/conditions/' in update_html

    definitions = _list_condition_definitions(app)
    assert len(definitions) == 1
    assert definitions[0].name == "Judged by the Tide"
    assert definitions[0].description_markdown == "The target leaves glowing footprints until the next dawn."

    retained_after_rename = _list_conditions(app, combatant.id)
    assert len(retained_after_rename) == 1
    assert retained_after_rename[0].id == active_condition.id
    assert retained_after_rename[0].name == "Marked for Judgment"
    assert retained_after_rename[0].duration_text == "Until next dawn"
    with app.app_context():
        assert (
            app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
            == revision_after_active_condition
        )

    combat_page = client.get("/campaigns/linden-pass/combat/dm")
    combat_html = combat_page.get_data(as_text=True)
    assert '<option value="Judged by the Tide"></option>' in combat_html
    assert '<option value="Marked for Judgment"></option>' not in combat_html

    delete_condition = client.post(
        f"/campaigns/linden-pass/dm-content/conditions/{definitions[0].id}/delete",
        follow_redirects=True,
    )

    assert delete_condition.status_code == 200
    assert "Deleted custom condition Judged by the Tide." in delete_condition.get_data(as_text=True)
    assert _list_condition_definitions(app) == []

    retained_after_delete = _list_conditions(app, combatant.id)
    assert len(retained_after_delete) == 1
    assert retained_after_delete[0].id == active_condition.id
    assert retained_after_delete[0].name == "Marked for Judgment"
    assert retained_after_delete[0].duration_text == "Until next dawn"
    with app.app_context():
        assert (
            app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
            == revision_after_active_condition
        )

    refreshed_combat = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    )
    refreshed_combat_html = refreshed_combat.get_data(as_text=True)
    assert '<option value="Judged by the Tide"></option>' not in refreshed_combat_html
    assert '<option value="Marked for Judgment"></option>' not in refreshed_combat_html
    assert "Marked for Judgment" in refreshed_combat_html
    assert "Until next dawn" in refreshed_combat_html


def test_condition_update_remains_durable_when_post_commit_audit_fails(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/dm-content/conditions",
        data={"name": "Marked", "description_markdown": "Initial description."},
    )
    definition = _list_condition_definitions(app)[0]

    def fail_audit(**_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(app.extensions["auth_store"], "write_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.post(
            f"/campaigns/linden-pass/dm-content/conditions/{definition.id}",
            data={"name": "Renamed", "description_markdown": "Updated description."},
        )

    updated = _list_condition_definitions(app)[0]
    assert updated.name == "Renamed"
    assert updated.description_markdown == "Updated description."


def test_dm_content_create_and_delete_skip_audit_refresh_and_combat_revision(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        original_revision = app.extensions["campaign_combat_service"].get_live_revision(
            "linden-pass"
        )

    audit_calls = []
    monkeypatch.setattr(
        app.extensions["auth_store"],
        "write_audit_event",
        lambda **kwargs: audit_calls.append(kwargs),
    )

    def fail_refresh():
        raise AssertionError("DM Content SQLite mutations must not refresh the wiki repository")

    monkeypatch.setattr(app.extensions["repository_store"], "refresh", fail_refresh)

    statblock_create = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "operative.md")},
        follow_redirects=False,
    )
    condition_create = client.post(
        "/campaigns/linden-pass/dm-content/conditions",
        data={"name": "Marked", "description_markdown": "A future picker option."},
        follow_redirects=False,
    )
    statblock = _list_statblocks(app)[0]
    condition = _list_condition_definitions(app)[0]
    statblock_delete = client.post(
        f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}/delete",
        follow_redirects=False,
    )
    condition_delete = client.post(
        f"/campaigns/linden-pass/dm-content/conditions/{condition.id}/delete",
        follow_redirects=False,
    )

    assert [
        statblock_create.status_code,
        condition_create.status_code,
        statblock_delete.status_code,
        condition_delete.status_code,
    ] == [302, 302, 302, 302]
    assert audit_calls == []
    assert _list_statblocks(app) == []
    assert _list_condition_definitions(app) == []
    with app.app_context():
        assert (
            app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
            == original_revision
        )


def test_dm_can_stage_session_article_from_dm_content_and_manage_it_from_session_dm(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/dm-content/staged-articles",
        data={
            "article_mode": "manual",
            "title": "Harbormaster Letter",
            "body_markdown": "The seal is fresh and the paper smells faintly of brine.",
        },
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    create_html = create_article.get_data(as_text=True)
    assert "Staged article added to the session reveal queue." in create_html
    assert "Harbormaster Letter" in create_html
    assert "Open Session DM" in create_html

    articles = _list_session_articles(app)
    assert len(articles) == 1
    assert articles[0].title == "Harbormaster Letter"
    assert not articles[0].is_revealed

    update_article = client.post(
        f"/campaigns/linden-pass/dm-content/staged-articles/{articles[0].id}",
        data={
            "title": "Harbormaster Letter Revised",
            "body_markdown": "The seal is fresh, and the revised copy names the east pier.",
        },
        follow_redirects=True,
    )

    assert update_article.status_code == 200
    update_html = update_article.get_data(as_text=True)
    assert "Staged article updated." in update_html
    assert "Harbormaster Letter Revised" in update_html
    assert "revised copy names the east pier" in update_html
    assert "The seal is fresh and the paper smells faintly of brine." not in update_html

    articles = _list_session_articles(app)
    assert len(articles) == 1
    assert articles[0].title == "Harbormaster Letter Revised"
    assert articles[0].body_markdown == "The seal is fresh, and the revised copy names the east pier."

    session_dm_page = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
    session_dm_html = session_dm_page.get_data(as_text=True)
    assert session_dm_page.status_code == 200
    assert "Harbormaster Letter Revised" in session_dm_html
    assert "revised copy names the east pier" in session_dm_html
    assert "Begin a session before revealing this article." in session_dm_html

    delete_article = client.post(
        f"/campaigns/linden-pass/dm-content/staged-articles/{articles[0].id}/delete",
        follow_redirects=True,
    )

    assert delete_article.status_code == 200
    delete_html = delete_article.get_data(as_text=True)
    assert "Staged article deleted from the session reveal queue." in delete_html
    assert _list_session_articles(app) == []


def test_dm_can_stage_image_only_session_article_from_dm_content(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/dm-content/staged-articles",
        data={
            "article_mode": "manual",
            "title": "Harbor Signal Sketch",
            "body_markdown": "",
            "image_alt": "A sketch of signal flags over the harbor.",
            "image_caption": "The sketch was shown without added body text.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "harbor-signal.png"),
        },
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    create_html = create_article.get_data(as_text=True)
    assert "Staged article added to the session reveal queue." in create_html
    assert "Harbor Signal Sketch" in create_html
    assert "The sketch was shown without added body text." in create_html

    articles = _list_session_articles(app)
    assert len(articles) == 1
    assert articles[0].title == "Harbor Signal Sketch"
    assert articles[0].body_markdown == ""
    assert not articles[0].is_revealed

    with app.app_context():
        image = app.extensions["campaign_session_service"].get_article_image("linden-pass", articles[0].id)

    assert image is not None
    assert image.filename == "harbor-signal.png"
    assert image.alt_text == "A sketch of signal flags over the harbor."
    assert image.caption == "The sketch was shown without added body text."
