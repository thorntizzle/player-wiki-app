"""Player assignment records through ordinary session/API admission."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import Callable
from flask import abort, jsonify, render_template, request
from .auth import campaign_scope_access_required
from .csrf import CSRF_FIELD_NAME

_BOOL_FIELDS = {"confirm", "nonmagical", "touch", "long_rest", "tools", "action", "tiny"}
_INT_FIELDS = {"message_seconds", "value_gp", "days_elapsed", "policy_revision"}
_TEXT_FIELDS = {"kind", "operation", "choice_id", "object_mode", "object_id", "object_name",
                "recipient", "object_kind", "attunement", "replace_oldest", "property_text",
                "assignment_id", "reason", "visual_type", "visual_text", "policy_sha256"}
_TRANSPORT = {CSRF_FIELD_NAME, "expected_revision", "mode", "page", "return_view"}

def _form_values(form):
    if any(len(form.getlist(key)) != 1 for key in form):
        raise ValueError("Submit each assignment field once.")
    if set(form) - (_BOOL_FIELDS | _INT_FIELDS | _TEXT_FIELDS | _TRANSPORT):
        raise ValueError("An unsupported assignment field was submitted.")
    values = {}
    for key in form:
        if key in _TRANSPORT:
            continue
        value = form[key]
        if key in _BOOL_FIELDS:
            if value != "1":
                raise ValueError("Confirm assignment conditions explicitly.")
            values[key] = True
        elif key in _INT_FIELDS:
            pattern = r"0|[1-9][0-9]{0,18}" if key == "policy_revision" else r"0|[1-9][0-9]{0,6}"
            if not re.fullmatch(pattern, value):
                raise ValueError("Assignment quantities must be whole numbers.")
            values[key] = int(value)
        else:
            values[key] = value
    return values

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Submit each JSON field once.")
        result[key] = value
    return result

def _json_precheck():
    def invalid_number(value):
        raise ValueError("Assignment numbers must be finite.")
    value = json.loads(request.get_data(), object_pairs_hook=_unique_object, parse_constant=invalid_number)
    if type(value) is not dict:
        raise ValueError("An assignment action must be a JSON object.")

@dataclass(frozen=True)
class AssignmentRouteDependencies:
    load_session_character_context: Callable
    has_session_mode_access: Callable
    get_character_state_service: Callable
    present_assignment_read: Callable
    run_session_mutation: Callable

def register_assignment_routes(app, *, dependencies):
    def view(campaign_slug, character_slug):
        loaded = dependencies.load_session_character_context(campaign_slug, character_slug)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        record = loaded.record
        if record.definition.system != "DND-5E":
            abort(404)
        if request.method == "POST":
            try:
                values = _form_values(request.form)
            except ValueError as error:
                abort(400, description=str(error))
            def action(current, expected_revision, user_id):
                return dependencies.get_character_state_service().artificer_assignment_action(
                    current, expected_revision=expected_revision, values=values,
                    updated_by_user_id=user_id)
            return dependencies.run_session_mutation(campaign_slug, character_slug,
                anchor="features", loaded_context=loaded, success_message="Assignment record saved.", action=action)
        assignments = dependencies.present_assignment_read(record, campaign=loaded.campaign)
        inventory = [{"id": item.get("id"), "name": item.get("name", "Object")}
                     for item in record.state_record.state.get("inventory", [])
                     if type(item) is dict and type(item.get("id")) is str
                     and type(item.get("quantity")) is int and item["quantity"] == 1]
        return render_template("character_artificer_assignments.html", campaign=loaded.campaign,
            character=record.definition, state_revision=record.state_record.revision,
            assignments=assignments, inventory_choices=inventory, active_nav="characters")
    app.add_url_rule("/campaigns/<campaign_slug>/characters/<character_slug>/session/artificer-assignments",
        endpoint="character_artificer_assignments_view",
        view_func=campaign_scope_access_required("characters", own_character=True)(view), methods=("GET", "POST"))

def register_assignment_api(api, *, login_required, load_character_record, has_session_mode_access,
                            get_character_state_service, present_assignment_read,
                            run_character_mutation, json_error):
    def view(campaign_slug, character_slug):
        if request.method == "GET":
            record = load_character_record(campaign_slug, character_slug)
            if not has_session_mode_access(campaign_slug, character_slug):
                return json_error("You do not have permission to manage these assignments.", 403, code="forbidden")
            return jsonify({"state_revision": record.state_record.revision,
                "assignments": present_assignment_read(record)})
        try:
            _json_precheck()
        except (ValueError, UnicodeError, TypeError):
            return json_error("Submit a JSON object with unique fields and finite numbers.", 400, code="invalid_json")
        def action(record, payload, user_id):
            revision = payload.get("expected_revision")
            if type(revision) is not int or revision < 1:
                raise ValueError("An exact integer state revision is required.")
            values = {key: value for key, value in payload.items() if key != "expected_revision"}
            return get_character_state_service().artificer_assignment_action(record,
                expected_revision=revision, values=values, updated_by_user_id=user_id)
        return run_character_mutation(campaign_slug, character_slug, action)
    api.add_url_rule("/campaigns/<campaign_slug>/characters/<character_slug>/session/artificer-assignments",
        endpoint="character_artificer_assignments", view_func=login_required(view), methods=("GET", "POST"))
