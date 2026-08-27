from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import yaml

from player_wiki.auth_store import AuthStore
from player_wiki.campaign_combat_preset_store import CampaignCombatPresetStore
from player_wiki.combat_preset_models import CampaignCombatPresetEntryInput
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics


CONTROLS_URL = "/campaigns/linden-pass/combat/dm?view=controls"
CREATE_URL = "/campaigns/linden-pass/combat/presets"


def _manual_form(*, intent: str, digest: str = "", name: str = "Road Ambush"):
    return {
        "intent": intent,
        "name": name,
        "expected_revision": "",
        "review_digest": digest,
        "entry_count": "1",
        "entry_0_id": "",
        "entry_0_source_kind": "manual_npc",
        "entry_0_source_ref": "",
        "entry_0_quantity": "2",
        "entry_0_turn_value": "",
        "entry_0_initiative_priority": "1",
        "entry_0_custom_name": "Road Guard",
        "entry_0_initiative_bonus": "3",
        "entry_0_dexterity_modifier": "2",
        "entry_0_max_hp": "18",
        "entry_0_movement_total": "30",
    }


def _review_digest(response) -> str:
    html = response.get_data(as_text=True)
    match = re.search(r'name="review_digest" value="([0-9a-f]{64})"', html)
    assert match is not None
    return match.group(1)


def _apply_digest(response) -> str:
    html = response.get_data(as_text=True)
    match = re.search(r'name="confirmation_digest" value="([0-9a-f]{64})"', html)
    assert match is not None
    return match.group(1)


def _row_formactions(response) -> list[str]:
    return re.findall(r'formaction="([^"]+)"', unescape(response.get_data(as_text=True)))


def _combat_and_source_state():
    connection = get_db()
    tables = (
        "campaign_combat_trackers",
        "campaign_combatants",
        "campaign_combat_conditions",
        "campaign_combatant_resource_counters",
        "campaign_combatant_resource_notes",
        "campaign_encounter_presets",
        "campaign_encounter_preset_entries",
        "character_state",
    )
    return {
        table: tuple(
            tuple(row)
            for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid",
            ).fetchall()
        )
        for table in tables
    }


def test_controls_renders_saved_encounters_outside_live_replaced_root(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.get(CONTROLS_URL).status_code == 200
    with app.app_context():
        before = _combat_and_source_state()
        response = client.get(CONTROLS_URL)
        after = _combat_and_source_state()
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Saved encounters" in html
    controls_end = html.index("</div>", html.index("data-combat-controls-root"))
    browser_start = html.index('id="saved-encounters"')
    cleanup_start = html.index("combat-clear-confirmation")
    assert controls_end < browser_start < cleanup_start
    assert after == before


def test_manual_review_save_detail_edit_and_delete_use_prg_and_service_audit(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    review = client.post(CREATE_URL, data=_manual_form(intent="review"))
    assert review.status_code == 200
    assert "Review saved encounter" in review.get_data(as_text=True)
    digest = _review_digest(review)

    saved = client.post(
        CREATE_URL,
        data=_manual_form(intent="save", digest=digest),
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert re.search(r"[?&]preset=\d+#saved-encounters$", saved.headers["Location"])

    with app.app_context():
        records = CampaignCombatPresetStore().list_presets("linden-pass")
        assert len(records) == 1
        preset = CampaignCombatPresetStore().get_preset("linden-pass", records[0].id)
        assert preset is not None
        assert preset.name == "Road Ambush"
        assert preset.entries[0].quantity == 2
        created_revision = preset.revision

    detail = client.get(saved.headers["Location"])
    detail_html = unescape(detail.get_data(as_text=True))
    assert detail.status_code == 200
    assert "Road Ambush" in detail_html
    assert "Road Guard" in detail_html
    assert "Current" in detail_html
    assert "Edit saved encounter" in detail_html

    stale_update = _manual_form(intent="review")
    stale_update["expected_revision"] = str(created_revision + 1)
    stale_update["entry_0_id"] = str(preset.entries[0].id)
    stale_response = client.post(
        f"/campaigns/linden-pass/combat/presets/{preset.id}",
        data=stale_update,
    )
    assert stale_response.status_code == 409
    assert "changed elsewhere" in stale_response.get_data(as_text=True)

    stale_delete = client.post(
        f"/campaigns/linden-pass/combat/presets/{preset.id}/delete",
        data={"expected_revision": str(created_revision + 1)},
    )
    assert stale_delete.status_code == 409
    with app.app_context():
        assert CampaignCombatPresetStore().get_preset("linden-pass", preset.id) is not None

    delete = client.post(
        f"/campaigns/linden-pass/combat/presets/{preset.id}/delete",
        data={"expected_revision": str(created_revision)},
        follow_redirects=False,
    )
    assert delete.status_code == 303
    assert delete.headers["Location"].endswith("?view=controls#saved-encounters")
    with app.app_context():
        assert CampaignCombatPresetStore().get_preset("linden-pass", preset.id) is None
        events = [
            event.event_type
            for event in AuthStore().list_recent_audit_events(limit=20)
            if event.event_type.startswith("campaign_encounter_preset_")
        ]
        assert events[:2] == [
            "campaign_encounter_preset_deleted",
            "campaign_encounter_preset_created",
        ]


def test_save_reprepares_and_rejects_changed_review_digest_without_persistence(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    review = client.post(CREATE_URL, data=_manual_form(intent="review"))
    digest = _review_digest(review)

    conflict = client.post(
        CREATE_URL,
        data=_manual_form(intent="save", digest=digest, name="Changed after review"),
    )

    assert conflict.status_code == 409
    assert "Review this draft again" in conflict.get_data(as_text=True)
    with app.app_context():
        assert CampaignCombatPresetStore().list_presets("linden-pass") == []


def test_manager_campaign_and_selector_boundaries(client, sign_in, users):
    assert client.get(CONTROLS_URL).status_code == 302
    sign_in(users["party"]["email"], users["party"]["password"])
    assert client.get(CONTROLS_URL).status_code == 403
    assert client.post(CREATE_URL, data={"intent": "review"}).status_code == 403
    assert client.post(
        f"{CREATE_URL}/1/apply", data={"confirmation_digest": "0" * 64}
    ).status_code == 403

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.get(f"{CONTROLS_URL}&preset=bogus").status_code == 404
    assert client.get(f"{CONTROLS_URL}&preset=999999").status_code == 404
    assert client.get(f"{CONTROLS_URL}&preset_page=1001").status_code == 400


def test_unknown_fields_indices_and_body_cap_are_rejected_without_truncation(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    unknown = _manual_form(intent="review")
    unknown["surprise"] = "nope"
    assert client.post(CREATE_URL, data=unknown).status_code == 400

    excess = _manual_form(intent="review")
    excess["entry_count"] = "51"
    excess["entry_50_custom_name"] = "Must not truncate"
    assert client.post(CREATE_URL, data=excess).status_code == 400

    oversized = _manual_form(intent="review")
    oversized["name"] = "x" * (256 * 1024)
    assert client.post(CREATE_URL, data=oversized).status_code == 413
    with app.app_context():
        assert CampaignCombatPresetStore().list_presets("linden-pass") == []


def test_draft_row_controls_preserve_order_and_review_paths_do_not_write(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    first = _manual_form(intent="add_entry")
    added = client.post(CREATE_URL, data=first)
    assert added.status_code == 200
    assert added.get_data(as_text=True).count("<legend>Row ") == 2

    two_rows = _manual_form(intent="move_down")
    two_rows["entry_count"] = "2"
    for key, value in {
        "entry_1_id": "",
        "entry_1_source_kind": "manual_npc",
        "entry_1_source_ref": "",
        "entry_1_quantity": "1",
        "entry_1_turn_value": "7",
        "entry_1_initiative_priority": "2",
        "entry_1_custom_name": "Second Guard",
        "entry_1_initiative_bonus": "1",
        "entry_1_dexterity_modifier": "0",
        "entry_1_max_hp": "9",
        "entry_1_movement_total": "25",
    }.items():
        two_rows[key] = value

    with app.app_context():
        reset_db_query_metrics()
        moved = client.post(f"{CREATE_URL}?row=0", data=two_rows)
        moved_metrics = get_db_query_metrics()
    moved_html = unescape(moved.get_data(as_text=True))
    assert moved.status_code == 200
    assert moved_html.index('value="Second Guard"') < moved_html.index('value="Road Guard"')
    assert moved_metrics["write_count"] == 0

    review_form = dict(two_rows)
    review_form["intent"] = "review"
    with app.app_context():
        reset_db_query_metrics()
        review = client.post(CREATE_URL, data=review_form)
        review_metrics = get_db_query_metrics()
    assert review.status_code == 200
    assert review_metrics["write_count"] == 0
    assert "Expanded combatants: 3" in review.get_data(as_text=True)


def test_row_action_urls_canonically_include_optional_combatant_and_row(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        preset = CampaignCombatPresetStore().create_preset(
            "linden-pass",
            name="Canonical Actions",
            entries=(
                CampaignCombatPresetEntryInput(
                    source_kind="manual_npc",
                    custom_name="Canonical Guard",
                    initiative_bonus=2,
                    dexterity_modifier=1,
                    max_hp=10,
                    movement_total=30,
                ),
            ),
            created_by_user_id=users["dm"]["id"],
        )

    def assert_row_actions(cases):
        for page_url, expected_path, expected_query in cases:
            response = client.get(page_url)
            assert response.status_code == 200
            actions = _row_formactions(response)
            assert len(actions) == 3
            for action in actions:
                assert action.count("?") == 1
                parsed = urlsplit(action)
                assert parsed.path == expected_path
                assert parse_qs(parsed.query) == expected_query

    assert_row_actions((
        (
            f"{CONTROLS_URL}&preset=new",
            CREATE_URL,
            {"row": ["0"]},
        ),
        (
            f"{CONTROLS_URL}&preset={preset.id}&preset_mode=edit",
            f"{CREATE_URL}/{preset.id}",
            {"row": ["0"]},
        ),
    ))
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Preserved Focus",
            turn_value=11,
            current_hp=12,
            max_hp=12,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
    assert_row_actions((
        (
            f"{CONTROLS_URL}&combatant={combatant.id}&preset=new",
            CREATE_URL,
            {"combatant": [str(combatant.id)], "row": ["0"]},
        ),
        (
            f"{CONTROLS_URL}&combatant={combatant.id}&preset={preset.id}&preset_mode=edit",
            f"{CREATE_URL}/{preset.id}",
            {"combatant": [str(combatant.id)], "row": ["0"]},
        ),
    ))


def test_server_error_marks_native_focus_and_emits_only_loading_aware_nonces_script(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    invalid = _manual_form(intent="review", name="鳥" * 107)
    response = client.post(CREATE_URL, data=invalid)
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert body.count("data-preset-first-error-focus") == 2
    field = re.search(
        r'<input\s+type="text"\s+name="name".*?>',
        body,
        re.DOTALL,
    )
    assert field is not None
    assert "autofocus" in field.group(0)
    assert "data-preset-first-error-focus" in field.group(0)
    script = re.search(
        r'<script nonce="([^"]+)" data-preset-error-focus>(.*?)</script>',
        body,
        re.DOTALL,
    )
    assert script is not None
    assert f"'nonce-{script.group(1)}'" in response.headers["Content-Security-Policy"]
    assert 'classList.contains("app-loading")' in script.group(2)
    assert script.group(2).count("window.requestAnimationFrame") == 2
    assert "invalidField.isConnected" in script.group(2)

    clean = client.get(f"{CONTROLS_URL}&preset=new").get_data(as_text=True)
    assert "data-preset-first-error-focus" not in clean
    assert "data-preset-error-focus" not in clean


def test_selected_source_status_is_sanitized_and_changed_source_requires_fresh_review(
    app, client, sign_in, users
):
    with app.app_context():
        assert app.extensions["character_repository"].get_visible_character(
            "linden-pass", "arden-march"
        ) is not None
    sign_in(users["dm"]["email"], users["dm"]["password"])
    source_form = _manual_form(intent="review", name="Character Patrol")
    source_form.update(
        {
            "entry_0_source_kind": "character",
            "entry_0_source_ref": "arden-march",
            "entry_0_quantity": "1",
            "entry_0_custom_name": "",
            "entry_0_initiative_bonus": "",
            "entry_0_dexterity_modifier": "",
            "entry_0_max_hp": "",
            "entry_0_movement_total": "",
        }
    )
    initial_review = client.post(CREATE_URL, data=source_form)
    initial_digest = _review_digest(initial_review)
    initial_save = client.post(
        CREATE_URL,
        data=dict(source_form, intent="save", review_digest=initial_digest),
    )
    assert initial_save.status_code == 303
    with app.app_context():
        created = CampaignCombatPresetStore().list_presets("linden-pass")[0]
        created = CampaignCombatPresetStore().get_preset("linden-pass", created.id)
        assert created is not None
        saved_version = created.entries[0].source_version

    detail = client.get(f"{CONTROLS_URL}&preset={created.id}")
    detail_html = unescape(detail.get_data(as_text=True))
    assert detail.status_code == 200
    assert "Current" in detail_html
    assert saved_version not in detail_html
    assert "definition.yaml" not in detail_html

    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    payload["stats"]["initiative_bonus"] = 17
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    app.extensions["character_repository"].invalidate_character("linden-pass", "arden-march")

    edit_url = f"{CONTROLS_URL}&preset={created.id}&preset_mode=edit"
    edit = client.get(edit_url)
    assert edit.status_code == 200
    form = {
        "intent": "review",
        "name": "Character Patrol",
        "expected_revision": str(created.revision),
        "review_digest": "",
        "entry_count": "1",
        "entry_0_id": str(created.entries[0].id),
        "entry_0_source_kind": "character",
        "entry_0_source_ref": "arden-march",
        "entry_0_quantity": "1",
        "entry_0_turn_value": "",
        "entry_0_initiative_priority": "1",
        "entry_0_custom_name": "",
        "entry_0_initiative_bonus": "",
        "entry_0_dexterity_modifier": "",
        "entry_0_max_hp": "",
        "entry_0_movement_total": "",
    }
    review = client.post(
        f"/campaigns/linden-pass/combat/presets/{created.id}", data=form
    )
    review_html = review.get_data(as_text=True)
    assert review.status_code == 200
    assert "Source changed" in review_html
    assert saved_version not in review_html
    digest = _review_digest(review)

    stale_save = dict(form, intent="save", review_digest="0" * 64)
    assert client.post(
        f"/campaigns/linden-pass/combat/presets/{created.id}", data=stale_save
    ).status_code == 409
    fresh_save = dict(form, intent="save", review_digest=digest)
    saved = client.post(
        f"/campaigns/linden-pass/combat/presets/{created.id}", data=fresh_save
    )
    assert saved.status_code == 303
    with app.app_context():
        updated = CampaignCombatPresetStore().get_preset("linden-pass", created.id)
        assert updated is not None
        assert updated.revision == created.revision + 1
        assert updated.entries[0].source_version != saved_version


def test_list_is_25_per_page_and_only_selected_detail_is_inspected(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        store = CampaignCombatPresetStore()
        for index in range(26):
            store.create_preset(
                "linden-pass",
                name=f"Preset {index:02d}",
                entries=(),
                created_by_user_id=users["dm"]["id"],
            )

    inspected = []
    service = app.extensions["campaign_combat_preset_service"]
    original_inspect = service.inspect_entries

    def inspect(campaign_slug, entries):
        inspected.append(tuple(entries))
        return original_inspect(campaign_slug, entries)

    monkeypatch.setattr(service, "inspect_entries", inspect)
    first = client.get(CONTROLS_URL)
    assert first.status_code == 200
    assert first.get_data(as_text=True).count("Revision 1") == 25
    assert "Next" in first.get_data(as_text=True)
    assert inspected == []

    second = client.get(f"{CONTROLS_URL}&preset_page=2")
    assert second.status_code == 200
    assert second.get_data(as_text=True).count("Revision 1") == 1
    assert "Previous" in second.get_data(as_text=True)
    assert inspected == []


def test_systems_search_is_one_bounded_row_and_ordinary_live_routes_do_not_query_presets(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    systems_service = app.extensions["systems_service"]
    calls = []

    def search(campaign_slug, *, query, limit):
        calls.append((campaign_slug, query, limit))
        return [
            SimpleNamespace(entry_key=f"monster|MM|{index}", title=f"Monster {index}", source_id="MM")
            for index in range(35)
        ]

    monkeypatch.setattr(systems_service, "search_monster_entries_for_campaign", search)
    form = _manual_form(intent="search_source")
    form["entry_0_source_kind"] = "systems_monster"
    form["entry_0_source_ref"] = ""
    form["entry_0_custom_name"] = ""
    form["entry_0_initiative_bonus"] = ""
    form["entry_0_dexterity_modifier"] = ""
    form["entry_0_max_hp"] = ""
    form["entry_0_movement_total"] = ""
    form["search_row"] = "0"
    form["search_query"] = "owl"
    response = client.post(CREATE_URL, data=form)
    assert response.status_code == 200
    assert calls == [("linden-pass", "owl", 30)]
    assert response.get_data(as_text=True).count("monster|MM|") == 30

    service = app.extensions["campaign_combat_preset_service"]
    monkeypatch.setattr(
        service,
        "list_presets",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preset query")),
    )
    assert client.get("/campaigns/linden-pass/combat/dm").status_code == 200
    assert client.get("/campaigns/linden-pass/combat/dm/live-state?view=controls").status_code == 200


def test_exact_four_preset_post_patterns_and_apply_resolver_is_explicit_only(app):
    rules = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith("campaign_combat_preset_")
    ]
    assert {(rule.rule, tuple(sorted(rule.methods - {"OPTIONS"}))) for rule in rules} == {
        ("/campaigns/<campaign_slug>/combat/presets", ("POST",)),
        ("/campaigns/<campaign_slug>/combat/presets/<int:preset_id>", ("POST",)),
        ("/campaigns/<campaign_slug>/combat/presets/<int:preset_id>/delete", ("POST",)),
        ("/campaigns/<campaign_slug>/combat/presets/<int:preset_id>/apply", ("POST",)),
    }
    source = (Path(app.root_path) / "combat_routes.py").read_text(encoding="utf-8")
    assert source.count("review_preset_apply") == 1


def test_apply_review_separates_proposed_and_existing_then_posts_with_prg_receipt(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        preset = CampaignCombatPresetStore().create_preset(
            "linden-pass",
            name="Apply Patrol",
            entries=(CampaignCombatPresetEntryInput(
                source_kind="manual_npc",
                custom_name="Apply Guard",
                quantity=2,
                initiative_bonus=2,
                dexterity_modifier=1,
                max_hp=9,
                movement_total=30,
            ),),
            created_by_user_id=users["dm"]["id"],
        )
        app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Already Here",
            turn_value=1,
            current_hp=5,
            max_hp=5,
            created_by_user_id=users["dm"]["id"],
        )

    review = client.get(
        f"{CONTROLS_URL}&preset={preset.id}&preset_mode=apply"
    )
    body = unescape(review.get_data(as_text=True))
    assert review.status_code == 200
    assert "Review additive apply" in body
    assert "Proposed combatants" in body and "Existing combatants" in body
    assert "Apply Guard" in body and "Already Here" in body
    assert "does not replace" in body
    digest = _apply_digest(review)

    applied = client.post(
        f"/campaigns/linden-pass/combat/presets/{preset.id}/apply",
        data={"confirmation_digest": digest},
        follow_redirects=False,
    )
    assert applied.status_code == 303
    receipt = client.get(applied.headers["Location"])
    receipt_body = receipt.get_data(as_text=True)
    assert receipt.status_code == 200
    assert "Applied 2 combatants from Apply Patrol" in receipt_body
    with app.app_context():
        assert len(app.extensions["campaign_combat_store"].list_combatants("linden-pass")) == 3


def test_apply_rejects_stale_tracker_and_malformed_forms_without_partial_writes(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        preset = CampaignCombatPresetStore().create_preset(
            "linden-pass",
            name="Guarded Apply",
            entries=(CampaignCombatPresetEntryInput(
                source_kind="manual_npc",
                custom_name="Guarded Apply NPC",
                initiative_bonus=1,
                dexterity_modifier=1,
                max_hp=8,
                movement_total=30,
            ),),
            created_by_user_id=users["dm"]["id"],
        )
    apply_url = f"{CREATE_URL}/{preset.id}/apply"
    review = client.get(f"{CONTROLS_URL}&preset={preset.id}&preset_mode=apply")
    digest = _apply_digest(review)

    assert client.post(apply_url, data={"confirmation_digest": "bad"}).status_code == 400
    assert client.post(
        apply_url,
        data={"confirmation_digest": digest, "unexpected": "field"},
    ).status_code == 400
    with app.app_context():
        assert app.extensions["campaign_combat_store"].list_combatants("linden-pass") == []
        app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Concurrent Existing",
            turn_value=2,
            current_hp=5,
            max_hp=5,
            created_by_user_id=users["dm"]["id"],
        )

    stale = client.post(apply_url, data={"confirmation_digest": digest})
    stale_body = stale.get_data(as_text=True)
    assert stale.status_code == 409
    assert "tracker" in stale_body and "fresh apply review" in stale_body
    assert 'name="confirmation_digest"' not in stale_body
    with app.app_context():
        combatants = app.extensions["campaign_combat_store"].list_combatants("linden-pass")
        assert [combatant.display_name for combatant in combatants] == ["Concurrent Existing"]


def test_unconfirmed_post_commit_page_has_no_repeat_control(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        preset = CampaignCombatPresetStore().create_preset(
            "linden-pass",
            name="Unconfirmed Browser Apply",
            entries=(CampaignCombatPresetEntryInput(
                source_kind="manual_npc",
                custom_name="Committed Once",
                initiative_bonus=0,
                dexterity_modifier=0,
                max_hp=1,
                movement_total=30,
            ),),
            created_by_user_id=users["dm"]["id"],
        )
    review = client.get(f"{CONTROLS_URL}&preset={preset.id}&preset_mode=apply")
    digest = _apply_digest(review)
    combat_store = app.extensions["campaign_combat_store"]
    preset_service = app.extensions["campaign_combat_preset_service"]
    monkeypatch.setattr(
        preset_service,
        "_verify_apply_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("injected browser readback failure")
        ),
    )
    response = client.post(
        f"{CREATE_URL}/{preset.id}/apply",
        data={"confirmation_digest": digest},
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 503
    assert "Apply outcome unconfirmed" in body
    assert "Do not submit it again" in body
    assert 'name="confirmation_digest"' not in body
    assert "Apply 1 combatants" not in body

    with app.app_context():
        assert [
            combatant.display_name
            for combatant in combat_store.list_combatants("linden-pass")
        ] == ["Committed Once"]


def test_materialization_occurs_only_for_explicit_apply_review_or_post(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        preset = CampaignCombatPresetStore().create_preset(
            "linden-pass",
            name="Explicit Review Only",
            entries=(CampaignCombatPresetEntryInput(
                source_kind="manual_npc",
                custom_name="Explicit",
                initiative_bonus=0,
                dexterity_modifier=0,
                max_hp=1,
                movement_total=30,
            ),),
            created_by_user_id=users["dm"]["id"],
        )
    service = app.extensions["campaign_combat_preset_service"]
    original = service.source_resolver.resolve_entries_for_apply
    calls = []

    def tracked(campaign_slug, entries):
        calls.append((campaign_slug, len(entries)))
        return original(campaign_slug, entries)

    monkeypatch.setattr(service.source_resolver, "resolve_entries_for_apply", tracked)
    assert client.get(CONTROLS_URL).status_code == 200
    assert client.get(f"{CONTROLS_URL}&preset={preset.id}").status_code == 200
    assert client.get("/campaigns/linden-pass/combat/dm").status_code == 200
    assert client.get("/campaigns/linden-pass/combat/dm/live-state?view=controls").status_code == 200
    assert calls == []
    explicit = client.get(f"{CONTROLS_URL}&preset={preset.id}&preset_mode=apply")
    assert explicit.status_code == 200
    assert calls == [("linden-pass", 1)]


def test_browser_row_expansion_name_reference_integer_and_search_caps(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    fifty = _manual_form(intent="review")
    fifty["entry_0_quantity"] = "50"
    assert client.post(CREATE_URL, data=fifty).status_code == 200

    fifty_one = _manual_form(intent="review")
    fifty_one["entry_0_quantity"] = "51"
    assert client.post(CREATE_URL, data=fifty_one).status_code == 400

    too_large_integer = _manual_form(intent="review")
    too_large_integer["entry_0_turn_value"] = str(2**63)
    assert client.post(CREATE_URL, data=too_large_integer).status_code == 400

    utf8_name = _manual_form(intent="review", name="鳥" * 107)
    assert len(utf8_name["name"].encode("utf-8")) == 321
    assert client.post(CREATE_URL, data=utf8_name).status_code == 400

    source_ref = _manual_form(intent="review")
    source_ref.update(
        {
            "entry_0_source_kind": "character",
            "entry_0_source_ref": "x" * 513,
            "entry_0_custom_name": "",
            "entry_0_initiative_bonus": "",
            "entry_0_dexterity_modifier": "",
            "entry_0_max_hp": "",
            "entry_0_movement_total": "",
        }
    )
    assert client.post(CREATE_URL, data=source_ref).status_code == 400

    called = False

    def fail_search(*_args, **_kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        app.extensions["systems_service"],
        "search_monster_entries_for_campaign",
        fail_search,
    )
    search = dict(source_ref, intent="search_source", search_row="0", search_query="x" * 101)
    search["entry_0_source_kind"] = "systems_monster"
    search["entry_0_source_ref"] = ""
    assert client.post(CREATE_URL, data=search).status_code == 400
    assert not called
