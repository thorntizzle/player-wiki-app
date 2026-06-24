import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import type { FormEvent } from "react";

import type { CharacterRetrainingPayload } from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { queryClient, useApiClient } from "../apiClientContext";
import { ApiErrorNotice, type ApiMessageEnvelope } from "../components/feedback";
import {
  characterAuthoringStringValues,
  characterNameFromRecord,
  characterRetrainingValuesFromContext,
  classLevelTextFromRecord,
  draftString,
  selectOptions,
  type CharacterAuthoringValues,
} from "../characterAuthoringUtils";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

export function CharacterRetrainingPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/retraining",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const retrainingQuery = useQuery({
    queryKey: ["character-retraining", campaignSlug, characterSlug],
    queryFn: () => apiClient.getCharacterRetraining(campaignSlug, characterSlug),
    enabled: Boolean(campaignSlug && characterSlug),
    retry: false,
  });

  const data = retrainingQuery.data;
  const retraining = data?.retraining ?? null;

  useEffect(() => {
    if (isAuthError(retrainingQuery.error)) {
      setAuthRequired(true);
    }
  }, [retrainingQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!retraining || loadedRevision === retraining.state_revision) {
      return;
    }
    setDraftValues(characterRetrainingValuesFromContext(retraining));
    setLoadedRevision(retraining.state_revision);
    setErrorMessage(null);
  }, [retraining, loadedRevision]);

  const updateValue = (key: string, value: string) => {
    setDraftValues((current) => ({ ...current, [key]: value }));
  };

  const submitRetraining = useMutation({
    mutationFn: (payload: CharacterRetrainingPayload) => apiClient.submitCharacterRetraining(campaignSlug, characterSlug, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(["character-retraining", campaignSlug, characterSlug], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setDraftValues(characterRetrainingValuesFromContext(response.retraining));
      setLoadedRevision(response.retraining?.state_revision ?? null);
      setStatusMessage(response.message || "Retraining saved.");
      setErrorMessage(null);
      if (response.links.character_url) {
        window.location.assign(`${response.links.character_url}?page=features`);
      }
    },
    onError: (error) => {
      setErrorMessage(getApiErrorMessage(error));
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const submitForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!retraining) {
      setErrorMessage({ status: 400, message: "The retraining context has not loaded yet." });
      return;
    }
    setStatusMessage(null);
    setErrorMessage(null);
    submitRetraining.mutate({
      expected_revision: retraining.state_revision,
      values: characterAuthoringStringValues(draftValues),
    });
  };

  const loadingError = getApiErrorMessage(retrainingQuery.error);
  const characterName = characterNameFromRecord(data?.character) || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="eyebrow">Character retraining</p>
        <h1>Retrain {characterName}</h1>
        {classLevelText ? <p className="lede">{classLevelText}</p> : null}
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.advanced_editor_url ? (
            <a className="ghost-button" href={data.links.advanced_editor_url}>
              Advanced Editor
            </a>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={retrainingQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>Retraining Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 retraining."}</p>
          <div className="hero-actions">
            {data.links.character_url ? (
              <a className="button-link" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
            {data.links.progression_repair_url ? (
              <a className="ghost-button" href={data.links.progression_repair_url}>
                Progression repair
              </a>
            ) : null}
            {data.links.cultivation_url ? (
              <a className="ghost-button" href={data.links.cultivation_url}>
                Cultivation
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {retraining ? (
        <article className="card character-edit-sheet">
          {retraining.supported_scope?.length ? (
            <section className="read-section">
              <div className="section-heading">
                <h2>Supported Scope</h2>
              </div>
              <ul className="plain-list builder-feature-list">
                {retraining.supported_scope.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <form className="stack-form" onSubmit={submitForm}>
            <section className="read-section">
              <div className="section-heading">
                <h2>Structured Choices</h2>
              </div>
              <div className="character-edit-stack">
                {retraining.feature_rows.map((row) => (
                  <article className="detail-card character-edit-row" key={row.id || row.index}>
                    <div className="section-heading">
                      <div>
                        <h3>{row.name || "Linked Feature"}</h3>
                        {row.page_ref ? <p className="meta">{row.page_ref}</p> : null}
                      </div>
                      {row.activation_type ? <span className="meta">{row.activation_type.replace(/_/g, " ")}</span> : null}
                    </div>
                    {row.summary ? <p className="meta">{row.summary}</p> : null}
                    <div className="detail-grid character-edit-grid">
                      {(row.choice_fields ?? []).map((field) => (
                        <label className="field" key={field.name}>
                          <span>{field.label}</span>
                          <select
                            name={field.name}
                            value={draftString(draftValues, field.name, field.selected || "")}
                            onChange={(event) => updateValue(field.name, event.currentTarget.value)}
                          >
                            <option value="">Choose an option</option>
                            {selectOptions(field.options ?? [])}
                          </select>
                          {field.help_text ? <small>{field.help_text}</small> : null}
                        </label>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <div className="hero-actions">
              <button type="submit" disabled={submitRetraining.isPending}>
                {submitRetraining.isPending ? "Saving..." : "Save retraining"}
              </button>
              {data?.links?.character_url ? (
                <a className="ghost-button" href={`${data.links.character_url}?page=features`}>
                  Cancel
                </a>
              ) : null}
            </div>
          </form>
        </article>
      ) : null}
    </>
  );
}
