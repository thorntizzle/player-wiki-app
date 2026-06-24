import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import type { FormEvent } from "react";

import type {
  CharacterEditorChoiceField,
  CharacterEditorEquipmentRow,
  CharacterEditorFeatureRow,
  CharacterEditorField,
  CharacterEditorRecoverablePenaltyRow,
} from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { queryClient, useApiClient } from "../apiClientContext";
import { ApiErrorNotice, type ApiMessageEnvelope } from "../components/feedback";
import {
  characterNameFromRecord,
  classLevelTextFromRecord,
  editorSelectOptions,
  editorValuesFromContext,
} from "../characterAuthoringUtils";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

export function CharacterAdvancedEditorPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug/edit",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<ApiMessageEnvelope | null>(null);

  const editorQuery = useQuery({
    queryKey: ["character-advanced-editor", campaignSlug, characterSlug],
    queryFn: () => apiClient.getCharacterAdvancedEditor(campaignSlug, characterSlug),
    enabled: Boolean(campaignSlug && characterSlug),
  });

  const data = editorQuery.data;
  const editor = data?.editor ?? null;

  useEffect(() => {
    if (!editor || loadedRevision === editor.state_revision) {
      return;
    }
    setDraftValues(editorValuesFromContext(editor));
    setLoadedRevision(editor.state_revision);
    setErrorMessage(null);
  }, [editor, loadedRevision]);

  const updateDraftValue = (key: string, value: string) => {
    setDraftValues((current) => ({ ...current, [key]: value }));
  };

  const saveEditor = useMutation({
    mutationFn: () => {
      if (!editor) {
        throw new Error("The editor context has not loaded yet.");
      }
      return apiClient.updateCharacterAdvancedEditor(campaignSlug, characterSlug, {
        expected_revision: editor.state_revision,
        values: draftValues,
      });
    },
    onSuccess: (response) => {
      queryClient.setQueryData(["character-advanced-editor", campaignSlug, characterSlug], response);
      queryClient.setQueryData(["character-detail", campaignSlug, characterSlug], {
        ok: true,
        character: response.character,
        links: response.links,
      });
      setDraftValues(editorValuesFromContext(response.editor));
      setLoadedRevision(response.editor?.state_revision ?? null);
      setStatusMessage(response.message || "Character details updated.");
      setErrorMessage(null);
    },
    onError: (error) => {
      setErrorMessage(getApiErrorMessage(error));
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
    },
  });

  const submitEditor = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatusMessage(null);
    setErrorMessage(null);
    saveEditor.mutate();
  };

  const renderField = (field: CharacterEditorField, options?: { textarea?: boolean; number?: boolean }) => (
    <article className="detail-card" key={field.name}>
      <label className="field">
        <span>{field.label}</span>
        {options?.textarea ? (
          <textarea
            name={field.name}
            rows={6}
            value={draftValues[field.name] ?? field.value ?? ""}
            onChange={(event) => updateDraftValue(field.name, event.currentTarget.value)}
          />
        ) : (
          <input
            type={options?.number ? "number" : "text"}
            name={field.name}
            value={draftValues[field.name] ?? field.value ?? ""}
            onChange={(event) => updateDraftValue(field.name, event.currentTarget.value)}
          />
        )}
      </label>
      {field.help_text ? <p className="meta">{field.help_text}</p> : null}
    </article>
  );

  const renderChoiceField = (field: CharacterEditorChoiceField) => (
    <label className="field" key={field.name}>
      <span>{field.label}</span>
      <select
        name={field.name}
        value={draftValues[field.name] ?? field.selected ?? ""}
        onChange={(event) => updateDraftValue(field.name, event.currentTarget.value)}
      >
        {editorSelectOptions(field.options, "Choose an option")}
      </select>
      {field.help_text ? <small>{field.help_text}</small> : null}
    </label>
  );

  const renderRecoverablePenalty = (row: CharacterEditorRecoverablePenaltyRow) => (
    <article className="detail-card character-edit-row" key={row.index}>
      <div className="character-edit-row__grid">
        <label className="field">
          <span>Source</span>
          <input
            type="text"
            value={draftValues[`recoverable_penalty_source_${row.index}`] ?? row.source ?? ""}
            onChange={(event) => updateDraftValue(`recoverable_penalty_source_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Target</span>
          <select
            value={draftValues[`recoverable_penalty_target_${row.index}`] ?? row.target ?? ""}
            onChange={(event) => updateDraftValue(`recoverable_penalty_target_${row.index}`, event.currentTarget.value)}
          >
            {editorSelectOptions(editor?.recoverable_penalty_target_options ?? [], "Choose a target")}
          </select>
        </label>
        <label className="field">
          <span>Penalty Amount</span>
          <input
            type="number"
            min={0}
            value={draftValues[`recoverable_penalty_amount_${row.index}`] ?? row.amount ?? ""}
            onChange={(event) => updateDraftValue(`recoverable_penalty_amount_${row.index}`, event.currentTarget.value)}
          />
        </label>
      </div>
      <label className="field">
        <span>Notes</span>
        <textarea
          rows={3}
          value={draftValues[`recoverable_penalty_notes_${row.index}`] ?? row.notes ?? ""}
          onChange={(event) => updateDraftValue(`recoverable_penalty_notes_${row.index}`, event.currentTarget.value)}
        />
      </label>
    </article>
  );

  const renderFeatureRow = (row: CharacterEditorFeatureRow) => (
    <article className="detail-card character-edit-row" key={row.index}>
      <div className="character-edit-row__grid">
        <label className="field">
          <span>Name</span>
          <input
            type="text"
            value={draftValues[`custom_feature_name_${row.index}`] ?? row.name ?? ""}
            onChange={(event) => updateDraftValue(`custom_feature_name_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Activation</span>
          <select
            value={draftValues[`custom_feature_activation_type_${row.index}`] ?? row.activation_type ?? ""}
            onChange={(event) => updateDraftValue(`custom_feature_activation_type_${row.index}`, event.currentTarget.value)}
          >
            {editorSelectOptions(editor?.activation_options ?? [])}
          </select>
        </label>
      </div>
      <label className="field">
        <span>Linked Page</span>
        <select
          value={draftValues[`custom_feature_page_ref_${row.index}`] ?? row.page_ref ?? ""}
          onChange={(event) => updateDraftValue(`custom_feature_page_ref_${row.index}`, event.currentTarget.value)}
        >
          {editorSelectOptions(editor?.campaign_page_options ?? [], "No linked page")}
        </select>
      </label>
      <label className="field">
        <span>Description (Markdown)</span>
        <textarea
          rows={6}
          value={draftValues[`custom_feature_description_${row.index}`] ?? row.description_markdown ?? ""}
          onChange={(event) => updateDraftValue(`custom_feature_description_${row.index}`, event.currentTarget.value)}
        />
      </label>
      <div className="character-edit-row__grid">
        <label className="field">
          <span>Uses / Max</span>
          <input
            type="number"
            min={0}
            value={draftValues[`custom_feature_resource_max_${row.index}`] ?? row.resource_max ?? ""}
            onChange={(event) => updateDraftValue(`custom_feature_resource_max_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Reset On</span>
          <select
            value={draftValues[`custom_feature_resource_reset_on_${row.index}`] ?? row.resource_reset_on ?? ""}
            onChange={(event) => updateDraftValue(`custom_feature_resource_reset_on_${row.index}`, event.currentTarget.value)}
          >
            {editorSelectOptions(editor?.resource_reset_options ?? [])}
          </select>
        </label>
      </div>
      {row.choice_fields?.length ? <div className="detail-grid character-edit-grid">{row.choice_fields.map(renderChoiceField)}</div> : null}
      <p className="meta">Leave Uses / Max blank for a non-tracked feature. Existing spent values are preserved when you change the limit.</p>
    </article>
  );

  const renderEquipmentRow = (row: CharacterEditorEquipmentRow) => (
    <article className="detail-card character-edit-row" key={row.index}>
      <div className="character-edit-row__grid character-edit-row__grid--equipment">
        <label className="field">
          <span>Name</span>
          <input
            type="text"
            value={draftValues[`manual_item_name_${row.index}`] ?? row.name ?? ""}
            onChange={(event) => updateDraftValue(`manual_item_name_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Quantity</span>
          <input
            type="number"
            min={0}
            value={draftValues[`manual_item_quantity_${row.index}`] ?? row.quantity ?? ""}
            onChange={(event) => updateDraftValue(`manual_item_quantity_${row.index}`, event.currentTarget.value)}
          />
        </label>
        <label className="field">
          <span>Weight</span>
          <input
            type="text"
            value={draftValues[`manual_item_weight_${row.index}`] ?? row.weight ?? ""}
            onChange={(event) => updateDraftValue(`manual_item_weight_${row.index}`, event.currentTarget.value)}
          />
        </label>
      </div>
      <label className="field">
        <span>Linked Page</span>
        <select
          value={draftValues[`manual_item_page_ref_${row.index}`] ?? row.page_ref ?? ""}
          onChange={(event) => updateDraftValue(`manual_item_page_ref_${row.index}`, event.currentTarget.value)}
        >
          {editorSelectOptions(editor?.equipment_page_options ?? [], "No linked page")}
        </select>
      </label>
      <label className="field">
        <span>Notes</span>
        <textarea
          rows={4}
          value={draftValues[`manual_item_notes_${row.index}`] ?? row.notes ?? ""}
          onChange={(event) => updateDraftValue(`manual_item_notes_${row.index}`, event.currentTarget.value)}
        />
      </label>
    </article>
  );

  const characterName = characterNameFromRecord(data?.character) || characterSlug;
  const classLevelText = classLevelTextFromRecord(data?.character);
  const loadingError = getApiErrorMessage(editorQuery.error);

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="eyebrow">Character editor</p>
        <h1>Edit {characterName}</h1>
        <p className="lede">Advanced campaign-time adjustments and durable reference text for this character are managed here.</p>
        <div className="hero-actions">
          {data?.links?.character_url ? (
            <a className="ghost-button" href={data.links.character_url}>
              Back to sheet
            </a>
          ) : null}
          {classLevelText ? <span className="meta">{classLevelText}</span> : null}
        </div>
      </section>

      <ApiErrorNotice isLoading={editorQuery.isLoading} message={loadingError || errorMessage} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}

      {data && !data.supported ? (
        <section className="card auth-card">
          <h2>Advanced Editor Is Not Available In Gen2</h2>
          <p>{data.unsupported_message || "This character system uses a different authoring lane."}</p>
          <div className="hero-actions">
            {data.links.character_url ? (
              <a className="button-link" href={data.links.character_url}>
                Back to sheet
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

      {editor ? (
        <form className="card character-edit-sheet gen2-character-editor" onSubmit={submitEditor}>
          <section className="read-section">
            <div className="section-heading">
              <h2>Proficiencies</h2>
            </div>
            <div className="detail-grid character-edit-grid">{editor.proficiency_fields.map((field) => renderField(field, { textarea: true }))}</div>
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Reference Text</h2>
            </div>
            <div className="detail-grid character-edit-grid">{editor.reference_fields.map((field) => renderField(field, { textarea: true }))}</div>
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Campaign Adjustments</h2>
            </div>
            <p className="meta">Use these controlled numeric adjustments when campaign play has changed sheet math outside builder and level-up rules.</p>
            <div className="detail-grid character-edit-grid">{editor.stat_adjustment_fields.map((field) => renderField(field, { number: true }))}</div>
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Recoverable Penalties</h2>
            </div>
            <p className="meta">Track sourced max-HP and ability-score reductions here when the penalty can later be reduced or removed.</p>
            <div className="character-edit-stack">{editor.recoverable_penalty_rows.map(renderRecoverablePenalty)}</div>
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Custom Features</h2>
            </div>
            {editor.linked_feature_authoring_supported ? (
              <>
                <p className="meta">Campaign boons, curses, training rewards, and other custom feature text.</p>
                <div className="character-edit-stack">{editor.feature_rows.map(renderFeatureRow)}</div>
              </>
            ) : (
              <>
                <p className="meta">{editor.linked_feature_authoring_message}</p>
                <p className="meta">Other edit sections stay available while progression repair is pending.</p>
              </>
            )}
          </section>

          <section className="read-section">
            <div className="section-heading">
              <h2>Manual Equipment</h2>
            </div>
            {editor.existing_managed_equipment?.length ? (
              <article className="detail-card">
                <h3>Existing built-in equipment</h3>
                <ul className="plain-list">
                  {editor.existing_managed_equipment.map((item) => (
                    <li key={`${item.name}-${item.quantity ?? ""}-${item.weight ?? ""}`}>
                      <strong>{item.name}</strong>
                      {item.quantity ? ` x${item.quantity}` : ""}
                      {item.weight ? <span className="meta"> | {item.weight}</span> : null}
                    </li>
                  ))}
                </ul>
              </article>
            ) : null}
            <div className="character-edit-stack">{editor.equipment_rows.map(renderEquipmentRow)}</div>
          </section>

          <div className="hero-actions">
            <button type="submit" disabled={saveEditor.isPending}>
              {saveEditor.isPending ? "Saving..." : "Save character edits"}
            </button>
            {data?.links?.character_url ? (
              <a className="ghost-button" href={data.links.character_url}>
                Back to sheet
              </a>
            ) : null}
          </div>
        </form>
      ) : null}
    </>
  );
}
