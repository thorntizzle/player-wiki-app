import React, { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import type { CampaignReferenceSearchResult } from "../api/types";
import { useApiClient } from "../apiClientContext";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

function formatSearchStatus(message: string | undefined, resultCount: number): string {
  const trimmedMessage = message?.trim();
  if (trimmedMessage) {
    return trimmedMessage;
  }
  if (resultCount > 0) {
    return `Found ${resultCount} matching reference${resultCount === 1 ? "" : "s"}.`;
  }
  return "No visible wiki pages or Systems entries matched that search.";
}

export function CampaignGlobalSearch({ campaignSlug }: { campaignSlug: string }) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [query, setQuery] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [results, setResults] = useState<CampaignReferenceSearchResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isDialogOpen, setDialogOpen] = useState(false);

  const searchDebounceTimer = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const searchAbortController = useRef<AbortController | null>(null);
  const previewAbortController = useRef<AbortController | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  const clearSearchState = (status: string) => {
    setStatusMessage(status);
    setResults([]);
    setShowResults(false);
  };

  const clearPendingSearch = () => {
    if (searchDebounceTimer.current !== null) {
      window.clearTimeout(searchDebounceTimer.current);
      searchDebounceTimer.current = null;
    }
    if (searchAbortController.current) {
      searchAbortController.current.abort();
      searchAbortController.current = null;
    }
  };

  const runSearch = async (rawQuery: string) => {
    const trimmedQuery = rawQuery.trim();
    if (!trimmedQuery) {
      clearSearchState("");
      return;
    }
    if (trimmedQuery.length < 2) {
      clearSearchState("Type at least 2 letters to search.");
      return;
    }

    if (searchAbortController.current) {
      searchAbortController.current.abort();
    }
    const controller = new AbortController();
    searchAbortController.current = controller;
    setStatusMessage("Searching...");
    setShowResults(false);

    try {
      const response = await apiClient.searchCampaignReferences(campaignSlug, trimmedQuery, controller.signal);
      if (controller.signal.aborted) {
        return;
      }
      setResults(response.results);
      setShowResults(response.results.length > 0);
      setStatusMessage(formatSearchStatus(response.message, response.results.length));
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setResults([]);
      setShowResults(false);
      setStatusMessage("Could not search campaign references right now.");
    } finally {
      if (searchAbortController.current === controller) {
        searchAbortController.current = null;
      }
    }
  };

  const onQuerySubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearPendingSearch();
    void runSearch(query);
  };

  const onQueryInput = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.currentTarget.value;
    if (searchAbortController.current) {
      searchAbortController.current.abort();
      searchAbortController.current = null;
    }
    setQuery(next);
    setStatusMessage("");
    clearSearchState("");
    if (searchDebounceTimer.current !== null) {
      window.clearTimeout(searchDebounceTimer.current);
      searchDebounceTimer.current = null;
    }
    const trimmedQuery = next.trim();
    if (!trimmedQuery) {
      return;
    }
    if (trimmedQuery.length < 2) {
      setStatusMessage("Type at least 2 letters to search.");
      return;
    }

    searchDebounceTimer.current = window.setTimeout(() => {
      void runSearch(next);
    }, 250);
  };

  const onQueryKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearPendingSearch();
      void runSearch(query);
    }
  };

  const openDialog = () => {
    setDialogOpen(true);
    window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus({ preventScroll: true });
    });
  };

  const closeDialog = () => {
    if (previewAbortController.current) {
      previewAbortController.current.abort();
      previewAbortController.current = null;
    }
    setDialogOpen(false);
    setPreviewError(null);
    setPreviewHtml("");
    setPreviewLoading(false);

    const focusTarget = returnFocusRef.current;
    if (focusTarget && document.contains(focusTarget)) {
      focusTarget.focus({ preventScroll: true });
    }
    returnFocusRef.current = null;
  };

  const openPreview = (result: CampaignReferenceSearchResult, trigger: HTMLElement | null) => {
    const resultId = result.result_id.trim();
    if (!resultId) {
      return;
    }

    returnFocusRef.current = trigger;
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewHtml("");
    openDialog();

    if (previewAbortController.current) {
      previewAbortController.current.abort();
    }
    const controller = new AbortController();
    previewAbortController.current = controller;

    apiClient
      .previewCampaignReference(campaignSlug, resultId, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) {
          return;
        }
        setPreviewHtml(response.preview_html || "");
      })
      .catch((error) => {
        if (controller.signal.aborted) {
          return;
        }
        if (isAuthError(error)) {
          setAuthRequired(true);
        }
        setPreviewError("Could not load that reference right now.");
      })
      .finally(() => {
        if (previewAbortController.current === controller) {
          previewAbortController.current = null;
        }
        if (!controller.signal.aborted) {
          setPreviewLoading(false);
        }
      });
  };

  useEffect(() => {
    if (!isDialogOpen) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeDialog();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isDialogOpen]);

  useEffect(() => {
    if (!campaignSlug) {
      setQuery("");
      clearSearchState("");
      return;
    }
    setQuery("");
    clearSearchState("");
    setPreviewError(null);
    setPreviewHtml("");
    setPreviewLoading(false);
    setDialogOpen(false);
    if (previewAbortController.current) {
      previewAbortController.current.abort();
      previewAbortController.current = null;
    }

    return () => {
      clearPendingSearch();
      if (previewAbortController.current) {
        previewAbortController.current.abort();
        previewAbortController.current = null;
      }
    };
  }, [campaignSlug]);

  return (
    <section className="campaign-global-search" aria-label="Global campaign search">
      <form className="campaign-global-search__form" onSubmit={onQuerySubmit}>
        <label className="campaign-global-search__field">
          <span className="sr-only">Search wiki or Systems</span>
          <input
            type="search"
            value={query}
            autoComplete="off"
            placeholder="Search wiki or Systems"
            onChange={onQueryInput}
            onKeyDown={onQueryKeyDown}
          />
        </label>
        <button type="submit">Search</button>
      </form>
      <p className="meta campaign-global-search__status" aria-live="polite">
        {statusMessage}
      </p>
      {showResults ? (
        <div className="campaign-global-search__results">
          <div className="campaign-global-search-result-list">
            {results.map((result) => {
              const meta = result.subtitle ? `${result.kind_label} | ${result.subtitle}` : result.kind_label;
              return (
                <button
                  type="button"
                  className="campaign-global-search-result"
                  key={result.result_id}
                  onClick={(event) => {
                    openPreview(result, event.currentTarget);
                  }}
                >
                  <span className="campaign-global-search-result__title">{result.title}</span>
                  <span className="campaign-global-search-result__meta">{meta}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      {isDialogOpen ? (
        <div className="detail-modal-backdrop" role="presentation" onMouseDown={closeDialog}>
          <section
            className="spell-detail-dialog campaign-global-search-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="campaign-search-preview-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="spell-detail-dialog__panel campaign-global-search-dialog__panel">
              <header className="spell-detail-dialog__header">
                <div>
                  <p className="eyebrow">Reference preview</p>
                  <h2 id="campaign-search-preview-title">Campaign Search</h2>
                </div>
                <button type="button" className="ghost-button" ref={closeButtonRef} onClick={closeDialog}>
                  Close
                </button>
              </header>
              <div
                className="campaign-global-search-dialog__body"
                aria-live="polite"
                aria-busy={previewLoading ? "true" : "false"}
              >
                {previewLoading ? <p className="status status-neutral">Loading reference preview...</p> : null}
                {previewError ? <p className="status status-error">{previewError}</p> : null}
                {previewHtml ? <div dangerouslySetInnerHTML={{ __html: previewHtml }} /> : null}
                {!previewLoading && !previewError && !previewHtml ? (
                  <p className="status status-neutral">No reference preview is available.</p>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
