"""Behavioral coverage for durable ability inputs and legacy recovery."""
from copy import deepcopy

import pytest

from player_wiki.character_ability_inputs import (
    KEYS, AbilityInputRecoveryRequired, effective_scores, input_records,
    recover_inputs, recovery_rows, require_resolved_ability_inputs,
    resolve_inputs, seed_base_inputs,
)
from player_wiki.character_adjustments import apply_recoverable_stat_penalties, strip_recoverable_stat_penalties
from player_wiki.character_builder import normalize_definition_to_native_model, project_definition_with_transient_effects
from player_wiki.character_editor import apply_native_character_edits
from player_wiki.character_importer import converge_imported_definition
from tests.helpers.character_builder_fakes import _minimal_character_definition, _minimal_import_metadata


def _definition(score=8, *, explicit=True):
    definition = _minimal_character_definition()
    for key in KEYS:
        definition.stats['ability_scores'][key] = {'score': score, 'modifier': (score - 10) // 2, 'save_bonus': (score - 10) // 2}
    if explicit:
        seed_base_inputs(definition.stats, {key: score for key in KEYS}, provenance='synthetic_author')
    return definition


def _penalty(amount, key='str', identity='p1'):
    return {'id': identity, 'kind': 'ability_score', 'ability_key': key, 'amount': amount, 'source': 'Synthetic drain'}


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('score,amount', [(0, 1), (8, 8), (8, 20), (14, 2)])
def test_repeated_normalization_and_penalty_removal_preserve_exact_input(key, score, amount):
    definition = _definition(score)
    definition.stats['recoverable_penalties'] = [_penalty(amount, key)]
    expected = max(score - amount, 0)
    for _ in range(3):
        definition = normalize_definition_to_native_model(definition)
        assert effective_scores(definition.stats)[key] == expected
        assert input_records(definition.stats)[key]['score'] == score
    definition.stats['recoverable_penalties'] = []
    definition = normalize_definition_to_native_model(definition)
    assert effective_scores(definition.stats)[key] == score


def test_zero_recalculates_modifiers_saves_initiative_capacity_and_transient_projection():
    definition = normalize_definition_to_native_model(_definition(0))
    assert all(row['score'] == 0 and row['modifier'] == -5 for row in definition.stats['ability_scores'].values())
    assert definition.stats['initiative_bonus'] == -5
    projected = project_definition_with_transient_effects(definition, {'ability_score_overrides': {'str': 20}})
    assert projected.stats['ability_scores']['str']['score'] == 20
    assert input_records(projected.stats)['str']['score'] == 0
    assert normalize_definition_to_native_model(definition).stats['ability_scores']['str']['score'] == 0


def test_zero_drives_real_defenses_saves_skills_attacks_and_carrying_capacity():
    from tests.helpers.character_builder_fakes import _systems_entry

    definition = _definition(0)
    definition.stats.update(carrying_capacity=120, push_drag_lift=240)
    definition.skills = [{'name': 'Athletics', 'proficiency_level': 'proficient'}, {'name': 'Perception', 'proficiency_level': 'none'}]
    definition.proficiencies['weapons'] = ['Martial Weapons']
    definition.equipment_catalog = [{'id': 'sword', 'name': 'Longsword', 'default_quantity': 1, 'is_equipped': True}]
    fighter = _systems_entry('class', 'phb-class-fighter', 'Fighter', metadata={'proficiency': ['str', 'con']})
    normalized = normalize_definition_to_native_model(definition, resolved_class=fighter)
    assert normalized.stats['armor_class'] == 5
    assert normalized.stats['ability_scores']['str']['save_bonus'] == -3
    assert normalized.stats['ability_scores']['con']['save_bonus'] == -3
    assert normalized.stats['ability_scores']['dex']['save_bonus'] == -5
    assert {row['name']: row['bonus'] for row in normalized.skills}['Athletics'] == -3
    assert normalized.stats['passive_perception'] == 5
    assert normalized.stats['carrying_capacity'] == 0
    assert normalized.stats['push_drag_lift'] == 0
    sword = next(row for row in normalized.attacks if row['name'] == 'Longsword')
    assert sword['attack_bonus'] == -3
    assert sword['damage'].startswith('1d8-5')


def test_zero_wisdom_and_charisma_drive_casting_preparation_and_resource_minima():
    from player_wiki.character_editor import build_character_spell_management_context
    from tests.helpers.character_builder_fakes import _systems_entry, _systems_ref, _FakeSystemsService

    cleric = _systems_entry('class', 'phb-class-cleric', 'Cleric', metadata={'hit_die': {'faces': 8}, 'spellcasting_ability': 'wis', 'caster_progression': 'full', 'prepared_spells': 'level + wis'})
    definition = _definition(0)
    definition.profile.update(class_ref=_systems_ref(cleric), class_level_text='Cleric 7', classes=[{'row_id': 'class-row-1', 'class_name': 'Cleric', 'level': 7, 'systems_ref': _systems_ref(cleric)}])
    definition.spellcasting.update(spellcasting_class='Cleric', spellcasting_ability='Wisdom')
    definition.features = [{'id': 'bardic-inspiration', 'name': 'Bardic Inspiration', 'category': 'class_feature', 'source': 'PHB'}]
    service = _FakeSystemsService({'class': [cleric]}, class_progression=[])
    normalized = normalize_definition_to_native_model(definition, systems_service=service)
    assert normalized.spellcasting['spell_save_dc'] == 6
    assert normalized.spellcasting['spell_attack_bonus'] == -2
    management = build_character_spell_management_context(normalized, selected_class=cleric)
    assert management['sections'][0]['target_prepared_count'] == 2
    assert next(row for row in normalized.resource_templates if row['id'] == 'bardic-inspiration')['max'] == 1


@pytest.mark.parametrize('prepared', [False, True])
@pytest.mark.parametrize('explicit', [False, True])
def test_scoped_item_floor_reads_never_invent_legacy_inputs(prepared, explicit):
    from player_wiki.campaign_item_mechanics import build_campaign_item_mechanics_metadata
    from player_wiki.character_builder import prepare_native_derivation_foundation, normalize_definition_with_prepared_native_foundation
    from tests.helpers.character_builder_fakes import _systems_entry, _systems_ref, _build_item_catalog, _FakeSystemsService

    circlet = _systems_entry('item', 'synthetic-circlet', 'Synthetic Circlet', metadata=build_campaign_item_mechanics_metadata(title='Synthetic Circlet', body_markdown='', explicit_mechanics={'ability_score_minimums': {'int': 14}}, source_page_ref='items/circlet', review_status='approved'))
    definition = _definition(8, explicit=explicit)
    definition.stats['ability_scores']['int']['score'] = 14
    definition.equipment_catalog = [{'id': 'circlet', 'name': circlet.title, 'default_quantity': 1, 'is_equipped': True, 'is_attuned': True, 'systems_ref': _systems_ref(circlet)}]
    catalog = _build_item_catalog([circlet])
    service = _FakeSystemsService({'item': [circlet]}, class_progression=[])
    kwargs = {'derivation_components': frozenset({'sheet_entries'}), 'item_catalog': catalog, 'systems_service': service}
    if prepared:
        foundation = prepare_native_derivation_foundation(definition, **kwargs)
        scoped = normalize_definition_with_prepared_native_foundation(definition, foundation)
    else:
        scoped = normalize_definition_to_native_model(definition, **kwargs)
    assert input_records(scoped.stats) == input_records(definition.stats)
    assert effective_scores(scoped.stats)['int'] == 14
    assert not service.list_enabled_entries_calls  # Scope must not broaden into full catalogs.
    direct = normalize_definition_to_native_model(definition, item_catalog=catalog)
    via_scoped = normalize_definition_to_native_model(scoped, item_catalog=catalog)
    assert input_records(via_scoped.stats) == input_records(direct.stats)
    if explicit:
        assert input_records(via_scoped.stats)['int']['score'] == 8
    else:
        assert input_records(via_scoped.stats)['int']['stage'] == 'unresolved'
        with pytest.raises(AbilityInputRecoveryRequired):
            require_resolved_ability_inputs(via_scoped)
        via_scoped = recover_inputs(via_scoped, {'recover_ability_int': '8'})
    via_scoped.equipment_catalog = []
    assert effective_scores(normalize_definition_to_native_model(via_scoped, item_catalog=catalog).stats)['int'] == 8


def test_legacy_first_read_after_source_floor_change_still_requires_original_input():
    from dataclasses import replace
    from player_wiki.campaign_item_mechanics import build_campaign_item_mechanics_metadata
    from tests.helpers.character_builder_fakes import _systems_entry, _systems_ref, _build_item_catalog

    def metadata(minimum):
        return build_campaign_item_mechanics_metadata(title='Changing Circlet', body_markdown='', explicit_mechanics={'ability_score_minimums': {'int': minimum}}, source_page_ref='items/changing-circlet', review_status='approved')
    old_source = _systems_entry('item', 'changing-circlet', 'Changing Circlet', metadata=metadata(14))
    legacy = _definition(8, explicit=False)
    legacy.stats['ability_scores']['int']['score'] = 14
    legacy.equipment_catalog = [{'id': 'circlet', 'name': old_source.title, 'default_quantity': 1, 'is_equipped': True, 'is_attuned': True, 'systems_ref': _systems_ref(old_source)}]
    # The source changed before this legacy record ever acquired provenance.
    current_source = replace(old_source, metadata=metadata(18))
    current_catalog = _build_item_catalog([current_source])
    normalized = normalize_definition_to_native_model(legacy, item_catalog=current_catalog)
    assert effective_scores(normalized.stats)['int'] == 14
    assert input_records(normalized.stats)['int']['stage'] == 'unresolved'
    assert recovery_rows(normalized)[0]['stage'] == 'base'
    with pytest.raises(AbilityInputRecoveryRequired):
        require_resolved_ability_inputs(normalized)
    recovered = recover_inputs(normalized, {'recover_ability_int': '8'})
    assert effective_scores(normalize_definition_to_native_model(recovered, item_catalog=current_catalog).stats)['int'] == 18
    recovered.equipment_catalog = []
    assert effective_scores(normalize_definition_to_native_model(recovered, item_catalog=current_catalog).stats)['int'] == 8


@pytest.mark.parametrize('saturated', [False, True])
def test_real_capped_level_up_feat_preserves_base_when_modeled_bonuses_are_removed(saturated):
    from player_wiki.character_builder import build_native_level_up_context, build_native_level_up_character_definition
    from tests.helpers.character_builder_fakes import _systems_entry, _FakeSystemsService

    fighter = _systems_entry('class', 'phb-class-fighter', 'Fighter', metadata={'hit_die': {'faces': 10}, 'proficiency': ['str', 'con']})
    human = _systems_entry('race', 'phb-race-human', 'Human', metadata={'size': ['M'], 'speed': 30})
    background = _systems_entry('background', 'phb-background-acolyte', 'Acolyte')
    asi = _systems_entry('classfeature', 'phb-classfeature-asi', 'Ability Score Improvement', metadata={'level': 4})
    feat = _systems_entry('feat', 'phb-feat-cap-test', 'Additional Strength', metadata={'ability': [{'str': 1}], 'campaign_option': {'kind': 'feat', 'ability': [{'str': 1}]}})
    service = _FakeSystemsService({'class': [fighter], 'race': [human], 'background': [background], 'feat': [feat], 'item': [], 'spell': [], 'subclass': []}, class_progression=[{'level': 4, 'feature_rows': [{'label': asi.title, 'entry': asi, 'embedded_card': {'option_groups': []}}]}])
    definition = _definition(18)
    definition.profile['classes'][0]['level'] = 3
    definition.profile['class_level_text'] = 'Fighter 3'
    definition.features = [{'id': 'old-feat', 'name': 'Prior Strength', 'page_ref': 'mechanics/prior-strength', 'campaign_option': {'kind': 'feat', 'ability': [{'str': 2}]}}]
    if saturated:
        definition.stats['recoverable_penalties'] = [_penalty(30)]
    values = {'hp_gain': '8', 'levelup_asi_mode_1': 'feat', 'levelup_feat_1': feat.slug}
    context = build_native_level_up_context(service, 'linden-pass', definition, values)
    leveled, _, _ = build_native_level_up_character_definition('linden-pass', definition, context, values)
    for _ in range(3):
        assert input_records(leveled.stats)['str']['score'] == 18
        assert input_records(leveled.stats)['str']['fixed_bonus'] == 0
        assert effective_scores(leveled.stats)['str'] == (0 if saturated else 20)
        leveled = normalize_definition_to_native_model(leveled)
    leveled.features = []
    leveled.stats['recoverable_penalties'] = []
    assert effective_scores(normalize_definition_to_native_model(leveled).stats)['str'] == 18


@pytest.mark.parametrize('grant_path', ['automatic', 'optional'])
def test_progression_granted_modeled_feat_never_subtracts_from_fixed_input(grant_path):
    from player_wiki.character_builder import build_native_level_up_context, build_native_level_up_character_definition
    from tests.helpers.character_builder_fakes import _systems_entry, _FakeSystemsService

    fighter = _systems_entry('class', 'phb-class-fighter', 'Fighter', metadata={'hit_die': {'faces': 10}, 'proficiency': ['str', 'con']})
    human = _systems_entry('race', 'phb-race-human', 'Human', metadata={'size': ['M'], 'speed': 30})
    background = _systems_entry('background', 'phb-background-acolyte', 'Acolyte')
    grant = _systems_entry('optionalfeature' if grant_path == 'optional' else 'classfeature', 'phb-strength-training', 'Strength Training', metadata={'level': 2, 'campaign_option': {'kind': 'feat', 'ability': [{'str': 1}]}})
    if grant_path == 'optional':
        feature = _systems_entry('classfeature', 'phb-training-choice', 'Training Choice', metadata={'level': 2})
        row = {'label': feature.title, 'entry': feature, 'embedded_card': {'option_groups': [{'options': [{'label': grant.title, 'slug': grant.slug}]}]}}
        values = {'hp_gain': '8', 'levelup_class_option_1': grant.slug}
    else:
        row = {'label': grant.title, 'entry': grant, 'embedded_card': {'option_groups': []}}
        values = {'hp_gain': '8'}
    service = _FakeSystemsService({'class': [fighter], 'race': [human], 'background': [background], 'feat': [], 'optionalfeature': [grant] if grant_path == 'optional' else [], 'item': [], 'spell': [], 'subclass': []}, class_progression=[{'level': 2, 'feature_rows': [row]}])
    definition = _definition(18)
    context = build_native_level_up_context(service, 'linden-pass', definition, values)
    leveled, _, _ = build_native_level_up_character_definition('linden-pass', definition, context, values)
    assert any(row['name'] == grant.title for row in leveled.features)
    for _ in range(3):
        assert input_records(leveled.stats)['str']['score'] == 18
        assert input_records(leveled.stats)['str']['fixed_bonus'] == 0
        assert effective_scores(leveled.stats)['str'] == 19
        leveled = normalize_definition_to_native_model(leveled)
    leveled.features = [row for row in leveled.features if row['name'] != grant.title]
    assert effective_scores(normalize_definition_to_native_model(leveled).stats)['str'] == 18


def test_native_creation_automatic_modeled_feat_never_subtracts_from_fixed_input():
    from player_wiki.character_builder import build_level_one_builder_context, build_level_one_character_definition
    from tests.helpers.character_builder_fakes import _systems_entry, _FakeSystemsService

    fighter = _systems_entry('class', 'phb-class-fighter', 'Fighter', metadata={'hit_die': {'faces': 10}, 'proficiency': ['str', 'con']})
    human = _systems_entry('race', 'phb-race-human', 'Human', metadata={'size': ['M'], 'speed': 30})
    background = _systems_entry('background', 'phb-background-acolyte', 'Acolyte')
    grant = _systems_entry('classfeature', 'phb-strength-training', 'Strength Training', metadata={'level': 1, 'campaign_option': {'kind': 'feat', 'ability': [{'str': 1}]}})
    service = _FakeSystemsService({'class': [fighter], 'race': [human], 'background': [background], 'feat': [], 'item': [], 'spell': [], 'subclass': []}, class_progression=[{'level': 1, 'feature_rows': [{'label': grant.title, 'entry': grant, 'embedded_card': {'option_groups': []}}]}])
    values = {'name': 'Synthetic creation', 'class_slug': fighter.slug, 'species_slug': human.slug, 'background_slug': background.slug, **{key: '18' for key in KEYS}}
    context = build_level_one_builder_context(service, 'linden-pass', values)
    definition, _ = build_level_one_character_definition('linden-pass', context, values)
    assert any(row['name'] == grant.title for row in definition.features)
    for _ in range(3):
        assert input_records(definition.stats)['str']['score'] == 18
        assert input_records(definition.stats)['str']['fixed_bonus'] == 0
        assert effective_scores(definition.stats)['str'] == 19
        definition = normalize_definition_to_native_model(definition)
    definition.features = [row for row in definition.features if row['name'] != grant.title]
    assert effective_scores(normalize_definition_to_native_model(definition).stats)['str'] == 18


def test_same_level_fresh_source_refreshes_inputs_under_existing_precedence():
    from player_wiki.character_importer import parse_character_sheet_text

    existing = _definition(18)
    existing.source['native_progression'] = {'history': [{'kind': 'level_up', 'to_level': 1}]}
    text = '# Synthetic sheet\n\n## Sheet Summary\n\n| Field | Value |\n| --- | --- |\n| Class & Level | Fighter 1 |\n\n## Ability Scores\n\n| Ability | Score | Modifier | Save |\n| --- | --- | --- | --- |\n| Strength | 6 | -2 | -2 |\n'
    fresh, _ = parse_character_sheet_text('linden-pass', text, source_path='synthetic.md', source_type='markdown_character_sheet', imported_from='Synthetic sheet', character_slug=existing.character_slug)
    assert fresh.profile['classes'][0]['level'] == 1
    refreshed = converge_imported_definition(fresh, existing_definition=existing)
    for _ in range(3):
        assert input_records(refreshed.stats)['str']['score'] == 6
        assert input_records(refreshed.stats)['str']['provenance'] == 'fresh_imported_source'
        assert effective_scores(refreshed.stats)['str'] == 6
        refreshed = normalize_definition_to_native_model(refreshed)


def test_structured_retraining_changes_layer_without_changing_author_input():
    from player_wiki.character_editor import apply_native_character_retraining, build_native_character_retraining_context
    from tests.helpers.character_builder_fakes import _campaign_page_record

    option = {'kind': 'feat', 'name': 'Focused Training', 'ability': [{'choose': {'from': ['str', 'dex'], 'count': 1}}]}
    page = _campaign_page_record('mechanics/focused-training', 'Focused Training', section='Mechanics', subsection='Feats', metadata={'character_option': option})
    values = {'custom_feature_page_ref_1': page.page_ref, 'custom_feature_activation_type_1': 'passive', 'feat_campaign-option-feat-custom-feature-focused-training_ability_1': 'str'}
    definition, metadata, _ = apply_native_character_edits('linden-pass', _definition(8), _minimal_import_metadata(), campaign_page_records=[page], form_values=values)
    assert effective_scores(definition.stats)['str'] == 9
    context = build_native_character_retraining_context(definition, campaign_page_records=[page])
    field = next(field for row in context['feature_rows'] for field in row['choice_fields'] if field['name'].endswith('_ability_1'))
    retrained, _, _ = apply_native_character_retraining('linden-pass', definition, metadata, campaign_page_records=[page], form_values={field['name']: 'dex'})
    for _ in range(3):
        assert effective_scores(retrained.stats)['str'] == 8
        assert effective_scores(retrained.stats)['dex'] == 9
        assert input_records(retrained.stats)['str']['score'] == input_records(retrained.stats)['dex']['score'] == 8
        assert input_records(retrained.stats)['dex']['provenance'] == 'synthetic_author'
        retrained = normalize_definition_to_native_model(retrained)
    retrained.features = []
    assert effective_scores(normalize_definition_to_native_model(retrained).stats)['dex'] == 8


def test_low_level_apply_strip_restores_actual_value_after_saturation():
    stats = _definition(3, explicit=False).stats
    penalized = apply_recoverable_stat_penalties(stats, [_penalty(20)])
    assert effective_scores(penalized)['str'] == 0
    repeated = apply_recoverable_stat_penalties(penalized, [_penalty(20)])
    assert effective_scores(repeated)['str'] == 0
    restored, _ = strip_recoverable_stat_penalties(repeated)
    assert effective_scores(restored)['str'] == 3


@pytest.mark.parametrize('payload', [3, {'score': 3, 'modifier': -4, 'save_bonus': -2}])
def test_saturated_restoration_keeps_every_short_and_long_alias_consistent(payload):
    stats = {'ability_scores': {'str': deepcopy(payload), 'strength': deepcopy(payload)}}
    adjusted = apply_recoverable_stat_penalties(stats, [_penalty(20)])
    restored, _ = strip_recoverable_stat_penalties(adjusted)
    assert restored['ability_scores'] == stats['ability_scores']


def test_zero_skill_bonus_is_preserved_in_all_passives():
    definition = _definition(0)
    definition.profile['classes'][0]['level'] = 13
    definition.profile['class_level_text'] = 'Fighter 13'
    definition.skills = [{'name': name, 'proficiency_level': 'proficient'} for name in ('Perception', 'Insight', 'Investigation')]
    normalized = normalize_definition_to_native_model(definition)
    assert normalized.stats['proficiency_bonus'] == 5
    assert all(row['bonus'] == 0 for row in normalized.skills if row['name'] in {'Perception', 'Insight', 'Investigation'})
    for name in ('perception', 'insight', 'investigation'):
        assert normalized.stats[f'passive_{name}'] == 10


def test_editor_stacking_reduction_clearing_and_other_adjustments_are_idempotent():
    definition = _definition(3)
    metadata = _minimal_import_metadata()
    values = {'recoverable_penalty_source_1': 'Drain', 'recoverable_penalty_target_1': 'ability_score:str', 'recoverable_penalty_amount_1': '20', 'stat_adjustment_initiative_bonus': '2'}
    definition, metadata, _ = apply_native_character_edits('linden-pass', definition, metadata, form_values=values)
    assert effective_scores(definition.stats)['str'] == 0
    values.update(recoverable_penalty_source_2='Other drain', recoverable_penalty_target_2='ability_score:str', recoverable_penalty_amount_2='10')
    definition, metadata, _ = apply_native_character_edits('linden-pass', definition, metadata, form_values=values)
    assert effective_scores(definition.stats)['str'] == 0
    definition, metadata, _ = apply_native_character_edits('linden-pass', definition, metadata, form_values={})
    assert effective_scores(definition.stats)['str'] == 3
    assert not definition.stats.get('recoverable_penalties')


def test_legacy_saturated_read_is_stable_and_only_explicit_recovery_permits_save():
    definition = _definition(8, explicit=False)
    definition.stats['ability_scores']['str']['score'] = 0
    definition.stats['recoverable_penalties'] = [_penalty(20)]
    normalized = normalize_definition_to_native_model(definition)
    assert effective_scores(normalized.stats)['str'] == 0
    assert [row['key'] for row in recovery_rows(normalized)] == ['str']
    with pytest.raises(AbilityInputRecoveryRequired):
        require_resolved_ability_inputs(normalized)
    with pytest.raises(AbilityInputRecoveryRequired):
        apply_native_character_edits('linden-pass', definition, _minimal_import_metadata(), form_values={})
    recovered, _, _ = apply_native_character_edits('linden-pass', definition, _minimal_import_metadata(), form_values={'recover_ability_str': '0'})
    assert effective_scores(recovered.stats)['str'] == 0
    assert effective_scores(recovered.stats)['dex'] == 8
    require_resolved_ability_inputs(recovered)


@pytest.mark.parametrize('value', ['', '-1', '1.5', 'nan', 'True', '١'])
def test_recovery_requires_explicit_nonnegative_whole_number(value):
    definition = _definition(0, explicit=False)
    definition.stats['recoverable_penalties'] = [_penalty(20)]
    with pytest.raises(AbilityInputRecoveryRequired):
        recover_inputs(normalize_definition_to_native_model(definition), {'recover_ability_str': value})


@pytest.mark.parametrize('corrupt', [{'fixed_bonus': []}, {'layers': []}, {'layers': {'bonus': 'bad'}}, {'score': True}, {'pre_penalty': 'bad'}])
def test_malformed_provenance_never_breaks_read(corrupt):
    definition = _definition(8)
    definition.stats['ability_inputs']['scores']['str'].update(corrupt)
    assert normalize_definition_to_native_model(definition).stats['ability_scores']['str']['score'] == 8


def test_output_disagreement_is_not_a_manual_input_and_explicit_new_input_wins():
    definition = normalize_definition_to_native_model(_definition(8))
    definition.stats['ability_scores']['str']['score'] = 25
    assert effective_scores(normalize_definition_to_native_model(definition).stats)['str'] == 8
    seed_base_inputs(definition.stats, {key: 0 for key in KEYS}, provenance='explicit_source_change')
    assert effective_scores(normalize_definition_to_native_model(definition).stats)['str'] == 0


def test_known_inputs_survive_floor_changes_and_reimport_without_stacking():
    stats = _definition(8).stats
    values, records = resolve_inputs(stats, bonuses={'str': 2}, minimums={'str': 14})
    assert values['str'] == 14
    stats['ability_inputs']['scores'] = records
    assert resolve_inputs(stats, bonuses={'str': 2}, minimums={'str': 18})[0]['str'] == 18
    assert resolve_inputs(stats, bonuses={}, minimums={})[0]['str'] == 8
    definition = _definition(8)
    definition.stats['recoverable_penalties'] = [_penalty(20)]
    for _ in range(3):
        definition = converge_imported_definition(definition, existing_definition=definition)
        assert effective_scores(definition.stats)['str'] == 0
    definition.stats['recoverable_penalties'] = []
    assert effective_scores(converge_imported_definition(definition).stats)['str'] == 8


def test_legacy_floor_recovery_requests_true_base_and_can_remove_floor():
    definition = _definition(14, explicit=False)
    values, records = resolve_inputs(definition.stats, bonuses={}, minimums={'str': 14})
    definition.stats['ability_inputs'] = {'version': 1, 'scores': records}
    row = recovery_rows(definition)[0]
    assert row['stage_label'] == 'before ability bonuses and minimums'
    recovered = recover_inputs(definition, {'recover_ability_str': '8'})
    assert resolve_inputs(recovered.stats, bonuses={}, minimums={})[0]['str'] == 8


def test_xianxia_passes_through_unchanged():
    definition = _definition(0, explicit=False)
    definition.system = 'Xianxia'
    definition.stats['recoverable_penalties'] = [_penalty(20)]
    assert normalize_definition_to_native_model(definition).stats == definition.stats
    assert 'ability_inputs' not in normalize_definition_to_native_model(definition).stats
    require_resolved_ability_inputs(definition)


@pytest.mark.parametrize('raw', [8, 21])
def test_real_native_creation_keeps_raw_input_before_modeled_feat_and_floor(raw):
    from player_wiki.character_builder import build_level_one_builder_context, build_level_one_character_definition
    from tests.helpers.character_builder_fakes import _FakeSystemsService, _systems_entry

    fighter = _systems_entry('class', 'phb-class-fighter', 'Fighter', metadata={'hit_die': {'faces': 10}, 'proficiency': ['str', 'con']})
    human = _systems_entry('race', 'phb-race-human', 'Human', metadata={'size': ['M'], 'speed': 30, 'feats': [{'any': 1}]})
    background = _systems_entry('background', 'phb-background-acolyte', 'Acolyte')
    feat = _systems_entry('feat', 'phb-feat-test', 'Synthetic Strength', metadata={'ability': [{'str': 2}], 'campaign_option': {'kind': 'feat', 'ability': [{'str': 2}]}})
    floor = _systems_entry('classfeature', 'phb-classfeature-floor', 'Synthetic Floor', metadata={'level': 1, 'campaign_option': {'kind': 'feature', 'mechanic_effects': [{'kind': 'ability_minimum', 'ability': 'str', 'minimum': 24}]}})
    service = _FakeSystemsService({'class': [fighter], 'race': [human], 'background': [background], 'feat': [feat], 'subclass': [], 'item': [], 'spell': []}, class_progression=[{'level': 1, 'level_label': 'Level 1', 'feature_rows': [{'label': floor.title, 'entry': floor, 'embedded_card': {'option_groups': []}}]}])
    values = {'name': 'Synthetic creator', 'class_slug': fighter.slug, 'species_slug': human.slug, 'background_slug': background.slug, 'species_feat_1': feat.slug, **{key: str(raw if key == 'str' else 10) for key in KEYS}}
    context = build_level_one_builder_context(service, 'linden-pass', values)
    definition, _ = build_level_one_character_definition('linden-pass', context, values)
    assert input_records(definition.stats)['str']['score'] == raw
    assert input_records(definition.stats)['str']['fixed_bonus'] == 0
    assert effective_scores(definition.stats)['str'] == 24
    definition.features = [row for row in definition.features if row['name'] != floor.title]
    definition = normalize_definition_to_native_model(definition)
    assert effective_scores(definition.stats)['str'] == min(raw + 2, 20)
    definition.features = [row for row in definition.features if row['name'] != feat.title]
    assert effective_scores(normalize_definition_to_native_model(definition).stats)['str'] == raw


def test_fresh_parser_seeds_only_explicit_source_scores_and_reimport_keeps_newer_progression():
    from player_wiki.character_importer import parse_character_sheet_text

    text = '# Synthetic sheet\n\n## Ability Scores\n\n| Ability | Score | Modifier | Save |\n| --- | --- | --- | --- |\n| Strength | 0 | -5 | -5 |\n'
    imported, _ = parse_character_sheet_text('linden-pass', text, source_path='synthetic.md', source_type='markdown_character_sheet', imported_from='Synthetic sheet', character_slug='new-hero')
    assert input_records(imported.stats)['str']['score'] == 0
    assert input_records(imported.stats)['str']['provenance'] == 'fresh_imported_source'
    assert input_records(imported.stats)['dex']['provenance'] != 'fresh_imported_source'
    imported.features = [{'id': 'feat', 'name': 'Source overlay', 'page_ref': 'mechanics/source-overlay', 'campaign_option': {'kind': 'feat', 'ability': [{'str': 2}]}}]
    for _ in range(3):
        imported = converge_imported_definition(imported)
        assert effective_scores(imported.stats)['str'] == 2
    existing = _definition(18)
    existing.profile['classes'][0]['level'] = 4
    existing.profile['class_level_text'] = 'Fighter 4'
    existing.source['native_progression'] = {'history': [{'kind': 'level_up', 'to_level': 4}]}
    merged = converge_imported_definition(imported, existing_definition=existing)
    assert input_records(merged.stats)['str']['score'] == 18
