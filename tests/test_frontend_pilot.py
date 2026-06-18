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

    assert 'className="hero-actions combat-turn-actions"' in turn_focus_markup
    assert '{advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}' in turn_focus_markup
    assert '<button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>' in turn_focus_markup

    assert '<div className="button-row">' not in turn_focus_markup


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
