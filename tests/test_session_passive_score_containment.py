from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from player_wiki import session_presenter
from player_wiki.character_builder import CharacterBuildError


def test_passive_score_rows_use_one_projection_per_dnd_record_and_current_state(
    app,
    monkeypatch,
):
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        records = app.extensions["character_repository"].list_visible_characters(
            "linden-pass"
        )

    xianxia_record = SimpleNamespace(
        definition=SimpleNamespace(system="xianxia", name="Excluded Cultivator"),
        state_record=SimpleNamespace(state={"xianxia": {"honor": 2}}),
    )
    projected_calls = []

    def project_character(*, campaign, definition, state, systems_service, campaign_page_records):
        projected_calls.append((definition.name, state))
        if definition.name == records[0].definition.name:
            raise CharacterBuildError("skip malformed character")
        offset = len(projected_calls)
        return {
            "definition": SimpleNamespace(
                stats={
                    "passive_perception": 10 + offset,
                    "passive_insight": 8 + offset,
                    "passive_investigation": -4 if offset == 2 else 7 + offset,
                }
            ),
            "state": state,
        }

    monkeypatch.setattr(
        session_presenter,
        "build_character_mechanics_projection",
        project_character,
    )

    rows = session_presenter.present_session_dm_passive_score_rows(
        campaign,
        [*records, xianxia_record],
        systems_service=object(),
        campaign_page_records=[],
    )

    assert len(projected_calls) == len(records)
    assert [state for _, state in projected_calls] == [
        record.state_record.state for record in records
    ]
    assert [row["name"] for row in rows] == [
        record.definition.name for record in records[1:]
    ]
    assert rows[0]["passive_perception"] == "12"
    assert rows[0]["passive_insight"] == "10"
    assert rows[0]["passive_investigation"] == "0"
    assert "present_character_detail" not in inspect.getsource(
        session_presenter.present_session_dm_passive_score_rows
    )


@pytest.mark.parametrize("dm_view", ("staged", "revealed", "article-store", "logs"))
@pytest.mark.parametrize("is_fragment", (False, True))
def test_non_tools_session_dm_workflows_never_build_passive_scores(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    dm_view,
    is_fragment,
):
    import player_wiki.app as app_module

    monkeypatch.setattr(
        app_module,
        "present_session_dm_passive_score_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"{dm_view} must not project passive scores")
        ),
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/dm?dm_view={dm_view}",
        headers={"X-Requested-With": "XMLHttpRequest"} if is_fragment else None,
    )

    assert response.status_code == 200
    assert "DM Passive Scores" not in response.get_data(as_text=True)


def test_only_normalized_tools_outer_dm_builds_passives_and_other_session_reads_skip(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    import player_wiki.app as app_module

    calls = []

    def present_passives(campaign, records, *, systems_service, campaign_page_records):
        calls.append((campaign.slug, len(records), len(campaign_page_records)))
        return []

    monkeypatch.setattr(
        app_module,
        "present_session_dm_passive_score_rows",
        present_passives,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    ordinary = client.get("/campaigns/linden-pass/session")
    character = client.get("/campaigns/linden-pass/session/character?closed=1")
    live_state = client.get("/campaigns/linden-pass/session/live-state?view=dm")
    bare = client.get("/campaigns/linden-pass/session/dm")
    unknown = client.get("/campaigns/linden-pass/session/dm?dm_view=unknown")
    assert ordinary.status_code == 200
    assert character.status_code == 200
    assert live_state.status_code == 200
    assert bare.status_code == 302
    assert unknown.status_code == 302
    assert calls == []
    assert "DM Passive Scores" not in ordinary.get_data(as_text=True)

    tools = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")
    tools_fragment = client.get(
        "/campaigns/linden-pass/session/dm?dm_view=tools",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert tools.status_code == 200
    assert tools_fragment.status_code == 200
    assert len(calls) == 2
    assert all(call[0] == "linden-pass" for call in calls)


def test_session_dm_access_runs_before_passive_projection(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    import player_wiki.app as app_module

    monkeypatch.setattr(
        app_module,
        "present_session_dm_passive_score_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unauthorized caller reached passive projection")
        ),
    )
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")

    assert response.status_code == 403


def test_xianxia_tools_dm_session_skips_passive_projection_entirely(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    import player_wiki.app as app_module
    from tests.helpers.xianxia_character_helpers import _configure_xianxia_campaign

    _configure_xianxia_campaign(app)
    monkeypatch.setattr(
        app_module,
        "present_session_dm_passive_score_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Xianxia must not project DND passive scores")
        ),
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/session/dm?dm_view=tools")

    assert response.status_code == 200
    assert "DM Passive Scores" not in response.get_data(as_text=True)
