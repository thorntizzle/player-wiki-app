"""Real transport/publication contracts for unresolved legacy abilities."""
from copy import deepcopy
from io import BytesIO
import pytest

from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.helpers.character_state_helpers import _read_character_definition, _write_character_definition
from tests.test_api_character_portrait_mutation_route_transport import _payload as portrait_payload, TINY_PNG

SLUG = 'arden-march'
PAGE = '/campaigns/linden-pass/characters/arden-march'
API = '/api/v1/campaigns/linden-pass/characters/arden-march'
CONTENT = '/api/v1/campaigns/linden-pass/content/characters/arden-march'


def legacy_character(app, *, two_abilities=False):
    def mutate(payload):
        stats = payload['stats']
        stats.pop('ability_inputs', None)
        stats['ability_scores']['str'] = {'score': 0, 'modifier': -5, 'save_bonus': -5}
        stats['recoverable_penalties'] = [{'id': 'legacy-drain', 'kind': 'ability_score', 'ability_key': 'str', 'amount': 20, 'source': 'Synthetic legacy drain'}]
        if two_abilities:
            stats['ability_scores']['dex'] = {'score': 0, 'modifier': -5, 'save_bonus': -5}
            stats['recoverable_penalties'].append({'id': 'legacy-dex-drain', 'kind': 'ability_score', 'ability_key': 'dex', 'amount': 20, 'source': 'Synthetic second drain'})
    _write_character_definition(app, SLUG, mutate)


def test_api_recovery_refusal_validation_conflict_and_success(app, client, users, get_character):
    legacy_character(app)
    headers = api_headers(issue_api_token(app, users['dm']['email']))
    before = _read_character_definition(app, SLUG)
    revision = get_character(SLUG).state_record.revision
    assert client.get(PAGE).status_code in (200, 302)
    url = API + '/advanced-editor'
    for values in ({}, {'recover_ability_str': '-1'}, {'recover_ability_str': '1.5'}):
        response = client.put(url, headers=headers, json={'expected_revision': revision, 'values': values})
        assert response.status_code == 400
        assert _read_character_definition(app, SLUG) == before
        assert get_character(SLUG).state_record.revision == revision
    response = client.put(url, headers=headers, json={'expected_revision': revision - 1, 'values': {'recover_ability_str': '8'}})
    assert response.status_code == 409
    assert _read_character_definition(app, SLUG) == before
    response = client.put(url, headers=headers, json={'expected_revision': revision, 'values': {'recover_ability_str': '8'}})
    assert response.status_code == 200
    record = get_character(SLUG)
    assert record.state_record.revision == revision + 1
    assert record.definition.stats['ability_scores']['str']['score'] == 8
    assert record.definition.stats['ability_scores']['dex']['score'] == before['stats']['ability_scores']['dex']['score']


def test_legacy_notes_and_portraits_stay_available_without_changing_inputs(app, client, users, sign_in, get_character):
    legacy_character(app)
    headers = api_headers(issue_api_token(app, users['dm']['email']))
    before_stats = deepcopy(_read_character_definition(app, SLUG)['stats'])
    revision = get_character(SLUG).state_record.revision
    response = client.patch(API + '/sheet-edit', headers=headers, json={'expected_revision': revision, 'notes': {'player_notes_markdown': 'Still writable'}})
    assert response.status_code == 200
    revision = get_character(SLUG).state_record.revision
    response = client.put(API + '/portrait', headers=headers, json=portrait_payload(revision))
    assert response.status_code == 200
    assert _read_character_definition(app, SLUG)['stats'] == before_stats
    sign_in(users['dm']['email'], users['dm']['password'])
    revision = get_character(SLUG).state_record.revision
    response = client.post(PAGE + '/personal/portrait', data={'expected_revision': str(revision), 'portrait_file': (BytesIO(TINY_PNG), 'portrait.png'), 'portrait_caption': 'Independent caption'}, content_type='multipart/form-data')
    assert response.status_code == 302
    assert get_character(SLUG).state_record.revision == revision + 1
    assert _read_character_definition(app, SLUG)['stats'] == before_stats


@pytest.mark.parametrize('transport', ['browser', 'api'])
@pytest.mark.parametrize('operation', ['upsert', 'remove'])
@pytest.mark.parametrize('unresolved', [False, True])
def test_portrait_preparation_recovers_only_missing_links_and_preserves_durable_data(
    app, client, users, sign_in, get_character, transport, operation, unresolved,
):
    from tests.helpers.character_state_helpers import _write_character_state
    from tests.helpers.systems_seed_helpers import _seed_systems_item_entry
    from player_wiki.character_models import CharacterDefinition
    from player_wiki.character_service import merge_state_with_definition

    chain_entry = _seed_systems_item_entry(app, slug='phb-item-chain-mail', title='Chain Mail', metadata={'type': 'HA', 'ac': 16})
    _seed_systems_item_entry(app, slug='phb-item-stormglass-compass', title='Stormglass Compass', metadata={})
    page_path = app.config['TEST_CAMPAIGNS_DIR'] / 'linden-pass/content/items/stormglass-compass.md'
    page_path.write_text(page_path.read_text(encoding='utf-8').replace('This brass', '*Wondrous item, rare*\n\nThis brass'), encoding='utf-8')
    with app.app_context():
        app.extensions['campaign_page_store'].sync_campaign_pages('linden-pass', page_path.parents[1])
    if unresolved:
        legacy_character(app, two_abilities=True)
    sign_in(users['dm']['email'], users['dm']['password'])
    headers = api_headers(issue_api_token(app, users['dm']['email']))
    if operation == 'remove':
        response = client.put(API + '/portrait', headers=headers, json=portrait_payload(get_character(SLUG).state_record.revision))
        assert response.status_code == 200

    explicit_ref = {'slug': 'explicit-identity', 'title': 'Author title', 'entry_type': 'item', 'source_id': 'OTHER'}
    def equipment(payload):
        payload['equipment_catalog'] = [
            {'id': 'chain-mail-authored', 'name': 'Chain Mail', 'default_quantity': 2, 'is_equipped': True,
             'is_attuned': True, 'charges_current': 3, 'charges_max': 7, 'notes': 'Preserve  spacing',
             'systems_ref': None, 'page_ref': None},
            {'id': 'chain-mail-second', 'name': 'Chain Mail', 'default_quantity': 4, 'systems_ref': deepcopy(explicit_ref)},
            {'id': 'page-explicit', 'name': 'Chain Mail', 'default_quantity': 1, 'page_ref': 'items/stormglass-compass'},
            {'id': 'page-recovered', 'name': 'Stormglass Compass', 'default_quantity': 1},
            {'id': 'no-match', 'name': 'Synthetic unmatched heirloom', 'default_quantity': 1},
        ]
    _write_character_definition(app, SLUG, equipment)
    # Establish a canonical durable definition and matching inventory before the
    # portrait action, rather than leaving state from the fixture's old rows.
    definition = CharacterDefinition.from_dict(_read_character_definition(app, SLUG))
    canonical = definition.to_dict()
    _write_character_definition(app, SLUG, lambda payload: (payload.clear(), payload.update(deepcopy(canonical))))
    def seed_state(state):
        merged = merge_state_with_definition(definition, state)
        merged['inventory'][0].update(quantity=5, charges_current=1)
        state.clear()
        state.update(merged)
    _write_character_state(app, SLUG, seed_state)
    before = _read_character_definition(app, SLUG)
    prior_record = get_character(SLUG)
    before_state = deepcopy(prior_record.state_record.state)
    revision = prior_record.state_record.revision
    if transport == 'api':
        response = (client.put(API + '/portrait', headers=headers, json=portrait_payload(revision))
                    if operation == 'upsert' else client.delete(API + '/portrait', headers=headers, json={'expected_revision': revision}))
        assert response.status_code == 200, response.get_json()
    else:
        data = {'expected_revision': str(revision), 'mode': 'read', 'page': 'portrait'}
        if operation == 'upsert':
            data.update(portrait_file=(BytesIO(TINY_PNG), 'portrait.png'), portrait_caption='Independent portrait')
        response = client.post(PAGE + '/personal/portrait' + ('/remove' if operation == 'remove' else ''),
                               data=data, content_type='multipart/form-data')
        assert response.status_code == 302
    after = _read_character_definition(app, SLUG)
    record = get_character(SLUG)
    assert record.state_record.revision == revision + 1
    assert record.state_record.state == before_state
    expected = deepcopy(before)
    for key in ('portrait_asset_ref', 'portrait_alt', 'portrait_caption'):
        if key in after['profile']:
            expected['profile'][key] = after['profile'][key]
        else:
            expected['profile'].pop(key, None)
    expected['equipment_catalog'][0]['systems_ref'] = {
        'slug': 'phb-item-chain-mail', 'title': 'Chain Mail', 'entry_type': 'item', 'source_id': 'PHB',
        'entry_key': chain_entry.entry_key,
    }
    expected['equipment_catalog'][3]['page_ref'] = {'slug': 'items/stormglass-compass', 'title': 'Stormglass Compass'}
    assert after == expected
    assert after['equipment_catalog'][1]['systems_ref'] == explicit_ref
    assert after['equipment_catalog'][2]['page_ref'] == 'items/stormglass-compass'
    assert not after['equipment_catalog'][3].get('systems_ref')
    assert not after['equipment_catalog'][4].get('systems_ref')
    if operation == 'remove':
        assert not after['profile'].get('portrait_asset_ref')
    else:
        assert after['profile']['portrait_asset_ref'].endswith('/portrait.webp')


def test_content_cosmetic_write_allowed_but_unknown_mechanics_rejected(app, client, users, get_character):
    legacy_character(app)
    get_character(SLUG)  # Establish the existing fixture's SQLite state first.
    headers = api_headers(issue_api_token(app, users['dm']['email']))
    original = _read_character_definition(app, SLUG)
    changed = deepcopy(original)
    changed['reference_notes']['additional_notes_markdown'] = 'Cosmetic file edit'
    response = client.put(CONTENT, headers=headers, json={'definition': changed})
    assert response.status_code == 200, response.get_json()
    baseline = _read_character_definition(app, SLUG)
    revision = get_character(SLUG).state_record.revision
    changed = deepcopy(baseline)
    changed['stats']['recoverable_penalties'] = []
    response = client.put(CONTENT, headers=headers, json={'definition': changed})
    assert response.status_code == 400
    assert _read_character_definition(app, SLUG) == baseline
    assert get_character(SLUG).state_record.revision == revision


def test_unresolved_equipment_write_refused_before_publication(app, client, users, sign_in, get_character):
    legacy_character(app)
    sign_in(users['dm']['email'], users['dm']['password'])
    before = _read_character_definition(app, SLUG)
    revision = get_character(SLUG).state_record.revision
    response = client.post(PAGE + '/equipment/add-manual', data={'expected_revision': str(revision), 'name': 'Synthetic rope', 'quantity': '1'})
    assert response.status_code == 302
    assert _read_character_definition(app, SLUG) == before
    assert get_character(SLUG).state_record.revision == revision


@pytest.mark.parametrize('change', ['subclass_ref', 'native_progression', 'source_type'])
def test_content_mechanical_discriminators_refuse_unresolved_inputs_before_publication(app, client, users, get_character, change):
    legacy_character(app)
    def fallback_profile(payload):
        payload['profile']['classes'][0].pop('subclass_ref', None)
        payload['profile'].pop('subclass_ref', None)
    _write_character_definition(app, SLUG, fallback_profile)
    revision = get_character(SLUG).state_record.revision
    original = _read_character_definition(app, SLUG)
    changed = deepcopy(original)
    if change == 'subclass_ref':
        changed['profile']['subclass_ref'] = {'entry_type': 'subclass', 'title': 'Eldritch Knight', 'slug': 'phb-subclass-eldritch-knight', 'source_id': 'PHB'}
        from player_wiki.character_profile import profile_primary_subclass_ref
        assert profile_primary_subclass_ref(changed['profile']) == changed['profile']['subclass_ref']
    elif change == 'native_progression':
        changed['source']['native_progression'] = {'hp_baseline': {'level': 1, 'max_hp': 99}}
    else:
        changed['source']['source_type'] = 'native_character_builder'
        assert changed['source']['source_type'] != original['source'].get('source_type')
    headers = api_headers(issue_api_token(app, users['dm']['email']))
    response = client.put(CONTENT, headers=headers, json={'definition': changed})
    assert response.status_code == 400, response.get_json()
    assert _read_character_definition(app, SLUG) == original
    assert get_character(SLUG).state_record.revision == revision


def test_content_source_bookkeeping_remains_available_for_unresolved_inputs(app, client, users, get_character):
    legacy_character(app)
    get_character(SLUG)
    changed = _read_character_definition(app, SLUG)
    stats = deepcopy(changed['stats'])
    changed['source']['imported_from'] = 'Updated source description'
    headers = api_headers(issue_api_token(app, users['dm']['email']))
    response = client.put(CONTENT, headers=headers, json={'definition': changed})
    assert response.status_code == 200, response.get_json()
    assert _read_character_definition(app, SLUG)['stats'] == stats


@pytest.mark.parametrize('invalid', ['', '-1'])
def test_two_ability_partial_recovery_never_publishes_valid_subset(app, client, users, get_character, invalid):
    legacy_character(app, two_abilities=True)
    original = _read_character_definition(app, SLUG)
    revision = get_character(SLUG).state_record.revision
    headers = api_headers(issue_api_token(app, users['dm']['email']))
    response = client.put(API + '/advanced-editor', headers=headers, json={'expected_revision': revision, 'values': {'recover_ability_str': '8', 'recover_ability_dex': invalid, 'additional_notes_markdown': 'Retained draft'}})
    assert response.status_code == 400
    assert _read_character_definition(app, SLUG) == original
    assert get_character(SLUG).state_record.revision == revision
