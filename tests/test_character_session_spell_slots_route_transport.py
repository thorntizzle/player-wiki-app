from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import Forbidden, NotFound

import player_wiki.character_session_spell_slots_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = '/campaigns/linden-pass/characters/arden-march/session/spell-slots/1'
ENDPOINT = 'character_session_spell_slots'


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _dependencies(app):
    raw = _handler(app)
    return dict(zip(raw.__code__.co_freevars, raw.__closure__))["dependencies"]


def _install_dependencies(app, monkeypatch, **replacements):
    cell = _dependencies(app)
    monkeypatch.setattr(cell, 'cell_contents', replace(cell.cell_contents, **replacements))


def _fixtures(events):
    admission = SimpleNamespace(campaign=SimpleNamespace(slug='linden-pass', system='dnd5e'),
                                record=SimpleNamespace(definition={'name': 'Arden'}))

    def admit(*args, **kwargs):
        events.append(('admit', args, kwargs))
        return admission

    def supported(*args):
        events.append(('supported', args, {}))
        return True

    def unsupported(*args):
        events.append(('redirect', args, {}))
        return 'unsupported-result'

    def update(*args, **kwargs):
        events.append(('update', args, kwargs))
        return 'updated-state'

    def service():
        events.append(('service', (), {}))
        return SimpleNamespace(update_spell_slots=update)

    def runner(*args, **kwargs):
        events.append(('runner', args, kwargs))
        assert kwargs['admission'] is admission
        assert kwargs['action'](admission.record, 17, 42) == 'updated-state'
        return 'mutation-result'

    return dict(admit_session_mutation=admit,
                campaign_supports_dnd5e_character_spellcasting_tools=supported,
                redirect_unsupported_dnd5e_character_spellcasting_tools=unsupported,
                run_session_mutation=runner, get_character_state_service=service)


def test_transport_registers_one_scoped_post_and_supplies_admission(app, client):
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    assert rule.rule == '/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<int:level>'
    assert rule.methods == {'POST', 'OPTIONS'}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ('get', 'head', 'put', 'patch', 'delete'):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    expected = {field.name for field in fields(route_module.CharacterSessionSpellSlotsRouteDependencies)}
    assert expected == {'admit_session_mutation', 'campaign_supports_dnd5e_character_spellcasting_tools',
                        'redirect_unsupported_dnd5e_character_spellcasting_tools',
                        'run_session_mutation', 'get_character_state_service'}
    route_tree = ast.parse(inspect.getsource(route_module))
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == 'campaign_scope_access_required' for node in ast.walk(route_tree)) == 1
    app_tree = ast.parse((PROJECT_ROOT / 'player_wiki/app.py').read_text(encoding='utf-8'))
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == 'register_character_session_spell_slots_route' for node in ast.walk(app_tree)) == 1
    assert not any(isinstance(node, ast.FunctionDef) and node.name == ENDPOINT for node in ast.walk(app_tree))
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert endpoints.index('character_session_resource') < endpoints.index(ENDPOINT) < endpoints.index('character_session_item_action_use')


def test_handler_passes_one_admission_and_defers_raw_forms_until_action(app, monkeypatch):
    events = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    values = {'slot_lane_id': ' wizard:main ', 'used': ' 2 ', 'delta_used': '-1'}

    class RecordingForm:
        def get(self, key, default=None):
            events.append(('form', (key, default), {}))
            return values.get(key, default)

    monkeypatch.setattr(route_module, 'request', SimpleNamespace(form=RecordingForm()))
    with app.test_request_context(ROUTE_PATH, method='POST'):
        assert _handler(app)('linden-pass', 'arden-march', 1) == 'mutation-result'
    assert [event[0] for event in events] == ['admit', 'supported', 'runner', 'service', 'form', 'form', 'form', 'update']
    runner = next(event for event in events if event[0] == 'runner')
    assert runner[1] == ('linden-pass', 'arden-march')
    assert runner[2]['anchor'] == 'session-spell-slots'
    assert runner[2]['success_message'] == 'Spell slot usage updated.'
    assert [event[1] for event in events if event[0] == 'form'] == [('slot_lane_id', ''), ('used', None), ('delta_used', None)]
    update = events[-1]
    assert update[1] == (runner[2]['admission'].record, 1)
    assert update[2] == dict(slot_lane_id=' wizard:main ', used=' 2 ', delta_used='-1', expected_revision=17, updated_by_user_id=42)


def test_raw_first_repeated_form_values_are_preserved(app, monkeypatch):
    events = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    data = MultiDict([('slot_lane_id', ' wizard:main '), ('slot_lane_id', 'warlock:pact'),
                      ('used', ' 2 '), ('used', '9'), ('delta_used', ''), ('delta_used', '7')])
    with app.test_request_context(ROUTE_PATH, method='POST', data=data):
        _handler(app)('linden-pass', 'arden-march', 1)
    assert events[-1][2] == dict(slot_lane_id=' wizard:main ', used=' 2 ', delta_used='', expected_revision=17, updated_by_user_id=42)


@pytest.mark.parametrize('error', [Forbidden, NotFound])
def test_failed_admission_precedes_support_runner_and_form(app, monkeypatch, error):
    events = []
    deps = _fixtures(events)
    def denied(*args):
        events.append(('admit', args, {}))
        raise error()
    deps['admit_session_mutation'] = denied
    _install_dependencies(app, monkeypatch, **deps)
    with app.test_request_context(ROUTE_PATH, method='POST'):
        with pytest.raises(error):
            _handler(app)('linden-pass', 'arden-march', 1)
    assert [event[0] for event in events] == ['admit']


def test_unsupported_campaign_redirects_before_runner_service_and_form(app, monkeypatch):
    events = []
    deps = _fixtures(events)
    def unsupported(*args):
        events.append(('supported', args, {}))
        return False
    deps['campaign_supports_dnd5e_character_spellcasting_tools'] = unsupported
    _install_dependencies(app, monkeypatch, **deps)
    with app.test_request_context(ROUTE_PATH, method='POST'):
        assert _handler(app)('linden-pass', 'arden-march', 1) == 'unsupported-result'
    assert [event[0] for event in events] == ['admit', 'supported', 'redirect']


def test_scope_and_view_as_denials_do_no_handler_work_but_bearer_wins(app, client, sign_in, users, set_campaign_visibility, monkeypatch):
    events = []
    _install_dependencies(app, monkeypatch, **_fixtures(events))
    set_campaign_visibility('linden-pass', characters='private')
    sign_in(users['owner']['email'], users['owner']['password'])
    assert client.post(ROUTE_PATH).status_code == 404
    assert events == []
    set_campaign_visibility('linden-pass', characters='public')
    sign_in(users['admin']['email'], users['admin']['password'])
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users['party']['id']
    assert client.post(ROUTE_PATH).status_code == 403
    assert events == []
    token = issue_api_token(app, users['admin']['email'], label='slots-transport')
    assert client.post(ROUTE_PATH, headers=api_headers(token)).status_code == 200
    assert [event[0] for event in events] == ['admit', 'supported', 'runner', 'service', 'update']


@pytest.mark.parametrize('stage', ['admit', 'supported', 'redirect', 'runner', 'service', 'slot_lane_id', 'used', 'delta_used', 'update'])
def test_faults_propagate_at_transport_stages(app, monkeypatch, stage):
    events = []
    deps = _fixtures(events)
    def fault(*args, **kwargs):
        raise RuntimeError(f'{stage} fault')
    names = dict(admit='admit_session_mutation', supported='campaign_supports_dnd5e_character_spellcasting_tools',
                 redirect='redirect_unsupported_dnd5e_character_spellcasting_tools', runner='run_session_mutation', service='get_character_state_service')
    if stage in names:
        deps[names[stage]] = fault
        if stage == 'redirect':
            deps['campaign_supports_dnd5e_character_spellcasting_tools'] = lambda _: False
    elif stage == 'update':
        deps['get_character_state_service'] = lambda: SimpleNamespace(update_spell_slots=fault)
    else:
        class FaultingForm:
            def get(self, key, default=None):
                if key == stage:
                    fault()
                return default
        monkeypatch.setattr(route_module, 'request', SimpleNamespace(form=FaultingForm()))
    _install_dependencies(app, monkeypatch, **deps)
    with app.test_request_context(ROUTE_PATH, method='POST'):
        with pytest.raises(RuntimeError, match=f'{stage} fault'):
            _handler(app)('linden-pass', 'arden-march', 1)
