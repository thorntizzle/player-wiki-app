import React, { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import type { FormEvent } from "react";

import type { CharacterProgressionRepairPayload } from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { queryClient, useApiClient } from "../apiClientContext";
import { ApiErrorNotice, ToastNotice, useToastNotice, type ApiMessageEnvelope } from "../components/feedback";
import {
  characterAuthoringStringValues,
  characterNameFromRecord,
  characterProgressionRepairValuesFromContext,
  classLevelTextFromRecord,
  draftString,
  selectOptions,
  type CharacterAuthoringValues,
} from "../characterAuthoringUtils";
import { asStringArray } from "../characterValueUtils";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

export function CharacterProgressionRepairPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/progression-repair",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);
  const { clearToast, showToast, toastMessage, toastTone } = useToastNotice({ defaultTone: "success" });

  const repairQuery = useQuery({
    queryKey: ["character-progression-repair", campaignSlug, characterSlug],
    queryFn: () => apiClient.getCharacterProgressionRepair(campaignSlug, characterSlug),
    enabled: Boolean(campaignSlug && characterSlug),
    retry: false,
  });

  const data = repairQuery.data;
  const repair = data?.repair ?? null;

  useEffect(() => {
    if (isAuthError(repairQuery.error)) {
      setAuthRequired(true);
    }
  }, [repairQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!repair || loadedRevision === repair.state_revision) {
      return;
    }
    setDraftValues(characterProgressionRepairValuesFromContext(repair));
    setLoadedRevision(repair.state_revision);
    setErrorMessage(null);
  }, [repair, loadedRevision]);

  const updateValue = (key: string, value: string) => {
    setDraftValues((current) => ({ ...current, [key]: value }));
  };

  const submitRepair = useMutation({
    mutationFn: (payload: CharacterProgressionRepairPayload) =>
      apiClient.submitCharacterProgressionRepair(campaignSlug, characterSlug, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(["character-progression-repair", campaignSlug, characterSlug], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setDraftValues(characterProgressionRepairValuesFromContext(response.repair));
      setLoadedRevision(response.repair?.state_revision ?? null);
      showToast(response.message || "Progression repair saved.", "success");
      setErrorMessage(null);
      if (!response.supported && response.links.level_up_url) {
        window.location.assign(response.links.level_up_url);
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
    if (!repair) {
      setErrorMessage({ status: 400, message: "The progression repair context has not loaded yet." });
      return;
    }
    clearToast();
    setErrorMessage(null);
    submitRepair.mutate({
      expected_revision: repair.state_revision,
      values: characterAuthoringStringValues(draftValues),
    });
  };

  const loadingError = getApiErrorMessage(repairQuery.error);
  const characterName = characterNameFromRecord(data?.character) || repair?.character_name || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);
  const reasons = asStringArray(repair?.readiness?.reasons);

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="eyebrow">Character progression</p>
        <h1>Prepare {characterName} For Native Level-Up</h1>
        <p className="lede">
          Repair imported baseline links and missing DND-5E progression details before advancing this character
          {repair?.current_level ? ` past level ${repair.current_level}` : ""}.
        </p>
        {classLevelText ? <p className="meta">{classLevelText}</p> : null}
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={repairQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      <ToastNotice message={toastMessage} tone={toastTone} />

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>{data.lane === "ready" ? "Progression Repair Is Complete" : "Progression Repair Is Not Available In Gen2"}</h2>
          <p>{data.unsupported_message || "This character is not ready for Gen2 progression repair."}</p>
          <div className="hero-actions">
            {data.links.level_up_url ? (
              <a className="button-link" href={data.links.level_up_url}>
                Level Up
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

      {repair ? (
        <article className="card character-edit-sheet">
          <section className="read-section">
            <div className="section-heading">
              <div>
                <h2>Progression Repair</h2>
                {repair.readiness?.message ? <p className="meta">{repair.readiness.message}</p> : null}
              </div>
            </div>
            {reasons.length ? (
              <div className="builder-section">
                <h3>What Needs Repair</h3>
                <ul className="plain-list builder-feature-list">
                  {reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          <form className="stack-form character-builder-form" onSubmit={submitForm}>
            {repair.class_rows?.length ? (
              <section className="builder-section">
                <h2>Class Rows</h2>
                <div className="builder-field-grid">
                  {repair.class_rows.map((row) => (
                    <React.Fragment key={row.row_id || row.class_field_name}>
                      <label className="field">
                        <span>
                          {row.class_name || "Class"}
                          {row.row_level ? ` ${row.row_level}` : ""}
                        </span>
                        <select
                          name={row.class_field_name}
                          value={draftString(draftValues, row.class_field_name, row.class_selected || "")}
                          onChange={(event) => updateValue(row.class_field_name, event.currentTarget.value)}
                        >
                          <option value="">Choose an option</option>
                          {selectOptions(row.class_options ?? [])}
                        </select>
                      </label>
                      <label className="field">
                        <span>Subclass Link</span>
                        <select
                          name={row.subclass_field_name}
                          value={draftString(draftValues, row.subclass_field_name, row.subclass_selected || "")}
                          onChange={(event) => updateValue(row.subclass_field_name, event.currentTarget.value)}
                        >
                          <option value="">No subclass link</option>
                          {selectOptions(row.subclass_options ?? [])}
                        </select>
                      </label>
                    </React.Fragment>
                  ))}
                </div>
              </section>
            ) : null}

            <section className="builder-section">
              <h2>Baseline Links</h2>
              <div className="builder-field-grid">
                <label className="field">
                  <span>Species</span>
                  <select
                    name="repair_species_slug"
                    value={draftString(draftValues, "repair_species_slug")}
                    onChange={(event) => updateValue("repair_species_slug", event.currentTarget.value)}
                  >
                    <option value="">Choose an option</option>
                    {selectOptions(repair.species_options ?? [])}
                  </select>
                </label>
                <label className="field">
                  <span>Background</span>
                  <select
                    name="repair_background_slug"
                    value={draftString(draftValues, "repair_background_slug")}
                    onChange={(event) => updateValue("repair_background_slug", event.currentTarget.value)}
                  >
                    <option value="">Choose an option</option>
                    {selectOptions(repair.background_options ?? [])}
                  </select>
                </label>
              </div>
            </section>

            {repair.feat_rows?.length ? (
              <section className="builder-section">
                <h2>Prior Feats</h2>
                <div className="builder-field-grid">
                  {repair.feat_rows.map((row) => (
                    <label className="field" key={row.name}>
                      <span>Feat {row.index ?? ""}</span>
                      <select
                        name={row.name}
                        value={draftString(draftValues, row.name, row.selected || "")}
                        onChange={(event) => updateValue(row.name, event.currentTarget.value)}
                      >
                        <option value="">Leave unchanged</option>
                        {selectOptions(row.options ?? [])}
                      </select>
                      <small>Backfill older feat picks not linked cleanly.</small>
                    </label>
                  ))}
                </div>
              </section>
            ) : null}

            {repair.optionalfeature_rows?.length ? (
              <section className="builder-section">
                <h2>Prior Optional Features</h2>
                <div className="builder-field-grid">
                  {repair.optionalfeature_rows.map((row) => (
                    <label className="field" key={row.name}>
                      <span>Optional Feature {row.index ?? ""}</span>
                      <select
                        name={row.name}
                        value={draftString(draftValues, row.name, row.selected || "")}
                        onChange={(event) => updateValue(row.name, event.currentTarget.value)}
                      >
                        <option value="">Leave unchanged</option>
                        {selectOptions(row.options ?? [])}
                      </select>
                      <small>Repair prior fighting styles, maneuvers, and similar linked feature choices.</small>
                    </label>
                  ))}
                </div>
              </section>
            ) : null}

            {repair.spell_rows?.length ? (
              <section className="builder-section">
                <h2>Spell Baseline</h2>
                <div className="builder-field-grid">
                  {repair.spell_rows.map((row) => (
                    <React.Fragment key={row.field_name}>
                      {(row.class_row_options?.length ?? 0) > 1 && row.class_row_field_name ? (
                        <label className="field">
                          <span>{row.name || "Spell"} Class Row</span>
                          <select
                            name={row.class_row_field_name}
                            value={draftString(draftValues, row.class_row_field_name, row.class_row_selected || "")}
                            onChange={(event) => updateValue(row.class_row_field_name || "", event.currentTarget.value)}
                          >
                            <option value="">Choose a class row</option>
                            {selectOptions(row.class_row_options ?? [])}
                          </select>
                        </label>
                      ) : null}
                      <label className="field">
                        <span>{row.name || "Spell"}</span>
                        <select
                          name={row.field_name}
                          value={draftString(draftValues, row.field_name, row.selected || "")}
                          onChange={(event) => updateValue(row.field_name, event.currentTarget.value)}
                        >
                          <option value="">Choose a spell mark</option>
                          {selectOptions(row.options ?? [])}
                        </select>
                      </label>
                    </React.Fragment>
                  ))}
                </div>
              </section>
            ) : null}

            <div className="builder-actions">
              <button className="ghost-button" type="submit" disabled={submitRepair.isPending}>
                {submitRepair.isPending ? "Saving..." : "Save Repair"}
              </button>
              {data?.links?.character_url ? (
                <a className="ghost-button" href={data.links.character_url}>
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
