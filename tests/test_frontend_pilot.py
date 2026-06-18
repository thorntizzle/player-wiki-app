from pathlib import Path
import re


def test_gen2_topbar_account_controls_use_flask_chrome_classes_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    account_row = re.search(r'<div className="account-row">([\s\S]*?)</div>', source)
    assert account_row is not None

    account_controls_markup = account_row.group(1)
    assert 'className="header-link" href="/app-next/admin"' in account_controls_markup
    assert 'className="header-link" href="/app-next/account"' in account_controls_markup
    assert '<span className="meta">Admin</span>' in account_controls_markup
    assert re.search(r'<button type="submit" className="ghost-button">\s*Sign out\s*</button>', account_controls_markup) is not None
    assert re.search(r'<a className="ghost-button" href=\{signInHref\}>\s*Sign in\s*</a>', account_controls_markup) is not None
    assert "button button-secondary" not in account_controls_markup


def test_frontend_pilot_routes_are_closed(client, app, tmp_path):
    dist_dir = tmp_path / "frontend-dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<!doctype html><html><body>pilot</body></html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('pilot')", encoding="utf-8")

    app.config["APP_NEXT_DIST_DIR"] = dist_dir

    bare_response = client.get("/app-next")
    assert bare_response.status_code == 404

    response = client.get("/app-next/")
    assert response.status_code == 404

    asset_response = client.get("/app-next/assets/app.js")
    assert asset_response.status_code == 404

    route_response = client.get("/app-next/campaigns/linden-pass/session")
    assert route_response.status_code == 404

    account_route_response = client.get("/app-next/account")
    assert account_route_response.status_code == 404

    admin_route_response = client.get("/app-next/admin")
    assert admin_route_response.status_code == 404

    admin_user_route_response = client.get("/app-next/admin/users/1")
    assert admin_user_route_response.status_code == 404

    help_route_response = client.get("/app-next/campaigns/linden-pass/help")
    assert help_route_response.status_code == 404

    control_route_response = client.get("/app-next/campaigns/linden-pass/control")
    assert control_route_response.status_code == 404

    character_route_response = client.get("/app-next/campaigns/linden-pass/characters/arden-march")
    assert character_route_response.status_code == 404

    character_editor_route_response = client.get("/app-next/campaigns/linden-pass/characters/arden-march/edit")
    assert character_editor_route_response.status_code == 404

    character_level_up_route_response = client.get("/app-next/campaigns/linden-pass/characters/arden-march/level-up")
    assert character_level_up_route_response.status_code == 404

    character_retraining_route_response = client.get("/app-next/campaigns/linden-pass/characters/arden-march/retraining")
    assert character_retraining_route_response.status_code == 404

    character_progression_repair_route_response = client.get(
        "/app-next/campaigns/linden-pass/characters/arden-march/progression-repair"
    )
    assert character_progression_repair_route_response.status_code == 404

    character_cultivation_route_response = client.get(
        "/app-next/campaigns/linden-pass/characters/arden-march/cultivation"
    )
    assert character_cultivation_route_response.status_code == 404

    combat_route_response = client.get("/app-next/campaigns/linden-pass/combat")
    assert combat_route_response.status_code == 404

    dm_content_route_response = client.get("/app-next/campaigns/linden-pass/dm-content")
    assert dm_content_route_response.status_code == 404

    systems_route_response = client.get("/app-next/campaigns/linden-pass/systems")
    assert systems_route_response.status_code == 404

    systems_source_route_response = client.get("/app-next/campaigns/linden-pass/systems/sources/MM")
    assert systems_source_route_response.status_code == 404

    systems_category_route_response = client.get("/app-next/campaigns/linden-pass/systems/sources/MM/types/monster")
    assert systems_category_route_response.status_code == 404

    systems_entry_route_response = client.get("/app-next/campaigns/linden-pass/systems/entries/goblin")
    assert systems_entry_route_response.status_code == 404

    missing_asset_response = client.get("/app-next/assets/missing.js")
    assert missing_asset_response.status_code == 404


def test_frontend_pilot_without_build_returns_not_found(client, app, tmp_path):
    # Avoid inheriting temp values from earlier test cases.
    app.config["APP_NEXT_DIST_DIR"] = tmp_path / "missing-frontend-dist"
    response = client.get("/app-next/")
    assert response.status_code == 404


def test_admin_user_detail_action_button_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    admin_user_detail_start = source.index("function AdminUserDetailPage() {")
    admin_user_detail_end = source.index("function AccountSettingsPage()", admin_user_detail_start)
    admin_user_detail_source = source[admin_user_detail_start:admin_user_detail_end]

    remove_on_click = 'onClick={() => removeMembership.mutate(membership)}'
    clear_on_click = 'onClick={() => removeAssignment.mutate(assignment)}'
    disable_on_click = 'onClick={() => disableUser.mutate()}'

    remove_start = admin_user_detail_source.rfind("<button", 0, admin_user_detail_source.index(remove_on_click))
    remove_end = admin_user_detail_source.index("</button>", remove_start) + len("</button>")
    remove_button_block = admin_user_detail_source[remove_start:remove_end]
    assert "className=\"button\"" in remove_button_block
    assert "className=\"button button-secondary\"" not in remove_button_block

    clear_start = admin_user_detail_source.rfind("<button", 0, admin_user_detail_source.index(clear_on_click))
    clear_end = admin_user_detail_source.index("</button>", clear_start) + len("</button>")
    clear_button_block = admin_user_detail_source[clear_start:clear_end]
    assert "className=\"button\"" in clear_button_block
    assert "className=\"button button-secondary\"" not in clear_button_block

    disable_start = admin_user_detail_source.rfind("<button", 0, admin_user_detail_source.index(disable_on_click))
    disable_end = admin_user_detail_source.index("</button>", disable_start) + len("</button>")
    disable_button_block = admin_user_detail_source[disable_start:disable_end]
    assert "className=\"button\"" in disable_button_block
    assert "className=\"button button-secondary\"" not in disable_button_block


def test_combat_action_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    combat_page_start = source.index("function CombatPage() {")
    campaign_combat_route_start = source.index("const campaignCombatRoute", combat_page_start)
    combat_page_source = source[combat_page_start:campaign_combat_route_start]

    remove_on_click = "onClick={() => deleteCombatantMutation.mutate()}"
    clear_on_click = "onClick={() => clearCombatMutation.mutate()}"

    remove_button_start = combat_page_source.rfind("<button", 0, combat_page_source.index(remove_on_click))
    remove_button_end = combat_page_source.index("</button>", remove_button_start) + len("</button>")
    remove_button_block = combat_page_source[remove_button_start:remove_button_end]
    assert 'className="ghost-button"' in remove_button_block
    assert "className=\"button button-secondary\"" not in remove_button_block
    assert "onClick={() => deleteCombatantMutation.mutate()}" in remove_button_block

    clear_button_start = combat_page_source.rfind("<button", 0, combat_page_source.index(clear_on_click))
    clear_button_end = combat_page_source.index("</button>", clear_button_start) + len("</button>")
    clear_button_block = combat_page_source[clear_button_start:clear_button_end]
    assert 'className="ghost-button"' in clear_button_block
    assert "className=\"button button-secondary\"" not in clear_button_block
    assert "onClick={() => clearCombatMutation.mutate()}" in clear_button_block


def test_combat_dm_controls_add_and_cleanup_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    combat_page_start = source.index("function CombatPage() {")
    campaign_combat_route_start = source.index("const campaignCombatRoute", combat_page_start)
    combat_page_source = source[combat_page_start:campaign_combat_route_start]

    add_heading_index = combat_page_source.index("<h2>Add combatant</h2>")
    add_card_start = combat_page_source.rfind('<section className="card sidebar-card">', 0, add_heading_index)
    add_card_end = combat_page_source.index("</section>", add_heading_index) + len("</section>")
    add_card_markup = combat_page_source[add_card_start:add_card_end]

    assert add_card_start >= 0
    assert add_card_markup.count('<section className="card sidebar-card">') == 1
    assert 'className="combat-add-combatant-mode-switcher"' in add_card_markup
    assert 'role="radiogroup"' in add_card_markup
    assert 'aria-label="Add combatant type"' in add_card_markup
    assert 'className="combat-add-combatant-mode-toggle"' in add_card_markup
    assert '<label className="ghost-button" htmlFor="combat-add-mode-player">' in add_card_markup
    assert '<label className="ghost-button" htmlFor="combat-add-mode-custom">' in add_card_markup
    assert "combat-add-combatant-mode-panel combat-add-combatant-mode-panel--player" in add_card_markup
    assert 'combat-add-combatant-mode-panel--systems' in add_card_markup
    assert 'combat-add-combatant-mode-panel--dm-content' in add_card_markup
    assert 'combat-add-combatant-mode-panel--custom' in add_card_markup
    assert 'className="field">' in add_card_markup
    assert '<span>Character</span>' in add_card_markup
    assert '<span>Search monsters</span>' in add_card_markup
    assert '<span>Statblock</span>' in add_card_markup
    assert '<span>Display name</span>' in add_card_markup
    assert '<span>Name</span>' in add_card_markup
    assert 'className="stack-form"' in add_card_markup
    assert 'combat-inline-form' not in add_card_markup
    assert 'className="chat-label"' not in add_card_markup
    assert '<h3>Add PC</h3>' not in add_card_markup
    assert '<h3>Add NPC</h3>' not in add_card_markup
    assert '<h3>Add Statblock</h3>' not in add_card_markup
    assert '<h3>Add Systems Monster</h3>' not in add_card_markup

    cleanup_heading_index = combat_page_source.index("<h2>Encounter cleanup</h2>")
    cleanup_card_start = combat_page_source.rfind('<section className="card sidebar-card">', 0, cleanup_heading_index)
    cleanup_card_end = combat_page_source.index("</section>", cleanup_heading_index) + len("</section>")
    cleanup_card_markup = combat_page_source[cleanup_card_start:cleanup_card_end]

    assert cleanup_card_start >= 0
    assert 'className="card sidebar-card"' in cleanup_card_markup
    assert "className=\"ghost-button\"" in cleanup_card_markup
    assert "onClick={() => clearCombatMutation.mutate()}" in cleanup_card_markup
    assert "Clear tracker" in cleanup_card_markup
    assert 'className="button-row"' not in cleanup_card_markup


def test_combat_turn_focus_dm_status_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    combat_page_start = source.index("function CombatPage() {")
    campaign_combat_route_start = source.index("const campaignCombatRoute", combat_page_start)
    combat_page_source = source[combat_page_start:campaign_combat_route_start]

    turn_focus_match = re.search(
        r'<article className="card combat-control-card">\s*<div className="section-heading combat-status-snapshot__heading"[\s\S]*?</article>',
        combat_page_source,
    )
    assert turn_focus_match is not None
    turn_focus_markup = turn_focus_match.group(0)

    assert 'className="section-heading combat-status-snapshot__heading"' in turn_focus_markup
    assert '<div className="combatant-badges">' in turn_focus_markup
    assert 'className="combat-badge">Round {tracker?.round_number ?? "?"}</span>' in turn_focus_markup
    assert 'className="combat-badge">Turn {selectedCombatant.turn_value}</span>' in turn_focus_markup
    assert '<span className="combat-badge combat-badge--active">Current turn</span>' in turn_focus_markup
    assert (
        'className="combat-badge combat-badge--button combat-status-snapshot__set-current"'
        in turn_focus_markup
    )
    assert (
        re.search(
            r'<button[^>]*className="combat-badge combat-badge--button combat-status-snapshot__set-current"[^>]*'
            r'onClick=\{\(\) => setCurrentMutation\.mutate\(\)\}[^>]*disabled=\{setCurrentMutation\.isPending\}\s*>',
            turn_focus_markup,
        )
        is not None
    )
    assert "{setCurrentMutation.isPending ? \"Setting...\" : \"Set current\"}" in turn_focus_markup

    assert 'className="stack-form combat-status-authority-form"' in turn_focus_markup
    assert re.search(r'<label className="field">\s*<span>Turn value</span>', turn_focus_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Priority</span>', turn_focus_markup) is not None
    assert "className=\"chat-label\"" not in turn_focus_markup

    assert 'className="hero-actions combat-turn-actions"' in turn_focus_markup
    assert '{advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}' in turn_focus_markup
    assert '<button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>' in turn_focus_markup

    assert '<div className="button-row">' not in turn_focus_markup


def test_combat_dm_status_tactical_forms_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    combat_page_start = source.index("function CombatPage() {")
    campaign_combat_route_start = source.index("const campaignCombatRoute", combat_page_start)
    combat_page_source = source[combat_page_start:campaign_combat_route_start]

    tactical_start = combat_page_source.index('<section className="combat-dm-grid" aria-label="DM tactical controls">')
    tactical_end = combat_page_source.index('<section className="combat-pc-workspace"', tactical_start)
    tactical_markup = combat_page_source[tactical_start:tactical_end]

    assert "combat-summary-grid combat-summary-grid--snapshot" in tactical_markup
    assert "combat-stat combat-stat--editable" in tactical_markup
    assert "combat-stat-input combat-stat-input--number" in tactical_markup
    assert "combat-stat-input combat-stat-input--single" in tactical_markup
    assert "combat-inline-value" in tactical_markup
    assert "combat-resource-strip combat-inline-resource-form" in tactical_markup
    assert "combat-resource-toggle" in tactical_markup
    assert "combat-resource" in tactical_markup

    assert "combat-inline-form" not in tactical_markup
    assert 'className="chat-label"' not in tactical_markup


def test_combat_player_workspace_target_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    workspace_match = re.search(
        r"const renderPlayerWorkspace = \(\) => \([\s\S]*?\n  \);(?=\n\n  return \()",
        source,
    )
    assert workspace_match is not None
    workspace_markup = workspace_match.group(0)

    assert 'className="combat-target-list"' in workspace_markup
    assert 'className={target.is_selected ? "button-link" : "ghost-button"}' in workspace_markup
    assert 'onClick={() => selectCombatant(target.combatant_id)}' in workspace_markup
    assert '<p className="meta">{target.subtitle}' in workspace_markup

    assert 'className="tab-button' not in workspace_markup
    assert 'className="button-row"' not in workspace_markup
    assert "Open Flask Combat" not in workspace_markup
    assert 'className="button button-secondary"' not in workspace_markup
    assert '<section className="card auth-card">' in workspace_markup
    assert "<h2>No tracked player character available</h2>" in workspace_markup
    assert (
        "There is not currently a tracked player character you can open from combat."
        in workspace_markup
    )


def test_combat_conditions_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    combat_page_start = source.index("function CombatPage() {")
    campaign_combat_route_start = source.index("const campaignCombatRoute", combat_page_start)
    combat_page_source = source[combat_page_start:campaign_combat_route_start]

    condition_section_match = re.search(
        r'<section className="combat-conditions combat-conditions--compact combat-status-conditions">([\s\S]*?)</section>',
        combat_page_source,
    )
    assert condition_section_match is not None
    condition_section_markup = condition_section_match.group(0)

    assert 'className="section-heading"' in condition_section_markup
    assert "<h3>Conditions</h3>" in condition_section_markup
    assert 'className="combat-condition-editor combat-condition-editor--add"' in condition_section_markup
    assert "<summary>Add condition</summary>" in condition_section_markup
    assert 'className="combat-condition-editor__form"' in condition_section_markup
    assert re.search(r'className="field">\s*<span>Condition</span>', condition_section_markup) is not None
    assert re.search(r'className="field">\s*<span>Duration</span>', condition_section_markup) is not None
    assert 'className="combat-condition-list"' in condition_section_markup
    assert 'className="combat-condition-item"' in condition_section_markup
    assert 'className="combat-condition-actions"' in condition_section_markup
    assert re.search(
        r'<button\s+type="button"\s+className="ghost-button"[^>]*onClick=\{\(\) => deleteConditionMutation\.mutate\(condition\)\}[^>]*>\s*Remove\s*</button>',
        condition_section_markup,
    ) is not None
    assert "className=\"button button-secondary\"" not in condition_section_markup


def test_character_maintenance_unsupported_card_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")

    def component_source(component_name: str) -> str:
        start = source.index(f"function {component_name}() {{")
        end = source.find("\nfunction ", start + len(component_name) + 10)
        if end == -1:
            end = len(source)
        return source[start:end]

    def unsupported_card(component_name: str) -> str:
        component_markup = component_source(component_name)
        unsupported_match = re.search(
            r"\{data && !data\.supported \? \(\s*<section className=\"[^\"]*\"\s*>[\s\S]*?</section>\s*\) : null\}",
            component_markup,
        )
        assert unsupported_match is not None, f"Unsupported block not found for {component_name}"
        return unsupported_match.group(0)

    advanced_markup = unsupported_card("CharacterAdvancedEditorPage")
    assert '<section className="card auth-card">' in advanced_markup
    assert '<div className="hero-actions">' in advanced_markup
    assert '<div className="button-row">' not in advanced_markup
    assert 'className="button button-secondary"' not in advanced_markup
    assert "Flask sheet" not in advanced_markup
    assert 'className="button-link" href={data.links.character_url}>' in advanced_markup
    assert "Back to sheet" in advanced_markup
    assert 'className="ghost-button" href={data.links.cultivation_url}>' in advanced_markup
    assert "Cultivation" in advanced_markup

    progression_markup = unsupported_card("CharacterProgressionRepairPage")
    assert '<section className="card auth-card">' in progression_markup
    assert '<div className="hero-actions">' in progression_markup
    assert '<div className="button-row">' not in progression_markup
    assert 'className="button button-secondary"' not in progression_markup
    assert "Flask sheet" not in progression_markup
    assert "Flask repair" not in progression_markup
    assert 'className="button-link" href={data.links.level_up_url}>' in progression_markup
    assert "Level Up" in progression_markup
    assert 'className="ghost-button" href={data.links.cultivation_url}>' in progression_markup
    assert "Cultivation" in progression_markup

    retraining_markup = unsupported_card("CharacterRetrainingPage")
    assert '<section className="card auth-card">' in retraining_markup
    assert '<div className="hero-actions">' in retraining_markup
    assert '<div className="button-row">' not in retraining_markup
    assert 'className="button button-secondary"' not in retraining_markup
    assert "Flask sheet" not in retraining_markup
    assert "Flask repair" not in retraining_markup
    assert 'className="button-link" href={data.links.character_url}>' in retraining_markup
    assert "Back to sheet" in retraining_markup
    assert 'className="ghost-button" href={data.links.progression_repair_url}>' in retraining_markup
    assert "Progression repair" in retraining_markup
    assert 'className="ghost-button" href={data.links.cultivation_url}>' in retraining_markup
    assert "Cultivation" in retraining_markup

    level_up_markup = unsupported_card("CharacterLevelUpPage")
    assert '<section className="card auth-card">' in level_up_markup
    assert '<div className="hero-actions">' in level_up_markup
    assert '<div className="button-row">' not in level_up_markup
    assert 'className="button button-secondary"' not in level_up_markup
    assert "Flask sheet" not in level_up_markup
    assert "Flask repair" not in level_up_markup
    assert 'className="button-link" href={data.links.character_url}>' in level_up_markup
    assert "Back to sheet" in level_up_markup
    assert 'className="ghost-button" href={data.links.progression_repair_url}>' in level_up_markup
    assert "Progression repair" in level_up_markup
    assert 'className="ghost-button" href={data.links.cultivation_url}>' in level_up_markup
    assert "Cultivation" in level_up_markup

    cultivation_markup = unsupported_card("CharacterCultivationPage")
    assert '<section className="card auth-card">' in cultivation_markup
    assert '<div className="hero-actions">' in cultivation_markup
    assert '<div className="button-row">' not in cultivation_markup
    assert 'className="button button-secondary"' not in cultivation_markup
    assert "Flask sheet" not in cultivation_markup
    assert 'className="button-link" href={data.links.character_url}>' in cultivation_markup
    assert "Back to sheet" in cultivation_markup


def test_character_supported_form_action_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")

    def component_source(component_name: str) -> str:
        start = source.index(f"function {component_name}() {{")
        end = source.find("\nfunction ", start + len(component_name) + 10)
        if end == -1:
            end = len(source)
        return source[start:end]

    def supported_component(component_name: str) -> str:
        component = component_source(component_name)
        unsupported_marker = "{data && !data.supported ? ("
        if unsupported_marker in component:
            return component.split(unsupported_marker, 1)[1].split(") : null}", 1)[1]
        return component

    create_markup = component_source("CharacterCreatePage")
    assert (
        re.search(
            r'<button\s+type="button"\s+className="ghost-button"\s+onClick=\{\(\) => refreshContext\(\)\}>\s*'
            r"Refresh options\s*</button>",
            create_markup,
        )
        is not None
    )
    assert "className=\"button button-secondary\"" not in create_markup

    manual_markup = component_source("CharacterXianxiaManualImportPage")
    assert (
        re.search(
            r'<button\s+type="button"\s+className="ghost-button"\s+onClick=\{\(\) => setRowCount\(\(current\) => current \+ 1\)\}>\s*'
            r"Add Martial Art\s*</button>",
            manual_markup,
        )
        is not None
    )
    assert "className=\"button button-secondary\"" not in manual_markup

    editor_markup = supported_component("CharacterAdvancedEditorPage")
    assert (
        re.search(
            r'<div className="hero-actions">\s*<button\s+type="submit"\s+disabled={saveEditor\.isPending}>',
            editor_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<div className="builder-actions">\s*<button\s+type="submit"\s+disabled={saveEditor\.isPending}>',
            editor_markup,
        )
        is None
    )
    assert 'className="ghost-button" href={data.links.character_url}>' in editor_markup
    assert re.search(r">\s*Back to sheet\s*</a>", editor_markup) is not None
    assert "className=\"button button-secondary\"" not in editor_markup

    progression_markup = supported_component("CharacterProgressionRepairPage")
    assert (
        re.search(
            r'<div className="builder-actions">\s*<button\s+className="ghost-button"\s+type="submit"\s+disabled={submitRepair\.isPending}>\s*{submitRepair\.isPending \? "Saving\.\.\." : "Save Repair"}\s*</button>',
            progression_markup,
        )
        is not None
    )
    assert 'className="ghost-button" href={data.links.character_url}>' in progression_markup
    assert "Save Repair" in progression_markup
    assert "Cancel" in progression_markup
    assert "className=\"button button-secondary\"" not in progression_markup

    retraining_markup = supported_component("CharacterRetrainingPage")
    assert (
        re.search(
            r'<div className="hero-actions">\s*<button\s+type="submit"\s+disabled={submitRetraining\.isPending}>',
            retraining_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<div className="builder-actions">\s*<button\s+type="submit"\s+disabled={submitRetraining\.isPending}>',
            retraining_markup,
        )
        is None
    )
    assert 'href={`${data.links.character_url}?page=features`}' in retraining_markup
    assert re.search(r'className="ghost-button"[^>]*>\s*Cancel\s*</a>', retraining_markup) is not None
    assert "className=\"button button-secondary\"" not in retraining_markup

    level_up_markup = supported_component("CharacterLevelUpPage")
    assert (
        re.search(
            r'<button\s+type="button"\s+className="ghost-button"\s+onClick=\{\(\) => refreshContext\(\)\}>\s*'
            r"Refresh preview\s*</button>",
            level_up_markup,
        )
        is not None
    )
    assert "className=\"button button-secondary\"" not in level_up_markup


def test_character_form_actions_do_not_convert_non_targeted_builder_rows() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")

    def component_source(component_name: str) -> str:
        start = source.index(f"function {component_name}() {{")
        end = source.find("\nfunction ", start + len(component_name) + 10)
        if end == -1:
            end = len(source)
        return source[start:end]

    create_markup = component_source("CharacterCreatePage")
    assert re.search(r'<div className="builder-actions">[\s\S]*?<button\s+type="submit"\s+disabled={!create\.builder_ready \|\| createMutation\.isPending}>', create_markup) is not None
    assert (
        re.search(
            r'<button\s+type="button"\s+className="ghost-button"\s+onClick=\{\(\) => refreshContext\(\)\}>\s*'
            r"Refresh options\s*</button>",
            create_markup,
        )
        is not None
    )

    manual_markup = component_source("CharacterXianxiaManualImportPage")
    assert (
        re.search(
            r'<div className="builder-actions">\s*<button\s+type="submit"\s+disabled={importMutation\.isPending}>',
            manual_markup,
        )
        is not None
    )

    level_up_markup = component_source("CharacterLevelUpPage")
    assert (
        re.search(
            r'<div className="builder-actions">\s*<button\s+type="button"\s+className="ghost-button"\s+onClick=\{\(\) => refreshContext\(\)\}>\s*'
            r"Refresh preview\s*</button>\s*<button\s+type=\"submit\" disabled={submitLevelUp\.isPending}>",
            level_up_markup,
        )
        is not None
    )


def test_combat_unsupported_system_fallback_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    combat_page_start = source.index("function CombatPage() {")
    campaign_combat_route_start = source.index("const campaignCombatRoute", combat_page_start)
    combat_page_source = source[combat_page_start:campaign_combat_route_start]

    unsupported_match = re.search(
        r'\{payload && !payload\.combat_system_supported \? \([\s\S]*?<section className="card auth-card"[\s\S]*?</section>[\s\S]*?\) : null\}',
        combat_page_source,
    )
    assert unsupported_match is not None
    unsupported_markup = unsupported_match.group(0)

    assert 'className="card auth-card"' in unsupported_markup
    assert (
        '<h2>Combat tracker not configured for {payload.campaign.system || "this system"} yet</h2>'
        in unsupported_markup
    )
    assert (
        re.search(
            r"This route is a placeholder for the campaign system lane\.\s*The current combat tracker is\s*"
            r"DND-5E-only, so no encounter automation is available here for {payload\.campaign\.system \|\| \"this system\"} yet\.",
            unsupported_markup,
        )
        is not None
    )
    assert 'className="hero-actions"' in unsupported_markup
    assert (
        re.search(
            r'<a className="button-link" href=\{payload\.links\?\.flask_campaign_url[^}]*\}',
            unsupported_markup,
        ) is not None
        and "Open Campaign Home" in unsupported_markup
    )
    assert (
        re.search(
            r'<a className="ghost-button" href=\{payload\.links\.flask_characters_url\}\>Open Characters</a>',
            unsupported_markup,
        )
        is not None
        or re.search(
            r'<a className="ghost-button" href=\{payload\.links\.flask_characters_url\}\>\s*Open Characters\s*</a>',
            unsupported_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<a className="ghost-button" href=\{payload\.links\.flask_session_url\}\>Open Session</a>',
            unsupported_markup,
        )
        is not None
        or re.search(
            r'<a className="ghost-button" href=\{payload\.links\.flask_session_url\}\>\s*Open Session\s*</a>',
            unsupported_markup,
        )
        is not None
    )
    assert "Open Flask Combat" not in unsupported_markup
    assert "button button-secondary" not in unsupported_markup

    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.auth-card\s*\{\s*max-width:\s*36rem;\s*\}", styles) is not None


def test_character_portrait_manager_action_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    section_start = source.index('<form className="stack-form character-portrait-manager"')
    section_end = source.index("</form>", section_start) + len("</form>")
    section_markup = source[section_start:section_end]

    assert 'className="stack-form character-portrait-manager"' in section_markup
    assert 'className="field" htmlFor="character-portrait-file"' in section_markup
    assert "<span>Portrait image</span>" in section_markup
    assert 'className="field" htmlFor="character-portrait-alt"' in section_markup
    assert "<span>Alt text</span>" in section_markup
    assert 'className="field" htmlFor="character-portrait-caption"' in section_markup
    assert "<span>Caption</span>" in section_markup
    assert "className=\"hero-actions character-portrait-manager__actions\"" in section_markup
    assert '<button className="button" type="submit" disabled={portraitMutationPending || !portraitDraft.file}>' in section_markup
    remove_button = re.search(
        r'<button\s+type="button"\s+className="ghost-button"\s+disabled={portraitMutationPending}\s+onClick={removePortrait}\s*>\s*Remove portrait\s*</button>',
        section_markup,
    )
    assert remove_button is not None
    assert 'className="button button-secondary"' not in section_markup
    assert 'className="button-row character-portrait-manager__actions"' not in section_markup
    assert "character-portrait-manager__fields" not in section_markup


def test_dm_article_creator_uses_flask_style_mode_panels_and_fields() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    component_start = source.index("function DmArticleCreator({")
    component_end = source.index("function SessionPane({", component_start)
    creator_markup = source[component_start:component_end]

    assert 'className="stack-form"' in creator_markup
    assert 'className="session-form-mode-radio session-form-mode-radio--manual"' in creator_markup
    assert 'className="session-form-mode-radio session-form-mode-radio--upload"' in creator_markup
    assert 'className="session-form-mode-radio session-form-mode-radio--wiki"' in creator_markup
    assert 'className="session-form-mode-toggle"' in creator_markup
    assert 'className="session-article-mode-panel session-article-mode-panel--manual"' in creator_markup
    assert 'className="session-article-mode-panel session-article-mode-panel--upload"' in creator_markup
    assert 'className="session-article-mode-panel session-article-mode-panel--wiki"' in creator_markup
    assert 'className="field"' in creator_markup
    assert 'className="field session-file-field"' in creator_markup
    assert 'className="session-file-input"' in creator_markup
    assert 'className="session-file-dropzone"' in creator_markup
    assert "className=\"session-form\"" not in creator_markup
    assert 'className="segmented"' not in creator_markup
    assert "className=\"segmented-button\"" not in creator_markup
    assert 'className="chat-label"' not in creator_markup
    assert "Search wiki / systems" not in creator_markup
    assert "Lookup" in creator_markup


def test_dm_content_player_wiki_editor_fields_use_flask_style_labels_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    helper_start = source.index("const renderPlayerWikiDraftFields = ({")
    helper_end = source.index("const renderStatblockCard =", helper_start)
    helper_markup = source[helper_start:helper_end]

    assert "className=\"chat-label\"" not in helper_markup
    assert "dm-content-image-edit-row" not in helper_markup
    assert '<label className="checkbox-label">' in helper_markup

    expected_player_wiki_fields = [
        ("title", "Title"),
        ("slug", "Slug"),
        ("section", "Section"),
        ("type", "Page type"),
        ("subsection", "Subsection"),
        ("summary", "Summary"),
        ("aliases", "Aliases"),
        ("reveal-after-session", "Reveal after session"),
        ("display-order", "Display order"),
        ("source-ref", "Source reference"),
        ("image", "Image path"),
        ("image-upload", "Upload image"),
        ("image-alt", "Image alt text"),
        ("image-caption", "Image caption"),
        ("body", "Markdown body"),
    ]

    for suffix, label in expected_player_wiki_fields:
        label_open = '<label htmlFor={`$' + '{idPrefix}-' + suffix + '`} className="field">'
        assert label_open in helper_markup
        assert f"<span>{label}</span>" in helper_markup

    player_wiki_form_class = 'className="stack-form dm-content-wiki-form"'
    form_class_matches = re.findall(rf"<form\s+{player_wiki_form_class}", source)
    assert len(form_class_matches) >= 2
    assert "dm-player-wiki-edit-form" not in source


def test_dm_content_systems_management_form_field_chrome() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    helper_start = source.index("const renderCustomFields = ({")
    helper_end = source.index("  if (systemsQuery.isLoading)", helper_start)
    helper_markup = source[helper_start:helper_end]

    expected_systems_custom_fields = [
        ("title", "Title"),
        ("slug", "URL slug"),
        ("type", "Entry type"),
        ("visibility", "Visibility"),
        ("provenance", "Source/provenance"),
        ("search", "Searchable metadata"),
        ("body", "Rendered body"),
    ]

    assert "className=\"chat-label\"" not in helper_markup
    assert "dm-content-image-edit-row" not in helper_markup
    assert 'className="builder-field-grid"' in helper_markup
    assert 'className="field"' in helper_markup

    for suffix, label in expected_systems_custom_fields:
        label_open = '<label htmlFor={`$' + '{idPrefix}-' + suffix + '`} className="field">'
        assert label_open in helper_markup
        assert f"<span>{label}</span>" in helper_markup

    override_start = source.index('<section className="card" id="systems-entry-overrides">')
    override_end = source.index('<section className="card" id="systems-custom-entries">', override_start)
    override_markup = source[override_start:override_end]

    assert 'className="stack-form"' in override_markup
    assert '<label htmlFor="systems-entry-override-key" className="field">' in override_markup
    assert '<label htmlFor="systems-entry-override-visibility" className="field">' in override_markup
    assert '<label htmlFor="systems-entry-override-enabled" className="field">' in override_markup
    assert "<span>Entry key</span>" in override_markup
    assert "<span>Visibility override</span>" in override_markup
    assert "<span>Enablement override</span>" in override_markup
    assert "className=\"chat-label\"" not in override_markup
    assert "dm-content-image-edit-row" not in override_markup


def test_dm_content_statblock_and_condition_forms_use_flask_field_labels_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")

    statblock_edit_start = source.index("const renderStatblockCard = (")
    statblock_edit_end = source.index("const renderConditionCard =", statblock_edit_start)
    statblock_edit_markup = source[statblock_edit_start:statblock_edit_end]

    assert 'className="chat-label"' not in statblock_edit_markup
    assert 'className="stack-form"' in statblock_edit_markup
    assert '<label className="field">' in statblock_edit_markup
    assert re.search(r'<label className="field">\s*<span>Subsection</span>', statblock_edit_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Source markdown body</span>', statblock_edit_markup) is not None
    assert 'name="subsection"' in statblock_edit_markup
    assert 'name="markdown_text"' in statblock_edit_markup

    condition_edit_start = source.index("const renderConditionCard = (")
    condition_edit_end = source.index("const renderPlayerWikiPageCard =", condition_edit_start)
    condition_edit_markup = source[condition_edit_start:condition_edit_end]

    assert 'className="chat-label"' not in condition_edit_markup
    assert 'className="stack-form"' in condition_edit_markup
    assert '<label className="field">' in condition_edit_markup
    assert re.search(r'<label className="field">\s*<span>Condition name</span>', condition_edit_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Description</span>', condition_edit_markup) is not None
    assert 'name="name"' in condition_edit_markup
    assert 'name="description_markdown"' in condition_edit_markup

    statblock_create_start = source.index('<section className="card dm-statblock-create">')
    statblock_create_end = source.index('<section className="card dm-statblock-library">', statblock_create_start)
    statblock_create_markup = source[statblock_create_start:statblock_create_end]

    assert 'className="stack-form"' in statblock_create_markup
    assert 'className="session-form"' not in statblock_create_markup
    assert 'className="chat-label"' not in statblock_create_markup
    assert re.search(r'<label className="field">\s*<span>Import markdown file</span>', statblock_create_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Source filename</span>', statblock_create_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Subsection</span>', statblock_create_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Source markdown body</span>', statblock_create_markup) is not None
    assert 'name="filename"' in statblock_create_markup
    assert 'name="subsection"' in statblock_create_markup
    assert 'name="markdown_text"' in statblock_create_markup
    assert 'type="file"' in statblock_create_markup

    condition_create_start = source.index('<section className="card dm-condition-create">')
    condition_create_end = source.index('<section className="card dm-condition-library">', condition_create_start)
    condition_create_markup = source[condition_create_start:condition_create_end]

    assert 'className="stack-form"' in condition_create_markup
    assert 'className="session-form"' not in condition_create_markup
    assert 'className="chat-label"' not in condition_create_markup
    assert re.search(r'<label className="field">\s*<span>Condition name</span>', condition_create_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Description</span>', condition_create_markup) is not None
    assert 'name="name"' in condition_create_markup
    assert 'name="description_markdown"' in condition_create_markup


def test_character_xianxia_inventory_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    resources_start = source.index('{isXianxia && activeCharacterSection === "resources" ? (')
    resources_end = source.index('{isXianxia && activeCharacterSection === "skills" ? (', resources_start)
    resources_markup = source[resources_start:resources_end]

    assert 'id="session-active-state"' in resources_markup
    assert '<h3>Active Stance and Aura</h3>' in resources_markup
    assert 'className="section-heading"' in resources_markup
    assert 'form onSubmit={submitXianxiaActiveState}' in resources_markup
    assert 'className="session-vitals-form"' in resources_markup
    assert (
        re.search(r'<label className="session-field" htmlFor="xianxia-active-stance">\s*<span>Active Stance</span>', resources_markup)
        is not None
    )
    assert (
        re.search(r'<label className="session-field" htmlFor="xianxia-active-aura">\s*<span>Active Aura</span>', resources_markup)
        is not None
    )
    assert 'Save Active Stance and Aura' in resources_markup
    assert 'className="inline-two-col"' not in resources_markup
    assert 'className="chat-label"' not in resources_markup

    section_start = source.index('{isXianxia && activeCharacterSection === "inventory" ? (')
    section_end = source.index('<section className="read-section" id="xianxia-personal">', section_start)
    section_markup = source[section_start:section_end]
    controls_end = section_markup.index('<div className="detail-grid" id="session-currency">')
    inventory_controls_markup = section_markup[:controls_end]
    currency_controls_markup = section_markup[controls_end:]

    assert 'className="inventory-list"' in inventory_controls_markup
    assert 'className="inventory-row"' in inventory_controls_markup
    assert 'className="inventory-row__header"' in inventory_controls_markup
    assert 'className="detail-cluster"' in inventory_controls_markup
    assert 'className="detail-card session-card" id="xianxia-inventory-add"' in inventory_controls_markup

    assert 'className="stack-form"' in inventory_controls_markup
    assert 'className="builder-field-grid"' in inventory_controls_markup
    assert 'className="session-field" htmlFor="xianxia-new-item-name"' in inventory_controls_markup
    assert 'className="session-field" htmlFor="xianxia-new-item-quantity"' in inventory_controls_markup
    assert 'className="session-field" htmlFor="xianxia-new-item-nature"' in inventory_controls_markup
    assert 'className="session-field" htmlFor="xianxia-new-item-type"' in inventory_controls_markup
    assert 'className="session-field" htmlFor="xianxia-new-item-tags"' in inventory_controls_markup
    assert 'className="session-field" htmlFor="xianxia-new-item-notes"' in inventory_controls_markup

    assert (
        re.search(
            r'<label className="session-field" htmlFor={`xianxia-inventory-name-\$\{item\.id\}`}>\s*<span>Name</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor={`xianxia-inventory-quantity-\$\{item\.id\}`}>\s*<span>Quantity</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor={`xianxia-inventory-nature-\$\{item\.id\}`}>\s*<span>Nature</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor={`xianxia-inventory-type-\$\{item\.id\}`}>\s*<span>Type</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor={`xianxia-inventory-tags-\$\{item\.id\}`}>\s*<span>Tags</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor={`xianxia-inventory-notes-\$\{item\.id\}`}>\s*<span>Notes</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor="xianxia-new-item-name">\s*<span>Name</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor="xianxia-new-item-quantity">\s*<span>Quantity</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor="xianxia-new-item-nature">\s*<span>Nature</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor="xianxia-new-item-type">\s*<span>Type</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor="xianxia-new-item-tags">\s*<span>Tags</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label className="session-field" htmlFor="xianxia-new-item-notes">\s*<span>Notes</span>',
            inventory_controls_markup,
        )
        is not None
    )

    assert "className=\"chat-label\"" not in inventory_controls_markup
    assert 'className="button-danger"' not in inventory_controls_markup
    assert 'className="button-link subtle"' in inventory_controls_markup

    assert 'className="detail-grid" id="session-currency"' in currency_controls_markup
    assert '<article className="detail-card session-card">' in currency_controls_markup
    assert "<h3>Currency</h3>" in currency_controls_markup
    assert 'className="currency-grid"' in currency_controls_markup
    assert 'className="currency-form currency-box"' in currency_controls_markup
    assert 'className="currency-box__header"' in currency_controls_markup
    assert 'className="currency-box__amount"' in currency_controls_markup
    assert "onBlur={submitCurrencyOnBlur}" in currency_controls_markup
    assert 'className="visually-hidden"' in currency_controls_markup
    assert 'Update {entry.label}' in currency_controls_markup
    assert re.search(r'<button type="submit" className="visually-hidden" disabled=\{patchCurrency\.isPending \|\| !canEdit\}>\s*Update \{entry\.label\}\s*</button>', currency_controls_markup) is not None

    assert 'className="chat-label"' not in currency_controls_markup
    assert 'className="inline-two-col"' not in currency_controls_markup
    assert 'form onSubmit={submitCurrency} className="currency-grid"' not in currency_controls_markup
    assert 'Save currency' not in currency_controls_markup


def test_character_dnd_inventory_currency_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isDnd && activeCharacterSection === "inventory" ? (')
    section_end = source.index('{isDnd && activeCharacterSection === "abilities" ? (', section_start)
    section_markup = source[section_start:section_end]

    controls_end = section_markup.index('<div className="detail-grid">')
    currency_controls_markup = section_markup[controls_end:]

    assert 'className="detail-grid"' in currency_controls_markup
    assert '<article className="detail-card">' in currency_controls_markup
    assert "<h3>Currency</h3>" in currency_controls_markup
    assert 'className="currency-grid" id="session-currency"' in currency_controls_markup
    assert 'className="currency-form currency-box"' in currency_controls_markup
    assert 'className="currency-box__header"' in currency_controls_markup
    assert 'className="currency-box__amount"' in currency_controls_markup
    assert "onBlur={submitCurrencyOnBlur}" in currency_controls_markup
    assert 'className="visually-hidden"' in currency_controls_markup
    assert 'Update {key.toUpperCase()}' in currency_controls_markup
    assert '["cp", "sp", "ep", "gp", "pp"].map((key) =>' in currency_controls_markup
    assert re.search(r'<button type="submit" className="visually-hidden" disabled=\{patchCurrency\.isPending \|\| !canEdit\}>\s*Update \{key\.toUpperCase\(\)\}\s*</button>', currency_controls_markup) is not None

    assert 'className="chat-label"' not in currency_controls_markup
    assert 'form onSubmit={submitCurrency} className="currency-grid"' not in currency_controls_markup
    assert 'Save currency' not in currency_controls_markup


def test_character_dnd_inventory_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isDnd && activeCharacterSection === "inventory" ? (')
    section_end = source.index('{isDnd && activeCharacterSection === "abilities" ? (', section_start)
    section_markup = source[section_start:section_end]

    controls_end = section_markup.index('<div className="detail-grid">')
    inventory_controls_markup = section_markup[:controls_end]

    assert 'className="inventory-list"' in inventory_controls_markup
    assert 'className="inventory-row"' in inventory_controls_markup
    assert 'className="inventory-row__header"' in inventory_controls_markup
    assert 'className="session-inline-form inventory-row__quantity-form"' in inventory_controls_markup
    assert 'data-character-autosubmit' in inventory_controls_markup
    assert 'data-character-sheet-edit-form="inventory"' in inventory_controls_markup
    assert 'data-character-sheet-edit-row-id={id}' in inventory_controls_markup
    assert 'className="session-field" htmlFor={`inventory-${id}`}' in inventory_controls_markup
    assert (
        re.search(
            r'<label className="session-field" htmlFor={`inventory-\$\{id\}`}>\s*<span>Quantity</span>',
            inventory_controls_markup,
        )
        is not None
    )
    assert 'onBlur={submitInventoryOnBlur}' in inventory_controls_markup
    assert 'className="visually-hidden"' in inventory_controls_markup
    assert 'Update {itemName} quantity' in inventory_controls_markup
    assert (
        re.search(
            r'<button type="submit" className="visually-hidden" disabled=\{patchInventory\.isPending \|\| !canEdit\}>\s*Update \{itemName\} quantity\s*</button>',
            inventory_controls_markup,
        )
        is not None
    )
    assert 'className="ghost-button item-detail-button"' in inventory_controls_markup

    assert '<strong>x{readNumber(item.quantity, 1)}</strong>' not in inventory_controls_markup
    assert 'className="character-card-grid"' not in inventory_controls_markup
    assert 'className="character-state-card"' not in inventory_controls_markup
    assert 'className="compact-state-form"' not in inventory_controls_markup
    assert 'className="chat-label"' not in inventory_controls_markup
    assert '>Save<' not in inventory_controls_markup


def test_character_dnd_resources_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    resources_start = source.index('{isDnd && activeCharacterSection === "resources" ? (')
    resources_end = source.index('{isDnd && activeCharacterSection === "spells" ? (', resources_start)
    resources_markup = source[resources_start:resources_end]

    assert 'className="resource-grid resource-grid--compact"' in resources_markup
    assert 'className="resource-card' in resources_markup
    assert 'className="session-inline-form"' in resources_markup
    assert 'data-character-autosubmit' in resources_markup
    assert 'data-character-sheet-edit-form="resource"' in resources_markup
    assert 'data-character-sheet-edit-row-id={id}' in resources_markup
    assert 'className="session-field"' in resources_markup
    assert (
        re.search(
            r'<label className="session-field" htmlFor=\{`resource-\$\{id\}`\}>\s*<span>Current</span>\s*<input',
            resources_markup,
        )
        is not None
    )
    assert 'className="resource-card__value"' in resources_markup
    assert 'className="visually-hidden"' in resources_markup
    assert 'Update {resourceLabel}' in resources_markup

    assert 'className="character-card-grid"' not in resources_markup
    assert 'className="character-state-card"' not in resources_markup
    assert 'className="compact-state-form"' not in resources_markup
    assert 'className="chat-label"' not in resources_markup
    assert 'Save' not in resources_markup


def test_character_dnd_spell_slots_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isDnd && activeCharacterSection === "spells" ? (')
    section_end = source.index('{isDnd && activeCharacterSection === "equipment" ? (', section_start)
    section_markup = source[section_start:section_end]

    controls_start = section_markup.index('{spellSlots.length ? (')
    controls_end = section_markup.index('{presentedSpells.length ? (', controls_start)
    slot_controls_markup = section_markup[controls_start:controls_end]

    assert 'className="spell-slot-editor-list spell-slot-editor-list--compact"' in slot_controls_markup
    assert '<article className="detail-card"' in slot_controls_markup
    assert 'onSubmit={(event) => submitSpellSlot(event, slot)}' in slot_controls_markup
    assert 'className="session-inline-form"' in slot_controls_markup
    assert 'data-character-autosubmit' in slot_controls_markup
    assert 'data-character-sheet-edit-form="spell-slot"' in slot_controls_markup
    assert 'data-character-sheet-edit-level={level}' in slot_controls_markup
    assert 'data-character-sheet-edit-slot-lane-id={slotLaneId}' in slot_controls_markup
    assert 'className="session-field" htmlFor={`spell-slot-${key}`}' in slot_controls_markup
    assert 'onBlur={submitSpellSlotOnBlur}' in slot_controls_markup
    assert (
        re.search(
            r'<button type="submit" className="visually-hidden" disabled=\{patchSpellSlot\.isPending \|\| !canEdit\}>\s*Update \{slotLabel\}\s*</button>',
            slot_controls_markup,
        )
        is not None
    )
    assert 'className="visually-hidden"' in slot_controls_markup
    assert 'Update {slotLabel}' in slot_controls_markup
    assert 'className="section-heading"' in slot_controls_markup
    assert '<h3>{slotLabel}</h3>' in slot_controls_markup
    assert (
        re.search(r'className="meta">\s*\{available\} available / \{max\}\s*</span>', slot_controls_markup) is not None
    )

    assert 'className="character-card-grid"' not in slot_controls_markup
    assert 'className="compact-state-form"' not in slot_controls_markup
    assert 'className="character-state-card"' not in slot_controls_markup
    assert 'className="chat-label"' not in slot_controls_markup
    assert 'Save' not in slot_controls_markup


def test_player_session_revealed_articles_panel_uses_session_article_row_chrome_in_source() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    panel_start = source.index("function SessionArticlesPanel({")
    panel_end = source.index("\nfunction SessionPaneChat(", panel_start)
    panel_markup = source[panel_start:panel_end]

    assert 'className="session-article-stack"' in panel_markup
    assert 'className="feature-detail session-article-detail"' in panel_markup
    assert "data-session-article-id={article.id}" in panel_markup
    assert 'className="article-figure"' in panel_markup
    assert "const revealedLabel = article.revealed_at" in panel_markup
    assert "Revealed ${formatTimestamp(article.revealed_at)}" in panel_markup
    assert "Revealed ${formatTimestamp(article.created_at)}" in panel_markup
    assert 'renderArticleBody(article, "article-body--compact")' in panel_markup
    assert 'className="session-article-detail__actions"' in panel_markup
    assert (
        "SessionArticleReferenceActions article={article} includePromotionLinks={false}" in panel_markup
    )

    assert 'className="article-stack"' not in panel_markup
    assert 'className="article-card"' not in panel_markup
    assert 'className="article-kind"' not in panel_markup
    assert 'className="article-actions"' not in panel_markup


def test_dm_content_staged_articles_edit_form_uses_flask_style_file_field_markup() -> None:
    source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    queue_start = source.index('<article className="card" id="dm-content-staged-articles-queue">')
    queue_end = source.index("</article>", queue_start) + len("</article>")
    queue_markup = source[queue_start:queue_end]

    assert 'className="session-article-stack"' in queue_markup
    assert 'className="feature-detail session-article-detail"' in queue_markup
    assert 'className="session-article-edit-detail"' in queue_markup
    assert 'className="stack-form session-article-edit-form"' in queue_markup

    form_match = re.search(
        r'<form\s+className="stack-form session-article-edit-form"[\s\S]*?>',
        queue_markup,
    )
    assert form_match is not None
    form_start = form_match.start()
    form_end = queue_markup.index("</form>", form_start) + len("</form>")
    form_markup = queue_markup[form_start:form_end]

    assert 'className="field session-file-field"' in form_markup
    assert 'className="session-file-input"' in form_markup
    assert 'className="session-file-dropzone"' in form_markup
    assert 'className="session-file-dropzone__browse"' in form_markup
    assert 'session-file-dropzone__name' in form_markup
    assert 'label className="field">' in form_markup
    assert re.search(r'<label className="field">\s*<span>Title</span>', form_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Body</span>', form_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Image alt text</span>', form_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Image caption</span>', form_markup) is not None
    assert 'className="chat-label"' not in queue_markup
    assert "dm-content-image-edit-row" not in queue_markup

    assert (
        re.search(r'<span>\{article\.image \? "Replace image" : "Image"\}</span>', queue_markup)
        is not None
    )
