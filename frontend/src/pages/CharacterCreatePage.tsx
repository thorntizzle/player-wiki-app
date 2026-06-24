import React, { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import type { FormEvent } from "react";

import type {
  CharacterCreateContextResponse,
  CharacterCreateSubmitPayload,
  CharacterDndCreateContext,
  CharacterXianxiaCreateContext,
} from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { CharacterDndChoiceSelect } from "../components/CharacterAuthoringFields";
import { CharacterPreviewList } from "../components/CharacterAuthoringPreview";
import { ApiErrorNotice, ToastNotice, useToastNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import {
  draftString,
  draftStringArray,
  selectOptions,
  type CharacterAuthoringValues,
} from "../characterAuthoringUtils";
import { stringFromUnknown } from "../characterValueUtils";

function isDndCreateContext(value: CharacterCreateContextResponse["create"] | undefined): value is CharacterDndCreateContext {
  return Boolean(value && value.lane === "dnd5e");
}

function isXianxiaCreateContext(value: CharacterCreateContextResponse["create"] | undefined): value is CharacterXianxiaCreateContext {
  return Boolean(value && value.lane === "xianxia");
}

export function CharacterCreatePage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/characters/new",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const [draftValues, setDraftValues] = useState<CharacterAuthoringValues>({});
  const [contextValues, setContextValues] = useState<CharacterAuthoringValues>({});
  const { clearToast, showToast, toastMessage, toastTone } = useToastNotice({ defaultTone: "success" });

  const createQuery = useQuery({
    queryKey: ["character-create", resolvedCampaignSlug, JSON.stringify(contextValues)],
    queryFn: () => apiClient.getCharacterCreateContext(resolvedCampaignSlug, contextValues),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(createQuery.error)) {
      setAuthRequired(true);
    }
  }, [createQuery.error, setAuthRequired]);

  useEffect(() => {
    const create = createQuery.data?.create;
    if (!create || Object.keys(draftValues).length) {
      return;
    }
    if (isDndCreateContext(create)) {
      setDraftValues({ ...create.values });
    } else if (isXianxiaCreateContext(create)) {
      const nextValues: CharacterAuthoringValues = {};
      for (const field of [...create.attribute_fields, ...create.effort_fields, ...create.energy_fields, ...create.trained_skill_fields]) {
        nextValues[field.input_name] = field.value;
      }
      for (const field of create.martial_art_fields) {
        nextValues[field.art_input_name] = field.selected_slug;
        nextValues[field.rank_input_name] = field.selected_rank;
      }
      nextValues[create.manual_armor_field.input_name] = create.manual_armor_field.value;
      nextValues[create.dao_field.input_name] = create.dao_field.value;
      setDraftValues(nextValues);
    }
  }, [createQuery.data, draftValues]);

  const createMutation = useMutation({
    mutationFn: (payload: CharacterCreateSubmitPayload) => apiClient.createCharacter(resolvedCampaignSlug, payload),
    onSuccess: (payload) => {
      showToast(payload.message, "success");
      if (payload.links.character_url) {
        window.location.assign(payload.links.character_url);
      }
    },
  });

  const error = getApiErrorMessage(createQuery.error || createMutation.error);
  const data = createQuery.data;
  const create = data?.create;

  const refreshContext = (values: CharacterAuthoringValues = draftValues) => {
    setContextValues({ ...values });
  };

  const submitCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearToast();
    createMutation.mutate({ values: draftValues });
  };

  const updateValue = (key: string, value: string | string[], refresh = false) => {
    const nextValues = { ...draftValues, [key]: value };
    setDraftValues(nextValues);
    if (refresh) {
      refreshContext(nextValues);
    }
  };

  return (
    <>
      <section className="hero compact character-authoring-hero">
        <p className="meta">Character authoring</p>
        <h1>{create?.lane === "xianxia" ? "Create Xianxia Character" : "Create Character"}</h1>
        <p className="lede">Create native character records through the same campaign system lane used by the Flask builder.</p>
        <div className="hero-actions character-authoring-hero-actions">
          {data?.links.gen2_roster_url ? (
            <a className="ghost-button" href={data.links.gen2_roster_url}>
              Back to roster
            </a>
          ) : null}
          {data?.links.gen2_import_xianxia_url ? (
            <a className="ghost-button" href={data.links.gen2_import_xianxia_url}>
              Import existing
            </a>
          ) : null}
        </div>
      </section>
      <ApiErrorNotice isLoading={createQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      <ToastNotice message={toastMessage} tone={toastTone} />

      {isDndCreateContext(create) ? (
        <div className="character-authoring-layout">
          <form className="stack-form character-authoring-form" onSubmit={submitCreate}>
            {!create.builder_ready ? (
              <p className="status status-warning">The builder needs a supported base class plus enabled Systems species and backgrounds before it can create characters in this campaign.</p>
            ) : null}
            <section className="builder-section">
              <h2>Identity</h2>
              <div className="builder-field-grid">
                {[
                  ["name", "Character Name", "Zigzag Blackscar"],
                  ["character_slug", "Character Slug", "Auto-generated from name if blank"],
                  ["alignment", "Alignment", "Neutral Good"],
                  ["experience_model", "Experience Model", "Milestone"],
                ].map(([key, label, placeholder]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <input
                      type="text"
                      name={key}
                      value={draftString(draftValues, key, create.values[key] || "")}
                      placeholder={placeholder}
                      onChange={(event) => updateValue(key, event.currentTarget.value)}
                    />
                  </label>
                ))}
              </div>
            </section>

            <section className="builder-section">
              <h2>Core Build</h2>
              <div className="builder-field-grid">
                <label className="field">
                  <span>Class</span>
                  <select
                    name="class_slug"
                    value={draftString(draftValues, "class_slug", create.values.class_slug || "")}
                    onChange={(event) => updateValue("class_slug", event.currentTarget.value, true)}
                  >
                    <option value="">Choose a class</option>
                    {selectOptions(create.class_options)}
                  </select>
                </label>
                {create.subclass_options.length || create.requires_subclass ? (
                  <label className="field">
                    <span>Subclass</span>
                    <select
                      name="subclass_slug"
                      value={draftString(draftValues, "subclass_slug", create.values.subclass_slug || "")}
                      onChange={(event) => updateValue("subclass_slug", event.currentTarget.value, true)}
                    >
                      <option value="">{create.requires_subclass ? "Choose a subclass" : "No subclass"}</option>
                      {selectOptions(create.subclass_options)}
                    </select>
                  </label>
                ) : null}
                <label className="field">
                  <span>Species</span>
                  <select
                    name="species_slug"
                    value={draftString(draftValues, "species_slug", create.values.species_slug || "")}
                    onChange={(event) => updateValue("species_slug", event.currentTarget.value, true)}
                  >
                    <option value="">Choose a species</option>
                    {selectOptions(create.species_options)}
                  </select>
                </label>
                <label className="field">
                  <span>Background</span>
                  <select
                    name="background_slug"
                    value={draftString(draftValues, "background_slug", create.values.background_slug || "")}
                    onChange={(event) => updateValue("background_slug", event.currentTarget.value, true)}
                  >
                    <option value="">Choose a background</option>
                    {selectOptions(create.background_options)}
                  </select>
                </label>
              </div>
            </section>

            <section className="builder-section">
              <h2>Ability Scores</h2>
              <div className="builder-ability-grid">
                {[
                  ["str", "Strength"],
                  ["dex", "Dexterity"],
                  ["con", "Constitution"],
                  ["int", "Intelligence"],
                  ["wis", "Wisdom"],
                  ["cha", "Charisma"],
                ].map(([key, label]) => (
                  <label className="field" key={key}>
                    <span>{label}</span>
                    <input
                      type="number"
                      name={key}
                      min={1}
                      max={30}
                      value={draftString(draftValues, key, create.values[key] || "10")}
                      onChange={(event) => updateValue(key, event.currentTarget.value)}
                    />
                  </label>
                ))}
              </div>
            </section>

            {create.choice_sections.map((section) => (
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

            <div className="builder-actions">
              <button type="button" className="ghost-button" onClick={() => refreshContext()}>
                Refresh options
              </button>
              <button type="submit" disabled={!create.builder_ready || createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create character"}
              </button>
            </div>
          </form>
          <CharacterPreviewList preview={create.preview} />
        </div>
      ) : null}

      {isXianxiaCreateContext(create) ? (
        <div className="character-authoring-layout">
          <form className="stack-form character-authoring-form" onSubmit={submitCreate}>
            <section className="builder-section">
              <h2>Identity</h2>
              <div className="builder-field-grid">
                <label className="field">
                  <span>Character Name</span>
                  <input type="text" name="name" value={draftString(draftValues, "name")} onChange={(event) => updateValue("name", event.currentTarget.value)} required />
                </label>
                <label className="field">
                  <span>Character Slug</span>
                  <input type="text" name="character_slug" value={draftString(draftValues, "character_slug")} onChange={(event) => updateValue("character_slug", event.currentTarget.value)} />
                </label>
              </div>
            </section>

            {([
              { title: "Attributes", fields: create.attribute_fields, inputType: "number" },
              { title: "Efforts", fields: create.effort_fields, inputType: "number" },
              { title: "Energies", fields: create.energy_fields, inputType: "number" },
              { title: "Trained Skills", fields: create.trained_skill_fields, inputType: "text" },
            ] as Array<{ title: string; fields: CharacterXianxiaCreateContext["attribute_fields"]; inputType: "number" | "text" }>).map(({ title, fields, inputType }) => (
              <section className="builder-section" key={title}>
                <h2>{title}</h2>
                <div className="builder-field-grid">
                  {fields.map((field) => (
                    <label className="field" key={field.input_name}>
                      <span>{field.label}</span>
                      <input
                        type={inputType}
                        name={field.input_name}
                        min={field.min ?? 0}
                        max={field.max}
                        step={1}
                        value={draftString(draftValues, field.input_name, field.value)}
                        onChange={(event) => updateValue(field.input_name, event.currentTarget.value)}
                        required
                      />
                    </label>
                  ))}
                </div>
              </section>
            ))}

            <section className="builder-section">
              <h2>Starting Martial Arts</h2>
              <div className="builder-field-grid">
                {create.martial_art_fields.map((field) => (
                  <React.Fragment key={field.index}>
                    <label className="field">
                      <span>Martial Art {field.index}</span>
                      <select
                        name={field.art_input_name}
                        value={draftString(draftValues, field.art_input_name, field.selected_slug)}
                        onChange={(event) => updateValue(field.art_input_name, event.currentTarget.value)}
                      >
                        <option value="">Choose Martial Art</option>
                        {selectOptions(create.martial_art_options)}
                      </select>
                    </label>
                    <label className="field">
                      <span>Starting Rank {field.index}</span>
                      <select
                        name={field.rank_input_name}
                        value={draftString(draftValues, field.rank_input_name, field.selected_rank)}
                        onChange={(event) => updateValue(field.rank_input_name, event.currentTarget.value)}
                      >
                        <option value="">Choose Rank</option>
                        {selectOptions(create.martial_art_rank_choices)}
                      </select>
                    </label>
                  </React.Fragment>
                ))}
              </div>
            </section>

            <section className="builder-section">
              <h2>GM Grants</h2>
              <div className="builder-field-grid">
                {[create.manual_armor_field, create.dao_field].map((field) => (
                  <label className="field" key={field.input_name}>
                    <span>{field.input_name === "dao_current" ? "Starting Dao" : "Manual Armor Bonus"}</span>
                    <input
                      type="number"
                      name={field.input_name}
                      min={field.min ?? 0}
                      max={field.max}
                      step={1}
                      value={draftString(draftValues, field.input_name, field.value)}
                      onChange={(event) => updateValue(field.input_name, event.currentTarget.value)}
                    />
                  </label>
                ))}
                {create.generic_technique_options.length ? (
                  <label className="field">
                    <span>GM-Granted Generic Techniques</span>
                    <select
                      name={create.gm_granted_generic_technique_input}
                      multiple
                      size={6}
                      value={draftStringArray(draftValues, create.gm_granted_generic_technique_input)}
                      onChange={(event) =>
                        updateValue(
                          create.gm_granted_generic_technique_input,
                          Array.from(event.currentTarget.selectedOptions).map((option) => option.value),
                        )
                      }
                    >
                      {selectOptions(create.generic_technique_options)}
                    </select>
                  </label>
                ) : null}
              </div>
            </section>

            <div className="builder-actions">
              <button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create character"}
              </button>
            </div>
          </form>
          <aside className="sidebar character-authoring-sidebar">
            <section className="card sidebar-card">
              <h2>Starting Defaults</h2>
              <div className="builder-preview-list">
                {Object.entries(create.defaults).map(([key, value]) => (
                  <div key={key}>
                    <span className="meta">{key.replace(/_/g, " ")}</span>
                    <strong>{stringFromUnknown(value)}</strong>
                  </div>
                ))}
              </div>
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}
