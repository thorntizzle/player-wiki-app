import React, { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import type { FormEvent } from "react";

import type {
  CharacterCultivationContext,
  CharacterCultivationStatRow,
  CharacterLevelUpPayload,
  CharacterRetrainingPayload,
} from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { queryClient, useApiClient } from "../apiClientContext";
import { CharacterDndChoiceSelect } from "../components/CharacterAuthoringFields";
import { CharacterLevelUpPreviewList } from "../components/CharacterAuthoringPreview";
import { ApiErrorNotice, type ApiMessageEnvelope } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import {
  characterAuthoringStringValues,
  characterNameFromRecord,
  characterLevelUpValuesFromContext,
  characterRetrainingValuesFromContext,
  classLevelTextFromRecord,
  draftString,
  draftStringArray,
  selectOptions,
  updateAuthoringValue,
  type CharacterAuthoringValues,
} from "../characterAuthoringUtils";
import {
  boolFromUnknown,
  numberFromUnknown,
  recordFromUnknown,
  recordListFromUnknown,
  stringFromUnknown,
} from "../characterValueUtils";

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

export function CharacterLevelUpPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/level-up",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [contextValues, setContextValues] = useState<CharacterAuthoringValues>({});
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const levelUpQuery = useQuery({
    queryKey: ["character-level-up", campaignSlug, characterSlug, JSON.stringify(contextValues)],
    queryFn: () => apiClient.getCharacterLevelUp(campaignSlug, characterSlug, contextValues),
    enabled: Boolean(campaignSlug && characterSlug),
    retry: false,
  });

  const data = levelUpQuery.data;
  const levelUp = data?.level_up ?? null;

  useEffect(() => {
    if (isAuthError(levelUpQuery.error)) {
      setAuthRequired(true);
    }
  }, [levelUpQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!levelUp || loadedRevision === levelUp.state_revision) {
      return;
    }
    setDraftValues(characterLevelUpValuesFromContext(levelUp));
    setLoadedRevision(levelUp.state_revision);
    setErrorMessage(null);
  }, [levelUp, loadedRevision]);

  const refreshContext = (values: CharacterAuthoringValues = draftValues) => {
    setContextValues({ ...values });
  };

  const updateValue = (key: string, value: string, refresh = false) => {
    const nextValues = { ...draftValues, [key]: value };
    setDraftValues(nextValues);
    if (refresh) {
      refreshContext(nextValues);
    }
  };

  const submitLevelUp = useMutation({
    mutationFn: (payload: CharacterLevelUpPayload) => apiClient.submitCharacterLevelUp(campaignSlug, characterSlug, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(["character-level-up", campaignSlug, characterSlug, JSON.stringify(contextValues)], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setDraftValues(characterLevelUpValuesFromContext(response.level_up));
      setLoadedRevision(response.level_up?.state_revision ?? null);
      setStatusMessage(response.message || "Character advanced.");
      setErrorMessage(null);
      if (response.links.character_url) {
        window.location.assign(response.links.character_url);
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
    if (!levelUp) {
      setErrorMessage({ status: 400, message: "The level-up context has not loaded yet." });
      return;
    }
    setStatusMessage(null);
    setErrorMessage(null);
    submitLevelUp.mutate({
      expected_revision: levelUp.state_revision,
      values: characterAuthoringStringValues(draftValues),
    });
  };

  const loadingError = getApiErrorMessage(levelUpQuery.error);
  const characterName = characterNameFromRecord(data?.character) || levelUp?.character_name || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);
  const advancementMode = draftString(draftValues, "advancement_mode", levelUp?.advancement_mode || "advance_existing");

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="eyebrow">Character level-up</p>
        <h1>Level Up {characterName}</h1>
        {classLevelText ? <p className="lede">{classLevelText}</p> : null}
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={levelUpQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>Level-Up Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 level-up."}</p>
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

      {levelUp ? (
        <div className="character-authoring-layout">
          <form className="stack-form character-authoring-form" onSubmit={submitForm}>
            <section className="builder-section">
              <h2>Advancement</h2>
              <div className="builder-field-grid">
                <label className="field">
                  <span>Mode</span>
                  <select
                    name="advancement_mode"
                    value={advancementMode}
                    onChange={(event) => updateValue("advancement_mode", event.currentTarget.value, true)}
                  >
                    {selectOptions(levelUp.mode_options ?? [])}
                  </select>
                </label>

                {advancementMode === "add_class" ? (
                  <>
                    <label className="field">
                      <span>New Class</span>
                      <select
                        name="new_class_slug"
                        value={draftString(draftValues, "new_class_slug")}
                        onChange={(event) => updateValue("new_class_slug", event.currentTarget.value, true)}
                      >
                        <option value="">Choose a class</option>
                        {selectOptions(levelUp.new_class_options ?? [])}
                      </select>
                    </label>
                    {levelUp.new_subclass_options?.length || levelUp.requires_subclass ? (
                      <label className="field">
                        <span>New Subclass</span>
                        <select
                          name="new_subclass_slug"
                          value={draftString(draftValues, "new_subclass_slug")}
                          onChange={(event) => updateValue("new_subclass_slug", event.currentTarget.value, true)}
                        >
                          <option value="">{levelUp.requires_subclass ? "Choose a subclass" : "No subclass"}</option>
                          {selectOptions(levelUp.new_subclass_options ?? [])}
                        </select>
                      </label>
                    ) : null}
                  </>
                ) : (
                  <label className="field">
                    <span>Class Row</span>
                    <select
                      name="target_class_row_id"
                      value={draftString(draftValues, "target_class_row_id", levelUp.target_class_row_id || "")}
                      onChange={(event) => updateValue("target_class_row_id", event.currentTarget.value, true)}
                    >
                      {selectOptions(levelUp.target_row_options ?? [])}
                    </select>
                  </label>
                )}

                {advancementMode !== "add_class" && (levelUp.subclass_options?.length || levelUp.requires_subclass) ? (
                  <label className="field">
                    <span>Subclass</span>
                    <select
                      name="subclass_slug"
                      value={draftString(draftValues, "subclass_slug")}
                      onChange={(event) => updateValue("subclass_slug", event.currentTarget.value, true)}
                    >
                      <option value="">{levelUp.requires_subclass ? "Choose a subclass" : "No subclass"}</option>
                      {selectOptions(levelUp.subclass_options ?? [])}
                    </select>
                  </label>
                ) : null}

                <label className="field">
                  <span>HP Gain</span>
                  <input
                    type="number"
                    name="hp_gain"
                    min={1}
                    value={draftString(draftValues, "hp_gain")}
                    onChange={(event) => updateValue("hp_gain", event.currentTarget.value)}
                  />
                </label>
              </div>
              {levelUp.multiclass_requirement_text ? (
                <p className={levelUp.multiclass_requirements_met ? "meta" : "status status-warning"}>
                  Multiclass requirement: {levelUp.multiclass_requirement_text}
                </p>
              ) : null}
            </section>

            {levelUp.choice_sections.map((section) => (
              <section className="builder-section" key={section.title}>
                <h2>{section.title}</h2>
                <div className="builder-field-grid">
                  {section.fields.map((field) => (
                    <CharacterDndChoiceSelect
                      key={field.name}
                      field={field}
                      draftValues={draftValues}
                      setDraftValues={setDraftValues}
                      refreshContext={refreshContext}
                    />
                  ))}
                </div>
              </section>
            ))}

            {levelUp.limitations?.length ? (
              <section className="builder-section">
                <h2>Limitations</h2>
                <ul className="plain-list">
                  {levelUp.limitations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            <div className="builder-actions">
              <button type="button" className="ghost-button" onClick={() => refreshContext()}>
                Refresh preview
              </button>
              <button type="submit" disabled={submitLevelUp.isPending}>
                {submitLevelUp.isPending ? "Leveling..." : `Advance to level ${levelUp.next_level}`}
              </button>
            </div>
          </form>
          <CharacterLevelUpPreviewList preview={levelUp.preview ?? {}} />
        </div>
      ) : null}
    </>
  );
}

export function CharacterCultivationPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/cultivation",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const cultivationQuery = useQuery({
    queryKey: ["character-cultivation", campaignSlug, characterSlug],
    queryFn: () => apiClient.getCharacterCultivation(campaignSlug, characterSlug),
    enabled: Boolean(campaignSlug && characterSlug),
  });

  const data = cultivationQuery.data;
  const cultivation = data?.cultivation ?? null;
  const actionMutation = useMutation({
    mutationFn: ({ action, values }: { action: string; values: Record<string, string> }) => {
      if (!data) {
        throw new Error("The cultivation context has not loaded yet.");
      }
      return apiClient.runCharacterCultivationAction(campaignSlug, characterSlug, {
        expected_revision: data.character.state_record.revision,
        action,
        values,
      });
    },
    onSuccess: (response) => {
      queryClient.setQueryData(["character-cultivation", campaignSlug, characterSlug], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setStatusMessage(response.message || "Cultivation updated.");
      setErrorMessage(null);
      if (response.anchor) {
        window.requestAnimationFrame(() => {
          document.getElementById(response.anchor || "")?.scrollIntoView({ block: "start" });
        });
      }
    },
    onError: (error) => {
      setErrorMessage(getApiErrorMessage(error));
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const submitCultivationAction = (event: FormEvent<HTMLFormElement>, action: string) => {
    event.preventDefault();
    const values: Record<string, string> = {};
    new FormData(event.currentTarget).forEach((value, key) => {
      if (typeof value === "string") {
        values[key] = value;
      }
    });
    setStatusMessage(null);
    setErrorMessage(null);
    actionMutation.mutate({ action, values });
  };

  const renderActionForm = (
    action: string,
    buttonLabel: string,
    children: React.ReactNode,
    options: { disabled?: boolean } = {},
  ) => (
    <form className="stack-form cultivation-action-form" onSubmit={(event) => submitCultivationAction(event, action)}>
      {children}
      <div className="hero-actions">
        <button type="submit" disabled={actionMutation.isPending || options.disabled}>
          {actionMutation.isPending ? "Saving..." : buttonLabel}
        </button>
      </div>
    </form>
  );

  const renderSpendCard = (
    row: CharacterCultivationStatRow,
    options: {
      action: string;
      keyName: string;
      hiddenName: string;
      notesName: string;
      buttonPrefix: string;
      meta: string;
    },
  ) => {
    const label = stringFromUnknown(row.label || row.key || "Resource");
    const hasEnoughInsight = boolFromUnknown(row.has_enough_insight);
    return (
      <article className="feature-row cultivation-card" key={`${options.action}-${options.keyName}`}>
        <div className="feature-row__header">
          <h3>{label}</h3>
          <p className="meta">
            Current {numberFromUnknown(row.current)} / Max {numberFromUnknown(row.max)}
          </p>
        </div>
        {renderActionForm(
          options.action,
          `${options.buttonPrefix} ${label}`,
          <>
            <input type="hidden" name={options.hiddenName} value={options.keyName} />
            <p className="meta">{options.meta}</p>
            <label className="field">
              <span>Notes</span>
              <textarea name={options.notesName} rows={2} />
            </label>
            {!hasEnoughInsight ? <p className="meta">Needs {numberFromUnknown(row.shortfall)} more available Insight.</p> : null}
          </>,
          { disabled: !hasEnoughInsight },
        )}
      </article>
    );
  };

  const renderHistoryRecords = (records: Array<Record<string, unknown>>) =>
    records.length ? (
      <div className="feature-stack">
        {records.map((record, index) => (
          <article className="feature-row" key={`${stringFromUnknown(record.action, "record")}-${index}`}>
            <div className="feature-row__header">
              <h3>{stringFromUnknown(record.action || record.status || "Record").replace(/_/g, " ")}</h3>
              {record.target_realm ? <p className="meta">Target {stringFromUnknown(record.target_realm)}</p> : null}
            </div>
            <ul className="plain-list slot-list">
              {Object.entries(record)
                .filter(([key, value]) => {
                  if (["snapshot", "pre_ascension_snapshot", "post_ascension_snapshot"].includes(key)) {
                    return false;
                  }
                  return value !== null && value !== undefined && String(value).trim() !== "";
                })
                .slice(0, 12)
                .map(([key, value]) => (
                  <li key={key}>
                    <strong>{key.replace(/_/g, " ")}:</strong> {stringFromUnknown(value)}
                  </li>
                ))}
            </ul>
          </article>
        ))}
      </div>
    ) : null;

  const renderMartialArts = (context: CharacterCultivationContext) => {
    if (!context.martial_arts.length) {
      return (
        <article className="detail-card">
          <p className="meta">No Martial Arts are recorded on this sheet yet.</p>
        </article>
      );
    }
    return (
      <div className="feature-stack">
        {context.martial_arts.map((rawArt, fallbackIndex) => {
          const art = recordFromUnknown(rawArt);
          const index = numberFromUnknown(art.index, fallbackIndex);
          const advancement = recordFromUnknown(art.advancement);
          const rankProgress = recordFromUnknown(art.rank_progress);
          const steps = recordListFromUnknown(rankProgress.steps);
          const name = stringFromUnknown(art.name, "Martial Art");
          const href = stringFromUnknown(art.href);
          const available = stringFromUnknown(advancement.status) === "available";
          const hasEnoughInsight = boolFromUnknown(advancement.has_enough_insight);
          const nextRankLabel = stringFromUnknown(advancement.next_rank_label, "next rank");
          return (
            <article className="feature-row cultivation-card" key={`${name}-${index}`}>
              <div className="feature-row__header">
                <h3>{href ? <a href={href}>{name}</a> : name}</h3>
                <p className="meta">
                  {art.current_rank ? `Current rank: ${stringFromUnknown(art.current_rank)}` : "Rank not recorded"}
                  {art.rank_records_status ? ` | ${stringFromUnknown(art.rank_records_status).replace(/_/g, " ")}` : ""}
                </p>
              </div>
              {steps.length ? (
                <div className="skill-grid">
                  {steps.map((step) => (
                    <div
                      className={boolFromUnknown(step.is_learned) ? "skill-pill skill-pill--proficient" : "skill-pill"}
                      key={stringFromUnknown(step.key || step.label)}
                    >
                      {step.href ? (
                        <a href={stringFromUnknown(step.href)}>{stringFromUnknown(step.label)}</a>
                      ) : (
                        <span>{stringFromUnknown(step.label)}</span>
                      )}
                      <span className="meta">{stringFromUnknown(step.status_label)}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {available ? (
                renderActionForm(
                  "advance_martial_art_rank",
                  `Advance to ${nextRankLabel}`,
                  <>
                    <input type="hidden" name="martial_art_index" value={String(index)} />
                    <input type="hidden" name="target_rank_key" value={stringFromUnknown(advancement.next_rank_key)} />
                    <p className="meta">
                      Spend {numberFromUnknown(advancement.insight_cost)} Insight to advance to {nextRankLabel}.
                    </p>
                    {advancement.teacher_breakthrough_note ? (
                      <p className="meta">Teacher/Breakthrough: {stringFromUnknown(advancement.teacher_breakthrough_note)}</p>
                    ) : null}
                    {boolFromUnknown(advancement.requires_legendary_note) ? (
                      <label className="field">
                        <span>Quest or mythic-master note</span>
                        <textarea name="legendary_quest_note" rows={3} required />
                      </label>
                    ) : null}
                    {!hasEnoughInsight ? <p className="meta">Needs {numberFromUnknown(advancement.shortfall)} more available Insight.</p> : null}
                  </>,
                  { disabled: !hasEnoughInsight },
                )
              ) : advancement.message ? (
                <p className="meta">{stringFromUnknown(advancement.message)}</p>
              ) : null}
            </article>
          );
        })}
      </div>
    );
  };

  const renderGenericTechniques = (context: CharacterCultivationContext) => (
    <div className="feature-stack">
      {context.generic_techniques.length ? (
        <article className="detail-card">
          <h3>Known Generic Techniques</h3>
          <ul className="plain-list slot-list">
            {context.generic_techniques.map((rawTechnique, index) => {
              const technique = recordFromUnknown(rawTechnique);
              const href = stringFromUnknown(technique.href);
              const name = stringFromUnknown(technique.name, "Generic Technique");
              return (
                <li key={`${name}-${index}`}>
                  {href ? <a href={href}>{name}</a> : <strong>{name}</strong>}
                  {technique.insight_cost ? <span className="meta"> | Insight {stringFromUnknown(technique.insight_cost)}</span> : null}
                </li>
              );
            })}
          </ul>
        </article>
      ) : null}
      {context.generic_technique_options.map((rawTechnique, index) => {
        const technique = recordFromUnknown(rawTechnique);
        const name = stringFromUnknown(technique.name, "Generic Technique");
        const href = stringFromUnknown(technique.href);
        const entryKey = stringFromUnknown(technique.entry_key);
        const hasEnoughInsight = boolFromUnknown(technique.has_enough_insight);
        return (
          <article className="feature-row cultivation-card" key={`${entryKey || name}-${index}`}>
            <div className="feature-row__header">
              <h3>{href ? <a href={href}>{name}</a> : name}</h3>
              <p className="meta">
                Insight {numberFromUnknown(technique.insight_cost)}
                {technique.support_state ? ` | ${stringFromUnknown(technique.support_state).replace(/_/g, " ")}` : ""}
              </p>
            </div>
            {renderActionForm(
              "learn_generic_technique",
              `Learn ${name}`,
              <>
                <input type="hidden" name="generic_technique_entry_key" value={entryKey} />
                <label className="field">
                  <span>Notes</span>
                  <textarea name="generic_technique_notes" rows={2} />
                </label>
                {!hasEnoughInsight ? <p className="meta">Needs {numberFromUnknown(technique.shortfall)} more available Insight.</p> : null}
              </>,
              { disabled: !hasEnoughInsight },
            )}
          </article>
        );
      })}
      {!context.generic_techniques.length && !context.generic_technique_options.length ? (
        <article className="detail-card">
          <p className="meta">No Generic Technique options are currently available.</p>
        </article>
      ) : null}
    </div>
  );

  const renderRealmAscension = (context: CharacterCultivationContext) => {
    const ascension = recordFromUnknown(context.realm_ascension);
    const target = recordFromUnknown(ascension.target);
    const statPrerequisite = recordFromUnknown(ascension.stat_prerequisite);
    const attributes = recordFromUnknown(ascension.attributes);
    const efforts = recordFromUnknown(ascension.efforts);
    const attributeRows = recordListFromUnknown(attributes.rows);
    const effortRows = recordListFromUnknown(efforts.rows);
    const trade = recordFromUnknown(ascension.hp_stance_trade);
    const pendingConfirmation = recordFromUnknown(ascension.pending_confirmation_rebuild);
    const targetRealm = stringFromUnknown(target.target_realm || pendingConfirmation.target_realm);
    const rebuildAction = targetRealm === "Divine" ? "apply_divine_realm_rebuild" : "apply_immortal_realm_rebuild";

    return (
      <section className="read-section" id="xianxia-cultivation-realm-ascension">
        <div className="section-heading">
          <h2>Realm Ascension</h2>
        </div>
        <div className="glance-grid">
          <div className="glance-card">
            <span className="meta">Current Realm</span>
            <strong>{stringFromUnknown(ascension.current_realm, "Unknown")}</strong>
          </div>
          {boolFromUnknown(ascension.available) ? (
            <>
              <div className="glance-card">
                <span className="meta">Target Realm</span>
                <strong>{stringFromUnknown(target.target_realm)}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Seclusion</span>
                <strong>{stringFromUnknown(target.seclusion_time)}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Rebuild</span>
                <strong>{numberFromUnknown(target.rebuild_budget)} points</strong>
                <span className="meta">Max {numberFromUnknown(target.stat_cap)} per Stat</span>
              </div>
              <div className="glance-card">
                <span className="meta">Stat prerequisite</span>
                <strong>{boolFromUnknown(statPrerequisite.is_met) ? "Met" : "Not met"}</strong>
                <span className="meta">{stringFromUnknown(statPrerequisite.requirement_text)}</span>
              </div>
            </>
          ) : (
            <div className="glance-card">
              <span className="meta">Target Realm</span>
              <strong>None</strong>
            </div>
          )}
        </div>
        <article className="detail-card">
          <div className="detail-grid">
            <div>
              <h3>Attributes</h3>
              <p className="meta">Current total {numberFromUnknown(attributes.total)}</p>
              <ul className="plain-list slot-list">
                {attributeRows.map((stat) => (
                  <li key={stringFromUnknown(stat.key || stat.label)}>
                    <strong>{stringFromUnknown(stat.label)}:</strong> {numberFromUnknown(stat.score)}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Efforts</h3>
              <p className="meta">Current total {numberFromUnknown(efforts.total)}</p>
              <ul className="plain-list slot-list">
                {effortRows.map((stat) => (
                  <li key={stringFromUnknown(stat.key || stat.label)}>
                    <strong>{stringFromUnknown(stat.label)}:</strong> {numberFromUnknown(stat.score)}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </article>
        {boolFromUnknown(ascension.available) ? (
          <article className="detail-card session-card">
            {!boolFromUnknown(ascension.can_start_review) ? (
              <p className="meta">
                {stringFromUnknown(ascension.confirmation_blocking_message || statPrerequisite.failure_message)}
              </p>
            ) : null}
            {renderActionForm(
              "start_realm_ascension_review",
              "Start Realm Review",
              <>
                <input type="hidden" name="target_realm" value={stringFromUnknown(target.target_realm)} />
                <label className="field">
                  <span>GM review note</span>
                  <textarea name="realm_ascension_gm_review_note" rows={3} required />
                </label>
                <label className="field">
                  <span>Seclusion notes</span>
                  <textarea name="realm_ascension_seclusion_notes" rows={2} />
                </label>
                <label className="field">
                  <span>HP/Stance trade notes</span>
                  <textarea name="realm_ascension_hp_stance_trade_notes" rows={2} />
                </label>
              </>,
              { disabled: !boolFromUnknown(ascension.can_start_review) },
            )}
          </article>
        ) : (
          <article className="detail-card">
            <p className="meta">{stringFromUnknown(ascension.message)}</p>
          </article>
        )}
        {renderHistoryRecords(
          [
            recordFromUnknown(ascension.latest_review),
            recordFromUnknown(ascension.latest_reset),
            recordFromUnknown(ascension.latest_rebuild),
            recordFromUnknown(ascension.latest_confirmation),
          ].filter((record) => Object.keys(record).length > 0),
        )}
        {boolFromUnknown(ascension.can_reset_stats) ? (
          <article className="detail-card session-card">
            <h3>Reset Rebuild Stats</h3>
            {renderActionForm(
              "reset_realm_ascension_stats",
              "Reset Attributes and Efforts",
              <>
                <input type="hidden" name="target_realm" value={targetRealm} />
                <label className="field">
                  <span>Reset notes</span>
                  <textarea name="realm_ascension_reset_notes" rows={2} />
                </label>
              </>,
            )}
          </article>
        ) : null}
        {boolFromUnknown(ascension.can_apply_rebuild) ? (
          <article className="detail-card session-card">
            <h3>Apply {targetRealm} Rebuild</h3>
            {renderActionForm(
              rebuildAction,
              `Apply ${targetRealm} Rebuild`,
              <>
                <input type="hidden" name="target_realm" value={targetRealm} />
                <div className="detail-grid">
                  <div>
                    <h4>Attributes</h4>
                    <div className="builder-field-grid">
                      {attributeRows.map((stat) => (
                        <label className="field" key={stringFromUnknown(stat.key)}>
                          <span>{stringFromUnknown(stat.label)}</span>
                          <input
                            type="number"
                            min={0}
                            max={numberFromUnknown(target.stat_cap)}
                            name={`realm_rebuild_attribute_${stringFromUnknown(stat.key)}`}
                            defaultValue={numberFromUnknown(stat.score)}
                            required
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4>Efforts</h4>
                    <div className="builder-field-grid">
                      {effortRows.map((stat) => (
                        <label className="field" key={stringFromUnknown(stat.key)}>
                          <span>{stringFromUnknown(stat.label)}</span>
                          <input
                            type="number"
                            min={0}
                            max={numberFromUnknown(target.stat_cap)}
                            name={`realm_rebuild_effort_${stringFromUnknown(stat.key)}`}
                            defaultValue={numberFromUnknown(stat.score)}
                            required
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="detail-grid">
                  <label className="field">
                    <span>HP maximum traded</span>
                    <input
                      type="number"
                      min={0}
                      max={numberFromUnknown(trade.hp_maximum_trade)}
                      step={numberFromUnknown(trade.unit, 10)}
                      name="realm_ascension_trade_hp"
                      defaultValue={0}
                      disabled={!numberFromUnknown(trade.hp_maximum_trade)}
                    />
                  </label>
                  <label className="field">
                    <span>Stance maximum traded</span>
                    <input
                      type="number"
                      min={0}
                      max={numberFromUnknown(trade.stance_maximum_trade)}
                      step={numberFromUnknown(trade.unit, 10)}
                      name="realm_ascension_trade_stance"
                      defaultValue={0}
                      disabled={!numberFromUnknown(trade.stance_maximum_trade)}
                    />
                  </label>
                </div>
                <label className="field">
                  <span>Rebuild notes</span>
                  <textarea name="realm_ascension_rebuild_notes" rows={2} />
                </label>
              </>,
            )}
          </article>
        ) : null}
        {boolFromUnknown(ascension.can_confirm_rebuild) && Object.keys(pendingConfirmation).length ? (
          <article className="detail-card session-card">
            <h3>Confirm {targetRealm} Ascension</h3>
            {renderActionForm(
              "confirm_realm_ascension",
              "Confirm Realm Ascension",
              <>
                <input type="hidden" name="target_realm" value={targetRealm} />
                <label className="field">
                  <span>GM confirmation note</span>
                  <textarea name="realm_ascension_gm_confirmation_note" rows={3} required />
                </label>
              </>,
            )}
          </article>
        ) : null}
      </section>
    );
  };

  const loadingError = getApiErrorMessage(cultivationQuery.error);
  const characterName = characterNameFromRecord(data?.character) || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);

  return (
    <>
      <section className="hero compact character-cultivation-hero character-authoring-hero">
        <p className="eyebrow">Character cultivation</p>
        <h1>Cultivation: {characterName}</h1>
        <p className="lede">Insight-based advancement for this Xianxia character.</p>
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="ghost-button" href={`${data.links.character_url}?page=martial_arts`}>
              Martial Arts
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="ghost-button" href={`${data.links.character_url}?page=techniques`}>
              Techniques
            </a>
          ) : null}
          {data?.links?.character_url ? (
            <a className="ghost-button" href={`${data.links.character_url}?page=resources`}>
              Resources
            </a>
          ) : null}
          <a className="ghost-button" href="#xianxia-cultivation-realm-ascension">
            Realm Ascension
          </a>
          {classLevelText ? <span className="meta">{classLevelText}</span> : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={cultivationQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>Cultivation Is Not Available</h2>
          <p>{data.unsupported_message || "This character system uses a different advancement lane."}</p>
          <div className="hero-actions">
            {data.links.character_url ? (
              <a className="button-link" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {cultivation ? (
        <>
          <section className="read-section" id="xianxia-cultivation-insight">
            <div className="section-heading">
              <h2>Insight</h2>
            </div>
            <div className="glance-grid">
              <div className="glance-card">
                <span className="meta">Available</span>
                <strong>{numberFromUnknown(cultivation.insight.available)}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Spent</span>
                <strong>{numberFromUnknown(cultivation.insight.spent)}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Martial Arts</span>
                <strong>{cultivation.martial_arts.length}</strong>
              </div>
              <div className="glance-card">
                <span className="meta">Generic Techniques</span>
                <strong>{cultivation.generic_techniques.length}</strong>
              </div>
            </div>
            <article className="detail-card session-card">
              {renderActionForm(
                "save_insight",
                "Save Insight",
                <div className="detail-grid">
                  <label className="field">
                    <span>Insight available</span>
                    <input type="number" name="insight_available" min={0} step={1} defaultValue={cultivation.insight.available} />
                  </label>
                  <label className="field">
                    <span>Insight spent</span>
                    <input type="number" name="insight_spent" min={0} step={1} defaultValue={cultivation.insight.spent} />
                  </label>
                </div>,
              )}
            </article>
          </section>

          <section className="read-section" id="xianxia-cultivation-gathering-insight">
            <div className="section-heading">
              <h2>Gathering Insight</h2>
            </div>
            <article className="detail-card session-card">
              {renderActionForm(
                "record_gathering_insight",
                "Record Gain",
                <>
                  <div className="detail-grid">
                    <label className="field">
                      <span>Insight gained</span>
                      <input type="number" name="insight_gain_amount" min={1} step={1} defaultValue={1} />
                    </label>
                    <label className="field">
                      <span>Downtime</span>
                      <input type="text" name="gathering_insight_downtime" />
                    </label>
                  </div>
                  <label className="field">
                    <span>Notes</span>
                    <textarea name="gathering_insight_notes" rows={3} />
                  </label>
                </>,
              )}
            </article>
          </section>

          <section className="read-section" id="xianxia-cultivation-energy">
            <div className="section-heading">
              <h2>Cultivation</h2>
            </div>
            <div className="feature-stack">
              {cultivation.energies.length ? (
                cultivation.energies.map((energy) =>
                  renderSpendCard(energy, {
                    action: "spend_cultivation_energy",
                    keyName: stringFromUnknown(energy.key),
                    hiddenName: "energy_key",
                    notesName: "cultivation_energy_notes",
                    buttonPrefix: "Increase",
                    meta: `Spend ${numberFromUnknown(energy.insight_cost)} Insight to increase ${stringFromUnknown(energy.label)} by 1.`,
                  }),
                )
              ) : (
                <article className="detail-card">
                  <p className="meta">No Energy resources are recorded on this sheet yet.</p>
                </article>
              )}
            </div>
          </section>

          <section className="read-section" id="xianxia-cultivation-meditation">
            <div className="section-heading">
              <h2>Meditation</h2>
            </div>
            <div className="feature-stack">
              {cultivation.yin_yang.length ? (
                cultivation.yin_yang.map((resource) =>
                  renderSpendCard(resource, {
                    action: "spend_meditation_yin_yang",
                    keyName: stringFromUnknown(resource.key),
                    hiddenName: "yin_yang_key",
                    notesName: "meditation_notes",
                    buttonPrefix: "Increase",
                    meta: `Spend ${numberFromUnknown(resource.insight_cost)} Insight to increase ${stringFromUnknown(resource.label)} by 1.`,
                  }),
                )
              ) : (
                <article className="detail-card">
                  <p className="meta">No Yin/Yang resources are recorded on this sheet yet.</p>
                </article>
              )}
            </div>
          </section>

          <section className="read-section" id="xianxia-cultivation-conditioning">
            <div className="section-heading">
              <h2>Conditioning</h2>
            </div>
            <div className="feature-stack">
              <article className="feature-row cultivation-card">
                <div className="feature-row__header">
                  <h3>HP</h3>
                  <p className="meta">
                    Current max {numberFromUnknown(cultivation.conditioning.hp.max)} / Cap {numberFromUnknown(cultivation.conditioning.hp.cap)}
                  </p>
                </div>
                {renderActionForm(
                  "spend_conditioning",
                  "Increase HP",
                  <>
                    <input type="hidden" name="conditioning_target" value="hp" />
                    <p className="meta">
                      Spend {numberFromUnknown(cultivation.conditioning.hp.insight_cost)} Insight to increase HP maximum by{" "}
                      {numberFromUnknown(cultivation.conditioning.hp.hp_increase)}.
                    </p>
                    <label className="field">
                      <span>Notes</span>
                      <textarea name="conditioning_notes" rows={2} />
                    </label>
                  </>,
                  {
                    disabled:
                      !boolFromUnknown(cultivation.conditioning.hp.has_enough_insight) ||
                      !boolFromUnknown(cultivation.conditioning.hp.can_increase),
                  },
                )}
              </article>
              {cultivation.conditioning.efforts.map((effort) => (
                <article className="feature-row cultivation-card" key={stringFromUnknown(effort.key)}>
                  <div className="feature-row__header">
                    <h3>{stringFromUnknown(effort.label)}</h3>
                    <p className="meta">Current score {numberFromUnknown(effort.score)}</p>
                  </div>
                  {renderActionForm(
                    "spend_conditioning",
                    `Increase ${stringFromUnknown(effort.label)}`,
                    <>
                      <input type="hidden" name="conditioning_target" value="effort" />
                      <input type="hidden" name="effort_key" value={stringFromUnknown(effort.key)} />
                      <p className="meta">
                        Spend {numberFromUnknown(effort.insight_cost)} Insight to add {numberFromUnknown(effort.effort_increase)}{" "}
                        {stringFromUnknown(effort.label)} points.
                      </p>
                      <label className="field">
                        <span>Notes</span>
                        <textarea name="conditioning_notes" rows={2} />
                      </label>
                    </>,
                    { disabled: !boolFromUnknown(effort.has_enough_insight) },
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className="read-section" id="xianxia-cultivation-training">
            <div className="section-heading">
              <h2>Training</h2>
            </div>
            <div className="feature-stack">
              <article className="feature-row cultivation-card">
                <div className="feature-row__header">
                  <h3>Stance</h3>
                  <p className="meta">
                    Current max {numberFromUnknown(cultivation.training.stance.max)} / Cap {numberFromUnknown(cultivation.training.stance.cap)}
                  </p>
                </div>
                {renderActionForm(
                  "spend_training",
                  "Increase Stance",
                  <>
                    <input type="hidden" name="training_target" value="stance" />
                    <p className="meta">
                      Spend {numberFromUnknown(cultivation.training.stance.insight_cost)} Insight to increase Stance maximum by{" "}
                      {numberFromUnknown(cultivation.training.stance.stance_increase)}.
                    </p>
                    <label className="field">
                      <span>Notes</span>
                      <textarea name="training_notes" rows={2} />
                    </label>
                  </>,
                  {
                    disabled:
                      !boolFromUnknown(cultivation.training.stance.has_enough_insight) ||
                      !boolFromUnknown(cultivation.training.stance.can_increase),
                  },
                )}
              </article>
              {cultivation.training.attributes.map((attribute) => (
                <article className="feature-row cultivation-card" key={stringFromUnknown(attribute.key)}>
                  <div className="feature-row__header">
                    <h3>{stringFromUnknown(attribute.label)}</h3>
                    <p className="meta">Current score {numberFromUnknown(attribute.score)}</p>
                  </div>
                  {renderActionForm(
                    "spend_training",
                    `Increase ${stringFromUnknown(attribute.label)}`,
                    <>
                      <input type="hidden" name="training_target" value="attribute" />
                      <input type="hidden" name="attribute_key" value={stringFromUnknown(attribute.key)} />
                      <p className="meta">
                        Spend {numberFromUnknown(attribute.insight_cost)} Insight to add {numberFromUnknown(attribute.attribute_increase)}{" "}
                        {stringFromUnknown(attribute.label)} points.
                      </p>
                      <label className="field">
                        <span>Notes</span>
                        <textarea name="training_notes" rows={2} />
                      </label>
                    </>,
                    { disabled: !boolFromUnknown(attribute.has_enough_insight) },
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className="read-section" id="xianxia-cultivation-martial-arts">
            <div className="section-heading">
              <h2>Martial Arts</h2>
            </div>
            {renderMartialArts(cultivation)}
          </section>

          <section className="read-section" id="xianxia-cultivation-techniques">
            <div className="section-heading">
              <h2>Generic Techniques</h2>
            </div>
            {renderGenericTechniques(cultivation)}
          </section>

          {renderRealmAscension(cultivation)}

          <section className="read-section" id="xianxia-cultivation-history">
            <div className="section-heading">
              <h2>Advancement History</h2>
            </div>
            {cultivation.history.length ? (
              <div className="feature-stack">
                {cultivation.history.map((event) => (
                  <article className="feature-row" key={`${event.index}-${event.action}`}>
                    <div className="feature-row__header">
                      <h3>{event.action}</h3>
                      <p className="meta">Entry {event.index}</p>
                    </div>
                    {event.details?.length ? (
                      <ul className="plain-list slot-list">
                        {event.details.map((detail) => (
                          <li key={`${detail.label}-${detail.value}`}>
                            <strong>{detail.label}:</strong> {detail.value}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : (
              <article className="detail-card">
                <p className="meta">No advancement history is recorded on this sheet yet.</p>
              </article>
            )}
          </section>
        </>
      ) : null}
    </>
  );
}

