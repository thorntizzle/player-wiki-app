from __future__ import annotations

import json
from datetime import date
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from player_wiki import auth as auth_module
from player_wiki.loading_presenter import (
    select_campaign_loading_image_url,
    select_campaign_loading_image_urls,
)
from player_wiki.models import Campaign, Page


def extract_stylesheet_href(html: str) -> str:
    match = re.search(r'href=\"([^\"]*/static/styles\.css[^\"]*)\"', html)
    assert match is not None
    return match.group(1)


def test_base_template_uses_versioned_stylesheet_url(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200

    href = extract_stylesheet_href(response.get_data(as_text=True))
    parsed = urlsplit(href)
    assert parsed.path == "/static/styles.css"

    query = parse_qs(parsed.query or "")
    assert "v" in query
    assert len(query["v"]) == 1
    assert query["v"][0].strip()


def test_base_template_and_stylesheet_define_shared_semantic_primitives(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert '<a class="skip-link" href="#main-content">Skip to main content</a>' in html
    assert (
        '<main id="main-content" class="main-content" tabindex="-1" '
        'aria-label="Main content">'
    ) in html

    stylesheet_response = client.get(extract_stylesheet_href(html))
    assert stylesheet_response.status_code == 200
    stylesheet = stylesheet_response.get_data(as_text=True)
    for selector in (
        ".skip-link",
        ".state-panel",
        ".state-panel--empty",
        ".state-panel--error",
        ".action-group",
        ".visually-hidden",
        ":where(a[href], button, input, select, textarea, summary):focus-visible",
        ".main-content:focus",
    ):
        assert selector in stylesheet
    assert stylesheet.count(".visually-hidden") == 1


def test_shared_feedback_partial_preserves_live_replacement_hook_contract():
    project_root = Path(__file__).resolve().parents[1]
    flash_partial = (project_root / "player_wiki/templates/_flash_stack.html").read_text()
    feedback_partial = (project_root / "player_wiki/templates/_feedback.html").read_text()
    base_template = (project_root / "player_wiki/templates/base.html").read_text()
    stylesheet = (project_root / "player_wiki/static/styles.css").read_text()

    assert 'data-flash-stack-root' in base_template
    assert base_template.index("</header>") < base_template.index(
        "data-flash-stack-root"
    ) < base_template.index('<main id="main-content"')
    assert '{% include "_flash_stack.html" %}' in base_template
    assert 'data-feedback-placement="{{ placement }}"' in feedback_partial
    assert 'data-feedback-tone="{{ tone }}"' in feedback_partial
    assert 'role="status"' in feedback_partial
    assert 'role="alert"' in feedback_partial
    assert 'aria-atomic="true"' in feedback_partial
    assert 'placement="transient"' in flash_partial
    assert (
        '.page-shell > [data-flash-stack-root] > '
        '[data-feedback][data-feedback-placement="transient"] {\n'
        '  pointer-events: none;\n'
        '}'
    ) in stylesheet.replace("\r\n", "\n")

    replacement_sources = {
        project_root / "player_wiki/static/session-live.js": (
            'flashRoot.innerHTML = payload.flash_html;',
        ),
        project_root / "player_wiki/static/combat-live.js": (
            'flashRoot.innerHTML = payload.flash_html;',
        ),
        project_root / "player_wiki/static/character-read-shell.js": (
            'flashStackHtml: flashStack ? flashStack.innerHTML : ""',
            'currentFlashStack.innerHTML = flashStackHtml;',
        ),
        project_root / "player_wiki/templates/_combat_status_live_scripts.html": (
            'flashRoot.innerHTML = payload.flash_html;',
        ),
    }
    for source_path, contracts in replacement_sources.items():
        source = source_path.read_text()
        assert '[data-flash-stack-root]' in source, source_path.name
        for contract in contracts:
            assert contract in source, (source_path.name, contract)


def test_session_dm_shell_owns_one_tools_pane_and_future_retained_stale_hooks():
    project_root = Path(__file__).resolve().parents[1]
    panel_template = (
        project_root / "player_wiki/templates/_session_dm_panel.html"
    ).read_text(encoding="utf-8")
    shell_template = (
        project_root / "player_wiki/templates/_session_dm_shell.html"
    ).read_text(encoding="utf-8")
    nav_template = (
        project_root / "player_wiki/templates/_session_dm_nav.html"
    ).read_text(encoding="utf-8")
    tools_template = (
        project_root / "player_wiki/templates/_session_dm_tools.html"
    ).read_text(encoding="utf-8")
    remainder_template = (
        project_root / "player_wiki/templates/_session_dm_legacy_remainder.html"
    ).read_text(encoding="utf-8")
    shell_script = (
        project_root / "player_wiki/static/session-shell.js"
    ).read_text(encoding="utf-8")
    live_script = (
        project_root / "player_wiki/static/session-live.js"
    ).read_text(encoding="utf-8")
    help_presenter = (
        project_root / "player_wiki/help_presenter.py"
    ).read_text(encoding="utf-8")
    dm_content_template = (
        project_root / "player_wiki/templates/dm_content.html"
    ).read_text(encoding="utf-8")
    staged_handoff_template = (
        project_root / "player_wiki/templates/_dm_content_staged_articles_card.html"
    ).read_text(encoding="utf-8")
    stylesheet = (project_root / "player_wiki/static/styles.css").read_text(
        encoding="utf-8"
    )

    assert panel_template.count("data-session-live-root") == 1
    assert panel_template.count('{% include "_session_dm_shell.html" %}') == 1
    assert shell_template.count("data-session-dm-shell-root") == 1
    assert shell_template.count('data-session-dm-pane="tools"') == 1
    assert shell_template.count("data-session-dm-legacy-remainder") == 1
    assert "data-session-dm-pane" not in remainder_template
    assert tools_template.count("data-session-controls-root") == 1
    assert tools_template.count('_session_passive_scores_bar.html') == 1
    assert "_session_status_controls_card.html" in tools_template
    for dm_view in ("tools", "staged", "revealed", "article-store", "logs"):
        assert f'("{dm_view}",' in nav_template
    assert nav_template.count("url_for('campaign_session_dm_view'") == 1
    assert 'dm_view=task[0]' in nav_template
    assert ".field input.session-file-input[data-session-file-input] {" in stylesheet

    for hook in (
        "data-session-dm-shell-root",
        "data-session-dm-pane",
        "sessionDmPaneLoaded",
        "sessionDmPaneStale",
        "sessionDmPaneUrl",
        "pane.innerHTML = await response.text();",
        "history.pushState({ sessionDmView: normalizedTarget }",
    ):
        assert hook in shell_script
    assert 'playerWiki:session-manager-state-changed' in shell_script
    assert 'playerWiki:session-manager-state-changed' in live_script
    assert 'dmShellRoot.closest("[data-session-live-root]")' in shell_script
    assert (
        'managerStateEventRoot.addEventListener('
        '"playerWiki:session-manager-state-changed"'
    ) in shell_script
    assert (
        'campaign_session_dm_view",\n'
        '                                campaign_slug=campaign.slug,\n'
        '                                dm_view="tools"'
    ) in help_presenter
    assert (
        "campaign_session_dm_view', campaign_slug=campaign.slug, "
        "dm_view='staged'"
    ) in dm_content_template
    assert (
        "campaign_session_dm_view', campaign_slug=campaign.slug, "
        "dm_view='staged', _anchor='session-staged-articles'"
    ) in staged_handoff_template


def test_global_search_dialog_adopts_shared_external_presentation_controller(client):
    project_root = Path(__file__).resolve().parents[1]
    search_template = (
        project_root / "player_wiki/templates/_campaign_global_search.html"
    ).read_text(encoding="utf-8")
    scripts_template = (
        project_root / "player_wiki/templates/_campaign_global_search_scripts.html"
    ).read_text(encoding="utf-8")
    preview_template = (
        project_root / "player_wiki/templates/_campaign_global_search_preview.html"
    ).read_text(encoding="utf-8")
    controller_source = (
        project_root / "player_wiki/static/presentation-controller.js"
    ).read_text(encoding="utf-8")

    assert "data-presentation-dialog" in search_template
    assert 'aria-labelledby="campaign-global-search-dialog-title"' in search_template
    assert 'id="campaign-global-search-dialog-title"' in search_template
    assert "data-presentation-dialog-close" in search_template
    assert "data-presentation-dialog-initial-focus" in search_template
    assert scripts_template.startswith(
        '<script src="{{ static_asset_url(\'presentation-controller.js\') }}"></script>'
    )
    assert scripts_template.index("presentation-controller.js") < scripts_template.index(
        '<script nonce="{{ csp_nonce() }}">'
    )
    assert "presentationController.init(root);" in scripts_template
    assert "presentationController.openDialog(dialog, trigger);" in scripts_template
    assert "showModal" not in scripts_template
    assert "dialog.close" not in scripts_template
    assert "__campaignGlobalSearchReturnFocus" not in scripts_template
    for preserved_domain_contract in (
        "searchAbortController",
        "previewAbortController",
        "campaignGlobalSearchResultId",
        "X-Requested-With",
        "payload.preview_html",
    ):
        assert preserved_domain_contract in scripts_template
    assert '<a class="button-link" href="{{ result_url }}">Open dedicated page</a>' in (
        preview_template
    )

    for controller_contract in (
        "window.__playerWikiPresentationController = controller;",
        "controller.init(document);",
        "const initializedDialogs = new WeakSet();",
        "const returnFocusTargets = new WeakMap();",
        "scope instanceof Element && scope.matches(DIALOG_SELECTOR)",
        'typeof dialog.showModal === "function"',
        'dialog.setAttribute("open", "")',
        'dialog.dispatchEvent(new Event("close"))',
        "target instanceof HTMLElement && target.isConnected",
    ):
        assert controller_contract in controller_source

    production_adopters = []
    for directory in (
        project_root / "player_wiki/templates",
        project_root / "player_wiki/static",
    ):
        for path in directory.glob("*"):
            if path.is_file() and path.name != "presentation-controller.js":
                if "data-presentation-dialog" in path.read_text(encoding="utf-8"):
                    production_adopters.append(path.name)
    assert production_adopters == [
        "character_read.html",
        "_campaign_global_search.html",
        "_character_spellcasting_section.html",
        "_combat_player_workspace_sections.html",
        "_combat_workspace_scripts.html",
        "_destructive_confirmation.html",
        "_session_character_dnd_workspace.html",
        "character-read-shell.js",
    ]

    response = client.get("/campaigns/linden-pass/help")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    external_match = re.search(
        r'<script src="([^\"]*/static/presentation-controller\.js\?v=[^\"]+)"></script>',
        html,
    )
    assert external_match is not None
    external_url = external_match.group(1)
    assert html.index(external_match.group(0)) < html.index(
        "const root = document.querySelector(\"[data-campaign-global-search-root]\")"
    )
    query = parse_qs(urlsplit(external_url).query)
    assert len(query.get("v", [])) == 1
    assert query["v"][0].strip()
    asset_response = client.get(external_url)
    assert asset_response.status_code == 200
    assert "__playerWikiPresentationController" in asset_response.get_data(as_text=True)


def test_character_read_dialogs_adopt_shared_scoped_presentation_lifecycle():
    project_root = Path(__file__).resolve().parents[1]
    item_template = (
        project_root / "player_wiki/templates/character_read.html"
    ).read_text(encoding="utf-8")
    spell_template = (
        project_root / "player_wiki/templates/_character_spellcasting_section.html"
    ).read_text(encoding="utf-8")
    character_script = (
        project_root / "player_wiki/static/character-read-shell.js"
    ).read_text(encoding="utf-8")
    base_template = (
        project_root / "player_wiki/templates/base.html"
    ).read_text(encoding="utf-8")
    shared_scripts = (
        project_root / "player_wiki/templates/_campaign_global_search_scripts.html"
    ).read_text(encoding="utf-8")
    character_scripts = (
        project_root / "player_wiki/templates/_character_read_shell_scripts.html"
    ).read_text(encoding="utf-8")

    dialog_label_contracts = (
        (item_template, "dialog_id"),
        (spell_template, "prep_spell_dialog_id"),
        (spell_template, "spell_dialog_id"),
    )
    for template, dialog_id in dialog_label_contracts:
        assert f'aria-labelledby="{{{{ {dialog_id} }}}}-title"' in template
        assert f'id="{{{{ {dialog_id} }}}}-title"' in template
        assert f'data-presentation-dialog-trigger="{{{{ {dialog_id} }}}}"' in template

    assert item_template.count("data-presentation-dialog\n") == 1
    assert spell_template.count("data-presentation-dialog\n") == 2
    assert item_template.count("data-presentation-dialog-initial-focus") == 1
    assert spell_template.count("data-presentation-dialog-initial-focus") == 2
    assert item_template.count("data-character-presentation-dialog-trigger-template") == 1
    assert spell_template.count("data-character-presentation-dialog-trigger-template") == 2
    assert item_template.count("data-character-spell-modal") >= 3
    assert spell_template.count("data-character-spell-modal") >= 6
    assert "<noscript>" in item_template
    assert "character_spell_fallback_details(prep_spell)" in spell_template
    assert "character_spell_fallback_details(spell)" in spell_template

    assert "presentationController.init(scope);" in character_script
    assert "triggerTemplate.content.cloneNode(true)" in character_script
    assert 'triggerGate.dataset.characterPresentationDialogTriggerGate = ""' in character_script
    assert 'scope.dataset.characterPresentationDialogState = "unavailable"' in character_script
    assert 'scope.dataset.characterPresentationDialogState = "ready"' in character_script
    assert "allSpellModalTriggersEnabled" in character_script
    assert "triggerGate.replaceWith(trigger)" in character_script
    assert "try {\n          presentationController.init(scope);\n        } catch (_error)" in character_script
    assert (
        'scope.querySelectorAll("[data-character-spell-modal-trigger]'
        '[data-presentation-dialog-trigger]")'
    ) in character_script
    assert 'classList.add("spell-modal-js")' in character_script
    assert "showModal" not in character_script
    assert "dialog.close" not in character_script
    assert "__characterSpellReturnFocus" not in character_script
    assert 'addEventListener("close"' not in character_script

    assert shared_scripts.startswith(
        '<script src="{{ static_asset_url(\'presentation-controller.js\') }}"></script>'
    )
    assert "character-read-shell.js" in character_scripts
    assert base_template.index(
        '{% include "_campaign_global_search_scripts.html" %}'
    ) < base_template.index("{% block scripts %}")


def test_session_character_dialogs_adopt_shared_scoped_presentation_lifecycle():
    project_root = Path(__file__).resolve().parents[1]
    workspace_template = (
        project_root / "player_wiki/templates/_session_character_dnd_workspace.html"
    ).read_text(encoding="utf-8")
    spell_template = (
        project_root / "player_wiki/templates/_character_spellcasting_section.html"
    ).read_text(encoding="utf-8")
    combat_script = (
        project_root / "player_wiki/templates/_combat_workspace_scripts.html"
    ).read_text(encoding="utf-8")
    session_template = (
        project_root / "player_wiki/templates/session.html"
    ).read_text(encoding="utf-8")
    shared_scripts = (
        project_root / "player_wiki/templates/_campaign_global_search_scripts.html"
    ).read_text(encoding="utf-8")

    for contract in (
        "data-session-character-presentation-dialog-scope",
        "data-character-presentation-dialog-trigger-template",
        'data-presentation-dialog-trigger="{{ dialog_id }}"',
        'aria-labelledby="{{ dialog_id }}-title"',
        'id="{{ dialog_id }}-title"',
        "data-presentation-dialog-close",
        "data-presentation-dialog-initial-focus",
        'class="item-description-detail spell-card__fallback"',
        "data-character-spell-fallback",
        "<summary>Item details</summary>",
    ):
        assert contract in workspace_template
    assert "<noscript>" not in workspace_template
    assert "data-character-presentation-dialog-trigger-template" in spell_template
    assert "data-presentation-dialog-trigger" in spell_template

    for contract in (
        "initSessionCharacterPresentationDialogs(root);",
        "sessionCharacterPresentationScopes(root)",
        "isSessionCharacterPresentationNode(trigger)",
        "isSessionCharacterPresentationNode(dialog)",
        'triggerGate.dataset.sessionCharacterPresentationDialogTriggerGate = ""',
        'scope.dataset.sessionCharacterPresentationDialogState = "unavailable"',
        'scope.dataset.sessionCharacterPresentationDialogState = "ready"',
        "presentationController.init(scope);",
        "allDialogTriggersEnabled",
        "triggerGate.replaceWith(trigger)",
    ):
        assert contract in combat_script
    assert combat_script.count("initSessionCharacterPresentationDialogs(root);") == 2
    assert "showModal" in combat_script
    assert "closeSpellDialog" in combat_script

    assert shared_scripts.startswith(
        '<script src="{{ static_asset_url(\'presentation-controller.js\') }}"></script>'
    )
    assert session_template.index('{% include "_combat_workspace_scripts.html" %}') < (
        session_template.index('{% include "_session_shell_scripts.html" %}')
    )


def test_combat_selected_pc_dialogs_adopt_shared_scoped_presentation_lifecycle():
    project_root = Path(__file__).resolve().parents[1]
    workspace_template = (
        project_root / "player_wiki/templates/_combat_player_workspace_sections.html"
    ).read_text(encoding="utf-8")
    combat_script = (
        project_root / "player_wiki/templates/_combat_workspace_scripts.html"
    ).read_text(encoding="utf-8")

    for contract in (
        "data-combat-presentation-dialog-scope",
        "data-combat-presentation-dialog-trigger-template",
        'data-presentation-dialog-trigger="{{ dialog_id }}"',
        'aria-labelledby="{{ dialog_id }}-title"',
        'id="{{ dialog_id }}-title"',
        "data-presentation-dialog-close",
        "data-presentation-dialog-initial-focus",
        'class="item-description-detail spell-card__fallback"',
        "data-character-spell-fallback",
        "<summary>Item details</summary>",
        "<summary>Spell details</summary>",
    ):
        assert contract in workspace_template
    assert "<noscript>" not in workspace_template

    for contract in (
        "initCombatPresentationDialogs(root);",
        "combatPresentationScopes(root)",
        "isCombatPresentationNode(trigger)",
        "isCombatPresentationNode(dialog)",
        'triggerGate.dataset.combatPresentationDialogTriggerGate = ""',
        'scope.dataset.combatPresentationDialogState = "unavailable"',
        'scope.dataset.combatPresentationDialogState = "ready"',
        "presentationController.init(scope);",
        "allDialogTriggersEnabled",
        "triggerGate.replaceWith(trigger)",
    ):
        assert contract in combat_script
    assert combat_script.count("initCombatPresentationDialogs(root);") == 2
    assert combat_script.count("initSessionCharacterPresentationDialogs(root);") == 2
    assert "initSessionCharacterPresentationDialogs(root);\n      initCombatPresentationDialogs(root);" in combat_script
    assert (
        "!isSessionCharacterPresentationNode(trigger) && !isCombatPresentationNode(trigger)"
        in combat_script
    )
    assert (
        "!isSessionCharacterPresentationNode(dialog) && !isCombatPresentationNode(dialog)"
        in combat_script
    )


def test_destructive_confirmation_uses_external_controller_and_combat_owned_recovery():
    project_root = Path(__file__).resolve().parents[1]
    primitive = (
        project_root / "player_wiki/templates/_destructive_confirmation.html"
    ).read_text(encoding="utf-8")
    controller = (
        project_root / "player_wiki/static/presentation-controller.js"
    ).read_text(encoding="utf-8")
    combat_live = (
        project_root / "player_wiki/static/combat-live.js"
    ).read_text(encoding="utf-8")
    controls = (
        project_root / "player_wiki/templates/_combat_dm_controls.html"
    ).read_text(encoding="utf-8")
    authority = (
        project_root / "player_wiki/templates/_combat_dm_selected_authority.html"
    ).read_text(encoding="utf-8")

    for contract in (
        "data-presentation-dialog-trigger",
        "data-presentation-dialog",
        "data-presentation-dialog-close",
        "data-presentation-dialog-initial-focus",
        "data-destructive-confirmation-form",
        "data-destructive-confirmation-recovery",
        "<noscript>",
        '<form method="post" action="{{ action_url }}" class="stack-form">',
    ):
        assert contract in primitive
    assert "onclick=" not in primitive
    assert "onsubmit=" not in primitive
    assert 'name="destructive_acknowledgement"' in primitive
    assert "required" in primitive

    for lifecycle_contract in (
        'const TRIGGER_SELECTOR = "[data-presentation-dialog-trigger]";',
        "trigger.removeAttribute(\"hidden\")",
        "event.target.closest(TRIGGER_SELECTOR)",
        "openDialog(dialog, trigger)",
        "target.focus({ preventScroll: true })",
    ):
        assert lifecycle_contract in controller

    for combat_contract in (
        "initializePresentation(statusAuthorityRoot);",
        "initializePresentation(controlsRoot);",
        "setDestructiveFormBusy(form, true);",
        "showDestructiveRecovery(form);",
        "recovery.focus({ preventScroll: true });",
        'form.matches("[data-combat-async], [data-destructive-confirmation-form]")',
    ):
        assert combat_contract in combat_live

    assert '"Clear tracker"' in controls
    assert '"Clear combat tracker?"' in controls
    assert 'risk="higher"' in controls
    assert "Round resets to 1 and the current turn is cleared." in controls
    assert "Character sheets and source records remain unchanged." in controls
    assert 'acknowledgement_label="I understand this clears every combatant' in controls
    assert '"Remove combatant"' in authority
    assert 'risk="lower"' in authority
    assert '"Remove " ~ selected_combatant.name ~ "?"' in authority
    assert "linked character, statblock, Systems entry, and source records remain unchanged" in authority
    assert "Refresh Combat before repeating this action." in controls
    assert "Refresh Combat before repeating this action." in authority


def test_session_clear_revealed_confirmation_adopts_shared_primitive():
    project_root = Path(__file__).resolve().parents[1]
    template = (
        project_root / "player_wiki/templates/_session_revealed_articles_card.html"
    ).read_text(encoding="utf-8")
    session_live = (
        project_root / "player_wiki/static/session-live.js"
    ).read_text(encoding="utf-8")

    for template_contract in (
        '{% from "_destructive_confirmation.html" import destructive_confirmation %}',
        '"session-clear-revealed-confirmation"',
        '"Clear all"',
        '"Clear all revealed articles?"',
        "revealed_article_count",
        "related reveal chat and log entries",
        "Staged articles remain unchanged.",
        "The result could not be confirmed. Refresh Session before repeating this action.",
        'risk="higher"',
        'acknowledgement_label="I understand this permanently deletes all revealed session articles',
        "{{ csrf_input() }}",
    ):
        assert template_contract in template
    assert "data-session-confirm" not in template
    assert "window.confirm" not in template

    for controller_contract in (
        'form.matches("[data-session-async], [data-destructive-confirmation-form]")',
        "initializePresentation(revealedRoot);",
        "initializePresentation(revealedRoot || liveRoot);",
        "setDestructiveFormBusy(form, true);",
        "hideDestructiveRecovery(form);",
        "showDestructiveRecovery(form);",
        "recovery.focus({ preventScroll: true });",
        "const destructiveValidationFailed = form.matches(\"[data-destructive-confirmation-form]\")",
        "suppressAnchor: composerValidationFailed || destructiveValidationFailed,",
    ):
        assert controller_contract in session_live


def test_campaign_shell_density_contract_owns_exact_820_boundary(client):
    response = client.get("/campaigns/linden-pass/help")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<nav class="campaign-nav" aria-label="Campaign navigation">' in html
    assert re.search(
        r'href="/campaigns/linden-pass/help"\s+aria-current="page">\s*Help\s*</a>',
        html,
    )

    stylesheet_response = client.get(extract_stylesheet_href(html))
    assert stylesheet_response.status_code == 200
    stylesheet = stylesheet_response.get_data(as_text=True).replace("\r\n", "\n")
    for contract in (
        "grid-template-columns: minmax(0, 1fr) minmax(16rem, 26rem);",
        ".campaign-global-search__field {\n  flex: 1 1 auto;\n  min-width: 0;",
        ".campaign-global-search__status:empty,\n.campaign-global-search__results:empty",
        "@media (max-width: 820px)",
        "grid-template-columns: repeat(auto-fit, minmax(min(6.4rem, 100%), 1fr));",
        ".site-header__secondary .campaign-global-search__form {\n    flex-direction: row;",
        ".site-header__secondary .campaign-global-search__form button {\n    width: auto;",
    ):
        assert contract in stylesheet


def test_base_template_includes_inline_loading_bootstrap_and_cover(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="app-loading-inline-styles"' in html
    assert ".app-loading-cover" in html
    assert 'id="app-loading-inline-script"' in html
    assert "requestAnimationFrame" in html
    assert "setTimeout" in html
    assert "failOpenDelayMs = 12000" in html
    assert "addEventListener" in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html

    html_opening_tag = re.search(r"<html[^>]*>", html)
    assert html_opening_tag is not None
    assert "app-loading" not in html_opening_tag.group(0)
    assert "cpw:app-loading-nav-start" in html
    assert "app-loading-closing" in html
    assert "prefers-reduced-motion" in html
    assert "html.app-loading::before" in html
    assert "html.app-loading::after" in html
    assert "function markLoadingDelayed()" in html
    assert "Still loading campaign player wiki..." in html
    assert ".app-loading-cover__media" in html
    assert "app-loading-cover__message" in html
    assert "root.classList.contains(loadingClass) && cover.classList.contains(\"app-loading-cover--media-ready\")" in html
    assert "function seedLoadingMediaFromCoverData()" in html
    assert "cpw:app-loading-active-media-url" in html
    assert "app-loading-media-ready" in html
    assert "function applyActiveLoadingMediaFromStorage()" in html
    assert "function loadingMediaUpdateIsSafe()" in html
    assert "if (!loadingMediaUpdateIsSafe())" in html
    assert "--app-loading-visible-media" in html
    assert "data-app-loading-prepared-media-url" in html
    assert "function setPreparedLoadingMedia(" in html
    assert "seedLoadingMediaFromCoverData();" in html
    assert "function softNavigate(" not in html
    assert "data-app-soft-navigation-script" not in html
    assert "--app-loading-bg" in html
    assert "Loading campaign player wiki..." in html


def test_versioned_stylesheet_response_uses_production_immutable_cache_headers(app, client):
    app.config["APP_ENV"] = "production"

    response = client.get("/campaigns/linden-pass")
    href = extract_stylesheet_href(response.get_data(as_text=True))
    css_response = client.get(href)
    assert css_response.status_code == 200

    cache_control = css_response.headers.get("Cache-Control", "")
    assert "public" in cache_control
    assert "max-age=31536000" in cache_control
    assert "immutable" in cache_control
    assert "no-cache" not in cache_control

    vary_header = (css_response.headers.get("Vary") or "").lower()
    assert "cookie" not in vary_header


def test_stylesheet_static_requests_bypass_request_identity(monkeypatch, client):
    call_count = {"count": 0}

    original_get_auth_store = auth_module.get_auth_store

    def tracking_get_auth_store():
        call_count["count"] += 1
        return original_get_auth_store()

    monkeypatch.setattr(auth_module, "get_auth_store", tracking_get_auth_store)

    page_response = client.get("/campaigns/linden-pass")
    assert page_response.status_code == 200
    assert call_count["count"] > 0
    page_request_count = call_count["count"]

    stylesheet_response = client.get("/static/styles.css?v=audittest")
    assert stylesheet_response.status_code == 200

    assert call_count["count"] == page_request_count
    vary_header = (stylesheet_response.headers.get("Vary") or "").lower()
    assert "cookie" not in vary_header


def test_base_template_uses_loading_image_for_campaign_when_available(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'app-loading-cover--with-image' in html
    assert 'app-loading-cover--media-ready' in html
    assert 'data-app-loading-media-urls=' in html
    assert 'data-app-loading-media-url="/campaigns/linden-pass/assets/' in html
    assert "style='--app-loading-media: url(\"/campaigns/linden-pass/assets/" in html
    assert "force-cache" in html
    assert "background-size: contain" in html


def test_base_template_no_loading_image_for_global_routes(client):
    response = client.get("/sign-in")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'app-loading-cover--with-image' not in html
    cover_match = re.search(r'<div class="app-loading-cover[^"]*"', html)
    assert cover_match is not None
    assert cover_match.group(0) == '<div class="app-loading-cover"'


def test_base_template_has_theme_scoped_palette_for_loading_cover(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    bg, ink, accent, _ = _loading_theme_palette("parchment")
    assert 'html[data-theme="parchment"]' in html
    assert f"--app-loading-bg: {bg};" in html
    assert f"--app-loading-ink: {ink};" in html
    assert f"--app-loading-accent: {accent};" in html


def _loading_theme_palette(theme_key: str) -> tuple[str, str, str, str]:
    themes = {
        "parchment": ("#efe2c5", "#2f241a", "#8c4f31", "0.16"),
        "moonlit": ("#172331", "#eaf1ff", "#d4b16f", "0.18"),
        "verdant": ("#dfe9db", "#233126", "#4a7e60", "0.16"),
        "ember": ("#f0d3bc", "#351d18", "#a34c31", "0.14"),
    }
    return themes[theme_key]


def _extract_loading_media_urls(html: str) -> list[str]:
    match = re.search(r"data-app-loading-media-urls='([^']*)'", html)
    if not match:
        return []
    raw_urls = match.group(1)
    try:
        parsed_urls = json.loads(raw_urls)
    except Exception:
        return []
    if not isinstance(parsed_urls, list):
        return []
    return [url for url in parsed_urls if isinstance(url, str)]


def _extract_loading_media_url(html: str) -> str | None:
    urls = _extract_loading_media_urls(html)
    if not urls:
        return None
    return urls[0]


def _browser_loading_media_urls(page) -> list[str]:
    return page.evaluate(
        """
        () => {
          const cover = document.querySelector('.app-loading-cover');
          if (!cover) {
            return [];
          }
          try {
            const parsed = JSON.parse(cover.getAttribute('data-app-loading-media-urls') || '[]');
            return Array.isArray(parsed) ? parsed.filter((url) => typeof url === 'string') : [];
          } catch {
            return [];
          }
        }
        """
    )


def _sign_in_in_browser(page, base_url: str, email: str, password: str):
    page.goto(f"{base_url}/sign-in", wait_until="load")
    page.wait_for_selector("input[name='email']")
    page.fill("input[name='email']", email)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_load_state("load")


def _set_browser_theme(page, base_url: str, theme_key: str):
    page.goto(f"{base_url}/account", wait_until="load")
    status = page.evaluate(
        """async (themeKey) => {
            const body = new URLSearchParams();
            body.set("theme_key", themeKey);
            const response = await fetch("/account/theme", {
              method: "POST",
              body,
              credentials: "same-origin",
            });
            return response.status;
        }""",
        theme_key,
    )
    assert status == 200


def _build_loading_presenter_campaign() -> Campaign:
    return Campaign(
        title="Loading Image Unit Test",
        slug="loading-images",
        summary="Unit fixture for loading image selection.",
        system="DND-5E",
        current_session=2,
        source_wiki_root="",
        player_content_dir="",
        assets_dir="",
        pages={},
    )


def test_select_campaign_loading_image_urls_filters_missing_and_ineligible_paths():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "visible-valid": Page(
            title="Captain",
            route_slug="captain",
            source_path="",
            body_markdown="",
            section="NPCs",
            page_type="npc",
            image_path="npcs/captain.png",
        ),
        "visible-unpublished": Page(
            title="Hidden",
            route_slug="hidden",
            source_path="",
            body_markdown="",
            section="NPCs",
            page_type="npc",
            published=False,
            image_path="images/hidden.png",
        ),
        "visible-traversal": Page(
            title="Traversal",
            route_slug="traversal",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="../outside/secret.png",
        ),
        "visible-external": Page(
            title="External",
            route_slug="external",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="https://example.com/artwork.png",
        ),
        "visible-missing": Page(
            title="Missing",
            route_slug="missing",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="missing/no-file.png",
        ),
        "global-page": Page(
            title="Global",
            route_slug="global-page",
            source_path="global/events/overview",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/global.png",
        ),
    }

    image_urls = select_campaign_loading_image_urls(
        campaign,
        can_access_wiki=True,
        image_exists=lambda _, image_path: image_path == "npcs/captain.png",
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        selection_seed="loading-unit-test",
        selection_date=date(2026, 5, 30),
        max_loading_images=4,
    )
    assert image_urls == ["/campaigns/loading-images/assets/npcs/captain.png"]


def test_select_campaign_loading_image_urls_limit_and_stable_for_same_day():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "first": Page(
            title="First",
            route_slug="first",
            source_path="content/first.md",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/first.png",
        ),
        "second": Page(
            title="Second",
            route_slug="second",
            source_path="content/second.md",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/second.png",
        ),
        "third": Page(
            title="Third",
            route_slug="third",
            source_path="content/third.md",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/third.png",
        ),
        "fourth": Page(
            title="Fourth",
            route_slug="fourth",
            source_path="content/fourth.md",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/fourth.png",
        ),
    }

    select_kwargs = {
        "can_access_wiki": True,
        "image_exists": lambda *_args: True,
        "build_image_url": lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        "selection_seed": "loading-unit-test",
        "selection_date": date(2026, 5, 30),
    }
    first_result = select_campaign_loading_image_urls(
        campaign,
        **select_kwargs,
        max_loading_images=3,
    )
    second_result = select_campaign_loading_image_urls(
        campaign,
        **select_kwargs,
        max_loading_images=3,
    )
    assert len(first_result) == 3
    assert first_result == second_result


def test_select_campaign_loading_image_urls_falls_back_when_no_candidates():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "missing-one": Page(
            title="Missing",
            route_slug="missing",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="missing/no-file.png",
        )
    }

    image_urls = select_campaign_loading_image_urls(
        campaign,
        can_access_wiki=True,
        image_exists=lambda *_args: False,
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        selection_seed="loading-unit-test",
        selection_date=date(2026, 5, 30),
    )
    assert image_urls == []


def test_select_campaign_loading_image_url_wraps_list_wrapper():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "single": Page(
            title="Single",
            route_slug="single",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/captain.png",
        )
    }

    image_url = select_campaign_loading_image_url(
        campaign,
        can_access_wiki=True,
        image_exists=lambda *_args: True,
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        selection_seed="loading-unit-test",
        selection_date=date(2026, 5, 30),
        max_scanned_pages=4,
    )
    assert image_url == "/campaigns/loading-images/assets/npcs/captain.png"


def test_select_campaign_loading_image_url_stable_for_same_day():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "first": Page(
            title="First",
            route_slug="first",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/captain.png",
        ),
        "second": Page(
            title="Second",
            route_slug="second",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="lore/map.png",
        ),
    }

    image_url = lambda: select_campaign_loading_image_url(
        campaign,
        can_access_wiki=True,
        image_exists=lambda _, image_path: True,
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        selection_date=date(2026, 5, 30),
    )
    assert image_url() == image_url()


def test_select_campaign_loading_image_url_blocks_inaccessible_campaign_content():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "visible": Page(
            title="Locked Page",
            route_slug="locked",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/captain.png",
        ),
    }

    image_url = select_campaign_loading_image_url(
        campaign,
        can_access_wiki=False,
        image_exists=lambda *_args: True,
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
    )
    assert image_url is None


@pytest.fixture
def static_asset_live_server(app):
    from werkzeug.serving import make_server

    app.config["APP_ENV"] = "production"
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "viewport",
    (
        {"width": 1280, "height": 900},
        {"width": 390, "height": 800},
    ),
    ids=("desktop", "mobile"),
)
def test_browser_session_dm_tools_canonical_history_and_no_js_fallback(
    static_asset_live_server,
    viewport,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            context = browser.new_context(viewport=viewport)
            page = context.new_page()
            _sign_in_in_browser(
                page,
                static_asset_live_server,
                "dm@example.com",
                "dm-pass",
            )

            response = page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass/session/dm",
                wait_until="load",
            )
            assert response is not None
            assert response.status == 200
            expect(page).to_have_url(
                f"{static_asset_live_server}/campaigns/linden-pass/session/dm?dm_view=tools"
            )

            dm_outer_pane = page.locator('[data-session-shell-pane="dm"]')
            dm_live_root = dm_outer_pane.locator('[data-session-live-view="dm"]')
            expect(dm_outer_pane.locator("[data-session-dm-shell-root]")).to_have_count(1)
            expect(dm_live_root).to_have_count(1)
            expect(dm_outer_pane.locator('[data-session-dm-pane="tools"]')).to_have_count(1)
            expect(dm_outer_pane.locator("[data-session-dm-switch='1']")).to_have_count(5)
            expect(dm_outer_pane.locator("[data-session-dm-legacy-remainder]")).to_have_count(1)
            expect(dm_live_root).to_have_attribute("data-session-live-paused", "0")

            if viewport["width"] == 390:
                mobile_overflow = page.evaluate(
                    """() => {
                        const documentRoot = document.documentElement;
                        const input = document.querySelector(
                            'input#session-manual-image-file.session-file-input'
                        );
                        const inputRect = input.getBoundingClientRect();
                        return {
                            clientWidth: documentRoot.clientWidth,
                            scrollWidth: documentRoot.scrollWidth,
                            inputRight: inputRect.right,
                        };
                    }"""
                )
                assert mobile_overflow["scrollWidth"] <= mobile_overflow["clientWidth"]
                assert mobile_overflow["inputRight"] <= mobile_overflow["clientWidth"]

            manager_event_topology = dm_live_root.evaluate(
                """liveRoot => {
                    const shellRoot = liveRoot.querySelector('[data-session-dm-shell-root]');
                    const toolsPane = liveRoot.querySelector('[data-session-dm-pane="tools"]');
                    toolsPane.hidden = true;
                    delete toolsPane.dataset.sessionDmPaneStale;
                    liveRoot.dispatchEvent(new CustomEvent(
                        'playerWiki:session-manager-state-changed',
                        {bubbles: true},
                    ));
                    return {
                        outerContainsShell: liveRoot.contains(shellRoot),
                        shellContainsOuter: shellRoot.contains(liveRoot),
                    };
                }"""
            )
            assert manager_event_topology == {
                "outerContainsShell": True,
                "shellContainsOuter": False,
            }
            tools_pane = dm_outer_pane.locator('[data-session-dm-pane="tools"]')
            expect(tools_pane).to_have_attribute("data-session-dm-pane-stale", "1")
            tools_pane.evaluate(
                """pane => {
                    pane.hidden = false;
                    delete pane.dataset.sessionDmPaneStale;
                }"""
            )

            page.evaluate(
                "document.querySelector('[data-session-dm-pane=tools]').dataset.retainedProof = '1'"
            )
            page.locator('[data-session-switch-target="session"]').click()
            expect(page).to_have_url(
                f"{static_asset_live_server}/campaigns/linden-pass/session"
            )
            expect(dm_outer_pane).to_be_hidden()
            expect(dm_live_root).to_have_attribute("data-session-live-paused", "1")

            page.go_back(wait_until="commit")
            expect(page).to_have_url(
                f"{static_asset_live_server}/campaigns/linden-pass/session/dm?dm_view=tools"
            )
            expect(dm_outer_pane).to_be_visible()
            expect(dm_live_root).to_have_attribute("data-session-live-paused", "0")
            expect(dm_outer_pane.locator('[data-retained-proof="1"]')).to_have_count(1)
            context.close()

            no_js_context = browser.new_context(
                viewport=viewport,
                java_script_enabled=False,
            )
            no_js_page = no_js_context.new_page()
            _sign_in_in_browser(
                no_js_page,
                static_asset_live_server,
                "dm@example.com",
                "dm-pass",
            )
            no_js_response = no_js_page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass/session/dm?dm_view=tools",
                wait_until="load",
            )
            assert no_js_response is not None
            assert no_js_response.status == 200
            expect(no_js_page.locator('[data-session-dm-pane="tools"]')).to_have_count(1)
            expect(no_js_page.locator('form[action$="/session/start"]')).to_have_count(1)
            expect(
                no_js_page.locator(
                    'a[href="/campaigns/linden-pass/session/dm?dm_view=staged"]'
                )
            ).to_have_count(1)
            no_js_context.close()
        finally:
            browser.close()


def test_browser_skip_link_moves_focus_to_main_across_representative_matrix(
    static_asset_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    scenarios = (
        {
            "viewport": {"width": 1280, "height": 900},
            "path": "/campaigns",
            "theme": "parchment",
            "signed_in": False,
            "expected_status": 200,
        },
        {
            "viewport": {"width": 390, "height": 800},
            "path": "/campaigns/linden-pass/pages/does-not-exist",
            "theme": "moonlit",
            "signed_in": True,
            "expected_status": 404,
        },
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            for scenario in scenarios:
                context = browser.new_context(viewport=scenario["viewport"])
                page = context.new_page()
                try:
                    if scenario["signed_in"]:
                        _sign_in_in_browser(
                            page,
                            static_asset_live_server,
                            "dm@example.com",
                            "dm-pass",
                        )
                        _set_browser_theme(page, static_asset_live_server, scenario["theme"])

                    response = page.goto(
                        f"{static_asset_live_server}{scenario['path']}",
                        wait_until="load",
                    )
                    assert response is not None
                    assert response.status == scenario["expected_status"]
                    expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
                    expect(page.locator("html")).to_have_attribute("data-theme", scenario["theme"])

                    if scenario["signed_in"]:
                        expect(page.locator(".user-badge")).to_contain_text("Dungeon Master")
                        expect(page.locator('a[href="/account"]')).to_have_count(1)
                        expect(page.locator('a[href="/admin"]')).to_have_count(0)
                    else:
                        expect(page.locator('a[href="/sign-in"]')).to_have_count(1)
                        expect(page.locator('a[href="/account"]')).to_have_count(0)

                    skip_link = page.locator(".skip-link")
                    before_focus_box = skip_link.bounding_box()
                    assert before_focus_box is not None
                    assert before_focus_box["y"] < 0

                    page.keyboard.press("Tab")
                    expect(skip_link).to_be_focused()
                    focused_box = skip_link.bounding_box()
                    assert focused_box is not None
                    assert focused_box["x"] >= 0
                    assert focused_box["y"] >= 0

                    page.keyboard.press("Enter")
                    main_content = page.locator("#main-content")
                    expect(main_content).to_have_attribute("aria-label", "Main content")
                    expect(main_content).to_be_focused()
                    assert page.evaluate("window.location.hash") == "#main-content"
                    assert page.evaluate(
                        """() => {
                          const main = document.querySelector('#main-content');
                          const style = getComputedStyle(main);
                          return style.outlineStyle !== 'none'
                            && parseFloat(style.outlineWidth) > 0;
                        }"""
                    )
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
                    )
                finally:
                    context.close()
        finally:
            browser.close()


def test_browser_campaign_shell_keeps_first_viewport_priorities_across_role_matrix(
    static_asset_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    role_contracts = {
        "signed-out": {
            "credentials": None,
            "labels": ("Campaign Home", "Help"),
            "badge": None,
            "admin": False,
        },
        "player": {
            "credentials": ("party@example.com", "party-pass"),
            "labels": ("Campaign Home", "Session", "Combat", "Systems", "Help"),
            "badge": "Party Player",
            "admin": False,
        },
        "dm": {
            "credentials": ("dm@example.com", "dm-pass"),
            "labels": (
                "Campaign Home",
                "Session",
                "Combat",
                "Characters",
                "Systems",
                "DM Content",
                "Control",
                "Help",
            ),
            "badge": "Dungeon Master",
            "admin": False,
        },
        "admin": {
            "credentials": ("admin@example.com", "admin-pass"),
            "labels": (
                "Campaign Home",
                "Session",
                "Combat",
                "Characters",
                "Systems",
                "DM Content",
                "Control",
                "Help",
            ),
            "badge": "Admin User",
            "admin": True,
        },
    }
    scenarios = []
    for viewport in ({"width": 1280, "height": 900}, {"width": 390, "height": 800}):
        for index, role in enumerate(("signed-out", "player", "dm", "admin")):
            scenarios.append(
                {
                    "role": role,
                    "viewport": viewport,
                    "theme": (
                        "moonlit"
                        if index % 2 == (0 if viewport["width"] == 390 else 1)
                        else "parchment"
                    ),
                }
            )
    scenarios.extend(
        (
            {
                "role": "dm",
                "viewport": {"width": 821, "height": 900},
                "theme": "moonlit",
                "boundary": "above",
            },
            {
                "role": "dm",
                "viewport": {"width": 820, "height": 900},
                "theme": "parchment",
                "boundary": "at",
            },
        )
    )

    def assert_in_first_viewport(locator, viewport, label):
        box = locator.bounding_box()
        assert box is not None, label
        assert box["x"] >= 0, label
        assert box["y"] >= 0, label
        assert box["x"] + box["width"] <= viewport["width"] + 1, label
        assert box["y"] + box["height"] <= viewport["height"] + 1, label

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            for scenario in scenarios:
                role = scenario["role"]
                contract = role_contracts[role]
                viewport = scenario["viewport"]
                context = browser.new_context(viewport=viewport)
                page = context.new_page()
                try:
                    if contract["credentials"] is not None:
                        email, password = contract["credentials"]
                        _sign_in_in_browser(page, static_asset_live_server, email, password)
                        _set_browser_theme(page, static_asset_live_server, scenario["theme"])

                    response = page.goto(
                        f"{static_asset_live_server}/campaigns/linden-pass/help",
                        wait_until="load",
                    )
                    assert response is not None
                    assert response.status == 200
                    expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
                    expected_theme = scenario["theme"] if contract["credentials"] else "parchment"
                    expect(page.locator("html")).to_have_attribute("data-theme", expected_theme)

                    nav = page.get_by_role("navigation", name="Campaign navigation")
                    expect(nav).to_be_visible()
                    nav_links = nav.get_by_role("link")
                    assert nav_links.all_inner_texts() == list(contract["labels"]), role
                    for index, label in enumerate(contract["labels"]):
                        link = nav_links.nth(index)
                        expect(link).to_be_visible()
                        href = link.get_attribute("href")
                        assert href is not None and href.startswith("/campaigns/linden-pass"), (
                            role,
                            label,
                        )
                        link_box = link.bounding_box()
                        assert link_box is not None, (role, label)
                        assert link_box["x"] >= 0, (role, label)
                        assert link_box["x"] + link_box["width"] <= viewport["width"] + 1, (
                            role,
                            label,
                        )
                    current_link = nav.locator('[aria-current="page"]')
                    expect(current_link).to_have_count(1)
                    expect(current_link).to_have_text("Help")
                    expect(current_link).to_have_class(re.compile(r"\bis-active\b"))

                    header_actions = page.locator(".site-header__actions")
                    if contract["badge"] is None:
                        expect(header_actions.locator('a[href="/sign-in"]')).to_have_count(1)
                        expect(header_actions.locator('a[href="/account"]')).to_have_count(0)
                        expect(header_actions.locator('form[action="/sign-out"]')).to_have_count(0)
                    else:
                        expect(header_actions.locator(".user-badge")).to_contain_text(
                            contract["badge"]
                        )
                        expect(header_actions.locator('a[href="/sign-in"]')).to_have_count(0)
                        expect(header_actions.locator('a[href="/account"]')).to_have_count(1)
                        sign_out_form = header_actions.locator('form[action="/sign-out"]')
                        expect(sign_out_form).to_have_count(1)
                        expect(sign_out_form.get_by_role("button", name="Sign out")).to_be_visible()
                    expect(header_actions.locator('a[href="/admin"]')).to_have_count(
                        1 if contract["admin"] else 0
                    )
                    expect(header_actions.get_by_text("View As", exact=True)).to_have_count(0)

                    heading = page.locator("main h1")
                    expect(heading).to_have_count(1)
                    expect(heading).to_have_text("Help")
                    first_action = page.locator("main .hero-actions a").first
                    expect(first_action).to_be_visible()
                    for locator, label in (
                        (page.locator(".site-header__campaign"), "campaign identity"),
                        (nav, "campaign navigation"),
                        (page.locator("[data-campaign-global-search-query]"), "global search"),
                        (heading, "route heading"),
                        (first_action, "primary action"),
                    ):
                        assert_in_first_viewport(locator, viewport, (role, viewport, label))

                    search_form_direction = page.locator(
                        "[data-campaign-global-search-form]"
                    ).evaluate("element => getComputedStyle(element).flexDirection")
                    assert search_form_direction == "row"
                    empty_search_height = page.evaluate(
                        """() => ({
                          status: document.querySelector('[data-campaign-global-search-status]')
                            .getBoundingClientRect().height,
                          results: document.querySelector('[data-campaign-global-search-results]')
                            .getBoundingClientRect().height,
                        })"""
                    )
                    assert empty_search_height == {"status": 0, "results": 0}
                    secondary_columns = page.locator(".site-header__secondary").evaluate(
                        "element => getComputedStyle(element).gridTemplateColumns"
                    )
                    nav_display = nav.evaluate("element => getComputedStyle(element).display")
                    if viewport["width"] <= 820:
                        assert len(secondary_columns.split()) == 1
                        assert nav_display == "grid"
                    else:
                        assert len(secondary_columns.split()) == 2
                        assert nav_display == "flex"
                    if scenario.get("boundary") == "above":
                        assert viewport["width"] == 821 and nav_display == "flex"
                    if scenario.get("boundary") == "at":
                        assert viewport["width"] == 820 and nav_display == "grid"

                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
                    )

                    skip_link = page.locator(".skip-link")
                    page.keyboard.press("Tab")
                    expect(skip_link).to_be_focused()
                    assert_in_first_viewport(skip_link, viewport, (role, viewport, "skip link"))
                    assert skip_link.evaluate(
                        "element => parseFloat(getComputedStyle(element).outlineWidth) > 0"
                    )
                    page.keyboard.press("Enter")
                    main_content = page.locator("#main-content")
                    expect(main_content).to_be_focused()
                    expect(main_content).to_have_attribute("aria-label", "Main content")

                    if role == "player" and viewport["width"] == 390:
                        query = page.locator("[data-campaign-global-search-query]")
                        query.fill("capt")
                        page.locator("[data-campaign-global-search-form] button").click()
                        result = page.locator(
                            "[data-campaign-global-search-result-id]",
                            has_text="Captain Lyra Vale",
                        )
                        expect(result).to_be_visible(timeout=5000)
                        result.click()
                        dialog = page.locator("[data-campaign-global-search-dialog]")
                        expect(dialog).to_be_visible(timeout=5000)
                        close_button = page.locator("[data-campaign-global-search-close]")
                        expect(close_button).to_be_focused()
                        dedicated_link = dialog.get_by_role("link", name="Open dedicated page")
                        expect(dedicated_link).to_have_attribute(
                            "href",
                            "/campaigns/linden-pass/pages/npcs/captain-lyra-vale",
                        )
                        page.keyboard.press("Escape")
                        expect(dialog).to_be_hidden()
                        expect(result).to_be_focused()
                        expect(page.locator(".app-loading-cover")).to_be_hidden()
                finally:
                    context.close()
        finally:
            browser.close()


def test_browser_global_search_shared_controller_preserves_keyboard_focus_across_viewports(
    static_asset_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    scenarios = (
        ({"width": 1280, "height": 900}, "parchment", ("button", "escape")),
        ({"width": 390, "height": 800}, "moonlit", ("backdrop",)),
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            for viewport, theme, close_methods in scenarios:
                context = browser.new_context(viewport=viewport)
                page = context.new_page()
                try:
                    _sign_in_in_browser(
                        page,
                        static_asset_live_server,
                        "party@example.com",
                        "party-pass",
                    )
                    _set_browser_theme(page, static_asset_live_server, theme)
                    response = page.goto(
                        f"{static_asset_live_server}/campaigns/linden-pass/help",
                        wait_until="load",
                    )
                    assert response is not None and response.status == 200
                    expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
                    expect(page.locator("html")).to_have_attribute("data-theme", theme)
                    expect(page.locator("main h1")).to_have_count(1)
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
                    )

                    query = page.locator("[data-campaign-global-search-query]")
                    query.focus()
                    query.fill("capt")
                    page.keyboard.press("Enter")
                    result = page.locator(
                        "[data-campaign-global-search-result-id]",
                        has_text="Captain Lyra Vale",
                    )
                    expect(result).to_be_visible(timeout=5000)
                    result.focus()
                    expect(result).to_be_focused()
                    scroll_before_open = page.evaluate("window.scrollY")
                    page.keyboard.press("Enter")

                    dialog = page.locator("[data-campaign-global-search-dialog]")
                    close_button = page.locator("[data-campaign-global-search-close]")
                    expect(dialog).to_be_visible(timeout=5000)
                    assert dialog.evaluate("element => element.matches(':modal')")
                    expect(close_button).to_be_focused()
                    expect(query).to_have_value("capt")
                    expect(dialog.get_by_role("link", name="Open dedicated page")).to_have_attribute(
                        "href",
                        "/campaigns/linden-pass/pages/npcs/captain-lyra-vale",
                    )

                    for index, close_method in enumerate(close_methods):
                        if index:
                            result.focus()
                            page.keyboard.press("Enter")
                            expect(dialog).to_be_visible(timeout=5000)
                            assert dialog.evaluate("element => element.matches(':modal')")
                            expect(close_button).to_be_focused()

                        if close_method == "button":
                            page.keyboard.press("Enter")
                        elif close_method == "escape":
                            page.keyboard.press("Escape")
                        else:
                            page.mouse.click(1, 1)

                        expect(dialog).to_be_hidden()
                        expect(result).to_be_focused()
                        expect(query).to_have_value("capt")
                        assert page.evaluate("window.scrollY") == scroll_before_open
                        assert result.evaluate(
                            "element => parseFloat(getComputedStyle(element).outlineWidth) > 0"
                        )
                        expect(page.locator(".app-loading-cover")).to_be_hidden()
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
                        )
                finally:
                    context.close()
        finally:
            browser.close()


def test_browser_shared_presentation_controller_reinitializes_inserted_dialog_once(
    static_asset_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            response = page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass/help",
                wait_until="load",
            )
            assert response is not None and response.status == 200
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)

            init_counts = page.evaluate(
                """() => {
                  const fragment = document.createElement('section');
                  fragment.id = 'presentation-controller-fragment';
                  fragment.innerHTML = `
                    <button type="button" id="inserted-dialog-invoker">Open inserted dialog</button>
                    <dialog
                      aria-labelledby="inserted-dialog-title"
                      data-presentation-dialog
                      id="inserted-dialog"
                    >
                      <h2 id="inserted-dialog-title">Inserted dialog</h2>
                      <button
                        type="button"
                        data-presentation-dialog-close
                        data-presentation-dialog-initial-focus
                      >Close inserted dialog</button>
                    </dialog>
                    <dialog data-presentation-dialog id="unlabelled-dialog">
                      <button type="button" data-presentation-dialog-close>Close</button>
                    </dialog>
                  `;
                  document.querySelector('#main-content').append(fragment);
                  const controller = window.__playerWikiPresentationController;
                  const dialog = fragment.querySelector('#inserted-dialog');
                  const invoker = fragment.querySelector('#inserted-dialog-invoker');
                  dialog.__closeCount = 0;
                  dialog.dataset.closeCount = '0';
                  dialog.addEventListener('close', () => {
                    dialog.__closeCount += 1;
                    dialog.dataset.closeCount = String(dialog.__closeCount);
                  });
                  invoker.addEventListener('click', () => controller.openDialog(dialog, invoker));
                  return [
                    controller.init(fragment),
                    controller.init(fragment),
                    controller.init(dialog),
                    controller.openDialog(fragment.querySelector('#unlabelled-dialog'), invoker),
                  ];
                }"""
            )
            assert init_counts == [1, 0, 0, False]

            invoker = page.locator("#inserted-dialog-invoker")
            dialog = page.locator("#inserted-dialog")
            close_button = dialog.get_by_role("button", name="Close inserted dialog")
            invoker.focus()
            page.keyboard.press("Enter")
            expect(dialog).to_be_visible()
            assert dialog.evaluate("element => element.matches(':modal')")
            expect(close_button).to_be_focused()
            page.keyboard.press("Enter")
            expect(dialog).to_be_hidden()
            expect(invoker).to_be_focused()
            expect(dialog).to_have_attribute("data-close-count", "1")
            assert dialog.evaluate("element => element.__closeCount") == 1

            invoker.focus()
            page.keyboard.press("Enter")
            expect(dialog).to_be_visible()
            invoker.evaluate("element => element.remove()")
            page.keyboard.press("Escape")
            expect(dialog).to_be_hidden()
            expect(dialog).to_have_attribute("data-close-count", "2")
            assert dialog.evaluate("element => element.__closeCount") == 2
            assert page_errors == []
        finally:
            browser.close()


def test_browser_account_feedback_contract_for_valid_invalid_and_no_js_submissions(
    static_asset_live_server,
    monkeypatch,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    def assert_no_horizontal_overflow(page):
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            desktop_context = browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            desktop_page = desktop_context.new_page()
            try:
                _sign_in_in_browser(
                    desktop_page,
                    static_asset_live_server,
                    "party@example.com",
                    "party-pass",
                )
                response = desktop_page.goto(
                    f"{static_asset_live_server}/account", wait_until="load"
                )
                assert response is not None and response.status == 200
                expect(desktop_page.locator(".app-loading-cover")).to_be_hidden(
                    timeout=5000
                )
                expect(desktop_page.locator("html")).to_have_attribute(
                    "data-theme", "parchment"
                )

                current = desktop_page.locator(
                    'input[name="session_chat_order"]:checked'
                )
                current_value = current.get_attribute("value")
                target_value = (
                    "newest_first" if current_value == "oldest_first" else "oldest_first"
                )
                target_label = (
                    "Newest first" if target_value == "newest_first" else "Oldest first"
                )
                target = desktop_page.locator(
                    f'input[name="session_chat_order"][value="{target_value}"]'
                )
                current.focus()
                expect(current).to_be_focused()
                desktop_page.keyboard.press("ArrowDown")
                expect(target).to_be_checked()
                submit = desktop_page.get_by_role("button", name="Save chat order")
                submit.focus()
                with desktop_page.expect_navigation(wait_until="load"):
                    desktop_page.keyboard.press("Enter")

                expect(desktop_page).to_have_url(
                    f"{static_asset_live_server}/account"
                )
                feedback = desktop_page.locator(
                    '[data-flash-stack-root] [data-feedback][data-feedback-tone="success"]'
                )
                expect(feedback).to_have_count(1)
                expect(feedback).to_have_text(
                    f"Live session chat order updated to {target_label}."
                )
                expect(feedback).to_have_attribute("data-feedback-placement", "transient")
                expect(feedback).to_have_attribute("role", "status")
                expect(feedback).to_have_attribute("aria-live", "polite")
                expect(feedback).to_have_attribute("aria-atomic", "true")
                box = feedback.bounding_box()
                assert box is not None
                assert 0 <= box["x"] < 1280 and 0 <= box["y"] < 900
                assert box["x"] + box["width"] <= 1280
                assert box["y"] + box["height"] <= 900
                assert_no_horizontal_overflow(desktop_page)
            finally:
                desktop_context.close()

            mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
            mobile_page = mobile_context.new_page()
            try:
                _sign_in_in_browser(
                    mobile_page,
                    static_asset_live_server,
                    "admin@example.com",
                    "admin-pass",
                )
                _set_browser_theme(mobile_page, static_asset_live_server, "moonlit")
                response = mobile_page.goto(
                    f"{static_asset_live_server}/account", wait_until="load"
                )
                assert response is not None and response.status == 200
                expect(mobile_page.locator(".app-loading-cover")).to_be_hidden(
                    timeout=5000
                )
                expect(mobile_page.locator("html")).to_have_attribute(
                    "data-theme", "moonlit"
                )
                mobile_page.evaluate(
                    """() => {
                      const form = document.querySelector('#account-session-chat-order-form');
                      form.noValidate = true;
                      for (const input of form.querySelectorAll('[name="session_chat_order"]')) {
                        input.checked = false;
                      }
                    }"""
                )
                submit = mobile_page.get_by_role("button", name="Save chat order")
                submit.focus()
                with mobile_page.expect_navigation(wait_until="load") as navigation:
                    mobile_page.keyboard.press("Enter")
                assert navigation.value is not None and navigation.value.status == 400

                error = mobile_page.locator("#session-chat-order-error")
                expect(error).to_have_count(1)
                expect(error).to_have_text("Choose a valid live session chat order.")
                expect(error).to_have_attribute("data-feedback-placement", "persistent")
                expect(error).to_have_attribute("data-feedback-tone", "error")
                expect(error).to_have_attribute("role", "alert")
                expect(error).to_have_attribute("aria-live", "assertive")
                expect(
                    mobile_page.locator('[data-flash-stack-root] [data-feedback-tone="error"]')
                ).to_have_count(0)
                inputs = mobile_page.locator('input[name="session_chat_order"]')
                expect(inputs).to_have_count(2)
                for index in range(2):
                    field = inputs.nth(index)
                    expect(field).to_have_attribute(
                        "aria-describedby", "session-chat-order-error"
                    )
                    expect(field).to_have_attribute("aria-invalid", "true")
                    expect(field).not_to_be_checked()
                expect(inputs.first).to_be_focused()
                assert inputs.first.locator("xpath=..").evaluate(
                    "element => getComputedStyle(element).boxShadow !== 'none'"
                )
                expect(mobile_page.locator("main h1")).to_have_count(1)
                assert_no_horizontal_overflow(mobile_page)

                response = mobile_page.goto(
                    f"{static_asset_live_server}/account", wait_until="load"
                )
                assert response is not None and response.status == 200
                expect(mobile_page.locator(".app-loading-cover")).to_be_hidden(
                    timeout=5000
                )
                current = mobile_page.locator(
                    'input[name="session_chat_order"]:checked'
                )
                current_value = current.get_attribute("value")
                target_value = (
                    "newest_first" if current_value == "oldest_first" else "oldest_first"
                )
                target_label = (
                    "Newest first" if target_value == "newest_first" else "Oldest first"
                )
                long_confirmation_label = (
                    f"{target_label} with an intentionally long confirmation label that "
                    "verifies transient feedback remains contained on a narrow moonlit viewport"
                )
                original_session_chat_order_labels = auth_module.SESSION_CHAT_ORDER_LABELS
                long_session_chat_order_labels = dict(original_session_chat_order_labels)
                long_session_chat_order_labels[target_value] = long_confirmation_label
                monkeypatch.setattr(
                    auth_module,
                    "SESSION_CHAT_ORDER_LABELS",
                    long_session_chat_order_labels,
                )

                current.focus()
                expect(current).to_be_focused()
                mobile_page.keyboard.press("ArrowDown")
                target = mobile_page.locator(
                    f'input[name="session_chat_order"][value="{target_value}"]'
                )
                expect(target).to_be_checked()
                with mobile_page.expect_navigation(wait_until="load"):
                    mobile_page.get_by_role("button", name="Save chat order").click()
                expect(mobile_page.locator(".app-loading-cover")).to_be_hidden(
                    timeout=5000
                )
                expect(mobile_page.locator("html")).to_have_attribute(
                    "data-theme", "moonlit"
                )

                feedback = mobile_page.locator(
                    '[data-flash-stack-root] [data-feedback][data-feedback-tone="success"]'
                )
                expect(feedback).to_have_count(1)
                expect(feedback).to_have_text(
                    f"Live session chat order updated to {long_confirmation_label}."
                )
                assert feedback.evaluate(
                    "element => getComputedStyle(element).pointerEvents === 'none'"
                )
                feedback_box = feedback.bounding_box()
                assert feedback_box is not None
                assert feedback_box["x"] >= 0 and feedback_box["y"] >= 0
                assert feedback_box["x"] + feedback_box["width"] <= 390
                assert feedback_box["y"] + feedback_box["height"] <= 800
                assert_no_horizontal_overflow(mobile_page)

                account_link = mobile_page.locator(
                    '.site-header__actions a[href="/account"]'
                )
                account_link_box = account_link.bounding_box()
                assert account_link_box is not None
                account_link_center = {
                    "x": account_link_box["x"] + account_link_box["width"] / 2,
                    "y": account_link_box["y"] + account_link_box["height"] / 2,
                }
                assert feedback_box["x"] <= account_link_center["x"] <= (
                    feedback_box["x"] + feedback_box["width"]
                )
                assert feedback_box["y"] <= account_link_center["y"] <= (
                    feedback_box["y"] + feedback_box["height"]
                )
                assert mobile_page.evaluate(
                    """point => {
                      const hit = document.elementFromPoint(point.x, point.y);
                      return !!(hit && hit.closest('.site-header__actions a[href="/account"]'));
                    }""",
                    account_link_center,
                )
                with mobile_page.expect_navigation(wait_until="load"):
                    account_link.click()
                expect(mobile_page).to_have_url(f"{static_asset_live_server}/account")
                monkeypatch.setattr(
                    auth_module,
                    "SESSION_CHAT_ORDER_LABELS",
                    original_session_chat_order_labels,
                )
            finally:
                mobile_context.close()

            no_js_context = browser.new_context(
                viewport={"width": 1280, "height": 900}, java_script_enabled=False
            )
            no_js_page = no_js_context.new_page()
            try:
                _sign_in_in_browser(
                    no_js_page,
                    static_asset_live_server,
                    "party@example.com",
                    "party-pass",
                )
                response = no_js_page.goto(
                    f"{static_asset_live_server}/account", wait_until="load"
                )
                assert response is not None and response.status == 200
                current_value = no_js_page.locator(
                    'input[name="session_chat_order"]:checked'
                ).get_attribute("value")
                target_value = (
                    "newest_first" if current_value == "oldest_first" else "oldest_first"
                )
                target_label = (
                    "Newest first" if target_value == "newest_first" else "Oldest first"
                )
                no_js_page.locator("label.theme-option", has_text=target_label).click()
                expect(
                    no_js_page.locator(
                        f'input[name="session_chat_order"][value="{target_value}"]'
                    )
                ).to_be_checked()
                with no_js_page.expect_navigation(wait_until="load"):
                    no_js_page.get_by_role("button", name="Save chat order").click()
                expect(no_js_page).to_have_url(f"{static_asset_live_server}/account")
                feedback = no_js_page.locator(
                    '[data-flash-stack-root] [data-feedback][data-feedback-tone="success"]'
                )
                expect(feedback).to_have_count(1)
                expect(feedback).to_have_text(
                    f"Live session chat order updated to {target_label}."
                )
                assert_no_horizontal_overflow(no_js_page)
            finally:
                no_js_context.close()
        finally:
            browser.close()


def test_browser_shows_loading_cover_while_stylesheet_streams(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            def delay_stylesheet(route):
                time.sleep(4.5)
                route.continue_()

            page.route("**/static/styles.css**", delay_stylesheet)

            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="commit",
            )

            page.wait_for_timeout(3500)
            loading_snapshot_during_delay = page.evaluate(
                """() => {
                    const cover = document.querySelector('.app-loading-cover');
                    const rootBefore = getComputedStyle(document.documentElement, '::before');
                    const rootAfter = getComputedStyle(document.documentElement, '::after');
                    return {
                      hasLoadingClass: document.documentElement.classList.contains('app-loading'),
                      coverOpacity: cover ? getComputedStyle(cover).opacity : null,
                      pageShellOpacity: getComputedStyle(document.querySelector('.page-shell')).opacity,
                      pageShellVisibility: getComputedStyle(document.querySelector('.page-shell')).visibility,
                      rootCoverContent: rootBefore.content,
                      rootCoverPosition: rootBefore.position,
                      rootCoverInsetTop: rootBefore.top,
                      rootMediaContent: rootAfter.content,
                    };
                }"""
            )
            assert loading_snapshot_during_delay["hasLoadingClass"] is True
            assert loading_snapshot_during_delay["coverOpacity"] == "1"
            assert loading_snapshot_during_delay["pageShellOpacity"] == "0"
            assert loading_snapshot_during_delay["pageShellVisibility"] == "hidden"
            assert loading_snapshot_during_delay["rootCoverContent"] != "none"
            assert loading_snapshot_during_delay["rootCoverPosition"] == "fixed"
            assert loading_snapshot_during_delay["rootCoverInsetTop"] == "0px"
            assert loading_snapshot_during_delay["rootMediaContent"] != "none"

            page.wait_for_load_state("load", timeout=12000)

            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)

            resource_urls = page.evaluate(
                "Array.from(performance.getEntriesByType('resource')).map((entry) => entry.name)"
            )
            stylesheet_urls = [
                url for url in resource_urls if "/static/styles.css" in str(url)
            ]
            assert stylesheet_urls
            assert all("?v=" in url for url in stylesheet_urls)

            assert page.evaluate("getComputedStyle(document.body).marginTop") == "0px"
            paint_timing = page.evaluate(
                """() => {
                    const cssEntry = performance
                        .getEntriesByType('resource')
                        .find((entry) => entry.name.includes('/static/styles.css'));
                    const fcpEntry = performance
                        .getEntriesByType('paint')
                        .find((entry) => entry.name === 'first-contentful-paint');
                    return {
                        cssResponseEnd: cssEntry ? cssEntry.responseEnd : 0,
                        firstContentfulPaint: fcpEntry ? fcpEntry.startTime : 0,
                    };
                }"""
            )
            assert paint_timing["cssResponseEnd"] > 0
            if paint_timing["firstContentfulPaint"] > 0:
                assert paint_timing["firstContentfulPaint"] >= paint_timing["cssResponseEnd"] - 1
        finally:
            page.close()
            browser.close()


def test_browser_loading_cover_stays_up_when_stylesheet_exceeds_delay(
    static_asset_live_server,
    client,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200
    html = response.get_data(as_text=True).replace(
        "failOpenDelayMs = 12000",
        "failOpenDelayMs = 100",
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.route(
                "**/campaigns/linden-pass",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=html,
                ),
            )

            def delay_stylesheet(route):
                time.sleep(0.7)
                route.continue_()

            page.route("**/static/styles.css**", delay_stylesheet)
            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="commit",
            )
            page.wait_for_timeout(250)

            delayed_snapshot = page.evaluate(
                """() => {
                    const root = document.documentElement;
                    const cover = document.querySelector('.app-loading-cover');
                    const shell = document.querySelector('.page-shell');
                    const message = document.querySelector('.app-loading-cover__message');
                    return {
                      hasLoadingClass: root.classList.contains('app-loading'),
                      coverVisibility: cover ? getComputedStyle(cover).visibility : null,
                      coverOpacity: cover ? getComputedStyle(cover).opacity : null,
                      shellVisibility: shell ? getComputedStyle(shell).visibility : null,
                      shellOpacity: shell ? getComputedStyle(shell).opacity : null,
                      message: message ? message.textContent : '',
                    };
                }"""
            )
            assert delayed_snapshot["hasLoadingClass"] is True
            assert delayed_snapshot["coverVisibility"] == "visible"
            assert delayed_snapshot["coverOpacity"] == "1"
            assert delayed_snapshot["shellVisibility"] == "hidden"
            assert delayed_snapshot["shellOpacity"] == "0"
            assert delayed_snapshot["message"] == "Still loading campaign player wiki..."

            page.wait_for_load_state("load", timeout=5000)
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)
        finally:
            page.close()
            browser.close()


def _set_viewport_for_theme_checks(page, is_mobile: bool):
    if is_mobile:
        page.set_viewport_size({"width": 390, "height": 844})
    else:
        page.set_viewport_size({"width": 1280, "height": 900})


@pytest.mark.parametrize("theme_key", ["parchment", "moonlit", "verdant", "ember"])
@pytest.mark.parametrize("is_mobile", [False, True])
def test_browser_loading_palette_for_themes_during_delayed_stylesheet(
    static_asset_live_server,
    users,
    theme_key,
    is_mobile,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _set_viewport_for_theme_checks(page, is_mobile)
            _sign_in_in_browser(
                page,
                static_asset_live_server,
                users["party"]["email"],
                users["party"]["password"],
            )
            _set_browser_theme(page, static_asset_live_server, theme_key)

            expected_bg, expected_ink, expected_accent, expected_media_opacity = _loading_theme_palette(theme_key)

            def delay_stylesheet(route):
                time.sleep(1.2)
                route.continue_()

            page.route("**/static/styles.css**", delay_stylesheet)
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="commit")
            page.wait_for_timeout(450)

            palette = page.evaluate(
                """() => {
                    const root = document.documentElement;
                    const cover = document.querySelector('.app-loading-cover');
                    return {
                      background: getComputedStyle(root).getPropertyValue('--app-loading-bg').trim(),
                      ink: getComputedStyle(root).getPropertyValue('--app-loading-ink').trim(),
                      accent: getComputedStyle(root).getPropertyValue('--app-loading-accent').trim(),
                      mediaOpacity: getComputedStyle(root).getPropertyValue('--app-loading-media-opacity').trim(),
                      hasLoadingClass: root.classList.contains('app-loading'),
                      coverOpacity: getComputedStyle(cover).opacity,
                      pageShellOpacity: getComputedStyle(document.querySelector('.page-shell')).opacity,
                    };
                }"""
            )
            assert palette["hasLoadingClass"] is True
            assert palette["coverOpacity"] == "1"
            assert palette["pageShellOpacity"] == "0"
            assert palette["background"] == expected_bg
            assert palette["ink"] == expected_ink
            assert palette["accent"] == expected_accent
            assert palette["mediaOpacity"] == expected_media_opacity

            page.unroute("**/static/styles.css**")
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)
        finally:
            page.close()
            browser.close()


def test_browser_loading_cover_dismisses_when_cover_image_is_blocked(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            baseline_response = page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            assert baseline_response is not None
            assert baseline_response.status == 200
            media_urls = _extract_loading_media_urls(baseline_response.text())
            assert media_urls
            page.wait_for_timeout(150)

            def block_loading_media(route):
                request_path = urlsplit(route.request.url).path
                for media_url in media_urls:
                    if request_path == urlsplit(media_url).path:
                        route.abort()
                        return
                route.continue_()

            page.route("**", block_loading_media)

            start_time = time.perf_counter()
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="commit")
            expect(page.locator("html.app-loading")).to_have_count(1, timeout=2000)
            expect(page.locator("html.app-loading")).to_have_count(0, timeout=5000)
            hide_ms = (time.perf_counter() - start_time) * 1000

            assert hide_ms < 2500
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=2000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=2000)
        finally:
            page.close()
            browser.close()


def test_browser_loading_cover_seeds_media_before_outgoing_navigation(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="load")
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)

            media_urls = page.evaluate(
                """
                () => {
                  const cover = document.querySelector('.app-loading-cover');
                  return cover ? JSON.parse(cover.getAttribute('data-app-loading-media-urls') || '[]') : [];
                }
                """
            )
            assert media_urls

            page.evaluate(
                """
                () => {
                  const cover = document.querySelector('.app-loading-cover');
                  cover.classList.remove('app-loading-cover--media-ready');
                  cover.style.removeProperty('--app-loading-media');
                  cover.style.removeProperty('--app-loading-visible-media');
                  cover.removeAttribute('data-app-loading-media-url');
                  cover.removeAttribute('data-app-loading-prepared-media-url');
                  const link = document.createElement('a');
                  link.id = 'app-loading-seed-link';
                  link.href = '/campaigns/linden-pass/session';
                  link.textContent = 'session';
                  document.body.appendChild(link);
                  document.addEventListener('click', (event) => {
                    if (event.target && event.target.id === 'app-loading-seed-link') {
                      event.preventDefault();
                    }
                  }, { once: true });
                }
                """
            )
            page.evaluate(
                """
                () => {
                  document.querySelector('#app-loading-seed-link').dispatchEvent(
                    new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
                  );
                }
                """
            )
            expect(page.locator(".app-loading-cover")).to_be_visible(timeout=1000)

            seeded = page.evaluate(
                """
                () => {
                  const cover = document.querySelector('.app-loading-cover');
                  const media = document.querySelector('.app-loading-cover__media');
                  return {
                    ready: cover.classList.contains('app-loading-cover--media-ready'),
                    styleValue: cover.style.getPropertyValue('--app-loading-visible-media'),
                    attrValue: cover.getAttribute('data-app-loading-media-url'),
                    backgroundImage: getComputedStyle(media).backgroundImage,
                  };
                }
                """
            )
            assert seeded["ready"] is True
            assert seeded["styleValue"].startswith('url("')
            assert seeded["attrValue"].startswith("/campaigns/linden-pass/assets/")
            assert "/campaigns/linden-pass/assets/" in seeded["backgroundImage"]
        finally:
            page.close()
            browser.close()


def test_browser_loading_cover_persists_prepared_media_before_outgoing_navigation(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="load")
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(
                page.locator(
                    ".app-loading-cover.app-loading-cover--media-ready"
                    "[data-app-loading-media-url][data-app-loading-prepared-media-url]"
                )
            ).to_have_count(1, timeout=5000)

            prepared = page.evaluate(
                """
                () => {
                  const cover = document.querySelector('.app-loading-cover');
                  return {
                    attrValue: cover.getAttribute('data-app-loading-media-url'),
                    preparedAttrValue: cover.getAttribute('data-app-loading-prepared-media-url'),
                    visibleStyleValue: cover.style.getPropertyValue('--app-loading-visible-media'),
                  };
                }
                """
            )

            page.evaluate(
                """
                () => {
                  const link = document.createElement('a');
                  link.id = 'app-loading-prepared-link';
                  link.href = '/campaigns/linden-pass?prepared-media=1';
                  link.textContent = 'campaign';
                  document.body.appendChild(link);
                  document.addEventListener('click', (event) => {
                    if (event.target && event.target.id === 'app-loading-prepared-link') {
                      event.preventDefault();
                    }
                  }, { once: true });
                }
                """
            )
            page.evaluate(
                """
                () => {
                  document.querySelector('#app-loading-prepared-link').dispatchEvent(
                    new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
                  );
                }
                """
            )
            expect(page.locator(".app-loading-cover")).to_be_visible(timeout=1000)

            active_snapshot = page.evaluate(
                """
                () => {
                  const root = document.documentElement;
                  const cover = document.querySelector('.app-loading-cover');
                  const media = document.querySelector('.app-loading-cover__media');
                  return {
                    rootReady: root.classList.contains('app-loading-media-ready'),
                    rootStyle: root.style.getPropertyValue('--app-loading-visible-media'),
                    storedActive: sessionStorage.getItem('cpw:app-loading-active-media-url') || '',
                    coverStyle: cover.style.getPropertyValue('--app-loading-visible-media'),
                    backgroundImage: getComputedStyle(media).backgroundImage,
                  };
                }
                """
            )
            assert active_snapshot["rootReady"] is True
            assert active_snapshot["storedActive"] == prepared["preparedAttrValue"]
            assert prepared["preparedAttrValue"] in active_snapshot["rootStyle"]
            assert prepared["preparedAttrValue"] in active_snapshot["coverStyle"]
            assert prepared["preparedAttrValue"] in active_snapshot["backgroundImage"]
            assert prepared["visibleStyleValue"] == ""
        finally:
            page.close()
            browser.close()


def test_browser_loading_cover_uses_active_media_across_incoming_document(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            first_response = page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="load")
            assert first_response is not None
            media_urls = _extract_loading_media_urls(first_response.text())
            if len(media_urls) < 2:
                pytest.skip("insufficient loading media candidates for active-media handoff test")
            active_media_url = media_urls[-1]
            page.evaluate(
                """(activeUrl) => {
                  sessionStorage.setItem('cpw:app-loading-active-media-url', activeUrl);
                }""",
                active_media_url,
            )

            def delay_stylesheet(route):
                time.sleep(4.5)
                route.continue_()

            page.route("**/static/styles.css**", delay_stylesheet)
            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass?active-media-handoff=1",
                wait_until="commit",
            )
            page.wait_for_timeout(3500)

            snapshot = page.evaluate(
                """
                () => {
                  const root = document.documentElement;
                  const media = document.querySelector('.app-loading-cover__media');
                  const style = document.querySelector('#app-loading-active-media-style');
                  return {
                    href: window.location.href,
                    rootLoading: root.classList.contains('app-loading'),
                    rootReady: root.classList.contains('app-loading-media-ready'),
                    rootStyle: root.style.getPropertyValue('--app-loading-visible-media'),
                    activeStyle: style ? style.textContent : '',
                    backgroundImage: getComputedStyle(media).backgroundImage,
                    storedActive: sessionStorage.getItem('cpw:app-loading-active-media-url') || '',
                  };
                }
                """
            )
            assert snapshot["rootLoading"] is True, snapshot
            assert snapshot["rootReady"] is True, snapshot
            assert active_media_url in snapshot["rootStyle"], snapshot
            assert active_media_url in snapshot["activeStyle"], snapshot
            assert active_media_url in snapshot["backgroundImage"], snapshot
            assert snapshot["storedActive"] == active_media_url, snapshot

            page.unroute("**/static/styles.css**")
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            assert page.evaluate("sessionStorage.getItem('cpw:app-loading-active-media-url')") is None
        finally:
            page.close()
            browser.close()


def test_browser_loading_media_rotation_advances_between_navigation(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.route("**/static/styles.css**", lambda route: route.continue_())
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="load")
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)

            media_urls = _browser_loading_media_urls(page)
            if len(media_urls) < 2:
                pytest.skip("insufficient loading media candidates for rotation test")

            start_index = page.evaluate(
                "Number(sessionStorage.getItem('cpw:app-loading-media-index') || 0)"
            )

            page.evaluate(
                """
                () => {
                  const link = document.createElement('a');
                  link.id = 'app-loading-rotation-link';
                  link.href = '/campaigns/linden-pass/pages/npcs/captain-lyra-vale';
                  link.textContent = 'captain';
                  link.style.position = 'relative';
                  document.body.appendChild(link);
                }
                """
            )
            page.locator("#app-loading-rotation-link").click()

            expect(page.locator(".app-loading-cover")).to_be_visible(timeout=5000)
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=7000)

            end_index = page.evaluate(
                "Number(sessionStorage.getItem('cpw:app-loading-media-index') || 0)"
            )
            assert start_index != end_index
        finally:
            page.close()
            browser.close()


def _measure_loading_hide_ms(page):
    return page.evaluate(
        """() => {
            const startMarker = Number(sessionStorage.getItem("cpw-test-nav-start") || 0);
            return new Promise((resolve) => {
              if (!startMarker) {
                resolve(-1);
                return;
              }
              let deadlineMs = 5000;
              const check = () => {
                if (!document.documentElement.classList.contains("app-loading")) {
                  resolve(Date.now() - startMarker);
                  return;
                }
                if (deadlineMs <= 0) {
                  resolve(-1);
                  return;
                }
                deadlineMs -= 32;
                window.setTimeout(check, 16);
              };
              check();
            });
        }"""
    )


def test_browser_navigation_feedback_short_minimum_duration(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.route("**/static/styles.css**", lambda route: route.continue_())

            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            page.wait_for_timeout(150)

            page.evaluate(
                """
                () => {
                  sessionStorage.setItem("cpw-test-nav-start", String(Date.now()));
                  const link = document.createElement("a");
                  link.href = "/campaigns/linden-pass?app-loading-nav-check=1";
                  link.id = "app-nav-feedback-check";
                  link.textContent = "Characters";
                  link.style.position = "relative";
                  document.body.appendChild(link);
                }
                """
            )

            nav_link = page.locator("#app-nav-feedback-check")
            nav_link.click()
            expect(page.locator("html.app-loading")).to_have_count(1)

            assert page.evaluate("document.documentElement.classList.contains('app-loading')")
            page.wait_for_timeout(50)
            assert page.evaluate("document.documentElement.classList.contains('app-loading')")

            hide_ms = _measure_loading_hide_ms(page)
            assert hide_ms >= 0
            assert hide_ms >= 170
            expect(page.locator("html")).not_to_have_class("app-loading", timeout=5000)
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)
        finally:
            page.close()
            browser.close()


def test_browser_campaign_link_uses_document_navigation(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            target_request_count = 0

            def delay_session_route(route):
                nonlocal target_request_count
                if route.request.method == "GET" and route.request.url.rstrip("/").endswith("/campaigns/linden-pass/sections/sessions"):
                    target_request_count += 1
                    time.sleep(0.35)
                route.continue_()

            page.route("**/campaigns/linden-pass/sections/sessions", delay_session_route)
            page.route("**/static/styles.css**", lambda route: route.continue_())

            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            page.evaluate(
                """
                () => {
                  window.__cpwDocumentNavigationMarker = "old-document";
                  const link = document.createElement("a");
                  link.href = "/campaigns/linden-pass/sections/sessions";
                  link.id = "app-document-nav-section-link";
                  link.textContent = "Sessions section";
                  document.body.appendChild(link);
                }
                """
            )

            page.locator("#app-document-nav-section-link").click()
            expect(page.locator("html.app-loading")).to_have_count(1, timeout=1000)

            page.wait_for_url("**/campaigns/linden-pass/sections/sessions")
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)
            expect(page.locator("main h1").first).to_contain_text("Sessions")
            assert page.evaluate("window.__cpwDocumentNavigationMarker") is None
            assert target_request_count == 1
        finally:
            page.close()
            browser.close()


def test_browser_navigation_feedback_form_submit_shows_loader(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.route("**/static/styles.css**", lambda route: route.continue_())

            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            page.wait_for_timeout(150)

            page.evaluate(
                """
                () => {
                  sessionStorage.setItem("cpw-test-nav-start", String(Date.now()));
                  const form = document.createElement("form");
                  form.id = "app-nav-feedback-form";
                  form.method = "get";
                  form.action = "/campaigns/linden-pass?app-loading-form-check=1";
                  const submitButton = document.createElement("button");
                  submitButton.type = "submit";
                  submitButton.id = "app-nav-feedback-form-submit";
                  submitButton.textContent = "Submit";
                  form.appendChild(submitButton);
                  document.body.appendChild(form);
                }
                """
            )

            page.locator("#app-nav-feedback-form-submit").click()
            expect(page.locator("html.app-loading")).to_have_count(1)

            assert page.evaluate("document.documentElement.classList.contains('app-loading')")
            hide_ms = _measure_loading_hide_ms(page)
            assert hide_ms >= 0
            assert hide_ms >= 170
            expect(page.locator("html")).not_to_have_class("app-loading", timeout=5000)
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)
        finally:
            page.close()
            browser.close()


def test_browser_navigation_feedback_exclusions_dont_show_loader(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            page.wait_for_timeout(150)

            page.evaluate(
                """
                () => {
                  const target = document.createElement("a");
                  target.href = "/campaigns/linden-pass?app-loading-nav-check=1";
                  target.textContent = "Characters";
                  target.id = "same-doc-exclude";
                  document.body.appendChild(target);

                  const hashTarget = document.createElement("a");
                  hashTarget.href = "#app-loading-test-hash";
                  hashTarget.textContent = "Hash jump";
                  hashTarget.id = "hash-only-exclude";
                  document.body.appendChild(hashTarget);

                  const section = document.createElement("section");
                  section.id = "app-loading-test-hash";
                  document.body.appendChild(section);

                  sessionStorage.removeItem("cpw:app-loading-nav-start");
                  sessionStorage.removeItem("cpw-test-nav-start");
                }
                """
            )

            page.evaluate(
                """
                () => {
                  const target = document.querySelector("#same-doc-exclude");
                  const clickEvent = new MouseEvent("click", {
                    bubbles: true,
                    cancelable: true,
                    button: 0,
                    ctrlKey: true,
                  });
                  target.dispatchEvent(clickEvent);
                }
                """
            )
            page.wait_for_timeout(150)
            expect(page.locator("html.app-loading")).to_have_count(0, timeout=5000)
            assert not page.evaluate("document.documentElement.classList.contains('app-loading')")
            assert (
                page.evaluate("sessionStorage.getItem('cpw:app-loading-nav-start')") is None
            )

            page.locator("#hash-only-exclude").click()
            page.wait_for_timeout(120)
            assert page.url.endswith("#app-loading-test-hash")
            assert not page.evaluate("document.documentElement.classList.contains('app-loading')")
            assert (
                page.evaluate("sessionStorage.getItem('cpw:app-loading-nav-start')") is None
            )
        finally:
            page.close()
            browser.close()
