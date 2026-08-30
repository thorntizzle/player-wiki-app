from __future__ import annotations

import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import request

from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.auth_store import AuthStore, isoformat, utcnow
from player_wiki.campaign_session_store import CampaignSessionStore
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics
from player_wiki.manager_tools_routes import MANAGER_TOOLS_HTML_MAX_BYTES
from player_wiki.session_readiness_presenter import (
    READINESS_STATES,
    present_encounter_presets,
    present_session_characters,
    present_session_content,
    present_source_health,
)


READINESS_URL = "/campaigns/linden-pass/manager-tools/session-readiness"


def _sign_in(sign_in, users, actor: str) -> None:
    response = sign_in(users[actor]["email"], users[actor]["password"])
    assert response.status_code == 302


def _row(body: str, slug: str) -> str:
    marker = f'data-readiness-check="{slug}"'
    return body.split(marker, 1)[1].split("</article>", 1)[0]


def _states(body: str) -> list[str]:
    return re.findall(r'data-readiness-state="([a-z-]+)"', body)


def test_session_readiness_renders_exact_independent_rows_links_and_no_mutation_ui(
    client,
    sign_in,
    users,
) -> None:
    _sign_in(sign_in, users, "dm")

    response = client.get(READINESS_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert len(response.data) <= MANAGER_TOOLS_HTML_MAX_BYTES
    assert body.count('data-readiness-check="') == 5
    assert [
        re.search(r"<h2>([^<]+)</h2>", _row(body, slug)).group(1)
        for slug in (
            "active-session",
            "session-characters",
            "session-content",
            "source-health",
            "encounter-presets",
        )
    ] == [
        "Active Session",
        "Session Characters",
        "Session content",
        "Source Health",
        "Encounter Presets",
    ]
    assert set(state.replace("-", " ") for state in _states(body)) <= set(
        READINESS_STATES
    )
    assert 'data-readiness-state="not-configured"' in _row(
        body, "active-session"
    )
    character_row = _row(body, "session-characters")
    assert 'data-readiness-state="ready"' in character_row
    assert "Available Characters: 3. Valid assignments: 1." in character_row
    assert 'href="/campaigns/linden-pass/session/dm?dm_view=tools"' in body
    assert 'href="/campaigns/linden-pass/session/character"' in body
    assert 'href="/campaigns/linden-pass/session/dm?dm_view=staged"' in body
    assert 'href="/campaigns/linden-pass/source-health"' in body
    assert (
        'href="/campaigns/linden-pass/combat/dm?view=controls#saved-encounters"'
        in body
    )
    main = body.split("<main", 1)[1].split("</main>", 1)[0]
    assert "<form" not in main
    assert "<script" not in main
    assert "overall" not in main.lower()
    assert "complete session" not in main.lower()
    assert "acknowledge" not in main.lower()
    assert "Revision" not in main


def test_session_readiness_authorizes_effective_actor_before_owner_reads(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        app.extensions["campaign_session_service"],
        "get_readiness_summary",
        lambda *_args, **_kwargs: events.append("session"),
    )
    monkeypatch.setattr(
        app.extensions["character_repository"],
        "summarize_session_readiness_characters",
        lambda *_args, **_kwargs: events.append("characters"),
    )
    monkeypatch.setattr(
        AuthStore,
        "summarize_session_readiness_assignments",
        lambda *_args, **_kwargs: events.append("assignments"),
    )
    monkeypatch.setattr(
        app.extensions["source_health_service"],
        "build_report",
        lambda *_args, **_kwargs: events.append("source-health"),
    )
    monkeypatch.setattr(
        app.extensions["campaign_combat_preset_service"],
        "count_presets_up_to",
        lambda *_args, **_kwargs: events.append("presets"),
    )

    _sign_in(sign_in, users, "owner")
    assert client.get(READINESS_URL).status_code == 403
    assert events == []

    _sign_in(sign_in, users, "admin")
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users["owner"]["id"]
    assert client.get(READINESS_URL).status_code == 403
    assert events == []

    set_campaign_visibility("linden-pass", session="private")
    _sign_in(sign_in, users, "dm")
    assert client.get(READINESS_URL).status_code == 403
    assert events == []


def test_session_readiness_owner_failures_are_independent_and_sanitized(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
) -> None:
    secret = "private-owner-failure-detail"
    monkeypatch.setattr(
        app.extensions["campaign_session_service"],
        "get_readiness_summary",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(
        app.extensions["character_repository"],
        "summarize_session_readiness_characters",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(
        app.extensions["source_health_service"],
        "build_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(
        app.extensions["campaign_combat_preset_service"],
        "count_presets_up_to",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    _sign_in(sign_in, users, "dm")

    response = client.get(READINESS_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _states(body) == ["unavailable"] * 5
    assert secret not in body


def test_session_readiness_preserves_character_and_combat_owner_gates(
    client,
    sign_in,
    users,
    set_campaign_visibility,
) -> None:
    set_campaign_visibility(
        "linden-pass",
        characters="private",
        combat="private",
    )
    _sign_in(sign_in, users, "dm")

    response = client.get(READINESS_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-readiness-state="unavailable"' in _row(
        body,
        "session-characters",
    )
    assert 'data-readiness-state="unavailable"' in _row(
        body,
        "encounter-presets",
    )


@pytest.mark.parametrize(
    ("available", "valid", "dangling", "expected"),
    (
        (0, 0, False, "not configured"),
        (0, 0, True, "needs review"),
        (3, 0, False, "needs review"),
        (3, 1, False, "ready"),
        (3, 1, True, "needs review"),
        (3, 2, False, "ready"),
    ),
)
def test_character_state_precedence(
    available,
    valid,
    dangling,
    expected,
) -> None:
    row = present_session_characters(
        available_count=available,
        valid_assignment_count=valid,
        has_dangling_assignments=dangling,
        href="/characters",
    )
    assert row.state == expected


@pytest.mark.parametrize(
    ("staged", "revealed", "expected"),
    ((0, 0, "not configured"), (1, 0, "ready"), (26, 0, "ready"), (1, 1, "needs review")),
)
def test_session_content_state_precedence(staged, revealed, expected) -> None:
    row = present_session_content(
        staged_count=staged,
        revealed_count=revealed,
        href="/session-content",
    )
    assert row.state == expected


@pytest.mark.parametrize(
    ("report_state", "complete", "expected"),
    (
        ("healthy", True, "ready"),
        ("healthy", False, "needs review"),
        ("findings", True, "needs review"),
        ("partial", False, "needs review"),
        ("report_stale", False, "needs review"),
        ("empty", True, "not applicable"),
        ("error", False, "unavailable"),
    ),
)
def test_source_health_state_mapping(report_state, complete, expected) -> None:
    row = present_source_health(
        report_state=report_state,
        complete=complete,
        href="/source-health",
    )
    assert row.state == expected


def test_encounter_preset_state_mapping_and_capped_presentation() -> None:
    assert present_encounter_presets(count=0, supported=True, href="/").state == (
        "not configured"
    )
    assert present_encounter_presets(count=1, supported=True, href="/").state == "ready"
    capped = present_encounter_presets(count=26, supported=True, href="/")
    assert capped.state == "ready" and capped.detail == "Saved presets: 25+."
    assert present_encounter_presets(count=0, supported=False, href="/").state == (
        "not applicable"
    )


def test_character_summary_is_bounded_and_never_enters_state(
    app,
    monkeypatch,
) -> None:
    repository = app.extensions["character_repository"]
    monkeypatch.setattr(
        repository.state_store,
        "get_state",
        lambda *_args, **_kwargs: pytest.fail("readiness entered Character state"),
    )
    monkeypatch.setattr(
        repository.state_store,
        "initialize_state_if_missing",
        lambda *_args, **_kwargs: pytest.fail("readiness initialized Character state"),
    )

    summary = repository.summarize_session_readiness_characters(
        "linden-pass",
        limit=50,
        initialize_missing_state=False,
    )

    assert summary.available_character_slugs == (
        "arden-march",
        "selene-brook",
        "tobin-slate",
    )


def test_assignment_summary_requires_active_player_membership(app, users) -> None:
    with app.app_context():
        store = AuthStore()
        available = ("arden-march", "selene-brook", "tobin-slate")
        initial = store.summarize_session_readiness_assignments(
            "linden-pass",
            available_character_slugs=available,
        )
        store.upsert_membership(
            users["owner"]["id"],
            "linden-pass",
            role="player",
            status="removed",
        )
        removed_membership = store.summarize_session_readiness_assignments(
            "linden-pass",
            available_character_slugs=available,
        )

    assert initial.valid_assignment_count == 1
    assert initial.has_dangling_assignments is False
    assert removed_membership.valid_assignment_count == 0
    assert removed_membership.has_dangling_assignments is True


def test_character_definition_overflow_is_unavailable_without_partial_count(
    app,
    client,
    sign_in,
    users,
) -> None:
    characters_dir = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
    )
    for index in range(48):
        character_slug = f"overflow-{index:02d}"
        character_dir = characters_dir / character_slug
        character_dir.mkdir()
        (character_dir / "definition.yaml").write_text(
            f"campaign_slug: linden-pass\ncharacter_slug: {character_slug}\nstatus: active\n",
            encoding="utf-8",
        )

    _sign_in(sign_in, users, "dm")
    response = client.get(READINESS_URL)
    character_row = _row(response.get_data(as_text=True), "session-characters")

    assert response.status_code == 200
    assert 'data-readiness-state="unavailable"' in character_row
    assert "Available Characters:" not in character_row


def test_unsafe_character_definition_ownership_is_unavailable_and_sanitized(
    app,
    client,
    sign_in,
    users,
) -> None:
    characters_dir = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
    )
    unsafe_dir = characters_dir / "unsafe-character"
    unsafe_dir.mkdir()
    (unsafe_dir / "definition.yaml").write_text(
        "campaign_slug: other-campaign\ncharacter_slug: unsafe-character\nstatus: active\n",
        encoding="utf-8",
    )
    (unsafe_dir / "import.yaml").write_text("{}\n", encoding="utf-8")

    _sign_in(sign_in, users, "dm")
    response = client.get(READINESS_URL)
    character_row = _row(response.get_data(as_text=True), "session-characters")

    assert response.status_code == 200
    assert 'data-readiness-state="unavailable"' in character_row
    assert "other-campaign" not in character_row


def test_session_aggregate_is_one_body_free_query_and_caps_counts(app) -> None:
    with app.app_context():
        connection = get_db()
        now = isoformat(utcnow())
        connection.executemany(
            """
            INSERT INTO campaign_session_articles (
                campaign_slug, title, body_markdown, source_page_ref, status,
                created_at, created_by_user_id, revealed_at,
                revealed_by_user_id, revealed_in_session_id
            ) VALUES ('linden-pass', ?, ?, '', ?, ?, NULL, NULL, NULL, NULL)
            """,
            [
                (f"Article {index}", f"private body {index}", status, now)
                for status in ("staged", "revealed")
                for index in range(30)
            ],
        )
        connection.commit()
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        try:
            reset_db_query_metrics()
            summary = CampaignSessionStore().get_readiness_summary(
                "linden-pass",
                count_limit=26,
            )
            metrics = get_db_query_metrics()
        finally:
            connection.set_trace_callback(None)

    selects = [statement for statement in statements if "WITH staged AS" in statement]
    assert len(selects) == 1
    assert "body_markdown" not in selects[0]
    assert "data_blob" not in selects[0]
    assert summary.staged_count == 26
    assert summary.revealed_count == 26
    assert metrics["query_count"] == 1
    assert metrics["write_count"] == 0
    assert metrics["commit_count"] == 0
    assert metrics["rollback_count"] == 0


def test_readiness_get_stays_within_query_write_response_and_local_p95_bounds(
    app,
    client,
    sign_in,
    users,
) -> None:
    request_metrics: list[dict[str, float | int]] = []

    @app.after_request
    def capture_readiness_metrics(response):
        if request.endpoint == "campaign_session_readiness_view":
            request_metrics.append(get_db_query_metrics())
        return response

    _sign_in(sign_in, users, "dm")
    assert client.get("/campaigns/linden-pass/manager-tools").status_code == 200
    timings_ms: list[float] = []

    for _index in range(25):
        started = time.perf_counter()
        response = client.get(READINESS_URL)
        timings_ms.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200
        assert len(response.data) <= 65_536

    p95 = sorted(timings_ms)[int(len(timings_ms) * 0.95) - 1]
    assert len(request_metrics) == 25
    assert max(int(metrics["query_count"]) for metrics in request_metrics) <= 32
    assert all(metrics["write_count"] == 0 for metrics in request_metrics)
    assert all(metrics["commit_count"] == 0 for metrics in request_metrics)
    assert all(metrics["rollback_count"] == 0 for metrics in request_metrics)
    assert p95 <= 100.0
