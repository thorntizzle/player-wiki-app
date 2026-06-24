import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import type { FormEvent } from "react";

import type { CharacterXianxiaManualImportContext } from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { ApiErrorNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import {
  draftString,
  manualImportRows,
  optionLabel,
  optionValue,
  selectOptions,
  updateAuthoringValue,
  type CharacterAuthoringValues,
} from "../characterAuthoringUtils";
import { stringFromUnknown } from "../characterValueUtils";

export function CharacterXianxiaManualImportPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/characters/import/xianxia-manual",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [contextValues, setContextValues] = useState<Record<string, string>>({});
  const [manualContext, setManualContext] = useState<CharacterXianxiaManualImportContext | null>(null);
  const [rowCount, setRowCount] = useState(3);
  const [statusMessage, setStatusMessage] = useState("");

  const importQuery = useQuery({
    queryKey: ["character-xianxia-import", resolvedCampaignSlug, JSON.stringify(contextValues)],
    queryFn: () => apiClient.getXianxiaManualImportContext(resolvedCampaignSlug, contextValues),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(importQuery.error)) {
      setAuthRequired(true);
    }
  }, [importQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!manualContext && importQuery.data?.import_context) {
      setManualContext(importQuery.data.import_context);
    }
  }, [importQuery.data, manualContext]);

  const importMutation = useMutation({
    mutationFn: ({ confirm }: { confirm: boolean }) =>
      apiClient.submitXianxiaManualImport(resolvedCampaignSlug, {
        values: Object.fromEntries(Object.entries(draftValues).map(([key, value]) => [key, Array.isArray(value) ? value.join("\n") : value])),
        confirm_import: confirm,
      }),
    onSuccess: (payload) => {
      setStatusMessage(payload.message || "");
      if ("character" in payload) {
        if (payload.links.character_url) {
          window.location.assign(payload.links.character_url);
        }
        return;
      }
      setManualContext(payload.import_context);
      setContextValues(payload.import_context.values);
    },
  });

  const context = manualContext || importQuery.data?.import_context;
  const links = importQuery.data?.links;
  const error = getApiErrorMessage(importQuery.error || importMutation.error);

  const updateValue = (key: string, value: string) => {
    updateAuthoringValue(setDraftValues, key, value);
  };

  const submitPreview = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatusMessage("");
    importMutation.mutate({ confirm: false });
  };

  const confirmImport = () => {
    setStatusMessage("");
    importMutation.mutate({ confirm: true });
  };

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="meta">Character importer</p>
        <h1>Import Existing Xianxia Character</h1>
        <p className="lede">Preview copied values, then create a normal native Xianxia sheet with SQLite-backed mutable state.</p>
        <div className="hero-actions character-authoring-hero-actions">
          {links?.gen2_roster_url ? (
            <a className="ghost-button" href={links.gen2_roster_url}>
              Back to roster
            </a>
          ) : null}
        </div>
      </section>
      <ApiErrorNotice isLoading={importQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}
      {context?.preview ? (
        <section className="card character-authoring-preview-card">
          <h2>Review Import</h2>
          <div className="builder-preview-list">
            {Object.entries(context.preview).map(([key, value]) => (
              <div key={key}>
                <span className="meta">{key.replace(/_/g, " ")}</span>
                <strong>{stringFromUnknown(value)}</strong>
              </div>
            ))}
          </div>
          <button type="button" onClick={confirmImport} disabled={importMutation.isPending}>
            {importMutation.isPending ? "Importing..." : "Confirm import"}
          </button>
        </section>
      ) : null}

      {context ? (
        <div className="character-authoring-layout">
          <form className="stack-form character-authoring-form" onSubmit={submitPreview}>
            <section className="builder-section">
              <h2>Identity</h2>
              <div className="builder-field-grid">
                {[
                  ["name", "Character Name", ""],
                  ["character_slug", "Character Slug", ""],
                  ["reputation", "Reputation", "Unknown"],
                ].map(([key, label, fallback]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <input type="text" name={key} value={draftString(draftValues, key, context.values[key] || fallback)} onChange={(event) => updateValue(key, event.currentTarget.value)} />
                  </label>
                ))}
                <label className="field">
                  <span>Realm</span>
                  <select name="realm" value={draftString(draftValues, "realm", context.values.realm || "Mortal")} onChange={(event) => updateValue("realm", event.currentTarget.value)}>
                    {context.realm_choices.map((realm) => (
                      <option key={realm} value={realm}>
                        {realm}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Honor</span>
                  <select name="honor" value={draftString(draftValues, "honor", context.values.honor || "Honorable")} onChange={(event) => updateValue("honor", event.currentTarget.value)}>
                    {context.honor_choices.map((honor) => (
                      <option key={honor} value={honor}>
                        {honor}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </section>

            {([
              { title: "Attributes", fields: context.attribute_fields },
              { title: "Efforts", fields: context.effort_fields },
            ] as Array<{ title: string; fields: CharacterXianxiaManualImportContext["attribute_fields"] }>).map(({ title, fields }) => (
              <section className="builder-section" key={title}>
                <h2>{title}</h2>
                <div className="builder-field-grid">
                  {fields.map((field) => (
                    <label className="field" key={field.input_name}>
                      <span>{field.label}</span>
                      <input type="number" name={field.input_name} value={draftString(draftValues, field.input_name, field.value)} step={1} onChange={(event) => updateValue(field.input_name, event.currentTarget.value)} />
                    </label>
                  ))}
                </div>
              </section>
            ))}

            <section className="builder-section">
              <h2>Resources</h2>
              <div className="builder-field-grid">
                {[
                  ["hp_max", "HP Max", "10"],
                  ["stance_max", "Stance Max", "10"],
                  ["manual_armor_bonus", "Manual Armor Bonus", "0"],
                  ["insight_available", "Insight Available", "0"],
                  ["insight_spent", "Insight Spent", "0"],
                  ["yin_max", "Yin Max", "1"],
                  ["yang_max", "Yang Max", "1"],
                  ["dao_max", "Dao Max", "3"],
                  ["coin", "Coin", "0"],
                  ["supply", "Supply", "0"],
                  ["spirit_stones", "Spirit Stones", "0"],
                ].map(([key, label, fallback]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <input type="number" name={key} value={draftString(draftValues, key, context.values[key] || fallback)} step={1} onChange={(event) => updateValue(key, event.currentTarget.value)} />
                  </label>
                ))}
                {context.energy_fields.map((field) => (
                  <label className="field" key={field.max_input_name}>
                    <span>{field.label} Max</span>
                    <input type="number" name={field.max_input_name} value={draftString(draftValues, field.max_input_name, field.max_value)} step={1} onChange={(event) => updateValue(field.max_input_name, event.currentTarget.value)} />
                  </label>
                ))}
              </div>
            </section>

            <section className="builder-section">
              <h2>Skills</h2>
              <label className="field">
                <span>Trained Skills</span>
                <textarea name="trained_skills_text" rows={6} value={draftString(draftValues, "trained_skills_text", context.values.trained_skills_text || "")} onChange={(event) => updateValue("trained_skills_text", event.currentTarget.value)} />
              </label>
            </section>

            <section className="builder-section">
              <h2>Martial Arts</h2>
              <div className="manual-import-rows">
                {manualImportRows(context, rowCount, draftValues).map((row) => (
                  <article className="manual-import-row" key={row.index}>
                    <h3>Martial Art {row.index}</h3>
                    <div className="builder-field-grid">
                      <label className="field">
                        <span>Stored Martial Art</span>
                        <select name={row.slug_input_name} value={row.selected_slug} onChange={(event) => updateValue(row.slug_input_name, event.currentTarget.value)}>
                          <option value="">Unlinked/manual</option>
                          {selectOptions(context.martial_art_options)}
                        </select>
                      </label>
                      {[
                        [row.name_input_name, "Manual Name", row.name],
                        [row.rank_input_name, "Current Rank", row.rank],
                        [row.teacher_input_name, "Teacher", row.teacher],
                        [row.breakthrough_input_name, "Breakthrough", row.breakthrough],
                        [row.notes_input_name, "Notes", row.notes],
                      ].map(([key, label, value]) => (
                        <label className="field" key={key}>
                          <span>{label}</span>
                          <input type="text" name={key} value={value} onChange={(event) => updateValue(key, event.currentTarget.value)} />
                        </label>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
              <button type="button" className="ghost-button" onClick={() => setRowCount((current) => current + 1)}>
                Add Martial Art
              </button>
            </section>

            <section className="builder-section">
              <h2>Inventory And Notes</h2>
              <label className="field">
                <span>Manual Inventory</span>
                <textarea name="inventory_text" rows={8} value={draftString(draftValues, "inventory_text", context.values.inventory_text || "")} onChange={(event) => updateValue("inventory_text", event.currentTarget.value)} />
              </label>
              <label className="field">
                <span>Reference Notes</span>
                <textarea name="additional_notes_markdown" rows={5} value={draftString(draftValues, "additional_notes_markdown", context.values.additional_notes_markdown || "")} onChange={(event) => updateValue("additional_notes_markdown", event.currentTarget.value)} />
              </label>
              <label className="field">
                <span>Player Notes</span>
                <textarea name="player_notes_markdown" rows={5} value={draftString(draftValues, "player_notes_markdown", context.values.player_notes_markdown || "")} onChange={(event) => updateValue("player_notes_markdown", event.currentTarget.value)} />
              </label>
            </section>

            <div className="builder-actions">
              <button type="submit" disabled={importMutation.isPending}>
                {importMutation.isPending ? "Previewing..." : "Preview import"}
              </button>
            </div>
          </form>
          <aside className="sidebar character-authoring-sidebar">
            <section className="card sidebar-card">
              <h2>Available Martial Arts</h2>
              {context.martial_art_options.length ? (
                <ul className="plain-list resource-preview-list">
                  {context.martial_art_options.map((option) => (
                    <li key={optionValue(option)}>
                      <span>{optionLabel(option)}</span>
                      <strong>{option.available_rank_labels?.join(", ") || option.martial_art_style || optionValue(option)}</strong>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta">No enabled Martial Art Systems entries are available.</p>
              )}
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}
