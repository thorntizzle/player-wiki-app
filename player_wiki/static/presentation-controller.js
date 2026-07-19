(() => {
  "use strict";

  const DIALOG_SELECTOR = "[data-presentation-dialog]";
  const TRIGGER_SELECTOR = "[data-presentation-dialog-trigger]";
  const CLOSE_SELECTOR = "[data-presentation-dialog-close]";
  const INITIAL_FOCUS_SELECTOR = "[data-presentation-dialog-initial-focus]";
  const initializedDialogs = new WeakSet();
  const returnFocusTargets = new WeakMap();

  const hasExplicitLabel = (dialog) => {
    const ariaLabel = (dialog.getAttribute("aria-label") || "").trim();
    if (ariaLabel) {
      return true;
    }

    const labelledBy = (dialog.getAttribute("aria-labelledby") || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    return labelledBy.length > 0 && labelledBy.every(
      (id) => dialog.ownerDocument.getElementById(id),
    );
  };

  const isOwnedDialog = (value) => (
    value instanceof HTMLElement
    && value.matches(DIALOG_SELECTOR)
    && value.tagName.toLowerCase() === "dialog"
    && hasExplicitLabel(value)
  );

  const returnFocus = (dialog) => {
    const target = returnFocusTargets.get(dialog);
    returnFocusTargets.delete(dialog);
    if (target instanceof HTMLElement && target.isConnected) {
      target.focus({ preventScroll: true });
    }
  };

  const closeDialog = (dialog) => {
    if (!isOwnedDialog(dialog) || !dialog.hasAttribute("open")) {
      return false;
    }
    if (typeof dialog.close === "function") {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
      dialog.dispatchEvent(new Event("close"));
    }
    return true;
  };

  const initializeDialog = (dialog) => {
    if (!isOwnedDialog(dialog) || initializedDialogs.has(dialog)) {
      return false;
    }

    for (const closeControl of dialog.querySelectorAll(CLOSE_SELECTOR)) {
      closeControl.addEventListener("click", () => closeDialog(dialog));
    }
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        closeDialog(dialog);
      }
    });
    dialog.addEventListener("close", () => returnFocus(dialog));
    initializedDialogs.add(dialog);
    return true;
  };

  const init = (scope = document) => {
    if (!(scope instanceof Document) && !(scope instanceof Element)) {
      return 0;
    }

    const dialogs = [];
    if (scope instanceof Element && scope.matches(DIALOG_SELECTOR)) {
      dialogs.push(scope);
    }
    dialogs.push(...scope.querySelectorAll(DIALOG_SELECTOR));
    const initializedCount = dialogs.reduce(
      (count, dialog) => count + (initializeDialog(dialog) ? 1 : 0),
      0,
    );
    const triggers = [];
    if (scope instanceof Element && scope.matches(TRIGGER_SELECTOR)) {
      triggers.push(scope);
    }
    triggers.push(...scope.querySelectorAll(TRIGGER_SELECTOR));
    for (const trigger of triggers) {
      const dialogId = (trigger.getAttribute("data-presentation-dialog-trigger") || "").trim();
      const dialog = dialogId ? trigger.ownerDocument.getElementById(dialogId) : null;
      if (isOwnedDialog(dialog)) {
        trigger.removeAttribute("hidden");
      }
    }
    return initializedCount;
  };

  const openDialog = (dialog, returnFocusTarget = null) => {
    if (!isOwnedDialog(dialog)) {
      return false;
    }
    initializeDialog(dialog);
    if (returnFocusTarget instanceof HTMLElement) {
      returnFocusTargets.set(dialog, returnFocusTarget);
    } else {
      returnFocusTargets.delete(dialog);
    }

    if (!dialog.hasAttribute("open")) {
      if (typeof dialog.showModal === "function") {
        dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
    }

    const initialFocus = dialog.querySelector(INITIAL_FOCUS_SELECTOR);
    if (initialFocus instanceof HTMLElement) {
      initialFocus.focus({ preventScroll: true });
    }
    return true;
  };

  const controller = Object.freeze({
    init,
    openDialog,
    closeDialog,
  });
  window.__playerWikiPresentationController = controller;
  document.addEventListener("click", (event) => {
    const trigger = event.target instanceof Element
      ? event.target.closest(TRIGGER_SELECTOR)
      : null;
    if (!(trigger instanceof HTMLElement)) {
      return;
    }
    const dialogId = (trigger.getAttribute("data-presentation-dialog-trigger") || "").trim();
    const dialog = dialogId ? trigger.ownerDocument.getElementById(dialogId) : null;
    if (openDialog(dialog, trigger)) {
      event.preventDefault();
    }
  });
  controller.init(document);
})();
