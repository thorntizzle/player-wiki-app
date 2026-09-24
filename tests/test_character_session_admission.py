from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import inspect
import os
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import g, request
from werkzeug.exceptions import Forbidden

import player_wiki.app as app_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_service import CharacterStateValidationError
from player_wiki.db import get_db
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.helpers.character_state_helpers import _write_campaign_config
from tests.test_character_session_spell_slots_route_transport import _dependencies, _install_dependencies

CAMPAIGN = 'linden-pass'
CHARACTER = 'arden-march'
ROUTE = f'/campaigns/{CAMPAIGN}/characters/{CHARACTER}/session/spell-slots/2'
CONFLICT = 'This sheet changed in another session. Refresh the page and try again.'


def _seed(app, sign_in, users, get_character, set_campaign_visibility, *, actor='owner'):
    set_campaign_visibility(CAMPAIGN, characters='players')
    sign_in(users[actor]['email'], users[actor]['password'])
    return get_character(CHARACTER)


def _snapshot(app):
    with app.app_context():
        rows = [tuple(row) for row in get_db().execute('SELECT campaign_slug, character_slug, revision, state_json, updated_at, updated_by_user_id FROM character_state ORDER BY campaign_slug, character_slug').fetchall()]
    root = app.config['TEST_CAMPAIGNS_DIR'] / CAMPAIGN / 'characters' / CHARACTER
    return rows, {name: (root / name).read_bytes() for name in ('definition.yaml', 'import.yaml')}


def _flashes(client):
    with client.session_transaction() as session:
        return list(session.get('_flashes', []))


def _measure(app, monkeypatch):
    repository = app.extensions['character_repository']
    service = app.extensions['character_state_service']
    counts = dict(load=0, action=0, replace=0, access=0)
    original_load = repository._load_character
    original_action = service.update_spell_slots
    original_replace = service.state_store.replace_state
    original_access = app_module.has_session_mode_access
    def load(*args, **kwargs):
        counts['load'] += 1
        assert kwargs['initialize_missing_state'] is False
        return original_load(*args, **kwargs)
    def action(*args, **kwargs):
        counts['action'] += 1
        return original_action(*args, **kwargs)
    def store(*args, **kwargs):
        counts['replace'] += 1
        return original_replace(*args, **kwargs)
    def access(*args, **kwargs):
        counts['access'] += 1
        return original_access(*args, **kwargs)
    monkeypatch.setattr(repository, '_load_character', load)
    monkeypatch.setattr(service, 'update_spell_slots', action)
    monkeypatch.setattr(service.state_store, 'replace_state', store)
    monkeypatch.setattr(app_module, 'has_session_mode_access', access)
    def unexpected_live_write(*args, **kwargs):
        raise AssertionError('spell-slot mutation added live-view invalidation')
    monkeypatch.setattr(app.extensions['campaign_session_service'], 'bump_live_state_revision', unexpected_live_write)
    monkeypatch.setattr(app.extensions['campaign_combat_service'], 'mark_character_state_changed', unexpected_live_write)
    return counts


@pytest.mark.parametrize('surface', ['read', 'session'])
def test_complete_post_admits_once_and_commits_once(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch, surface):
    active = surface == 'session'
    if active:
        sign_in(users['dm']['email'], users['dm']['password'])
        assert client.post(f'/campaigns/{CAMPAIGN}/session/start').status_code == 302
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    before = _snapshot(app)
    counts = _measure(app, monkeypatch)
    data = dict(expected_revision=str(record.state_record.revision), used='1', mode='read', page='spellcasting')
    headers = {}
    if active:
        data.update(mode='session', return_view='session-character', fragment='1')
        headers['X-Requested-With'] = 'XMLHttpRequest'
    response = client.post(ROUTE, data=data, headers=headers, follow_redirects=False)
    assert response.status_code == 302
    assert counts == dict(load=1, action=1, replace=1, access=1)
    location = urlsplit(response.headers['Location'])
    assert location.fragment == 'session-spell-slots'
    query = parse_qs(location.query)
    if active:
        assert location.path == f'/campaigns/{CAMPAIGN}/session/character'
        assert query == dict(character=[CHARACTER], page=['spells'], fragment=['1'])
    else:
        assert location.path == f'/campaigns/{CAMPAIGN}/characters/{CHARACTER}'
        assert query == dict(page=['spellcasting'])
    after = _snapshot(app)
    assert after[1] == before[1]
    assert after[0][0][2] == before[0][0][2] + 1
    assert after[0][0][-1] == users['owner']['id']
    assert ('success', 'Spell slot usage updated.') in _flashes(client)


def test_actual_validation_and_stale_feedback_do_not_write(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    before = _snapshot(app)
    counts = _measure(app, monkeypatch)
    response = client.post(ROUTE, data=dict(expected_revision=str(record.state_record.revision), used='oops', mode='read', page='spellcasting'))
    assert response.status_code == 302
    assert counts == dict(load=1, action=1, replace=0, access=1)
    assert any(category == 'error' and 'oops' in message for category, message in _flashes(client))
    assert _snapshot(app) == before
    response = client.post(ROUTE, data=dict(expected_revision=str(record.state_record.revision - 1), used='1', mode='read', page='spellcasting'))
    assert response.status_code == 302
    assert ('error', CONFLICT) in _flashes(client)
    assert counts == dict(load=2, action=2, replace=1, access=2)
    assert _snapshot(app) == before

@pytest.mark.parametrize('actor', ['dm', 'admin'])
def test_manager_actor_is_preserved(app, client, sign_in, users, get_character, set_campaign_visibility, actor):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility, actor=actor)
    response = client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used='1', user_id=999, character_slug='selene-brook'))
    assert response.status_code == 302
    assert _snapshot(app)[0][0][-1] == users[actor]['id']


@pytest.mark.parametrize('changes,message', [
    ({'expected_revision': None}, 'Missing sheet revision.'),
    ({'expected_revision': ''}, 'Missing sheet revision.'),
    ({'expected_revision': 'bad'}, 'bad'),
    ({'used': 'bad'}, 'bad'),
    ({'delta_used': 'bad'}, 'bad'),
    ({'used': '-1'}, 'must be between'),
    ({'used': '999'}, 'must be between'),
    ({'slot_lane_id': 'unknown-lane', 'level': '9'}, 'Unknown spell slot level'),
    ({'level': '9'}, 'Unknown spell slot level'),
])
def test_malformed_values_leave_exact_state_and_sources_unchanged(app, client, sign_in, users, get_character, set_campaign_visibility, changes, message):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    data = dict(expected_revision=str(record.state_record.revision), used='1', mode='read', page='spellcasting')
    data.update(changes)
    level = data.pop('level', '2')
    data = {key: value for key, value in data.items() if value is not None}
    before = _snapshot(app)
    response = client.post(ROUTE.rsplit('/', 1)[0] + '/' + level, data=data)
    assert response.status_code == 302
    assert any(category == 'error' and message in text for category, text in _flashes(client))
    assert _snapshot(app) == before


def test_used_and_delta_keep_service_semantics(app, client, sign_in, users, get_character, set_campaign_visibility):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    response = client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used=' 2 ', delta_used=' -1 '))
    assert response.status_code == 302
    updated = get_character(CHARACTER)
    assert next(slot['used'] for slot in updated.state_record.state['spell_slots'] if slot['level'] == 2) == 1


@pytest.mark.parametrize('actor', ['party', 'observer', 'outsider', None])
def test_in_scope_access_denial_never_writes(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch, actor):
    record = get_character(CHARACTER)
    set_campaign_visibility(CAMPAIGN, characters='public')
    if actor:
        sign_in(users[actor]['email'], users[actor]['password'])
    before = _snapshot(app)
    counts = _measure(app, monkeypatch)
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used='1')).status_code == 403
    assert counts == dict(load=1, action=0, replace=0, access=1)
    assert _snapshot(app) == before


def test_scope_and_view_as_refusals_never_admit_or_write(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch):
    record = get_character(CHARACTER)
    set_campaign_visibility(CAMPAIGN, characters='private')
    sign_in(users['owner']['email'], users['owner']['password'])
    before = _snapshot(app)
    counts = _measure(app, monkeypatch)
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used=1)).status_code == 404
    set_campaign_visibility(CAMPAIGN, characters='public')
    sign_in(users['admin']['email'], users['admin']['password'])
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users['party']['id']
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used=1)).status_code == 403
    assert counts == dict(load=0, action=0, replace=0, access=0)
    assert _snapshot(app) == before


@pytest.mark.parametrize('missing_variant', ['valid-form', 'denied-actor', 'malformed', 'unsupported'])
def test_missing_state_is_404_without_initialization(app, client, sign_in, users, set_campaign_visibility, monkeypatch, missing_variant):
    set_campaign_visibility(CAMPAIGN, characters='public')
    actor = 'party' if missing_variant == 'denied-actor' else 'owner'
    sign_in(users[actor]['email'], users[actor]['password'])
    if missing_variant == 'unsupported':
        _write_campaign_config(app, lambda payload: payload.update(system='Xianxia', systems_library='Xianxia'))
    repository = app.extensions['character_repository']
    def forbidden(*args, **kwargs):
        raise AssertionError('refusal initialized state')
    monkeypatch.setattr(repository.state_store, 'initialize_state_if_missing', forbidden)
    before = _snapshot(app)
    assert before[0] == []
    response = client.post(ROUTE, data=dict(expected_revision='bad' if missing_variant == 'malformed' else '1', used='1'))
    assert response.status_code == 404
    assert _snapshot(app) == before


@pytest.mark.parametrize('case', ['missing', 'unsafe', 'inactive', 'incomplete', 'protected', 'wrong-definition-target'])
def test_unavailable_target_refuses_before_action_without_writes(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch, case):
    _seed(app, sign_in, users, get_character, set_campaign_visibility)
    repository = app.extensions['character_repository']
    root = app.config['TEST_CAMPAIGNS_DIR'] / CAMPAIGN / 'characters' / CHARACTER
    path = ROUTE
    if case == 'missing':
        path = path.replace(CHARACTER, 'missing-character')
    elif case == 'unsafe':
        path = path.replace(CHARACTER, '..%5Cvictim')
    elif case == 'incomplete':
        (root / 'import.yaml').rename(root / 'absent-import.yaml')
    elif case == 'protected':
        monkeypatch.setattr(repository, '_is_reconciliation_protected', lambda *_: True)
    elif case in ('inactive', 'wrong-definition-target'):
        definition = root / 'definition.yaml'
        text = definition.read_text(encoding='utf-8')
        if case == 'inactive':
            assert 'status: active' in text
            text = text.replace('status: active', 'status: archived')
        else:
            text = text.replace('character_slug: arden-march', 'character_slug: selene-brook')
        definition.write_text(text, encoding='utf-8')
    with app.app_context():
        before = app.extensions['character_state_store'].get_state(CAMPAIGN, CHARACTER)
    counts = _measure(app, monkeypatch)
    assert client.post(path, data=dict(expected_revision=before.revision, used='1')).status_code == 404
    assert counts['action'] == counts['replace'] == counts['access'] == 0
    with app.app_context():
        assert app.extensions['character_state_store'].get_state(CAMPAIGN, CHARACTER) == before


def test_unsupported_and_inactive_session_refusals_keep_redirects_and_do_not_write(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    before = _snapshot(app)
    counts = _measure(app, monkeypatch)
    response = client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used='1', return_view='session-character', page='spellcasting', fragment='1'), headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers['Location']).query)
    assert query == dict(character=[CHARACTER], page=['spells'], fragment=['1'])
    assert ('error', 'The live session has ended. Session character editing is no longer available.') in _flashes(client)
    assert counts == dict(load=1, action=0, replace=0, access=1)
    assert _snapshot(app) == before
    _write_campaign_config(app, lambda payload: payload.update(system='Xianxia', systems_library='Xianxia'))
    response = client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used='1'))
    assert response.status_code == 302
    assert response.headers['Location'] == f'/campaigns/{CAMPAIGN}/characters/{CHARACTER}'
    assert ('error', app_module.DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE) in _flashes(client)
    assert counts == dict(load=2, action=0, replace=0, access=2)
    assert _snapshot(app) == before


def test_cookie_csrf_denial_and_bearer_precedence_keep_actor(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    app.config['CSRF_ENABLED'] = True
    client.get('/account')
    with client.session_transaction() as session:
        token = session['csrf_token']
    before = _snapshot(app)
    counts = _measure(app, monkeypatch)
    data = dict(expected_revision=record.state_record.revision, used='1')
    for headers in ({}, {'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': 'invalid'}):
        response = client.post(ROUTE, data=data, headers=headers)
        assert response.status_code == 400
        if headers:
            assert response.get_json()['error']['code'] == 'csrf_failed'
    assert counts == dict(load=0, action=0, replace=0, access=0)
    assert _snapshot(app) == before
    assert client.post(ROUTE, data={**data, '_csrf_token': token}).status_code == 302
    api_token = issue_api_token(app, users['admin']['email'], label='slot-actor')
    with client.session_transaction() as session:
        session[VIEW_AS_SESSION_KEY] = users['party']['id']
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision + 1, used='2'), headers=api_headers(api_token)).status_code == 302
    assert _snapshot(app)[0][0][-1] == users['admin']['id']
    assert counts == dict(load=2, action=2, replace=2, access=2)


def _runner_call(runner, admission, *, campaign=CAMPAIGN, character=CHARACTER, action=lambda *_: None):
    return runner(campaign, character, admission=admission, anchor='session-spell-slots', success_message='updated', action=action)


@pytest.mark.parametrize('case', ['fabricated', 'plain-object', 'campaign', 'character', 'actor', 'missing-actor', 'definition-campaign', 'definition-character', 'state-campaign', 'state-character', 'campaign-object'])
def test_invalid_admission_is_rejected_without_action_or_fallback_load(app, get_character, monkeypatch, case):
    record = get_character(CHARACTER)
    deps = _dependencies(app).cell_contents
    actor = SimpleNamespace(id=42)
    monkeypatch.setattr(app_module, 'get_current_user', lambda: actor)
    monkeypatch.setattr(app_module, 'has_session_mode_access', lambda *_: True)
    before = _snapshot(app)
    with app.test_request_context(ROUTE, method='POST', data=dict(expected_revision=record.state_record.revision)):
        admission = deps.admit_session_mutation(CAMPAIGN, CHARACTER)
        kwargs = {}
        if case == 'fabricated':
            admission = replace(admission)
        elif case == 'plain-object':
            admission = object()
        elif case in ('campaign', 'character'):
            kwargs[case] = 'different-target'
        elif case == 'actor':
            actor = SimpleNamespace(id=43)
        elif case == 'missing-actor':
            actor = None
        elif case.startswith('definition-'):
            setattr(admission.record.definition, case.removeprefix('definition-') + '_slug', 'different-target')
        elif case.startswith('state-'):
            setattr(admission.record.state_record, case.removeprefix('state-') + '_slug', 'different-target')
        elif case == 'campaign-object':
            admission.campaign.slug = 'different-target'
        def forbidden(*args, **kwargs):
            raise AssertionError('invalid context performed fallback admission or action')
        monkeypatch.setattr(app.extensions['character_repository'], '_load_character', forbidden)
        with pytest.raises(Forbidden):
            _runner_call(deps.run_session_mutation, admission, action=forbidden, **kwargs)
    assert _snapshot(app) == before


def test_admission_is_bound_to_concrete_request_and_cannot_mutate_twice(app, get_character, monkeypatch):
    record = get_character(CHARACTER)
    deps = _dependencies(app).cell_contents
    monkeypatch.setattr(app_module, 'get_current_user', lambda: SimpleNamespace(id=42))
    monkeypatch.setattr(app_module, 'has_session_mode_access', lambda *_: True)
    calls = []
    with app.test_request_context(ROUTE, method='POST', data=dict(expected_revision=record.state_record.revision)):
        admission = deps.admit_session_mutation(CAMPAIGN, CHARACTER)
        assert admission.request_identity is request._get_current_object()
        with pytest.raises(Forbidden):
            deps.admit_session_mutation(CAMPAIGN, CHARACTER)
        assert _runner_call(deps.run_session_mutation, admission, action=lambda *args: calls.append(args)).status_code == 302
        with pytest.raises(Forbidden):
            _runner_call(deps.run_session_mutation, admission, action=lambda *args: calls.append(args))
    with app.test_request_context(ROUTE, method='POST', data=dict(expected_revision=record.state_record.revision)):
        g.character_session_admission = admission
        g.character_session_mutation_started = False
        with pytest.raises(Forbidden):
            _runner_call(deps.run_session_mutation, admission, action=lambda *args: calls.append(args))
    assert len(calls) == 1


def test_intervening_state_write_is_not_overwritten(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    service = app.extensions['character_state_service']
    original = service.update_spell_slots
    newer = None
    def concurrent_update(admitted, *args, **kwargs):
        nonlocal newer
        state = deepcopy(admitted.state_record.state)
        state['notes']['player_notes_markdown'] = 'Concurrent update'
        newer = service.state_store.replace_state(admitted.definition, state, expected_revision=admitted.state_record.revision, updated_by_user_id=users['dm']['id'])
        return original(admitted, *args, **kwargs)
    monkeypatch.setattr(service, 'update_spell_slots', concurrent_update)
    response = client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used='1'))
    assert response.status_code == 302
    assert ('error', CONFLICT) in _flashes(client)
    with app.app_context():
        assert service.state_store.get_state(CAMPAIGN, CHARACTER) == newer


@pytest.mark.parametrize('source', ['definition.yaml', 'import.yaml'])
@pytest.mark.parametrize('method', ['atomic', 'in-place'])
def test_new_posts_observe_same_size_same_timestamp_source_changes(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch, source, method):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    service = app.extensions['character_state_service']
    action = service.update_spell_slots
    seen = []
    def observe(admitted, *args, **kwargs):
        seen.append((admitted.definition.name, admitted.import_metadata.parser_version))
        return action(admitted, *args, **kwargs)
    monkeypatch.setattr(service, 'update_spell_slots', observe)
    repository = app.extensions['character_repository']
    load = repository._load_character
    loads = []
    def observe_load(*args, **kwargs):
        loads.append(kwargs)
        return load(*args, **kwargs)
    monkeypatch.setattr(repository, '_load_character', observe_load)
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used='1')).status_code == 302
    path = app.config['TEST_CAMPAIGNS_DIR'] / CAMPAIGN / 'characters' / CHARACTER / source
    original_stat = path.stat()
    content = path.read_bytes()
    old, new = ((b'name: Arden March', b'name: Arden Marsh') if source == 'definition.yaml'
                else (b'parser_version: fixture', b'parser_version: mixture'))
    changed = content.replace(old, new, 1)
    assert changed != content and len(changed) == len(content)
    destination = path.with_suffix('.replacement') if method == 'atomic' else path
    destination.write_bytes(changed)
    os.utime(destination, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    if method == 'atomic':
        os.replace(destination, path)
    assert (path.stat().st_size, path.stat().st_mtime_ns) == (original_stat.st_size, original_stat.st_mtime_ns)
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision + 1, used='2')).status_code == 302
    assert len(loads) == 2 and all(not call['initialize_missing_state'] for call in loads)
    assert seen[1] == (('Arden Marsh', seen[0][1]) if source == 'definition.yaml' else (seen[0][0], 'mixture'))


@pytest.mark.parametrize('stage', ['load', 'access', 'actor', 'service', 'validation', 'store-before', 'store-after', 'flash-after', 'redirect-after'])
def test_faults_preserve_precommit_no_write_and_postcommit_one_write(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch, stage):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    before = _snapshot(app)
    service = app.extensions['character_state_service']
    def fault(*args, **kwargs):
        raise RuntimeError(stage + ' fault')
    if stage == 'load':
        monkeypatch.setattr(app.extensions['character_repository'], 'get_combat_seed_character', fault)
    elif stage == 'access':
        monkeypatch.setattr(app_module, 'has_session_mode_access', fault)
    elif stage == 'actor':
        monkeypatch.setattr(app_module, 'get_current_user', fault)
    elif stage in ('service', 'validation'):
        def service_fault(*args, **kwargs):
            if stage == 'validation':
                raise CharacterStateValidationError('representative validation')
            fault()
        monkeypatch.setattr(service, 'update_spell_slots', service_fault)
    elif stage.startswith('store-'):
        original = service.state_store.replace_state
        def store_fault(*args, **kwargs):
            if stage == 'store-after':
                original(*args, **kwargs)
            fault()
        monkeypatch.setattr(service.state_store, 'replace_state', store_fault)
    elif stage == 'flash-after':
        monkeypatch.setattr(app_module, 'flash', fault)
    else:
        monkeypatch.setattr(app_module, 'redirect', fault)
    data = dict(expected_revision=record.state_record.revision, used='1')
    if stage == 'validation':
        assert client.post(ROUTE, data=data).status_code == 302
        assert ('error', 'representative validation') in _flashes(client)
    else:
        with pytest.raises(RuntimeError, match=stage + ' fault'):
            client.post(ROUTE, data=data)
    after = _snapshot(app)
    if stage in ('store-after', 'flash-after', 'redirect-after'):
        assert after[0][0][2] == before[0][0][2] + 1
        assert after[0][0][-1] == users['owner']['id']
        assert after[1] == before[1]
    else:
        assert after == before


def test_other_runner_consumers_keep_missing_state_initialization(app, client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility(CAMPAIGN, characters='players')
    sign_in(users['owner']['email'], users['owner']['password'])
    assert _snapshot(app)[0] == []
    response = client.post(ROUTE.rsplit('/', 2)[0] + '/vitals', data=dict(expected_revision='1', current_hp='20', temp_hp='0'))
    assert response.status_code == 302
    assert _snapshot(app)[0][0][2] == 2


def test_legacy_mode_and_invalid_session_return_keep_character_redirect(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    counts = _measure(app, monkeypatch)
    response = client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used=1, mode='session', page='spellcasting', return_view='invalid'))
    assert response.status_code == 302
    location = urlsplit(response.headers['Location'])
    assert location.path == f'/campaigns/{CAMPAIGN}/characters/{CHARACTER}'
    assert parse_qs(location.query) == dict(page=['spellcasting'], mode=['session'])
    assert counts == dict(load=1, action=1, replace=1, access=1)


def test_session_return_requires_session_access_even_for_character_editor(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    set_campaign_visibility(CAMPAIGN, session='private')
    counts = _measure(app, monkeypatch)
    response = client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used=1, mode='read', page='spellcasting', return_view='session-character', fragment=1), headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 302
    assert urlsplit(response.headers['Location']).path == f'/campaigns/{CAMPAIGN}/characters/{CHARACTER}'
    assert counts == dict(load=1, action=1, replace=1, access=1)


def test_missing_actor_after_access_admission_cannot_write(app, client, get_character, set_campaign_visibility, monkeypatch):
    record = get_character(CHARACTER)
    set_campaign_visibility(CAMPAIGN, characters='public')
    monkeypatch.setattr(app_module, 'has_session_mode_access', lambda *_: True)
    before = _snapshot(app)
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used=1)).status_code == 403
    assert _snapshot(app) == before


def test_next_request_reauthorizes_after_assignment_changes(app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch):
    from player_wiki.auth_store import AuthStore
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility)
    counts = _measure(app, monkeypatch)
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used=1)).status_code == 302
    with app.app_context():
        AuthStore().upsert_character_assignment(users['party']['id'], CAMPAIGN, CHARACTER)
    before = _snapshot(app)
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision + 1, used=2)).status_code == 403
    assert _snapshot(app) == before
    assert counts == dict(load=2, action=1, replace=1, access=2)


def test_selected_update_leaves_other_character_unchanged(app, client, sign_in, users, get_character, set_campaign_visibility):
    record = _seed(app, sign_in, users, get_character, set_campaign_visibility, actor='dm')
    other = get_character('selene-brook')
    before = _snapshot(app)
    assert len(before[0]) == 2
    assert client.post(ROUTE, data=dict(expected_revision=record.state_record.revision, used=1)).status_code == 302
    after = _snapshot(app)
    assert after[0][1] == before[0][1]
    assert after[0][0][2] == before[0][0][2] + 1
    assert get_character('selene-brook').state_record == other.state_record
