from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flask import Flask, render_template
from markupsafe import Markup


def _template_app() -> Flask:
    template_root = Path(__file__).resolve().parents[1] / "player_wiki" / "templates"
    app = Flask(__name__, template_folder=str(template_root))
    app.config.update(TESTING=True, SECRET_KEY="test-secret")
    app.jinja_env.globals["csrf_input"] = lambda: Markup(
        '<input type="hidden" name="csrf_token" value="test">'
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/divine-avatar-forms/"
        "<form_key>/<action>",
        endpoint="character_divine_avatar_form_update",
        view_func=lambda **_kwargs: "",
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/"
        "divine-avatar-forms/<form_key>/<action>",
        endpoint="campaign_combat_character_divine_avatar_form",
        view_func=lambda **_kwargs: "",
        methods=("POST",),
    )
    return app


def _render_avatar(state, *, render_mode="card", combatant_id=None, can_edit=True) -> str:
    app = _template_app()
    with app.test_request_context("/"):
        return render_template(
            "_divine_avatar_forms_state_card.html",
            campaign=SimpleNamespace(slug="linden-pass"),
            character=SimpleNamespace(slug="tod"),
            divine_avatar_forms_state=state,
            divine_avatar_forms_can_edit=can_edit,
            divine_avatar_forms_expected_revision=14,
            divine_avatar_forms_mode="read",
            divine_avatar_forms_page="features",
            divine_avatar_forms_return_view="",
            divine_avatar_forms_combat_view="status" if combatant_id else "",
            divine_avatar_forms_combatant_id=combatant_id,
            divine_avatar_forms_async=bool(combatant_id),
            divine_avatar_forms_anchor="avatar-test-anchor",
            divine_avatar_forms_render_mode=render_mode,
        )


def test_avatar_state_errors_fail_closed_even_if_presenter_flags_are_incorrect():
    html = _render_avatar(
        {
            "available": True,
            "label": "Divine Avatar Forms",
            "state_errors": ["Stored Avatar state is inconsistent."],
            "pending_resolution": {
                "resolution_id": "avatar_of_mourning:2:1",
                "form_key": "avatar_of_mourning",
                "status": "pending",
                "rounds": 3,
                "exhaustion_gained": 3,
                "radiant_damage_dice": "15d12",
                "reason": "dismissed",
            },
            "can_resolve_pending": True,
            "can_correct_pending": True,
            "can_undo_last_action": True,
            "last_transition": {"action": "end"},
            "forms": [],
        },
        render_mode="pending",
        combatant_id=7,
    )

    assert "Stored Avatar state is inconsistent." in html
    assert "Avatar actions are unavailable while this warning is present." in html
    assert "/resolve_end_cost" not in html
    assert "/correct_end_cost" not in html
    assert "/undo_last_action" not in html
    assert 'name="confirmed" value="1"' not in html


def test_pending_avatar_ui_requires_actual_damage_and_exposes_corrections():
    html = _render_avatar(
        {
            "available": True,
            "label": "Divine Avatar Forms",
            "state_errors": [],
            "pending_resolution": {
                "resolution_id": "avatar_of_mourning:2:1",
                "form_key": "avatar_of_mourning",
                "status": "pending",
                "rounds": 3,
                "exhaustion_gained": 3,
                "radiant_damage_dice": "15d12",
                "reason": "dismissed",
            },
            "can_resolve_pending": True,
            "can_correct_pending": True,
            "can_undo_last_action": True,
            "last_transition": {"action": "end"},
            "forms": [],
        },
        render_mode="pending",
        combatant_id=7,
    )

    assert 'name="resolution_id" value="avatar_of_mourning:2:1"' in html
    assert 'name="radiant_damage_applied" min="0" step="1"' in html
    assert 'name="correction_rounds"' in html
    assert 'name="correction_radiant_damage_applied"' not in html
    assert "/resolve_end_cost" in html
    assert "/correct_end_cost" in html
    assert "/undo_last_action" in html
    assert "data-combat-async" in html
    assert 'name="confirmed" value="1"' in html


def test_resolved_avatar_end_cost_correction_includes_actual_damage_without_changing_lifecycle():
    html = _render_avatar(
        {
            "available": True,
            "label": "Divine Avatar Forms",
            "state_errors": [],
            "has_active_form": False,
            "active_form_label": "",
            "exhaustion_level": 3,
            "last_resolution": {
                "resolution_id": "avatar_of_mourning:2:1",
                "kind": "avatar_form_end_cost",
                "form_key": "avatar_of_mourning",
                "status": "resolved",
                "rounds": 3,
                "exhaustion_gained": 3,
                "radiant_damage_dice": "15d12",
                "radiant_damage_applied": 41,
                "reason": "dismissed",
            },
            "can_correct_last_resolution": True,
            "forms": [
                {
                    "form_key": "avatar_of_mourning",
                    "label": "Avatar of Mourning",
                    "active": False,
                    "status_label": "Recharging",
                    "cooldown_active": True,
                    "last_end_cost": {
                        "exhaustion_gained": 3,
                        "radiant_damage_dice": "15d12",
                    },
                    "can_complete_cooldown": False,
                    "can_correct_cooldown_complete": False,
                }
            ],
        }
    )

    assert "Correct Resolved End Cost" in html
    assert 'name="resolution_id" value="avatar_of_mourning:2:1"' in html
    assert 'name="correction_rounds"' in html
    assert 'name="correction_radiant_damage_applied" min="0" step="1" value="41"' in html
    assert "does not change current hit points, reactivate the form, or alter its cooldown" in html
    assert "/correct_end_cost" in html


def test_active_avatar_ui_keeps_power_status_readable_and_wisdom_transient():
    html = _render_avatar(
        {
            "available": True,
            "label": "Divine Avatar Forms",
            "state_errors": [],
            "has_active_form": True,
            "active_form_label": "Avatar of Mourning",
            "exhaustion_level": 1,
            "last_resolution": {
                "resolution_id": "avatar_of_mourning:1:1",
                "form_key": "avatar_of_mourning",
                "status": "resolved",
                "rounds": 1,
                "exhaustion_gained": 1,
                "radiant_damage_dice": "5d12",
                "radiant_damage_applied": 12,
                "reason": "dismissed",
            },
            "can_correct_last_resolution": True,
            "forms": [
                {
                    "form_key": "avatar_of_mourning",
                    "label": "Avatar of Mourning",
                    "active": True,
                    "status_label": "Active",
                    "rounds_elapsed": 2,
                    "rounds_remaining": 8,
                    "end_exhaustion": 2,
                    "end_damage_dice": "10d12",
                    "mourning_wave_used": True,
                    "mourning_wave_available": False,
                    "can_correct_mourning_wave": True,
                    "strength_of_remembrance_used": False,
                    "strength_of_remembrance_available": True,
                    "can_correct_strength_of_remembrance": False,
                }
            ],
        }
    )

    assert "stored, true Wisdom score is never overwritten" in html
    assert "returns immediately when the form ends" in html
    assert ">Used</span>" in html
    assert ">Available</span>" in html
    assert "/correct_mourning_wave" in html
    assert "/strength_of_remembrance" in html
    assert "/end" in html
    assert "data-post-submit-focus-key" in html
    assert "Correct Resolved End Cost" not in html


def test_projection_error_safe_end_respects_read_only_access():
    state = {
        "available": True,
        "label": "Divine Avatar Forms",
        "state_errors": ["Divine Avatar mechanics could not be safely projected."],
        "has_active_form": True,
        "active_form_label": "Avatar of Mourning",
        "forms": [
            {
                "form_key": "avatar_of_mourning",
                "label": "Avatar of Mourning",
                "active": True,
                "end_available": True,
                "status_label": "Active",
                "rounds_elapsed": 2,
                "rounds_remaining": 8,
                "end_exhaustion": 2,
                "end_damage_dice": "10d12",
                "mourning_wave_used": False,
                "mourning_wave_available": False,
                "can_correct_mourning_wave": False,
                "strength_of_remembrance_used": False,
                "strength_of_remembrance_available": False,
                "can_correct_strength_of_remembrance": False,
            }
        ],
    }

    editable_html = _render_avatar(state, can_edit=True)
    read_only_html = _render_avatar(state, can_edit=False)

    assert "/end" in editable_html
    assert "/mourning_wave" not in editable_html
    assert "/end" not in read_only_html
