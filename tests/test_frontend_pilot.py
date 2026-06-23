from pathlib import Path
import re


def _extract_component_source(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _extract_function_component_source(source: str, component_name: str) -> str:
    plain_marker = f"function {component_name}() {{"
    export_marker = f"export {plain_marker}"
    start = source.find(export_marker)
    marker = export_marker
    if start == -1:
        start = source.index(plain_marker)
        marker = plain_marker

    search_start = start + len(marker)
    end_candidates = [
        index
        for index in (
            source.find("\nfunction ", search_start),
            source.find("\nexport function ", search_start),
        )
        if index != -1
    ]
    end = min(end_candidates) if end_candidates else len(source)
    return source[start:end]


def test_gen2_topbar_account_controls_use_flask_chrome_classes_in_source() -> None:
    source = Path("frontend/src/AppShell.tsx").read_text(encoding="utf-8")
    account_row = re.search(r'<div className="account-row">([\s\S]*?)</div>', source)
    assert account_row is not None

    account_controls_markup = account_row.group(1)
    assert 'className="header-link" href="/app-next/admin"' in account_controls_markup
    assert 'className="header-link" href="/app-next/account"' in account_controls_markup
    assert '<span className="meta">Admin</span>' in account_controls_markup
    assert re.search(r'<button type="submit" className="ghost-button">\s*Sign out\s*</button>', account_controls_markup) is not None
    assert re.search(r'<a className="ghost-button" href=\{signInHref\}>\s*Sign in\s*</a>', account_controls_markup) is not None
    assert "button button-secondary" not in account_controls_markup


def test_campaign_picker_grid_and_empty_state_are_mutually_exclusive_in_source() -> None:
    campaign_list_source = Path("frontend/src/routes/CampaignPickerPage.tsx").read_text(encoding="utf-8")

    assert (
        re.search(
            r"\{campaigns\.length \? \(\s*<section className=\"grid campaign-picker-grid\">[\s\S]*?</section>\s*\)\s*:\s*null\}",
            campaign_list_source,
        )
        is not None
    )
    assert "{campaigns.length ? (" in campaign_list_source
    assert (
        '{!appQuery.isLoading && !campaignsQuery.isLoading && !campaigns.length && !campaignError ? ('
        in campaign_list_source
    )

    assert (
        re.search(r"<ApiErrorNotice[\s\S]*?/\>\s*\r?\n\s*\{campaigns\.length \? \(", campaign_list_source) is not None
    )
    assert (
        re.search(r"<ApiErrorNotice[\s\S]*?/\>\s*\r?\n\s*<section className=\"grid campaign-picker-grid\">", campaign_list_source)
        is None
    )
    assert '<p className="meta">Visible through session {entry.campaign.current_session}</p>' in campaign_list_source
    assert "entry.campaign.current_session !== null && entry.campaign.current_session !== undefined ? (" not in campaign_list_source


def test_frontend_pilot_routes_are_closed(client, app, tmp_path):
    # Ensure closed mode is explicit even when a build is present.
    app.config["APP_NEXT_PREVIEW_ENABLED"] = False
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


def test_frontend_pilot_routes_are_available_with_preview_and_index(app, client, tmp_path):
    app.config["APP_NEXT_PREVIEW_ENABLED"] = True
    dist_dir = tmp_path / "frontend-dist-preview"
    assets_dir = dist_dir / "assets"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        (
            '<!doctype html><html lang="en" data-theme="ember"><head>'
            '<style id="app-loading-inline-styles">html.app-loading #root { opacity: 0; }</style>'
            '<script id="app-loading-inline-script">const failOpenDelayMs = 12000;</script>'
            "</head><body>"
            '<div class="app-loading-cover" role="status" aria-live="polite" aria-label="Loading application">'
            '<div class="app-loading-cover__media" aria-hidden="true"></div>'
            '<p class="app-loading-cover__message">Loading campaign player wiki...</p>'
            "</div>"
            '<div id="root">preview</div></body></html>'
        ),
        encoding="utf-8",
    )
    (dist_dir / "manifest.webmanifest").write_text("{\"name\":\"preview\"}", encoding="utf-8")
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "app.js").write_text("console.log('app-next-preview')", encoding="utf-8")
    app.config["APP_NEXT_DIST_DIR"] = dist_dir

    app_root_response = client.get("/app-next")
    assert app_root_response.status_code == 200
    app_root_html = app_root_response.get_data(as_text=True)
    assert "preview" in app_root_html
    assert 'data-theme="parchment"' in app_root_html
    assert 'id="app-loading-inline-styles"' in app_root_html
    assert 'id="app-loading-inline-script"' in app_root_html
    assert 'class="app-loading-cover"' in app_root_html
    assert "app-loading-cover--with-image" not in app_root_html

    app_root_slash_response = client.get("/app-next/")
    assert app_root_slash_response.status_code == 200
    assert "preview" in app_root_slash_response.get_data(as_text=True)

    asset_response = client.get("/app-next/assets/app.js")
    assert asset_response.status_code == 200
    assert asset_response.data == b"console.log('app-next-preview')"

    manifest_response = client.get("/app-next/manifest.webmanifest")
    assert manifest_response.status_code == 200
    assert manifest_response.data == b"{\"name\":\"preview\"}"

    route_response = client.get("/app-next/campaigns/linden-pass/session")
    assert route_response.status_code == 200
    route_html = route_response.get_data(as_text=True)
    assert "preview" in route_html
    assert (
        'class="app-loading-cover app-loading-cover--with-image app-loading-cover--media-ready"'
        in route_html
    )
    assert 'data-app-loading-media-urls=' in route_html
    assert 'data-app-loading-media-url="/campaigns/linden-pass/assets/' in route_html
    assert 'style="--app-loading-media: url(&quot;/campaigns/linden-pass/assets/' in route_html

    admin_route_response = client.get("/app-next/admin")
    assert admin_route_response.status_code == 200
    admin_route_html = admin_route_response.get_data(as_text=True)
    assert "preview" in admin_route_html
    assert "app-loading-cover--with-image" not in admin_route_html
    assert "app-loading-cover--media-ready" not in admin_route_html

    missing_asset_response = client.get("/app-next/assets/missing.js")
    assert missing_asset_response.status_code == 404


def test_frontend_index_includes_app_loading_shell_source() -> None:
    source = Path("frontend/index.html").read_text(encoding="utf-8")

    assert 'id="app-loading-inline-styles"' in source
    assert 'id="app-loading-inline-script"' in source
    assert 'class="app-loading-cover"' in source
    assert ".app-loading-cover__media" in source
    assert "html.app-loading #root" in source
    assert "html.app-loading::before" in source
    assert "html.app-loading::after" in source
    assert "failOpenDelayMs = 12000" in source
    assert "/app-next/assets/" in source
    assert "__cpwAppLoadingBegin" in source
    assert "__cpwAppLoadingReady" in source
    assert "function advanceAndPrepareNextLoadingMedia()" in source
    assert "function seedLoadingMediaFromCoverData()" in source
    assert "cpw:app-loading-active-media-url" in source
    assert "app-loading-media-ready" in source
    assert "function applyActiveLoadingMediaFromStorage()" in source
    assert "function loadingMediaUpdateIsSafe()" in source
    assert "if (!loadingMediaUpdateIsSafe())" in source
    assert "--app-loading-visible-media" in source
    assert "data-app-loading-prepared-media-url" in source
    assert "function setPreparedLoadingMedia(" in source
    assert "seedLoadingMediaFromCoverData();" in source
    assert "loadingCoverIsVisible() && cover.classList.contains(\"app-loading-cover--media-ready\")" in source
    assert "Loading campaign player wiki..." in source


def test_frontend_app_signals_loading_readiness_from_query_state_source() -> None:
    source = Path("frontend/src/AppShell.tsx").read_text(encoding="utf-8")
    link_helper_source = Path("frontend/src/campaignLinks.ts").read_text(encoding="utf-8")

    assert "useIsFetching" in source
    assert "useNavigate" in source
    assert "function useAppLoadingReadiness" in source
    assert "function appNextHrefToRouterPath" in link_helper_source
    assert "location.pathname" in source
    assert "previousLocationPathname" in source
    assert "window.__cpwAppLoadingBegin?.();" in source
    assert "window.__cpwAppLoadingReady?.();" in source
    assert "void navigate({ to: appNextHrefToRouterPath(item.href) as never });" in source
    assert "activeFetchCount > 0" in source
    assert "queryClient.isFetching() === 0" in source


def test_frontend_pilot_without_build_returns_not_found(client, app, tmp_path):
    # Avoid inheriting temp values from earlier test cases.
    app.config["APP_NEXT_PREVIEW_ENABLED"] = True
    missing_dist_dir = tmp_path / "missing-frontend-dist"
    missing_dist_dir.mkdir()
    (missing_dist_dir / "other.html").write_text("<!doctype html><html><body>no index</body></html>", encoding="utf-8")
    app.config["APP_NEXT_DIST_DIR"] = missing_dist_dir
    response = client.get("/app-next/")
    deep_route_response = client.get("/app-next/campaigns/linden-pass/session")
    assert response.status_code == 404
    assert deep_route_response.status_code == 404


def test_session_pane_no_player_wiki_lookup_widget_in_source() -> None:
    source = Path("frontend/src/routes/SessionRoutes.tsx").read_text(encoding="utf-8")
    shell_source = Path("frontend/src/AppShell.tsx").read_text(encoding="utf-8")
    session_pane_source = source[source.index("export function SessionPane({"):]

    assert "SessionPaneWikiLookup" not in session_pane_source
    assert "wikiQuery" not in session_pane_source
    assert "session-player-wiki-details" not in session_pane_source
    assert "Player wiki lookup" not in session_pane_source
    assert "Search player-visible wiki articles and read them here without leaving the live session page." not in session_pane_source
    assert "Type at least 2 letters to search." not in session_pane_source
    assert "Search published pages / systems" not in session_pane_source
    assert "className=\"wiki-result-stack\"" not in session_pane_source
    assert "className=\"wiki-preview\"" not in session_pane_source
    assert 'className="campaign-global-search__form"' in shell_source


def test_character_pane_non_read_selector_uses_flask_style_field_chrome_in_source() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    character_pane_source = source[source.index("export function CharacterPane({"):]
    selector_class_start = character_pane_source.index('className={isReadSurface ? "character-subpage-nav-card" : "character-selector-card"}')
    selector_start = character_pane_source.rfind("<div", 0, selector_class_start)
    selector_end = character_pane_source.index("{listQuery.isLoading ? <p className=\"status status-neutral\">Loading characters...</p> : null}", selector_start)
    selector_markup = character_pane_source[selector_start:selector_end]

    assert 'className={isReadSurface ? "character-subpage-nav-card" : "character-selector-card"}' in selector_markup
    assert "data-character-subpage-nav-card={isReadSurface ? \"\" : undefined}" in selector_markup
    assert '<label className="field" htmlFor="character-selector">' in selector_markup
    assert "<span>Character</span>" in selector_markup
    assert "id=\"character-selector\"" in selector_markup
    assert "selectCharacter(event.currentTarget.value || null)" in selector_markup
    assert "className=\"chat-label\"" not in selector_markup


def test_admin_user_detail_action_button_chrome_in_source() -> None:
    source = Path("frontend/src/routes/AdminRoutes.tsx").read_text(encoding="utf-8")
    admin_user_detail_source = source[source.index("export function AdminUserDetailPage() {"):]

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


def test_admin_user_delete_button_uses_ghost_button_class_in_source() -> None:
    source = Path("frontend/src/routes/AdminRoutes.tsx").read_text(encoding="utf-8")
    admin_user_detail_source = source[source.index("export function AdminUserDetailPage() {"):]

    delete_on_click = 'onClick={() => deleteUser.mutate()}'
    delete_button_start = admin_user_detail_source.rfind("<button", 0, admin_user_detail_source.index(delete_on_click))
    delete_button_end = admin_user_detail_source.index("</button>", delete_button_start) + len("</button>")
    delete_button_block = admin_user_detail_source[delete_button_start:delete_button_end]

    assert 'className="ghost-button"' in delete_button_block
    assert 'className="button-danger"' not in delete_button_block
    assert delete_on_click in delete_button_block
    assert (
        "disabled={mutationPending || deleteConfirm.trim().toLowerCase() !== data.managed_user.email.toLowerCase()}"
        in delete_button_block
    )
    assert "{deleteUser.isPending ? \"Deleting...\" : \"Delete user\"}" in delete_button_block


def test_admin_user_account_actions_are_flat_stack_in_source() -> None:
    source = Path("frontend/src/routes/AdminRoutes.tsx").read_text(encoding="utf-8")
    admin_user_detail_source = source[source.index("export function AdminUserDetailPage() {"):]

    heading_index = admin_user_detail_source.index("<h2>Account actions</h2>")
    account_actions_start = admin_user_detail_source.rfind('<article className="card admin-panel">', 0, heading_index)
    account_actions_end = admin_user_detail_source.index("</article>", heading_index) + len("</article>")
    account_actions_block = admin_user_detail_source[account_actions_start:account_actions_end]

    assert '<div className="admin-action-stack">' in account_actions_block
    assert 'className="admin-action-stack admin-action-groups"' not in account_actions_block

    assert "admin-action-groups" not in account_actions_block
    assert "admin-action-group" not in account_actions_block
    assert "admin-action-group__heading" not in account_actions_block
    assert "admin-danger-box" not in account_actions_block
    assert "Credential actions" not in account_actions_block
    assert "Account state" not in account_actions_block
    assert "Destructive actions" not in account_actions_block

    assert "Generate invite link" in account_actions_block
    assert "onClick={() => issueInvite.mutate()}" in account_actions_block
    assert "Generate password reset link" in account_actions_block
    assert "onClick={() => issuePasswordReset.mutate()}" in account_actions_block
    assert "Re-enable user" in account_actions_block
    assert "onClick={() => enableUser.mutate()}" in account_actions_block
    assert "Disable user" in account_actions_block
    assert "onClick={() => disableUser.mutate()}" in account_actions_block

    assert '<label className="field">' in account_actions_block
    assert "id=\"admin-delete-confirm-email\"" in account_actions_block
    assert "onClick={() => deleteUser.mutate()}" in account_actions_block
    assert (
        "disabled={mutationPending || deleteConfirm.trim().toLowerCase() !== data.managed_user.email.toLowerCase()}"
        in account_actions_block
    )
    assert "{deleteUser.isPending ? \"Deleting...\" : \"Delete user\"}" in account_actions_block
    assert "Delete user" in account_actions_block
    assert 'className="ghost-button"' in account_actions_block

    assert 'className="meta"' in account_actions_block
    assert "status-error admin-non-admin-note" not in account_actions_block
    assert "status-error" not in account_actions_block


def test_session_chat_logs_card_uses_flask_style_row_hooks_in_source() -> None:
    source = Path("frontend/src/routes/SessionDmPane.tsx").read_text(encoding="utf-8")
    chat_logs_start = source.index('<article className="card session-sidebar-card" id="session-chat-logs">')
    chat_logs_end = source.index('<aside className="session-sidebar">', chat_logs_start)
    chat_logs_source = source[chat_logs_start:chat_logs_end]

    assert 'className="plain-list session-log-list"' in chat_logs_source
    assert "session-log-list__row" in chat_logs_source
    assert "session-log-list__content" in chat_logs_source
    assert "Session log from ${formatTimestamp(entry.session.started_at)}" in chat_logs_source
    assert "Session ${entry.session.id}" in chat_logs_source
    assert "Closed sessions will appear here after the first live run." in chat_logs_source
    assert "session-log-list-row" not in chat_logs_source

    row_delete_on_click = "onClick={() => deleteLogMutation.mutate(entry.session.id)}"
    row_delete_button_start = chat_logs_source.rfind("<button", 0, chat_logs_source.index(row_delete_on_click))
    row_delete_button_end = chat_logs_source.index("</button>", row_delete_button_start) + len("</button>")
    row_delete_button_block = chat_logs_source[row_delete_button_start:row_delete_button_end]
    assert "className=\"ghost-button\"" in row_delete_button_block
    assert "className=\"button-danger\"" not in row_delete_button_block
    assert row_delete_on_click in row_delete_button_block
    assert "{deleteLogMutation.isPending ? \"Deleting...\" : \"Delete log\"}" in row_delete_button_block
    assert "disabled={deleteLogMutation.isPending}" in row_delete_button_block

    detail_delete_on_click = "onClick={() => deleteLogMutation.mutate(logQuery.data.session.id)}"
    detail_delete_button_start = chat_logs_source.rfind("<button", 0, chat_logs_source.index(detail_delete_on_click))
    detail_delete_button_end = chat_logs_source.index("</button>", detail_delete_button_start) + len("</button>")
    detail_delete_button_block = chat_logs_source[detail_delete_button_start:detail_delete_button_end]
    assert "{deleteLogMutation.isPending ? \"Deleting...\" : \"Delete log\"}" in detail_delete_button_block
    assert 'className="ghost-button"' in detail_delete_button_block
    assert "className=\"button-danger\"" not in detail_delete_button_block
    assert detail_delete_on_click in detail_delete_button_block
    assert "disabled={deleteLogMutation.isPending}" in detail_delete_button_block


def test_session_log_detail_delete_button_uses_ghost_button_class_in_source() -> None:
    source = Path("frontend/src/routes/SessionDmPane.tsx").read_text(encoding="utf-8")

    delete_on_click = "onClick={() => deleteLogMutation.mutate(logQuery.data.session.id)}"
    delete_button_start = source.rfind("<button", 0, source.index(delete_on_click))
    delete_button_end = source.index("</button>", delete_button_start) + len("</button>")
    delete_button_block = source[delete_button_start:delete_button_end]

    assert "{deleteLogMutation.isPending ? \"Deleting...\" : \"Delete log\"}" in delete_button_block
    assert 'className="ghost-button"' in delete_button_block
    assert 'className="button-danger"' not in delete_button_block
    assert delete_on_click in delete_button_block
    assert "disabled={deleteLogMutation.isPending}" in delete_button_block


def test_combat_action_chrome_in_source() -> None:
    source = Path("frontend/src/routes/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

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
    source = Path("frontend/src/routes/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

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


def test_campaign_control_page_cleanup_removes_flask_control_fallback_link() -> None:
    control_markup = Path("frontend/src/routes/CampaignControlPage.tsx").read_text(encoding="utf-8")

    assert "Flask Control" not in control_markup
    assert "Flask Control panel" not in control_markup
    assert "className=\"page-layout\"" in control_markup
    assert "className=\"article card\"" in control_markup
    assert "className=\"stack-form\"" in control_markup
    assert "className=\"field\"" in control_markup
    assert 'name={`${row.scope}_visibility`}' in control_markup
    assert "Save visibility" in control_markup
    assert "using default visibility" in control_markup
    assert "statusMessage ? <p className=\"status status-neutral\">{statusMessage}</p> : null" in control_markup
    assert "saveError ? <p className=\"status status-error\">{saveError}</p> : null" in control_markup
    assert "className=\"button-link\"" not in control_markup
    assert "className=\"hero-actions\"" not in control_markup
    assert "campaign-control-layout" not in control_markup
    assert "campaign-control-form" not in control_markup
    assert "campaign-control-grid" not in control_markup
    assert "campaign-control-row" not in control_markup
    assert "campaign-control-sidebar" not in control_markup
    assert "session-sidebar-card" not in control_markup
    assert "reference-stack" not in control_markup
    assert "help-detail-card" not in control_markup
    assert "Flask Control panel" not in control_markup
    assert "configured: {row.configured_visibility_label}" in control_markup
    assert "using default visibility" in control_markup
    assert re.search(
        r'\{row\.configured_visibility_label \?\s*\(\s*<>\s*Effective visibility: \{row\.effective_visibility_label\} \| configured: \{row\.configured_visibility_label\}',
        control_markup,
        flags=re.MULTILINE | re.DOTALL,
    ) is not None
    assert re.search(
        r'\(\s*<>\s*Effective visibility: \{row\.effective_visibility_label\} \| using default visibility</>\s*\)',
        control_markup,
        flags=re.MULTILINE | re.DOTALL,
    ) is not None
    assert "{rule.label}: {rule.description}" in control_markup

    source_css = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    assert ".campaign-control-layout" not in source_css
    assert ".campaign-control-panel" not in source_css
    assert ".campaign-control-form" not in source_css
    assert ".campaign-control-sidebar" not in source_css
    assert ".campaign-control-grid" not in source_css
    assert ".campaign-control-row" not in source_css
    assert ".campaign-control-row__header" not in source_css
    assert ".campaign-control-row__label" not in source_css
    assert ".campaign-control-row__meta" not in source_css
    assert ".campaign-control-hero" in source_css


def test_account_settings_page_removes_flask_account_fallback_link() -> None:
    account_settings_markup = Path("frontend/src/routes/AccountSettingsPage.tsx").read_text(encoding="utf-8")

    assert "Flask account" not in account_settings_markup
    assert 'className="ghost-button" href="/campaigns">' in account_settings_markup
    assert "className=\"stack-form\" onSubmit={handleThemeSubmit}>" in account_settings_markup
    assert "className=\"stack-form\" onSubmit={handleChatOrderSubmit}>" in account_settings_markup
    assert "Save theme" in account_settings_markup
    assert "Save chat order" in account_settings_markup
    assert "Save account settings" not in account_settings_markup
    assert "account-settings-actions" not in account_settings_markup
    theme_submit_match = re.search(
        r"const handleThemeSubmit[\s\S]*?saveThemeSettings\.mutate\((\{[\s\S]*?\})\);",
        account_settings_markup,
    )
    assert theme_submit_match is not None
    theme_payload = theme_submit_match.group(1)
    assert "theme_key: draftThemeKey" in theme_payload
    assert "session_chat_order" not in theme_payload
    chat_submit_match = re.search(
        r"const handleChatOrderSubmit[\s\S]*?saveChatSettings\.mutate\((\{[\s\S]*?\})\);",
        account_settings_markup,
    )
    assert chat_submit_match is not None
    chat_payload = chat_submit_match.group(1)
    assert "session_chat_order: draftChatOrder" in chat_payload
    assert "theme_key" not in chat_payload


def test_account_option_css_matches_flask_parity() -> None:
    source = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    def css_block(selector: str) -> str:
        selector_start = source.index(f"{selector} {{")
        selector_end = source.index("}", selector_start)
        return source[selector_start:selector_end]

    theme_option_block = css_block(".theme-option")
    assert "align-content: start;" not in theme_option_block

    theme_header_block = css_block(".theme-option__header")
    assert "align-items: center;" in theme_header_block
    assert "gap: 1rem;" in theme_header_block

    theme_status_block = css_block(".theme-option__status")
    assert "margin-left: 0.45rem;" in theme_status_block
    assert "display: block;" not in theme_status_block
    assert "margin-top" not in theme_status_block


def test_campaign_help_page_removes_flask_help_fallback() -> None:
    help_markup = Path("frontend/src/routes/CampaignHelpPage.tsx").read_text(encoding="utf-8")

    assert "Flask Help" not in help_markup
    assert "help-anchor-row" not in help_markup
    assert "campaign-help-account-actions" not in help_markup
    assert 'href={data.links.account_url}>Open Account</a>' in help_markup
    assert "href={data.links.sign_in_url}>Sign in</a>" in help_markup

    top_help_row_match = re.search(
        r'<div className="hero-actions" aria-label="Help sections">([\s\S]*?)</div>',
        help_markup,
    )
    assert top_help_row_match is not None
    top_help_row_markup = top_help_row_match.group(1)

    top_help_anchor_tags = [
        tag for tag in re.findall(r"<a[^>]*>", top_help_row_markup) if "${surface.anchor}" in tag
    ]
    assert len(top_help_anchor_tags) >= 1
    for tag in top_help_anchor_tags:
        class_match = re.search(r'className="([^"]+)"', tag)
        assert class_match is not None
        assert class_match.group(1) == "ghost-button"


def test_systems_entry_navigation_removes_open_flask_entry_link() -> None:
    source = Path("frontend/src/routes/SystemsRoutes.tsx").read_text(encoding="utf-8")
    systems_entry_start = source.index("export function SystemsEntryPage() {")
    systems_entry_markup = source[systems_entry_start:]

    assert "Open Flask entry" not in systems_entry_markup
    assert "Systems landing" in systems_entry_markup
    assert "Source page" in systems_entry_markup
    assert "Source category" in systems_entry_markup
    assert "Entry Management" in systems_entry_markup


def test_combat_empty_tracker_prompt_uses_current_surface_wording() -> None:
    source = Path("frontend/src/routes/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

    assert "Use the Encounter controls or DM controls to seed the encounter for now." in combat_page_source
    assert "Use the Flask DM controls to seed the encounter for now." not in combat_page_source


def test_combat_turn_focus_dm_status_chrome_in_source() -> None:
    source = Path("frontend/src/routes/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

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
    source = Path("frontend/src/routes/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

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
    source = Path("frontend/src/routes/CombatPage.tsx").read_text(encoding="utf-8")
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
    source = Path("frontend/src/routes/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

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
    source = Path("frontend/src/routes/CharacterAuthoringRoutes.tsx").read_text(encoding="utf-8")

    def component_source(component_name: str) -> str:
        return _extract_function_component_source(source, component_name)

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
    source = Path("frontend/src/routes/CharacterAuthoringRoutes.tsx").read_text(encoding="utf-8")

    def component_source(component_name: str) -> str:
        return _extract_function_component_source(source, component_name)

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


def test_character_supported_hero_links_preserve_supported_nav_while_hiding_flask_fallbacks() -> None:
    source = Path("frontend/src/routes/CharacterAuthoringRoutes.tsx").read_text(encoding="utf-8")

    def component_source(component_name: str) -> str:
        return _extract_function_component_source(source, component_name)

    def hero_section(component_name: str) -> str:
        component = component_source(component_name)
        hero_start = component.index('<section className="hero')
        hero_end = component.index("</section>", hero_start) + len("</section>")
        return component[hero_start:hero_end]

    create_hero = hero_section("CharacterCreatePage")
    assert "Flask create" not in create_hero
    assert "Back to roster" in create_hero
    assert "Import existing" in create_hero

    manual_hero = hero_section("CharacterXianxiaManualImportPage")
    assert "Flask import" not in manual_hero
    assert "Back to roster" in manual_hero
    assert "Import existing" not in manual_hero

    editor_hero = hero_section("CharacterAdvancedEditorPage")
    assert "Flask editor" not in editor_hero
    assert re.search(r">\s*Back to sheet\s*</a>", editor_hero) is not None
    assert '<span className="meta">' in editor_hero

    progression_hero = hero_section("CharacterProgressionRepairPage")
    assert "Flask repair" not in progression_hero
    assert "Back to sheet" in progression_hero
    assert '<p className="meta">' in progression_hero

    retraining_hero = hero_section("CharacterRetrainingPage")
    assert "Flask retraining" not in retraining_hero
    assert "Back to sheet" in retraining_hero
    assert "Advanced Editor" in retraining_hero

    level_up_hero = hero_section("CharacterLevelUpPage")
    assert "Flask level-up" not in level_up_hero
    assert "Back to sheet" in level_up_hero

    cultivation_hero = hero_section("CharacterCultivationPage")
    assert "Flask Cultivation" not in cultivation_hero
    assert "Back to sheet" in cultivation_hero
    assert "Martial Arts" in cultivation_hero
    assert "Techniques" in cultivation_hero
    assert "Resources" in cultivation_hero
    assert "Realm Ascension" in cultivation_hero


def test_character_roster_page_copy_and_grid_class_parity_in_source() -> None:
    roster_source = Path("frontend/src/routes/CharacterRosterPage.tsx").read_text(encoding="utf-8")

    assert (
        "Open a player sheet in read mode for play, or start a new in-app PHB level 1 character when you need native sheet data instead of an imported PDF."
        in roster_source
    )
    assert (
        "Open a player sheet in read mode for play, or start a new native Xianxia character record for this campaign."
        in roster_source
    )
    assert (
        "Open a player sheet for read mode, use inline state controls when authorized, and use Advanced Editor for larger sheet changes."
        in roster_source
    )
    assert (
        "Open player sheets, use the shared inline state controls, and keep larger authoring workflows in Flask while Gen2 parity grows."
        not in roster_source
    )
    assert '<section className="grid">' in roster_source
    assert 'className="character-roster-grid"' not in roster_source


def test_character_roster_heading_visibility_is_gated_by_create_or_unsupported_system_in_source() -> None:
    roster_source = Path("frontend/src/routes/CharacterRosterPage.tsx").read_text(encoding="utf-8")

    assert re.search(
        r"const shouldShowRosterToolsHeading\s*=\s*hasCreateCharacterLink \|\| data\?\.tools\?\.native_character_create_supported === false;",
        roster_source,
    ) is not None
    assert re.search(
        r"\{shouldShowRosterToolsHeading \? \(\s*<div className=\"section-heading\">",
        roster_source,
        re.S,
    ) is not None
    assert (
        "Native character creation and progression stay hidden here for campaigns outside the current DND-5E in-app toolset."
        in roster_source
    )
    assert (
        "hasCreateCharacterLink ? \"Roster tools\" : \"Roster\"" in roster_source
    )
    assert re.search(
        r'<section className="card search-card character-roster-tools">\s*<div className="section-heading">',
        roster_source,
        re.S,
    ) is None


def test_character_roster_card_meta_join_and_stats_divs_in_source() -> None:
    roster_source = Path("frontend/src/routes/CharacterRosterPage.tsx").read_text(encoding="utf-8")

    card_start = roster_source.index('<article className="card character-card"')
    card_end = roster_source.index("</article>", card_start) + len("</article>")
    card_markup = roster_source[card_start:card_end]
    stats_markup = card_markup[card_markup.index('<div className="character-card__stats">'): card_markup.index("</a>", card_markup.index("className=\"button-link\""))]

    assert 'className="character-card__meta"' in card_markup
    assert 'join(" · ")' in card_markup
    assert 'join(" | ")' not in card_markup

    assert "<article>" not in stats_markup
    assert '<div className="character-card__stats">' in stats_markup
    assert card_markup.count("className=\"character-card__top\"") == 1
    assert 'className="button-link"' in card_markup


def test_character_roster_empty_state_copy_is_exact_in_source() -> None:
    source = Path("frontend/src/routes/CharacterRosterPage.tsx").read_text(encoding="utf-8")
    assert (
        "This campaign does not currently have any active player sheets available in the app."
        in source
    )
    assert "This campaign does not currently have active player sheets available in the app." not in source


def test_character_roster_card_css_hooks_match_flask_targets() -> None:
    source = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    def css_block(selector: str) -> str:
        selector_start = source.index(f"{selector} {{")
        selector_end = source.index("}", selector_start)
        return source[selector_start:selector_end]

    assert "display: grid;" in css_block(".character-card")
    assert "gap: 1rem;" in css_block(".character-card")
    assert ".character-card__meta {" in source
    assert "margin: 0;" in css_block(".character-card__meta")
    assert "color: var(--muted);" in css_block(".character-card__meta")

    character_card_stats_block = css_block(".character-card__stats")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in character_card_stats_block
    assert "gap: 0.75rem;" in character_card_stats_block
    assert ".character-card__stats article" not in source
    assert "padding: 0.8rem 0.9rem;" in css_block(".character-card__stats div")
    assert "border: 1px solid var(--border);" in css_block(".character-card__stats div")
    assert "border-radius: 16px;" in css_block(".character-card__stats div")


def test_grid_minimum_card_size_is_flask_260px_and_character_roster_grid_selector_is_removed() -> None:
    source = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));" in source
    assert ".character-roster-grid" not in source


def test_character_form_actions_do_not_convert_non_targeted_builder_rows() -> None:
    source = Path("frontend/src/routes/CharacterAuthoringRoutes.tsx").read_text(encoding="utf-8")

    def component_source(component_name: str) -> str:
        return _extract_function_component_source(source, component_name)

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
    source = Path("frontend/src/routes/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

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
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
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
    source = Path("frontend/src/components/DmArticleCreator.tsx").read_text(encoding="utf-8")
    component_start = source.index("function DmArticleCreator({")
    creator_markup = source[component_start:]

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


def test_wiki_home_uses_section_cards_while_detail_pages_keep_section_nav() -> None:
    source = Path("frontend/src/routes/WikiRoutes.tsx").read_text(encoding="utf-8")
    nav_source = _extract_component_source(
        source,
        "function WikiSectionNav({",
        "function WikiSectionBrowse({",
    )
    home_page_source = _extract_component_source(
        source,
        "export function WikiHomePage() {",
        "export function WikiSectionPage() {",
    )
    section_page_source = _extract_component_source(
        source,
        "export function WikiSectionPage() {",
        "export function WikiArticlePage() {",
    )
    article_page_source = source[source.index("export function WikiArticlePage() {"):]
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    assert 'className="wiki-section-nav"' in nav_source
    assert 'aria-label="Wiki sections"' in nav_source
    assert 'href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}' in nav_source
    assert 'aria-current={isActive ? "page" : undefined}' in nav_source
    assert 'title={`${section.page_count} page${section.page_count === 1 ? "" : "s"}`}' in nav_source

    assert "function WikiHomeSectionGrid({" in nav_source
    assert 'className="wiki-home-section-grid"' in nav_source
    assert 'aria-label="Campaign wiki sections"' in nav_source
    assert 'className="card wiki-home-section-card"' in nav_source
    assert 'className="wiki-home-section-card__icon"' in nav_source
    assert "WIKI_SECTION_ICON_BY_SLUG" in nav_source
    assert "overview: \"book\"" not in nav_source
    assert "spells: \"wand\"" in nav_source
    assert "mechanics: \"cog\"" in nav_source
    assert 'targetSubdir: "overview"' not in source
    assert 'defaultType: "overview"' not in source

    assert "<WikiHomeSectionGrid" in home_page_source
    assert "sections={data.section_navigation}" in home_page_source
    assert "<WikiSectionNav" not in home_page_source
    assert "wiki-overview-card" not in home_page_source
    assert "data.overview_page.body_html" not in home_page_source

    assert "sections={data.section_navigation}" in section_page_source
    assert "activeSectionSlug={data.section_slug}" in section_page_source
    assert "sections={data?.section_navigation ?? []}" in article_page_source
    assert "activeSectionSlug={page.section_slug}" in article_page_source
    assert 'className={hasBacklinks ? "page-layout wiki-article-page" : "page-layout wiki-article-page wiki-article-page--single"}' in article_page_source

    assert "<h2>Context</h2>" not in article_page_source
    assert "Campaign:" not in article_page_source
    assert "Section:" not in article_page_source
    assert "campaignContextLink" not in article_page_source
    assert "sectionContextLink" not in article_page_source

    assert ".wiki-section-nav" in styles
    assert ".wiki-home-section-grid" in styles
    assert "grid-template-columns: repeat(6, minmax(0, 1fr));" in styles
    assert ".wiki-home-section-card__icon-svg" in styles
    assert ".wiki-article-page--single" in styles


def test_dm_content_player_wiki_editor_fields_use_flask_style_labels_in_source() -> None:
    source = Path("frontend/src/routes/DmContentPage.tsx").read_text(encoding="utf-8")
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
    source = Path("frontend/src/routes/DmContentSystemsLane.tsx").read_text(encoding="utf-8")
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
    source = Path("frontend/src/routes/DmContentPage.tsx").read_text(encoding="utf-8")

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
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
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
    section_end = source.index('{isXianxia && activeCharacterSection === "personal" ? (', section_start)
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


def test_character_xianxia_resources_section_uses_flask_style_resource_cards() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    resources_start = source.index('{isXianxia && activeCharacterSection === "resources" ? (')
    resources_end = source.index('{isXianxia && activeCharacterSection === "skills" ? (', resources_start)
    resources_markup = source[resources_start:resources_end]

    assert 'Current {pool.current} / Max {pool.max}' in source
    assert '{pool.temp ? <p className="meta">Temporary {pool.label}: {pool.temp}</p> : null}' in source
    assert 'className="resource-grid"' in resources_markup
    assert 'className="resource-card"' in resources_markup
    assert 'className="resource-card__value"' in resources_markup
    assert 'Current {xianxiaDao.current} / Max {xianxiaDao.max}' in resources_markup
    assert '<h3>Dao</h3>' in resources_markup
    assert '<h3>Insight</h3>' in resources_markup
    assert 'className="meta">Spent {readNumber(xianxiaInsight.spent, 0)}</p>' in resources_markup
    assert 'id="session-active-state"' in resources_markup

    assert 'className="character-card-grid"' not in resources_markup
    assert 'className="character-state-card"' not in resources_markup
    assert 'className="inline-two-col"' not in resources_markup
    assert 'className="chat-label"' not in resources_markup


def test_character_xianxia_skills_section_uses_flask_style_skill_pills() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isXianxia && activeCharacterSection === "skills" ? (')
    section_end = source.index('{isXianxia && activeCharacterSection === "equipment" ? (', section_start)
    skills_markup = source[section_start:section_end]

    assert 'className="skill-grid"' in skills_markup
    assert 'className="skill-pill skill-pill--proficient"' in skills_markup
    assert '<span className="meta">Trained</span>' in skills_markup
    assert 'className="detail-card"' in skills_markup
    assert "No trained skills are recorded on this sheet yet." in skills_markup
    assert 'id="xianxia-skills-guardrail"' in skills_markup
    assert "Skill use guardrails" in skills_markup
    assert 'className="button-link subtle"' in skills_markup

    assert 'className="ability-grid"' not in skills_markup
    assert 'className="character-state-card"' not in skills_markup
    assert 'className="character-card-grid"' not in skills_markup
    assert 'className="plain-list compact-list"' not in skills_markup
    assert 'className="status status-neutral"' not in skills_markup
    assert 'className="inline-two-col"' not in skills_markup
    assert 'className="chat-label"' not in skills_markup


def test_character_xianxia_equipment_section_uses_flask_style_read_section_shape() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isXianxia && activeCharacterSection === "equipment" ? (')
    section_end = source.index('{isXianxia && activeCharacterSection === "inventory" ? (', section_start)
    section_markup = source[section_start:section_end]

    assert 'className="detail-grid"' in section_markup
    assert 'className="detail-card"' in section_markup
    assert "Defense calculation" in section_markup
    assert 'className="plain-list slot-list"' in section_markup
    assert "Manual armor bonus" in section_markup
    assert "Constitution" in section_markup

    assert "Necessary weapons" in section_markup
    assert "No necessary weapons are recorded on this sheet yet." in section_markup
    assert "Necessary tools" in section_markup
    assert "No necessary tools are recorded on this sheet yet." in section_markup
    assert "Equipped inventory" in section_markup
    assert "Armor is displayed here only; Defense still uses the manual armor bonus above." in section_markup
    assert "No equippable inventory is currently marked equipped." in section_markup

    assert 'className="stat-grid"' not in section_markup
    assert 'className="character-card-grid"' not in section_markup
    assert 'className="character-state-card"' not in section_markup
    assert 'className="status status-neutral"' not in section_markup
    assert 'renderXianxiaRecordCard(record, "Necessary Weapon")' not in section_markup
    assert 'renderXianxiaRecordCard(record, "Necessary Tool")' not in section_markup
    assert 'className="chat-label"' not in section_markup
    assert 'className="inline-two-col"' not in section_markup


def test_character_xianxia_quick_reference_section_uses_flask_style_read_chrome() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isXianxia && activeCharacterSection === "quick-reference" ? (')
    section_end = source.index('{isXianxia && activeCharacterSection === "martial-arts" ? (', section_start)
    section_markup = source[section_start:section_end]

    assert 'id: "xianxia-quick-reference"' in section_markup
    assert 'className="glance-grid"' in section_markup
    assert 'className="glance-card"' in section_markup
    assert 'id="xianxia-check-formula"' in section_markup
    assert 'id="xianxia-difficulty-states"' in section_markup
    assert 'id="xianxia-action-count"' in section_markup
    assert 'id="xianxia-defense-derivation"' in section_markup
    assert 'id="xianxia-effort-damage"' in section_markup
    assert 'id="xianxia-active-state-reminders"' in section_markup
    assert 'className="detail-grid"' in section_markup
    assert 'className="detail-card"' in section_markup
    assert "Check formula" in section_markup
    assert "Difficulty states" in section_markup
    assert "Action count" in section_markup
    assert "Defense calculation" in section_markup
    assert "Effort damage" in section_markup
    assert "Active Stance and Aura" in section_markup

    assert 'className="stat-grid"' not in section_markup
    assert 'className="character-card-grid"' not in section_markup
    assert 'className="character-state-card"' not in section_markup
    assert 'className="plain-list compact-list"' not in section_markup
    assert 'className="status status-neutral"' not in section_markup
    assert 'className="inline-two-col"' not in section_markup
    assert 'className="chat-label"' not in section_markup


def test_character_xianxia_quick_reference_section_renders_flask_rule_reference_subsections() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isXianxia && activeCharacterSection === "quick-reference" ? (')
    section_end = source.index('{isXianxia && activeCharacterSection === "martial-arts" ? (', section_start)
    section_markup = source[section_start:section_end]

    assert 'id="xianxia-honor-interactions"' in section_markup
    assert "Honor interactions" in section_markup
    assert "Interaction modifier" in section_markup
    assert "Honor context" in section_markup
    assert "Honor interactions = " in section_markup
    assert "xianxiaHonorInteractions.status_label" in section_markup

    assert 'id="xianxia-skill-use-guardrails"' in section_markup
    assert "Skill use guardrails" in section_markup
    assert 'className="button-link subtle"' in section_markup

    assert 'id="xianxia-rule-text-references"' in section_markup
    assert "Rules text references" in section_markup
    assert "xianxiaRuleTextReferences" in section_markup

    assert 'id="xianxia-stance-break"' in section_markup
    assert "Stance Break" in section_markup
    assert "Current Stance" in section_markup
    assert "xianxiaStanceBreak" in section_markup
    assert "xianxiaStanceBreak.status_label" in section_markup

    assert 'className="character-state-card"' not in section_markup
    assert 'className="plain-list compact-list"' not in section_markup
    assert 'className="status status-neutral"' not in section_markup
    assert 'className="inline-two-col"' not in section_markup
    assert 'className="chat-label"' not in section_markup


def test_character_xianxia_martial_arts_section_uses_flask_feature_row_chrome() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isXianxia && activeCharacterSection === "martial-arts" ? (')
    section_end = source.index('{isXianxia && activeCharacterSection === "techniques" ? (', section_start)
    section_markup = source[section_start:section_end]

    assert 'id: "xianxia-martial-arts"' in section_markup
    assert 'className="feature-groups"' in section_markup
    assert 'className="feature-group"' in section_markup
    assert 'className="feature-stack"' in section_markup
    assert 'className="feature-row"' in section_markup
    assert 'className="feature-row__header"' in section_markup
    assert "Martial Art details" in section_markup
    assert "Rank progress" in section_markup
    assert 'className="skill-grid"' in section_markup
    assert 'skill-pill skill-pill--proficient' in section_markup
    assert "Learned rank abilities" in section_markup
    assert "Learned ranks" in section_markup
    assert 'className="feature-detail"' in section_markup
    assert 'className="article-body article-body--compact"' in section_markup
    assert "numberFromUnknown(rank.insight_cost)" in section_markup
    assert "No Martial Arts are recorded on this sheet yet." in section_markup

    assert 'className="character-card-grid"' not in section_markup
    assert 'renderXianxiaRecordCard(record, "Martial Art")' not in section_markup
    assert 'className="character-state-card"' not in section_markup
    assert 'className="status status-neutral"' not in section_markup
    assert 'className="inline-two-col"' not in section_markup
    assert 'className="chat-label"' not in section_markup


def test_character_xianxia_techniques_section_uses_flask_chrome_parity() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    section_start = source.index('{isXianxia && activeCharacterSection === "techniques" ? (')
    section_end = source.index('{isXianxia && activeCharacterSection === "resources" ? (', section_start)
    section_markup = source[section_start:section_end]

    assert 'id="xianxia-techniques"' in section_markup
    assert "<h2>Techniques</h2>" in section_markup
    assert 'className="detail-grid"' in section_markup

    assert "Known Generic Techniques" in section_markup
    assert "No Generic Techniques are recorded on this sheet yet." in section_markup
    assert "Technique details" in section_markup

    assert "Basic Actions" in section_markup
    assert "No Basic Action Systems entries are available for this campaign." in section_markup
    assert "Action details" in section_markup
    assert "No Basic Action Systems entries are available for this campaign." in section_markup

    assert "approval-record__heading" in section_markup
    assert "Approval state" in section_markup
    assert "xianxia-approval-" in section_markup
    assert 'id={groupId}' in section_markup

    assert "Prepared Dao Immolating Techniques" in section_markup
    assert "No prepared Dao Immolating Technique notes yet." in section_markup
    assert (
        re.search(
            r'const insightCost = isDaoImmolatingUseRecords\s*\?\s*readNumber\(data\.insight_cost, 10\)',
            section_markup,
        )
        is not None
    )
    assert "readNumber(data.insight_cost, 0)" not in section_markup

    assert 'id="xianxia-dao-immolating-use-request"' in section_markup
    assert "Ad Hoc Dao Immolating Use Request" in section_markup
    assert 'className="session-field" htmlFor="xianxia-dao-request-name"' in section_markup
    assert 'className="session-field" htmlFor="xianxia-dao-prepared-record"' in section_markup
    assert 'className="session-field" htmlFor="xianxia-dao-request-notes"' in section_markup
    assert (
        re.search(
            r'<label[^>]*htmlFor={`xianxia-dao-use-notes-\$\{useRecordDraftKey\}`}[^>]*>\s*<span>Use notes</span>\s*<textarea',
            section_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label[^>]*htmlFor="xianxia-dao-prepared-record"[^>]*>\s*<span>Prepared note</span>\s*<select',
            section_markup,
        )
        is not None
    )
    assert (
        re.search(
            r'<label[^>]*htmlFor="xianxia-dao-request-notes"[^>]*>\s*<span>Request notes</span>\s*<textarea',
            section_markup,
        )
        is not None
    )
    assert re.search(
        r'<label className="session-field" htmlFor="xianxia-dao-prepared-record">\s*<span>Prepared note</span>\s*</label>\s*<select',
        section_markup,
    ) is None
    assert re.search(
        r'<label className="session-field" htmlFor="xianxia-dao-request-notes">\s*<span>Request notes</span>\s*</label>\s*<textarea',
        section_markup,
    ) is None
    assert 'className="button-link"' in section_markup

    assert 'className="renderXianxiaRecordCard"' not in section_markup
    assert 'renderXianxiaRecordCard(record, "Generic Technique")' not in section_markup
    assert 'renderXianxiaRecordCard(record, "Basic Action")' not in section_markup
    assert "renderXianxiaApprovalRecordCard" not in section_markup
    assert 'className="character-card-grid"' not in section_markup
    assert 'className="status status-neutral"' not in section_markup
    assert 'className="inline-two-col"' not in section_markup
    assert 'className="chat-label"' not in section_markup


def test_character_xianxia_personal_section_uses_flask_style_reference_stack_and_detail_cards() -> None:
    source = Path("frontend/src/components/CharacterPersonalSection.tsx").read_text(encoding="utf-8")
    personal_section_markup = source

    assert 'className="read-section" id="xianxia-personal"' in personal_section_markup
    assert "<h2>Personal</h2>" in personal_section_markup
    assert 'className="reference-stack"' in personal_section_markup
    assert 'id="character-personal-portrait"' in personal_section_markup
    assert "Physical Description" in personal_section_markup
    assert "Background" in personal_section_markup
    assert 'className="detail-card"' in personal_section_markup
    assert 'className="article-body article-body--compact"' in personal_section_markup
    assert "dangerouslySetInnerHTML" in personal_section_markup
    assert "No personal details yet." in personal_section_markup
    assert 'id="character-personal-portrait-manager"' not in personal_section_markup

    assert 'className="stat-grid"' not in personal_section_markup
    assert 'className="character-state-card"' not in personal_section_markup
    assert 'className="inline-two-col"' not in personal_section_markup
    assert 'className="chat-label"' not in personal_section_markup
    assert 'profile.species' not in personal_section_markup
    assert 'profile.background' not in personal_section_markup


def test_character_generic_system_summary_section_uses_detail_grid_cards() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    summary_section_start = source.index('<section className="read-section" id="character-system-summary">')
    generic_summary_end = source.index("</section>", summary_section_start)
    generic_summary_markup = source[summary_section_start:generic_summary_end]

    assert '<section className="read-section" id="character-system-summary">' in generic_summary_markup
    assert 'className="detail-grid"' in generic_summary_markup
    assert '<article className="detail-card">' in generic_summary_markup
    assert "<h3>Current HP</h3>" in generic_summary_markup
    assert "<h3>Temp HP</h3>" in generic_summary_markup
    assert '<strong>{String(vitals.current_hp ?? "--")}</strong>' in generic_summary_markup
    assert '<strong>{String(vitals.temp_hp ?? "--")}</strong>' in generic_summary_markup

    assert 'className="stat-grid"' not in generic_summary_markup


def test_character_pane_status_messages_use_toast_overlay() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    feedback_source = Path("frontend/src/components/feedback.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    pane_start = source.index("export function CharacterPane(")
    pane_markup = source[pane_start:]

    assert "const TOAST_DISMISS_MS = 3600;" in feedback_source
    assert "function ToastNotice" in feedback_source
    assert 'className={`toast-notice toast-notice--${tone}`}' in feedback_source
    assert 'role="status" aria-live="polite"' in feedback_source
    assert "window.setTimeout(() => setStatusMessage(null), TOAST_DISMISS_MS)" in pane_markup
    assert "setRestPreview(response.preview);" in pane_markup
    assert 'setStatusMessage(`${response.preview.label} preview loaded.`);' not in pane_markup
    assert "preview loaded." not in pane_markup
    assert "<ToastNotice message={statusMessage} />" in pane_markup
    assert 'statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null' not in pane_markup
    assert ".toast-notice {" in styles
    assert "position: fixed;" in styles
    assert "z-index: 1200;" in styles
    assert "animation: toast-notice-fade 3600ms ease forwards;" in styles
    assert "@keyframes toast-notice-fade" in styles


def test_character_dnd_overview_section_uses_flask_style_glance_rows() -> None:
    route_source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    section_markup = Path("frontend/src/components/CharacterDndOverviewSection.tsx").read_text(encoding="utf-8")

    assert '<h2>At a glance</h2>' in section_markup
    assert 'className={`glance-grid glance-grid--row glance-grid--quick-row-${rowIndex + 1}`}' in section_markup
    assert 'className="glance-card"' in section_markup
    assert 'className="meta"' in section_markup
    assert "readString(stat.value, \"--\")" in section_markup
    assert '<h2>Overview</h2>' not in section_markup
    assert 'className="stat-grid"' not in section_markup
    assert "rawOverviewStatRows.length > 0" in route_source
    assert "hasOverviewStatRows ? (" in section_markup
    assert 'className="glance-grid">' in section_markup


def test_character_dnd_inventory_currency_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
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
    source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
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


def test_character_dnd_abilities_and_skills_section_uses_compact_skill_proficiency_cues() -> None:
    source = Path("frontend/src/components/CharacterDndAbilitySkillsSection.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    section_markup = source

    assert 'className="ability-grid ability-grid--skills"' in section_markup
    assert 'className="ability-card ability-card--skills"' in section_markup
    assert 'className="ability-card__name"' in section_markup
    assert 'className="ability-card__score"' in section_markup
    assert 'className="ability-card__values"' in section_markup
    assert 'className="ability-card__value"' in section_markup
    assert 'className="plain-list ability-skill-list"' in section_markup
    assert "ability-skill-list__item" in section_markup
    assert "ability-skill-list__item--proficient" in section_markup
    assert "ability-skill-list__item--expertise" in section_markup
    assert 'className="ability-skill-list__pill"' in section_markup
    assert 'className="ability-skill-list__name"' in section_markup
    assert 'className="ability-skill-list__bonus"' in section_markup
    assert 'className="visually-hidden"' in section_markup
    assert '<span>{readString(skillRecord.name)}</span>' not in section_markup
    assert '<strong>{readString(skillRecord.bonus)}</strong>' not in section_markup
    assert '<span className="meta">{proficiencyLabel}</span>' not in section_markup
    assert 'className="card-kicker"' not in section_markup
    assert "No linked skills" in section_markup
    assert 'className="detail-cluster"' in section_markup
    assert 'className="detail-card"' in section_markup
    assert "No ability or skill details are recorded on this sheet yet." in section_markup
    assert ".ability-grid--skills {" in styles
    assert ".ability-card__name {" in styles
    assert ".ability-card__value strong {" in styles
    assert ".ability-skill-list__pill {" in styles
    assert ".ability-skill-list__item--proficient .ability-skill-list__pill" in styles
    assert ".ability-skill-list__item--expertise .ability-skill-list__pill" in styles

    assert 'className="character-state-card"' not in section_markup
    assert 'className="stat-grid"' not in section_markup
    assert "Passive Perception" not in section_markup
    assert "Passive Insight" not in section_markup
    assert "Passive Investigation" not in section_markup


def test_character_controls_section_keeps_flask_card_form_chrome() -> None:
    source = Path("frontend/src/components/CharacterControlsSection.tsx").read_text(encoding="utf-8")

    assert 'className="read-section character-controls-panel"' in source
    assert 'className="detail-grid character-controls-grid"' in source
    assert 'className="detail-card"' in source
    assert 'className="ghost-button"' in source
    assert 'className="stack-form"' in source
    assert 'className="field"' in source
    assert "Player controls" in source
    assert "Current owner" in source
    assert "Open user record" in source
    assert "Save assignment" in source
    assert "Clear assignment" in source
    assert 'className="detail-card character-controls-card--danger"' in source
    assert "Delete character" in source
    assert "Type <code>{characterSlug}</code> to confirm" in source

    assert 'className="character-state-card"' not in source
    assert 'className="button-row"' not in source
    assert 'className="button button-secondary"' not in source
    assert "Flask Controls" not in source


def test_character_dnd_equipment_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/components/CharacterDndEquipmentSection.tsx").read_text(encoding="utf-8")
    section_markup = source

    summary_end = section_markup.index('className="detail-card character-edit-row"')
    summary_markup = section_markup[:summary_end]

    assert 'className="detail-grid"' in summary_markup
    assert 'className="detail-card"' in summary_markup
    assert 'className="stat-grid"' not in section_markup
    assert '<h3>Attuned items</h3>' in summary_markup
    assert '<h3>Equipped items</h3>' in summary_markup
    assert '{equipmentState.attuned_count} / {equipmentState.max_attuned_items}' in summary_markup
    assert '<strong>{equipmentState.equipped_count}</strong>' in summary_markup
    assert (
        'Attunement is separate from equipped state and usually has room for up to {equipmentState.max_attuned_items} items.'
        in summary_markup
    )
    assert (
        'Armor and magic items use equipped state; weapons also track an applicable wielding mode.'
        in summary_markup
    )

    assert 'className="equipment-state-grid"' in section_markup
    assert 'id={isCombatSurface ? "combat-character-equipment-state" : "character-equipment-state"}' in section_markup
    assert 'className="detail-card character-edit-row"' in section_markup
    assert 'className="section-heading"' in section_markup
    assert 'className="stack-form"' in section_markup
    assert 'data-character-autosubmit' in section_markup
    assert 'data-character-sheet-edit-form="equipment-state"' in section_markup
    assert 'className="detail-grid"' in section_markup
    assert 'className="checkbox-label"' in section_markup
    assert 'Arcane Armor enabled' in section_markup
    assert 'name="enabled"' in section_markup
    assert "isFeatureStateSaving || !canEdit" in section_markup
    assert "isEquipmentStateSaving || !canEdit" in section_markup
    assert 'name="weapon_wield_mode"' in section_markup
    assert 'name="is_equipped"' in section_markup
    assert 'name="is_attuned"' in section_markup
    assert 'className="ghost-button item-detail-button"' in section_markup
    assert 'className="character-card-grid"' not in section_markup
    assert 'className="character-state-card"' not in section_markup
    assert 'className="equipment-state-form"' not in section_markup
    assert 'className="chat-label"' not in section_markup
    assert 'Save equipment state' not in section_markup
    assert 'Save feature state' not in section_markup
    assert '<p className="meta">Requires attunement</p>' not in section_markup
    assert 'item.attunement_hint !== "Requires attunement"' in section_markup


def test_character_dnd_resources_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/components/CharacterDndResourcesSection.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    resources_markup = source

    assert 'className={`resource-grid resource-grid--compact${canEdit ? " resource-grid--editable" : ""}`}' in resources_markup
    assert 'className="resource-card' in resources_markup
    assert 'className="session-inline-form session-inline-form--compact-resource"' in resources_markup
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
    assert ".visually-hidden" in styles
    assert ".resource-grid {" in styles
    assert ".character-sheet .resource-grid--compact," in styles
    assert ".character-sheet .resource-grid--editable" in styles
    assert "grid-template-columns: repeat(3, minmax(0, min(24rem, 100%)));" in styles
    assert ".resource-card {" in styles
    assert ".session-resource-card--compact" in styles
    assert ".session-inline-form--compact-resource" in styles

    assert 'className="character-card-grid"' not in resources_markup
    assert 'className="character-state-card"' not in resources_markup
    assert 'className="compact-state-form"' not in resources_markup
    assert 'className="chat-label"' not in resources_markup
    assert 'Save' not in resources_markup


def test_character_dnd_spell_slots_section_uses_flask_style_row_form_chrome() -> None:
    route_source = Path("frontend/src/routes/CharacterPane.tsx").read_text(encoding="utf-8")
    source = Path("frontend/src/components/CharacterDndSpellsSection.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    section_markup = source

    controls_start = section_markup.index('{spellSlots.length ? (')
    controls_end = section_markup.index('{presentedSpells.length ? (', controls_start)
    slot_controls_markup = section_markup[controls_start:controls_end]
    presented_start = section_markup.index('{presentedSpells.length ? (')
    presented_fallback_start = section_markup.index(') : spells.length ? (', presented_start)
    presented_markup = section_markup[presented_start:presented_fallback_start]

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
            r'<button type="submit" className="visually-hidden" disabled=\{isSaving \|\| !canEdit\}>\s*Update \{slotLabel\}\s*</button>',
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

    assert 'className="detail-grid spellcasting-summary-grid"' in section_markup
    assert "spellcasting-class-card" in section_markup
    assert "<h3>Spellcasting</h3>" in section_markup
    assert "Ability:" in section_markup
    assert "Save DC:" in section_markup
    assert "Attack:" in section_markup

    assert "groupSpellsByLevel" in route_source
    assert "presentedSpellGroups" in section_markup
    assert "rawSpellGroups" in section_markup
    assert 'className="spell-level-groups"' in section_markup
    assert 'className="spell-level-group"' in section_markup
    assert 'className="spell-level-group__heading"' in section_markup
    assert 'className="spell-card-grid spell-card-grid--level"' in section_markup
    assert ".spell-slot-editor-list {" in styles
    assert ".character-sheet .spell-slot-editor-list--compact," in styles
    assert ".character-sheet .spell-card-grid--level" in styles
    assert (
        re.search(
            r"\.character-sheet \.spell-slot-editor-list--compact,\s*"
            r"\.character-sheet \.spell-card-grid--level\s*\{\s*"
            r"grid-template-columns: repeat\(3, minmax\(0, min\(24rem, 100%\)\)\);",
            styles,
        )
        is not None
    )
    assert (
        re.search(
            r"@media \(max-width: 740px\) \{[\s\S]*?"
            r"\.character-sheet \.spell-slot-editor-list--compact,\s*"
            r"\.character-sheet \.spell-card-grid--level\s*\{\s*"
            r"grid-template-columns: repeat\(2, minmax\(0, min\(24rem, 100%\)\)\);",
            styles,
        )
        is not None
    )
    assert (
        re.search(
            r"@media \(max-width: 520px\) \{[\s\S]*?"
            r"\.character-sheet \.spell-slot-editor-list--compact,\s*"
            r"\.character-sheet \.spell-card-grid--level\s*\{\s*"
            r"grid-template-columns: minmax\(0, min\(24rem, 100%\)\);",
            styles,
        )
        is not None
    )
    assert 'className="spell-card"' in section_markup
    assert 'className="spell-card__main"' in section_markup
    assert 'className="spell-card__eyebrow"' in section_markup
    assert 'className="spell-card__name"' in section_markup
    assert 'className="spell-card__meta"' in section_markup
    assert 'className="badge-list spell-card__badges"' in section_markup
    assert "openSpellDetail(spell)" in section_markup
    assert "presentedSpellCardDetailLine(spell)" in presented_markup
    assert "rawSpellCardDetailLine(spell)" in section_markup
    assert "presentedSpells.map" not in presented_markup
    assert (
        re.search(
            r'group\.spells\.map\(\(spell\) => \{\s*const detailLine = presentedSpellCardDetailLine\(spell\);[\s\S]*?const spellCardContent = \(\s*<>\s*<span className="spell-card__name"',
            presented_markup,
            re.S,
        )
        is not None
    )
    assert presented_markup.index('className="spell-card__name"') < presented_markup.index('className="spell-card__eyebrow"')
    assert presented_markup.index('className="spell-card__eyebrow"') < presented_markup.index(
        'className="badge-list spell-card__badges"'
    )
    assert "{detailLine ? <span className=\"spell-card__meta\">{detailLine}</span> : null}" in presented_markup
    assert (
        re.search(
            r':\s*\(\s*<span className="spell-card__main">{spellCardContent}</span>',
            presented_markup,
            re.S,
        )
        is not None
    )
    assert 'className="stat-grid"' not in section_markup
    assert 'className="spell-card-list"' not in section_markup
    assert 'className="character-state-card"' not in section_markup
    assert 'className="ghost-button item-detail-button"' not in section_markup
    assert 'className="chat-label"' not in section_markup
    assert 'className="inline-two-col"' not in section_markup


def test_character_notes_section_uses_flask_style_reference_stack_and_edit_chrome() -> None:
    source = Path("frontend/src/components/CharacterNotesSection.tsx").read_text(encoding="utf-8")
    notes_section_markup = source

    assert 'className="read-section" id="session-notes"' in notes_section_markup
    assert "className=\"section-heading\"" in notes_section_markup
    assert "<h2>Notes</h2>" in notes_section_markup
    assert 'className="reference-stack"' in notes_section_markup
    assert 'className="detail-card"' in notes_section_markup
    assert "<h3>Note</h3>" in notes_section_markup
    assert 'className="article-body article-body--compact"' in notes_section_markup
    assert "dangerouslySetInnerHTML" in notes_section_markup
    assert "<p className=\"meta\">No notes yet.</p>" in notes_section_markup
    assert 'className="detail-card session-card"' in notes_section_markup
    assert 'className="stack-form" data-character-sheet-edit-form="notes"' in notes_section_markup
    assert 'className="field"' in notes_section_markup
    assert "<span>Markdown note</span>" in notes_section_markup
    assert 'name="player_notes_markdown"' in notes_section_markup
    assert "Save note" in notes_section_markup
    assert "className=\"chat-label\"" not in notes_section_markup
    assert "Player notes" not in notes_section_markup
    assert "Save notes" not in notes_section_markup


def test_dm_session_revealed_articles_panel_uses_session_article_row_chrome_in_source() -> None:
    source = Path("frontend/src/routes/SessionDmPane.tsx").read_text(encoding="utf-8")
    panel_id_start = source.index('id="session-revealed-articles"')
    panel_start = source.rfind("<article", 0, panel_id_start)
    panel_end = source.index('<article className="card session-sidebar-card" id="session-chat-logs">', panel_start)
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
        "SessionArticleReferenceActions article={article} includePromotionLinks />" in panel_markup
    )

    assert 'className="article-stack"' not in panel_markup
    assert 'className="article-card"' not in panel_markup
    assert 'className="article-kind"' not in panel_markup
    assert 'className="article-actions"' not in panel_markup


def test_dm_content_staged_articles_edit_form_uses_flask_style_file_field_markup() -> None:
    source = Path("frontend/src/routes/DmContentPage.tsx").read_text(encoding="utf-8")
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
