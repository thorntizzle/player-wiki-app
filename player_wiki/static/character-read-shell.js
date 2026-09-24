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
      let reachedRedirectTarget = false;
      try {
        const redirectUrl = new URL(initialResponse.url);
        reachedRedirectTarget = initialResponse.redirected
          && redirectUrl.origin === window.location.origin
          && redirectUrl.pathname === window.location.pathname
          && initialResponse.url !== normalizedActionHref;
      } catch (_error) {
        reachedRedirectTarget = false;
      }
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
      const modalDialogTrigger = modalDialog instanceof HTMLDialogElement && modalDialog.id
        ? Array.from(root.querySelectorAll("[data-presentation-dialog-trigger]")).find(
          (trigger) => (
            trigger instanceof HTMLElement
            && (trigger.getAttribute("data-presentation-dialog-trigger") || "").trim() === modalDialog.id
          ),
        ) || null
        : null;
      return {
        focusState: captureFocus ? captureFocus(root) : null,
        modalDialog: modalDialog instanceof HTMLDialogElement ? modalDialog : null,
        modalDialogTrigger,
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

      // Selection belongs to this mount. A later frame must not overwrite an
      // edit made after publication, including on a retained cached node.
      if (restoreFocus) restoreFocus(root, snapshot.focusState);
      const restorationIntent = navigationIntent;
      window.requestAnimationFrame(() => {
        if (root !== getSectionContent() || restorationIntent !== navigationIntent) return;
        if (restoreViewportAnchor) {
          restoreViewportAnchor(root, snapshot.viewportAnchor);
        }
      });
    };

    const restoreLiveMountedState = (root, snapshot) => {
      if (!(root instanceof Element) || !snapshot || typeof snapshot !== "object") {
        return;
      }
      const modalDialog = snapshot.modalDialog;
      const modalDialogTrigger = snapshot.modalDialogTrigger;
      if (
        modalDialog instanceof HTMLDialogElement
        && modalDialog.isConnected
        && modalDialog.open
        && !modalDialog.matches(":modal")
      ) {
        modalDialog.open = false;
        const presentationController = window.__playerWikiPresentationController;
        const reopened = presentationController && typeof presentationController.openDialog === "function"
          ? presentationController.openDialog(modalDialog, modalDialogTrigger)
          : false;
        if (!reopened) {
          modalDialog.open = true;
        }
      }
      if (restoreFocus) restoreFocus(root, snapshot.focusState);
      const restorationIntent = navigationIntent;
      window.requestAnimationFrame(() => {
        if (root !== getSectionContent() || restorationIntent !== navigationIntent) return;
        if (restoreViewportAnchor) {
          restoreViewportAnchor(root, snapshot.viewportAnchor);
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
      draftTransfers = [],
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
        draftTransfers,
        rollbackPublication: null,
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
      rollbackDraftTransfers(transition.draftTransfers);
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
      if (transition.rollbackPublication) transition.rollbackPublication();
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
        responsePanel,
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
            option.value = String(result.selection_value || result.entry_slug || "");
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

      const mountedContent = parsed.responseContent;
      const draftTransfers = [];
      try {
        section.replaceWith(mountedContent);
        restoreDrafts(mountedContent, draftSections.get(canonicalHref), draftTransfers);
        initPanelScriptForms(mountedContent);
      } catch (error) {
        rollbackDraftTransfers(draftTransfers);
        if (mountedContent.isConnected) mountedContent.replaceWith(section);
        throw error;
      }

      return {
        mode: parsed.responseMode,
        page: parsed.responseSubpage,
        href: canonicalHref,
        content: mountedContent,
        draftTransfers,
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

    // Mutations and navigation have separate lifetimes. A POST is never cancelled or
    // repeated by transport recovery; a later navigation always owns the visible pane.
    const pendingMutations = [];
    const draftSections = new Map();
    const fileIdentities = new WeakMap();
    let nextFileIdentity = 0;
    let activeMutation = null;
    let pausedMutation = null;
    let queuePaused = false;
    let accessBlocked = false;
    let navigationIntent = 0;
    let mutationEpoch = 0;
    let deferredNavigation = null;
    let knownRevision = getSectionContent()?.querySelector("input[name='expected_revision']")?.value || "";
    const characterPath = window.location.pathname;
    const initialCsrf = shellRoot.querySelector("input[name='_csrf_token']")?.value || "";
    const recovery = document.createElement("div");
    recovery.dataset.characterReadRecovery = "";
    recovery.setAttribute("role", "status");
    recovery.hidden = true;
    shellRoot.append(recovery);

    const formKey = (form) => JSON.stringify([
      form.getAttribute("action"),
      Array.from(form.querySelectorAll("input[type='hidden']"))
        .filter((field) => !["_csrf_token", "expected_revision"].includes(field.name))
        .map((field) => [field.name, field.value]),
      Array.from(form.querySelectorAll("input, textarea, select"))
        .filter((field) => isTrackableField(field) || field.type === "file")
        .map((field) => [field.name, field.type]),
    ]);
    const matchingForm = (root, key) => Array.from(root.querySelectorAll("form"))
      .find((form) => formKey(form) === key);
    const fieldValue = (field) => {
      if (field.type === "file") {
        return Array.from(field.files || []);
      }
      if (["checkbox", "radio"].includes(field.type)) {
        return field.checked;
      }
      if (field instanceof HTMLSelectElement) {
        return Array.from(field.selectedOptions).map((option) => option.value);
      }
      return field.value;
    };
    const sameValue = (left, right) => Array.isArray(left) && Array.isArray(right)
      ? left.length === right.length && left.every((value, index) => value === right[index])
      : left === right;
    const editableFields = (form) => Array.from(form.querySelectorAll("input, textarea, select"))
      .filter((field) => isTrackableField(field) || field.type === "file");
    const captureFormFields = (form) => editableFields(form).map((field) => ({
      field,
      name: field.name,
      type: field.type,
      index: editableFields(form).filter((other) => other.name === field.name && other.type === field.type)
        .indexOf(field),
      value: fieldValue(field),
    }));
    const isDirtyField = (field) => {
      if (field.type === "file") {
        return field.files.length > 0;
      }
      if (["checkbox", "radio"].includes(field.type)) {
        return field.checked !== field.defaultChecked;
      }
      if (field instanceof HTMLSelectElement) {
        const options = Array.from(field.options);
        if (field.multiple) {
          return options.some((option) => option.selected !== option.defaultSelected);
        }
        let defaultIndex = -1;
        options.forEach((option, index) => { if (option.defaultSelected) defaultIndex = index; });
        if (defaultIndex < 0 && field.size <= 1) {
          defaultIndex = options.findIndex((option) => !option.disabled && !option.closest("optgroup[disabled]"));
        }
        return field.selectedIndex !== defaultIndex;
      }
      return field.value !== field.defaultValue;
    };
    const captureDrafts = (section, acknowledged = null) => {
      if (!section) return [];
      return Array.from(section.querySelectorAll("form")).map((form) => {
        const key = formKey(form);
        const values = captureFormFields(form).filter((value) => {
          const queued = pendingMutations.findLast((intent) => intent.key === key);
          const reference = queued || (acknowledged?.key === key ? acknowledged : null)
            || (activeMutation?.key === key ? activeMutation : null);
          const submitted = reference?.fields.find((prior) => (
            prior.name === value.name && prior.type === value.type && prior.index === value.index
          ));
          // A queued submission is explicit intent, including an empty value or
          // a return to the original default. Keep the current value through the
          // earlier response so its paint cannot masquerade as a later user edit.
          if (queued && submitted) return true;
          if (!queued && reference === acknowledged && submitted && sameValue(submitted.value, value.value)) return false;
          return isDirtyField(value.field) || (submitted && !sameValue(submitted.value, value.value));
        });
        return { key, values };
      }).filter((draft) => draft.values.length);
    };
    const rollbackDraftTransfers = (transfers) => {
      for (const transfer of [...transfers].reverse()) {
        const { live, sourceParent, sourceNext, placeholder, targetParent, targetNext } = transfer;
        if (live.parentNode === targetParent) live.replaceWith(placeholder);
        if (!placeholder.parentNode) {
          targetParent.insertBefore(placeholder, targetNext?.parentNode === targetParent ? targetNext : null);
        }
        sourceParent.insertBefore(live, sourceNext?.parentNode === sourceParent ? sourceNext : null);
      }
      transfers.length = 0;
    };
    const restoreDrafts = (section, drafts, transfers) => {
      for (const draft of drafts || []) {
        const form = matchingForm(section, draft.key);
        if (!form) continue; // Never restore an editor removed by an access change.
        for (const value of draft.values) {
          const field = editableFields(form).filter((candidate) => (
            candidate.name === value.name && candidate.type === value.type
          ))[value.index];
          if (!field) continue;
          if (field.type === "file") {
            // Record both positions before moving a live input. Even a later
            // transfer or History failure must leave the retained form intact.
            transfers.push({
              live: value.field, sourceParent: value.field.parentNode, sourceNext: value.field.nextSibling,
              placeholder: field, targetParent: field.parentNode, targetNext: field.nextSibling,
            });
            field.replaceWith(value.field);
          } else if (["checkbox", "radio"].includes(field.type)) {
            field.checked = value.value;
          } else if (field instanceof HTMLSelectElement) {
            for (const option of field.options) option.selected = value.value.includes(option.value);
          } else {
            field.value = value.value;
          }
        }
      }
    };
    const rememberDrafts = (acknowledged = null) => {
      for (const [href, entry] of sectionMountedStateCache) {
        draftSections.set(href, captureDrafts(entry.section, acknowledged));
      }
      draftSections.set(getHistoryKey(window.location.href), captureDrafts(getSectionContent(), acknowledged));
    };
    const admitResponse = (parsed, response, { allowAction = false } = {}) => {
      if (!parsed || parsed.responseMode !== "read") return false;
      if (response.url) {
        const url = new URL(response.url, window.location.origin);
        if (url.origin !== window.location.origin || (
          url.pathname !== characterPath && !(allowAction && url.pathname.startsWith(`${characterPath}/`))
        )) return false;
      }
      const links = Array.from(parsed.responseNav.querySelectorAll("[data-character-read-subpage-link]"));
      if (!links.length || links.some((link) => {
        const url = new URL(link.getAttribute("href"), window.location.origin);
        return url.origin !== window.location.origin || url.pathname !== characterPath;
      })) return false;
      const csrf = parsed.responsePanel.querySelector("input[name='_csrf_token']")?.value || "";
      return !initialCsrf || !csrf || csrf === initialCsrf;
    };
    const responseRevision = (parsed) => {
      const revisions = new Set(Array.from(parsed.responsePanel.querySelectorAll("input[name='expected_revision']"))
        .map((field) => field.value).filter(Boolean));
      const value = revisions.size === 1 ? Array.from(revisions)[0] : "";
      return /^(0|[1-9][0-9]*)$/.test(value) && Number.isSafeInteger(Number(value)) ? value : "";
    };
    const showRecovery = (message) => {
      recovery.replaceChildren();
      const guidance = document.createElement("p");
      guidance.textContent = message;
      recovery.append(guidance);
      recovery.hidden = false;
      if (!knownRevision || accessBlocked) return;
      const addContinuation = (label, repeat) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.addEventListener("click", () => {
          if (activeMutation || !knownRevision || accessBlocked) return;
          if (repeat && pausedMutation) pendingMutations.unshift(pausedMutation);
          pausedMutation = null;
          queuePaused = false;
          recovery.hidden = true;
          void drainMutations();
        });
        recovery.append(button);
      };
      if (pausedMutation) addContinuation("Repeat submitted change", true);
      if (pendingMutations.length) addContinuation("Continue queued changes", false);
    };
    const stopForAccess = () => {
      accessBlocked = true;
      queuePaused = true;
      knownRevision = "";
      pendingMutations.length = 0;
      pausedMutation = null;
      draftSections.clear();
      sectionMountedStateCache.clear();
      getPanel().hidden = true;
      showRecovery("Character access could not be confirmed. Reload the page to sign in or check access before editing.");
    };
    const isProtectedConflict = (parsed, response, expectedHref) => {
      if (response.status !== 409
        || response.headers.get("X-Live-Mutation-Outcome") !== "character-revision-conflict"
        || !parsed || parsed.responseMode !== "read"
        || parsed.responsePanel.dataset.characterWriteConflict !== decodeURIComponent(characterPath.split("/").pop())) return false;
      const expected = new URL(expectedHref, window.location.origin);
      const actual = new URL(response.url || expectedHref, window.location.origin);
      return expected.origin === window.location.origin && actual.origin === window.location.origin
        && actual.pathname === expected.pathname
        && (actual.pathname === characterPath || actual.pathname.startsWith(`${characterPath}/`));
    };
    const pauseProtectedConflict = (parsed, intent = null, { mount = true } = {}) => {
      queuePaused = true;
      knownRevision = "";
      pausedMutation = intent;
      rememberDrafts();
      const queuedDrafts = [];
      const copyValue = (value) => ["checkbox", "radio"].includes(value.type)
        ? (value.value ? "Yes" : "No")
        : Array.isArray(value.value) ? value.value.join(", ") : String(value.value);
      const copied = new Set();
      // The helper already copies mounted fields; the response retains the
      // submitted server draft. Add only distinct detached/queued values.
      for (const root of [getPanel(), parsed.responsePanel]) {
        for (const field of root.querySelectorAll("textarea[name], input[name], select[name]")) {
          if (["hidden", "password", "file"].includes(field.type)) continue;
          copied.add(JSON.stringify([field.name, copyValue({ type: field.type, value: fieldValue(field) })]));
        }
      }
      const keepDraft = (value) => {
        if (["hidden", "password", "file"].includes(value.type)) return;
        const text = copyValue(value);
        const key = JSON.stringify([value.name, text]);
        if (copied.has(key)) return;
        copied.add(key);
        queuedDrafts.push({ name: value.name, label: value.name, value: text });
      };
      for (const drafts of draftSections.values()) {
        for (const draft of drafts) {
          for (const value of draft.values) keepDraft(value);
        }
      }
      for (const queued of [intent, ...pendingMutations].filter(Boolean)) {
        for (const value of queued.fields) keepDraft(value);
      }
      liveUiTools.appendCharacterRecoveryDrafts?.(getPanel(), parsed.responsePanel, queuedDrafts);
      sectionMountedStateCache.clear();
      for (const field of getPanel().querySelectorAll("input[name='expected_revision']")) field.value = "";
      if (mount) {
        getSectionContent().replaceWith(parsed.responseContent);
        reconcileCommonChrome(parsed);
        replaceFlashStack(parsed.flashStackHtml);
      }
      showRecovery("This Character is temporarily unavailable for updates. Your changes were not saved. Keep a copy of your draft, then refresh and review the Character. Queued changes are paused.");
      if (!mount) recovery.append(parsed.responseContent);
    };
    const mountMutationResponse = (parsed, href, acknowledged = null) => {
      const oldSection = getSectionContent();
      flushAutosubmits(oldSection);
      const mountedState = captureMountedState(oldSection);
      const drafts = captureDrafts(oldSection, acknowledged);
      const chrome = [getPanel().querySelector(".character-header"), getPanel().querySelector("[data-character-subpage-nav-card]"),
        getPanel().querySelector(".character-subpage-nav"), ...getPanelLinks()]
        .map((node) => ({ node, attributes: Array.from(node.attributes).map((attr) => [attr.name, attr.value]), children: Array.from(node.childNodes) }));
      const flashes = document.querySelector("[data-flash-stack-root]");
      const priorFlash = flashes?.innerHTML;
      const priorHistory = { href: window.location.href, state: window.history.state };
      const priorShell = getShellState();
      const priorCache = new Map(sectionMountedStateCache);
      const draftTransfers = [];
      try {
        oldSection.replaceWith(parsed.responseContent);
        initPanelScriptForms(parsed.responseContent);
        if (!reconcileCommonChrome(parsed)) throw new Error("Character chrome could not be mounted");
        restoreDrafts(parsed.responseContent, drafts, draftTransfers);
        replaceFlashStack(parsed.flashStackHtml);
        updateHistory({ href, replace: true });
        syncShellState(parseModeAndPageFromUrl(href));
        restoreMountedState(parsed.responseContent, mountedState, { restoreFieldValues: false });
        cacheSectionState(href, parsed.responseContent, null);
        return parsed.responseContent;
      } catch (error) {
        rollbackDraftTransfers(draftTransfers);
        if (parsed.responseContent.isConnected) parsed.responseContent.replaceWith(oldSection);
        for (const backup of chrome) {
          for (const attr of Array.from(backup.node.attributes)) backup.node.removeAttribute(attr.name);
          for (const [name, value] of backup.attributes) backup.node.setAttribute(name, value);
          backup.node.replaceChildren(...backup.children);
        }
        if (flashes) flashes.innerHTML = priorFlash;
        sectionMountedStateCache.clear();
        for (const [key, value] of priorCache) sectionMountedStateCache.set(key, value);
        window.history.replaceState(priorHistory.state, "", priorHistory.href);
        syncShellState(priorShell);
        restoreMountedState(oldSection, mountedState, { restoreFieldValues: false });
        // A safe reconciliation may complete before the next animation frame.
        // Restore the live anchor now so that read captures the same user focus.
        if (restoreViewportAnchor) restoreViewportAnchor(oldSection, mountedState.viewportAnchor);
        if (restoreFocus) restoreFocus(oldSection, mountedState.focusState);
        throw error;
      }
    };
    const reconcileCurrentSection = async () => {
      if (window._characterReadShellAbortController || mountedSectionTransition) return;
      const intent = navigationIntent;
      const href = getHistoryKey(window.location.href);
      try {
        const response = await fetch(href, {
          headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "text/html" },
          cache: "no-store", credentials: "same-origin",
        });
        const parsed = getResponseStateFromHtml(await response.text());
        if (isProtectedConflict(parsed, response, href)) {
          if (intent === navigationIntent && href === getHistoryKey(window.location.href)
            && !window._characterReadShellAbortController && !mountedSectionTransition) {
            pauseProtectedConflict(parsed);
          }
          return;
        }
        if ([401, 403].includes(response.status) || (parsed && !admitResponse(parsed, response))) {
          stopForAccess();
          return;
        }
        if (!response.ok || !admitResponse(parsed, response)) return;
        // Navigation and new drafts may have advanced while this one safe read ran.
        if (intent !== navigationIntent || href !== getHistoryKey(window.location.href)
          || window._characterReadShellAbortController || mountedSectionTransition) return;
        if (parsed.responseSubpage !== getShellState().subpage) return;
        const revision = responseRevision(parsed);
        if (revision && knownRevision && Number(revision) < Number(knownRevision)) return;
        mountMutationResponse(parsed, href);
        if (revision && (!knownRevision || Number(revision) >= Number(knownRevision))) knownRevision = revision;
      } catch (_error) {
        // One attempt only. A subsequent user-selected section is a new safe read.
      }
    };
    const pauseUnknownMutation = async (intent, { reconcile = true } = {}) => {
      mutationEpoch += 1;
      queuePaused = true;
      pausedMutation = intent;
      knownRevision = "";
      rememberDrafts();
      sectionMountedStateCache.clear();
      showRecovery("The save result could not be confirmed. Inspect the current sheet before repeating the action. Queued changes are paused.");
      if (reconcile) await reconcileCurrentSection();
      if (!accessBlocked) showRecovery("The save result could not be confirmed. Inspect the current sheet before repeating the action. Queued changes are paused.");
    };
    const fingerprintPayload = (payload) => JSON.stringify(Array.from(payload.entries())
      .filter(([name]) => name !== "expected_revision")
      .map(([name, value]) => {
        if (typeof value === "string") return [name, value];
        if (!value.size && !value.name) return [name, null];
        if (!fileIdentities.has(value)) fileIdentities.set(value, ++nextFileIdentity);
        return [name, fileIdentities.get(value)];
      }));
    const enqueueMutation = (form, submitter) => {
      if (accessBlocked) return;
      window.clearTimeout(Number(form.dataset.characterAutosubmitTimer || "0"));
      form.dataset.characterAutosubmitTimer = "0";
      const payload = buildSubmitPayload(form, submitter);
      const key = formKey(form);
      const fingerprint = fingerprintPayload(payload);
      const lastForForm = pendingMutations.findLast((intent) => intent.key === key)
        || (activeMutation?.key === key ? activeMutation : null);
      if (lastForForm?.fingerprint === fingerprint) return;
      form.dataset.characterAutosubmitState = buildAutosubmitFormState(form);
      pendingMutations.push({
        form, key, payload, fingerprint, fields: captureFormFields(form),
        action: new URL(form.getAttribute("action") || "", document.baseURI).href,
        href: getHistoryKey(window.location.href),
        navigationIntent, focusKey: String(form.dataset.postSubmitFocusKey || "").trim(),
      });
      if (queuePaused) showRecovery("Inspect the current sheet before repeating the action. Queued changes are paused.");
      void drainMutations();
    };
    const flushAutosubmits = (section) => {
      for (const form of section?.querySelectorAll("form[data-character-autosubmit]") || []) {
        if (Number(form.dataset.characterAutosubmitTimer || "0") && form.checkValidity()
          && buildAutosubmitFormState(form) !== form.dataset.characterAutosubmitState) {
          enqueueMutation(form, null);
        }
      }
    };
    const drainMutations = async () => {
      if (activeMutation || queuePaused || accessBlocked || !pendingMutations.length) return;
      const intent = pendingMutations.shift();
      activeMutation = intent;
      const form = intent.form;
      form.dataset.characterReadSubmitting = "1";
      form.setAttribute("aria-busy", "true");
      if (knownRevision && intent.payload.has("expected_revision")) intent.payload.set("expected_revision", knownRevision);
      mutationEpoch += 1;
      try {
        let response = await fetch(intent.action, {
          method: "POST", headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "text/html" },
          body: intent.payload, cache: "no-store", credentials: "same-origin",
        });
        const refresh = await retryBusyPostSaveRefresh(response, intent.href, intent.action);
        response = refresh.response;
        if (refresh.attempted && !window._characterReadShellAbortController) clearSubpageBusy();
        if (refresh.exhausted) {
          await pauseUnknownMutation(intent, { reconcile: false });
          showPostSaveRefreshUnavailable();
          return;
        }
        const parsed = getResponseStateFromHtml(await response.text());
        if (isProtectedConflict(parsed, response, intent.action)) {
          mutationEpoch += 1;
          pauseProtectedConflict(parsed, intent, { mount: intent.navigationIntent === navigationIntent
            && intent.href === getHistoryKey(window.location.href)
            && !window._characterReadShellAbortController && !mountedSectionTransition });
          return;
        }
        if ([401, 403].includes(response.status) || (parsed && !admitResponse(parsed, response, { allowAction: true }))) {
          stopForAccess();
          return;
        }
        const revision = parsed && responseRevision(parsed);
        const feedback = [400, 409, 422].includes(response.status) || (response.ok && parsed?.hasErrorFlash);
        const confirmed = response.ok && !feedback && admitResponse(parsed, response, { allowAction: true })
          && revision && Number(revision) > Number(intent.payload.get("expected_revision"));
        if (!admitResponse(parsed, response, { allowAction: true }) || !revision || (!feedback && !confirmed)) {
          await pauseUnknownMutation(intent);
          return;
        }
        knownRevision = revision;
        mutationEpoch += 1;
        const stillCurrent = intent.navigationIntent === navigationIntent
          && intent.href === getHistoryKey(window.location.href)
          && !window._characterReadShellAbortController;
        if (confirmed) {
          rememberDrafts(intent);
          sectionMountedStateCache.clear();
        }
        if (stillCurrent) {
          cancelActiveSubpageRequest();
          const href = buildCharacterReadHref({ mode: "read", page: parsed.responseSubpage, path: characterPath });
          mountMutationResponse(parsed, href, confirmed ? intent : null);
          if (intent.focusKey && restoreFocusKey) restoreFocusKey(getPanel(), intent.focusKey);
        }
        if (feedback) {
          queuePaused = true;
          pausedMutation = intent;
          if (!stillCurrent) replaceFlashStack(parsed.flashStackHtml);
          showRecovery("Review the validation or conflict feedback and current sheet before repeating the action. Queued changes are paused.");
        } else if (!stillCurrent && !window._characterReadShellAbortController) {
          // Read the chosen section, never paint the old POST's section or chrome.
          await reconcileCurrentSection();
        }
      } catch (_error) {
        await pauseUnknownMutation(intent);
      } finally {
        delete form.dataset.characterReadSubmitting;
        form.removeAttribute("aria-busy");
        activeMutation = null;
        if (!queuePaused) void drainMutations();
        resumeDeferredNavigation();
      }
    };
    const resumeDeferredNavigation = () => {
      if (!deferredNavigation || activeMutation || (!queuePaused && pendingMutations.length)) return;
      const navigation = deferredNavigation;
      deferredNavigation = null;
      void updateHistoryFromSubpage(navigation);
    };

    const updateHistoryFromSubpage = async ({ href, replaceHistory = false, fromHistory = false }) => {
      flushAutosubmits(getSectionContent());
      deferredNavigation = null;
      navigationIntent += 1;
      const readEpoch = mutationEpoch;
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
      let admittedMount = false;
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
        if (controller.signal.aborted) return;
        if (readEpoch !== mutationEpoch) {
          // A response read before a confirmed write cannot become current truth.
          // Keep the latest destination and fetch it once the writes settle.
          deferredNavigation = { href, replaceHistory, fromHistory };
          return;
        }
        const parsed = getResponseStateFromHtml(responseText);
        if (isProtectedConflict(parsed, response, targetState.href)) {
          pauseProtectedConflict(parsed);
          return;
        }
        if (parsed && !admitResponse(parsed, response)) {
          stopForAccess();
          return;
        }
        if ([401, 403].includes(response.status)) {
          stopForAccess();
          return;
        }
        if (parsed && (!activeMutation || queuePaused)) {
          const revision = responseRevision(parsed);
          if (revision && (!knownRevision || Number(revision) >= Number(knownRevision))) knownRevision = revision;
        }
        admittedMount = !!parsed;
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
          draftTransfers: switched.draftTransfers,
        });
        await waitForMountedContentSettlement();
        if (controller.signal.aborted || !isMountedSectionTransitionCurrent(transitionToken)) {
          rollbackMountedSectionTransition(controller);
          return;
        }
        if (readEpoch !== mutationEpoch) {
          rollbackMountedSectionTransition(controller);
          deferredNavigation = { href, replaceHistory, fromHistory };
          return;
        }
        // Keep the live-field journal and the visible publication recoverable
        // until chrome, History, shell metadata and cache all agree.
        const priorChrome = [getPanel().querySelector(".character-header"), getPanel().querySelector("[data-character-subpage-nav-card]"),
          getPanel().querySelector(".character-subpage-nav"), ...getPanelLinks()]
          .map((node) => ({ node, attributes: Array.from(node.attributes).map((attr) => [attr.name, attr.value]), children: Array.from(node.childNodes) }));
        const priorFlash = document.querySelector("[data-flash-stack-root]")?.innerHTML;
        const priorCache = new Map(sectionMountedStateCache);
        const priorHref = committedSnapshot?.href || getHistoryKey(window.location.href);
        const priorShell = parseModeAndPageFromUrl(priorHref);
        const priorHistory = getHistoryKey(window.location.href) === priorHref ? window.history.state : {
          characterReadMode: priorShell.mode, characterReadSubpage: priorShell.page, characterReadHref: priorHref,
        };
        mountedSectionTransition.rollbackPublication = () => {
          for (const backup of priorChrome) {
            for (const attr of Array.from(backup.node.attributes)) backup.node.removeAttribute(attr.name);
            for (const [name, value] of backup.attributes) backup.node.setAttribute(name, value);
            backup.node.replaceChildren(...backup.children);
          }
          replaceFlashStack(priorFlash);
          sectionMountedStateCache.clear();
          for (const [key, value] of priorCache) sectionMountedStateCache.set(key, value);
          window.history.replaceState(priorHistory, "", priorHref);
          syncShellState(priorShell);
        };
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
          showUnavailableAfterRequest = true;
          return;
        }

        const shellStateFromHref = getHistoryKey(switched.href);
        if (fromHistory || replaceHistory) {
          updateHistory({ href: shellStateFromHref, replace: true });
        } else {
          updateHistory({ href: shellStateFromHref, replace: false });
        }
        syncShellState(parseModeAndPageFromUrl(shellStateFromHref));
        cacheSectionState(shellStateFromHref, switched.content, null);
        draftSections.delete(shellStateFromHref);
        completeMountedSectionTransition(transitionToken);
      } catch (error) {
        rollbackMountedSectionTransition(controller);
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (admittedMount) {
          showUnavailableAfterRequest = true;
          return;
        }
        window.location.assign(targetState.href);
      } finally {
        clearSubpageBusy(controller);
        if (showUnavailableAfterRequest) {
          showSubpageUnavailable();
        }
        resumeDeferredNavigation();
        if (queuePaused && !accessBlocked) {
          showRecovery("Inspect the current sheet before repeating the action. Queued changes are paused.");
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
      const submitter = event.submitter instanceof HTMLElement ? event.submitter : null;
      enqueueMutation(form, submitter);
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
