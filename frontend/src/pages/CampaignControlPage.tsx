import React, { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import type { ChangeEvent, FormEvent } from "react";

import { apiErrorMessage } from "../api/client";
import type {
  CampaignControlResponse,
  CampaignControlVisibilityRow,
} from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { queryClient, useApiClient } from "../apiClientContext";
import { ApiErrorNotice, ToastNotice, useToastNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

function buildControlVisibilityDraft(rows: CampaignControlVisibilityRow[]): Record<string, string> {
  return rows.reduce<Record<string, string>>((accumulator, row) => {
    accumulator[row.scope] = row.selected_visibility;
    return accumulator;
  }, {});
}

function isControlDraftUnchanged(rows: CampaignControlVisibilityRow[], draft: Record<string, string>): boolean {
  if (!rows.length) {
    return true;
  }
  return rows.every((row) => (draft[row.scope] || "") === row.selected_visibility);
}

export function CampaignControlPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/control",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftVisibility, setDraftVisibility] = useState<Record<string, string>>({});
  const { clearToast, showToast, toastMessage, toastTone } = useToastNotice();

  const controlQuery = useQuery({
    queryKey: ["campaign-control", resolvedCampaignSlug],
    queryFn: () => apiClient.getCampaignControl(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(controlQuery.error)) {
      setAuthRequired(true);
    }
  }, [controlQuery.error, setAuthRequired]);

  useEffect(() => {
    const rows = controlQuery.data?.visibility_rows;
    if (!rows) {
      return;
    }
    setDraftVisibility(buildControlVisibilityDraft(rows));
  }, [controlQuery.data?.visibility_rows]);

  const saveVisibility = useMutation({
    mutationFn: () => apiClient.patchCampaignControlVisibility(resolvedCampaignSlug, { visibility: draftVisibility }),
    onSuccess: (response) => {
      showToast(response.message);
      setDraftVisibility(buildControlVisibilityDraft(response.visibility_rows));
      void queryClient.invalidateQueries({ queryKey: ["campaign-control", resolvedCampaignSlug] });
      void queryClient.invalidateQueries({ queryKey: ["campaign", resolvedCampaignSlug] });
    },
    onError: (error) => {
      clearToast();
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const data: CampaignControlResponse | undefined = controlQuery.data;
  const error = getApiErrorMessage(controlQuery.error);
  const saveError = saveVisibility.error ? apiErrorMessage(saveVisibility.error) : null;
  const isUnchanged = data ? isControlDraftUnchanged(data.visibility_rows, draftVisibility) : true;

  const handleVisibilityChange = (scope: string, value: string) => {
    setDraftVisibility((previous) => ({
      ...previous,
      [scope]: value,
    }));
    clearToast();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!data) {
      return;
    }
    clearToast();
    saveVisibility.mutate();
  };

  return (
    <>
      <section className="hero compact campaign-control-hero">
        <p className="eyebrow">Control panel</p>
        <h1>Visibility</h1>
        <p className="lede">
          Control who can see the campaign, wiki, systems reference, session tools, combat tracker, DM content, and character section.
        </p>
      </section>

      <ApiErrorNotice isLoading={controlQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      <ToastNotice message={toastMessage} tone={toastTone} />

      {data ? (
        <div className="page-layout">
          <section className="article card">
            <h2>Visibility settings</h2>
            <form className="stack-form" onSubmit={handleSubmit}>
              {data.visibility_rows.map((row) => {
                const fieldId = `campaign-control-${row.scope}`;
                return (
                  <React.Fragment key={row.scope}>
                    <label className="field" htmlFor={fieldId}>
                      <span>{row.label}</span>
                      <select
                        id={fieldId}
                        name={`${row.scope}_visibility`}
                        value={draftVisibility[row.scope] || row.selected_visibility}
                        onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                          handleVisibilityChange(row.scope, event.currentTarget.value)
                        }
                      >
                        {row.choices.map((choice) => (
                          <option value={choice.value} key={`${row.scope}-${choice.value}`}>
                            {choice.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="meta">
                      {row.configured_visibility_label ? (
                        <>
                          Effective visibility: {row.effective_visibility_label} | configured: {row.configured_visibility_label}
                        </>
                      ) : (
                        <>Effective visibility: {row.effective_visibility_label} | using default visibility</>
                      )}
                    </p>
                    {row.is_overridden_by_campaign ? (
                      <p className="meta">The campaign-level visibility is currently more private than this section setting.</p>
                    ) : null}
                  </React.Fragment>
                );
              })}
              <button type="submit" disabled={saveVisibility.isPending || isUnchanged}>
                {saveVisibility.isPending ? "Saving..." : "Save visibility"}
              </button>
              {isUnchanged && !saveVisibility.isPending ? <p className="meta">No visibility changes to save.</p> : null}
              {saveError ? <p className="status status-error">{saveError}</p> : null}
            </form>
          </section>

          <aside className="sidebar">
            <section className="card sidebar-card">
              <h2>Visibility rules</h2>
              {data.rules.map((rule) => (
                <p className="meta" key={rule.label}>
                  {rule.label}: {rule.description}
                </p>
              ))}
            </section>

            <section className="card sidebar-card">
              <h2>Notes</h2>
              {data.notes.length ? (
                data.notes.map((note) => (
                  <p className="meta" key={note}>
                    {note}
                  </p>
                ))
              ) : (
                <p className="meta">No additional visibility notes are available.</p>
              )}
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}
