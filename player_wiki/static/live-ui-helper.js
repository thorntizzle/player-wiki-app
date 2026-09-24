  (() => {
    if (window.__playerWikiLiveUiTools) {
      return;
    }

    const anchorSelector = [
      "[id]",
      "[data-live-builder-region]",
      "[data-session-article-id]",
      "[data-combatant-id]",
    ].join(", ");

    const escapeSelectorValue = (value) => {
      const text = String(value || "");
      if (window.CSS && typeof window.CSS.escape === "function") {
        return window.CSS.escape(text);
      }
      return text.replace(/["\\]/g, "\\$&");
    };

    const findAnchorNode = (root, descriptor) => {
      if (!(root instanceof HTMLElement) || !descriptor || !descriptor.kind || !descriptor.value) {
        return null;
      }
      if (descriptor.kind === "id") {
        return root.querySelector(`#${escapeSelectorValue(descriptor.value)}`);
      }
      if (descriptor.kind === "attr" && descriptor.attribute) {
        return root.querySelector(`[${descriptor.attribute}="${escapeSelectorValue(descriptor.value)}"]`);
      }
      return null;
    };

    const describeAnchorNode = (node) => {
      if (!(node instanceof HTMLElement)) {
        return null;
      }
      if (node.id) {
        return { kind: "id", value: node.id };
      }
      for (const attribute of [
        "data-live-builder-region",
        "data-session-article-id",
        "data-combatant-id",
      ]) {
        const value = node.getAttribute(attribute);
        if (value) {
          return { kind: "attr", attribute, value };
        }
      }
      return null;
    };

    const describeForm = (root, form) => {
      if (!(root instanceof HTMLElement) || !(form instanceof HTMLFormElement)) {
        return null;
      }
      const descriptor = {
        method: String(form.getAttribute("method") || "get").toLowerCase(),
        action: String(form.getAttribute("action") || ""),
      };
      if (form.id) {
        descriptor.id = form.id;
        return descriptor;
      }
      const matchingForms = Array.from(root.querySelectorAll("form")).filter((candidate) => {
        if (!(candidate instanceof HTMLFormElement)) {
          return false;
        }
        return (
          String(candidate.getAttribute("method") || "get").toLowerCase() === descriptor.method
          && String(candidate.getAttribute("action") || "") === descriptor.action
        );
      });
      const index = matchingForms.indexOf(form);
      if (index >= 0) {
        descriptor.index = index;
      }
      return descriptor;
    };

    const findMatchingForm = (root, descriptor) => {
      if (!(root instanceof HTMLElement) || !descriptor || typeof descriptor !== "object") {
        return null;
      }
      if (descriptor.id) {
        const target = root.querySelector(`#${escapeSelectorValue(descriptor.id)}`);
        if (target instanceof HTMLFormElement) {
          return target;
        }
      }
      const matchingForms = Array.from(root.querySelectorAll("form")).filter((candidate) => {
        if (!(candidate instanceof HTMLFormElement)) {
          return false;
        }
        return (
          String(candidate.getAttribute("method") || "get").toLowerCase() === String(descriptor.method || "get").toLowerCase()
          && String(candidate.getAttribute("action") || "") === String(descriptor.action || "")
        );
      });
      if (!matchingForms.length) {
        return null;
      }
      const index = Number.isInteger(descriptor.index) ? descriptor.index : 0;
      return matchingForms[Math.min(Math.max(index, 0), matchingForms.length - 1)] || null;
    };

    const captureFocus = (root) => {
      const active = document.activeElement;
      if (!(root instanceof HTMLElement) || !(active instanceof HTMLElement) || !root.contains(active)) {
        return null;
      }
      const focusKey = String(active.dataset.liveFocusKey || "").trim();
      const name = String(active.getAttribute("name") || "").trim();
      if (!focusKey && !name) {
        return null;
      }
      const focusState = { name, focusKey };
      focusState.node = active;
      const form = active.closest("form");
      if (form instanceof HTMLFormElement) {
        focusState.form = describeForm(root, form);
      }
      if (typeof active.selectionStart === "number" && typeof active.selectionEnd === "number") {
        focusState.selectionStart = active.selectionStart;
        focusState.selectionEnd = active.selectionEnd;
        focusState.selectionDirection = active.selectionDirection;
      }
      return focusState;
    };

    const restoreFocus = (root, focusState) => {
      if (!(root instanceof HTMLElement) || !focusState) {
        return;
      }
      // An untouched control already owns its selection and native IME session.
      if (focusState.node?.isConnected && document.activeElement === focusState.node) return;
      const focusKey = String(focusState.focusKey || "").trim();
      if (focusKey) {
        const keyedTarget = root.querySelector(
          `[data-live-focus-key="${escapeSelectorValue(focusKey)}"]`,
        );
        if (
          keyedTarget instanceof HTMLElement
          && !keyedTarget.hasAttribute("disabled")
          && keyedTarget.getAttribute("aria-disabled") !== "true"
          && !keyedTarget.hidden
        ) {
          keyedTarget.focus({ preventScroll: true });
          return;
        }
      }
      if (!focusState.name) {
        return;
      }
      const fieldRoot = findMatchingForm(root, focusState.form) || root;
      const field = fieldRoot.querySelector(`[name="${escapeSelectorValue(focusState.name)}"]`);
      if (!(field instanceof HTMLElement)) {
        return;
      }
      if (typeof field.focus === "function") {
        field.focus({ preventScroll: true });
      }
      if (
        typeof focusState.selectionStart === "number"
        && typeof field.setSelectionRange === "function"
      ) {
        field.setSelectionRange(
          focusState.selectionStart,
          focusState.selectionEnd ?? focusState.selectionStart,
          focusState.selectionDirection || "none",
        );
      }
    };

    const restoreFocusKey = (root, focusKey) => {
      const normalizedFocusKey = String(focusKey || "").trim();
      if (!normalizedFocusKey) {
        return false;
      }
      const target = root instanceof HTMLElement
        ? root.querySelector(`[data-live-focus-key="${escapeSelectorValue(normalizedFocusKey)}"]`)
        : null;
      if (
        !(target instanceof HTMLElement)
        || target.hasAttribute("disabled")
        || target.getAttribute("aria-disabled") === "true"
        || target.hidden
      ) {
        return false;
      }
      target.focus({ preventScroll: true });
      return true;
    };

    const interactionSpacing = new Map();
    document.addEventListener("focusout", () => queueMicrotask(() => {
      for (const [form, spacing] of interactionSpacing) {
        if (form.contains(document.activeElement)) continue;
        form.style.paddingTop = spacing.original;
        interactionSpacing.delete(form);
      }
    }));

    const captureViewportAnchor = (root, { interaction = false } = {}) => {
      if (!(root instanceof HTMLElement)) {
        return {
          descriptor: null,
          top: 0,
          scrollY: window.scrollY,
        };
      }
      const active = document.activeElement;
      if (interaction && active instanceof HTMLElement && root.contains(active)
        && active.matches("input, textarea, select, [contenteditable=true]")
        && active.getClientRects().length > 0) {
        return { node: active, top: active.getBoundingClientRect().top, scrollY: window.scrollY };
      }
      const viewportTop = 84;
      const viewportBottom = Math.max(viewportTop + 1, window.innerHeight);
      for (const candidate of root.querySelectorAll(anchorSelector)) {
        const descriptor = describeAnchorNode(candidate);
        if (!descriptor) {
          continue;
        }
        const rect = candidate.getBoundingClientRect();
        if (rect.bottom <= viewportTop || rect.top >= viewportBottom) {
          continue;
        }
        return {
          descriptor,
          top: rect.top,
          scrollY: window.scrollY,
        };
      }
      return {
        descriptor: null,
        top: 0,
        scrollY: window.scrollY,
      };
    };

    const restoreViewportAnchor = (root, anchorState) => {
      if (!anchorState) {
        return;
      }
      if (anchorState.node?.isConnected && root.contains(anchorState.node)) {
        const target = anchorState.node;
        let delta = target.getBoundingClientRect().top - anchorState.top;
        if (Math.abs(delta) <= 1) return;
        window.scrollTo(window.scrollX, Math.max(0, window.scrollY + delta));
        delta = target.getBoundingClientRect().top - anchorState.top;
        const form = target.closest("form");
        // A shrinking page can hit scroll zero. Keep the retained interaction in
        // place with local spacing until focus leaves, using existing events.
        if (form && delta < -1) {
          const spacing = interactionSpacing.get(form) || {
            original: form.style.paddingTop,
            value: Number.parseFloat(getComputedStyle(form).paddingTop) || 0,
          };
          spacing.value -= delta;
          interactionSpacing.set(form, spacing);
          form.style.paddingTop = `${spacing.value}px`;
        }
        return;
      }
      if (anchorState.descriptor && root instanceof HTMLElement) {
        const target = findAnchorNode(root, anchorState.descriptor);
        if (target instanceof HTMLElement) {
          const delta = target.getBoundingClientRect().top - Number(anchorState.top || 0);
          if (Number.isFinite(delta) && Math.abs(delta) > 1) {
            window.scrollTo(window.scrollX, Math.max(0, window.scrollY + delta));
          }
          return;
        }
      }
      const scrollY = Number(anchorState.scrollY || 0);
      if (Number.isFinite(scrollY)) {
        window.scrollTo(window.scrollX, Math.max(0, scrollY));
      }
    };

    const createAsyncPolicy = (root, options = {}) => {
      if (!(root instanceof HTMLElement)) {
        return null;
      }

      const activeIntervalMs = Math.max(1, Number(options.activeIntervalMs) || 3000);
      const idleIntervalMs = Math.max(1, Number(options.idleIntervalMs) || activeIntervalMs);
      const idleThresholdMs = Math.max(1, Number(options.idleThresholdMs) || 30000);
      const readErrorMessage = String(
        options.readErrorMessage || "Live Session updates are unavailable. Current content is still shown.",
      );
      const offlineMessage = String(
        options.offlineMessage || "Live Session updates are paused while you are offline.",
      );
      const updatedMessage = String(options.updatedMessage || "Session updated.");
      const readStatus = root.querySelector("[data-live-read-status]");
      const readStatusMessage = root.querySelector("[data-live-read-status-message]");
      const safeReadRetry = root.querySelector("[data-live-safe-read-retry]");
      const safeReadRetryContainer = safeReadRetry instanceof HTMLElement
        ? safeReadRetry.closest("[data-live-safe-read-retry-container]")
        : null;
      const announcement = root.querySelector("[data-live-read-announcement]");
      let readSequence = 0;
      let currentRead = null;
      let mutationSequence = 0;
      let announcementSequence = 0;
      let errorCount = Math.max(0, Number.parseInt(root.dataset.liveReadErrorCount || "0", 10) || 0);
      let pauseReason = "";
      let lastActivityAt = Date.now();

      const rootIsVisible = () => (
        !document.hidden
        && !root.hidden
        && root.getClientRects().length > 0
        && !root.closest("[hidden]")
      );

      const syncRootState = (state) => {
        root.dataset.liveAsyncState = state;
        root.dataset.liveReadErrorCount = String(errorCount);
      };

      const setReadStatus = (state, message = "", {
        retry = false,
        announce = false,
        announcementMessage = message,
        resolveAnnouncementVisibility = null,
      } = {}) => {
        const currentAnnouncementSequence = ++announcementSequence;
        syncRootState(state);
        if (readStatus instanceof HTMLElement) {
          readStatus.hidden = state !== "poll-error" && state !== "offline" && state !== "revision-conflict";
          readStatus.setAttribute("aria-busy", state === "checking" ? "true" : "false");
        }
        if (readStatusMessage instanceof HTMLElement) {
          readStatusMessage.textContent = message;
        }
        if (safeReadRetry instanceof HTMLElement) {
          safeReadRetry.hidden = !retry;
        }
        if (safeReadRetryContainer instanceof HTMLElement) {
          safeReadRetryContainer.hidden = !retry;
        }
        if (announce && announcement instanceof HTMLElement) {
          const hasDeferredAnnouncementVisibility = typeof resolveAnnouncementVisibility === "function";
          if (!hasDeferredAnnouncementVisibility) {
            announcement.textContent = "";
          }
          window.requestAnimationFrame(() => {
            if (announcementSequence !== currentAnnouncementSequence) {
              return;
            }
            if (
              hasDeferredAnnouncementVisibility
              && !resolveAnnouncementVisibility()
            ) {
              return;
            }
            announcement.textContent = announcementMessage;
          });
        }
      };

      const invalidateCurrentRead = () => {
        if (!currentRead) {
          return;
        }
        const staleRead = currentRead;
        currentRead = null;
        staleRead.controller.abort();
      };

      const beginRead = (contextKey = "default") => {
        if (pauseReason || currentRead || !navigator.onLine || document.hidden) {
          return null;
        }
        const controller = new AbortController();
        const ticket = {
          id: ++readSequence,
          contextKey: String(contextKey || "default"),
          controller,
          signal: controller.signal,
          timeoutMs: idleThresholdMs,
          startedAt: performance.now(),
        };
        currentRead = ticket;
        setReadStatus("checking");
        return ticket;
      };

      const settleRead = (ticket, outcome, settleOptions = {}) => {
        if (!ticket || currentRead !== ticket) {
          return "superseded-response";
        }
        currentRead = null;
        const normalizedOutcome = String(outcome || "poll-error");
        if (normalizedOutcome === "unchanged" || normalizedOutcome === "updated") {
          errorCount = 0;
          const shouldAnnounceUpdate = normalizedOutcome === "updated" && Boolean(settleOptions.didReplace);
          const resolveDidReplaceVisible = typeof settleOptions.resolveDidReplaceVisible === "function"
            ? settleOptions.resolveDidReplaceVisible
            : () => true;
          setReadStatus("active", "", {
            announce: shouldAnnounceUpdate,
            announcementMessage: updatedMessage,
            resolveAnnouncementVisibility: shouldAnnounceUpdate
              ? () => resolveDidReplaceVisible() && rootIsVisible()
              : null,
          });
          return normalizedOutcome;
        }
        if (normalizedOutcome === "superseded-response") {
          setReadStatus(pauseReason || "active");
          return normalizedOutcome;
        }
        if (normalizedOutcome === "revision-conflict") {
          setReadStatus(
            "revision-conflict",
            String(settleOptions.message || "This view changed elsewhere. Refresh and review before repeating the action."),
            { retry: true, announce: true },
          );
          return normalizedOutcome;
        }
        errorCount += 1;
        setReadStatus(
          "poll-error",
          String(settleOptions.message || readErrorMessage),
          { retry: true, announce: true },
        );
        return "poll-error";
      };

      const pause = (reason = "paused") => {
        pauseReason = String(reason || "paused");
        invalidateCurrentRead();
        if (pauseReason === "offline") {
          setReadStatus(
            "offline",
            offlineMessage,
            { announce: true },
          );
        } else {
          setReadStatus("paused");
        }
      };

      const resume = () => {
        if (!navigator.onLine) {
          pause("offline");
          return false;
        }
        if (document.hidden) {
          pause("document-hidden");
          return false;
        }
        pauseReason = "";
        setReadStatus(errorCount ? "poll-error" : "active", errorCount
          ? readErrorMessage
          : "", { retry: errorCount > 0 });
        return true;
      };

      const markActivity = () => {
        lastActivityAt = Date.now();
      };

      const nextDelay = () => {
        if (errorCount > 0) {
          return Math.min(idleThresholdMs, idleIntervalMs * (2 ** (errorCount - 1)));
        }
        return Date.now() - lastActivityAt >= idleThresholdMs ? idleIntervalMs : activeIntervalMs;
      };

      const beginMutation = (form) => {
        if (!(form instanceof HTMLFormElement) || form.dataset.liveMutationState === "pending") {
          return null;
        }
        const ticket = { id: ++mutationSequence, form };
        form.dataset.liveMutationState = "pending";
        return ticket;
      };

      const settleMutation = (form, outcome, settleOptions = {}) => {
        if (!(form instanceof HTMLFormElement)) {
          return String(outcome || "mutation-unknown");
        }
        const normalizedOutcome = String(outcome || "mutation-unknown");
        form.dataset.liveMutationState = normalizedOutcome;
        if (normalizedOutcome === "revision-conflict" && settleOptions.message) {
          setReadStatus("revision-conflict", String(settleOptions.message), {
            retry: true,
            announce: true,
          });
        }
        return normalizedOutcome;
      };

      const captureState = (stateRoot = root) => ({
        focus: captureFocus(stateRoot),
        viewport: captureViewportAnchor(stateRoot),
      });

      const restoreState = (stateRoot = root, state = null) => {
        if (!state) {
          return;
        }
        restoreFocus(stateRoot, state.focus);
        restoreViewportAnchor(stateRoot, state.viewport);
      };

      const snapshot = () => ({
        state: root.dataset.liveAsyncState || "active",
        errorCount,
        pauseReason,
        readInFlight: Boolean(currentRead),
        currentReadId: currentRead ? currentRead.id : null,
        currentContextKey: currentRead ? currentRead.contextKey : "",
        activeIntervalMs,
        idleIntervalMs,
        idleThresholdMs,
        lastActivityAt,
      });

      syncRootState("active");
      return {
        beginRead,
        settleRead,
        pause,
        resume,
        markActivity,
        nextDelay,
        snapshot,
        beginMutation,
        settleMutation,
        captureState,
        restoreState,
      };
    };

    const createFragmentGuard = (root, { canFlush = () => true, interactionViewport = false } = {}) => {
      const composing = new Set();
      const pending = new Map();
      const dirtyField = (field) => {
        if (!field.form) return false;
        if (field instanceof HTMLInputElement) {
          if (field.type === "file") return Boolean(field.files?.length);
          if (["checkbox", "radio"].includes(field.type)) return field.checked !== field.defaultChecked;
          if (["hidden", "submit", "button"].includes(field.type)) return false;
          return field.value !== field.defaultValue;
        }
        if (field instanceof HTMLTextAreaElement) return field.value !== field.defaultValue;
        if (field instanceof HTMLSelectElement) {
          const defaults = Array.from(field.options).filter((option) => option.defaultSelected);
          return field.value !== (defaults[0]?.value ?? field.options[0]?.value ?? "");
        }
        return false;
      };
      const isProtected = (region, { ignoreForms = [], protectDirty = true, protectFocus = true } = {}) => {
        const ignored = (field) => ignoreForms.includes(field.form);
        const active = document.activeElement;
        if (protectFocus && active instanceof Element && region.contains(active)
          && active.matches("input, textarea, select, [contenteditable=true]") && !ignored(active)) return true;
        if (protectFocus && Array.from(composing).some((field) => region.contains(field) && !ignored(field))) return true;
        return protectDirty && Array.from(region.querySelectorAll("input, textarea, select")).some(
          (field) => !ignored(field) && dirtyField(field),
        );
      };
      const syncAuthority = (region, html) => {
        const parsed = document.createElement("template");
        parsed.innerHTML = html;
        for (const form of region.querySelectorAll("form")) {
          const incoming = Array.from(parsed.content.querySelectorAll("form")).find(
            (candidate) => candidate.getAttribute("action") === form.getAttribute("action"),
          );
          const unavailable = !incoming || Array.from(incoming.querySelectorAll("button[type=submit], button:not([type]), input[type=submit]"))
            .every((button) => button.disabled);
          if (!unavailable) continue;
          form.dataset.liveAuthorityUnavailable = "1";
          for (const button of form.querySelectorAll("button[type=submit], button:not([type]), input[type=submit]")) button.disabled = true;
          if (!form.querySelector("[data-live-draft-authority]")) {
            const message = document.createElement("p");
            message.dataset.liveDraftAuthority = "1";
            message.setAttribute("role", "status");
            message.textContent = "These controls are no longer available. Your draft is retained; refresh and compare before continuing.";
            form.append(message);
          }
        }
      };
      const apply = (region, entry) => {
        const focus = captureFocus(root);
        const anchor = captureViewportAnchor(root, { interaction: interactionViewport });
        const detailKey = (detail) => {
          if (detail.id) return detail.id;
          const owner = detail.closest("[data-session-article-id], [data-combatant-id]");
          const ownerKey = owner?.dataset.sessionArticleId || owner?.dataset.combatantId || "";
          return `${ownerKey}:${owner === detail ? "article" : detail.querySelector("summary")?.textContent}`;
        };
        const details = Array.from(region.querySelectorAll("details")).map((detail) => ({
          key: detailKey(detail),
          open: detail.open,
        }));
        const applied = entry.apply() !== false;
        for (const detail of region.querySelectorAll("details")) {
          const key = detailKey(detail);
          const previous = details.find((item) => item.key === key);
          if (previous) detail.open = previous.open;
        }
        restoreFocus(root, focus);
        restoreViewportAnchor(root, anchor);
        return applied;
      };
      const reconcileInteractions = (region, entry) => {
        const incoming = document.createElement("div");
        incoming.innerHTML = entry.html;
        const retained = new Map();
        const islands = new Set();
        const matchingContainer = (current) => {
          if (current === region) return incoming;
          const parent = current.parentElement && matchingContainer(current.parentElement);
          if (!parent) return null;
          const sameContainer = (candidate) => candidate.tagName === current.tagName
            && (current.id ? candidate.id === current.id : candidate.className === current.className);
          const index = Array.from(current.parentElement.children).filter(sameContainer).indexOf(current);
          return Array.from(parent.children).filter(sameContainer)[index] || null;
        };
        for (const form of region.querySelectorAll("form")) {
          if (!isProtected(form, entry.options)) continue;
          const nextForm = findMatchingForm(incoming, describeForm(region, form));
          const confirmation = form.closest("[data-destructive-confirmation]");
          let current = confirmation || form;
          let next = nextForm?.closest("[data-destructive-confirmation]") || nextForm;
          if (!next) {
            // An uncertain confirmation is transient local context. When a
            // peer removes its target, retain only the revoked dialog in its
            // existing container while rendering authoritative empty content.
            const container = confirmation && matchingContainer(confirmation.parentElement);
            if (!container) return false;
            next = confirmation.cloneNode(true);
            container.append(next);
          }
          islands.add(current);
          while (current !== region && next !== incoming) {
            if (current.tagName !== next.tagName || (retained.has(next) && retained.get(next) !== current)) return false;
            retained.set(next, current);
            current = current.parentElement;
            next = next.parentElement;
          }
          if (current !== region || next !== incoming) return false;
        }
        if (!islands.size) return false;
        // Do not detach any island if a future payload changes its hierarchy
        // or relative ordering. That interaction can catch up after release.
        for (const [next, current] of [[incoming, region], ...retained]) {
          if (islands.has(current)) continue;
          const expected = Array.from(next.childNodes).map((child) => retained.get(child)).filter(Boolean);
          const actual = Array.from(current.childNodes).filter((child) => expected.includes(child));
          if (actual.length !== expected.length || actual.some((child, index) => child !== expected[index])) return false;
        }
        const patch = (current, next) => {
          if (islands.has(current)) {
            // Keep acknowledgement/recovery controls mounted, but make the
            // destructive scope describe the current authoritative articles.
            const scope = current.querySelector("[data-destructive-confirmation-scope]");
            const nextScope = next.querySelector("[data-destructive-confirmation-scope]");
            if (scope && nextScope) scope.innerHTML = nextScope.innerHTML;
            return;
          }
          let cursor = current.firstChild;
          for (const child of Array.from(next.childNodes)) {
            const kept = retained.get(child);
            if (kept) {
              // Retained ancestors keep their original place and never detach
              // a focused control, even when moveBefore is unavailable.
              while (cursor && cursor !== kept) {
                const obsolete = cursor;
                cursor = cursor.nextSibling;
                obsolete.remove();
              }
              patch(kept, child);
              cursor = kept.nextSibling;
            } else {
              current.insertBefore(child.cloneNode(true), cursor);
            }
          }
          while (cursor) {
            const obsolete = cursor;
            cursor = cursor.nextSibling;
            obsolete.remove();
          }
        };
        patch(region, incoming);
        entry.options.afterRetained?.();
        return true;
      };
      const replace = (region, html, applyReplacement = () => { region.innerHTML = html; }, options = {}) => {
        if (!(region instanceof Element)) return false;
        const entry = { html, apply: applyReplacement, options };
        if (isProtected(region, options)) {
          pending.set(region, entry);
          syncAuthority(region, html);
          if (options.retainInteractions) {
            return apply(region, { apply: () => reconcileInteractions(region, entry) });
          }
          return false;
        }
        pending.delete(region);
        return apply(region, entry);
      };
      const flush = () => {
        if (!canFlush()) return;
        for (const [region, entry] of pending) {
          if (!region.isConnected) { pending.delete(region); continue; }
          if (!isProtected(region, entry.options)) {
            pending.delete(region);
            apply(region, entry);
          }
        }
      };
      root.addEventListener("compositionstart", (event) => composing.add(event.target));
      root.addEventListener("compositionend", (event) => { composing.delete(event.target); queueMicrotask(flush); });
      for (const eventName of ["focusout", "input", "change", "reset"]) root.addEventListener(eventName, () => queueMicrotask(flush));
      root.addEventListener("submit", (event) => {
        if (event.target.dataset.liveAuthorityUnavailable === "1") { event.preventDefault(); event.stopImmediatePropagation(); }
      }, true);
      return { replace, flush, isProtected, denyAuthority: () => {
        pending.clear();
        syncAuthority(root, "");
        root.dispatchEvent(new CustomEvent("playerWiki:live-authority-unavailable", { bubbles: true }));
      } };
    };

    const appendCharacterRecoveryDrafts = (source, recovery, queuedDrafts = []) => {
      if (!(source instanceof HTMLElement) || !(recovery instanceof HTMLElement)) {
        return;
      }
      const drafts = [];
      for (const field of source.querySelectorAll("textarea[name], input[name], select[name]")) {
        if (
          field instanceof HTMLInputElement
          && ["hidden", "password", "file", "submit", "button", "reset"].includes(field.type)
        ) {
          continue;
        }
        const label = Array.from(field.labels || []).map((item) => item.textContent.trim()).join(" ")
          || field.getAttribute("aria-label") || field.name;
        const value = field instanceof HTMLInputElement && ["checkbox", "radio"].includes(field.type)
          ? (field.checked ? "Yes" : "No")
          : field instanceof HTMLSelectElement && field.multiple
            ? Array.from(field.selectedOptions).map((option) => option.value).join(", ")
            : field.value;
        drafts.push({ name: field.name, label, value: String(value) });
      }
      drafts.push(...queuedDrafts);
      const section = document.createElement("section");
      section.className = "card";
      section.setAttribute("aria-label", "Local values kept for copying");
      const heading = document.createElement("h2");
      heading.textContent = "Local values kept for copying";
      section.append(heading);
      const seen = new Set();
      for (const draft of drafts) {
        const key = JSON.stringify([draft.name, draft.label, draft.value]);
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        const label = document.createElement("label");
        label.textContent = draft.label;
        const copy = document.createElement("textarea");
        copy.dataset.characterLocalDraft = draft.name;
        copy.readOnly = true;
        copy.rows = String(draft.value).includes("\n") ? 4 : 2;
        copy.value = String(draft.value);
        label.append(copy);
        section.append(label);
      }
      if (seen.size) {
        (recovery.querySelector("[data-character-read-section-content]") || recovery).append(section);
      }
    };

    window.__playerWikiLiveUiTools = {
      createFragmentGuard,
      captureFocus,
      restoreFocus,
      restoreFocusKey,
      captureViewportAnchor,
      restoreViewportAnchor,
      createAsyncPolicy,
      appendCharacterRecoveryDrafts,
    };
  })();

  (() => {
    if (window.__playerWikiLiveDiagnosticsTools) {
      return;
    }

    const ensureMetricsStore = () => {
      if (!(window.__playerWikiLiveMetrics && typeof window.__playerWikiLiveMetrics === "object")) {
        window.__playerWikiLiveMetrics = {};
      }
      const store = window.__playerWikiLiveMetrics;
      if (typeof store.sequence !== "number") {
        store.sequence = 0;
      }
      if (!(store.latest && typeof store.latest === "object")) {
        store.latest = {};
      }
      if (!(store.history && typeof store.history === "object")) {
        store.history = {};
      }
      return store;
    };

    const recordMetric = (viewName, metric) => {
      const store = ensureMetricsStore();
      store.sequence += 1;
      const entry = {
        sequence: store.sequence,
        recordedAt: new Date().toISOString(),
        view: viewName,
        ...metric,
      };
      store.latest[viewName] = entry;
      if (!Array.isArray(store.history[viewName])) {
        store.history[viewName] = [];
      }
      store.history[viewName].push(entry);
      if (store.history[viewName].length > 25) {
        store.history[viewName].shift();
      }
      return entry;
    };

    const registerSampler = (viewName, sampler) => {
      if (!(window.__playerWikiLiveDiagnostics && typeof window.__playerWikiLiveDiagnostics === "object")) {
        window.__playerWikiLiveDiagnostics = {};
      }
      window.__playerWikiLiveDiagnostics[viewName] = {
        sample: sampler,
      };
    };

    window.__playerWikiLiveDiagnosticsTools = {
      ensureMetricsStore,
      recordMetric,
      registerSampler,
    };
  })();
