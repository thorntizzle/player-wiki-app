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


def _read_optional_source(path: str) -> str:
    source_path = Path(path)
    return source_path.read_text(encoding="utf-8") if source_path.exists() else ""


def test_normal_gen2_user_surfaces_do_not_render_revision_copy() -> None:
    user_surface_paths = [
        "frontend/src/pages/SessionPage.tsx",
        "frontend/src/pages/CharacterPane.tsx",
        "frontend/src/pages/CharacterRosterPage.tsx",
        "frontend/src/pages/CombatPage.tsx",
        "frontend/src/pages/WikiRoutes.tsx",
        "frontend/src/pages/SystemsRoutes.tsx",
        "frontend/src/pages/CampaignHelpPage.tsx",
        "frontend/src/components/CharacterDndAbilitySkillsSection.tsx",
        "frontend/src/components/CharacterDndSpellsSection.tsx",
        "frontend/src/components/CharacterDndEquipmentSection.tsx",
        "frontend/src/components/CharacterDndInventorySection.tsx",
        "frontend/src/components/CharacterSystemSummarySection.tsx",
        "frontend/src/components/CharacterXianxiaResourcesSection.tsx",
        "frontend/src/components/CharacterXianxiaSkillsSection.tsx",
        "frontend/src/components/CharacterXianxiaTechniquesSection.tsx",
        "frontend/src/components/CharacterXianxiaEquipmentSection.tsx",
        "frontend/src/components/CharacterXianxiaInventorySection.tsx",
        "frontend/src/components/SessionArticleDisplay.tsx",
        "frontend/src/components/WikiChrome.tsx",
        "frontend/src/components/SystemsChrome.tsx",
    ]

    rendered_revision_copy = re.compile(r"(?:>\s*|[\"'`])Revision\b")
    offenders = [
        path
        for path in user_surface_paths
        if rendered_revision_copy.search(Path(path).read_text(encoding="utf-8"))
    ]

    assert offenders == []


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
    campaign_list_source = Path("frontend/src/pages/CampaignPickerPage.tsx").read_text(encoding="utf-8")

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
    assert "const signInHref = `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;" in campaign_list_source
    assert '<p className="card-kicker">{campaignRoleLabel(entry.role)}</p>' in campaign_list_source
    assert "<h2>{entry.campaign.title}</h2>" in campaign_list_source
    assert "{entry.campaign.system ? <p className=\"meta\">System: {entry.campaign.system}</p> : null}" in campaign_list_source
    assert '<p className="meta">Visible through session {entry.campaign.current_session}</p>' in campaign_list_source
    assert campaign_list_source.count('className="button-link" href={campaignRouteHref(entry.campaign.slug, "", pickerRouteMode)}') == 1
    assert '<a className="ghost-button" href={signInHref}>' in campaign_list_source
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


def test_frontend_pilot_routes_are_available_by_default_with_index(app, client, tmp_path):
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


def test_home_redirects_to_gen2_campaign_when_built_index_is_available(app, client, tmp_path):
    dist_dir = tmp_path / "frontend-dist-default"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<!doctype html><html><body>gen2</body></html>", encoding="utf-8")
    app.config["APP_NEXT_DIST_DIR"] = dist_dir

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/app-next/campaigns/linden-pass")


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
    loading_source = Path("frontend/src/appLoadingReadiness.tsx").read_text(encoding="utf-8")
    link_helper_source = Path("frontend/src/campaignLinks.ts").read_text(encoding="utf-8")

    assert "useIsFetching" in loading_source
    assert "useNavigate" in source
    assert "function useAppLoadingReadiness" in loading_source
    assert "function appNextHrefToRouterPath" in link_helper_source
    assert "location.pathname" in source
    assert "previousLocationPathname" in loading_source
    assert "window.__cpwAppLoadingBegin?.();" in loading_source
    assert "window.__cpwAppLoadingReady?.();" in loading_source
    assert "void navigate({ to: appNextHrefToRouterPath(item.href) as never });" in source
    assert "const isActive = isNavItemActive(item.label, item.href);" in source
    assert 'aria-current={isActive ? "page" : undefined}' in source
    assert "activeFetchCount > 0" in loading_source
    assert "queryClient.isFetching() === 0" in loading_source


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
    source = Path("frontend/src/pages/SessionRoutes.tsx").read_text(encoding="utf-8")
    shell_source = Path("frontend/src/AppShell.tsx").read_text(encoding="utf-8")
    search_source = Path("frontend/src/components/CampaignGlobalSearch.tsx").read_text(encoding="utf-8")
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
    assert 'className="campaign-global-search__form"' in search_source
    assert "<CampaignGlobalSearch campaignSlug={campaignSlug} />" in shell_source


def test_app_shell_search_auth_and_loading_live_in_shared_modules() -> None:
    shell_source = Path("frontend/src/AppShell.tsx").read_text(encoding="utf-8")
    search_source = Path("frontend/src/components/CampaignGlobalSearch.tsx").read_text(encoding="utf-8")
    auth_source = Path("frontend/src/components/AuthNotice.tsx").read_text(encoding="utf-8")
    loading_source = Path("frontend/src/appLoadingReadiness.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    assert 'import { CampaignGlobalSearch } from "./components/CampaignGlobalSearch";' in shell_source
    assert 'import { AuthNotice } from "./components/AuthNotice";' in shell_source
    assert 'import { RouteSuspenseFallback, useAppLoadingReadiness } from "./appLoadingReadiness";' in shell_source
    assert "function CampaignGlobalSearch" not in shell_source
    assert "function AuthNotice" not in shell_source
    assert "function RouteSuspenseFallback" not in shell_source
    assert "function useAppLoadingReadiness" not in shell_source
    assert "export function CampaignGlobalSearch" in search_source
    assert "function formatSearchStatus" in search_source
    assert "Search complete." not in search_source
    assert 'return `Found ${resultCount} matching reference${resultCount === 1 ? "" : "s"}.`;' in search_source
    assert 'className="campaign-global-search"' in search_source
    assert "previewCampaignReference" in search_source
    assert ".campaign-global-search-result:focus-visible" in styles
    assert "outline: 2px solid var(--focus-ring);" in styles[
        styles.index(".campaign-global-search-result:hover,"):styles.index(".campaign-global-search-result__title")
    ]
    assert "export function AuthNotice" in auth_source
    assert 'className="card auth-notice"' in auth_source
    assert "export function RouteSuspenseFallback" in loading_source
    assert "export function useAppLoadingReadiness" in loading_source


def test_character_navigation_card_uses_flask_style_chrome_in_source() -> None:
    source = Path("frontend/src/components/CharacterNavigationCard.tsx").read_text(encoding="utf-8")

    assert 'className={isReadSurface ? "character-subpage-nav-card" : "character-selector-card"}' in source
    assert "data-character-subpage-nav-card={isReadSurface ? \"\" : undefined}" in source
    assert '<nav className="character-subpage-nav" aria-label="Character subpages">' in source
    assert "href={readSurfaceSectionUrl(section.id)}" in source
    assert "const isActive = activeCharacterSection === section.id;" in source
    assert 'className={isActive ? "button-link" : "ghost-button"}' in source
    assert 'aria-current={isActive ? "page" : undefined}' in source
    assert "data-character-read-subpage-link" in source
    assert "data-character-read-target-subpage={section.id}" in source
    assert "onClick={handleReadSurfaceSectionNavClick(section.id)}" in source
    assert '<label className="field" htmlFor="character-selector">' in source
    assert "<span>Character</span>" in source
    assert 'id="character-selector"' in source
    assert "selectCharacter(event.currentTarget.value || null)" in source
    assert "className=\"chat-label\"" not in source


def test_character_embedded_section_nav_uses_flask_style_chrome_in_source() -> None:
    source = Path("frontend/src/components/CharacterEmbeddedSectionNav.tsx").read_text(encoding="utf-8")

    assert '<nav className="combat-workspace-nav session-character-section-nav" aria-label="Session character sections">' in source
    assert 'className={`ghost-button combat-workspace-button${isActive ? " combat-workspace-button--active" : ""}`}' in source
    assert "aria-pressed={isActive}" in source
    assert 'aria-current={isActive ? "page" : undefined}' in source
    assert 'className="character-subpage-nav-card"' in source
    assert '<nav className="character-subpage-nav" aria-label="Character subpages">' in source
    assert 'className={isActive ? "button-link" : "ghost-button"}' in source
    assert source.count("aria-pressed={isActive}") == 2
    assert "onClick={() => selectCharacterSection(section.id)}" in source
    assert "className=\"section-tabs\"" not in source
    assert "className=\"chat-label\"" not in source


def test_character_header_uses_flask_style_chrome_in_source() -> None:
    source = Path("frontend/src/components/CharacterHeader.tsx").read_text(encoding="utf-8")

    assert '<header className="character-header">' in source
    assert 'className="character-header__top"' in source
    assert 'className="character-header__identity"' in source
    assert '<p className="eyebrow">Character sheet</p>' in source
    assert 'className="character-header__actions"' in source
    assert "detailLinks.advanced_editor_url" in source
    assert "detailLinks.retraining_url" in source
    assert "detailLinks.level_up_url" in source
    assert "detailProgressionRepairUrl" in source
    assert 'detailLinks.progression_repair_url ? "Progression repair" : "Prepare for level-up"' in source
    assert "detailLinks.cultivation_url" in source
    assert '<p className="eyebrow">{surfaceMetaLabel}</p>' in source
    assert 'embeddedHeaderDetails.join(" | ")' in source
    assert '<div className="hero-actions">' in source
    assert '{isCombatSurface ? "Open full sheet" : "Open full character page"}' in source
    assert "className=\"article-actions\"" not in source
    assert "className=\"button button-secondary\"" not in source
    assert "Character route" not in source


def test_character_vitals_bar_uses_flask_style_chrome_in_source() -> None:
    source = Path("frontend/src/components/CharacterVitalsBar.tsx").read_text(encoding="utf-8")

    assert '<section className="session-bar session-bar--compact" id="session-vitals">' in source
    assert 'className="session-bar__summary"' in source
    assert '<div className="session-bar__actions" id="session-rest">' in source
    assert 'onClick={() => onPreviewRest("short")}' in source
    assert 'onClick={() => onPreviewRest("long")}' in source
    assert 'className="session-vitals-form session-vitals-form--compact"' in source
    assert "xianxiaVitalsFields.map((field)" in source
    assert "id={`xianxia-${field.key}`}" in source
    assert "Save Xianxia pools" in source
    assert 'id="character-current-hp"' in source
    assert 'id="character-temp-hp"' in source
    assert "<span> / {maxHp}</span>" in source
    assert 'className="plain-list rest-preview-list"' in source
    assert '{"->"}' in source
    assert 'onClick={() => onApplyRest(restPreview.rest_type === "short" ? "short" : "long")}' in source
    assert "onClick={onClearRestPreview}" in source
    assert "className=\"chat-label\"" not in source


def test_character_detail_dialog_state_builders_live_in_shared_utils() -> None:
    source = Path("frontend/src/characterPaneUtils.ts").read_text(encoding="utf-8")
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")

    assert "export function itemDetailDialogState" in source
    assert 'eyebrow: "Item details"' in source
    assert 'title: item.name || "Item"' in source
    assert 'html: item.description_html || ""' in source
    assert "export function spellDetailDialogState" in source
    assert 'eyebrow: [spell.level_label, spell.school].filter(Boolean).join(" | ") || "Spell details"' in source
    assert 'title: spell.name || "Spell"' in source
    assert 'notes: spell.management_note || ""' in source
    assert 'facts: [...spellDetailFacts(spell), ...(source ? [{ label: "Source", value: source }] : [])]' in source
    assert "badges: spell.badges ?? []" in source
    assert "setDetailDialog(itemDetailDialogState(item));" in route_source
    assert "setDetailDialog(spellDetailDialogState(spell));" in route_source


def test_character_number_input_parser_lives_in_shared_utils() -> None:
    source = Path("frontend/src/characterPaneUtils.ts").read_text(encoding="utf-8")
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    submit_handler_source = Path("frontend/src/characterPaneSubmitHandlers.ts").read_text(encoding="utf-8")

    assert "export function parseCharacterNumberInput" in source
    assert "const parsed = Number(value);" in source
    assert "Number.isFinite(parsed)" in source
    assert 'return { value: null, errorMessage: `Enter a valid ${label}.` };' in source
    assert "return { value: parsed, errorMessage: null };" in source
    assert "parseCharacterNumberInput(value, label)" in submit_handler_source
    assert "setErrorMessage(result.errorMessage)" in submit_handler_source
    assert "setStatusMessage(null)" in submit_handler_source
    assert "parseCharacterNumberInput(value, label)" not in route_source


def test_character_read_section_url_helpers_live_in_shared_utils() -> None:
    source = Path("frontend/src/characterPaneUtils.ts").read_text(encoding="utf-8")
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")

    assert "export function defaultCharacterReadSection" in source
    assert 'return isXianxia ? "quick-reference" : "overview";' in source
    assert "export function characterReadSectionUrl" in source
    assert "if (!characterSlug) {" in source
    assert "encodeURIComponent(campaignSlug)" in source
    assert "encodeURIComponent(characterSlug)" in source
    assert "if (section === defaultSection)" in source
    assert "return `${basePath}?page=${encodeURIComponent(section)}`;" in source
    assert "defaultCharacterReadSection(isXianxia)" in route_source
    assert "characterReadSectionUrl(campaignSlug, selectedSlug, section, readSurfaceDefaultSection)" in route_source
    assert "characterReadSectionUrl(campaignSlug, selectedSlug, section, defaultCharacterReadSection(isXianxia))" in route_source
    assert "readSurfaceSectionBaseUrl" not in route_source


def test_character_detail_route_wrapper_lives_in_route_module() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    file_route_source = Path(
        "frontend/src/routes/campaigns/$campaignSlug/characters/$characterSlug/index.tsx"
    ).read_text(encoding="utf-8")
    route_source = Path("frontend/src/pages/CharacterDetailPage.tsx").read_text(encoding="utf-8")

    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert "function CharacterDetailPage" not in main_source
    assert "useParams" not in main_source
    assert "useLocation" not in main_source
    assert "normalizeCharacterSection" not in main_source
    assert 'from "../../../../../pages/CharacterDetailPage";' in file_route_source
    assert 'createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/")' in file_route_source
    assert "component: CharacterDetailPage" in file_route_source

    assert "export function CharacterDetailPage()" in route_source
    assert 'from: "/campaigns/$campaignSlug/characters/$characterSlug/"' in route_source
    assert "normalizeCharacterSection(new URLSearchParams(location.search).get(\"page\"))" in route_source
    assert "<CharacterPane" in route_source
    assert 'surface="read"' in route_source
    assert "onSelectedCharacterChange" in route_source


def test_character_create_route_lives_in_route_module() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    file_route_source = Path("frontend/src/routes/campaigns/$campaignSlug/characters/new.tsx").read_text(
        encoding="utf-8"
    )
    create_source = Path("frontend/src/pages/CharacterCreatePage.tsx").read_text(encoding="utf-8")

    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert 'from "../../../../pages/CharacterCreatePage";' in file_route_source
    assert 'createFileRoute("/campaigns/$campaignSlug/characters/new")' in file_route_source
    assert "component: CharacterCreatePage" in file_route_source

    assert "export function CharacterCreatePage()" in create_source
    assert 'from: "/campaigns/$campaignSlug/characters/new"' in create_source
    assert "apiClient.getCharacterCreateContext(resolvedCampaignSlug, contextValues)" in create_source
    assert "apiClient.createCharacter(resolvedCampaignSlug, payload)" in create_source
    assert "<CharacterPreviewList preview={create.preview} />" in create_source


def test_character_xianxia_manual_import_route_lives_in_route_module() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    file_route_source = Path(
        "frontend/src/routes/campaigns/$campaignSlug/characters/import/xianxia-manual.tsx"
    ).read_text(encoding="utf-8")
    import_source = Path("frontend/src/pages/CharacterXianxiaManualImportPage.tsx").read_text(encoding="utf-8")

    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert 'from "../../../../../pages/CharacterXianxiaManualImportPage";' in file_route_source
    assert 'createFileRoute("/campaigns/$campaignSlug/characters/import/xianxia-manual")' in file_route_source
    assert "component: CharacterXianxiaManualImportPage" in file_route_source

    assert "export function CharacterXianxiaManualImportPage()" in import_source
    assert 'from: "/campaigns/$campaignSlug/characters/import/xianxia-manual"' in import_source
    assert "apiClient.getXianxiaManualImportContext(resolvedCampaignSlug, contextValues)" in import_source
    assert "apiClient.submitXianxiaManualImport(resolvedCampaignSlug" in import_source
    assert "manualImportRows(context, rowCount, draftValues)" in import_source


def test_character_advanced_editor_route_lives_in_route_module() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    file_route_source = Path(
        "frontend/src/routes/campaigns/$campaignSlug/characters/$characterSlug/edit.tsx"
    ).read_text(encoding="utf-8")
    editor_source = Path("frontend/src/pages/CharacterAdvancedEditorPage.tsx").read_text(encoding="utf-8")

    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert 'from "../../../../../pages/CharacterAdvancedEditorPage";' in file_route_source
    assert 'createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/edit")' in file_route_source
    assert "component: CharacterAdvancedEditorPage" in file_route_source

    assert "export function CharacterAdvancedEditorPage()" in editor_source
    assert 'from: "/campaigns/$campaignSlug/characters/$characterSlug/edit"' in editor_source
    assert "apiClient.getCharacterAdvancedEditor(campaignSlug, characterSlug)" in editor_source
    assert "apiClient.updateCharacterAdvancedEditor(campaignSlug, characterSlug" in editor_source
    assert "editorValuesFromContext(editor)" in editor_source
    assert "expected_revision: editor.state_revision" in editor_source


def test_character_progression_repair_route_lives_in_route_module() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    file_route_source = Path(
        "frontend/src/routes/campaigns/$campaignSlug/characters/$characterSlug/progression-repair.tsx"
    ).read_text(encoding="utf-8")
    repair_source = Path("frontend/src/pages/CharacterProgressionRepairPage.tsx").read_text(encoding="utf-8")

    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert 'from "../../../../../pages/CharacterProgressionRepairPage";' in file_route_source
    assert 'createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/progression-repair")' in file_route_source
    assert "component: CharacterProgressionRepairPage" in file_route_source

    assert "export function CharacterProgressionRepairPage()" in repair_source
    assert 'from: "/campaigns/$campaignSlug/characters/$characterSlug/progression-repair"' in repair_source
    assert "apiClient.getCharacterProgressionRepair(campaignSlug, characterSlug)" in repair_source
    assert "apiClient.submitCharacterProgressionRepair(campaignSlug, characterSlug, payload)" in repair_source
    assert "characterProgressionRepairValuesFromContext(repair)" in repair_source
    assert "expected_revision: repair.state_revision" in repair_source


def test_character_retraining_route_lives_in_route_module() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    file_route_source = Path(
        "frontend/src/routes/campaigns/$campaignSlug/characters/$characterSlug/retraining.tsx"
    ).read_text(encoding="utf-8")
    retraining_source = Path("frontend/src/pages/CharacterRetrainingPage.tsx").read_text(encoding="utf-8")

    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert 'from "../../../../../pages/CharacterRetrainingPage";' in file_route_source
    assert 'createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/retraining")' in file_route_source
    assert "component: CharacterRetrainingPage" in file_route_source

    assert "export function CharacterRetrainingPage()" in retraining_source
    assert 'from: "/campaigns/$campaignSlug/characters/$characterSlug/retraining"' in retraining_source
    assert "apiClient.getCharacterRetraining(campaignSlug, characterSlug)" in retraining_source
    assert "apiClient.submitCharacterRetraining(campaignSlug, characterSlug, payload)" in retraining_source
    assert "characterRetrainingValuesFromContext(retraining)" in retraining_source
    assert "expected_revision: retraining.state_revision" in retraining_source


def test_character_level_up_route_lives_in_route_module() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    file_route_source = Path(
        "frontend/src/routes/campaigns/$campaignSlug/characters/$characterSlug/level-up.tsx"
    ).read_text(encoding="utf-8")
    level_up_source = Path("frontend/src/pages/CharacterLevelUpPage.tsx").read_text(encoding="utf-8")

    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert 'from "../../../../../pages/CharacterLevelUpPage";' in file_route_source
    assert 'createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/level-up")' in file_route_source
    assert "component: CharacterLevelUpPage" in file_route_source

    assert "export function CharacterLevelUpPage()" in level_up_source
    assert 'from: "/campaigns/$campaignSlug/characters/$characterSlug/level-up"' in level_up_source
    assert "apiClient.getCharacterLevelUp(campaignSlug, characterSlug, contextValues)" in level_up_source
    assert "apiClient.submitCharacterLevelUp(campaignSlug, characterSlug, payload)" in level_up_source
    assert "characterLevelUpValuesFromContext(levelUp)" in level_up_source
    assert "expected_revision: levelUp.state_revision" in level_up_source


def test_character_cultivation_route_lives_in_route_module_and_aggregate_is_retired() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    authoring_path = Path("frontend/src/pages/CharacterAuthoringRoutes.tsx")
    file_route_source = Path(
        "frontend/src/routes/campaigns/$campaignSlug/characters/$characterSlug/cultivation.tsx"
    ).read_text(encoding="utf-8")
    cultivation_source = Path("frontend/src/pages/CharacterCultivationPage.tsx").read_text(encoding="utf-8")

    assert not authoring_path.exists()
    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert 'from "../../../../../pages/CharacterCultivationPage";' in file_route_source
    assert 'createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/cultivation")' in file_route_source
    assert "component: CharacterCultivationPage" in file_route_source
    assert "export function CharacterCultivationPage()" in cultivation_source
    assert 'from: "/campaigns/$campaignSlug/characters/$characterSlug/cultivation"' in cultivation_source
    assert "apiClient.getCharacterCultivation(campaignSlug, characterSlug)" in cultivation_source
    assert "apiClient.runCharacterCultivationAction(campaignSlug, characterSlug" in cultivation_source
    assert "expected_revision: data.character.state_record.revision" in cultivation_source


def test_character_cultivation_realm_ascension_lives_in_component_module() -> None:
    route_source = Path("frontend/src/pages/CharacterCultivationPage.tsx").read_text(encoding="utf-8")
    realm_source = Path("frontend/src/components/CharacterCultivationRealmAscension.tsx").read_text(encoding="utf-8")

    assert "export function CharacterCultivationRealmAscension" in realm_source
    assert "function CultivationHistoryRecords" in realm_source
    assert "recordFromUnknown(context.realm_ascension)" in realm_source
    assert 'name="realm_ascension_gm_review_note"' in realm_source
    assert 'name="realm_ascension_gm_confirmation_note"' in realm_source
    assert "pre_ascension_snapshot" in realm_source
    assert "post_ascension_snapshot" in realm_source

    assert 'from "../components/CharacterCultivationRealmAscension";' in route_source
    assert "<CharacterCultivationRealmAscension context={cultivation} renderActionForm={renderActionForm} />" in route_source
    assert "const renderRealmAscension" not in route_source
    assert "function CultivationHistoryRecords" not in route_source
    assert 'name="realm_ascension_gm_review_note"' not in route_source


def test_gen2_route_modules_are_lazy_loaded_without_dropping_loading_cover_early() -> None:
    main_source = Path("frontend/src/main.tsx").read_text(encoding="utf-8")
    vite_source = Path("frontend/vite.config.ts").read_text(encoding="utf-8")
    route_tree_source = Path("frontend/src/routeTree.gen.ts").read_text(encoding="utf-8")
    shell_source = Path("frontend/src/AppShell.tsx").read_text(encoding="utf-8")
    loading_source = Path("frontend/src/appLoadingReadiness.tsx").read_text(encoding="utf-8")

    assert 'import { routeTree } from "./routeTree.gen";' in main_source
    assert "React.lazy" not in main_source
    assert 'import { SessionPage } from "./pages/SessionPage";' not in main_source
    assert 'import { CombatPage } from "./pages/CombatPage";' not in main_source
    assert 'import { DmContentPage } from "./pages/DmContentPage";' not in main_source
    assert 'import { CharacterDetailPage } from "./pages/CharacterDetailPage";' not in main_source
    assert "tanstackRouter({" in vite_source
    assert "autoCodeSplitting: true" in vite_source
    assert "CampaignsCampaignSlugSessionRouteImport" in route_tree_source
    assert "CampaignsCampaignSlugCombatRouteImport" in route_tree_source
    assert "CampaignsCampaignSlugDmContentRouteImport" in route_tree_source
    assert "CampaignsCampaignSlugCharactersCharacterSlugIndexRouteImport" in route_tree_source
    assert "CampaignsCampaignSlugSystemsEntriesEntrySlugRouteImport" in route_tree_source
    assert "CampaignsCampaignSlugPagesSplatRouteImport" in route_tree_source

    assert "export function RouteSuspenseFallback" in loading_source
    assert "setRouteSuspensePending(true);" in loading_source
    assert "return () => setRouteSuspensePending(false);" in loading_source
    assert "export function useAppLoadingReadiness(locationPathname: string, routeSuspensePending: boolean)" in loading_source
    assert "if (activeFetchCount > 0 || routeSuspensePending)" in loading_source
    assert "<React.Suspense fallback={<RouteSuspenseFallback setRouteSuspensePending={setRouteSuspensePending} />}>" in shell_source
    assert "useAppLoadingReadiness(location.pathname, routeSuspensePending);" in shell_source


def test_character_authoring_preview_lists_live_in_component_module() -> None:
    create_source = Path("frontend/src/pages/CharacterCreatePage.tsx").read_text(encoding="utf-8")
    level_up_source = Path("frontend/src/pages/CharacterLevelUpPage.tsx").read_text(encoding="utf-8")
    preview_source = Path("frontend/src/components/CharacterAuthoringPreview.tsx").read_text(encoding="utf-8")

    assert 'import { CharacterLevelUpPreviewList } from "../components/CharacterAuthoringPreview";' in level_up_source
    assert 'import { CharacterPreviewList } from "../components/CharacterAuthoringPreview";' in create_source
    assert "function CharacterPreviewList" not in create_source
    assert "function CharacterLevelUpPreviewList" not in level_up_source
    assert "<CharacterPreviewList preview={create.preview} />" in create_source
    assert "<CharacterLevelUpPreviewList preview={levelUp.preview ?? {}} />" in level_up_source

    assert "function PreviewSidebar(" in preview_source
    assert "export function CharacterPreviewList" in preview_source
    assert "export function CharacterLevelUpPreviewList" in preview_source
    assert 'emptyMessage="Choose core options to populate the preview."' in preview_source
    assert 'className="builder-preview-list"' in preview_source
    assert 'className="character-authoring-preview-section"' in preview_source
    assert 'card sidebar-card character-authoring-preview-section' not in preview_source
    assert "asStringArray(preview.saving_throws)" in preview_source
    assert "asStringArray(preview.new_spells)" in preview_source


def test_character_authoring_dnd_choice_select_lives_in_field_component() -> None:
    create_source = Path("frontend/src/pages/CharacterCreatePage.tsx").read_text(encoding="utf-8")
    level_up_source = Path("frontend/src/pages/CharacterLevelUpPage.tsx").read_text(encoding="utf-8")
    field_source = Path("frontend/src/components/CharacterAuthoringFields.tsx").read_text(encoding="utf-8")

    assert 'import { CharacterDndChoiceSelect } from "../components/CharacterAuthoringFields";' in level_up_source
    assert 'import { CharacterDndChoiceSelect } from "../components/CharacterAuthoringFields";' in create_source
    assert "function CharacterDndChoiceSelect" not in create_source
    assert "function CharacterDndChoiceSelect" not in level_up_source
    assert "export function CharacterDndChoiceSelect" in field_source
    assert "field: CharacterDndChoiceField;" in field_source
    assert "refreshContext(nextValues);" in field_source
    assert "{selectOptions(field.options ?? [])}" in field_source


def test_character_authoring_shared_helpers_live_in_utility_module() -> None:
    cultivation_source = Path("frontend/src/pages/CharacterCultivationPage.tsx").read_text(encoding="utf-8")
    editor_source = Path("frontend/src/pages/CharacterAdvancedEditorPage.tsx").read_text(encoding="utf-8")
    import_source = Path("frontend/src/pages/CharacterXianxiaManualImportPage.tsx").read_text(encoding="utf-8")
    level_up_source = Path("frontend/src/pages/CharacterLevelUpPage.tsx").read_text(encoding="utf-8")
    repair_source = Path("frontend/src/pages/CharacterProgressionRepairPage.tsx").read_text(encoding="utf-8")
    retraining_source = Path("frontend/src/pages/CharacterRetrainingPage.tsx").read_text(encoding="utf-8")
    helper_source = Path("frontend/src/characterAuthoringUtils.tsx").read_text(encoding="utf-8")

    assert "from \"../characterAuthoringUtils\";" in cultivation_source
    assert "from \"../characterAuthoringUtils\";" in level_up_source
    assert "function characterNameFromRecord" not in cultivation_source
    assert "function classLevelTextFromRecord" not in cultivation_source
    assert "function characterNameFromRecord" not in editor_source
    assert "function classLevelTextFromRecord" not in editor_source
    assert "function characterNameFromRecord" not in level_up_source
    assert "function classLevelTextFromRecord" not in level_up_source
    assert "function optionValue" not in level_up_source
    assert "function optionLabel" not in level_up_source
    assert "function draftString(" not in cultivation_source
    assert "function draftStringArray" not in cultivation_source
    assert "function updateAuthoringValue" not in level_up_source
    assert "function selectOptions" not in level_up_source
    assert "function editorSelectOptions" not in editor_source
    assert "function editorValuesFromContext" not in editor_source
    assert "function characterLevelUpValuesFromContext" not in level_up_source
    assert "function characterAuthoringStringValues" not in level_up_source
    assert "function characterProgressionRepairValuesFromContext" not in repair_source
    assert "function characterRetrainingValuesFromContext" not in retraining_source
    assert "function manualImportRows" not in import_source
    assert "manualImportRows(context, rowCount, draftValues)" in import_source

    assert "export type CharacterAuthoringValues" in helper_source
    assert "export function characterNameFromRecord" in helper_source
    assert "export function classLevelTextFromRecord" in helper_source
    assert "export function optionValue" in helper_source
    assert "export function optionLabel" in helper_source
    assert "export function draftString" in helper_source
    assert "export function draftStringArray" in helper_source
    assert "export function updateAuthoringValue" in helper_source
    assert "export function selectOptions" in helper_source
    assert "export function editorSelectOptions" in helper_source
    assert "export function editorValuesFromContext" in helper_source
    assert "export function characterLevelUpValuesFromContext" in helper_source
    assert "export function characterAuthoringStringValues" in helper_source
    assert "export function characterProgressionRepairValuesFromContext" in helper_source
    assert "export function characterRetrainingValuesFromContext" in helper_source
    assert "export function manualImportRows" in helper_source
    assert 'return option.source_id ? `${label} (${option.source_id})` : label;' in helper_source
    assert '<option key={value || optionLabel(option)} value={value}>' in helper_source
    assert "values[`custom_feature_name_${row.index}`]" in helper_source
    assert "values.advancement_mode = draftString(values, \"advancement_mode\"" in helper_source
    assert "slug_input_name: `martial_art_${index}_slug`" in helper_source


def test_character_section_policy_helpers_live_in_shared_utils() -> None:
    source = Path("frontend/src/characterPaneUtils.ts").read_text(encoding="utf-8")
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")

    assert "export function visibleCharacterSectionsForSystem" in source
    assert "const baseSections = isDnd ? dndCharacterSections : xianxiaCharacterSections;" in source
    assert "return canUseControls ? [...baseSections, characterControlsSection] : baseSections;" in source
    assert "export function normalizeActiveCharacterSectionForSystem" in source
    assert 'isXianxia && activeSection === "overview"' in source
    assert 'isDnd && activeSection === "quick-reference"' in source
    assert 'activeSection === "controls" && hasDetailRecord && !canUseControls' in source
    assert "return defaultCharacterReadSection(isXianxia);" in source
    assert "visibleCharacterSectionsForSystem(true, canUseControls)" in route_source
    assert "visibleCharacterSectionsForSystem(false, canUseControls)" in route_source
    assert "normalizeActiveCharacterSectionForSystem(activeCharacterSection" in route_source
    assert "normalizedActiveCharacterSection !== activeCharacterSection" in route_source
    assert "? [...dndCharacterSections" not in route_source
    assert "? [...xianxiaCharacterSections" not in route_source


def test_admin_user_detail_action_button_chrome_in_source() -> None:
    source = Path("frontend/src/pages/AdminRoutes.tsx").read_text(encoding="utf-8")
    admin_user_detail_source = source[source.index("export function AdminUserDetailPage() {"):]

    destructive_actions = [
        ("removeMembership.mutate(membership);", "Confirm remove", "Remove"),
        ("removeAssignment.mutate(assignment);", "Confirm clear", "Clear"),
        ("disableUser.mutate();", "Confirm disable", "Disable user"),
    ]

    for mutation_call, confirmation_label, button_label in destructive_actions:
        action_start = admin_user_detail_source.rfind("<form", 0, admin_user_detail_source.index(mutation_call))
        action_end = admin_user_detail_source.index("</form>", action_start) + len("</form>")
        action_block = admin_user_detail_source[action_start:action_end]
        assert 'className="confirmed-action"' in action_block
        assert 'className="checkbox-label"' in action_block
        assert confirmation_label in action_block
        assert button_label in action_block
        assert 'className="ghost-button"' in action_block
        assert 'className="button-danger"' not in action_block
        assert 'className="button button-secondary"' not in action_block


def test_admin_user_detail_labels_use_display_values_in_source() -> None:
    route_source = Path("frontend/src/pages/AdminRoutes.tsx").read_text(encoding="utf-8")
    api_types = Path("frontend/src/api/types.ts").read_text(encoding="utf-8")
    admin_context = Path("player_wiki/admin_context.py").read_text(encoding="utf-8")
    api_source = Path("player_wiki/api.py").read_text(encoding="utf-8")

    assert "function formatAdminValue(value: string): string" in route_source
    assert "Account status: {formatAdminValue(data.managed_user.status)}" in route_source
    assert "{formatAdminValue(user.status)}" in route_source
    assert "{formatAdminValue(membership.role)} | {formatAdminValue(membership.status)}" in route_source
    assert "{assignment.character_label} | {formatAdminValue(assignment.assignment_type)}" in route_source
    assert "assignment.character_slug} | {assignment.assignment_type}" not in route_source
    assert "character_label: string;" in api_types
    assert "def build_character_assignment_label_lookup(" in admin_context
    assert "def get_assignment_character_label(" in admin_context
    assert '"character_label": get_assignment_character_label(assignment, assignment_label_lookup)' in api_source


def test_admin_activity_chrome_lives_in_component_module() -> None:
    route_source = Path("frontend/src/pages/AdminRoutes.tsx").read_text(encoding="utf-8")
    activity_source = Path("frontend/src/components/AdminActivity.tsx").read_text(encoding="utf-8")

    assert 'import { AdminActivityFilters, AdminActivityList, AdminPagination } from "../components/AdminActivity";' in route_source
    assert "function AdminActivityFilters" not in route_source
    assert "function AdminActivityList" not in route_source
    assert "function AdminPagination" not in route_source
    assert "<AdminActivityFilters" in route_source
    assert "<AdminActivityList" in route_source
    assert "<AdminPagination" in route_source
    assert "export function AdminActivityFilters" in activity_source
    assert "export function AdminActivityList" in activity_source
    assert "export function AdminPagination" in activity_source
    assert 'className="audit-filter-form admin-filter-form"' in activity_source
    assert 'className="plain-list audit-list admin-audit-list"' in activity_source
    assert 'className="pagination-bar admin-pagination"' in activity_source
    assert 'className="ghost-button" href={data.export_url}' in activity_source


def test_admin_mutations_live_in_shared_hook() -> None:
    route_source = Path("frontend/src/pages/AdminRoutes.tsx").read_text(encoding="utf-8")
    hook_source = Path("frontend/src/adminMutations.ts").read_text(encoding="utf-8")

    assert 'import { useAdminDashboardMutations, useAdminUserDetailMutations } from "../adminMutations";' in route_source
    assert "useAdminDashboardMutations({" in route_source
    assert "useAdminUserDetailMutations({" in route_source
    assert "export function useAdminDashboardMutations(" in hook_source
    assert "export function useAdminUserDetailMutations(" in hook_source
    assert "apiClient.inviteAdminUser" in hook_source
    assert "apiClient.setAdminUserMembership" in hook_source
    assert "apiClient.removeAdminUserMembership" in hook_source
    assert "apiClient.assignAdminUserCharacter" in hook_source
    assert "apiClient.removeAdminUserCharacterAssignment" in hook_source
    assert "apiClient.issueAdminUserInvite" in hook_source
    assert "apiClient.issueAdminUserPasswordReset" in hook_source
    assert "apiClient.disableAdminUser" in hook_source
    assert "apiClient.enableAdminUser" in hook_source
    assert "apiClient.deleteAdminUser" in hook_source
    assert "queryClient.setQueryData" in hook_source
    assert "useMutation(" not in route_source
    assert "apiClient.inviteAdminUser" not in route_source
    assert "apiClient.deleteAdminUser" not in route_source


def test_admin_user_delete_button_uses_ghost_button_class_in_source() -> None:
    source = Path("frontend/src/pages/AdminRoutes.tsx").read_text(encoding="utf-8")
    admin_user_detail_source = source[source.index("export function AdminUserDetailPage() {"):]

    assert "const deleteEmailMatches = data" in admin_user_detail_source
    assert "const deleteUserHint = data && !deleteEmailMatches" in admin_user_detail_source
    assert "Type ${data.managed_user.email} exactly to enable deletion." in admin_user_detail_source
    assert 'id="admin-delete-user-hint"' in admin_user_detail_source

    delete_on_click = 'onClick={() => deleteUser.mutate()}'
    delete_button_start = admin_user_detail_source.rfind("<button", 0, admin_user_detail_source.index(delete_on_click))
    delete_button_end = admin_user_detail_source.index("</button>", delete_button_start) + len("</button>")
    delete_button_block = admin_user_detail_source[delete_button_start:delete_button_end]

    assert 'className="ghost-button"' in delete_button_block
    assert 'className="button-danger"' not in delete_button_block
    assert delete_on_click in delete_button_block
    assert "disabled={mutationPending || !deleteEmailMatches}" in delete_button_block
    assert 'aria-describedby={deleteUserHint ? "admin-delete-user-hint" : undefined}' in delete_button_block
    assert "{deleteUser.isPending ? \"Deleting...\" : \"Delete user\"}" in delete_button_block


def test_admin_user_disabled_actions_have_visible_reasons_in_source() -> None:
    source = Path("frontend/src/pages/AdminRoutes.tsx").read_text(encoding="utf-8")
    admin_user_detail_source = source[source.index("export function AdminUserDetailPage() {"):]

    expected_hints = {
        "membershipSaveHint": (
            "admin-membership-save-hint",
            "Choose a campaign before saving membership.",
            "Finish the current admin action before saving membership.",
        ),
        "assignmentSaveHint": (
            "admin-assignment-save-hint",
            "Choose a character before assigning.",
            "Finish the current admin action before assigning a character.",
        ),
        "disableUserHint": (
            "admin-disable-user-hint",
            "Check Confirm disable to enable this action.",
            "Finish the current admin action before disabling this account.",
        ),
        "deleteUserHint": (
            "admin-delete-user-hint",
            "Type ${data.managed_user.email} exactly to enable deletion.",
            "Finish the current admin action before deleting this account.",
        ),
    }

    for hint_name, (hint_id, primary_reason, pending_reason) in expected_hints.items():
        assert f"const {hint_name} =" in admin_user_detail_source
        assert primary_reason in admin_user_detail_source
        assert pending_reason in admin_user_detail_source
        assert f'id="{hint_id}"' in admin_user_detail_source
        assert f'aria-describedby={{{hint_name} ? "{hint_id}" : undefined}}' in admin_user_detail_source


def test_admin_user_account_actions_are_flat_stack_in_source() -> None:
    source = Path("frontend/src/pages/AdminRoutes.tsx").read_text(encoding="utf-8")
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
    assert "disableUser.mutate();" in account_actions_block
    assert "Confirm disable" in account_actions_block

    assert '<label className="field">' in account_actions_block
    assert "id=\"admin-delete-confirm-email\"" in account_actions_block
    assert "onClick={() => deleteUser.mutate()}" in account_actions_block
    assert "disabled={mutationPending || !deleteEmailMatches}" in account_actions_block
    assert "{deleteUser.isPending ? \"Deleting...\" : \"Delete user\"}" in account_actions_block
    assert "Delete user" in account_actions_block
    assert 'className="ghost-button"' in account_actions_block

    assert 'className="meta"' in account_actions_block
    assert "status-error admin-non-admin-note" not in account_actions_block
    assert "status-error" not in account_actions_block


def test_session_chat_logs_card_uses_flask_style_row_hooks_in_source() -> None:
    source = Path("frontend/src/pages/SessionDmPane.tsx").read_text(encoding="utf-8")
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

    row_delete_call = "deleteLog(entry.session.id);"
    row_delete_form_start = chat_logs_source.rfind("<form", 0, chat_logs_source.index(row_delete_call))
    row_delete_form_end = chat_logs_source.index("</form>", row_delete_form_start) + len("</form>")
    row_delete_button_block = chat_logs_source[row_delete_form_start:row_delete_form_end]
    assert 'className="confirmed-action"' in row_delete_button_block
    assert "className=\"ghost-button\"" in row_delete_button_block
    assert "className=\"button-danger\"" not in row_delete_button_block
    assert row_delete_call in row_delete_button_block
    assert "{deleteLogMutation.isPending ? \"Deleting...\" : \"Delete log\"}" in row_delete_button_block
    assert "disabled={!deleteConfirmed || deleteLogMutation.isPending}" in row_delete_button_block

    assert "deleteLog(logQuery.data.session.id);" not in chat_logs_source
    assert "session-log-detail-head" not in chat_logs_source


def test_session_dm_mutations_live_in_shared_hook() -> None:
    pane_source = Path("frontend/src/pages/SessionDmPane.tsx").read_text(encoding="utf-8")
    hook_source = Path("frontend/src/sessionDmMutations.ts").read_text(encoding="utf-8")

    assert 'import { useSessionDmMutations } from "../sessionDmMutations";' in pane_source
    assert "} = useSessionDmMutations({" in pane_source
    assert 'import { useMutation } from "@tanstack/react-query";' not in pane_source
    assert "apiClient.startSession(campaignSlug)" not in pane_source
    assert "apiClient.revealSessionArticle(campaignSlug, articleId)" not in pane_source
    assert "apiClient.deleteSessionLog(campaignSlug, sessionId)" not in pane_source

    assert "export function useSessionDmMutations(" in hook_source
    assert "const startSessionMutation = useMutation({" in hook_source
    assert "const revealArticleMutation = useMutation({" in hook_source
    assert "const deleteLogMutation = useMutation({" in hook_source
    assert 'showToastMessage("Revealed articles cleared.");' in hook_source
    assert "setManualDraft(buildEmptyManualArticleDraft());" in hook_source


def test_combat_action_chrome_in_source() -> None:
    source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    status_panel_source = Path("frontend/src/components/CombatDmStatusPanel.tsx").read_text(encoding="utf-8")
    controls_panel_source = Path("frontend/src/components/CombatDmControlsPanel.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

    remove_call = "onDeleteCombatant();"
    clear_on_click = "onClick={onClearCombat}"

    assert "onDeleteCombatant={() => deleteCombatantMutation.mutate()}" in combat_page_source
    remove_form_start = status_panel_source.rfind("<form", 0, status_panel_source.index(remove_call))
    remove_form_end = status_panel_source.index("</form>", remove_form_start) + len("</form>")
    remove_button_block = status_panel_source[remove_form_start:remove_form_end]
    assert 'className="confirmed-action"' in remove_button_block
    assert 'className="ghost-button"' in remove_button_block
    assert 'aria-describedby={removeCombatantHint ? "combat-remove-combatant-hint" : undefined}' in remove_button_block
    assert 'id="combat-remove-combatant-hint"' in remove_button_block
    assert "Check Confirm removal to enable this action." in status_panel_source
    assert "Selected combatant removal is already in progress." in status_panel_source
    assert "className=\"button button-secondary\"" not in remove_button_block
    assert remove_call in remove_button_block

    assert "onClearCombat={() => clearCombatMutation.mutate()}" in combat_page_source
    clear_button_start = controls_panel_source.rfind("<button", 0, controls_panel_source.index(clear_on_click))
    clear_button_end = controls_panel_source.index("</button>", clear_button_start) + len("</button>")
    clear_button_block = controls_panel_source[clear_button_start:clear_button_end]
    assert 'className="ghost-button"' in clear_button_block
    assert 'aria-describedby={clearTrackerHint ? "combat-clear-tracker-hint" : undefined}' in clear_button_block
    assert 'id="combat-clear-tracker-hint"' in controls_panel_source
    assert "Check Confirm clear tracker to enable this action." in controls_panel_source
    assert "Tracker clear is already in progress." in controls_panel_source
    assert "className=\"button button-secondary\"" not in clear_button_block
    assert clear_on_click in clear_button_block


def test_combat_chrome_components_preserve_summary_carousel_and_view_switch() -> None:
    route_source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    chrome_source = Path("frontend/src/components/CombatChrome.tsx").read_text(encoding="utf-8")

    assert "CombatantCarousel" in route_source
    assert "CombatSummaryBand" in route_source
    assert "CombatViewSwitch" in route_source
    assert "const renderCombatantCard =" not in route_source
    assert "const renderCombatViewSwitch =" not in route_source

    view_switch_source = _extract_component_source(
        chrome_source,
        "export function CombatViewSwitch",
        "interface CombatSummaryBandProps",
    )
    assert 'aria-label="DM encounter subview"' in view_switch_source
    assert 'label: "DM status"' in view_switch_source
    assert 'label: "Controls"' in view_switch_source
    assert 'activeClass: "button-link"' in view_switch_source
    assert 'inactiveClass: "ghost-button"' in view_switch_source
    assert "onClick={() => onSelect(view.id)}" in view_switch_source

    summary_source = _extract_component_source(
        chrome_source,
        "export function CombatSummaryBand",
        "interface CombatantCarouselProps",
    )
    assert 'className="combat-summary-band"' in summary_source
    assert 'aria-label="Encounter summary"' in summary_source
    assert "<span className=\"meta\">Round</span>" in summary_source
    assert "<span className=\"meta\">Current turn</span>" in summary_source
    assert "<span className=\"meta\">Combatants</span>" in summary_source

    carousel_source = chrome_source[chrome_source.index("export function CombatantCarousel") :]
    assert 'className="combat-carousel"' in carousel_source
    assert 'aria-label="Combatant carousel"' in carousel_source
    assert "<h2>Turn Order</h2>" in carousel_source
    assert "Initiative is pinned here while the main panel shows your tracked character." in carousel_source
    assert 'className="combat-carousel-track"' in carousel_source
    assert 'className="combat-turn-order-jump__label"' in carousel_source
    assert 'htmlFor="combat-turn-order-jump-select"' in carousel_source
    assert 'className="combat-turn-order-jump__select"' in carousel_source
    assert "onSelectCombatant(Number(event.currentTarget.value))" in carousel_source

    card_start = chrome_source.index("function CombatantCard(")
    card_end = chrome_source.index("export function CombatantCarousel(", card_start)
    card_source = chrome_source[card_start:card_end]
    assert 'className={isSelected ? "combatant-card combatant-card--selected" : "combatant-card"}' in card_source
    assert "onClick={() => onSelect(combatant.id)}" in card_source
    assert "aria-pressed={isSelected}" in card_source
    assert 'className="combatant-card__topline"' in card_source
    assert 'className="combatant-card__stats"' in card_source
    assert 'className="combatant-card__conditions"' in card_source


def test_combat_dm_controls_add_and_cleanup_chrome_in_source() -> None:
    route_source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    controls_panel_source = Path("frontend/src/components/CombatDmControlsPanel.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(route_source, "CombatPage")

    assert "<CombatDmControlsPanel" in combat_page_source
    assert "onAddSystemsMonster={(entryKey) => addSystemsMonsterMutation.mutate(entryKey)}" in combat_page_source

    add_heading_index = controls_panel_source.index("<h2>Add combatant</h2>")
    add_card_start = controls_panel_source.rfind('<section className="card sidebar-card">', 0, add_heading_index)
    add_card_end = controls_panel_source.index("</section>", add_heading_index) + len("</section>")
    add_card_markup = controls_panel_source[add_card_start:add_card_end]

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

    cleanup_heading_index = controls_panel_source.index("<h2>Encounter cleanup</h2>")
    cleanup_card_start = controls_panel_source.rfind('<section className="card sidebar-card">', 0, cleanup_heading_index)
    cleanup_card_end = controls_panel_source.index("</section>", cleanup_heading_index) + len("</section>")
    cleanup_card_markup = controls_panel_source[cleanup_card_start:cleanup_card_end]

    assert cleanup_card_start >= 0
    assert 'className="card sidebar-card"' in cleanup_card_markup
    assert "className=\"ghost-button\"" in cleanup_card_markup
    assert "onClick={onClearCombat}" in cleanup_card_markup
    assert "Clear tracker" in cleanup_card_markup
    assert 'className="button-row"' not in cleanup_card_markup


def test_campaign_control_page_cleanup_removes_flask_control_fallback_link() -> None:
    control_markup = Path("frontend/src/pages/CampaignControlPage.tsx").read_text(encoding="utf-8")

    assert "Flask Control" not in control_markup
    assert "Flask Control panel" not in control_markup
    assert "className=\"page-layout\"" in control_markup
    assert "className=\"article card\"" in control_markup
    assert "className=\"stack-form\"" in control_markup
    assert "className=\"field\"" in control_markup
    assert 'name={`${row.scope}_visibility`}' in control_markup
    assert "Save visibility" in control_markup
    assert "using default visibility" in control_markup
    assert "<ToastNotice message={toastMessage} tone={toastTone} />" in control_markup
    assert "statusMessage ?" not in control_markup
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
    assert "<h2>Visibility guidance</h2>" in control_markup
    assert "<h3>Visibility rules</h3>" in control_markup
    assert "<h3>Notes</h3>" in control_markup
    assert 'className="sidebar-card-section"' in control_markup

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
    assert ".sidebar-card-section" in source_css


def test_account_settings_page_removes_flask_account_fallback_link() -> None:
    account_settings_markup = Path("frontend/src/pages/AccountSettingsPage.tsx").read_text(encoding="utf-8")

    assert "Flask account" not in account_settings_markup
    assert 'className="ghost-button" href="/campaigns">' in account_settings_markup
    assert "account-sidebar" not in account_settings_markup
    assert "className=\"stack-form\" onSubmit={handleThemeSubmit}>" in account_settings_markup
    assert "className=\"stack-form\" onSubmit={handleChatOrderSubmit}>" in account_settings_markup
    assert "Save theme" in account_settings_markup
    assert "Save chat order" in account_settings_markup
    assert "Save account settings" not in account_settings_markup
    assert "account-settings-actions" not in account_settings_markup
    assert "const descriptionId = `${inputId}-description`;" in account_settings_markup
    assert "const currentStatusId = `${inputId}-current-status`;" in account_settings_markup
    assert "const isCurrent = preferences?.theme_key === theme.key;" in account_settings_markup
    assert "const isCurrent = preferences?.session_chat_order === choice.value;" in account_settings_markup
    assert 'aria-describedby={isCurrent ? `${descriptionId} ${currentStatusId}` : descriptionId}' in account_settings_markup
    assert '<span id={currentStatusId} className="meta theme-option__status">Current</span>' in account_settings_markup
    assert 'className="meta theme-option__description"' in account_settings_markup
    assert (
        'aria-describedby={isThemeUnchanged && !saveThemeSettings.isPending ? "account-theme-save-hint" : undefined}'
        in account_settings_markup
    )
    assert '<p id="account-theme-save-hint" className="meta">Theme is already current.</p>' in account_settings_markup
    assert (
        'aria-describedby={isChatOrderUnchanged && !saveChatSettings.isPending ? "account-chat-order-save-hint" : undefined}'
        in account_settings_markup
    )
    assert '<p id="account-chat-order-save-hint" className="meta">Chat order is already current.</p>' in account_settings_markup
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
    assert "account-sidebar" not in source

    def css_block(selector: str) -> str:
        selector_start = source.index(f"{selector} {{")
        selector_end = source.index("}", selector_start)
        return source[selector_start:selector_end]

    theme_option_block = css_block(".theme-option")
    assert "align-content: start;" not in theme_option_block

    theme_header_block = css_block(".theme-option__header")
    assert "align-items: center;" in theme_header_block
    assert "flex-wrap: wrap;" in theme_header_block
    assert "gap: 1rem;" in theme_header_block

    theme_header_text_match = re.search(r"\.theme-option__header > span:first-child,\s*\.theme-option__description\s*\{([\s\S]*?)\}", source)
    assert theme_header_text_match is not None
    theme_header_text_block = theme_header_text_match.group(1)
    assert "min-width: 0;" in theme_header_text_block
    assert "overflow-wrap: anywhere;" in theme_header_text_block

    theme_status_block = css_block(".theme-option__status")
    assert "margin-left: 0.45rem;" in theme_status_block
    assert "display: block;" not in theme_status_block
    assert "margin-top" not in theme_status_block


def test_campaign_help_page_removes_flask_help_fallback() -> None:
    help_markup = Path("frontend/src/pages/CampaignHelpPage.tsx").read_text(encoding="utf-8")

    assert "Flask Help" not in help_markup
    assert "help-anchor-row" not in help_markup
    assert "campaign-help-account-actions" not in help_markup
    assert "detail-card help-detail-card" not in help_markup
    assert "<h2>Help reference</h2>" in help_markup
    assert help_markup.count('className="card sidebar-card session-sidebar-card"') == 1
    assert 'className="sidebar-card-section"' in help_markup
    assert "<h3>Visibility by scope</h3>" in help_markup
    assert "<h3>Cross-cutting limits</h3>" in help_markup
    assert "<h3>Account settings</h3>" in help_markup
    assert "<h4>{row.label}</h4>" in help_markup
    assert 'className="help-panel"' in help_markup
    assert 'href={data.links.account_url}>Open Account</a>' in help_markup
    assert "href={data.links.sign_in_url}>Sign in</a>" in help_markup
    assert "and which first-pass limits still shape the workflow." not in help_markup
    assert "and which workflow constraints still shape the experience." in help_markup
    assert '<p><strong>{surface.status_label}</strong></p>' not in help_markup
    assert 'tabIndex={-1}' in help_markup

    help_css = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    assert ".help-panel" in help_css
    assert ".help-panel h4" in help_css
    assert ".help-detail-card" not in help_css
    assert ".campaign-help-surface:target" in help_css
    assert ".campaign-help-surface:focus-visible" in help_css
    assert ".button-link:focus-visible" in help_css
    assert ".ghost-button:focus-visible" in help_css

    top_help_row_match = re.search(
        r'<nav className="hero-actions campaign-help-section-nav" aria-label="Help sections">([\s\S]*?)</nav>',
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
        assert class_match.group(1) == "ghost-button campaign-help-section-link"


def test_shared_focus_and_field_contracts_use_theme_tokens() -> None:
    source = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    shared_focus_match = re.search(
        r"button:focus-visible,\s*"
        r"\.button:focus-visible,\s*"
        r"\.button-link:focus-visible,\s*"
        r"\.button-danger:focus-visible,\s*"
        r"\.ghost-button:focus-visible,\s*"
        r"\.link-like-button:focus-visible,\s*"
        r"\.tab-button:focus-visible,\s*"
        r"input:focus-visible,\s*"
        r"select:focus-visible,\s*"
        r"textarea:focus-visible\s*\{([\s\S]*?)\}",
        source,
    )
    assert shared_focus_match is not None
    shared_focus_block = shared_focus_match.group(1)
    assert "outline: 2px solid var(--focus-ring);" in shared_focus_block
    assert "outline-offset: 2px;" in shared_focus_block
    assert "var(--accent)" not in shared_focus_block

    help_target_match = re.search(
        r"\.campaign-help-surface:target,\s*"
        r"\.campaign-help-surface:focus-visible\s*\{([\s\S]*?)\}",
        source,
    )
    assert help_target_match is not None
    assert "outline: 2px solid var(--focus-ring);" in help_target_match.group(1)

    field_match = re.search(r"\.field\s*\{([\s\S]*?)\}", source)
    assert field_match is not None
    assert "color: var(--ink);" in field_match.group(1)

    field_control_match = re.search(
        r"\.field input,\s*"
        r"\.field select,\s*"
        r"\.field textarea\s*\{([\s\S]*?)\}",
        source,
    )
    assert field_control_match is not None
    field_control_block = field_control_match.group(1)
    assert "border: 1px solid var(--border);" in field_control_block
    assert "color: var(--ink);" in field_control_block
    assert "background: var(--input-bg);" in field_control_block
    assert "#cfd9e8" not in field_control_block
    assert "#182437" not in field_control_block
    assert "#fff" not in field_control_block

    field_small_match = re.search(r"\.field small\s*\{([\s\S]*?)\}", source)
    assert field_small_match is not None
    assert "color: var(--muted);" in field_small_match.group(1)


def test_systems_entry_navigation_removes_open_flask_entry_link() -> None:
    source = Path("frontend/src/pages/SystemsRoutes.tsx").read_text(encoding="utf-8")
    systems_entry_start = source.index("export function SystemsEntryPage() {")
    systems_entry_markup = source[systems_entry_start:]

    assert "Open Flask entry" not in systems_entry_markup
    assert "Entry Metadata" not in systems_entry_markup
    assert "Entry Reference" in systems_entry_markup
    assert 'className="sidebar-card-section"' in systems_entry_markup
    assert "Systems landing" in systems_entry_markup
    assert "Source page" in systems_entry_markup
    assert "Source category" in systems_entry_markup
    assert "Entry Management" in systems_entry_markup
    management_start = systems_entry_markup.index('<section className="card sidebar-card systems-sidebar-card" id="systems-entry-management">')
    before_management = systems_entry_markup[:management_start]
    management_markup = systems_entry_markup[management_start:]
    assert "Entry key: {entry.entry_key}" not in before_management
    assert "Entry key: {entry.entry_key}" in management_markup


def test_systems_shared_chrome_lives_in_component_module() -> None:
    route_source = Path("frontend/src/pages/SystemsRoutes.tsx").read_text(encoding="utf-8")
    chrome_source = Path("frontend/src/components/SystemsChrome.tsx").read_text(encoding="utf-8")
    source_page_source = _extract_function_component_source(route_source, "SystemsSourcePage")

    assert 'from "../components/SystemsChrome";' in route_source
    assert "function SystemsEntryList" not in route_source
    assert "function SystemsRulesReferenceList" not in route_source
    assert "function SystemsCategoryList" not in route_source
    assert "function SystemsManageLink" not in route_source
    assert "export function systemsIndexHref" in chrome_source
    assert "export function systemsSourceHref" in chrome_source
    assert "export function systemsSourceCategoryHref" in chrome_source
    assert "export function SystemsEntryList" in chrome_source
    assert "export function SystemsRulesReferenceList" in chrome_source
    assert "export function SystemsCategoryList" in chrome_source
    assert "export function SystemsManageLink" in chrome_source
    assert 'className="plain-list systems-entry-list"' in chrome_source
    assert "Systems settings" in chrome_source
    assert "Browse This Source" in source_page_source
    assert "Content Categories" not in source_page_source


def test_systems_player_browse_hides_raw_source_metadata() -> None:
    route_source = Path("frontend/src/pages/SystemsRoutes.tsx").read_text(encoding="utf-8")
    chrome_source = Path("frontend/src/components/SystemsChrome.tsx").read_text(encoding="utf-8")
    index_source = _extract_function_component_source(route_source, "SystemsIndexPage")
    source_page_source = _extract_function_component_source(route_source, "SystemsSourcePage")
    category_page_source = _extract_function_component_source(route_source, "SystemsSourceCategoryPage")
    entry_page_source = _extract_function_component_source(route_source, "SystemsEntryPage")

    assert "source IDs only" not in index_source
    assert "{source.source_id} | {source.license_class_label}" not in index_source
    assert "{source.default_visibility} visibility" not in index_source
    assert "Source policy: {source.license_class_label}" in index_source

    assert "Source ID:" not in source_page_source
    assert "Default visibility:" not in source_page_source
    assert "{data.source.source_id} | {data.source.license_class_label}" not in source_page_source
    assert "{data.source.default_visibility} visibility" not in source_page_source
    assert "<h2>Browse Summary</h2>" in source_page_source
    assert "Source policy: {data.source.license_class_label}" in source_page_source
    assert "Visible entries: {data.browsable_entry_count}" in source_page_source

    assert "Source ID:" not in category_page_source
    assert "{data.source.source_id} | {data.source.license_class_label}" not in category_page_source
    assert "{data.source.default_visibility} visibility" not in category_page_source
    assert "<h2>Category Summary</h2>" in category_page_source
    assert "Source: {data.source.title}" in category_page_source

    management_start = entry_page_source.index('<section className="card sidebar-card systems-sidebar-card" id="systems-entry-management">')
    entry_viewer_source = entry_page_source[:management_start]
    assert "{entry.entry_type_label} | {entry.source_id}" not in entry_viewer_source
    assert '<p className="meta">Source: {entry.source_id}</p>' not in entry_viewer_source
    assert "Source: {sourceState.title}" in entry_viewer_source
    assert "Entry key: {entry.entry_key}" not in entry_viewer_source

    assert "{entry.source_id} | {entry.entry_type_label}" not in chrome_source
    assert "{entry.source_id} |" not in chrome_source


def test_systems_source_category_nav_has_active_state_and_wrap_css() -> None:
    route_source = Path("frontend/src/pages/SystemsRoutes.tsx").read_text(encoding="utf-8")
    chrome_source = Path("frontend/src/components/SystemsChrome.tsx").read_text(encoding="utf-8")
    type_source = Path("frontend/src/api/types.ts").read_text(encoding="utf-8")
    source_css = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    source_page_source = _extract_function_component_source(route_source, "SystemsSourcePage")
    category_page_source = _extract_function_component_source(route_source, "SystemsSourceCategoryPage")

    assert "export function SystemsSourceNav" in chrome_source
    assert 'className="systems-source-nav"' in chrome_source
    assert 'aria-label="Systems source categories"' in chrome_source
    assert 'aria-current={activeEntryType ? undefined : "page"}' in chrome_source
    assert 'aria-current={isActive ? "page" : undefined}' in chrome_source
    assert 'className="systems-source-nav__count"' in chrome_source

    assert "SystemsSourceNav" in source_page_source
    assert "SystemsCategoryList" not in source_page_source
    assert "sourceTitle={data.source.title}" in source_page_source
    assert "groups={data.entry_groups}" in source_page_source

    assert "SystemsSourceNav" in category_page_source
    assert "groups={data.entry_groups}" in category_page_source
    assert "activeEntryType={data.entry_type}" in category_page_source
    assert "entry_groups: SystemsSourceBrowseGroup[];" in type_source

    source_nav_match = re.search(r"\.systems-source-nav\s*\{([\s\S]*?)\}", source_css)
    assert source_nav_match is not None
    source_nav_block = source_nav_match.group(1)
    assert "display: flex;" in source_nav_block
    assert "flex-wrap: wrap;" in source_nav_block
    assert "gap: 0.45rem;" in source_nav_block
    assert ".systems-source-nav .button-link[aria-current=\"page\"]" in source_css
    assert "box-shadow: 0 0 0 2px var(--border-accent);" in source_css
    assert "color-mix" not in source_css


def test_combat_empty_tracker_prompt_uses_current_surface_wording() -> None:
    source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

    assert "Use the Encounter controls or DM controls to seed the encounter for now." in combat_page_source
    assert "Use the Flask DM controls to seed the encounter for now." not in combat_page_source


def test_gen2_combat_focus_changes_preserve_mounted_payload_in_source() -> None:
    source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    workspace_source = Path("frontend/src/components/CombatPlayerWorkspace.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

    assert "const navigate = useNavigate();" in combat_page_source
    assert "const setCombatUrl = (view: CombatView, combatantId: number | null) => {" in combat_page_source
    assert 'params.set("combatant", String(combatantId));' in combat_page_source
    assert "setCombatUrl(view, selectedCombatantId ?? selectedCombatant?.id ?? null);" in combat_page_source
    assert "void navigate({ to: nextPath as never });" in combat_page_source
    assert "window.history.pushState" not in combat_page_source
    assert "window.location.assign" not in combat_page_source
    assert "window.location.href =" not in combat_page_source
    assert "placeholderData: (previousData) => previousData" in combat_page_source
    assert "focusedCombatantFromTracker" in combat_page_source
    assert "syncCombatantDrafts(focusedCombatant);" in combat_page_source
    assert 'onClick={() => onSelectCombatant(target.combatant_id)}' in workspace_source
    assert 'href={target' not in workspace_source
    assert 'href={`${target' not in workspace_source


def test_gen2_combat_dm_resolves_away_from_player_workspace_in_source() -> None:
    source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")

    assert (
        'const effectiveCombatView: CombatView = canManageCombat\n'
        '    ? activeCombatView === "controls"\n'
        '      ? "controls"\n'
        '      : "status"\n'
        '    : "player";'
    ) in combat_page_source
    assert 'import { CombatPlayerWorkspace } from "../components/CombatPlayerWorkspace";' in source
    assert '<CombatPlayerWorkspace' in combat_page_source
    assert 'onSelectCombatant={selectCombatant}' in combat_page_source
    assert 'onSelectedCharacterChange={selectCharacterTarget}' in combat_page_source
    assert 'import { CombatDmStatusPanel } from "../components/CombatDmStatusPanel";' in source
    assert '<CombatDmStatusPanel' in combat_page_source


def test_combat_player_selected_snapshot_uses_label_value_tactical_tiles() -> None:
    source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    combat_page_source = _extract_function_component_source(source, "CombatPage")
    snapshot_start = combat_page_source.index('<section className="combat-selected-snapshot card combat-character-snapshot">')
    snapshot_end = combat_page_source.index('{effectiveCombatView === "status"', snapshot_start)
    snapshot_markup = combat_page_source[snapshot_start:snapshot_end]

    assert 'className="combat-selected-snapshot__stats" aria-label="Selected combatant tactical values"' in snapshot_markup
    assert 'className="combat-stat-tile__label">HP</span>' in snapshot_markup
    assert 'className="combat-stat-tile__label">Move</span>' in snapshot_markup
    assert 'className="combat-stat-tile__label">Action</span>' in snapshot_markup
    assert 'className="combat-stat-tile__label">Bonus</span>' in snapshot_markup
    assert 'className="combat-stat-tile__label">Reaction</span>' in snapshot_markup
    assert "{selectedCombatant.has_action ? \"Available\" : \"Spent\"}" in snapshot_markup
    assert "{selectedCombatant.has_bonus_action ? \"Available\" : \"Spent\"}" in snapshot_markup
    assert "{selectedCombatant.has_reaction ? \"Available\" : \"Spent\"}" in snapshot_markup
    assert "HP {readNumber(selectedCombatant.current_hp)}" not in snapshot_markup
    assert "No action" not in snapshot_markup
    assert ".combat-stat-tile {" in styles
    assert ".combat-stat-tile__label {" in styles
    assert ".combat-stat-tile__value {" in styles


def test_gen2_combat_dm_status_omits_nested_selected_pc_detail_in_source() -> None:
    route_source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    dm_status_source = Path("frontend/src/components/CombatDmStatusPanel.tsx").read_text(encoding="utf-8")

    assert "const renderDmStatus" not in route_source
    assert "<CombatDmStatusPanel" in route_source
    assert "Selected PC detail" not in dm_status_source
    assert "initialCharacterSlug={selectedCombatant.character_slug}" not in dm_status_source


def test_combat_mutations_live_in_shared_hook() -> None:
    route_source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    hook_source = Path("frontend/src/combatMutations.ts").read_text(encoding="utf-8")

    assert 'import { useCombatMutations, type CombatConditionDraft } from "../combatMutations";' in route_source
    assert "} = useCombatMutations({" in route_source
    assert "export function useCombatMutations(" in hook_source
    assert "apiClient.patchCombatantTurn" in hook_source
    assert "apiClient.patchCombatantVitals" in hook_source
    assert "apiClient.patchCombatantResources" in hook_source
    assert "apiClient.addCombatPlayer" in hook_source
    assert "apiClient.addCombatNpc" in hook_source
    assert "apiClient.addCombatStatblock" in hook_source
    assert "apiClient.addCombatSystemsMonster" in hook_source
    assert "apiClient.searchCombatSystemsMonsters" in hook_source
    assert 'queryClient.setQueryData(["combat", campaignSlug, activeCombatView, selectedCombatantId], response);' in hook_source
    assert "const updateTurnMutation = useMutation" not in route_source
    assert "apiClient.patchCombatantTurn" not in route_source
    assert "apiClient.addCombatPlayer" not in route_source


def test_combat_turn_focus_dm_status_chrome_in_source() -> None:
    source = Path("frontend/src/components/CombatDmStatusPanel.tsx").read_text(encoding="utf-8")

    turn_focus_match = re.search(
        r'<article className="card combat-control-card">\s*<div className="section-heading combat-status-snapshot__heading"[\s\S]*?</article>',
        source,
    )
    assert turn_focus_match is not None
    turn_focus_markup = turn_focus_match.group(0)

    assert 'className="section-heading combat-status-snapshot__heading"' in turn_focus_markup
    assert '<div className="combatant-badges">' in turn_focus_markup
    assert 'className="combat-badge">Round {trackerRoundNumber ?? "?"}</span>' in turn_focus_markup
    assert 'className="combat-badge">Turn {selectedCombatant.turn_value}</span>' in turn_focus_markup
    assert '<span className="combat-badge combat-badge--active">Current turn</span>' in turn_focus_markup
    assert (
        'className="combat-badge combat-badge--button combat-status-snapshot__set-current"'
        in turn_focus_markup
    )
    assert (
        re.search(
            r'<button[^>]*className="combat-badge combat-badge--button combat-status-snapshot__set-current"[^>]*'
            r'onClick=\{onSetCurrent\}[^>]*disabled=\{isSettingCurrent\}\s*>',
            turn_focus_markup,
        )
        is not None
    )
    assert '{isSettingCurrent ? "Setting..." : "Set current"}' in turn_focus_markup

    assert 'id="combat-turn-editor-help"' in turn_focus_markup
    assert "Turn value orders initiative. Priority breaks ties after turn value." in turn_focus_markup
    assert 'className="stack-form combat-status-authority-form"' in turn_focus_markup
    assert 'aria-describedby="combat-turn-editor-help"' in turn_focus_markup
    assert re.search(r'<label className="field">\s*<span>Turn value</span>', turn_focus_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Priority</span>', turn_focus_markup) is not None
    assert "className=\"chat-label\"" not in turn_focus_markup

    assert 'className="hero-actions combat-turn-actions"' in turn_focus_markup
    assert '{isAdvancingTurn ? "Advancing..." : "Advance turn"}' in turn_focus_markup
    assert '<button type="button" onClick={onAdvanceTurn} disabled={isAdvancingTurn}>' in turn_focus_markup

    assert '<div className="button-row">' not in turn_focus_markup


def test_combat_dm_status_tactical_forms_chrome_in_source() -> None:
    combat_page_source = Path("frontend/src/components/CombatDmStatusPanel.tsx").read_text(encoding="utf-8")

    tactical_start = combat_page_source.index('<section className="combat-dm-grid" aria-label="DM tactical controls">')
    tactical_end = combat_page_source.index('<section className="card combat-danger-card">', tactical_start)
    tactical_markup = combat_page_source[tactical_start:tactical_end]

    assert "combat-summary-grid combat-summary-grid--snapshot" in tactical_markup
    assert 'id="combat-vitals-editor-help"' in tactical_markup
    assert "Current and temp HP save for every combatant. NPC maximums appear when editable." in tactical_markup
    assert 'aria-describedby="combat-vitals-editor-help"' in tactical_markup
    assert "combat-stat combat-stat--editable" in tactical_markup
    assert "combat-stat-input combat-stat-input--number" in tactical_markup
    assert "combat-stat-input combat-stat-input--single" in tactical_markup
    assert "combat-inline-value" in tactical_markup
    assert 'id="combat-economy-editor-help"' in tactical_markup
    assert "Checked actions are available. Movement left saves with the action economy." in tactical_markup
    assert 'aria-describedby="combat-economy-editor-help"' in tactical_markup
    assert "combat-resource-strip combat-inline-resource-form" in tactical_markup
    assert "combat-resource-toggle" in tactical_markup
    assert "combat-resource" in tactical_markup
    assert '<span className="meta">Move left</span>' in tactical_markup

    assert "combat-inline-form" not in tactical_markup
    assert 'className="chat-label"' not in tactical_markup


def test_combat_player_workspace_target_chrome_in_source() -> None:
    source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
    workspace_markup = Path("frontend/src/components/CombatPlayerWorkspace.tsx").read_text(encoding="utf-8")

    assert 'import { CombatPlayerWorkspace } from "../components/CombatPlayerWorkspace";' in source
    assert "const renderPlayerWorkspace" not in source
    assert "<CombatPlayerWorkspace" in source

    assert 'className="combat-target-list"' in workspace_markup
    assert 'className={target.is_selected ? "button-link" : "ghost-button"}' in workspace_markup
    assert 'onClick={() => onSelectCombatant(target.combatant_id)}' in workspace_markup
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
    combat_page_source = Path("frontend/src/components/CombatDmStatusPanel.tsx").read_text(encoding="utf-8")

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
        r'<button\s+type="button"\s+className="ghost-button"[^>]*onClick=\{\(\) => onDeleteCondition\(condition\)\}[^>]*>\s*Remove\s*</button>',
        condition_section_markup,
    ) is not None
    assert "className=\"button button-secondary\"" not in condition_section_markup


def test_character_maintenance_unsupported_card_chrome_in_source() -> None:
    source = Path("frontend/src/pages/CharacterCultivationPage.tsx").read_text(encoding="utf-8")
    advanced_source = Path("frontend/src/pages/CharacterAdvancedEditorPage.tsx").read_text(encoding="utf-8")
    level_up_source = Path("frontend/src/pages/CharacterLevelUpPage.tsx").read_text(encoding="utf-8")
    progression_source = Path("frontend/src/pages/CharacterProgressionRepairPage.tsx").read_text(encoding="utf-8")
    retraining_source = Path("frontend/src/pages/CharacterRetrainingPage.tsx").read_text(encoding="utf-8")
    route_sources = {
        "CharacterAdvancedEditorPage": advanced_source,
        "CharacterLevelUpPage": level_up_source,
        "CharacterProgressionRepairPage": progression_source,
        "CharacterRetrainingPage": retraining_source,
    }

    def component_source(component_name: str) -> str:
        component_owner = route_sources.get(component_name, source)
        return _extract_function_component_source(component_owner, component_name)

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
    source = Path("frontend/src/pages/CharacterCultivationPage.tsx").read_text(encoding="utf-8")
    advanced_source = Path("frontend/src/pages/CharacterAdvancedEditorPage.tsx").read_text(encoding="utf-8")
    level_up_source = Path("frontend/src/pages/CharacterLevelUpPage.tsx").read_text(encoding="utf-8")
    progression_source = Path("frontend/src/pages/CharacterProgressionRepairPage.tsx").read_text(encoding="utf-8")
    retraining_source = Path("frontend/src/pages/CharacterRetrainingPage.tsx").read_text(encoding="utf-8")
    create_source = Path("frontend/src/pages/CharacterCreatePage.tsx").read_text(encoding="utf-8")
    manual_import_source = Path("frontend/src/pages/CharacterXianxiaManualImportPage.tsx").read_text(encoding="utf-8")
    route_sources = {
        "CharacterAdvancedEditorPage": advanced_source,
        "CharacterLevelUpPage": level_up_source,
        "CharacterProgressionRepairPage": progression_source,
        "CharacterRetrainingPage": retraining_source,
    }

    def component_source(component_name: str) -> str:
        component_owner = route_sources.get(component_name, source)
        return _extract_function_component_source(component_owner, component_name)

    def supported_component(component_name: str) -> str:
        component = component_source(component_name)
        unsupported_marker = "{data && !data.supported ? ("
        if unsupported_marker in component:
            return component.split(unsupported_marker, 1)[1].split(") : null}", 1)[1]
        return component

    create_markup = _extract_function_component_source(create_source, "CharacterCreatePage")
    assert (
        re.search(
            r'<button\s+type="button"\s+className="ghost-button"\s+onClick=\{\(\) => refreshContext\(\)\}>\s*'
            r"Refresh options\s*</button>",
            create_markup,
        )
        is not None
    )
    assert "className=\"button button-secondary\"" not in create_markup

    manual_markup = _extract_function_component_source(manual_import_source, "CharacterXianxiaManualImportPage")
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


def test_character_authoring_labels_and_confirmation_chrome_in_source() -> None:
    create_source = Path("frontend/src/pages/CharacterCreatePage.tsx").read_text(encoding="utf-8")
    manual_import_source = Path("frontend/src/pages/CharacterXianxiaManualImportPage.tsx").read_text(encoding="utf-8")
    editor_source = Path("frontend/src/pages/CharacterAdvancedEditorPage.tsx").read_text(encoding="utf-8")
    realm_source = Path("frontend/src/components/CharacterCultivationRealmAscension.tsx").read_text(encoding="utf-8")

    assert '["character_slug", "Character URL name", "Auto-generated from name if blank"]' in create_source
    assert "<span>Character URL name</span>" in create_source
    assert '["character_slug", "Character URL name", ""]' in manual_import_source
    assert "<span>Stored Martial Art</span>" in manual_import_source
    assert '<option value="">Unlinked/manual</option>' in manual_import_source
    assert '[row.name_input_name, "Manual Name", row.name]' in manual_import_source
    assert "<h2>Review Import</h2>" in manual_import_source
    assert '{importMutation.isPending ? "Previewing..." : "Preview import"}' in manual_import_source
    assert '{importMutation.isPending ? "Importing..." : "Confirm import"}' in manual_import_source

    assert "<span>Character slug</span>" not in create_source
    assert "<span>Character slug</span>" not in manual_import_source
    assert "<span>Slug</span>" not in create_source
    assert "<span>Slug</span>" not in manual_import_source

    assert "Track sourced max-HP and ability-score reductions here" in editor_source
    assert "<span>Source</span>" in editor_source
    assert "<h2>Custom Features</h2>" in editor_source
    assert "<h2>Manual Equipment</h2>" in editor_source

    for input_name, label in (
        ("realm_ascension_reset_confirmed", "Confirm reset"),
        ("realm_ascension_rebuild_confirmed", "Confirm rebuild"),
        ("realm_ascension_final_confirmed", "Confirm ascension"),
    ):
        assert re.search(
            rf'<div className="confirmed-action">\s*'
            rf'<label className="checkbox-label">\s*'
            rf'<input type="checkbox" name="{input_name}" required />\s*'
            rf"<span>{label}</span>",
            realm_source,
        ) is not None

    assert 'name="realm_ascension_gm_review_note" rows={3} required' in realm_source
    assert 'name="realm_ascension_gm_confirmation_note" rows={3} required' in realm_source


def test_character_supported_hero_links_preserve_supported_nav_while_hiding_flask_fallbacks() -> None:
    source = Path("frontend/src/pages/CharacterCultivationPage.tsx").read_text(encoding="utf-8")
    advanced_source = Path("frontend/src/pages/CharacterAdvancedEditorPage.tsx").read_text(encoding="utf-8")
    level_up_source = Path("frontend/src/pages/CharacterLevelUpPage.tsx").read_text(encoding="utf-8")
    progression_source = Path("frontend/src/pages/CharacterProgressionRepairPage.tsx").read_text(encoding="utf-8")
    retraining_source = Path("frontend/src/pages/CharacterRetrainingPage.tsx").read_text(encoding="utf-8")
    create_source = Path("frontend/src/pages/CharacterCreatePage.tsx").read_text(encoding="utf-8")
    manual_import_source = Path("frontend/src/pages/CharacterXianxiaManualImportPage.tsx").read_text(encoding="utf-8")
    route_sources = {
        "CharacterAdvancedEditorPage": advanced_source,
        "CharacterLevelUpPage": level_up_source,
        "CharacterProgressionRepairPage": progression_source,
        "CharacterRetrainingPage": retraining_source,
    }

    def component_source(component_name: str) -> str:
        component_owner = route_sources.get(component_name, source)
        return _extract_function_component_source(component_owner, component_name)

    def hero_section(component_name: str) -> str:
        component = component_source(component_name)
        hero_start = component.index('<section className="hero')
        hero_end = component.index("</section>", hero_start) + len("</section>")
        return component[hero_start:hero_end]

    create_component = _extract_function_component_source(create_source, "CharacterCreatePage")
    create_hero_start = create_component.index('<section className="hero')
    create_hero = create_component[create_hero_start:create_component.index("</section>", create_hero_start) + len("</section>")]
    assert "Flask create" not in create_hero
    assert "Back to roster" in create_hero
    assert "Import existing" in create_hero

    manual_component = _extract_function_component_source(manual_import_source, "CharacterXianxiaManualImportPage")
    manual_hero_start = manual_component.index('<section className="hero')
    manual_hero = manual_component[manual_hero_start:manual_component.index("</section>", manual_hero_start) + len("</section>")]
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
    roster_source = Path("frontend/src/pages/CharacterRosterPage.tsx").read_text(encoding="utf-8")

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
    roster_source = Path("frontend/src/pages/CharacterRosterPage.tsx").read_text(encoding="utf-8")

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
    roster_source = Path("frontend/src/pages/CharacterRosterPage.tsx").read_text(encoding="utf-8")
    navigation_source = Path("frontend/src/components/CharacterNavigationCard.tsx").read_text(encoding="utf-8")

    card_start = roster_source.index('<article className="card character-card"')
    card_end = roster_source.index("</article>", card_start) + len("</article>")
    card_markup = roster_source[card_start:card_end]
    stats_markup = card_markup[card_markup.index('<div className="character-card__stats">'): card_markup.index("</a>", card_markup.index("className=\"button-link\""))]

    assert 'className="character-card__meta"' in card_markup
    assert 'join(" / ")' in card_markup
    assert 'join(" | ")' not in card_markup

    assert "<article>" not in stats_markup
    assert '<div className="character-card__stats">' in stats_markup
    assert card_markup.count("className=\"character-card__top\"") == 1
    assert 'className="button-link"' in card_markup
    assert "{character.name}" in card_markup
    assert ">{character.slug}</" not in card_markup
    assert "Status:" not in card_markup
    assert "{item.name}" in navigation_source
    assert 'aria-current={isActive ? "page" : undefined}' in navigation_source


def test_character_section_empty_states_are_not_status_alerts() -> None:
    section_paths = [
        Path("frontend/src/components/CharacterDndResourcesSection.tsx"),
        Path("frontend/src/components/CharacterDndEquipmentSection.tsx"),
        Path("frontend/src/components/CharacterXianxiaInventorySection.tsx"),
    ]
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    for section_path in section_paths:
        source = section_path.read_text(encoding="utf-8")
        assert 'className="detail-card character-empty-state"' in source
        assert 'className="status status-neutral"' not in source

    assert ".character-empty-state p {" in styles


def test_session_character_identity_uses_names_not_slugs_or_status_fields() -> None:
    pane_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    header_source = Path("frontend/src/components/CharacterHeader.tsx").read_text(encoding="utf-8")
    navigation_source = Path("frontend/src/components/CharacterNavigationCard.tsx").read_text(encoding="utf-8")
    summary_source = Path("frontend/src/components/CharacterSummaryCard.tsx").read_text(encoding="utf-8")

    assert "selectedName={selected?.name}" in pane_source
    assert "{selectedName || surfaceHeading}" in header_source
    assert "{item.name}" in navigation_source
    assert "<h3>{selected.name}</h3>" in summary_source
    assert ">{selected.slug}</" not in summary_source
    assert ">{item.slug}</" not in navigation_source
    assert "Status:" not in summary_source
    assert "Status:" not in header_source


def test_character_roster_empty_state_copy_is_exact_in_source() -> None:
    source = Path("frontend/src/pages/CharacterRosterPage.tsx").read_text(encoding="utf-8")
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
    source = Path("frontend/src/pages/CharacterCultivationPage.tsx").read_text(encoding="utf-8")
    create_source = Path("frontend/src/pages/CharacterCreatePage.tsx").read_text(encoding="utf-8")
    level_up_source = Path("frontend/src/pages/CharacterLevelUpPage.tsx").read_text(encoding="utf-8")
    manual_import_source = Path("frontend/src/pages/CharacterXianxiaManualImportPage.tsx").read_text(encoding="utf-8")

    def component_source(component_name: str) -> str:
        component_owner = level_up_source if component_name == "CharacterLevelUpPage" else source
        return _extract_function_component_source(component_owner, component_name)

    create_markup = _extract_function_component_source(create_source, "CharacterCreatePage")
    assert re.search(r'<div className="builder-actions">[\s\S]*?<button\s+type="submit"\s+disabled={!create\.builder_ready \|\| createMutation\.isPending}>', create_markup) is not None
    assert (
        re.search(
            r'<button\s+type="button"\s+className="ghost-button"\s+onClick=\{\(\) => refreshContext\(\)\}>\s*'
            r"Refresh options\s*</button>",
            create_markup,
        )
        is not None
    )

    manual_markup = _extract_function_component_source(manual_import_source, "CharacterXianxiaManualImportPage")
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
    source = Path("frontend/src/pages/CombatPage.tsx").read_text(encoding="utf-8")
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
    assert "const campaignHomeHref = `/app-next/campaigns/${encodedCampaignSlug}`;" in combat_page_source
    assert "const campaignCharactersHref = `${campaignHomeHref}/characters`;" in combat_page_source
    assert "const campaignSessionHref = `${campaignHomeHref}/session`;" in combat_page_source
    assert '<a className="button-link" href={campaignHomeHref}>' in unsupported_markup
    assert '<a className="ghost-button" href={campaignCharactersHref}>' in unsupported_markup
    assert '<a className="ghost-button" href={campaignSessionHref}>' in unsupported_markup
    assert "flask_campaign_url" not in unsupported_markup
    assert "flask_characters_url" not in unsupported_markup
    assert "flask_session_url" not in unsupported_markup
    assert "Open Campaign Home" in unsupported_markup
    assert "Open Characters" in unsupported_markup
    assert "Open Session" in unsupported_markup
    assert "Open Flask Combat" not in unsupported_markup
    assert "button button-secondary" not in unsupported_markup

    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.auth-card\s*\{\s*max-width:\s*36rem;\s*\}", styles) is not None


def test_character_portrait_manager_action_chrome_in_source() -> None:
    source = Path("frontend/src/components/CharacterPortraitManager.tsx").read_text(encoding="utf-8")
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


def test_character_summary_card_chrome_in_source() -> None:
    source = Path("frontend/src/components/CharacterSummaryCard.tsx").read_text(encoding="utf-8")

    assert 'className="character-summary"' in source
    assert 'className="character-summary__main"' in source
    assert 'className="character-portrait"' in source
    assert 'alt={selectedPortrait.alt_text || selected.name}' in source
    assert 'className="plain-list resource-preview-list"' in source
    assert "HP: {currentHp} / {maxHp}" in source
    assert "Temp HP: {tempHp}" in source
    assert "Hit Dice: {selected.hit_dice.value}" in source
    assert 'Class: {selected.class_level_text || "Unknown"}' in source
    assert "System: {systemLabel}" in source
    assert "{children}" in source
    assert 'className="character-state-card"' not in source
    assert 'className="button-row character-portrait-manager__actions"' not in source


def test_dm_article_creator_uses_flask_style_mode_panels_and_fields() -> None:
    source = Path("frontend/src/components/DmArticleCreator.tsx").read_text(encoding="utf-8")
    dropzone_source = Path("frontend/src/components/SessionFileDropzone.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    component_start = source.index("function DmArticleCreator({")
    creator_markup = source[component_start:]

    assert 'import { SessionFileDropzone } from "./SessionFileDropzone";' in source
    assert 'const modeHelpId = `${idSeed}-article-mode-help`;' in creator_markup
    assert "aria-describedby={modeHelpId}" in creator_markup
    assert 'className="stack-form"' in creator_markup
    assert 'className="session-form-mode-radio session-form-mode-radio--manual"' in creator_markup
    assert 'className="session-form-mode-radio session-form-mode-radio--upload"' in creator_markup
    assert 'className="session-form-mode-radio session-form-mode-radio--wiki"' in creator_markup
    assert 'className="session-form-mode-toggle"' in creator_markup
    assert 'id={modeHelpId} className="meta session-article-mode-help"' in creator_markup
    assert 'className="status status-neutral">{instructions}</p>' not in creator_markup
    assert 'className="session-article-mode-panel session-article-mode-panel--manual"' in creator_markup
    assert 'className="session-article-mode-panel session-article-mode-panel--upload"' in creator_markup
    assert 'className="session-article-mode-panel session-article-mode-panel--wiki"' in creator_markup
    assert 'className="field"' in creator_markup
    assert "<SessionFileDropzone" in creator_markup
    assert "selectedFileName={manualDraft.image ? manualDraft.image.filename : undefined}" in creator_markup
    assert "selectedFileName={uploadDraft.image ? uploadDraft.image.filename : undefined}" in creator_markup
    assert "className=\"session-form\"" not in creator_markup
    assert 'className="segmented"' not in creator_markup
    assert "className=\"segmented-button\"" not in creator_markup
    assert 'className="chat-label"' not in creator_markup
    assert "Search wiki / systems" not in creator_markup
    assert "Lookup" in creator_markup
    assert ".session-article-mode-help" in styles
    assert 'className="meta session-article-selected-source"' in creator_markup
    assert "Selected source:" not in creator_markup
    assert 'className="field session-file-field"' in dropzone_source
    assert 'className="session-file-input"' in dropzone_source
    assert 'className={`session-file-dropzone${isDragging ? " is-dragging" : ""}`}' in dropzone_source
    assert "onDragOver={handleDragOver}" in dropzone_source
    assert "onDrop={handleDrop}" in dropzone_source
    assert "event.dataTransfer.files?.item(0)" in dropzone_source
    assert "aria-labelledby={labelId}" in dropzone_source
    assert 'aria-describedby={`${descriptionId} ${fileNameId}`}' in dropzone_source
    assert 'id={fileNameId} aria-live="polite"' in dropzone_source
    assert 'event.dataTransfer.dropEffect = "none";' in dropzone_source
    assert "tabIndex" not in dropzone_source
    assert ".session-file-input:focus-visible + .session-file-dropzone" in styles


def test_session_dm_article_source_search_status_is_specific() -> None:
    source = Path("frontend/src/pages/SessionDmPane.tsx").read_text(encoding="utf-8")

    assert "function formatSourceSearchStatus" in source
    assert "Search complete." not in source
    assert 'return `Found ${resultCount} matching article${resultCount === 1 ? "" : "s"}.`;' in source
    assert 'setSourceStatus(formatSourceSearchStatus(response.message, response.results.length));' in source


def test_session_article_source_metadata_is_action_or_recovery_only() -> None:
    source = Path("frontend/src/components/SessionArticleDisplay.tsx").read_text(encoding="utf-8")
    source_line = source[
        source.index("export function SessionArticleSourceLine"):
        source.index("export function SessionArticleReferenceActions")
    ]
    actions = source[source.index("export function SessionArticleReferenceActions"):]

    assert "if (sourceTitle && !sourceUrl)" in source_line
    assert "Pulled from" not in source_line
    assert 'const sourceContext = sourceLabel ? `Source (${sourceLabel})` : "Source";' in source_line
    assert "{sourceContext}: {sourceTitle}" in source_line
    assert "article.source?.missing_message" in source_line
    assert "if (sourceUrl)" in actions
    assert "{article.source?.action_label || \"View source\"}" in actions


def test_wiki_home_uses_section_cards_while_detail_pages_keep_section_nav() -> None:
    source = Path("frontend/src/pages/WikiRoutes.tsx").read_text(encoding="utf-8")
    chrome_source = Path("frontend/src/components/WikiChrome.tsx").read_text(encoding="utf-8")
    nav_source = _extract_component_source(
        chrome_source,
        "export function WikiSectionNav({",
        "export function WikiSectionBrowse({",
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

    assert 'from "../components/WikiChrome"' in source
    assert "function WikiSectionNav({" not in source
    assert "function WikiHomeSectionGrid({" not in source
    assert "function WikiSectionBrowse({" not in source
    assert 'className="wiki-section-nav"' in nav_source
    assert 'aria-label="Wiki sections"' in nav_source
    assert 'href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}' in nav_source
    assert 'aria-current={isActive ? "page" : undefined}' in nav_source
    assert 'title={`${section.page_count} page${section.page_count === 1 ? "" : "s"}`}' in nav_source

    assert "export function WikiHomeSectionGrid({" in nav_source
    assert 'className="wiki-home-section-grid"' in nav_source
    assert 'aria-label="Campaign wiki sections"' in nav_source
    assert 'className="card wiki-home-section-card"' in nav_source
    assert 'className="wiki-home-section-card__icon"' in nav_source
    assert "Open {section.section_name}" not in nav_source
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
    assert 'className="wiki-backlink-strip"' in article_page_source
    assert 'aria-label="Pages linking here"' in article_page_source
    assert 'className="wiki-backlink-list"' in article_page_source
    assert '<section className="page-layout wiki-article-page wiki-article-page--single">' in article_page_source
    assert '<aside className="sidebar">' not in article_page_source
    assert "Linked From" not in article_page_source

    assert "<h2>Context</h2>" not in article_page_source
    assert "Campaign:" not in article_page_source
    assert "Section:" not in article_page_source
    assert "campaignContextLink" not in article_page_source
    assert "sectionContextLink" not in article_page_source

    assert ".wiki-section-nav" in styles
    assert ".wiki-home-section-grid" in styles
    assert "grid-template-columns: repeat(6, minmax(0, 1fr));" in styles
    assert ".wiki-home-section-card__icon-svg" in styles
    assert ".wiki-backlink-strip" in styles
    assert ".wiki-backlink-list" in styles
    assert ".wiki-article-page--single" in styles


def test_dm_content_player_wiki_editor_fields_use_flask_style_labels_in_source() -> None:
    source = Path("frontend/src/pages/DmContentPage.tsx").read_text(encoding="utf-8")
    lane_source = Path("frontend/src/components/DmPlayerWikiLane.tsx").read_text(encoding="utf-8")
    card_source = Path("frontend/src/components/DmPlayerWikiPageCard.tsx").read_text(encoding="utf-8")
    fields_source = Path("frontend/src/components/DmPlayerWikiDraftFields.tsx").read_text(encoding="utf-8")

    assert 'import { DmPlayerWikiLane } from "../components/DmPlayerWikiLane";' in source
    assert "<DmPlayerWikiLane" in source
    assert 'import { DmPlayerWikiDraftFields } from "../components/DmPlayerWikiDraftFields";' not in source
    assert 'import { DmPlayerWikiPageCard } from "../components/DmPlayerWikiPageCard";' not in source
    assert "<DmPlayerWikiDraftFields" not in source
    assert "<DmPlayerWikiPageCard" not in source
    assert '<section className="card dm-player-wiki-create">' not in source
    assert 'className="card dm-player-wiki-create"' in lane_source
    assert 'className="card dm-player-wiki-library"' in lane_source
    assert "<DmPlayerWikiDraftFields" in lane_source
    assert "<DmPlayerWikiPageCard" in lane_source
    assert 'className="dm-content-item dm-player-wiki-card"' not in source
    assert 'className="dm-content-item dm-player-wiki-card"' in card_source
    assert "<DmPlayerWikiDraftFields" in card_source
    assert "const renderPlayerWikiDraftFields = ({" not in source

    helper_start = fields_source.index("export function DmPlayerWikiDraftFields(")
    helper_markup = fields_source[helper_start:]

    assert "className=\"chat-label\"" not in helper_markup
    assert "dm-content-image-edit-row" not in helper_markup
    assert '<label className="checkbox-label">' in helper_markup

    expected_player_wiki_fields = [
        ("title", "Title"),
        ("slug", "URL name"),
        ("section", "Section"),
        ("type", "Page type"),
        ("subsection", "Subsection"),
        ("summary", "Summary"),
        ("aliases", "Aliases"),
        ("reveal-after-session", "Reveal after session"),
        ("display-order", "Display order"),
        ("source-ref", "Original source"),
        ("image", "Image asset"),
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
    form_class_matches = re.findall(rf"<form\s+{player_wiki_form_class}", lane_source + card_source)
    assert len(form_class_matches) >= 2
    assert "dm-player-wiki-edit-form" not in source
    assert "dm-player-wiki-edit-form" not in lane_source
    assert "dm-player-wiki-edit-form" not in card_source


def test_dm_content_hero_nav_lives_in_component_module() -> None:
    route_source = Path("frontend/src/pages/DmContentPage.tsx").read_text(encoding="utf-8")
    hero_source = Path("frontend/src/components/DmContentHero.tsx").read_text(encoding="utf-8")

    assert 'import { DmContentHero } from "../components/DmContentHero";' in route_source
    assert "<DmContentHero" in route_source
    assert "laneCounts={dmContentLaneCounts}" in route_source
    assert "lede={dmContentLede}" in route_source
    assert 'className="hero compact dm-content-hero"' not in route_source
    assert 'className="hero compact dm-content-hero"' in hero_source
    assert 'className="character-subpage-nav dm-content-subpage-nav"' in hero_source
    assert 'aria-label="DM Content subpages"' in hero_source
    assert 'aria-current={activeLane === "statblocks" ? "page" : undefined}' in hero_source
    assert 'aria-current={activeLane === "staged-articles" ? "page" : undefined}' in hero_source
    assert 'aria-current={activeLane === "conditions" ? "page" : undefined}' in hero_source
    assert 'aria-current={activeLane === "player-wiki" ? "page" : undefined}' in hero_source
    assert 'aria-current={activeLane === "systems" ? "page" : undefined}' in hero_source
    assert "laneCounts.statblocks" in hero_source
    assert "laneCounts.stagedArticles" in hero_source
    assert "laneCounts.conditions" in hero_source
    assert "laneCounts.playerWiki" in hero_source
    assert "laneCounts.systems" in hero_source
    assert "subpage_counts?.statblocks" in route_source
    assert "subpage_counts?.staged_articles" in route_source


def test_dm_content_create_panels_keep_helper_copy_sparse() -> None:
    statblocks_lane_source = Path("frontend/src/components/DmStatblocksLane.tsx").read_text(encoding="utf-8")
    conditions_lane_source = Path("frontend/src/components/DmConditionsLane.tsx").read_text(encoding="utf-8")
    player_wiki_lane_source = Path("frontend/src/components/DmPlayerWikiLane.tsx").read_text(encoding="utf-8")

    assert "Upload or paste markdown for DM-side encounter prep." not in statblocks_lane_source
    assert "Custom combat condition reminder." not in conditions_lane_source
    assert "Direct authoring for durable player-facing reference pages." not in player_wiki_lane_source
    assert "<h2>Create statblock</h2>" in statblocks_lane_source
    assert "<h2>Create condition</h2>" in conditions_lane_source
    assert "<h2>Create player wiki page</h2>" in player_wiki_lane_source


def test_dm_content_mutations_live_in_shared_hook() -> None:
    route_source = Path("frontend/src/pages/DmContentPage.tsx").read_text(encoding="utf-8")
    hook_source = Path("frontend/src/dmContentMutations.ts").read_text(encoding="utf-8")

    assert 'import { useDmContentMutations } from "../dmContentMutations";' in route_source
    assert "} = useDmContentMutations({" in route_source
    assert 'import { useMutation } from "@tanstack/react-query";' not in route_source
    assert "apiClient.createDmContentStatblock" not in route_source
    assert "apiClient.upsertContentPage" not in route_source
    assert "apiClient.createSessionArticle" not in route_source

    assert "export function useDmContentMutations(" in hook_source
    assert "const createStatblockMutation = useMutation({" in hook_source
    assert "const savePlayerWikiPageMutation = useMutation({" in hook_source
    assert "const createArticleMutation = useMutation({" in hook_source
    assert "buildPlayerWikiAssetRef(args.pageRef, args.draft.imageUpload)" in hook_source
    assert 'showToastMessage("Article staged.");' in hook_source


def test_dm_content_systems_management_form_field_chrome() -> None:
    source = Path("frontend/src/pages/DmContentSystemsLane.tsx").read_text(encoding="utf-8")
    helper_start = source.index("const renderCustomFields = ({")
    helper_end = source.index("  if (systemsQuery.isLoading)", helper_start)
    helper_markup = source[helper_start:helper_end]

    expected_systems_custom_fields = [
        ("title", "Title"),
        ("slug", "URL name"),
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


def test_dm_content_systems_mutations_live_in_shared_hook() -> None:
    lane_source = Path("frontend/src/pages/DmContentSystemsLane.tsx").read_text(encoding="utf-8")
    hook_source = Path("frontend/src/dmContentSystemsMutations.ts").read_text(encoding="utf-8")

    assert "useDmContentSystemsMutations" in lane_source
    assert "} = useDmContentSystemsMutations({" in lane_source
    assert 'import { useMutation } from "@tanstack/react-query";' not in lane_source
    assert "apiClient.updateSystemsSources" not in lane_source
    assert "apiClient.updateSystemsEntryOverride" not in lane_source
    assert "apiClient.createSystemsCustomEntry" not in lane_source

    assert "export function useDmContentSystemsMutations(" in hook_source
    assert "const updateSourcesMutation = useMutation({" in hook_source
    assert "const updateOverrideMutation = useMutation({" in hook_source
    assert "const createCustomMutation = useMutation({" in hook_source
    assert "apiClient.restoreSystemsCustomEntry(campaignSlug, entry.slug)" in hook_source
    assert 'setSystemsMessage("Systems source policy saved.");' in hook_source
    assert "<ToastNotice message={toastMessage} tone={toastTone} />" in lane_source
    assert "Flask form" not in lane_source
    assert "for this slice" not in lane_source
    assert "Import-Run History" not in lane_source
    assert "Open admin import form" not in lane_source
    assert "<h2>Import History</h2>" in lane_source
    assert "Open import form" in lane_source
    assert "review import history and manage campaign policy" in lane_source
    assert "No Systems imports have been recorded yet." in lane_source


def test_dm_content_statblock_and_condition_forms_use_flask_field_labels_in_source() -> None:
    source = Path("frontend/src/pages/DmContentPage.tsx").read_text(encoding="utf-8")
    card_source = Path("frontend/src/components/DmContentCards.tsx").read_text(encoding="utf-8")
    statblocks_lane_source = Path("frontend/src/components/DmStatblocksLane.tsx").read_text(encoding="utf-8")
    conditions_lane_source = Path("frontend/src/components/DmConditionsLane.tsx").read_text(encoding="utf-8")
    source_css = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    assert 'import { DmConditionsLane } from "../components/DmConditionsLane";' in source
    assert 'import { DmStatblocksLane } from "../components/DmStatblocksLane";' in source
    assert "<DmConditionsLane" in source
    assert "<DmStatblocksLane" in source
    assert "const renderConditionCard = (" not in source
    assert "const renderStatblockCard = (" not in source
    assert '<section className="card dm-condition-create">' not in source
    assert '<section className="card dm-statblock-create">' not in source
    assert "<DmContentConditionCard" in conditions_lane_source
    assert "<DmContentStatblockCard" in statblocks_lane_source
    assert 'className="dm-content-list dm-condition-list"' in conditions_lane_source
    assert ".dm-condition-list" in source_css
    assert "grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));" in source_css

    statblock_edit_start = card_source.index("export function DmContentStatblockCard(")
    statblock_edit_end = card_source.index("export function DmContentConditionCard(", statblock_edit_start)
    statblock_edit_markup = card_source[statblock_edit_start:statblock_edit_end]

    assert 'className="chat-label"' not in statblock_edit_markup
    assert 'className="stack-form"' in statblock_edit_markup
    assert '<label className="field">' in statblock_edit_markup
    assert 'className="feature-detail dm-maintenance-detail"' in statblock_edit_markup
    assert "Source filename: {statblock.source_filename}" in statblock_edit_markup
    assert "Parser summary: {statblock.parser_feedback.summary}" in statblock_edit_markup
    assert "Combat seed source" not in statblock_edit_markup
    assert '<p className="status status-neutral">{statblock.parser_feedback.summary}</p>' not in statblock_edit_markup
    assert re.search(r'<label className="field">\s*<span>Subsection</span>', statblock_edit_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Source markdown body</span>', statblock_edit_markup) is not None
    assert 'name="subsection"' in statblock_edit_markup
    assert 'name="markdown_text"' in statblock_edit_markup

    condition_edit_start = card_source.index("export function DmContentConditionCard(")
    condition_edit_markup = card_source[condition_edit_start:]

    assert 'className="chat-label"' not in condition_edit_markup
    assert 'className="stack-form"' in condition_edit_markup
    assert '<label className="field">' in condition_edit_markup
    assert re.search(r'<label className="field">\s*<span>Condition name</span>', condition_edit_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Description</span>', condition_edit_markup) is not None
    assert 'name="name"' in condition_edit_markup
    assert 'name="description_markdown"' in condition_edit_markup

    statblock_create_start = statblocks_lane_source.index('<section className="card dm-statblock-create">')
    statblock_create_end = statblocks_lane_source.index('<section className="card dm-statblock-library">', statblock_create_start)
    statblock_create_markup = statblocks_lane_source[statblock_create_start:statblock_create_end]

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

    condition_create_start = conditions_lane_source.index('<section className="card dm-condition-create">')
    condition_create_end = conditions_lane_source.index('<section className="card dm-condition-library">', condition_create_start)
    condition_create_markup = conditions_lane_source[condition_create_start:condition_create_end]

    assert 'className="stack-form"' in condition_create_markup
    assert 'className="session-form"' not in condition_create_markup
    assert 'className="chat-label"' not in condition_create_markup
    assert re.search(r'<label className="field">\s*<span>Condition name</span>', condition_create_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Description</span>', condition_create_markup) is not None
    assert 'name="name"' in condition_create_markup
    assert 'name="description_markdown"' in condition_create_markup


def test_character_xianxia_inventory_section_uses_flask_style_row_form_chrome() -> None:
    inventory_markup = Path("frontend/src/components/CharacterXianxiaInventorySection.tsx").read_text(encoding="utf-8")
    resources_markup = Path("frontend/src/components/CharacterXianxiaResourcesSection.tsx").read_text(encoding="utf-8")

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

    controls_end = inventory_markup.index('<div className="detail-grid" id="session-currency">')
    inventory_controls_markup = inventory_markup[:controls_end]
    currency_controls_markup = inventory_markup[controls_end:]

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
    assert re.search(r'<button type="submit" className="visually-hidden" disabled=\{isCurrencySaving \|\| !canEdit\}>\s*Update \{entry\.label\}\s*</button>', currency_controls_markup) is not None

    assert 'className="chat-label"' not in currency_controls_markup
    assert 'className="inline-two-col"' not in currency_controls_markup
    assert 'form onSubmit={submitCurrency} className="currency-grid"' not in currency_controls_markup
    assert 'Save currency' not in currency_controls_markup


def test_character_xianxia_resources_section_uses_flask_style_resource_cards() -> None:
    resources_markup = Path("frontend/src/components/CharacterXianxiaResourcesSection.tsx").read_text(encoding="utf-8")

    assert 'Current {pool.current} / Max {pool.max}' in resources_markup
    assert '{pool.temp ? <p className="meta">Temporary {pool.label}: {pool.temp}</p> : null}' in resources_markup
    assert 'className="resource-grid"' in resources_markup
    assert 'className="resource-card"' in resources_markup
    assert 'className="resource-card__value"' in resources_markup
    assert 'Current {xianxiaDao.current} / Max {xianxiaDao.max}' in resources_markup
    assert '<h3>Dao</h3>' in resources_markup
    assert '<h3>Insight</h3>' in resources_markup
    assert 'className="meta">Spent {readNumber(insight.spent, 0)}</p>' in resources_markup
    assert 'id="session-active-state"' in resources_markup

    assert 'className="character-card-grid"' not in resources_markup
    assert 'className="character-state-card"' not in resources_markup
    assert 'className="inline-two-col"' not in resources_markup
    assert 'className="chat-label"' not in resources_markup


def test_character_xianxia_skills_section_uses_flask_style_skill_pills() -> None:
    skills_markup = Path("frontend/src/components/CharacterXianxiaSkillsSection.tsx").read_text(encoding="utf-8")

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
    section_markup = Path("frontend/src/components/CharacterXianxiaEquipmentSection.tsx").read_text(encoding="utf-8")

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
    section_markup = Path("frontend/src/components/CharacterXianxiaQuickReferenceSection.tsx").read_text(encoding="utf-8")

    assert 'id="xianxia-quick-reference"' in section_markup
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
    section_markup = Path("frontend/src/components/CharacterXianxiaQuickReferenceSection.tsx").read_text(encoding="utf-8")

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
    section_markup = Path("frontend/src/components/CharacterXianxiaMartialArtsSection.tsx").read_text(
        encoding="utf-8"
    )

    assert 'id="xianxia-martial-arts"' in section_markup
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
    section_markup = Path("frontend/src/components/CharacterXianxiaTechniquesSection.tsx").read_text(
        encoding="utf-8"
    )

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
    generic_summary_markup = Path("frontend/src/components/CharacterSystemSummarySection.tsx").read_text(encoding="utf-8")

    assert '<section className="read-section" id="character-system-summary">' in generic_summary_markup
    assert 'className="detail-grid"' in generic_summary_markup
    assert '<article className="detail-card">' in generic_summary_markup
    assert "<h3>Current HP</h3>" in generic_summary_markup
    assert "<h3>Temp HP</h3>" in generic_summary_markup
    assert '<strong>{String(currentHp ?? "--")}</strong>' in generic_summary_markup
    assert '<strong>{String(tempHp ?? "--")}</strong>' in generic_summary_markup

    assert 'className="stat-grid"' not in generic_summary_markup


def test_character_pane_status_messages_use_toast_overlay() -> None:
    source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    mutation_source = Path("frontend/src/characterPaneMutations.ts").read_text(encoding="utf-8")
    feedback_source = Path("frontend/src/components/feedback.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    pane_start = source.index("export function CharacterPane(")
    pane_markup = source[pane_start:]

    assert "const TOAST_DISMISS_MS = 3600;" in feedback_source
    assert "function ToastNotice" in feedback_source
    assert 'className={`toast-notice toast-notice--${tone}`}' in feedback_source
    assert 'role="status" aria-live="polite"' in feedback_source
    assert "const timer = window.setTimeout(() => setToastMessage(null), dismissMs);" in feedback_source
    assert "return () => window.clearTimeout(timer);" in feedback_source
    assert "window.setTimeout(" not in pane_markup
    assert "setRestPreview(response.preview);" in mutation_source
    assert 'setStatusMessage(`${response.preview.label} preview loaded.`);' not in mutation_source
    assert "preview loaded." not in pane_markup
    assert "preview loaded." not in mutation_source
    assert "<ToastNotice message={statusMessage} tone={toastTone} />" in pane_markup
    assert 'statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null' not in pane_markup
    assert ".toast-notice {" in styles
    assert "position: fixed;" in styles
    assert "z-index: 1200;" in styles
    assert "animation: toast-notice-fade 3600ms ease forwards;" in styles
    assert "@keyframes toast-notice-fade" in styles


def test_session_player_message_success_uses_toast_overlay() -> None:
    source = Path("frontend/src/pages/SessionRoutes.tsx").read_text(encoding="utf-8")

    assert 'import { ToastNotice, useToastNotice } from "../components/feedback";' in source
    assert 'const { clearToast, showToast, toastMessage, toastTone } = useToastNotice({ defaultTone: "success" });' in source
    assert 'showToast("Message posted.", "success");' in source
    assert "<ToastNotice message={toastMessage} tone={toastTone} />" in source
    assert 'sendError ? <p className="status status-error">{sendError}</p> : null' in source
    assert 'setSendError("Type a message first.");' in source
    assert 'setSendError("No active session.");' in source
    assert 'statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null' not in source
    assert "window.setTimeout(" not in source


def test_session_player_composer_uses_compact_target_row_and_labels() -> None:
    source = Path("frontend/src/pages/SessionRoutes.tsx").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8")
    composer_markup = source[
        source.index("function SessionPaneMessageComposer"):
        source.index("export function SessionPane")
    ]

    assert 'className="stack-form session-message-form"' in composer_markup
    assert 'className="session-message-target-row"' in composer_markup
    assert 'htmlFor="session-message-audience"' in composer_markup
    assert 'id="session-message-audience"' in composer_markup
    assert '{recipientScope === "player" ? (' in composer_markup
    assert 'htmlFor="session-message-player"' in composer_markup
    assert 'id="session-message-player"' in composer_markup
    assert 'disabled={!recipientPlayerChoices.length}' in composer_markup
    assert 'disabled={recipientScope !== "player" || !recipientPlayerChoices.length}' not in composer_markup
    assert 'htmlFor="session-message-body"' in composer_markup
    assert 'id="session-message-body"' in composer_markup
    assert ".session-message-target-row {" in styles
    assert "grid-template-columns: repeat(auto-fit, minmax(min(14rem, 100%), 1fr));" in styles
    assert ".session-message-form textarea {" in styles


def test_mutation_heavy_gen2_routes_use_shared_toast_notice() -> None:
    toast_route_paths = [
        "frontend/src/pages/AccountSettingsPage.tsx",
        "frontend/src/pages/AdminRoutes.tsx",
        "frontend/src/pages/CampaignControlPage.tsx",
        "frontend/src/pages/CharacterAdvancedEditorPage.tsx",
        "frontend/src/pages/CharacterCreatePage.tsx",
        "frontend/src/pages/CharacterCultivationPage.tsx",
        "frontend/src/pages/CharacterLevelUpPage.tsx",
        "frontend/src/pages/CharacterPane.tsx",
        "frontend/src/pages/CharacterProgressionRepairPage.tsx",
        "frontend/src/pages/CharacterRetrainingPage.tsx",
        "frontend/src/pages/CharacterXianxiaManualImportPage.tsx",
        "frontend/src/pages/CombatPage.tsx",
        "frontend/src/pages/DmContentPage.tsx",
        "frontend/src/pages/DmContentSystemsLane.tsx",
        "frontend/src/pages/SessionDmPane.tsx",
        "frontend/src/pages/SessionRoutes.tsx",
    ]

    for path in toast_route_paths:
        source = Path(path).read_text(encoding="utf-8")
        assert "useToastNotice" in source, path
        assert "<ToastNotice message=" in source, path
        assert "window.setTimeout(" not in source, path
        assert "TOAST_DISMISS_MS" not in source, path


def test_character_pane_draft_state_lives_in_shared_hook() -> None:
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    draft_source = Path("frontend/src/characterPaneDrafts.ts").read_text(encoding="utf-8")

    assert "export function useCharacterPaneDraftState" in draft_source
    assert "const draftSnapshot = buildCharacterPaneDraftSnapshot(character);" in draft_source
    assert "setXianxiaDaoRequestDraft(emptyCharacterXianxiaDaoUseRequestDraft());" in draft_source
    assert "portraitFileInputRef.current.value = \"\";" in draft_source
    assert "useCharacterPaneDraftState({" in route_source
    assert "buildCharacterPaneDraftSnapshot(detailQuery.data.character)" not in route_source
    assert "setEquipmentDrafts(draftSnapshot.equipmentDrafts)" not in route_source


def test_character_pane_xianxia_reference_model_lives_in_shared_helper() -> None:
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    model_source = Path("frontend/src/characterPaneXianxiaModel.ts").read_text(encoding="utf-8")

    assert "export function buildCharacterPaneXianxiaModel" in model_source
    assert "presentedXianxia.quick_reference?.skill_use_guardrails" in model_source
    assert "presentedXianxia.quick_reference?.honor_interactions" in model_source
    assert "presentedXianxia.quick_reference?.stance_break" in model_source
    assert "activeStateStatus: joinDisplay([" in model_source
    assert "const xianxiaModel = buildCharacterPaneXianxiaModel(presentedXianxia);" in route_source
    assert "const skillUseGuardrails = asRecord(presentedXianxia.quick_reference?.skill_use_guardrails);" not in route_source
    assert "const xianxiaHonorInteractions = asRecord(presentedXianxia.quick_reference?.honor_interactions);" not in route_source
    assert "const xianxiaStanceBreak = asRecord(presentedXianxia.quick_reference?.stance_break);" not in route_source


def test_character_pane_common_dnd_model_lives_in_shared_helper() -> None:
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    model_source = Path("frontend/src/characterPaneModel.ts").read_text(encoding="utf-8")

    assert "export function buildCharacterPaneModel" in model_source
    assert "rawOverviewStatRows.length > 0" in model_source
    assert "collectPresentedSpells(character)" in model_source
    assert "groupSpellsByLevel(presentedSpells" in model_source
    assert "function buildPresentedInventoryLookup" in model_source
    assert "const presentedInventory = character?.presented_inventory ?? [];" in model_source
    assert "useMemo(() => buildCharacterPaneModel(detailRecord, { isXianxia })" in route_source
    assert "const overviewStatRowPayload = detailRecord?.overview_stat_rows;" not in route_source
    assert "const presentedSpells = collectPresentedSpells(detailRecord);" not in route_source
    assert "const presentedInventoryByKey = useMemo(() => {" not in route_source


def test_character_pane_mutations_live_in_shared_hook() -> None:
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    mutation_source = Path("frontend/src/characterPaneMutations.ts").read_text(encoding="utf-8")

    assert "export function useCharacterPaneMutations" in mutation_source
    assert "const handleMutationSuccess" in mutation_source
    assert "const handleMutationError" in mutation_source
    assert "apiClient.patchCharacterVitals" in mutation_source
    assert "apiClient.patchCharacterXianxiaActiveState" in mutation_source
    assert "apiClient.postCharacterXianxiaDaoUseRecord" in mutation_source
    assert "queryClient.setQueryData<CharacterDetailResponse>" in mutation_source
    assert "emptyCharacterXianxiaDaoUseRequestDraft()" in mutation_source

    assert 'import { useCharacterPaneMutations } from "../characterPaneMutations";' in route_source
    assert "useCharacterPaneMutations({" in route_source
    assert "const handleMutationSuccess" not in route_source
    assert "const handleMutationError" not in route_source
    assert "useMutation({" not in route_source
    assert "apiErrorMessage(error)" not in route_source
    assert "queryClient.setQueryData" not in route_source


def test_character_pane_submit_handlers_live_in_shared_hook() -> None:
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    handler_source = Path("frontend/src/characterPaneSubmitHandlers.ts").read_text(encoding="utf-8")

    assert "export function useCharacterPaneSubmitHandlers" in handler_source
    assert "parseCharacterNumberInput(value, label)" in handler_source
    assert "readBinaryAsBase64(file" in handler_source
    assert "xianxiaInventoryPayloadFromDraft(newXianxiaInventoryDraft)" in handler_source
    assert "mutations.patchVitals.mutate" in handler_source
    assert "mutations.patchSpellSlot.mutate" in handler_source
    assert "mutations.patchEquipmentState.mutate" in handler_source
    assert "mutations.postXianxiaDaoUseRecord.mutate" in handler_source
    assert 'player_notes_markdown: notesDraft.notes' in handler_source

    assert 'import { useCharacterPaneSubmitHandlers } from "../characterPaneSubmitHandlers";' in route_source
    assert "useCharacterPaneSubmitHandlers({" in route_source
    assert "mutations: characterPaneMutations" in route_source
    assert "const submitVitals = " not in route_source
    assert "const submitXianxiaDaoUseRequest = " not in route_source
    assert "const submitCurrency = " not in route_source
    assert "parseCharacterNumberInput(value, label)" not in route_source
    assert "xianxiaInventoryPayloadFromDraft" not in route_source
    assert "readBinaryAsBase64(file" not in route_source


def test_character_dnd_overview_section_uses_flask_style_glance_rows() -> None:
    model_source = Path("frontend/src/characterPaneModel.ts").read_text(encoding="utf-8")
    section_markup = Path("frontend/src/components/CharacterDndOverviewSection.tsx").read_text(encoding="utf-8")

    assert '<h2>At a glance</h2>' in section_markup
    assert 'className={`glance-grid glance-grid--row glance-grid--quick-row-${rowIndex + 1}`}' in section_markup
    assert 'className="glance-card"' in section_markup
    assert 'className="meta"' in section_markup
    assert "readString(stat.value, \"--\")" in section_markup
    assert '<h2>Overview</h2>' not in section_markup
    assert 'className="stat-grid"' not in section_markup
    assert "rawOverviewStatRows.length > 0" in model_source
    assert "hasOverviewStatRows ? (" in section_markup
    assert 'className="glance-grid">' in section_markup


def test_character_dnd_inventory_currency_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/components/CharacterDndInventorySection.tsx").read_text(encoding="utf-8")
    section_markup = source

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
    assert re.search(r'<button type="submit" className="visually-hidden" disabled=\{isCurrencySaving \|\| !canEdit\}>\s*Update \{key\.toUpperCase\(\)\}\s*</button>', currency_controls_markup) is not None

    assert 'className="chat-label"' not in currency_controls_markup
    assert 'form onSubmit={submitCurrency} className="currency-grid"' not in currency_controls_markup
    assert 'Save currency' not in currency_controls_markup


def test_character_dnd_inventory_section_uses_flask_style_row_form_chrome() -> None:
    source = Path("frontend/src/components/CharacterDndInventorySection.tsx").read_text(encoding="utf-8")
    section_markup = source

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
            r'<button type="submit" className="visually-hidden" disabled=\{isInventorySaving \|\| !canEdit\}>\s*Update \{itemName\} quantity\s*</button>',
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
    assert "Type this character's URL name to confirm: <code>{characterSlug}</code>" in source

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
    model_source = Path("frontend/src/characterPaneModel.ts").read_text(encoding="utf-8")
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

    assert "groupSpellsByLevel" in model_source
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


def test_character_pane_delegates_dnd_section_composition() -> None:
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    dnd_sections_source = Path("frontend/src/components/CharacterDndSections.tsx").read_text(encoding="utf-8")

    assert 'import { CharacterDndSections } from "../components/CharacterDndSections";' in route_source
    assert "<CharacterDndSections" in route_source
    assert "activeCharacterSection={activeCharacterSection}" in route_source
    assert "CharacterDndOverviewSection" not in route_source
    assert "CharacterDndResourcesSection" not in route_source
    assert "CharacterDndSpellsSection" not in route_source
    assert "CharacterDndEquipmentSection" not in route_source
    assert "CharacterDndInventorySection" not in route_source
    assert "CharacterDndAbilitySkillsSection" not in route_source

    for section_name in [
        "CharacterDndOverviewSection",
        "CharacterDndResourcesSection",
        "CharacterDndSpellsSection",
        "CharacterDndEquipmentSection",
        "CharacterDndInventorySection",
        "CharacterDndAbilitySkillsSection",
    ]:
        assert section_name in dnd_sections_source

    assert 'activeCharacterSection === "overview"' in dnd_sections_source
    assert 'activeCharacterSection === "resources"' in dnd_sections_source
    assert 'activeCharacterSection === "spells"' in dnd_sections_source
    assert 'activeCharacterSection === "equipment"' in dnd_sections_source
    assert 'activeCharacterSection === "inventory"' in dnd_sections_source
    assert 'activeCharacterSection === "abilities"' in dnd_sections_source


def test_character_pane_delegates_xianxia_section_composition() -> None:
    route_source = Path("frontend/src/pages/CharacterPane.tsx").read_text(encoding="utf-8")
    xianxia_sections_source = Path("frontend/src/components/CharacterXianxiaSections.tsx").read_text(encoding="utf-8")

    assert 'import { CharacterXianxiaSections } from "../components/CharacterXianxiaSections";' in route_source
    assert "<CharacterXianxiaSections" in route_source
    assert "activeCharacterSection={activeCharacterSection}" in route_source
    assert "CharacterXianxiaQuickReferenceSection" not in route_source
    assert "CharacterXianxiaMartialArtsSection" not in route_source
    assert "CharacterXianxiaTechniquesSection" not in route_source
    assert "CharacterXianxiaResourcesSection" not in route_source
    assert "CharacterXianxiaSkillsSection" not in route_source
    assert "CharacterXianxiaEquipmentSection" not in route_source
    assert "CharacterXianxiaInventorySection" not in route_source
    assert "CharacterPersonalSection" not in route_source

    for section_name in [
        "CharacterXianxiaQuickReferenceSection",
        "CharacterXianxiaMartialArtsSection",
        "CharacterXianxiaTechniquesSection",
        "CharacterXianxiaResourcesSection",
        "CharacterXianxiaSkillsSection",
        "CharacterXianxiaEquipmentSection",
        "CharacterXianxiaInventorySection",
        "CharacterPersonalSection",
    ]:
        assert section_name in xianxia_sections_source

    assert 'activeCharacterSection === "quick-reference"' in xianxia_sections_source
    assert 'activeCharacterSection === "martial-arts"' in xianxia_sections_source
    assert 'activeCharacterSection === "techniques"' in xianxia_sections_source
    assert 'activeCharacterSection === "resources"' in xianxia_sections_source
    assert 'activeCharacterSection === "skills"' in xianxia_sections_source
    assert 'activeCharacterSection === "equipment"' in xianxia_sections_source
    assert 'activeCharacterSection === "inventory"' in xianxia_sections_source
    assert 'activeCharacterSection === "personal"' in xianxia_sections_source


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
    source = Path("frontend/src/pages/SessionDmPane.tsx").read_text(encoding="utf-8")
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
    route_source = Path("frontend/src/pages/DmContentPage.tsx").read_text(encoding="utf-8")
    lane_source = Path("frontend/src/components/DmStagedArticlesLane.tsx").read_text(encoding="utf-8")
    queue_markup = Path("frontend/src/components/DmStagedArticleQueue.tsx").read_text(encoding="utf-8")

    assert 'import { DmStagedArticlesLane } from "../components/DmStagedArticlesLane";' in route_source
    assert "<DmStagedArticlesLane" in route_source
    assert 'import { DmStagedArticleQueue } from "../components/DmStagedArticleQueue";' not in route_source
    assert "<DmStagedArticleQueue" not in route_source
    assert 'import { DmStagedArticleQueue } from "./DmStagedArticleQueue";' in lane_source
    assert 'import { DmArticleCreator } from "./DmArticleCreator";' in lane_source
    assert "<DmStagedArticleQueue" in lane_source
    assert "<DmArticleCreator" in lane_source
    assert 'id="dm-content-staged-articles-queue"' in queue_markup

    assert 'className="session-article-stack"' in queue_markup
    assert 'className="feature-detail session-article-detail"' in queue_markup
    assert "data-session-article-id={article.id}" in queue_markup
    assert 'className="session-article-edit-detail"' in queue_markup
    assert 'className="stack-form session-article-edit-form"' in queue_markup
    assert 'renderArticleBody(article, "article-body--compact")' in queue_markup
    assert "SessionArticleReferenceActions article={article} includePromotionLinks />" in queue_markup
    assert 'import { SessionFileDropzone } from "./SessionFileDropzone";' in queue_markup

    form_match = re.search(
        r'<form\s+className="stack-form session-article-edit-form"[\s\S]*?>',
        queue_markup,
    )
    assert form_match is not None
    form_start = form_match.start()
    form_end = queue_markup.index("</form>", form_start) + len("</form>")
    form_markup = queue_markup[form_start:form_end]

    assert "<SessionFileDropzone" in form_markup
    assert 'id={`dm-content-stage-image-${article.id}`}' in form_markup
    assert 'selectedFileName={draft.image ? draft.image.filename : undefined}' in form_markup
    assert 'disabled={!canManageSession}' in form_markup
    assert 'label className="field">' in form_markup
    assert re.search(r'<label className="field">\s*<span>Title</span>', form_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Body</span>', form_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Image alt text</span>', form_markup) is not None
    assert re.search(r'<label className="field">\s*<span>Image caption</span>', form_markup) is not None
    assert 'className="chat-label"' not in queue_markup
    assert "dm-content-image-edit-row" not in queue_markup
    assert "Selected image:" not in queue_markup

    assert (
        re.search(r'label=\{article\.image \? "Replace image" : "Image"\}', queue_markup)
        is not None
    )
