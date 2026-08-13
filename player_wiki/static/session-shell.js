  (() => {
    const shellRoot = document.querySelector("[data-session-shell-root]");
    if (!shellRoot) {
      return;
    }

    const liveUiTools = window.__playerWikiLiveUiTools || {};
    const restoreFocusKey = typeof liveUiTools.restoreFocusKey === "function"
      ? liveUiTools.restoreFocusKey
      : null;

    const switchLinks = Array.from(shellRoot.querySelectorAll("[data-session-switch='1']"));
    const panes = new Map(
      Array.from(shellRoot.querySelectorAll("[data-session-shell-pane]"))
        .map((pane) => [pane.dataset.sessionShellPane || "", pane])
        .filter(([target]) => target),
    );
    const visitedCharacterFragments = new Map();
    const mountedPaneDraftGuards = new WeakMap();
    let characterReadRequestId = 0;
    let characterReadAbortController = null;
    const pendingMutations = [];
    const pendingByKey = new Map();
    const queuedIntentByForm = new WeakMap();
    let activeMutation = null;
    let queuePausedReason = "";
    let queueDrainScheduled = false;
    let characterLifecycleGeneration = 0;
    let shellViewIntentId = 0;
    let shellViewIntentTarget = "";

    const getTargetFromUrl = () => {
      const pathname = window.location.pathname || "";
      if (pathname.includes("/session/character")) {
        return "character";
      }
      if (pathname.includes("/session/dm")) {
        return "dm";
      }
      return "session";
    };

    const normalizeTarget = (target) => {
      const normalized = String(target || "").trim().toLowerCase();
      return panes.has(normalized) ? normalized : "session";
    };

    const initPane = (pane) => {
      if (!pane) {
        return;
      }
      if (pane.dataset.sessionShellPane === "character") {
        if (window.__playerWikiCombatWorkspace && typeof window.__playerWikiCombatWorkspace.init === "function") {
          window.__playerWikiCombatWorkspace.init(pane);
        }
      }
      if (window.__playerWikiSessionLive && typeof window.__playerWikiSessionLive.init === "function") {
        window.__playerWikiSessionLive.init(pane);
      }
    };

    const initMountedPanes = () => {
      for (const pane of panes.values()) {
        initPane(pane);
      }
    };

    const setActiveLivePane = (pane) => {
      if (window.__playerWikiSessionLive && typeof window.__playerWikiSessionLive.activatePane === "function") {
        window.__playerWikiSessionLive.activatePane(pane);
      }
    };

    const updatePaneHtml = (target, html, { lifecycleGeneration = null } = {}) => {
      const pane = panes.get(target);
      if (!pane) {
        return false;
      }
      if (target === "character") {
        if (
          lifecycleGeneration !== null
          && lifecycleGeneration !== characterLifecycleGeneration
        ) {
          return false;
        }
        const parsed = parseCharacterFragment(html);
        const identity = parsed ? describeCharacterIdentity(parsed.root) : null;
        if (!parsed || !identity) {
          return false;
        }
        if (
          lifecycleGeneration !== null
          && lifecycleGeneration !== characterLifecycleGeneration
        ) {
          return false;
        }
        try {
          return commitCharacterNodes(
            pane,
            parsed.template.content,
            identity,
            { cacheCurrent: false },
          );
        } catch (_error) {
          return false;
        }
      }
      pane.innerHTML = html;
      pane.dataset.sessionShellPaneLoaded = "1";
      delete pane.dataset.sessionShellPaneStale;
      initPane(pane);
      return true;
    };

    const fallbackUrlFromResponse = (responseUrl) => {
      if (!responseUrl) {
        return "";
      }
      try {
        const url = new URL(responseUrl, window.location.origin);
        url.searchParams.delete("fragment");
        return `${url.pathname}${url.search}${url.hash}`;
      } catch (_error) {
        return "";
      }
    };

    const rememberCharacterPaneUrl = (value) => {
      const pane = panes.get("character");
      if (!(pane instanceof HTMLElement) || !value) {
        return;
      }
      try {
        const url = new URL(value, window.location.href);
        url.searchParams.set("fragment", "1");
        pane.dataset.sessionShellPaneUrl = `${url.pathname}${url.search}${url.hash}`;
      } catch (_error) {
        // Keep the existing canonical fragment URL when a response URL is unavailable.
      }
    };

    const parseCharacterFragment = (html) => {
      const sourceTemplate = document.createElement("template");
      sourceTemplate.innerHTML = String(html || "");
      const root = sourceTemplate.content.querySelector("[data-session-character-fragment-root]");
      if (!(root instanceof HTMLElement)) {
        return null;
      }
      const fragmentTemplate = document.createElement("template");
      const flashStack = root.previousElementSibling;
      if (
        flashStack instanceof HTMLElement
        && flashStack.matches("[data-session-character-flash-stack]")
      ) {
        fragmentTemplate.content.append(flashStack);
      }
      fragmentTemplate.content.append(root);
      const template = fragmentTemplate;
      return { template, root };
    };

    const canonicalUrlFromCharacterFragment = (parsed, fallbackValue = "") => {
      if (!parsed || !(parsed.root instanceof HTMLElement)) {
        return "";
      }
      const identity = describeCharacterIdentity(parsed.root);
      const matchingSectionLink = identity
        ? Array.from(parsed.root.querySelectorAll("[data-session-character-section-link]"))
          .find((link) => (
            link instanceof HTMLAnchorElement
            && link.dataset.sessionCharacterSectionLink === identity.page
          ))
        : null;
      const currentPageLink = parsed.root.querySelector("a[aria-current='page']");
      const candidates = [
        matchingSectionLink instanceof HTMLAnchorElement
          ? matchingSectionLink.getAttribute("href")
          : "",
        currentPageLink instanceof HTMLAnchorElement
          ? currentPageLink.getAttribute("href")
          : "",
        fallbackValue,
      ];
      for (const candidate of candidates) {
        if (!candidate) {
          continue;
        }
        try {
          const url = new URL(candidate, window.location.href);
          if (
            url.origin !== window.location.origin
            || !url.pathname.endsWith("/session/character")
          ) {
            continue;
          }
          url.searchParams.delete("fragment");
          return `${url.pathname}${url.search}${url.hash}`;
        } catch (_error) {
          // Try the next server-rendered canonical candidate.
        }
      }
      return "";
    };

    const describeCharacterIdentity = (root) => {
      if (!(root instanceof HTMLElement)) {
        return null;
      }
      const identity = {
        character: String(root.dataset.sessionCharacterCharacter || ""),
        page: String(root.dataset.sessionCharacterPage || ""),
        revision: String(root.dataset.sessionCharacterRevision || ""),
        activeSession: String(root.dataset.sessionCharacterActiveSession || ""),
        projection: String(root.dataset.sessionCharacterProjection || ""),
        access: String(root.dataset.sessionCharacterAccess || ""),
      };
      return identity.character && identity.page && identity.projection && identity.access
        ? identity
        : null;
    };

    const currentCharacterIdentity = (pane = panes.get("character")) => {
      if (!(pane instanceof HTMLElement)) {
        return null;
      }
      return describeCharacterIdentity(
        pane.querySelector("[data-session-character-fragment-root]"),
      );
    };

    const canonicalUrlFromMountedCharacterPane = (pane = panes.get("character")) => {
      if (!(pane instanceof HTMLElement)) {
        return "";
      }
      const root = pane.querySelector("[data-session-character-fragment-root]");
      if (!(root instanceof HTMLElement)) {
        return "";
      }
      return canonicalUrlFromCharacterFragment(
        { root },
        pane.dataset.sessionShellPaneUrl || "",
      );
    };

    const characterIdentityKey = (identity) => (
      identity
        ? [
          identity.character,
          identity.page,
          identity.revision,
          identity.activeSession,
          identity.projection,
          identity.access,
        ].join("\u001f")
        : ""
    );

    const characterIdentityMatchesIntent = (identity, intent) => Boolean(
      identity
      && intent
      && identity.character === intent.character
      && identity.page === intent.page
      && identity.revision === intent.revision
      && identity.activeSession === intent.activeSession
      && identity.projection === intent.projection
      && identity.access === intent.access
    );

    const characterIdentityInvalidatesRetainedFragments = (identity, committedIdentity) => Boolean(
      identity
      && committedIdentity
      && (
        identity.character !== committedIdentity.character
        || identity.revision !== committedIdentity.revision
        || identity.activeSession !== committedIdentity.activeSession
        || identity.projection !== committedIdentity.projection
        || identity.access !== committedIdentity.access
      )
    );

    const abortCharacterSafeRead = () => {
      const pane = panes.get("character");
      if (pane instanceof HTMLElement) {
        const nav = pane.querySelector("[data-session-character-section-nav]");
        if (nav instanceof HTMLElement) {
          nav.removeAttribute("aria-busy");
        }
      }
      characterReadRequestId += 1;
      if (characterReadAbortController) {
        characterReadAbortController.abort();
      }
      characterReadAbortController = null;
    };

    const clearVisitedCharacterFragments = (reason = "") => {
      visitedCharacterFragments.clear();
      shellRoot.dispatchEvent(new CustomEvent("playerWiki:session-character-fragments-cleared", {
        detail: { reason: String(reason || "") },
      }));
    };

    const buildSubmitFormData = (form, submitter) => {
      let formData;
      try {
        formData = submitter ? new FormData(form, submitter) : new FormData(form);
      } catch (_error) {
        formData = new FormData(form);
        if (submitter && submitter.name && !submitter.disabled) {
          formData.append(submitter.name, submitter.value || "");
        }
      }
      formData.set("fragment", "1");
      return formData;
    };

    const describeAutosubmitFormState = (form) => {
      const params = new URLSearchParams();
      for (const [name, value] of new FormData(form).entries()) {
        params.append(name, typeof value === "string" ? value : "");
      }
      return params.toString();
    };

    const isRestorableField = (field) => {
      if (field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement) {
        return !!field.name;
      }
      if (!(field instanceof HTMLInputElement) || !field.name) {
        return false;
      }
      const type = String(field.type || "text").toLowerCase();
      return !["button", "file", "hidden", "image", "reset", "submit"].includes(type);
    };

    const getRestorableFields = (form) => (
      Array.from(form.elements).filter((field) => isRestorableField(field))
    );

    const getFieldTypeKey = (field) => {
      if (field instanceof HTMLInputElement) {
        return String(field.type || "text").toLowerCase();
      }
      return field.tagName.toLowerCase();
    };

    const describeFormBase = (form) => {
      if (!(form instanceof HTMLFormElement)) {
        return null;
      }
      const fieldSignature = getRestorableFields(form)
        .map((field) => `${field.name}:${getFieldTypeKey(field)}`)
        .join("|");
      const hiddenValue = (name) => {
        const field = form.querySelector(`input[type="hidden"][name="${name}"]`);
        return field instanceof HTMLInputElement ? field.value : "";
      };
      return {
        action: form.getAttribute("action") || "",
        method: String(form.method || "get").toLowerCase(),
        editForm: form.dataset.characterSheetEditForm || "",
        editRowId: form.dataset.characterSheetEditRowId || "",
        mode: hiddenValue("mode"),
        page: hiddenValue("page"),
        returnView: hiddenValue("return_view"),
        fieldSignature,
      };
    };

    const formDescriptionsShareBase = (left, right) => Boolean(
      left
      && right
      && left.action === right.action
      && left.method === right.method
      && left.editForm === right.editForm
      && left.editRowId === right.editRowId
      && left.mode === right.mode
      && left.page === right.page
      && left.returnView === right.returnView
      && left.fieldSignature === right.fieldSignature
    );

    const describeForm = (form) => {
      const base = describeFormBase(form);
      if (!base || !(form instanceof HTMLFormElement)) {
        return null;
      }
      const scope = form.closest("[data-session-shell-pane='character']") || form.parentElement;
      const sameDescriptionForms = scope instanceof Element
        ? Array.from(scope.querySelectorAll("form")).filter((candidate) => (
          candidate instanceof HTMLFormElement
          && formDescriptionsShareBase(describeFormBase(candidate), base)
        ))
        : [form];
      return {
        ...base,
        id: String(form.id || ""),
        focusKey: String(form.dataset.liveFocusKey || ""),
        ordinal: Math.max(0, sameDescriptionForms.indexOf(form)),
      };
    };

    const describeField = (field, form) => {
      if (!isRestorableField(field) || !(form instanceof HTMLFormElement)) {
        return null;
      }
      const typeKey = getFieldTypeKey(field);
      const matchingFields = getRestorableFields(form).filter((candidate) => (
        candidate.name === field.name && getFieldTypeKey(candidate) === typeKey
      ));
      return {
        name: field.name,
        typeKey,
        index: Math.max(0, matchingFields.indexOf(field)),
      };
    };

    const captureFieldValue = (field, form) => {
      const description = describeField(field, form);
      if (!description) {
        return null;
      }
      let value = field.value;
      if (field instanceof HTMLInputElement && ["checkbox", "radio"].includes(getFieldTypeKey(field))) {
        value = field.checked;
      } else if (field instanceof HTMLSelectElement && field.multiple) {
        value = Array.from(field.selectedOptions).map((option) => option.value);
      }
      return {
        ...description,
        value,
      };
    };

    const captureSelection = (field) => {
      if (!(field instanceof HTMLInputElement) && !(field instanceof HTMLTextAreaElement)) {
        return null;
      }
      try {
        if (typeof field.selectionStart !== "number" || typeof field.selectionEnd !== "number") {
          return null;
        }
        return {
          start: field.selectionStart,
          end: field.selectionEnd,
          direction: field.selectionDirection || "none",
        };
      } catch (_error) {
        return null;
      }
    };

    const describePreservedElement = (element, index) => ({
      id: String(element.id || ""),
      focusKey: String(element.dataset.liveFocusKey || ""),
      index,
    });

    const characterFocusableSelector = [
      "a[href]",
      "button",
      "input",
      "select",
      "summary",
      "textarea",
      "[tabindex]",
    ].join(",");

    const describeFocusedElement = (pane, element) => {
      if (!(pane instanceof HTMLElement) || !(element instanceof HTMLElement) || !pane.contains(element)) {
        return null;
      }
      const focusableElements = Array.from(pane.querySelectorAll(characterFocusableSelector));
      const dialog = element.closest("dialog[id]");
      return {
        ...describePreservedElement(element, Math.max(0, focusableElements.indexOf(element))),
        tagName: element.tagName,
        sectionLink: String(element.dataset.sessionCharacterSectionLink || ""),
        dialogId: dialog instanceof HTMLDialogElement ? dialog.id : "",
        dialogInitialFocus: element.hasAttribute("data-presentation-dialog-initial-focus"),
        dialogClose: element.hasAttribute("data-presentation-dialog-close"),
      };
    };

    const captureCharacterPaneRestoreState = (pane) => {
      if (!(pane instanceof HTMLElement)) {
        return null;
      }
      const state = {
        form: null,
        activeField: null,
        values: [],
        selection: null,
        details: Array.from(pane.querySelectorAll("details"))
          .map((detail, index) => ({
            ...describePreservedElement(detail, index),
            open: detail.open,
          })),
        dialogs: Array.from(pane.querySelectorAll("dialog[open]"))
          .map((dialog, index) => describePreservedElement(dialog, index)),
        paneScrollLeft: pane.scrollLeft,
        paneScrollTop: pane.scrollTop,
        viewportX: window.scrollX,
        viewportY: window.scrollY,
        focusedElement: null,
      };
      const activeField = document.activeElement;
      state.focusedElement = describeFocusedElement(pane, activeField);
      if (!isRestorableField(activeField) || !pane.contains(activeField)) {
        return state;
      }
      const form = activeField.form;
      if (!(form instanceof HTMLFormElement) || !pane.contains(form)) {
        return state;
      }
      const activeFieldDescription = describeField(activeField, form);
      if (!activeFieldDescription) {
        return state;
      }
      state.form = describeForm(form);
      state.activeField = activeFieldDescription;
      state.values = getRestorableFields(form)
        .map((field) => captureFieldValue(field, form))
        .filter(Boolean);
      state.selection = captureSelection(activeField);
      return state;
    };

    const formsMatchDescription = (form, description) => {
      const nextDescription = describeForm(form);
      if (!nextDescription || !description) {
        return false;
      }
      return (
        nextDescription.action === description.action
        && nextDescription.method === description.method
        && nextDescription.editForm === description.editForm
        && nextDescription.editRowId === description.editRowId
        && nextDescription.mode === description.mode
        && nextDescription.page === description.page
        && nextDescription.returnView === description.returnView
        && nextDescription.fieldSignature === description.fieldSignature
        && nextDescription.id === description.id
        && nextDescription.focusKey === description.focusKey
        && nextDescription.ordinal === description.ordinal
      );
    };

    const findMatchingForm = (pane, description) => {
      if (!(pane instanceof HTMLElement) || !description) {
        return null;
      }
      return Array.from(pane.querySelectorAll("form")).find((form) => (
        form instanceof HTMLFormElement && formsMatchDescription(form, description)
      )) || null;
    };

    const findMatchingField = (form, description) => {
      if (!(form instanceof HTMLFormElement) || !description) {
        return null;
      }
      const matches = getRestorableFields(form).filter((field) => (
        field.name === description.name && getFieldTypeKey(field) === description.typeKey
      ));
      return matches[description.index] || null;
    };

    const captureMountedPaneDrafts = (pane) => {
      if (!(pane instanceof HTMLElement)) {
        return [];
      }
      const defaultSelectedIndex = (field) => {
        const options = Array.from(field.options);
        let explicitDefaultIndex = -1;
        options.forEach((option, index) => {
          if (option.defaultSelected) {
            explicitDefaultIndex = index;
          }
        });
        if (explicitDefaultIndex >= 0 || field.size > 1) {
          return explicitDefaultIndex;
        }
        return options.findIndex((option) => {
          const optionGroup = option.parentElement;
          return !option.disabled && !(
            optionGroup instanceof HTMLOptGroupElement && optionGroup.disabled
          );
        });
      };
      const isDirty = (field) => {
        if (field instanceof HTMLInputElement && ["checkbox", "radio"].includes(getFieldTypeKey(field))) {
          return field.checked !== field.defaultChecked;
        }
        if (field instanceof HTMLSelectElement) {
          const options = Array.from(field.options);
          if (field.multiple) {
            return options.some((option) => option.selected !== option.defaultSelected);
          }
          return field.selectedIndex !== defaultSelectedIndex(field);
        }
        if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
          return field.value !== field.defaultValue;
        }
        return false;
      };
      return Array.from(pane.querySelectorAll("form"))
        .filter((form) => form instanceof HTMLFormElement)
        .map((form) => {
          const dirtyFields = getRestorableFields(form).filter((field) => isDirty(field));
          return {
            form: describeForm(form),
            values: dirtyFields
              .map((field) => captureFieldValue(field, form))
              .filter(Boolean),
          };
        })
        .filter((state) => state.form && state.values.length > 0);
    };

    const restoreMountedPaneDrafts = (pane, states) => {
      if (!(pane instanceof HTMLElement)) {
        return;
      }
      for (const state of states || []) {
        const form = findMatchingForm(pane, state.form);
        if (!(form instanceof HTMLFormElement)) {
          continue;
        }
        for (const fieldState of state.values || []) {
          const field = findMatchingField(form, fieldState);
          if (field) {
            restoreFieldValue(field, fieldState.value);
          }
        }
      }
    };

    const restoreFieldValue = (field, value) => {
      if (field instanceof HTMLInputElement && ["checkbox", "radio"].includes(getFieldTypeKey(field))) {
        field.checked = !!value;
        return;
      }
      if (field instanceof HTMLSelectElement && field.multiple && Array.isArray(value)) {
        const selectedValues = new Set(value.map((entry) => String(entry)));
        for (const option of field.options) {
          option.selected = selectedValues.has(option.value);
        }
        return;
      }
      if (
        field instanceof HTMLInputElement
        || field instanceof HTMLSelectElement
        || field instanceof HTMLTextAreaElement
      ) {
        field.value = String(value ?? "");
      }
    };

    const defaultSelectedIndex = (field) => {
      const options = Array.from(field.options);
      let explicitDefaultIndex = -1;
      options.forEach((option, index) => {
        if (option.defaultSelected) {
          explicitDefaultIndex = index;
        }
      });
      if (explicitDefaultIndex >= 0 || field.size > 1) {
        return explicitDefaultIndex;
      }
      return options.findIndex((option) => {
        const optionGroup = option.parentElement;
        return !option.disabled && !(
          optionGroup instanceof HTMLOptGroupElement && optionGroup.disabled
        );
      });
    };

    const isRestorableFieldDirty = (field) => {
      if (field instanceof HTMLInputElement && ["checkbox", "radio"].includes(getFieldTypeKey(field))) {
        return field.checked !== field.defaultChecked;
      }
      if (field instanceof HTMLSelectElement) {
        const options = Array.from(field.options);
        if (field.multiple) {
          return options.some((option) => option.selected !== option.defaultSelected);
        }
        return field.selectedIndex !== defaultSelectedIndex(field);
      }
      if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
        return field.value !== field.defaultValue;
      }
      return false;
    };

    const isVisibleRestorableField = (field) => Boolean(
      isRestorableField(field)
      && !field.hidden
      && !field.closest("[hidden], [aria-hidden='true']")
      && field.getClientRects().length > 0
    );

    const mutationIntentKey = (descriptor) => JSON.stringify(descriptor || {});

    const captureAutosubmitIntent = (form) => {
      if (!(form instanceof HTMLFormElement)) {
        return null;
      }
      const descriptor = describeForm(form);
      if (!descriptor) {
        return null;
      }
      const values = getRestorableFields(form)
        .filter((field) => isVisibleRestorableField(field) && isRestorableFieldDirty(field))
        .map((field) => captureFieldValue(field, form))
        .filter(Boolean);
      const key = mutationIntentKey(descriptor);
      return {
        key,
        descriptor,
        generation: characterLifecycleGeneration,
        values,
        fingerprint: JSON.stringify([key, values]),
      };
    };

    const enqueueIntent = (intent) => {
      if (!intent || intent.generation !== characterLifecycleGeneration) {
        return false;
      }
      if (
        activeMutation
        && activeMutation.key === intent.key
        && activeMutation.fingerprint === intent.fingerprint
      ) {
        return false;
      }
      const existing = pendingByKey.get(intent.key);
      if (existing) {
        if (existing.fingerprint === intent.fingerprint) {
          return false;
        }
        existing.descriptor = intent.descriptor;
        existing.generation = intent.generation;
        existing.values = intent.values;
        existing.fingerprint = intent.fingerprint;
        return true;
      }
      pendingMutations.push(intent);
      pendingByKey.set(intent.key, intent);
      return true;
    };

    const removePendingIntent = (key) => {
      const existing = pendingByKey.get(key);
      if (!existing) {
        return;
      }
      pendingByKey.delete(key);
      const index = pendingMutations.indexOf(existing);
      if (index >= 0) {
        pendingMutations.splice(index, 1);
      }
    };

    const captureAllDirtyAutosubmits = (pane, { excludeForm = null } = {}) => {
      if (!(pane instanceof HTMLElement)) {
        return false;
      }
      let foundDirty = false;
      let foundInvalid = false;
      const forms = Array.from(pane.querySelectorAll("form[data-character-autosubmit]"));
      for (const form of forms) {
        if (!(form instanceof HTMLFormElement) || form === excludeForm) {
          continue;
        }
        window.clearTimeout(Number(form.dataset.characterAutosubmitTimer || "0"));
        form.dataset.characterAutosubmitTimer = "0";
        if (
          describeAutosubmitFormState(form)
          === String(form.dataset.characterAutosubmitState || "")
        ) {
          continue;
        }
        foundDirty = true;
        if (!form.checkValidity()) {
          foundInvalid = true;
          const invalidIntent = captureAutosubmitIntent(form);
          if (invalidIntent && invalidIntent.values.length > 0) {
            enqueueIntent(invalidIntent);
          }
          continue;
        }
        const intent = captureAutosubmitIntent(form);
        if (intent && intent.values.length > 0) {
          enqueueIntent(intent);
        }
      }
      if (foundInvalid) {
        queuePausedReason = "invalid-draft";
      }
      return foundDirty;
    };

    const restoreIntentValues = (pane, intent) => {
      const form = findMatchingForm(pane, intent?.descriptor);
      if (!(form instanceof HTMLFormElement)) {
        return null;
      }
      for (const fieldState of intent.values || []) {
        const field = findMatchingField(form, fieldState);
        if (field) {
          restoreFieldValue(field, fieldState.value);
        }
      }
      window.clearTimeout(Number(form.dataset.characterAutosubmitTimer || "0"));
      form.dataset.characterAutosubmitTimer = "0";
      return form;
    };

    const restoreAllQueuedDrafts = (pane) => {
      if (!(pane instanceof HTMLElement)) {
        return;
      }
      for (const intent of pendingMutations) {
        restoreIntentValues(pane, intent);
      }
    };

    const hasUnsettledMutations = () => Boolean(
      activeMutation || pendingMutations.length > 0
    );

    const startNextQueuedMutation = () => {
      queueDrainScheduled = false;
      if (activeMutation || queuePausedReason || pendingMutations.length === 0) {
        return;
      }
      const pane = panes.get("character");
      const intent = pendingMutations[0];
      if (!(pane instanceof HTMLElement) || intent.generation !== characterLifecycleGeneration) {
        queuePausedReason = "stale-mutation";
        return;
      }
      const form = restoreIntentValues(pane, intent);
      if (!(form instanceof HTMLFormElement)) {
        queuePausedReason = "missing-form";
        showCharacterSectionGuidance(
          pane,
          "A queued sheet edit no longer matches this section. Review the current values before continuing.",
        );
        return;
      }
      pendingMutations.shift();
      if (pendingByKey.get(intent.key) === intent) {
        pendingByKey.delete(intent.key);
      }
      queuedIntentByForm.set(form, intent);
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      }
      if (!activeMutation) {
        queuedIntentByForm.delete(form);
        pendingMutations.unshift(intent);
        pendingByKey.set(intent.key, intent);
        queuePausedReason = "submission-not-started";
      }
    };

    const scheduleQueueDrain = () => {
      if (
        queueDrainScheduled
        || activeMutation
        || queuePausedReason
        || pendingMutations.length === 0
      ) {
        return;
      }
      queueDrainScheduled = true;
      window.queueMicrotask(startNextQueuedMutation);
    };

    const blockCharacterNavigationForMutations = (pane) => {
      if (!hasUnsettledMutations()) {
        return false;
      }
      showCharacterSectionGuidance(
        pane,
        queuePausedReason
          ? "Review the unsaved sheet edit before switching sections."
          : "Finish the current sheet save before switching sections.",
      );
      return true;
    };

    const invalidateMutationQueue = () => {
      const pane = panes.get("character");
      if (pane instanceof HTMLElement) {
        for (const form of pane.querySelectorAll("form[data-character-autosubmit]")) {
          if (form instanceof HTMLFormElement) {
            window.clearTimeout(Number(form.dataset.characterAutosubmitTimer || "0"));
            form.dataset.characterAutosubmitTimer = "0";
            form.dataset.characterAutosubmitState = describeAutosubmitFormState(form);
          }
        }
      }
      pendingMutations.splice(0, pendingMutations.length);
      pendingByKey.clear();
      activeMutation = null;
      queuePausedReason = "";
      queueDrainScheduled = false;
    };

    const findPreservedElement = (pane, selector, description) => {
      if (!(pane instanceof HTMLElement) || !description) {
        return null;
      }
      if (description.id) {
        const byId = pane.querySelector(`#${CSS.escape(description.id)}`);
        if (byId && byId.matches(selector)) {
          return byId;
        }
      }
      if (description.focusKey) {
        const byFocusKey = pane.querySelector(
          `${selector}[data-live-focus-key="${CSS.escape(description.focusKey)}"]`,
        );
        if (byFocusKey) {
          return byFocusKey;
        }
      }
      return Array.from(pane.querySelectorAll(selector))[description.index] || null;
    };

    const findPreservedFocusedElement = (
      pane,
      description,
      { allowIndexFallback = false } = {},
    ) => {
      if (!(pane instanceof HTMLElement) || !description) {
        return null;
      }
      if (description.id) {
        const byId = pane.querySelector(`#${CSS.escape(description.id)}`);
        if (byId instanceof HTMLElement) {
          return byId;
        }
      }
      if (description.focusKey) {
        const byFocusKey = pane.querySelector(
          `[data-live-focus-key="${CSS.escape(description.focusKey)}"]`,
        );
        if (byFocusKey instanceof HTMLElement) {
          return byFocusKey;
        }
      }
      if (description.sectionLink) {
        const bySection = pane.querySelector(
          `[data-session-character-section-link="${CSS.escape(description.sectionLink)}"]`,
        );
        if (bySection instanceof HTMLElement) {
          return bySection;
        }
      }
      if (description.dialogId && (description.dialogInitialFocus || description.dialogClose)) {
        const marker = description.dialogInitialFocus
          ? "[data-presentation-dialog-initial-focus]"
          : "[data-presentation-dialog-close]";
        const byDialogMarker = pane.querySelector(
          `#${CSS.escape(description.dialogId)} ${marker}`,
        );
        if (byDialogMarker instanceof HTMLElement) {
          return byDialogMarker;
        }
      }
      if (!allowIndexFallback) {
        return null;
      }
      const indexed = Array.from(pane.querySelectorAll(characterFocusableSelector))[description.index];
      return indexed instanceof HTMLElement && indexed.tagName === description.tagName
        ? indexed
        : null;
    };

    const restorePreservedFocus = (
      pane,
      state,
      { allowIndexFallback = false } = {},
    ) => {
      const focusedElement = findPreservedFocusedElement(
        pane,
        state?.focusedElement,
        { allowIndexFallback },
      );
      if (!(focusedElement instanceof HTMLElement)) {
        return false;
      }
      focusedElement.focus({ preventScroll: true });
      return document.activeElement === focusedElement;
    };

    const restoreCharacterPaneState = (
      pane,
      state,
      { restoreValues = true } = {},
    ) => {
      if (!(pane instanceof HTMLElement) || !state) {
        return;
      }
      for (const detailState of state.details || []) {
        const detail = findPreservedElement(pane, "details", detailState);
        if (detail instanceof HTMLDetailsElement) {
          detail.open = !!detailState.open;
        }
      }
      for (const dialogState of state.dialogs || []) {
        const dialog = findPreservedElement(pane, "dialog", dialogState);
        if (
          dialog instanceof HTMLDialogElement
          && !(typeof dialog.matches === "function" && dialog.matches(":modal"))
        ) {
          if (dialog.open) {
            dialog.removeAttribute("open");
          }
          try {
            dialog.showModal();
          } catch (_error) {
            dialog.setAttribute("open", "");
          }
        }
      }
      pane.scrollLeft = Number(state.paneScrollLeft || 0);
      pane.scrollTop = Number(state.paneScrollTop || 0);

      const form = state.form ? findMatchingForm(pane, state.form) : null;
      let restoredFormFocus = false;
      if (form instanceof HTMLFormElement) {
        if (restoreValues) {
          for (const fieldState of state.values || []) {
            const field = findMatchingField(form, fieldState);
            if (field) {
              restoreFieldValue(field, fieldState.value);
            }
          }
        }
        const activeField = findMatchingField(form, state.activeField);
        if (activeField) {
          activeField.focus({ preventScroll: true });
          restoredFormFocus = document.activeElement === activeField;
          if (
            state.selection
            && (activeField instanceof HTMLInputElement || activeField instanceof HTMLTextAreaElement)
            && typeof activeField.setSelectionRange === "function"
          ) {
            try {
              activeField.setSelectionRange(
                state.selection.start,
                state.selection.end,
                state.selection.direction || "none",
              );
            } catch (_error) {
              // Some input types, including number inputs in some browsers, do not support selection ranges.
            }
          }
        }
      }
      if (!restoredFormFocus) {
        restorePreservedFocus(pane, state, { allowIndexFallback: true });
      }
      window.requestAnimationFrame(() => {
        window.scrollTo(Number(state.viewportX || 0), Number(state.viewportY || 0));
      });
    };

    const restoreCharacterViewport = (pane, state) => {
      if (!(pane instanceof HTMLElement) || !state) {
        return;
      }
      pane.scrollLeft = Number(state.paneScrollLeft || 0);
      pane.scrollTop = Number(state.paneScrollTop || 0);
      restorePreservedFocus(pane, state, { allowIndexFallback: false });
      window.requestAnimationFrame(() => {
        window.scrollTo(Number(state.viewportX || 0), Number(state.viewportY || 0));
      });
    };

    const takePaneChildren = (pane) => {
      const fragment = document.createDocumentFragment();
      while (pane.firstChild) {
        fragment.append(pane.firstChild);
      }
      return fragment;
    };

    const normalizeCharacterFragmentForCache = (fragment) => {
      if (!(fragment instanceof DocumentFragment)) {
        return;
      }
      for (const nav of fragment.querySelectorAll("[data-session-character-section-nav]")) {
        nav.removeAttribute("aria-busy");
      }
      for (const flashStack of fragment.querySelectorAll("[data-session-character-flash-stack]")) {
        flashStack.replaceChildren();
      }
    };

    const setCharacterSectionBusy = (pane, busy) => {
      if (!(pane instanceof HTMLElement)) {
        return;
      }
      const nav = pane.querySelector("[data-session-character-section-nav]");
      if (!(nav instanceof HTMLElement)) {
        return;
      }
      if (busy) {
        nav.setAttribute("aria-busy", "true");
      } else {
        nav.removeAttribute("aria-busy");
      }
    };

    const showCharacterSectionGuidance = (pane, message) => {
      if (!(pane instanceof HTMLElement)) {
        return;
      }
      const root = pane.querySelector("[data-session-character-fragment-root]");
      if (!(root instanceof HTMLElement)) {
        return;
      }
      let status = root.querySelector("[data-session-character-section-status]");
      if (!(status instanceof HTMLElement)) {
        status = document.createElement("p");
        status.className = "meta";
        status.dataset.sessionCharacterSectionStatus = "";
        status.setAttribute("role", "status");
        status.tabIndex = -1;
        const nav = root.querySelector("[data-session-character-section-nav]");
        if (nav) {
          nav.insertAdjacentElement("afterend", status);
        } else {
          root.prepend(status);
        }
      }
      status.textContent = String(message || "");
      if (message) {
        status.focus({ preventScroll: true });
      }
    };

    const updateCharacterHistory = (identity, url, { replace = false } = {}) => {
      if (!identity || !url) {
        return;
      }
      const nextState = {
        ...(history.state || {}),
        sessionShellView: "character",
        sessionCharacterPage: identity.page,
      };
      if (replace) {
        history.replaceState(nextState, "", url);
      } else {
        history.pushState(nextState, "", url);
      }
    };

    const commitCharacterNodes = (
      pane,
      nodes,
      nextIdentity,
      {
        cacheCurrent = true,
        restoreState = null,
        restoreValues = true,
        cachedEntry = null,
        preservePreviousViewport = false,
      } = {},
    ) => {
      if (!(pane instanceof HTMLElement) || !(nodes instanceof DocumentFragment) || !nextIdentity) {
        return false;
      }
      const previousIdentity = currentCharacterIdentity(pane);
      const previousKey = characterIdentityKey(previousIdentity);
      const nextKey = characterIdentityKey(nextIdentity);
      const previousState = captureCharacterPaneRestoreState(pane);
      const previousNodes = takePaneChildren(pane);
      pane.append(nodes);
      try {
        const mountedIdentity = currentCharacterIdentity(pane);
        if (characterIdentityKey(mountedIdentity) !== nextKey) {
          throw new Error("Session Character fragment identity changed during mount.");
        }
        initPane(pane);
      } catch (error) {
        const rejectedNodes = takePaneChildren(pane);
        if (cachedEntry) {
          cachedEntry.fragment = rejectedNodes;
        }
        pane.append(previousNodes);
        restoreCharacterPaneState(pane, previousState, { restoreValues: true });
        throw error;
      }
      if (cacheCurrent && previousKey && previousKey !== nextKey) {
        normalizeCharacterFragmentForCache(previousNodes);
        visitedCharacterFragments.set(previousKey, {
          fragment: previousNodes,
          identity: previousIdentity,
          state: previousState,
        });
      }
      pane.dataset.sessionShellPaneLoaded = "1";
      delete pane.dataset.sessionShellPaneStale;
      if (restoreState) {
        restoreCharacterPaneState(pane, restoreState, { restoreValues });
      } else if (preservePreviousViewport) {
        restoreCharacterViewport(pane, previousState);
      }
      return true;
    };

    const restoreVisitedCharacterFragment = (pane, key, entry) => {
      if (!entry || !(entry.fragment instanceof DocumentFragment) || !entry.identity) {
        return false;
      }
      visitedCharacterFragments.delete(key);
      try {
        const committed = commitCharacterNodes(
          pane,
          entry.fragment,
          entry.identity,
          {
            cacheCurrent: true,
            restoreState: entry.state,
            restoreValues: true,
            cachedEntry: entry,
          },
        );
        if (!committed) {
          visitedCharacterFragments.set(key, entry);
        }
        return committed;
      } catch (_error) {
        visitedCharacterFragments.set(key, entry);
        return false;
      }
    };

    const navigateCharacterSection = async (
      link,
      { fromHistory = false, historyUrl = "" } = {},
    ) => {
      const pane = panes.get("character");
      if (!(pane instanceof HTMLElement) || !(link instanceof HTMLAnchorElement)) {
        return false;
      }
      const currentIdentity = currentCharacterIdentity(pane);
      const requestedPage = String(link.dataset.sessionCharacterSectionLink || "");
      const fallbackHref = historyUrl || link.getAttribute("href") || "";
      if (!currentIdentity || !requestedPage || !fallbackHref) {
        return false;
      }
      captureAllDirtyAutosubmits(pane);
      scheduleQueueDrain();
      if (blockCharacterNavigationForMutations(pane)) {
        return false;
      }
      if (currentIdentity.page === requestedPage) {
        return true;
      }
      const viewIntentId = shellViewIntentId;
      const lifecycleGeneration = characterLifecycleGeneration;
      const intent = { ...currentIdentity, page: requestedPage };
      const intentKey = characterIdentityKey(intent);

      abortCharacterSafeRead();
      const cached = visitedCharacterFragments.get(intentKey);
      if (cached) {
        if (!restoreVisitedCharacterFragment(pane, intentKey, cached)) {
          link.dataset.sessionCharacterFallbackOnly = "1";
          showCharacterSectionGuidance(
            pane,
            "That cached section could not be restored. Choose it again to use the full page.",
          );
          return false;
        }
        showCharacterSectionGuidance(pane, "");
        rememberCharacterPaneUrl(fallbackHref);
        if (!fromHistory) {
          updateCharacterHistory(intent, fallbackHref);
        }
        return true;
      }

      const requestId = characterReadRequestId;
      const controller = new AbortController();
      characterReadAbortController = controller;
      setCharacterSectionBusy(pane, true);
      let fragmentUrl;
      try {
        fragmentUrl = new URL(fallbackHref, window.location.href);
        fragmentUrl.searchParams.set("fragment", "1");
      } catch (_error) {
        setCharacterSectionBusy(pane, false);
        return false;
      }

      try {
        const response = await fetch(fragmentUrl.href, {
          headers: {
            "X-Requested-With": "XMLHttpRequest",
          },
          cache: "no-store",
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (
          requestId !== characterReadRequestId
          || controller.signal.aborted
          || viewIntentId !== shellViewIntentId
          || lifecycleGeneration !== characterLifecycleGeneration
          || shellRoot.dataset.sessionShellActive !== "character"
        ) {
          return false;
        }
        if (!response.ok) {
          showCharacterSectionGuidance(
            pane,
            response.status === 503
              ? "That section is busy right now. Wait a moment and choose it again."
              : "That section could not be loaded. Choose it again to retry or follow its full-page link.",
          );
          return false;
        }
        const parsed = parseCharacterFragment(await response.text());
        if (
          requestId !== characterReadRequestId
          || controller.signal.aborted
          || viewIntentId !== shellViewIntentId
          || lifecycleGeneration !== characterLifecycleGeneration
          || shellRoot.dataset.sessionShellActive !== "character"
        ) {
          return false;
        }
        const responseIdentity = parsed ? describeCharacterIdentity(parsed.root) : null;
        if (!parsed || !characterIdentityMatchesIntent(responseIdentity, intent)) {
          if (characterIdentityInvalidatesRetainedFragments(responseIdentity, currentIdentity)) {
            clearVisitedCharacterFragments("response-identity-mismatch");
            pane.dataset.sessionShellPaneStale = "1";
          }
          link.dataset.sessionCharacterFallbackOnly = "1";
          showCharacterSectionGuidance(
            pane,
            "The sheet changed while that section was loading. Choose the section again to use its current full page.",
          );
          return false;
        }
        try {
          commitCharacterNodes(
            pane,
            parsed.template.content,
            responseIdentity,
            { cacheCurrent: true, preservePreviousViewport: true },
          );
        } catch (_error) {
          link.dataset.sessionCharacterFallbackOnly = "1";
          showCharacterSectionGuidance(
            pane,
            "That section could not be initialized. Choose it again to use the full page.",
          );
          return false;
        }
        showCharacterSectionGuidance(pane, "");
        const canonicalUrl = canonicalUrlFromCharacterFragment(
          parsed,
          response.url || fallbackHref,
        );
        rememberCharacterPaneUrl(canonicalUrl || fallbackHref);
        if (!fromHistory) {
          updateCharacterHistory(
            responseIdentity,
            canonicalUrl || fallbackHref,
          );
        }
        return true;
      } catch (error) {
        if (error && error.name === "AbortError") {
          return false;
        }
        showCharacterSectionGuidance(
          pane,
          "That section could not be loaded. Choose it again to retry or follow its full-page link.",
        );
        return false;
      } finally {
        if (requestId === characterReadRequestId) {
          characterReadAbortController = null;
          setCharacterSectionBusy(pane, false);
        }
      }
    };

    const isPaneLoaded = (target) => {
      const pane = panes.get(target);
      if (!pane) {
        return false;
      }
      if (pane.dataset.sessionShellPaneStale === "1") {
        return false;
      }
      if (pane.dataset.sessionShellPaneLoaded === "1") {
        return true;
      }
      return pane.innerHTML.trim().length > 0;
    };

    const loadPane = async (target, viewIntentId) => {
      const pane = panes.get(target);
      if (!pane) {
        return false;
      }
      if (isPaneLoaded(target)) {
        pane.dataset.sessionShellPaneLoaded = "1";
        return true;
      }

      const fragmentUrl = pane.dataset.sessionShellPaneUrl || "";
      if (!fragmentUrl) {
        return true;
      }
      const lifecycleGeneration = characterLifecycleGeneration;

      const response = await fetch(fragmentUrl, {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
        cache: "no-store",
        credentials: "same-origin",
      });
      if (viewIntentId !== shellViewIntentId) {
        return true;
      }
      if (
        target === "character"
        && lifecycleGeneration !== characterLifecycleGeneration
      ) {
        return false;
      }
      if (!response.ok) {
        return false;
      }

      const html = await response.text();
      if (viewIntentId !== shellViewIntentId) {
        return true;
      }
      if (
        target === "character"
        && lifecycleGeneration !== characterLifecycleGeneration
      ) {
        return false;
      }
      return updatePaneHtml(target, html, { lifecycleGeneration });
    };

    const showOnlyPane = (target) => {
      const nextTarget = normalizeTarget(target);
      const nextPane = panes.get(nextTarget);
      const existingGuard = nextPane instanceof HTMLElement
        ? mountedPaneDraftGuards.get(nextPane)
        : null;
      if (typeof existingGuard === "function") {
        existingGuard();
      }
      let retainedDrafts = nextTarget === "character"
        ? []
        : captureMountedPaneDrafts(nextPane);
      let activationObserver = null;
      if (retainedDrafts.length > 0 && nextPane instanceof HTMLElement) {
        const refreshRetainedDrafts = () => {
          retainedDrafts = captureMountedPaneDrafts(nextPane);
        };
        const retireFormDraft = (form) => {
          retainedDrafts = retainedDrafts.filter((state) => (
            !formsMatchDescription(form, state.form)
          ));
        };
        const retireSubmittedFormDraft = (event) => {
          const form = event.target instanceof HTMLFormElement ? event.target : null;
          if (
            form
            && form.matches("[data-session-async], [data-destructive-confirmation-form]")
            && event.defaultPrevented
            && form.getAttribute("aria-busy") === "true"
          ) {
            retireFormDraft(form);
          }
        };
        const retireResetFormDraft = (event) => {
          const form = event.target instanceof HTMLFormElement ? event.target : null;
          if (form && !event.defaultPrevented) {
            retireFormDraft(form);
          }
        };
        nextPane.addEventListener("input", refreshRetainedDrafts);
        nextPane.addEventListener("change", refreshRetainedDrafts);
        nextPane.addEventListener("submit", retireSubmittedFormDraft);
        nextPane.addEventListener("reset", retireResetFormDraft);
        activationObserver = new MutationObserver(() => {
          restoreMountedPaneDrafts(nextPane, retainedDrafts);
        });
        activationObserver.observe(nextPane, { childList: true, subtree: true });
        const guardTimeoutId = window.setTimeout(() => {
          const cleanupGuard = mountedPaneDraftGuards.get(nextPane);
          if (typeof cleanupGuard === "function") {
            cleanupGuard();
          }
        }, 30000);
        const cleanupGuard = () => {
          activationObserver.disconnect();
          window.clearTimeout(guardTimeoutId);
          nextPane.removeEventListener("input", refreshRetainedDrafts);
          nextPane.removeEventListener("change", refreshRetainedDrafts);
          nextPane.removeEventListener("submit", retireSubmittedFormDraft);
          nextPane.removeEventListener("reset", retireResetFormDraft);
          if (mountedPaneDraftGuards.get(nextPane) === cleanupGuard) {
            mountedPaneDraftGuards.delete(nextPane);
          }
        };
        mountedPaneDraftGuards.set(nextPane, cleanupGuard);
      }
      for (const [paneTarget, pane] of panes.entries()) {
        pane.hidden = paneTarget !== nextTarget;
      }
      shellRoot.dataset.sessionShellActive = nextTarget;
      setActiveLivePane(nextPane);
      restoreMountedPaneDrafts(nextPane, retainedDrafts);
    };

    const syncSwitchButtons = (target) => {
      const nextTarget = normalizeTarget(target);
      for (const link of switchLinks) {
        const linkTarget = link.dataset.sessionSwitchTarget;
        link.classList.toggle("button-link", linkTarget === nextTarget);
        link.classList.toggle("ghost-button", linkTarget !== nextTarget);
      }
    };

    const submitCharacterPaneForm = async (event) => {
      const characterPane = panes.get("character");
      if (!characterPane) {
        return;
      }
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || !characterPane.contains(form)) {
        return;
      }
      const method = String(form.method || "get").toLowerCase();
      if (method !== "post") {
        return;
      }
      const action = form.getAttribute("action") || "";
      if (!action) {
        return;
      }

      const isSessionCurrencyForm = Boolean(
        form.querySelector("[data-session-currency-autosubmit='1']"),
      );
      event.preventDefault();
      const queuedIntent = queuedIntentByForm.get(form) || null;
      if (queuedIntent) {
        queuedIntentByForm.delete(form);
      }
      const intent = queuedIntent || captureAutosubmitIntent(form);
      if (!intent) {
        return;
      }
      if (activeMutation) {
        captureAllDirtyAutosubmits(characterPane, { excludeForm: form });
        enqueueIntent(intent);
        scheduleQueueDrain();
        return;
      }
      if (!queuedIntent) {
        queuePausedReason = "";
        removePendingIntent(intent.key);
      }
      captureAllDirtyAutosubmits(characterPane, { excludeForm: form });
      const submitter = event.submitter instanceof HTMLElement ? event.submitter : null;
      const postSubmitFocusKey = String(form.dataset.postSubmitFocusKey || "").trim();
      const formData = buildSubmitFormData(form, submitter);
      const submissionFingerprint = Array.from(formData.entries())
        .map(([name, value]) => (
          `${name}=${typeof value === "string" ? value : `[file:${value.name}:${value.size}]`}`
        ))
        .join("&");
      const submissionTime = window.performance.now();
      if (
        !queuedIntent
        &&
        form.dataset.sessionCharacterLastSubmission === submissionFingerprint
        && submissionTime - Number(form.dataset.sessionCharacterLastSubmissionAt || "0") < 1000
      ) {
        scheduleQueueDrain();
        return;
      }
      form.dataset.sessionCharacterLastSubmission = submissionFingerprint;
      form.dataset.sessionCharacterLastSubmissionAt = String(submissionTime);
      const submissionViewIntentId = shellViewIntentId;
      const submissionLifecycleGeneration = characterLifecycleGeneration;
      activeMutation = intent;
      abortCharacterSafeRead();
      clearVisitedCharacterFragments("mutation-start");
      characterPane.dispatchEvent(new CustomEvent("playerWiki:session-character-invalidated", {
        bubbles: true,
        detail: { reason: "mutation" },
      }));
      form.dataset.sessionCharacterSubmitting = "1";
      if (isSessionCurrencyForm) {
        form.dataset.sessionCurrencySubmitting = "1";
      }
      const submitControls = Array.from(form.querySelectorAll("button, input[type='submit']"));
      form.setAttribute("aria-busy", "true");
      for (const control of submitControls) {
        control.disabled = true;
      }
      const pauseMutation = (reason) => {
        if (activeMutation === intent) {
          activeMutation = null;
        }
        if (form.matches("[data-character-autosubmit]") && !pendingByKey.has(intent.key)) {
          enqueueIntent(intent);
        }
        queuePausedReason = reason;
        restoreAllQueuedDrafts(characterPane);
      };
      try {
        const response = await fetch(action, {
          method: "POST",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
          },
          body: formData,
          cache: "no-store",
          credentials: "same-origin",
        });
        if (submissionLifecycleGeneration !== characterLifecycleGeneration) {
          return;
        }
        const html = await response.text();
        if (submissionLifecycleGeneration !== characterLifecycleGeneration) {
          return;
        }
        const parsed = parseCharacterFragment(html);
        const responseIdentity = parsed ? describeCharacterIdentity(parsed.root) : null;
        const priorIdentity = currentCharacterIdentity(characterPane);
        const feedbackStatus = [400, 409, 422].includes(response.status);
        const sameSurfaceIdentity = Boolean(
          responseIdentity
          && priorIdentity
          && responseIdentity.character === priorIdentity.character
          && responseIdentity.page === priorIdentity.page
          && responseIdentity.activeSession === priorIdentity.activeSession
          && responseIdentity.access === priorIdentity.access
        );
        const confirmedSuccess = Boolean(
          response.ok
          && parsed
          && sameSurfaceIdentity
          && parsed.template.content.querySelector(
            "[data-session-character-flash-stack] .flash-success",
          )
        );
        if ((!confirmedSuccess && !feedbackStatus) || !parsed || !sameSurfaceIdentity) {
          showCharacterSectionGuidance(
            characterPane,
            "The save result could not be confirmed. Refresh Session and inspect the current sheet before repeating the action.",
          );
          pauseMutation(response.status === 503 ? "service-unavailable" : "ambiguous-response");
          return;
        }
        if (submissionLifecycleGeneration !== characterLifecycleGeneration) {
          return;
        }

        const restoreState = captureCharacterPaneRestoreState(characterPane);
        const revisionChanged = Boolean(
          priorIdentity
          && (
            responseIdentity.revision !== priorIdentity.revision
            || responseIdentity.projection !== priorIdentity.projection
          )
        );
        if (confirmedSuccess) {
          clearVisitedCharacterFragments("mutation-success");
        } else if (revisionChanged) {
          clearVisitedCharacterFragments("observed-character-revision");
        }
        try {
          commitCharacterNodes(
            characterPane,
            parsed.template.content,
            responseIdentity,
            {
              cacheCurrent: false,
              restoreState,
              restoreValues: true,
            },
          );
        } catch (_error) {
          showCharacterSectionGuidance(
            characterPane,
            "The save response could not be initialized. Refresh Session and inspect the current sheet before repeating the action.",
          );
          pauseMutation("mount-failed");
          return;
        }
        if (feedbackStatus) {
          if (activeMutation === intent) {
            activeMutation = null;
          }
          queuePausedReason = `feedback-${response.status}`;
          restoreAllQueuedDrafts(characterPane);
          const restoredForm = findMatchingForm(characterPane, intent.descriptor);
          if (
            restoredForm instanceof HTMLFormElement
            && restoredForm.matches("[data-character-autosubmit]")
          ) {
            restoredForm.dataset.characterAutosubmitState = describeAutosubmitFormState(restoredForm);
          }
        } else {
          if (activeMutation === intent) {
            activeMutation = null;
          }
          queuePausedReason = "";
          restoreAllQueuedDrafts(characterPane);
          scheduleQueueDrain();
        }
        const nextUrl = canonicalUrlFromCharacterFragment(
          parsed,
          characterPane.dataset.sessionShellPaneUrl || "",
        );
        const characterIntentStillCurrent = Boolean(
          submissionViewIntentId === shellViewIntentId
          && shellRoot.dataset.sessionShellActive === "character"
        );
        if (nextUrl) {
          rememberCharacterPaneUrl(nextUrl);
          if (characterIntentStillCurrent) {
            updateCharacterHistory(responseIdentity, nextUrl, { replace: true });
          }
        }
        if (!characterIntentStillCurrent) {
          return;
        }
        const nextCharacterPane = panes.get("character");
        if (postSubmitFocusKey && restoreFocusKey && nextCharacterPane) {
          window.requestAnimationFrame(() => {
            restoreFocusKey(nextCharacterPane, postSubmitFocusKey);
          });
        }
      } catch (_error) {
        if (submissionLifecycleGeneration === characterLifecycleGeneration) {
          showCharacterSectionGuidance(
            characterPane,
            "The save result could not be confirmed. Refresh Session and inspect the current sheet before repeating the action.",
          );
          pauseMutation("network-error");
        }
      } finally {
        if (form.isConnected) {
          delete form.dataset.sessionCharacterSubmitting;
          delete form.dataset.sessionCurrencySubmitting;
          form.removeAttribute("aria-busy");
          for (const control of submitControls) {
            control.disabled = false;
          }
        }
      }
    };

    const reconcileHistoryToMountedShellView = () => {
      const mountedTarget = normalizeTarget(shellRoot.dataset.sessionShellActive || "session");
      if (mountedTarget === "character") {
        const pane = panes.get("character");
        const identity = currentCharacterIdentity(pane);
        const canonicalUrl = canonicalUrlFromMountedCharacterPane(pane);
        if (identity && canonicalUrl) {
          rememberCharacterPaneUrl(canonicalUrl);
          updateCharacterHistory(identity, canonicalUrl, { replace: true });
          return true;
        }
        return false;
      }
      const mountedLink = switchLinks.find((link) => (
        link.dataset.sessionSwitchTarget === mountedTarget
      ));
      const mountedUrl = mountedLink
        ? mountedLink.dataset.sessionSwitchFullHref || mountedLink.getAttribute("href") || ""
        : "";
      if (!mountedUrl) {
        return false;
      }
      history.replaceState(
        {
          ...(history.state || {}),
          sessionShellView: mountedTarget,
        },
        "",
        mountedUrl,
      );
      return true;
    };

    const showShellView = async (target, { url = "", fromHistory = false } = {}) => {
      const nextTarget = normalizeTarget(target);
      const characterPane = panes.get("character");
      if (
        nextTarget !== "character"
        && shellRoot.dataset.sessionShellActive === "character"
        && characterPane instanceof HTMLElement
      ) {
        captureAllDirtyAutosubmits(characterPane);
        scheduleQueueDrain();
        if (blockCharacterNavigationForMutations(characterPane)) {
          return false;
        }
      }
      const viewIntentId = ++shellViewIntentId;
      const lifecycleGeneration = characterLifecycleGeneration;
      shellViewIntentTarget = nextTarget;
      if (nextTarget !== "character") {
        abortCharacterSafeRead();
      }
      shellRoot.dispatchEvent(new CustomEvent("playerWiki:session-shell-view-intent", {
        detail: { target: nextTarget },
      }));
      const loaded = await loadPane(nextTarget, viewIntentId);
      if (
        viewIntentId !== shellViewIntentId
        || (
          nextTarget === "character"
          && lifecycleGeneration !== characterLifecycleGeneration
        )
      ) {
        return false;
      }
      if (!loaded) {
        if (url) {
          window.location.assign(url);
        }
        return false;
      }

      showOnlyPane(nextTarget);
      syncSwitchButtons(nextTarget);
      if (!fromHistory && url) {
        const nextState = {
          ...(history.state || {}),
          sessionShellView: nextTarget,
        };
        if (nextTarget === "character") {
          const identity = currentCharacterIdentity();
          if (identity) {
            nextState.sessionCharacterPage = identity.page;
          }
        }
        history.pushState(nextState, "", url);
      }
      return true;
    };

    const clickHandler = async (event) => {
      const link = event.target instanceof Element ? event.target.closest("[data-session-switch='1']") : null;
      if (!link) {
        return;
      }
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button === 1) {
        return;
      }

      const target = link.dataset.sessionSwitchTarget || "";
      if (!panes.has(target)) {
        return;
      }
      if (
        shellRoot.dataset.sessionShellActive === target
        && shellViewIntentTarget === target
      ) {
        event.preventDefault();
        return;
      }

      const href = link.dataset.sessionSwitchFullHref || link.getAttribute("href") || "";
      if (!href) {
        return;
      }

      event.preventDefault();
      await showShellView(target, { url: href });
    };

    const initialTarget = normalizeTarget(shellRoot.dataset.sessionShellActive || getTargetFromUrl());
    shellViewIntentTarget = initialTarget;
    initMountedPanes();
    showOnlyPane(initialTarget);
    syncSwitchButtons(initialTarget);
    if (initialTarget === "character") {
      const initialCharacterIdentity = currentCharacterIdentity();
      if (initialCharacterIdentity) {
        updateCharacterHistory(
          initialCharacterIdentity,
          `${window.location.pathname}${window.location.search}${window.location.hash}`,
          { replace: true },
        );
      }
    }

    window.addEventListener("popstate", async (event) => {
      const stateTarget = event.state && typeof event.state.sessionShellView === "string" ? event.state.sessionShellView : "";
      const resolved = normalizeTarget(stateTarget || getTargetFromUrl());
      const shownPromise = showShellView(resolved, { fromHistory: true });
      const popstateViewIntentId = shellViewIntentId;
      const popstateLifecycleGeneration = characterLifecycleGeneration;
      const shown = await shownPromise;
      if (!shown) {
        if (
          popstateViewIntentId === shellViewIntentId
          && popstateLifecycleGeneration === characterLifecycleGeneration
        ) {
          reconcileHistoryToMountedShellView();
        }
        return;
      }
      if (resolved !== "character") {
        return;
      }
      const pane = panes.get("character");
      const currentIdentity = currentCharacterIdentity(pane);
      const statePage = event.state && typeof event.state.sessionCharacterPage === "string"
        ? event.state.sessionCharacterPage
        : "";
      const targetPage = statePage || new URL(window.location.href).searchParams.get("page") || "overview";
      if (!currentIdentity || currentIdentity.page === targetPage || !(pane instanceof HTMLElement)) {
        return;
      }
      const targetLink = Array.from(
        pane.querySelectorAll("[data-session-character-section-link]"),
      ).find((candidate) => (
        candidate instanceof HTMLAnchorElement
        && candidate.dataset.sessionCharacterSectionLink === targetPage
      ));
      if (targetLink instanceof HTMLAnchorElement) {
        const navigated = await navigateCharacterSection(targetLink, {
          fromHistory: true,
          historyUrl: `${window.location.pathname}${window.location.search}${window.location.hash}`,
        });
        if (
          !navigated
          && popstateViewIntentId === shellViewIntentId
          && popstateLifecycleGeneration === characterLifecycleGeneration
          && shellRoot.dataset.sessionShellActive === "character"
        ) {
          reconcileHistoryToMountedShellView();
        }
      }
    });

    shellRoot.addEventListener("click", (event) => {
      clickHandler(event).catch(() => {
        const clickedLink = event.target instanceof Element ? event.target.closest("[data-session-switch='1']") : null;
        if (!clickedLink) {
          return;
        }
        const nextUrl = clickedLink.dataset.sessionSwitchFullHref || clickedLink.getAttribute("href");
        if (nextUrl) {
          window.location.assign(nextUrl);
        }
      });
    });

    const characterPane = panes.get("character");
    if (characterPane) {
      characterPane.addEventListener("click", (event) => {
        const link = event.target instanceof Element
          ? event.target.closest("[data-session-character-section-link]")
          : null;
        if (!(link instanceof HTMLAnchorElement) || !characterPane.contains(link)) {
          return;
        }
        if (
          event.defaultPrevented
          || event.ctrlKey
          || event.metaKey
          || event.shiftKey
          || event.altKey
          || event.button === 1
          || link.dataset.sessionCharacterFallbackOnly === "1"
        ) {
          return;
        }
        event.preventDefault();
        navigateCharacterSection(link).catch(() => {
          showCharacterSectionGuidance(
            characterPane,
            "That section could not be loaded. Follow its full-page link to continue.",
          );
        });
      });

      characterPane.addEventListener("submit", (event) => {
        submitCharacterPaneForm(event).catch(() => {
          showCharacterSectionGuidance(
            characterPane,
            "The save result could not be confirmed. Refresh Session and inspect the current sheet before repeating the action.",
          );
        });
      });

      characterPane.addEventListener("change", (event) => {
        const field = event.target instanceof Element
          ? event.target.closest("[data-session-currency-autosubmit='1']")
          : null;
        if (!(field instanceof HTMLInputElement) || !characterPane.contains(field)) {
          return;
        }
        if (field.form) {
          window.clearTimeout(Number(field.form.dataset.characterAutosubmitTimer || "0"));
          field.form.dataset.characterAutosubmitTimer = "0";
          field.form.requestSubmit();
        }
      });
    }

    shellRoot.addEventListener("playerWiki:session-state-changed", (event) => {
      const characterPane = panes.get("character");
      if (!characterPane || characterPane.contains(event.target)) {
        return;
      }
      characterLifecycleGeneration += 1;
      invalidateMutationQueue();
      abortCharacterSafeRead();
      clearVisitedCharacterFragments("active-session-lifecycle");
      characterPane.dataset.sessionShellPaneLoaded = "0";
      characterPane.dataset.sessionShellPaneStale = "1";
    });
  })();

  (() => {
    const dmShellRoot = document.querySelector("[data-session-dm-shell-root]");
    if (!(dmShellRoot instanceof HTMLElement)) {
      return;
    }
    const dmLiveRoot = dmShellRoot.closest("[data-session-live-root]");

    const switchLinks = Array.from(
      dmShellRoot.querySelectorAll("[data-session-dm-switch='1']"),
    );
    const panes = new Map(
      Array.from(dmShellRoot.querySelectorAll("[data-session-dm-pane]"))
        .map((pane) => [pane.dataset.sessionDmPane || "", pane])
        .filter(([target]) => target),
    );
    const uiStateTools = window.__playerWikiLiveUiTools || null;
    let navigationRequestId = 0;
    const paneUiStates = new Map();
    let pointerNavigationCapture = null;
    let articleStoreLastFocusedViewport = null;

    const capturePaneUiState = (target) => {
      if (!target || !(dmLiveRoot instanceof HTMLElement) || !uiStateTools) {
        return;
      }
      const pane = panes.get(target);
      const activeElement = document.activeElement;
      const articleStoreQueryFocus = (
        target === "article-store"
        && pane instanceof HTMLElement
        && activeElement instanceof HTMLInputElement
        && pane.contains(activeElement)
        && activeElement.matches("[data-session-article-source-query]")
      )
        ? {
            selectionStart: activeElement.selectionStart,
            selectionEnd: activeElement.selectionEnd,
          }
        : null;
      paneUiStates.set(target, {
        focus: uiStateTools.captureFocus(dmLiveRoot),
        viewport: uiStateTools.captureViewportAnchor(dmLiveRoot),
        scrollX: window.scrollX,
        scrollY: window.scrollY,
        articleStoreQueryFocus,
      });
    };

    const restorePaneUiState = (target) => {
      if (!(dmLiveRoot instanceof HTMLElement) || !uiStateTools || !paneUiStates.has(target)) {
        return;
      }
      const state = paneUiStates.get(target);
      uiStateTools.restoreFocus(dmLiveRoot, state.focus);
      uiStateTools.restoreViewportAnchor(dmLiveRoot, state.viewport);
      window.scrollTo(Number(state.scrollX || 0), Number(state.scrollY || 0));
      if (state.articleStoreQueryFocus) {
        const pane = panes.get(target);
        const query = pane instanceof HTMLElement
          ? pane.querySelector("[data-session-article-source-query]")
          : null;
        if (query instanceof HTMLInputElement) {
          query.focus({ preventScroll: true });
          if (
            typeof state.articleStoreQueryFocus.selectionStart === "number"
            && typeof state.articleStoreQueryFocus.selectionEnd === "number"
          ) {
            query.setSelectionRange(
              state.articleStoreQueryFocus.selectionStart,
              state.articleStoreQueryFocus.selectionEnd,
            );
          }
        }
      }
    };

    const rememberArticleStoreFocusedViewport = (event) => {
      const query = event.target instanceof Element
        ? event.target.closest("[data-session-article-source-query]")
        : null;
      const pane = panes.get("article-store");
      if (
        !(query instanceof HTMLInputElement)
        || !(pane instanceof HTMLElement)
        || !pane.contains(query)
        || pane.hidden
        || !(dmLiveRoot instanceof HTMLElement)
        || !uiStateTools
      ) {
        return;
      }
      articleStoreLastFocusedViewport = {
        query,
        viewport: uiStateTools.captureViewportAnchor(dmLiveRoot),
        scrollX: window.scrollX,
        scrollY: window.scrollY,
      };
    };

    dmShellRoot.addEventListener("focusin", rememberArticleStoreFocusedViewport);
    dmShellRoot.addEventListener("input", rememberArticleStoreFocusedViewport);
    dmShellRoot.addEventListener("select", rememberArticleStoreFocusedViewport);

    const stagedEditFormSelector = "form.session-article-edit-form";

    const stagedArticleIdFor = (node) => {
      const articleDetail = node instanceof Element
        ? node.closest("details[data-session-article-id]")
        : null;
      return articleDetail instanceof HTMLElement
        ? String(articleDetail.dataset.sessionArticleId || "")
        : "";
    };

    const isDirtyStagedEditForm = (form) => {
      if (!(form instanceof HTMLFormElement) || !form.matches(stagedEditFormSelector)) {
        return false;
      }
      for (const field of form.querySelectorAll("input[name], textarea[name]")) {
        if (field instanceof HTMLInputElement && field.type === "file") {
          if (field.files && field.files.length) {
            return true;
          }
          continue;
        }
        if (
          (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement)
          && field.value !== field.defaultValue
        ) {
          return true;
        }
      }
      return !form.checkValidity();
    };

    const openStagedDetailKeys = (root) => {
      const keys = new Set();
      if (!(root instanceof Element)) {
        return keys;
      }
      for (const detail of root.querySelectorAll("details[open]")) {
        const articleId = stagedArticleIdFor(detail);
        if (!articleId) {
          continue;
        }
        keys.add(`${articleId}:${detail.matches(".session-article-edit-detail") ? "edit" : "article"}`);
      }
      return keys;
    };

    const restoreStagedDetailKeys = (root, keys) => {
      if (!(root instanceof Element)) {
        return;
      }
      for (const detail of root.querySelectorAll("details")) {
        const articleId = stagedArticleIdFor(detail);
        if (!articleId) {
          continue;
        }
        const key = `${articleId}:${detail.matches(".session-article-edit-detail") ? "edit" : "article"}`;
        detail.open = keys.has(key);
      }
    };

    const replaceStagedHtml = (
      container,
      html,
      { preserveDirtyForms = true, ignoreDirtyArticleIds = [] } = {},
    ) => {
      if (!(container instanceof HTMLElement) || typeof html !== "string") {
        return { applied: false, retainedUnmatchedDirtyForm: false };
      }
      const ignoredIds = new Set(Array.from(ignoreDirtyArticleIds, (value) => String(value || "")));
      const dirtyEditDetails = new Map();
      if (preserveDirtyForms) {
        for (const form of container.querySelectorAll(stagedEditFormSelector)) {
          const articleId = stagedArticleIdFor(form);
          const editDetail = form.closest("details.session-article-edit-detail");
          if (
            articleId
            && !ignoredIds.has(articleId)
            && editDetail instanceof HTMLDetailsElement
            && isDirtyStagedEditForm(form)
          ) {
            dirtyEditDetails.set(articleId, editDetail);
          }
        }
      }

      const openDetailKeys = openStagedDetailKeys(container);
      const parsed = document.createElement("template");
      parsed.innerHTML = html;
      for (const [articleId, retainedEditDetail] of dirtyEditDetails.entries()) {
        const incomingArticle = Array.from(
          parsed.content.querySelectorAll("details[data-session-article-id]"),
        ).find((detail) => String(detail.dataset.sessionArticleId || "") === articleId);
        const incomingEditDetail = incomingArticle instanceof Element
          ? incomingArticle.querySelector("details.session-article-edit-detail")
          : null;
        if (!(incomingEditDetail instanceof HTMLDetailsElement)) {
          return { applied: false, retainedUnmatchedDirtyForm: true };
        }
        incomingEditDetail.replaceWith(retainedEditDetail);
      }

      container.replaceChildren(parsed.content);
      restoreStagedDetailKeys(container, openDetailKeys);
      return { applied: true, retainedUnmatchedDirtyForm: false };
    };

    window.__playerWikiSessionStagedState = {
      isDirtyEditForm: isDirtyStagedEditForm,
      replaceHtml: replaceStagedHtml,
    };

    const articleStoreFormSelector = "form[data-session-article-form][data-session-article-mode-root]";
    const normalizeArticleMode = (value) => {
      const normalized = String(value || "").trim().toLowerCase();
      return ["manual", "upload", "wiki"].includes(normalized) ? normalized : "manual";
    };

    const articleStoreFormHasMeaningfulState = (form) => {
      if (!(form instanceof HTMLFormElement) || !form.matches(articleStoreFormSelector)) {
        return false;
      }
      const selectedMode = normalizeArticleMode(
        form.querySelector('input[name="article_mode"]:checked')?.value || "manual",
      );
      const defaultMode = normalizeArticleMode(
        Array.from(form.querySelectorAll('input[name="article_mode"]'))
          .find((field) => field instanceof HTMLInputElement && field.defaultChecked)?.value || "manual",
      );
      if (
        selectedMode !== defaultMode
        || !form.checkValidity()
        || form.getAttribute("aria-invalid") === "true"
        || form.dataset.sessionArticleValidationRetained === "1"
      ) {
        return true;
      }
      for (const field of form.querySelectorAll("input[name], textarea[name], select[name]")) {
        if (field instanceof HTMLInputElement) {
          if (field.type === "hidden" || field.type === "radio") {
            continue;
          }
          if (field.type === "file") {
            if (field.files && field.files.length) {
              return true;
            }
            continue;
          }
          if (field.value !== field.defaultValue) {
            return true;
          }
        } else if (field instanceof HTMLTextAreaElement && field.value !== field.defaultValue) {
          return true;
        } else if (field instanceof HTMLSelectElement) {
          const defaultOption = Array.from(field.options).find((option) => option.defaultSelected);
          if (
            field.value !== String(defaultOption?.value || "")
            || !field.disabled
            || field.options.length > 1
          ) {
            return true;
          }
        }
      }
      const query = form.querySelector("[data-session-article-source-query]");
      if (query instanceof HTMLInputElement && query.value) {
        return true;
      }
      const recovery = form.querySelector("[data-session-article-mutation-recovery]");
      return recovery instanceof HTMLElement && !recovery.hidden;
    };

    const replaceArticleStoreHtml = (container, html) => {
      if (!(container instanceof HTMLElement) || typeof html !== "string") {
        return { applied: false, retainedMeaningfulState: false };
      }
      const form = container.querySelector(articleStoreFormSelector);
      if (articleStoreFormHasMeaningfulState(form)) {
        return { applied: false, retainedMeaningfulState: true };
      }
      const parsed = document.createElement("template");
      parsed.innerHTML = html;
      container.replaceChildren(parsed.content);
      return { applied: true, retainedMeaningfulState: false };
    };

    window.__playerWikiSessionArticleStoreState = {
      hasMeaningfulState: articleStoreFormHasMeaningfulState,
      replaceHtml: replaceArticleStoreHtml,
    };

    const updateArticleStoreModeUrl = (mode, { updateHistory = false } = {}) => {
      const pane = panes.get("article-store");
      if (!(pane instanceof HTMLElement)) {
        return;
      }
      const normalizedMode = normalizeArticleMode(mode);
      const fragmentUrl = new URL(pane.dataset.sessionDmPaneUrl || window.location.href, window.location.href);
      fragmentUrl.searchParams.set("dm_view", "article-store");
      fragmentUrl.searchParams.set("article_mode", normalizedMode);
      pane.dataset.sessionDmPaneUrl = `${fragmentUrl.pathname}${fragmentUrl.search}`;
      const link = switchLinks.find((candidate) => (
        candidate.dataset.sessionDmSwitchTarget === "article-store"
      ));
      if (link instanceof HTMLAnchorElement) {
        link.href = pane.dataset.sessionDmPaneUrl;
      }
      if (updateHistory && dmShellRoot.dataset.sessionDmActive === "article-store") {
        const currentUrl = new URL(window.location.href);
        currentUrl.searchParams.set("dm_view", "article-store");
        currentUrl.searchParams.set("article_mode", normalizedMode);
        history.replaceState({ sessionDmView: "article-store" }, "", currentUrl.href);
      }
    };

    const invalidatePendingDmNavigation = () => {
      navigationRequestId += 1;
    };

    const normalizeTarget = (target) => {
      const normalized = String(target || "").trim().toLowerCase();
      return panes.has(normalized) ? normalized : "";
    };

    const isPaneLoaded = (pane) => (
      pane instanceof HTMLElement
      && pane.dataset.sessionDmPaneLoaded === "1"
      && pane.dataset.sessionDmPaneStale !== "1"
    );

    const loadPane = async (pane, requestId) => {
      if (!(pane instanceof HTMLElement)) {
        return false;
      }
      if (isPaneLoaded(pane)) {
        return true;
      }
      const fragmentUrl = pane.dataset.sessionDmPaneUrl || "";
      if (!fragmentUrl) {
        return false;
      }
      const response = await fetch(fragmentUrl, {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) {
        return false;
      }
      const html = await response.text();
      if (navigationRequestId !== requestId) {
        return false;
      }
      const openArticleIds = new Set(
        Array.from(pane.querySelectorAll("details[data-session-article-id][open]"))
          .map((detail) => detail.dataset.sessionArticleId || "")
          .filter(Boolean),
      );
      const focusState = uiStateTools && dmLiveRoot instanceof HTMLElement
        ? uiStateTools.captureFocus(dmLiveRoot)
        : null;
      const viewportAnchor = uiStateTools && dmLiveRoot instanceof HTMLElement
        ? uiStateTools.captureViewportAnchor(dmLiveRoot)
        : null;
      const stagedReplacement = pane.dataset.sessionDmPane === "staged"
        ? replaceStagedHtml(pane, html)
        : null;
      const articleStoreReplacement = pane.dataset.sessionDmPane === "article-store"
        ? replaceArticleStoreHtml(pane, html)
        : null;
      if (stagedReplacement && !stagedReplacement.applied) {
        if (stagedReplacement.retainedUnmatchedDirtyForm) {
          pane.dataset.sessionDmPaneLoaded = "1";
          pane.dataset.sessionDmPaneStale = "1";
          return true;
        }
        return false;
      }
      if (articleStoreReplacement && !articleStoreReplacement.applied) {
        if (articleStoreReplacement.retainedMeaningfulState) {
          pane.dataset.sessionDmPaneLoaded = "1";
          pane.dataset.sessionDmPaneStale = "1";
          return true;
        }
        return false;
      }
      if (!stagedReplacement && !articleStoreReplacement) {
        pane.innerHTML = html;
        for (const detail of pane.querySelectorAll("details[data-session-article-id]")) {
          if (openArticleIds.has(detail.dataset.sessionArticleId || "")) {
            detail.open = true;
          }
        }
      }
      pane.dataset.sessionDmPaneLoaded = "1";
      delete pane.dataset.sessionDmPaneStale;
      if (
        dmLiveRoot instanceof HTMLElement
        && window.__playerWikiSessionLive
        && typeof window.__playerWikiSessionLive.rebindRegions === "function"
      ) {
        window.__playerWikiSessionLive.rebindRegions(dmLiveRoot);
      }
      if (
        window.__playerWikiPresentationController
        && typeof window.__playerWikiPresentationController.init === "function"
      ) {
        window.__playerWikiPresentationController.init(pane);
      }
      if (pane.dataset.sessionDmPane === "article-store") {
        const form = pane.querySelector(articleStoreFormSelector);
        updateArticleStoreModeUrl(
          form?.querySelector('input[name="article_mode"]:checked')?.value || "manual",
        );
      }
      if (uiStateTools && dmLiveRoot instanceof HTMLElement) {
        uiStateTools.restoreFocus(dmLiveRoot, focusState);
        uiStateTools.restoreViewportAnchor(dmLiveRoot, viewportAnchor);
      }
      return true;
    };

    const syncLinks = (target) => {
      for (const link of switchLinks) {
        const isActive = link.dataset.sessionDmSwitchTarget === target;
        link.classList.toggle("button-link", isActive);
        link.classList.toggle("ghost-button", !isActive);
        if (isActive) {
          link.setAttribute("aria-current", "page");
        } else {
          link.removeAttribute("aria-current");
        }
      }
    };

    const showPane = async (
      target,
      url,
      { fromHistory = false, capturedPreviousTarget = "" } = {},
    ) => {
      const requestId = navigationRequestId + 1;
      navigationRequestId = requestId;
      const normalizedTarget = normalizeTarget(target);
      const pane = panes.get(normalizedTarget);
      if (!normalizedTarget || !(pane instanceof HTMLElement)) {
        return false;
      }
      const previousTarget = normalizeTarget(dmShellRoot.dataset.sessionDmActive || "");
      const hasRetainedUiState = paneUiStates.has(normalizedTarget);
      if (
        previousTarget
        && previousTarget !== normalizedTarget
        && capturedPreviousTarget !== previousTarget
      ) {
        capturePaneUiState(previousTarget);
      }
      if (!(await loadPane(pane, requestId))) {
        if (navigationRequestId !== requestId) {
          return true;
        }
        return false;
      }
      for (const [paneTarget, candidate] of panes.entries()) {
        candidate.hidden = paneTarget !== normalizedTarget;
      }
      dmShellRoot.dataset.sessionDmActive = normalizedTarget;
      syncLinks(normalizedTarget);
      if (hasRetainedUiState) {
        restorePaneUiState(normalizedTarget);
      } else {
        pane.scrollIntoView({ block: "start" });
      }
      if (url && !fromHistory) {
        const historyUrl = normalizedTarget === "article-store"
          ? pane.dataset.sessionDmPaneUrl || url
          : url;
        history.pushState({ sessionDmView: normalizedTarget }, "", historyUrl);
      }
      return true;
    };

    dmShellRoot.addEventListener("pointerdown", (event) => {
      pointerNavigationCapture = null;
      const link = event.target instanceof Element
        ? event.target.closest("[data-session-dm-switch='1']")
        : null;
      if (
        !(link instanceof HTMLAnchorElement)
        || !dmShellRoot.contains(link)
        || event.button !== 0
        || event.ctrlKey
        || event.metaKey
        || event.shiftKey
        || event.altKey
      ) {
        return;
      }
      const target = normalizeTarget(link.dataset.sessionDmSwitchTarget || "");
      const previousTarget = normalizeTarget(dmShellRoot.dataset.sessionDmActive || "");
      if (!target || !previousTarget || previousTarget === target) {
        return;
      }
      const activeElement = document.activeElement;
      const retainedArticleStoreViewport = (
        previousTarget === "article-store"
        && activeElement instanceof HTMLInputElement
        && activeElement.matches("[data-session-article-source-query]")
        && articleStoreLastFocusedViewport?.query === activeElement
      )
        ? articleStoreLastFocusedViewport
        : null;
      capturePaneUiState(previousTarget);
      const capturedState = paneUiStates.get(previousTarget);
      if (retainedArticleStoreViewport && capturedState) {
        capturedState.viewport = retainedArticleStoreViewport.viewport;
        capturedState.scrollX = retainedArticleStoreViewport.scrollX;
        capturedState.scrollY = retainedArticleStoreViewport.scrollY;
      }
      pointerNavigationCapture = { link, previousTarget };
    });

    dmShellRoot.addEventListener("click", (event) => {
      const link = event.target instanceof Element
        ? event.target.closest("[data-session-dm-switch='1']")
        : null;
      const capturedPreviousTarget = (
        event.detail > 0
        && pointerNavigationCapture?.link === link
      )
        ? pointerNavigationCapture.previousTarget
        : "";
      pointerNavigationCapture = null;
      if (!(link instanceof HTMLAnchorElement) || !dmShellRoot.contains(link)) {
        return;
      }
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button === 1) {
        return;
      }
      const target = normalizeTarget(link.dataset.sessionDmSwitchTarget || "");
      if (!target) {
        return;
      }
      if (dmShellRoot.dataset.sessionDmActive === target) {
        invalidatePendingDmNavigation();
        event.preventDefault();
        return;
      }
      const href = link.getAttribute("href") || "";
      event.preventDefault();
      showPane(target, href, { capturedPreviousTarget }).then((shown) => {
        if (!shown && href) {
          window.location.assign(href);
        }
      }).catch(() => {
        if (href) {
          window.location.assign(href);
        }
      });
    });

    dmShellRoot.addEventListener("change", (event) => {
      const modeField = event.target instanceof Element
        ? event.target.closest('input[name="article_mode"]')
        : null;
      if (!(modeField instanceof HTMLInputElement) || !modeField.checked) {
        return;
      }
      const form = modeField.closest(articleStoreFormSelector);
      if (!(form instanceof HTMLFormElement) || !dmShellRoot.contains(form)) {
        return;
      }
      updateArticleStoreModeUrl(modeField.value, { updateHistory: true });
    });

    const sessionShellRoot = dmShellRoot.closest("[data-session-shell-root]");
    if (sessionShellRoot instanceof HTMLElement) {
      sessionShellRoot.addEventListener("playerWiki:session-shell-view-intent", (event) => {
        const target = event instanceof CustomEvent && event.detail
          ? String(event.detail.target || "")
          : "";
        if (target && target !== "dm") {
          invalidatePendingDmNavigation();
        }
      });
    }

    const managerStateEventRoot = dmLiveRoot instanceof HTMLElement ? dmLiveRoot : dmShellRoot;
    managerStateEventRoot.addEventListener("playerWiki:session-manager-state-changed", (event) => {
      for (const pane of panes.values()) {
        if (pane.hidden && !pane.contains(event.target)) {
          pane.dataset.sessionDmPaneStale = "1";
        }
      }
    });

    window.addEventListener("popstate", () => {
      const currentUrl = new URL(window.location.href);
      const target = normalizeTarget(currentUrl.searchParams.get("dm_view") || "");
      if (!target) {
        return;
      }
      showPane(target, "", { fromHistory: true }).then((shown) => {
        if (!shown) {
          window.location.assign(currentUrl.href);
        }
      }).catch(() => {
        window.location.assign(currentUrl.href);
      });
    });

    const initialTarget = normalizeTarget(dmShellRoot.dataset.sessionDmActive || "");
    if (initialTarget) {
      const initialPane = panes.get(initialTarget);
      if (initialPane instanceof HTMLElement) {
        initialPane.dataset.sessionDmPaneLoaded = "1";
      }
      syncLinks(initialTarget);
      if (initialTarget === "article-store" && initialPane instanceof HTMLElement) {
        const form = initialPane.querySelector(articleStoreFormSelector);
        updateArticleStoreModeUrl(
          form?.querySelector('input[name="article_mode"]:checked')?.value || "manual",
        );
      }
    }
  })();
