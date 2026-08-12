  (() => {
    const shellRoot = document.querySelector("[data-character-read-shell-root]");
    if (!shellRoot) {
      return;
    }

    const liveUiTools = window.__playerWikiLiveUiTools || {};
    const captureFocus = typeof liveUiTools.captureFocus === "function" ? liveUiTools.captureFocus : null;
    const restoreFocus = typeof liveUiTools.restoreFocus === "function" ? liveUiTools.restoreFocus : null;
    const restoreFocusKey = typeof liveUiTools.restoreFocusKey === "function"
      ? liveUiTools.restoreFocusKey
      : null;
    const captureViewportAnchor = typeof liveUiTools.captureViewportAnchor === "function"
      ? liveUiTools.captureViewportAnchor
      : null;
    const restoreViewportAnchor = typeof liveUiTools.restoreViewportAnchor === "function"
      ? liveUiTools.restoreViewportAnchor
      : null;

    const normalizeMode = (value) => {
      const normalized = String(value || "").trim().toLowerCase();
      return normalized === "session" ? "session" : "read";
    };

    const normalizeSubpage = (value) => {
      const normalized = String(value || "").trim().toLowerCase();
      return normalized || "quick";
    };

    const toPathFromUrl = (rawUrl) => {
      try {
        const url = new URL(rawUrl, window.location.origin);
        return url.pathname || window.location.pathname;
      } catch (_error) {
        return window.location.pathname;
      }
    };

    const parseModeAndPageFromUrl = (rawUrl) => {
      try {
        const url = new URL(rawUrl, window.location.origin);
        const params = new URLSearchParams(url.search);
        const requestedPage = params.get("page");
        return {
          mode: normalizeMode(params.get("mode")),
          page: normalizeSubpage(requestedPage || "quick"),
          hash: url.hash || "",
          path: url.pathname || window.location.pathname,
          href: `${url.pathname}${url.search}${url.hash}`,
        };
      } catch (_error) {
        return {
          mode: normalizeMode(shellRoot.dataset.characterReadShellMode || "read"),
          page: normalizeSubpage(shellRoot.dataset.characterReadShellPage || "quick"),
          hash: window.location.hash || "",
          path: window.location.pathname,
          href: window.location.pathname + window.location.search + window.location.hash,
        };
      }
    };

    const buildCharacterReadHref = ({ mode, page, path, hash }) => {
      const searchParams = new URLSearchParams();
      const normalizedMode = normalizeMode(mode);
      const normalizedPage = normalizeSubpage(page);
      if (normalizedMode === "session") {
        searchParams.set("mode", "session");
      }
      searchParams.set("page", normalizedPage);
      const query = searchParams.toString();
      return `${path || window.location.pathname}${query ? `?${query}` : ""}${hash || ""}`;
    };

    const getPanel = () => shellRoot.querySelector("[data-character-read-shell-panel]");
    const getSectionContent = () => shellRoot.querySelector("[data-character-read-section-content]");
    const getPanelLinks = () => Array.from(
      shellRoot.querySelectorAll("[data-character-read-subpage-link]"),
    );
    const getLoadingStatus = () => shellRoot.querySelector("[data-character-read-shell-loading]");
    let mountedSectionTransition = null;
    const clearSubpageBusy = (controller = null) => {
      const activeController = window._characterReadShellAbortController || null;
      if (controller && activeController && activeController !== controller) {
        return;
      }
      shellRoot.removeAttribute("aria-busy");
      const loadingStatus = getLoadingStatus();
      if (loadingStatus) {
        loadingStatus.hidden = true;
      }
      for (const link of getPanelLinks()) {
        link.removeAttribute("data-character-read-pending");
      }
      if (!controller || activeController === controller) {
        window._characterReadShellAbortController = null;
      }
    };
    const cancelActiveSubpageRequest = () => {
      const activeController = window._characterReadShellAbortController || null;
      if (!activeController) {
        rollbackMountedSectionTransition();
        clearSubpageBusy();
        return;
      }
      activeController.abort();
      rollbackMountedSectionTransition(activeController);
      clearSubpageBusy(activeController);
    };
    const setSubpageBusy = (controller, targetState) => {
      window._characterReadShellAbortController = controller;
      shellRoot.setAttribute("aria-busy", "true");
      const targetLink = getPanelLinks().find((link) => {
        const linkState = parseModeAndPageFromUrl(link.getAttribute("href") || "");
        return linkState.mode === targetState.mode && linkState.page === targetState.page;
      });
      if (targetLink) {
        targetLink.setAttribute("data-character-read-pending", "true");
      }
      const loadingStatus = getLoadingStatus();
      if (loadingStatus) {
        const loadingMessage = loadingStatus.querySelector(
          "[data-character-read-shell-loading-message]",
        );
        if (loadingMessage) {
          const targetLabel = String(targetLink?.textContent || "").trim();
          loadingMessage.textContent = targetLabel
            ? `Loading ${targetLabel}...`
            : "Loading character section...";
        }
        loadingStatus.hidden = false;
      }
    };
    const showSubpageUnavailable = () => {
      const loadingStatus = getLoadingStatus();
      if (!loadingStatus) {
        return;
      }
      const loadingMessage = loadingStatus.querySelector(
        "[data-character-read-shell-loading-message]",
      );
      if (loadingMessage) {
        loadingMessage.textContent = "Character pages are busy. Wait a moment, then choose the section again.";
      }
      loadingStatus.hidden = false;
    };
    const POST_SAVE_BUSY_RETRY_LIMIT = 4;
    const POST_SAVE_BUSY_DEFAULT_DELAY_MS = 2000;
    const POST_SAVE_BUSY_MAX_DELAY_MS = 5000;
    const POST_SAVE_BUSY_JITTER_MS = 250;
    const getPostSaveBusyRetryDelayMs = (response) => {
      const retryAfterSeconds = Number.parseFloat(
        String(response.headers.get("Retry-After") || ""),
      );
      const requestedDelayMs = Number.isFinite(retryAfterSeconds) && retryAfterSeconds >= 0
        ? retryAfterSeconds * 1000
        : POST_SAVE_BUSY_DEFAULT_DELAY_MS;
      const boundedDelayMs = Math.min(
        POST_SAVE_BUSY_MAX_DELAY_MS,
        Math.max(100, requestedDelayMs),
      );
      return boundedDelayMs + Math.floor(Math.random() * POST_SAVE_BUSY_JITTER_MS);
    };
    const showPostSaveRefreshPending = () => {
      shellRoot.setAttribute("aria-busy", "true");
      const loadingStatus = getLoadingStatus();
      if (!loadingStatus) {
        return;
      }
      const loadingMessage = loadingStatus.querySelector(
        "[data-character-read-shell-loading-message]",
      );
      if (loadingMessage) {
        loadingMessage.textContent = "Change submitted. Waiting for the refreshed character sheet...";
      }
      loadingStatus.hidden = false;
    };
    const showPostSaveRefreshUnavailable = () => {
      const loadingStatus = getLoadingStatus();
      if (!loadingStatus) {
        return;
      }
      const loadingMessage = loadingStatus.querySelector(
        "[data-character-read-shell-loading-message]",
      );
      if (loadingMessage) {
        loadingMessage.textContent = "Change submitted, but the refreshed character sheet is still busy. Wait a moment, then choose another section and return.";
      }
      loadingStatus.hidden = false;
    };
    const retryBusyPostSaveRefresh = async (initialResponse, fallbackHref, actionHref) => {
      let normalizedActionHref = "";
      try {
        normalizedActionHref = new URL(actionHref, window.location.origin).href;
      } catch (_error) {
        normalizedActionHref = "";
      }
      const reachedRedirectTarget = initialResponse.redirected || (
        !!initialResponse.url
        && !!normalizedActionHref
        && initialResponse.url !== normalizedActionHref
      );
      if (initialResponse.status !== 503 || !reachedRedirectTarget) {
        return {
          response: initialResponse,
          attempted: false,
          exhausted: false,
        };
      }

      const refreshHref = initialResponse.url || fallbackHref;
      if (!refreshHref) {
        return {
          response: initialResponse,
          attempted: false,
          exhausted: false,
        };
      }

      let response = initialResponse;
      for (let attempt = 0; attempt < POST_SAVE_BUSY_RETRY_LIMIT; attempt += 1) {
        showPostSaveRefreshPending();
        await new Promise((resolve) => {
          window.setTimeout(resolve, getPostSaveBusyRetryDelayMs(response));
        });
        try {
          response = await fetch(refreshHref, {
            headers: {
              "X-Requested-With": "XMLHttpRequest",
              "Accept": "text/html",
            },
            cache: "no-store",
            credentials: "same-origin",
          });
        } catch (_error) {
          return {
            response,
            attempted: true,
            exhausted: true,
          };
        }
        if (response.status !== 503) {
          return {
            response,
            attempted: true,
            exhausted: false,
          };
        }
      }

      return {
        response,
        attempted: true,
        exhausted: true,
      };
    };
    const getShellState = () => {
      return {
        mode: normalizeMode(shellRoot.dataset.characterReadShellMode || "read"),
        subpage: normalizeSubpage(shellRoot.dataset.characterReadShellPage || "quick"),
      };
    };

    const makePanelSnapshotState = (href) => parseModeAndPageFromUrl(href);

    const isTrackableField = (field) => {
      if (field instanceof HTMLInputElement) {
        return !["hidden", "submit", "button", "file"].includes(field.type);
      }
      return field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement;
    };

    const captureMountedState = (root) => {
      if (!(root instanceof Element)) {
        return null;
      }
      const fields = Array.from(root.querySelectorAll("input, textarea, select"));
      const trackedFields = [];
      for (const field of fields) {
        if (!isTrackableField(field)) {
          continue;
        }
        const index = trackedFields.length;
        const fieldState = {
          index,
          tagName: field.tagName.toLowerCase(),
          type: field instanceof HTMLInputElement ? String(field.type || "").toLowerCase() : "",
          name: field.name || "",
          value: String(field.value || ""),
        };
        if (field instanceof HTMLInputElement && (field.type === "checkbox" || field.type === "radio")) {
          fieldState.checked = !!field.checked;
        }
        if (field instanceof HTMLSelectElement) {
          if (field.multiple) {
            fieldState.selectedValues = Array.from(field.selectedOptions || []).map(
              (option) => String(option.value || ""),
            );
          } else {
            fieldState.selectedIndex = Number.isInteger(field.selectedIndex) ? field.selectedIndex : 0;
          }
        }
        trackedFields.push(fieldState);
      }

      const openDetails = Array.from(root.querySelectorAll("details")).map((details, index) => ({
        index,
        open: !!details.open,
      }));
      const spellcastingViews = Array.from(root.querySelectorAll("[data-character-spellcasting-view-switch]"))
        .map((viewSwitch, index) => {
          if (!(viewSwitch instanceof HTMLElement)) {
            return null;
          }
          const activePanel = Array.from(
            viewSwitch.querySelectorAll("[data-character-spellcasting-view-panel]"),
          ).find((panel) => panel instanceof HTMLElement && !panel.hidden);
          if (!(activePanel instanceof HTMLElement)) {
            return null;
          }
          return {
            index,
            view: activePanel.dataset.characterSpellcastingViewPanel || "",
          };
        })
        .filter(Boolean);
      const focusState = captureFocus ? captureFocus(root) : null;
      const viewportAnchor = captureViewportAnchor ? captureViewportAnchor(root) : null;
      return {
        trackedFields,
        openDetails,
        spellcastingViews,
        focusState,
        viewportAnchor,
      };
    };

    const captureLiveMountedState = (root) => {
      if (!(root instanceof Element)) {
        return null;
      }
      const activeElement = document.activeElement;
      const modalDialog = activeElement instanceof Element
        ? activeElement.closest("dialog:modal")
        : null;
      return {
        focusState: captureFocus ? captureFocus(root) : null,
        modalDialog: modalDialog instanceof HTMLDialogElement ? modalDialog : null,
        viewportAnchor: {
          descriptor: null,
          top: 0,
          scrollY: window.scrollY,
        },
      };
    };

    const restoreMountedState = (root, snapshot, { restoreFieldValues = true } = {}) => {
      if (!(root instanceof Element) || !snapshot || typeof snapshot !== "object") {
        return;
      }
      if (restoreFieldValues && Array.isArray(snapshot.trackedFields)) {
        const fields = Array.from(root.querySelectorAll("input, textarea, select"));
        const trackedFields = fields.filter(isTrackableField);
        for (const snapshotField of snapshot.trackedFields) {
          if (!snapshotField || typeof snapshotField.index !== "number") {
            continue;
          }
          const field = trackedFields[snapshotField.index];
          if (
            !(field instanceof HTMLInputElement)
            && !(field instanceof HTMLTextAreaElement)
            && !(field instanceof HTMLSelectElement)
          ) {
            continue;
          }
          if (field instanceof HTMLInputElement && (field.type === "checkbox" || field.type === "radio")) {
            if (typeof snapshotField.checked === "boolean") {
              field.checked = snapshotField.checked;
            }
            continue;
          }
          if (field instanceof HTMLSelectElement) {
            if (field.multiple && Array.isArray(snapshotField.selectedValues)) {
              const selectedValues = new Set(snapshotField.selectedValues.map(String));
              for (const option of Array.from(field.options)) {
                option.selected = selectedValues.has(String(option.value || ""));
              }
              continue;
            }
            const selectedIndex = Number.isInteger(snapshotField.selectedIndex) ? snapshotField.selectedIndex : 0;
            if (selectedIndex >= 0 && selectedIndex < field.options.length) {
              field.selectedIndex = selectedIndex;
            }
            continue;
          }
          if (typeof snapshotField.value === "string") {
            field.value = snapshotField.value;
          }
        }
      }

      const details = Array.from(root.querySelectorAll("details"));
      if (Array.isArray(snapshot.openDetails)) {
        for (const detailState of snapshot.openDetails) {
          const detailsIndex = Number(detailState?.index);
          const detailsNode = detailState
            && Number.isInteger(detailsIndex)
            && details[detailsIndex];
          if (detailsNode instanceof HTMLDetailsElement) {
            detailsNode.open = !!detailState.open;
          }
        }
      }

      if (Array.isArray(snapshot.spellcastingViews)) {
        const viewSwitches = Array.from(root.querySelectorAll("[data-character-spellcasting-view-switch]"));
        for (const spellcastingViewState of snapshot.spellcastingViews) {
          const viewSwitchIndex = Number(spellcastingViewState?.index);
          const viewSwitch = spellcastingViewState
            && Number.isInteger(viewSwitchIndex)
            && viewSwitches[viewSwitchIndex];
          const activateView = viewSwitch && viewSwitch.__characterSpellcastingActivateView;
          if (viewSwitch instanceof HTMLElement && typeof activateView === "function") {
            activateView(String(spellcastingViewState.view || ""));
          }
        }
      }

      window.requestAnimationFrame(() => {
        if (restoreViewportAnchor) {
          restoreViewportAnchor(root, snapshot.viewportAnchor);
        }
        if (restoreFocus) {
          restoreFocus(root, snapshot.focusState);
        }
      });
    };

    const restoreLiveMountedState = (root, snapshot) => {
      if (!(root instanceof Element) || !snapshot || typeof snapshot !== "object") {
        return;
      }
      const modalDialog = snapshot.modalDialog;
      if (
        modalDialog instanceof HTMLDialogElement
        && modalDialog.isConnected
        && modalDialog.open
        && !modalDialog.matches(":modal")
      ) {
        modalDialog.open = false;
        try {
          modalDialog.showModal();
        } catch (_error) {
          modalDialog.open = true;
        }
      }
      window.requestAnimationFrame(() => {
        if (restoreViewportAnchor) {
          restoreViewportAnchor(root, snapshot.viewportAnchor);
        }
        if (restoreFocus) {
          restoreFocus(root, snapshot.focusState);
        }
      });
    };

    const beginMountedSectionTransition = ({
      controller = null,
      committedHref,
      committedSection,
      committedMountedState,
      restoreMutableState = false,
      stagedSection,
    }) => {
      const token = {};
      mountedSectionTransition = {
        token,
        controller,
        committedHref,
        committedSection,
        committedMountedState,
        restoreMutableState,
        stagedSection,
      };
      return token;
    };

    const completeMountedSectionTransition = (token) => {
      if (!mountedSectionTransition || mountedSectionTransition.token !== token) {
        return false;
      }
      mountedSectionTransition = null;
      return true;
    };

    const isMountedSectionTransitionCurrent = (token) => (
      !!mountedSectionTransition && mountedSectionTransition.token === token
    );

    const rollbackMountedSectionTransition = (controller = null) => {
      const transition = mountedSectionTransition;
      if (!transition || (controller && transition.controller !== controller)) {
        return false;
      }
      mountedSectionTransition = null;
      if (
        transition.stagedSection instanceof Element
        && transition.stagedSection.isConnected
        && transition.committedSection instanceof Element
      ) {
        transition.stagedSection.replaceWith(transition.committedSection);
        syncShellState(parseModeAndPageFromUrl(transition.committedHref));
        if (transition.restoreMutableState) {
          restoreMountedState(transition.committedSection, transition.committedMountedState);
        } else {
          restoreLiveMountedState(transition.committedSection, transition.committedMountedState);
        }
      }
      return true;
    };

    const syncActiveNav = (targetSubpage) => {
      const normalized = normalizeSubpage(targetSubpage);
      for (const link of getPanelLinks()) {
        const isActive = normalizeSubpage(link.dataset.characterReadTargetSubpage || "") === normalized;
        link.classList.toggle("button-link", isActive);
        link.classList.toggle("ghost-button", !isActive);
      }
    };

    const syncShellState = ({ mode, subpage, page }) => {
      const nextMode = normalizeMode(mode);
      const nextSubpage = normalizeSubpage(subpage || page);
      shellRoot.dataset.characterReadShellMode = nextMode;
      shellRoot.dataset.characterReadShellPage = nextSubpage;
      syncActiveNav(nextSubpage);
    };

    const syncElementAttributes = (currentElement, responseElement) => {
      for (const attribute of Array.from(currentElement.attributes)) {
        if (!responseElement.hasAttribute(attribute.name)) {
          currentElement.removeAttribute(attribute.name);
        }
      }
      for (const attribute of Array.from(responseElement.attributes)) {
        currentElement.setAttribute(attribute.name, attribute.value);
      }
    };

    const reconcileCommonChrome = ({ responseHeader, responseNavCard, responseNav }) => {
      const panel = getPanel();
      const currentHeader = panel?.querySelector(".character-header");
      const currentNavCard = panel?.querySelector("[data-character-subpage-nav-card]");
      const currentNav = currentNavCard?.querySelector(".character-subpage-nav");
      if (
        !(currentHeader instanceof HTMLElement)
        || !(currentNavCard instanceof HTMLElement)
        || !(currentNav instanceof HTMLElement)
        || !(responseHeader instanceof HTMLElement)
        || !(responseNavCard instanceof HTMLElement)
        || !(responseNav instanceof HTMLElement)
      ) {
        return false;
      }

      const currentLinks = Array.from(
        currentNav.querySelectorAll("[data-character-read-subpage-link]"),
      );
      const currentLinksBySubpage = new Map();
      for (const link of currentLinks) {
        const subpage = String(link.dataset.characterReadTargetSubpage || "").trim();
        if (!subpage || currentLinksBySubpage.has(subpage)) {
          return false;
        }
        currentLinksBySubpage.set(subpage, link);
      }

      const responseLinks = Array.from(
        responseNav.querySelectorAll("[data-character-read-subpage-link]"),
      );
      const desiredLinks = [];
      const desiredSubpages = new Set();
      for (const responseLink of responseLinks) {
        const subpage = String(responseLink.dataset.characterReadTargetSubpage || "").trim();
        if (!subpage || desiredSubpages.has(subpage)) {
          return false;
        }
        desiredSubpages.add(subpage);
        const currentLink = currentLinksBySubpage.get(subpage) || responseLink;
        if (currentLink !== responseLink) {
          syncElementAttributes(currentLink, responseLink);
          currentLink.replaceChildren(...Array.from(responseLink.childNodes));
        }
        desiredLinks.push(currentLink);
      }

      syncElementAttributes(currentHeader, responseHeader);
      currentHeader.replaceChildren(...Array.from(responseHeader.childNodes));
      syncElementAttributes(currentNavCard, responseNavCard);
      syncElementAttributes(currentNav, responseNav);

      let insertionPoint = currentNav.firstElementChild;
      for (const desiredLink of desiredLinks) {
        if (desiredLink !== insertionPoint) {
          currentNav.insertBefore(desiredLink, insertionPoint);
        }
        insertionPoint = desiredLink.nextElementSibling;
      }
      for (const currentLink of currentLinks) {
        const subpage = String(currentLink.dataset.characterReadTargetSubpage || "").trim();
        if (!desiredSubpages.has(subpage)) {
          currentLink.remove();
        }
      }
      return true;
    };

    const getResponseStateFromHtml = (html) => {
      const parser = new DOMParser();
      const responseDocument = parser.parseFromString(html, "text/html");
      const responseShellRoot = responseDocument.querySelector("[data-character-read-shell-root]");
      const responsePanel = responseDocument.querySelector("[data-character-read-shell-panel]");
      const responseHeader = responsePanel?.querySelector(".character-header");
      const responseNavCard = responsePanel?.querySelector("[data-character-subpage-nav-card]");
      const responseNav = responseNavCard?.querySelector(".character-subpage-nav");
      const responseContent = responsePanel?.querySelector("[data-character-read-section-content]");
      const flashStack = responseDocument.querySelector("[data-flash-stack-root]");
      const hasErrorFlash = !!(flashStack && flashStack.querySelector(".flash-error"));
      if (
        !responseShellRoot
        || !responsePanel
        || !responseHeader
        || !responseNavCard
        || !responseNav
        || !responseContent
      ) {
        return null;
      }
      return {
        responseHeader,
        responseNavCard,
        responseNav,
        responseContent,
        responseMode: normalizeMode(responseShellRoot.dataset.characterReadShellMode || ""),
        responseSubpage: normalizeSubpage(responseShellRoot.dataset.characterReadShellPage || ""),
        flashStackHtml: flashStack ? flashStack.innerHTML : "",
        hasErrorFlash,
      };
    };

    const replaceFlashStack = (flashStackHtml) => {
      const currentFlashStack = document.querySelector("[data-flash-stack-root]");
      if (!currentFlashStack || typeof flashStackHtml !== "string") {
        return;
      }
      currentFlashStack.innerHTML = flashStackHtml;
    };

    const waitForMountedContentSettlement = () => new Promise((resolve) => {
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(resolve);
      });
    });

    const initialPanelState = getShellState();
    if (initialPanelState.mode !== "read") {
      return;
    }
    const initialState = makePanelSnapshotState(window.location.href);
    syncActiveNav(initialState.page);
    const sectionMountedStateCache = new Map();
    const initializedAutosubmitForms = new WeakSet();
    const initializedSpellcastingSearchForms = new WeakSet();
    const initializedSystemsItemSearchForms = new WeakSet();
    const initializedSpellcastingViewSwitches = new WeakSet();
    const buildAutosubmitFormState = (form) => {
      if (!(form instanceof HTMLFormElement)) {
        return "";
      }
      const params = new URLSearchParams();
      for (const [name, value] of new FormData(form).entries()) {
        params.append(name, typeof value === "string" ? value : "");
      }
      return params.toString();
    };
    const fieldAllowsAutosubmit = (field) => {
      if (field instanceof HTMLInputElement && field.type === "number" && field.value.trim() === "") {
        return false;
      }
      return true;
    };
    const queueAutosubmit = (form, field, delayMs = 350) => {
      if (!(form instanceof HTMLFormElement) || !fieldAllowsAutosubmit(field)) {
        return;
      }
      window.clearTimeout(Number(form.dataset.characterAutosubmitTimer || "0"));
      const submit = () => {
        form.dataset.characterAutosubmitTimer = "0";
        if (buildAutosubmitFormState(form) === String(form.dataset.characterAutosubmitState || "")) {
          return;
        }
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
          return;
        }
        form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      };
      form.dataset.characterAutosubmitTimer = String(window.setTimeout(submit, delayMs));
    };
    const initAutosubmitForms = (scope) => {
      if (!(scope instanceof Element)) {
        return;
      }
      const forms = Array.from(scope.querySelectorAll("[data-character-autosubmit]"));
      for (const form of forms) {
        if (!(form instanceof HTMLFormElement)) {
          continue;
        }
        form.dataset.characterAutosubmitState = buildAutosubmitFormState(form);
        if (initializedAutosubmitForms.has(form)) {
          continue;
        }
        initializedAutosubmitForms.add(form);
        form.addEventListener("input", (event) => {
          const field = event.target;
          if (!(field instanceof HTMLInputElement) || field.type !== "number") {
            return;
          }
          queueAutosubmit(form, field, 450);
        });
        form.addEventListener("change", (event) => {
          const field = event.target;
          if (
            !(field instanceof HTMLInputElement)
            && !(field instanceof HTMLSelectElement)
            && !(field instanceof HTMLTextAreaElement)
          ) {
            return;
          }
          queueAutosubmit(form, field, 0);
        });
        form.addEventListener("keydown", (event) => {
          const field = event.target;
          if (event.key !== "Enter" || !fieldAllowsAutosubmit(field)) {
            return;
          }
          if (
            !(field instanceof HTMLInputElement)
            && !(field instanceof HTMLSelectElement)
          ) {
            return;
          }
          event.preventDefault();
          queueAutosubmit(form, field, 0);
        });
      }
    };
    const initPanelScriptForms = (scope) => {
      if (!(scope instanceof Element)) {
        return;
      }
      initAutosubmitForms(scope);

      const spellcastingViewSwitches = Array.from(scope.querySelectorAll("[data-character-spellcasting-view-switch]"));
      for (const viewSwitch of spellcastingViewSwitches) {
        if (!(viewSwitch instanceof HTMLElement) || initializedSpellcastingViewSwitches.has(viewSwitch)) {
          continue;
        }
        initializedSpellcastingViewSwitches.add(viewSwitch);
        const buttons = Array.from(
          viewSwitch.querySelectorAll("[data-character-spellcasting-view-button]"),
        ).filter((button) => button instanceof HTMLElement);
        const panels = Array.from(
          viewSwitch.querySelectorAll("[data-character-spellcasting-view-panel]"),
        ).filter((panel) => panel instanceof HTMLElement);
        if (!buttons.length || !panels.length) {
          continue;
        }

        const panelViews = new Set(panels.map((panel) => panel.dataset.characterSpellcastingViewPanel || ""));
        const defaultView = panelViews.has(viewSwitch.dataset.characterSpellcastingDefaultView || "")
          ? viewSwitch.dataset.characterSpellcastingDefaultView
          : panels[0].dataset.characterSpellcastingViewPanel || "current";

        const activateView = (requestedView, { focusPanel = false } = {}) => {
          const nextView = panelViews.has(requestedView) ? requestedView : defaultView;
          for (const panel of panels) {
            const isActive = (panel.dataset.characterSpellcastingViewPanel || "") === nextView;
            panel.hidden = !isActive;
            panel.setAttribute("aria-hidden", isActive ? "false" : "true");
            if (isActive && focusPanel) {
              panel.focus({ preventScroll: true });
            }
          }
          for (const button of buttons) {
            const isActive = (button.dataset.characterSpellcastingViewButton || "") === nextView;
            button.classList.toggle("button-link", isActive);
            button.classList.toggle("ghost-button", !isActive);
            button.setAttribute("aria-selected", isActive ? "true" : "false");
          }
        };

        for (const button of buttons) {
          button.addEventListener("click", () => {
            activateView(button.dataset.characterSpellcastingViewButton || "", {
              focusPanel: true,
            });
          });
        }

        viewSwitch.__characterSpellcastingActivateView = activateView;
        activateView(defaultView);
      }

      const presentationController = window.__playerWikiPresentationController;
      if (presentationController && typeof presentationController.init === "function") {
        const triggerGates = [];
        for (const triggerTemplate of scope.querySelectorAll(
          "template[data-character-presentation-dialog-trigger-template]",
        )) {
          if (triggerTemplate instanceof HTMLTemplateElement) {
            const triggerGate = document.createElement("span");
            triggerGate.hidden = true;
            triggerGate.dataset.characterPresentationDialogTriggerGate = "";
            triggerGate.append(triggerTemplate.content.cloneNode(true));
            triggerTemplate.replaceWith(triggerGate);
            triggerGates.push(triggerGate);
          }
        }
        if (triggerGates.length) {
          document.documentElement.classList.remove("spell-modal-js");
        }
        let presentationInitializationFailed = false;
        try {
          presentationController.init(scope);
        } catch (_error) {
          presentationInitializationFailed = true;
          scope.dataset.characterPresentationDialogState = "unavailable";
        }
        if (!presentationInitializationFailed) {
          const spellModalTriggers = Array.from(
            scope.querySelectorAll("[data-character-spell-modal-trigger][data-presentation-dialog-trigger]"),
          );
          const allSpellModalTriggersEnabled = spellModalTriggers.length > 0 && spellModalTriggers.every(
            (trigger) => trigger instanceof HTMLElement && !trigger.hidden,
          );
          if (allSpellModalTriggersEnabled) {
            for (const triggerGate of triggerGates) {
              const trigger = triggerGate.querySelector(
                "[data-character-spell-modal-trigger][data-presentation-dialog-trigger]",
              );
              if (trigger instanceof HTMLElement) {
                triggerGate.replaceWith(trigger);
              }
            }
            scope.dataset.characterPresentationDialogState = "ready";
            document.documentElement.classList.add("spell-modal-js");
          } else {
            scope.dataset.characterPresentationDialogState = "unavailable";
          }
        }
      }

      const castSearchForms = Array.from(scope.querySelectorAll("[data-character-spell-search-form]"));
      for (const form of castSearchForms) {
        if (!(form instanceof HTMLFormElement) || initializedSpellcastingSearchForms.has(form)) {
          continue;
        }
        initializedSpellcastingSearchForms.add(form);

        const searchInput = form.querySelector("[data-character-spell-query]");
        const resultsSelect = form.querySelector("[data-character-spell-results]");
        const status = form.querySelector("[data-character-spell-status]");
        const searchUrl = form.dataset.characterSpellSearchUrl || "";
        const searchKind = form.dataset.characterSpellSearchKind || "spell";
        const targetClassRowId = form.dataset.characterSpellSearchTargetRow || "";
        const emptyLabel = form.dataset.characterSpellSearchEmptyLabel || "Search to load matching spells";
        const promptText = form.dataset.characterSpellSearchPrompt || "Type at least 2 letters to search eligible class spells.";
        if (
          !(searchInput instanceof HTMLInputElement)
          || !(resultsSelect instanceof HTMLSelectElement)
          || !(status instanceof HTMLElement)
          || !searchUrl
        ) {
          continue;
        }

        let searchAbortController = null;
        let searchTimerId = 0;

        const resetResults = (message) => {
          resultsSelect.innerHTML = "";
          const option = document.createElement("option");
          option.value = "";
          option.textContent = emptyLabel;
          resultsSelect.append(option);
          resultsSelect.disabled = true;
          status.textContent = message || promptText;
        };

        const renderResults = (results, message) => {
          if (!Array.isArray(results) || !results.length) {
            resetResults(message || "No eligible class spells matched that search.");
            return;
          }
          resultsSelect.innerHTML = "";
          for (const result of results) {
            const option = document.createElement("option");
            option.value = String(result.entry_slug || "");
            option.textContent = String(result.select_label || result.title || "");
            resultsSelect.append(option);
          }
          resultsSelect.disabled = false;
          resultsSelect.selectedIndex = 0;
          status.textContent = message || `Found ${results.length} matching spells.`;
        };

        const runSearch = async () => {
          const query = searchInput.value.trim();
          if (searchAbortController) {
            searchAbortController.abort();
          }
          if (query.length < 2) {
            resetResults(promptText);
            return;
          }

          searchAbortController = new AbortController();
          status.textContent = "Searching spells...";
          try {
            const params = new URLSearchParams({
              kind: searchKind,
              q: query,
            });
            if (targetClassRowId) {
              params.set("target_class_row_id", targetClassRowId);
            }
            const response = await fetch(
              `${searchUrl}?${params.toString()}`,
              {
                headers: {
                  "X-Requested-With": "XMLHttpRequest",
                  "Accept": "application/json",
                },
                cache: "no-store",
                credentials: "same-origin",
                signal: searchAbortController.signal,
              },
            );
            if (!response.ok) {
              resetResults("Could not search spells right now.");
              return;
            }

            const payload = await response.json();
            renderResults(payload.results, typeof payload.message === "string" ? payload.message : "");
          } catch (error) {
            if (error instanceof DOMException && error.name === "AbortError") {
              return;
            }
            resetResults("Could not search spells right now.");
          } finally {
            searchAbortController = null;
          }
        };

        searchInput.addEventListener("keydown", (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
          }
        });
        searchInput.addEventListener("input", () => {
          window.clearTimeout(searchTimerId);
          searchTimerId = window.setTimeout(runSearch, 250);
        });

        resetResults(status.textContent || promptText);
      }

      const systemsSearchForms = Array.from(scope.querySelectorAll("[data-character-systems-item-search-form]"));
      for (const form of systemsSearchForms) {
        if (!(form instanceof HTMLFormElement) || initializedSystemsItemSearchForms.has(form)) {
          continue;
        }
        initializedSystemsItemSearchForms.add(form);

        const searchInput = form.querySelector("[data-character-systems-item-query]");
        const resultsSelect = form.querySelector("[data-character-systems-item-results]");
        const status = form.querySelector("[data-character-systems-item-status]");
        const searchUrl = form.dataset.characterSystemsItemSearchUrl || "";
        if (
          !(searchInput instanceof HTMLInputElement)
          || !(resultsSelect instanceof HTMLSelectElement)
          || !(status instanceof HTMLElement)
          || !searchUrl
        ) {
          continue;
        }

        let searchAbortController = null;
        let searchTimerId = 0;

        const resetResults = (message) => {
          resultsSelect.innerHTML = "";
          const option = document.createElement("option");
          option.value = "";
          option.textContent = "Search to load matching items";
          resultsSelect.append(option);
          resultsSelect.disabled = true;
          status.textContent = message;
        };

        const renderResults = (results, message) => {
          if (!Array.isArray(results) || !results.length) {
            resetResults(message || "No enabled Systems items matched that search.");
            return;
          }
          resultsSelect.innerHTML = "";
          for (const result of results) {
            const option = document.createElement("option");
            option.value = String(result.entry_slug || "");
            option.textContent = String(result.select_label || result.title || "");
            resultsSelect.append(option);
          }
          resultsSelect.disabled = false;
          resultsSelect.selectedIndex = 0;
          status.textContent = message || `Found ${results.length} matching Systems items.`;
        };

        const runSearch = async () => {
          const query = searchInput.value.trim();
          if (searchAbortController) {
            searchAbortController.abort();
          }
          if (query.length < 2) {
            resetResults("Type at least 2 letters to search enabled Systems items.");
            return;
          }

          searchAbortController = new AbortController();
          status.textContent = "Searching Systems items...";
          try {
            const response = await fetch(`${searchUrl}?q=${encodeURIComponent(query)}`, {
              headers: {
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
              },
              cache: "no-store",
              credentials: "same-origin",
              signal: searchAbortController.signal,
            });
            if (!response.ok) {
              resetResults("Could not search Systems items right now.");
              return;
            }

            const payload = await response.json();
            renderResults(payload.results, typeof payload.message === "string" ? payload.message : "");
          } catch (error) {
            if (error instanceof DOMException && error.name === "AbortError") {
              return;
            }
            resetResults("Could not search Systems items right now.");
          } finally {
            searchAbortController = null;
          }
        };

        searchInput.addEventListener("keydown", (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
          }
        });
        searchInput.addEventListener("input", () => {
          window.clearTimeout(searchTimerId);
          searchTimerId = window.setTimeout(runSearch, 250);
        });

        resetResults("Type at least 2 letters to search enabled Systems items.");
      }
    };

    const makeSubmitState = () => {
      const { mode, subpage } = getShellState();
      return {
        mode,
        subpage,
        href: buildCharacterReadHref({
          mode,
          page: subpage,
          path: toPathFromUrl(window.location.href),
          hash: window.location.hash || "",
        }),
        mountedState: null,
      };
    };

    const cacheSectionState = (stateKey, section, mountedState = null) => {
      sectionMountedStateCache.set(stateKey, {
        section,
        mountedState,
      });
    };

    const getHistoryKey = (rawUrl) => {
      const stateFromUrl = parseModeAndPageFromUrl(rawUrl);
      return buildCharacterReadHref({
        mode: stateFromUrl.mode,
        page: stateFromUrl.page,
        path: stateFromUrl.path,
        hash: stateFromUrl.hash,
      });
    };

    const cacheCurrentSection = ({ captureMutableState = false } = {}) => {
      const section = getSectionContent();
      if (!section) {
        return;
      }
      const snapshot = makeSubmitState();
      snapshot.mountedState = captureMutableState
        ? captureMountedState(section)
        : captureLiveMountedState(section);
      cacheSectionState(snapshot.href, section, snapshot.mountedState);
      return snapshot;
    };

    const commitHistory = ({ canonical, replace }) => {
      const canonicalState = parseModeAndPageFromUrl(canonical);
      const state = {
        characterReadMode: canonicalState.mode,
        characterReadSubpage: canonicalState.page,
        characterReadHref: canonical,
      };
      if (replace) {
        window.history.replaceState(state, "", canonical);
      } else {
        window.history.pushState(state, "", canonical);
      }
      return canonical;
    };

    const updateHistory = ({ href, replace }) => commitHistory({
      canonical: getHistoryKey(href),
      replace,
    });

    const restoreFromCache = (stateHref, targetState) => {
      const state = sectionMountedStateCache.get(stateHref);
      if (!state) {
        return false;
      }
      const section = getSectionContent();
      if (!section) {
        return false;
      }
      if (!(state.section instanceof Element)) {
        return false;
      }
      section.replaceWith(state.section);
      syncShellState(targetState);
      restoreLiveMountedState(state.section, state.mountedState);
      return true;
    };

    const loadPanelFromResponseText = (responseText, responseHref, { fallbackPath = "" } = {}) => {
      const section = getSectionContent();
      if (!section) {
        return null;
      }

      const parsed = getResponseStateFromHtml(responseText);
      if (!parsed) {
        return null;
      }

      const responseUrl = parseModeAndPageFromUrl(responseHref || window.location.href);
      const canonicalHref = buildCharacterReadHref({
        mode: parsed.responseMode,
        page: parsed.responseSubpage,
        path: fallbackPath || responseUrl.path || window.location.pathname,
        hash: responseUrl.hash,
      });

      section.replaceWith(parsed.responseContent);
      const mountedContent = parsed.responseContent;
      initPanelScriptForms(mountedContent);

      return {
        mode: parsed.responseMode,
        page: parsed.responseSubpage,
        href: canonicalHref,
        content: mountedContent,
        flashStackHtml: parsed.flashStackHtml,
        hasErrorFlash: !!parsed.hasErrorFlash,
        commonChrome: parsed,
      };
    };

    const buildSubmitPayload = (form, submitter) => {
      let formData;
      try {
        formData = submitter ? new FormData(form, submitter) : new FormData(form);
      } catch (_error) {
        formData = new FormData(form);
        if (
          submitter
          && (submitter instanceof HTMLButtonElement || submitter instanceof HTMLInputElement)
          && submitter.name
          && !submitter.disabled
        ) {
          formData.append(submitter.name, submitter.value || "");
        }
      }
      return formData;
    };

    const submitFormInPanel = async (form, submitter) => {
      const action = form.getAttribute("action") || "";
      if (!action) {
        return;
      }
      if (form.method.toLowerCase() !== "post") {
        return;
      }

      const previousStateHref = getHistoryKey(window.location.pathname + window.location.search + window.location.hash);
      const committedSection = getSectionContent();
      const currentSectionSnapshot = cacheCurrentSection({ captureMutableState: true });
      const submittedMountedState = currentSectionSnapshot ? currentSectionSnapshot.mountedState : null;
      const postSubmitFocusKey = String(form.dataset.postSubmitFocusKey || "").trim();
      const payload = buildSubmitPayload(form, submitter);
      const submitControls = Array.from(form.querySelectorAll("button, input[type='submit']"));
      form.dataset.characterReadSubmitting = "1";
      form.setAttribute("aria-busy", "true");
      for (const control of submitControls) {
        control.disabled = true;
      }
      try {
        let response;
        try {
          response = await fetch(action, {
            method: "POST",
            headers: {
              "X-Requested-With": "XMLHttpRequest",
              "Accept": "text/html",
            },
            body: payload,
            cache: "no-store",
            credentials: "same-origin",
          });
        } catch (_error) {
          if (form.isConnected) {
            HTMLFormElement.prototype.submit.call(form);
          }
          return;
        }

        const postSaveRefreshResult = await retryBusyPostSaveRefresh(
          response,
          previousStateHref,
          action,
        );
        response = postSaveRefreshResult.response;
        if (postSaveRefreshResult.attempted) {
          clearSubpageBusy();
          if (postSaveRefreshResult.exhausted) {
            showPostSaveRefreshUnavailable();
            return;
          }
        }

        const responseText = await response.text();
        const switched = loadPanelFromResponseText(responseText, response.url, {
          fallbackPath: window.location.pathname,
        });
        if (!switched) {
          window.location.assign(response.url || action);
          return;
        }
        const transitionToken = beginMountedSectionTransition({
          committedHref: previousStateHref,
          committedSection,
          committedMountedState: submittedMountedState,
          restoreMutableState: true,
          stagedSection: switched.content,
        });
        let chromeReconciled = false;
        try {
          chromeReconciled = reconcileCommonChrome(switched.commonChrome);
          if (chromeReconciled) {
            replaceFlashStack(switched.flashStackHtml);
          }
        } catch (_error) {
          chromeReconciled = false;
        }
        if (!chromeReconciled) {
          rollbackMountedSectionTransition();
          window.location.assign(response.url || action);
          return;
        }
        if (!completeMountedSectionTransition(transitionToken)) {
          return;
        }
        const canonicalState = parseModeAndPageFromUrl(switched.href);
        if (response.ok && !switched.hasErrorFlash) {
          sectionMountedStateCache.clear();
        }
        cacheSectionState(canonicalState.href, switched.content, null);
        updateHistory({
          href: canonicalState.href,
          replace: true,
        });
        syncShellState(canonicalState);
        const currentContent = getSectionContent();
        if (currentContent) {
          const currentMode = shellRoot.dataset.characterReadShellMode;
          if (currentMode !== "read") {
            window.location.assign(response.url || action);
            return;
          }
          restoreMountedState(currentContent, submittedMountedState, {
            restoreFieldValues: !response.ok || !!switched.hasErrorFlash,
          });
          if (postSubmitFocusKey && restoreFocusKey) {
            window.requestAnimationFrame(() => {
              restoreFocusKey(currentContent, postSubmitFocusKey);
            });
          }
        }
        if (canonicalState.href !== getHistoryKey(previousStateHref)) {
          cacheCurrentSection();
        }
      } finally {
        if (form.isConnected) {
          delete form.dataset.characterReadSubmitting;
          form.removeAttribute("aria-busy");
          for (const control of submitControls) {
            control.disabled = false;
          }
        }
      }
    };

    const updateHistoryFromSubpage = async ({ href, replaceHistory = false, fromHistory = false }) => {
      const targetState = parseModeAndPageFromUrl(href);
      const currentState = getShellState();
      cancelActiveSubpageRequest();
      if (currentState.mode === targetState.mode && currentState.subpage === targetState.page) {
        if (fromHistory || replaceHistory) {
          syncShellState(currentState);
          updateHistory({ href: targetState.href, replace: true });
        }
        return;
      }

      const targetKey = buildCharacterReadHref({
        mode: targetState.mode,
        page: targetState.page,
        path: targetState.path,
        hash: targetState.hash,
      });
      const committedSection = getSectionContent();
      const committedSnapshot = cacheCurrentSection();
      if (restoreFromCache(targetKey, targetState)) {
        if (!fromHistory) {
          commitHistory({
            canonical: targetKey,
            replace: replaceHistory,
          });
        }
        return;
      }

      const controller = new AbortController();
      let showUnavailableAfterRequest = false;
      let completedShellState = null;
      setSubpageBusy(controller, targetState);
      try {
        const response = await fetch(targetState.href, {
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "text/html",
          },
          cache: "no-store",
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (controller.signal.aborted) {
          return;
        }
        if (response.status === 503) {
          showUnavailableAfterRequest = true;
          return;
        }
        const responseText = await response.text();
        const switched = loadPanelFromResponseText(responseText, response.url, {
          fallbackPath: targetState.path,
        });
        if (!switched) {
          window.location.assign(targetState.href);
          return;
        }
        const transitionToken = beginMountedSectionTransition({
          controller,
          committedHref: committedSnapshot?.href || getHistoryKey(window.location.href),
          committedSection,
          committedMountedState: committedSnapshot?.mountedState || null,
          stagedSection: switched.content,
        });
        await waitForMountedContentSettlement();
        if (controller.signal.aborted || !isMountedSectionTransitionCurrent(transitionToken)) {
          rollbackMountedSectionTransition(controller);
          return;
        }
        let chromeReconciled = false;
        try {
          chromeReconciled = reconcileCommonChrome(switched.commonChrome);
          if (chromeReconciled) {
            replaceFlashStack(switched.flashStackHtml);
          }
        } catch (_error) {
          chromeReconciled = false;
        }
        if (!chromeReconciled) {
          rollbackMountedSectionTransition(controller);
          window.location.assign(targetState.href);
          return;
        }
        if (!completeMountedSectionTransition(transitionToken)) {
          rollbackMountedSectionTransition(controller);
          return;
        }

        const shellStateFromHref = getHistoryKey(switched.href);
        cacheSectionState(shellStateFromHref, switched.content, null);
        if (fromHistory || replaceHistory) {
          updateHistory({ href: shellStateFromHref, replace: true });
        } else {
          updateHistory({ href: shellStateFromHref, replace: false });
        }
        completedShellState = parseModeAndPageFromUrl(shellStateFromHref);
      } catch (error) {
        rollbackMountedSectionTransition(controller);
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        window.location.assign(targetState.href);
      } finally {
        clearSubpageBusy(controller);
        if (completedShellState) {
          syncShellState(completedShellState);
        }
        if (showUnavailableAfterRequest) {
          showSubpageUnavailable();
        }
      }
    };

    const clickHandler = (event) => {
      if (event.defaultPrevented || event.button !== 0) {
        return;
      }
      const link = event.target instanceof Element
        ? event.target.closest("[data-character-read-subpage-link]")
        : null;
      if (!link || !shellRoot.contains(link)) {
        return;
      }
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
        return;
      }

      const href = link.getAttribute("href") || "";
      if (!href) {
        return;
      }
      event.preventDefault();
      void updateHistoryFromSubpage({ href, replaceHistory: false });
    };

    const submitHandler = (event) => {
      const panel = getPanel();
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || !panel || !panel.contains(form)) {
        return;
      }

      const method = String(form.method || "get").trim().toLowerCase();
      if (method !== "post") {
        return;
      }
      const action = form.getAttribute("action") || "";
      if (!action) {
        return;
      }
      event.preventDefault();
      if (form.dataset.characterReadSubmitting === "1") {
        return;
      }
      const submitter = event.submitter instanceof HTMLElement ? event.submitter : null;
      submitFormInPanel(form, submitter).catch(() => {
        if (form.isConnected) {
          HTMLFormElement.prototype.submit.call(form);
        } else {
          window.location.reload();
        }
      });
    };

    window.__playerWikiCharacterReadShell = {
      initPanelScriptForms,
      updateHistoryFromSubpage,
      syncActiveNav,
      toShellState: getShellState,
      cache: sectionMountedStateCache,
    };

    cacheCurrentSection();
    initPanelScriptForms(shellRoot);
    const initialCanonicalHref = getHistoryKey(window.location.href);
    window.history.replaceState(
      {
        characterReadMode: initialState.mode,
        characterReadSubpage: initialState.page,
        characterReadHref: initialCanonicalHref,
      },
      "",
      initialState.href,
    );

    const panel = getPanel();
    if (panel) {
      syncActiveNav(initialState.page);
    }

    shellRoot.addEventListener("click", clickHandler);
    shellRoot.addEventListener("submit", submitHandler);
    window.addEventListener("popstate", () => {
      const stateHref = window.history.state && typeof window.history.state.characterReadHref === "string"
        ? window.history.state.characterReadHref
        : window.location.pathname + window.location.search + window.location.hash;
      void updateHistoryFromSubpage({
        href: stateHref || window.location.pathname + window.location.search + window.location.hash,
        replaceHistory: true,
        fromHistory: true,
      });
    });
  })();
