  (() => {
    const controllers = new WeakMap();
    const controllerSet = new Set();

    const initSessionLiveRoot = (liveRoot, { autoStart = true } = {}) => {
      if (!(liveRoot instanceof HTMLElement)) {
        return null;
      }
      if (controllers.has(liveRoot)) {
        return controllers.get(liveRoot);
      }

      const flashRoot = document.querySelector("[data-flash-stack-root]");
      let statusCard = liveRoot.querySelector("[data-session-status-card]");
      let chatCard = liveRoot.querySelector("[data-session-chat-card]");
      let composerRoot = liveRoot.querySelector("[data-session-composer-root]");
      let controlsRoot = liveRoot.querySelector("[data-session-controls-root]");
      let stagedRoot = liveRoot.querySelector("[data-session-staged-root]");
      let revealedRoot = liveRoot.querySelector("[data-session-revealed-root]");
      let articleStoreRoot = liveRoot.querySelector("[data-session-article-store-root]");
      let logsRoot = liveRoot.querySelector("[data-session-logs-root]");
      const pollUrl = liveRoot.dataset.sessionLiveUrl;
      const liveViewName = liveRoot.dataset.sessionLiveView || "session";
      const metricName = liveViewName === "dm" ? "session-dm" : "session";
      let activeSessionId = liveRoot.dataset.activeSessionId || "";
      let managerStateToken = liveRoot.dataset.sessionManagerStateToken || "";
      let liveRevision = Number.parseInt(liveRoot.dataset.liveRevision || "0", 10);
      if (!Number.isFinite(liveRevision) || liveRevision < 0) {
        liveRevision = 0;
      }
      let liveViewToken = liveRoot.dataset.liveViewToken || "";
      const activeIntervalMs = Number.parseInt(liveRoot.dataset.liveActiveIntervalMs || "3000", 10) || 3000;
      const idleIntervalMs = Number.parseInt(liveRoot.dataset.liveIdleIntervalMs || String(activeIntervalMs), 10) || activeIntervalMs;
      const idleThresholdMs = Number.parseInt(liveRoot.dataset.liveIdleThresholdMs || "30000", 10) || 30000;
      const diagnosticsEnabled = liveRoot.dataset.liveDiagnosticsEnabled === "1";
      const diagnosticsTools = diagnosticsEnabled ? window.__playerWikiLiveDiagnosticsTools : null;
      const uiStateTools = window.__playerWikiLiveUiTools || null;
      const presentationController = window.__playerWikiPresentationController || null;
      const sessionArticleSourceSearchResetters = new WeakMap();
      let pollTimerId = 0;
      let pollInFlight = false;
      let requestInFlight = false;
      let paused = false;
      let lastActivityAt = Date.now();

      const enclosingPane = () => liveRoot.closest("[data-session-shell-pane]");
      const isPaneHidden = () => {
        const pane = enclosingPane();
        return pane instanceof HTMLElement ? pane.hidden : false;
      };
      const isPaused = () => paused || isPaneHidden() || !pollUrl;

      const isHiddenDmRegion = (region) => {
        if (!(region instanceof HTMLElement)) {
          return false;
        }
        const pane = region.closest("[data-session-dm-pane]");
        return pane instanceof HTMLElement && pane.hidden;
      };

      const rebindRegions = () => {
        statusCard = liveRoot.querySelector("[data-session-status-card]");
        chatCard = liveRoot.querySelector("[data-session-chat-card]");
        composerRoot = liveRoot.querySelector("[data-session-composer-root]");
        controlsRoot = liveRoot.querySelector("[data-session-controls-root]");
        stagedRoot = liveRoot.querySelector("[data-session-staged-root]");
        revealedRoot = liveRoot.querySelector("[data-session-revealed-root]");
        articleStoreRoot = liveRoot.querySelector("[data-session-article-store-root]");
        logsRoot = liveRoot.querySelector("[data-session-logs-root]");
        initializeFileFields(stagedRoot || liveRoot);
        initializeFileFields(articleStoreRoot || liveRoot);
        initializeSessionArticleSourceSearch(articleStoreRoot || liveRoot);
      };

      const isSessionAsyncForm = (form) => (
        form instanceof HTMLFormElement
        && form.matches("[data-session-async], [data-destructive-confirmation-form]")
      );

      const initializePresentation = (root) => {
        if (
          (root instanceof Document || root instanceof Element)
          && presentationController
          && typeof presentationController.init === "function"
        ) {
          presentationController.init(root);
        }
      };

      const setDestructiveFormBusy = (form, isBusy) => {
        if (!(form instanceof HTMLFormElement) || !form.matches("[data-destructive-confirmation-form]")) {
          return;
        }
        form.setAttribute("aria-busy", isBusy ? "true" : "false");
      };

      const hideDestructiveRecovery = (form) => {
        const dialog = form instanceof Element
          ? form.closest("[data-destructive-confirmation-dialog]")
          : null;
        const recovery = dialog instanceof Element
          ? dialog.querySelector("[data-destructive-confirmation-recovery]")
          : null;
        if (recovery instanceof HTMLElement) {
          recovery.hidden = true;
        }
      };

      const showDestructiveRecovery = (form) => {
        const dialog = form instanceof Element
          ? form.closest("[data-destructive-confirmation-dialog]")
          : null;
        const recovery = dialog instanceof Element
          ? dialog.querySelector("[data-destructive-confirmation-recovery]")
          : null;
        if (recovery instanceof HTMLElement) {
          recovery.hidden = false;
          recovery.focus({ preventScroll: true });
        }
      };

      const hideArticleMutationRecovery = (form) => {
        const recovery = form instanceof Element
          ? form.querySelector("[data-session-article-mutation-recovery]")
          : null;
        if (recovery instanceof HTMLElement) {
          recovery.hidden = true;
        }
      };

      const showArticleMutationRecovery = (form) => {
        const recovery = form instanceof Element
          ? form.querySelector("[data-session-article-mutation-recovery]")
          : null;
        if (recovery instanceof HTMLElement) {
          recovery.hidden = false;
          recovery.focus({ preventScroll: true });
        }
      };

      const showMutationRecovery = (form) => {
        if (form instanceof HTMLFormElement && form.matches("[data-session-article-form]")) {
          showArticleMutationRecovery(form);
          return;
        }
        showDestructiveRecovery(form);
      };

      const markActivity = () => {
        lastActivityAt = Date.now();
      };

      const getNextPollDelay = () => {
        if (document.hidden) {
          return idleIntervalMs;
        }
        return Date.now() - lastActivityAt >= idleThresholdMs ? idleIntervalMs : activeIntervalMs;
      };

      const scheduleNextPoll = (delayMs = getNextPollDelay()) => {
        window.clearTimeout(pollTimerId);
        if (isPaused()) {
          pollTimerId = 0;
          return;
        }
        pollTimerId = window.setTimeout(() => {
          pollTimerId = 0;
          refreshLiveState();
        }, delayMs);
      };

      const syncLiveMetadata = (payload = {}, response = null) => {
        const payloadRevision = Number.parseInt(
          typeof payload.live_revision === "number" || typeof payload.live_revision === "string"
            ? String(payload.live_revision)
            : "",
          10,
        );
        if (Number.isFinite(payloadRevision) && payloadRevision >= 0) {
          liveRevision = payloadRevision;
        } else if (response instanceof Response) {
          const headerRevision = Number.parseInt(response.headers.get("X-Live-Revision") || "", 10);
          if (Number.isFinite(headerRevision) && headerRevision >= 0) {
            liveRevision = headerRevision;
          }
        }

        if (typeof payload.live_view_token === "string" && payload.live_view_token) {
          liveViewToken = payload.live_view_token;
        }

        liveRoot.dataset.liveRevision = String(liveRevision);
        liveRoot.dataset.liveViewToken = liveViewToken;
      };

      const buildLiveHeaders = () => {
        const headers = {
          "X-Requested-With": "XMLHttpRequest",
        };
        headers["X-Live-Revision"] = String(liveRevision);
        if (liveViewToken) {
          headers["X-Live-View-Token"] = liveViewToken;
        }
        return headers;
      };

      const logLiveDiagnostics = (viewName, response, payload = null) => {
        if (!diagnosticsEnabled || !(response instanceof Response) || typeof console === "undefined" || !console.debug) {
          return;
        }
        console.debug(`[live:${viewName}]`, {
          changed:
            typeof payload?.changed === "boolean"
              ? payload.changed
              : response.headers.get("X-Live-State-Changed"),
          revision: response.headers.get("X-Live-Revision") || liveRevision,
          payloadBytes: response.headers.get("X-Live-Payload-Bytes"),
          serverTiming: response.headers.get("Server-Timing"),
        });
      };

      const recordLiveMetric = (metric) => {
        if (!diagnosticsEnabled || !diagnosticsTools) {
          return metric;
        }
        return diagnosticsTools.recordMetric(metricName, metric);
      };

      const buildLiveMetric = (response, payload, { mode, requestMs = 0, applyMs = 0 } = {}) => {
        const headerChanged = response.headers.get("X-Live-State-Changed");
        const queryCount = Number.parseInt(response.headers.get("X-Live-Query-Count") || "0", 10);
        const queryTimeMs = Number.parseFloat(response.headers.get("X-Live-Query-Time-Ms") || "0");
        const requestTimeMs = Number.parseFloat(response.headers.get("X-Live-Request-Time-Ms") || "0");
        const payloadBytes = Number.parseInt(response.headers.get("X-Live-Payload-Bytes") || "0", 10);
        return recordLiveMetric({
          mode,
          changed: typeof payload?.changed === "boolean" ? payload.changed : headerChanged === "true",
          requestMs: Number(requestMs.toFixed(2)),
          applyMs: Number(applyMs.toFixed(2)),
          liveRevision,
          liveViewToken,
          payloadBytes: Number.isFinite(payloadBytes) ? payloadBytes : 0,
          queryCount: Number.isFinite(queryCount) ? queryCount : 0,
          queryTimeMs: Number.isFinite(queryTimeMs) ? Number(queryTimeMs.toFixed(2)) : 0,
          requestTimeMs: Number.isFinite(requestTimeMs) ? Number(requestTimeMs.toFixed(2)) : 0,
          serverTiming: response.headers.get("Server-Timing") || "",
        });
      };

      const hasFocusedFormControl = () => {
        const activeElement = document.activeElement;
        if (!activeElement || !liveRoot.contains(activeElement)) {
          return false;
        }
        const stagedEditForm = activeElement.closest("form.session-article-edit-form");
        const stagedState = window.__playerWikiSessionStagedState || null;
        if (
          stagedEditForm instanceof HTMLFormElement
          && stagedState
          && typeof stagedState.isDirtyEditForm === "function"
          && stagedState.isDirtyEditForm(stagedEditForm)
        ) {
          return false;
        }
        return activeElement.matches("input, textarea, select");
      };

      const updateFileFieldName = (field) => {
        const input = field.querySelector("[data-session-file-input]");
        const fileName = field.querySelector("[data-session-file-name]");
        if (!input || !fileName) {
          return;
        }
        const selectedFile = input.files && input.files.length ? input.files[0] : null;
        fileName.textContent = selectedFile ? selectedFile.name : "No file selected.";
      };

      const initializeFileField = (field) => {
        if (field.dataset.sessionFileInitialized === "1") {
          updateFileFieldName(field);
          return;
        }

        const input = field.querySelector("[data-session-file-input]");
        const dropzone = field.querySelector("[data-session-file-dropzone]");
        if (!input || !dropzone) {
          return;
        }

        const clearDragging = () => {
          dropzone.classList.remove("is-dragging");
        };

        dropzone.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") {
            return;
          }
          event.preventDefault();
          input.click();
        });
        dropzone.addEventListener("dragenter", (event) => {
          event.preventDefault();
          dropzone.classList.add("is-dragging");
        });
        dropzone.addEventListener("dragover", (event) => {
          event.preventDefault();
          dropzone.classList.add("is-dragging");
        });
        dropzone.addEventListener("dragleave", (event) => {
          if (dropzone.contains(event.relatedTarget)) {
            return;
          }
          clearDragging();
        });
        dropzone.addEventListener("drop", (event) => {
          event.preventDefault();
          clearDragging();
          const droppedFiles = event.dataTransfer && event.dataTransfer.files;
          if (!droppedFiles || !droppedFiles.length) {
            return;
          }
          const transfer = new DataTransfer();
          transfer.items.add(droppedFiles[0]);
          input.files = transfer.files;
          input.dispatchEvent(new Event("change", { bubbles: true }));
        });

        input.addEventListener("change", () => updateFileFieldName(field));
        field.dataset.sessionFileInitialized = "1";
        updateFileFieldName(field);
      };

      const initializeFileFields = (root = liveRoot) => {
        const fileFields = Array.from(root.querySelectorAll(".session-file-field"));
        for (const field of fileFields) {
          initializeFileField(field);
        }
      };

      const resetSessionArticleSourceSearch = (form) => {
        const resetter = sessionArticleSourceSearchResetters.get(form);
        if (typeof resetter === "function") {
          resetter();
        }
      };

      const initializeSessionArticleSourceSearch = (root = liveRoot) => {
        const forms = root instanceof HTMLFormElement
          ? [root]
          : Array.from(root.querySelectorAll("[data-session-article-form]"));

        for (const form of forms) {
          if (!(form instanceof HTMLFormElement)) {
            continue;
          }

          const searchInput = form.querySelector("[data-session-article-source-query]");
          const resultsSelect = form.querySelector("[data-session-article-source-results]");
          const status = form.querySelector("[data-session-article-source-status]");
          const searchUrl = form.dataset.sessionArticleSourceSearchUrl || "";
          const defaultMessage = "Type at least 2 letters to search published wiki pages and Systems entries.";

          if (
            !(searchInput instanceof HTMLInputElement)
            || !(resultsSelect instanceof HTMLSelectElement)
            || !(status instanceof HTMLElement)
            || !searchUrl
          ) {
            continue;
          }

          if (form.dataset.sessionArticleSourceSearchInitialized === "1") {
            continue;
          }

          let searchAbortController = null;
          let searchTimerId = 0;
          let searchRequestGeneration = 0;

          const setStatus = (message) => {
            status.textContent = message;
          };

          const resetResults = (message = defaultMessage) => {
            resultsSelect.innerHTML = "";
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "Search to load matching articles";
            resultsSelect.append(option);
            resultsSelect.disabled = true;
            setStatus(message);
          };

          const renderResults = (results, message) => {
            if (!Array.isArray(results) || !results.length) {
              resetResults(message || "No published wiki or Systems articles matched that search.");
              return;
            }

            resultsSelect.innerHTML = "";
            for (const result of results) {
              const option = document.createElement("option");
              option.value = String(result.source_ref || "");
              option.textContent = String(result.select_label || result.title || "");
              resultsSelect.append(option);
            }
            resultsSelect.disabled = false;
            resultsSelect.selectedIndex = 0;
            setStatus(message || `Found ${results.length} matching articles.`);
          };

          const runSearch = async (requestGeneration) => {
            if (requestGeneration !== searchRequestGeneration) {
              return;
            }
            const query = searchInput.value.trim();
            if (query.length < 2) {
              resetResults(defaultMessage);
              return;
            }

            setStatus("Searching published wiki pages and Systems entries...");
            const requestController = new AbortController();
            searchAbortController = requestController;
            try {
              const response = await fetch(`${searchUrl}?q=${encodeURIComponent(query)}`, {
                headers: {
                  "X-Requested-With": "XMLHttpRequest",
                  "Accept": "application/json",
                },
                cache: "no-store",
                credentials: "same-origin",
                signal: requestController.signal,
              });
              if (
                requestGeneration !== searchRequestGeneration
                || searchAbortController !== requestController
              ) {
                return;
              }
              if (!response.ok) {
                resetResults("Could not search article sources right now.");
                return;
              }

              const payload = await response.json();
              if (
                requestGeneration !== searchRequestGeneration
                || searchAbortController !== requestController
              ) {
                return;
              }
              renderResults(payload.results, typeof payload.message === "string" ? payload.message : "");
            } catch (error) {
              if (error instanceof DOMException && error.name === "AbortError") {
                return;
              }
              if (
                requestGeneration === searchRequestGeneration
                && searchAbortController === requestController
              ) {
                resetResults("Could not search article sources right now.");
              }
            } finally {
              if (searchAbortController === requestController) {
                searchAbortController = null;
              }
            }
          };

          searchInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
              event.preventDefault();
            }
          });
          searchInput.addEventListener("input", () => {
            window.clearTimeout(searchTimerId);
            searchRequestGeneration += 1;
            const queuedGeneration = searchRequestGeneration;
            if (searchAbortController) {
              searchAbortController.abort();
              searchAbortController = null;
            }
            if (searchInput.value.trim().length < 2) {
              resetResults(defaultMessage);
              return;
            }
            searchTimerId = window.setTimeout(() => runSearch(queuedGeneration), 250);
          });

          sessionArticleSourceSearchResetters.set(form, () => {
            searchRequestGeneration += 1;
            if (searchAbortController) {
              searchAbortController.abort();
              searchAbortController = null;
            }
            window.clearTimeout(searchTimerId);
            searchInput.value = "";
            resetResults(defaultMessage);
          });
          form.dataset.sessionArticleSourceSearchInitialized = "1";
          resetResults(defaultMessage);
        }
      };

      const clearSessionArticleForm = (form) => {
        const selectedMode = form.querySelector('input[name="article_mode"]:checked')?.value || "manual";
        form.reset();
        const selectedRadio = form.querySelector(`input[name="article_mode"][value="${selectedMode}"]`);
        if (selectedRadio) {
          selectedRadio.checked = true;
        }
        initializeFileFields(form);
        resetSessionArticleSourceSearch(form);
      };

      const scrollToAnchor = (anchor) => {
        if (!anchor) {
          return;
        }
        const target = document.getElementById(anchor);
        if (target) {
          target.scrollIntoView({ block: "start" });
        }
      };

      const collectOpenSessionArticleIds = (root) => {
        if (!(root instanceof HTMLElement)) {
          return [];
        }
        return Array.from(root.querySelectorAll("details[data-session-article-id][open]"))
          .map((detail) => detail.dataset.sessionArticleId || "")
          .filter(Boolean);
      };

      const restoreOpenSessionArticleIds = (root, openIds) => {
        if (!(root instanceof HTMLElement) || !openIds.size) {
          return;
        }
        for (const detail of root.querySelectorAll("details[data-session-article-id]")) {
          const articleId = detail.dataset.sessionArticleId || "";
          if (openIds.has(articleId)) {
            detail.open = true;
          }
        }
      };

      const renderSessionFormFeedback = (form, feedbackHtml) => {
        if (!(form instanceof HTMLFormElement) || typeof feedbackHtml !== "string") {
          return;
        }
        const feedbackRoot = form.querySelector("[data-session-form-feedback]");
        if (!(feedbackRoot instanceof HTMLElement)) {
          return;
        }
        feedbackRoot.innerHTML = feedbackHtml;
        for (const feedback of feedbackRoot.querySelectorAll("[data-feedback]")) {
          feedback.dataset.feedbackPlacement = "persistent";
          feedback.classList.remove("feedback--transient");
          feedback.classList.add("feedback--persistent");
        }
        form.setAttribute("aria-invalid", "true");
      };

      const restoreComposerFocus = () => {
        if (!(composerRoot instanceof HTMLElement)) {
          return;
        }
        const nextComposerField = composerRoot.querySelector(
          "[data-session-composer-form] textarea[name='body']",
        );
        if (nextComposerField instanceof HTMLElement) {
          nextComposerField.focus({ preventScroll: true });
        }
      };

      const renderPayload = (payload, {
        forceManager = false,
        forceComposer = false,
        preserveComposer = false,
        forceFlash = false,
        sessionFeedbackForm = null,
        suppressAnchor = false,
        ignoreDirtyStagedArticleIds = [],
      } = {}) => {
        const focusState = uiStateTools ? uiStateTools.captureFocus(liveRoot) : null;
        const viewportAnchor = uiStateTools ? uiStateTools.captureViewportAnchor(liveRoot) : null;
        const openSessionArticleIds = new Set([
          ...collectOpenSessionArticleIds(stagedRoot),
          ...collectOpenSessionArticleIds(revealedRoot),
        ]);

        if (statusCard && !isHiddenDmRegion(statusCard) && typeof payload.status_html === "string") {
          statusCard.innerHTML = payload.status_html;
        }
        if (chatCard && typeof payload.chat_html === "string") {
          chatCard.innerHTML = payload.chat_html;
        }

        const nextActiveSessionId = payload.active_session_id ? String(payload.active_session_id) : "";
        const nextManagerStateToken = payload.manager_state_token ? String(payload.manager_state_token) : "";
        const sessionChanged = nextActiveSessionId !== activeSessionId;
        const managerChanged = nextManagerStateToken !== managerStateToken;

        if (
          !preserveComposer
          && (sessionChanged || forceComposer)
          && composerRoot
          && !isHiddenDmRegion(composerRoot)
          && typeof payload.composer_html === "string"
        ) {
          composerRoot.innerHTML = payload.composer_html;
        }
        if ((sessionChanged || managerChanged || forceManager) && controlsRoot && !isHiddenDmRegion(controlsRoot) && typeof payload.controls_html === "string") {
          controlsRoot.innerHTML = payload.controls_html;
          statusCard = liveRoot.querySelector("[data-session-status-card]");
        }
        if ((sessionChanged || managerChanged || forceManager) && stagedRoot && !isHiddenDmRegion(stagedRoot) && typeof payload.staged_articles_html === "string") {
          const stagedState = window.__playerWikiSessionStagedState || null;
          if (stagedState && typeof stagedState.replaceHtml === "function") {
            stagedState.replaceHtml(stagedRoot, payload.staged_articles_html, {
              ignoreDirtyArticleIds: ignoreDirtyStagedArticleIds,
            });
          } else {
            stagedRoot.innerHTML = payload.staged_articles_html;
          }
        }
        if ((sessionChanged || managerChanged || forceManager) && revealedRoot && !isHiddenDmRegion(revealedRoot) && typeof payload.revealed_articles_html === "string") {
          revealedRoot.innerHTML = payload.revealed_articles_html;
          initializePresentation(revealedRoot);
        }
        if ((sessionChanged || managerChanged || forceManager) && logsRoot && !isHiddenDmRegion(logsRoot) && typeof payload.logs_html === "string") {
          logsRoot.innerHTML = payload.logs_html;
        }

        initializeFileFields(stagedRoot || liveRoot);
        initializeFileFields(revealedRoot || liveRoot);
        restoreOpenSessionArticleIds(stagedRoot, openSessionArticleIds);
        restoreOpenSessionArticleIds(revealedRoot, openSessionArticleIds);

        if (forceFlash && flashRoot && typeof payload.flash_html === "string") {
          flashRoot.innerHTML = payload.flash_html;
        }
        if (sessionFeedbackForm instanceof HTMLFormElement) {
          if (flashRoot) {
            flashRoot.innerHTML = "";
          }
          renderSessionFormFeedback(sessionFeedbackForm, payload.flash_html);
        }

        activeSessionId = nextActiveSessionId;
        managerStateToken = nextManagerStateToken;
        liveRoot.dataset.activeSessionId = activeSessionId;
        liveRoot.dataset.sessionManagerStateToken = managerStateToken;
        if (sessionChanged) {
          liveRoot.dispatchEvent(new CustomEvent("playerWiki:session-state-changed", {
            bubbles: true,
            detail: {
              activeSessionId,
              managerStateToken,
            },
          }));
        }
        if (managerChanged) {
          liveRoot.dispatchEvent(new CustomEvent("playerWiki:session-manager-state-changed", {
            bubbles: true,
            detail: {
              activeSessionId,
              managerStateToken,
            },
          }));
        }
        if (uiStateTools) {
          uiStateTools.restoreFocus(liveRoot, focusState);
          uiStateTools.restoreViewportAnchor(liveRoot, viewportAnchor);
        }
        if (!suppressAnchor) {
          scrollToAnchor(payload.anchor || "");
        }
      };

      const refreshLiveState = async ({
        forceManager = false,
        forceComposer = false,
        allowShortCircuit = true,
        bypassGuards = false,
        reschedule = true,
        mode = allowShortCircuit ? "steady" : "cold",
      } = {}) => {
        if (isPaused()) {
          return;
        }
        if (!bypassGuards && (pollInFlight || requestInFlight || document.hidden || hasFocusedFormControl())) {
          if (reschedule) {
            scheduleNextPoll();
          }
          return;
        }

        pollInFlight = true;
        liveRoot.dataset.loading = "1";
        try {
          const requestStartedAt = performance.now();
          const response = await fetch(pollUrl, {
            headers: allowShortCircuit ? buildLiveHeaders() : { "X-Requested-With": "XMLHttpRequest" },
            cache: "no-store",
            credentials: "same-origin",
          });
          if (!response.ok) {
            return;
          }

          const payload = await response.json();
          syncLiveMetadata(payload, response);
          logLiveDiagnostics(`session-${liveViewName}`, response, payload);
          const requestMs = performance.now() - requestStartedAt;
          if (payload && payload.changed === false) {
            return buildLiveMetric(response, payload, { mode, requestMs, applyMs: 0 });
          }
          const applyStartedAt = performance.now();
          renderPayload(payload, { forceManager, forceComposer });
          return buildLiveMetric(response, payload, {
            mode,
            requestMs,
            applyMs: performance.now() - applyStartedAt,
          });
        } catch (_) {
          return;
        } finally {
          pollInFlight = false;
          liveRoot.dataset.loading = "0";
          if (reschedule) {
            scheduleNextPoll();
          }
        }
      };

      const handleSubmit = async (event) => {
        const form = event.target;
        if (!isSessionAsyncForm(form) || !liveRoot.contains(form)) {
          return;
        }

        event.preventDefault();
        const confirmMessage = form.dataset.sessionConfirm;
        if (typeof confirmMessage === "string" && confirmMessage.trim()) {
          if (!window.confirm(confirmMessage)) {
            return;
          }
        }
        if (requestInFlight) {
          return;
        }

        requestInFlight = true;
        markActivity();
        hideDestructiveRecovery(form);
        hideArticleMutationRecovery(form);
        setDestructiveFormBusy(form, true);
        if (!form.matches("[data-destructive-confirmation-form]")) {
          form.setAttribute("aria-busy", "true");
        }
        const buttons = Array.from(form.querySelectorAll("button, input[type='submit']"));
        const submittingArticleDetail = form.closest("details[data-session-article-id]");
        const submittingArticleId = submittingArticleDetail instanceof HTMLElement
          ? String(submittingArticleDetail.dataset.sessionArticleId || "")
          : "";
        for (const button of buttons) {
          button.disabled = true;
        }

        try {
          const response = await fetch(form.action, {
            method: (form.method || "POST").toUpperCase(),
            headers: {
              "X-Requested-With": "XMLHttpRequest",
              "Accept": "application/json",
            },
            body: new FormData(form),
            credentials: "same-origin",
          });
          if (!response.ok) {
            showMutationRecovery(form);
            return;
          }

          const payload = await response.json();
          if (!payload || typeof payload !== "object" || typeof payload.ok !== "boolean") {
            showMutationRecovery(form);
            return;
          }
          syncLiveMetadata(payload, response);
          logLiveDiagnostics(`session-${liveViewName}-mutation`, response, payload);
          const isComposerForm = form.matches("[data-session-composer-form]");
          const composerValidationFailed = isComposerForm && payload.ok === false;
          const destructiveValidationFailed = form.matches("[data-destructive-confirmation-form]")
            && payload.ok === false;
          const articleValidationFailed = form.matches("[data-session-article-form]")
            && payload.ok === false;
          if (articleValidationFailed) {
            form.dataset.sessionArticleValidationRetained = "1";
          } else if (payload.ok === true && form.matches("[data-session-article-form]")) {
            delete form.dataset.sessionArticleValidationRetained;
          }
          renderPayload(payload, {
            forceManager: true,
            forceComposer: !composerValidationFailed,
            preserveComposer: composerValidationFailed,
            forceFlash: !composerValidationFailed,
            sessionFeedbackForm: composerValidationFailed ? form : null,
            suppressAnchor: composerValidationFailed || destructiveValidationFailed,
            ignoreDirtyStagedArticleIds: payload.ok && submittingArticleId
              ? [submittingArticleId]
              : [],
          });
          if (isComposerForm && payload.ok === true) {
            restoreComposerFocus();
          }
          if (payload.ok && form.matches("[data-session-article-form]")) {
            clearSessionArticleForm(form);
          }
        } catch (_) {
          showMutationRecovery(form);
          return;
        } finally {
          requestInFlight = false;
          setDestructiveFormBusy(form, false);
          if (!form.matches("[data-destructive-confirmation-form]")) {
            form.removeAttribute("aria-busy");
          }
          for (const button of buttons) {
            button.disabled = false;
          }
          scheduleNextPoll(activeIntervalMs);
        }
      };

      const pause = () => {
        paused = true;
        window.clearTimeout(pollTimerId);
        pollTimerId = 0;
        liveRoot.dataset.sessionLivePaused = "1";
        liveRoot.dataset.loading = "0";
      };

      const resume = ({ refresh = true } = {}) => {
        paused = false;
        liveRoot.dataset.sessionLivePaused = "0";
        markActivity();
        if (refresh) {
          refreshLiveState({ forceManager: true, forceComposer: true });
        } else {
          scheduleNextPoll(0);
        }
      };

      initializeFileFields();
      initializeSessionArticleSourceSearch();
      initializePresentation(revealedRoot || liveRoot);
      liveRoot.addEventListener("submit", handleSubmit);
      ["pointerdown", "keydown", "input", "focusin"].forEach((eventName) => {
        liveRoot.addEventListener(eventName, markActivity, true);
      });
      window.addEventListener("pageshow", () => {
        if (isPaused()) {
          return;
        }
        markActivity();
        refreshLiveState({ forceManager: true, forceComposer: true });
      });
      document.addEventListener("visibilitychange", () => {
        if (isPaused()) {
          return;
        }
        if (!document.hidden) {
          markActivity();
          refreshLiveState({ forceManager: true, forceComposer: true });
          return;
        }
        scheduleNextPoll(idleIntervalMs);
      });
      if (diagnosticsEnabled && diagnosticsTools) {
        diagnosticsTools.ensureMetricsStore();
        diagnosticsTools.registerSampler(metricName, async (options = {}) => {
          const requestedMode = options && options.mode === "cold" ? "cold" : "steady";
          return refreshLiveState({
            forceManager: Boolean(options.forceManager),
            forceComposer: Boolean(options.forceComposer),
            allowShortCircuit: requestedMode !== "cold",
            bypassGuards: true,
            reschedule: false,
            mode: requestedMode,
          });
        });
      }

      const controller = {
        root: liveRoot,
        pause,
        resume,
        refresh: refreshLiveState,
        rebindRegions,
      };
      controllers.set(liveRoot, controller);
      controllerSet.add(controller);
      if (autoStart) {
        if (isPaneHidden()) {
          pause();
        } else {
          resume();
        }
      }
      return controller;
    };

    const init = (root = document, options = {}) => {
      const roots = root instanceof HTMLElement && root.matches("[data-session-live-root]")
        ? [root]
        : Array.from(root.querySelectorAll("[data-session-live-root]"));
      for (const liveRoot of roots) {
        initSessionLiveRoot(liveRoot, options);
      }
    };

    const activatePane = (pane) => {
      if (!(pane instanceof HTMLElement)) {
        return;
      }
      const shellRoot = pane.closest("[data-session-shell-root]");
      const scope = shellRoot || document;
      const roots = Array.from(scope.querySelectorAll("[data-session-live-root]"));
      for (const liveRoot of roots) {
        const controller = initSessionLiveRoot(liveRoot, { autoStart: false });
        if (!controller) {
          continue;
        }
        if (pane.contains(liveRoot) && !pane.hidden) {
          controller.resume();
        } else {
          controller.pause();
        }
      }
    };

    const rebindRegions = (liveRoot) => {
      if (!(liveRoot instanceof HTMLElement)) {
        return;
      }
      const controller = initSessionLiveRoot(liveRoot, { autoStart: false });
      if (controller && typeof controller.rebindRegions === "function") {
        controller.rebindRegions();
      }
    };

    window.__playerWikiSessionLive = {
      init,
      activatePane,
      rebindRegions,
    };

    const activePane = document.querySelector("[data-session-shell-root] [data-session-shell-pane]:not([hidden])");
    init(document, { autoStart: !(activePane instanceof HTMLElement) });
    if (activePane instanceof HTMLElement) {
      activatePane(activePane);
    }
  })();
