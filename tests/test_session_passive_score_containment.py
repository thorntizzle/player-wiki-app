from __future__ import annotations

import inspect
from types import SimpleNamespace

from player_wiki.character_builder import CharacterBuildError
from player_wiki import session_presenter


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
        definition=SimpleNamespace(
            system="xianxia",
            name="Excluded Cultivator",
        ),
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


def test_session_shell_only_builds_passive_rows_for_requested_dnd_dm_pane(
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
    assert ordinary.status_code == 200
    assert character.status_code == 200
    assert calls == []
    assert "DM Passive Scores" not in ordinary.get_data(as_text=True)

    dm_page = client.get("/campaigns/linden-pass/session/dm")
    assert dm_page.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == "linden-pass"


def test_xianxia_dm_session_skips_passive_projection_entirely(
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

    response = client.get("/campaigns/linden-pass/session/dm")

    assert response.status_code == 200
    assert "DM Passive Scores" not in response.get_data(as_text=True)
