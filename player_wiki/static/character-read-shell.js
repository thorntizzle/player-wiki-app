  (() => {
    const shellRoot = document.querySelector("[data-character-read-shell-root]");
    if (!shellRoot) {
      return;
    }

    const liveUiTools = window.__playerWikiLiveUiTools || {};
    const captureFocus = typeof liveUiTools.captureFocus === "function" ? liveUiTools.captureFocus : null;
    const restoreFocus = typeof liveUiTools.restoreFocus === "function" ? liveUiTools.restoreFocus : null;
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
    const getPanelLinks = () => Array.from(
      shellRoot.querySelectorAll("[data-character-read-subpage-link]"),
    );
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

    const getResponseStateFromHtml = (html) => {
      const parser = new DOMParser();
      const responseDocument = parser.parseFromString(html, "text/html");
      const responseShellRoot = responseDocument.querySelector("[data-character-read-shell-root]");
      const responsePanel = responseDocument.querySelector("[data-character-read-shell-panel]");
      const flashStack = responseDocument.querySelector("[data-flash-stack-root]");
      const hasErrorFlash = !!(flashStack && flashStack.querySelector(".flash-error"));
      if (!responseShellRoot || !responsePanel) {
        return null;
      }
      return {
        responsePanelHtml: responsePanel.innerHTML,
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

    const initialPanelState = getShellState();
    if (initialPanelState.mode !== "read") {
      return;
    }
    const initialState = makePanelSnapshotState(window.location.href);
    syncActiveNav(initialState.page);
    const panelMountedStateCache = new Map();
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
        for (const triggerTemplate of scope.querySelectorAll(
          "template[data-character-presentation-dialog-trigger-template]",
        )) {
          if (triggerTemplate instanceof HTMLTemplateElement) {
            triggerTemplate.replaceWith(triggerTemplate.content.cloneNode(true));
          }
        }
        presentationController.init(scope);
        const enabledSpellModalTrigger = Array.from(
          scope.querySelectorAll("[data-character-spell-modal-trigger][data-presentation-dialog-trigger]"),
        ).some((trigger) => trigger instanceof HTMLElement && !trigger.hidden);
        if (enabledSpellModalTrigger) {
          document.documentElement.classList.add("spell-modal-js");
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

    const makeSubmitState = (panel) => {
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
        mountedState: captureMountedState(panel),
      };
    };

    const cachePanelState = (stateKey, panelHtml, mountedState = null) => {
      panelMountedStateCache.set(stateKey, {
        panelHtml,
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

    const cacheCurrentPanel = () => {
      const panel = getPanel();
      if (!panel) {
        return;
      }
      const snapshot = makeSubmitState(panel);
      snapshot.mountedState = captureMountedState(panel);
      cachePanelState(snapshot.href, panel.innerHTML, snapshot.mountedState);
      return snapshot;
    };

    const updateHistory = ({ href, replace }) => {
      const canonical = getHistoryKey(href);
      const state = {
        characterReadMode: normalizeMode(shellRoot.dataset.characterReadShellMode || "read"),
        characterReadSubpage: normalizeSubpage(shellRoot.dataset.characterReadShellPage || "quick"),
        characterReadHref: canonical,
      };
      if (replace) {
        window.history.replaceState(state, "", canonical);
      } else {
        window.history.pushState(state, "", canonical);
      }
      return canonical;
    };

    const restoreFromCache = (stateHref) => {
      const state = panelMountedStateCache.get(stateHref);
      if (!state) {
        return false;
      }
      const panel = getPanel();
      if (!panel) {
        return false;
      }
      panel.innerHTML = state.panelHtml;
      syncShellState(parseModeAndPageFromUrl(stateHref));
      initPanelScriptForms(panel);
      restoreMountedState(panel, state.mountedState);
      return true;
    };

    const loadPanelFromResponseText = (responseText, responseHref, { fallbackPath = "" } = {}) => {
      const panel = getPanel();
      if (!panel) {
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

      panel.innerHTML = parsed.responsePanelHtml;
      replaceFlashStack(parsed.flashStackHtml);
      syncShellState({
        mode: parsed.responseMode,
        subpage: parsed.responseSubpage,
      });
      initPanelScriptForms(panel);

      return {
        mode: parsed.responseMode,
        page: parsed.responseSubpage,
        href: canonicalHref,
        html: parsed.responsePanelHtml,
        hasErrorFlash: !!parsed.hasErrorFlash,
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
      const currentPanelSnapshot = cacheCurrentPanel();
      const submittedMountedState = currentPanelSnapshot ? currentPanelSnapshot.mountedState : null;
      const payload = buildSubmitPayload(form, submitter);
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
        if (action) {
          window.location.assign(action);
        }
        return;
      }

      const responseText = await response.text();
      const shellState = getResponseStateFromHtml(responseText);
      if (!shellState) {
        window.location.assign(response.url || action);
        return;
      }

      const switched = loadPanelFromResponseText(responseText, response.url, {
        fallbackPath: window.location.pathname,
      });
      if (!switched) {
        window.location.assign(response.url || action);
        return;
      }
      const canonicalState = parseModeAndPageFromUrl(switched.href);
      cachePanelState(canonicalState.href, switched.html, null);
      updateHistory({
        href: canonicalState.href,
        replace: true,
      });
      const currentPanel = getPanel();
      if (currentPanel) {
        const currentMode = shellRoot.dataset.characterReadShellMode;
        if (currentMode !== "read") {
          window.location.assign(response.url || action);
          return;
        }
        restoreMountedState(currentPanel, submittedMountedState, {
          restoreFieldValues: !response.ok || !!switched.hasErrorFlash,
        });
      }
      if (canonicalState.href !== getHistoryKey(previousStateHref)) {
        cacheCurrentPanel();
      }
    };

    const updateHistoryFromSubpage = async ({ href, replaceHistory = false, fromHistory = false }) => {
      const targetState = parseModeAndPageFromUrl(href);
      const currentState = getShellState();
      if (currentState.mode === targetState.mode && currentState.subpage === targetState.page) {
        if (fromHistory || replaceHistory) {
          syncShellState(currentState);
          updateHistory({ href: targetState.href, replace: true });
        }
        return;
      }

      const targetKey = getHistoryKey(targetState.href);
      cacheCurrentPanel();
      if (restoreFromCache(targetKey)) {
        if (!fromHistory) {
          updateHistory({
            href: targetKey,
            replace: replaceHistory,
          });
        }
        return;
      }

      try {
        if (window._characterReadShellAbortController) {
          window._characterReadShellAbortController.abort();
        }
        const controller = new AbortController();
        window._characterReadShellAbortController = controller;
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
        const responseText = await response.text();
        const shellState = getResponseStateFromHtml(responseText);
        if (!shellState) {
          window.location.assign(targetState.href);
          return;
        }

        const switched = loadPanelFromResponseText(responseText, response.url, {
          fallbackPath: targetState.path,
        });
        if (!switched) {
          window.location.assign(targetState.href);
          return;
        }

        const shellStateFromHref = getHistoryKey(switched.href);
        cachePanelState(shellStateFromHref, switched.html, null);
        if (fromHistory || replaceHistory) {
          updateHistory({ href: shellStateFromHref, replace: true });
        } else {
          updateHistory({ href: shellStateFromHref, replace: false });
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        window.location.assign(targetState.href);
      } finally {
        if (window._characterReadShellAbortController && window._characterReadShellAbortController.signal.aborted) {
          window._characterReadShellAbortController = null;
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
      submitFormInPanel(form, submitter).catch(() => {
        if (action) {
          window.location.assign(action);
        }
      });
    };

    window.__playerWikiCharacterReadShell = {
      initPanelScriptForms,
      updateHistoryFromSubpage,
      syncActiveNav,
      toShellState: getShellState,
      cache: panelMountedStateCache,
    };

    cacheCurrentPanel();
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
