import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { apiErrorMessage } from "../api/client";
import type { CustomSystemsEntry, SystemsSourceRow } from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { ApiErrorNotice } from "../components/feedback";
import {
  buildCustomSystemsPayload,
  buildInitialSystemsCustomDraft,
  buildSystemsCustomDraftFromEntry,
  type DmContentSystemsCustomDraftState,
} from "../dmContentUtils";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { formatTimestamp } from "../timeFormatting";

export function DmContentSystemsLane({ campaignSlug }: { campaignSlug: string }) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [sourceDrafts, setSourceDrafts] = useState<Record<string, { isEnabled: boolean; defaultVisibility: string }>>({});
  const [acknowledgeProprietary, setAcknowledgeProprietary] = useState(false);
  const [overrideDraft, setOverrideDraft] = useState({ entryKey: "", visibilityOverride: "", enablementOverride: "" });
  const [customCreateDraft, setCustomCreateDraft] = useState<DmContentSystemsCustomDraftState>(() => buildInitialSystemsCustomDraft());
  const [customEditDrafts, setCustomEditDrafts] = useState<Record<string, DmContentSystemsCustomDraftState>>({});
  const [customQuery, setCustomQuery] = useState("");
  const [systemsMessage, setSystemsMessage] = useState<string | null>(null);
  const [systemsError, setSystemsError] = useState<string | null>(null);

  const systemsQuery = useQuery({
    queryKey: ["dm-content-systems", campaignSlug],
    queryFn: () => apiClient.getDmContentSystems(campaignSlug),
    enabled: Boolean(campaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(systemsQuery.error)) {
      setAuthRequired(true);
    }
  }, [setAuthRequired, systemsQuery.error]);

  useEffect(() => {
    const payload = systemsQuery.data;
    if (!payload) {
      return;
    }
    setSourceDrafts((current) => {
      const next: Record<string, { isEnabled: boolean; defaultVisibility: string }> = {};
      for (const source of payload.source_rows) {
        next[source.source_id] = current[source.source_id] ?? {
          isEnabled: source.is_enabled,
          defaultVisibility: source.default_visibility,
        };
      }
      return next;
    });
    setCustomEditDrafts((current) => {
      const next: Record<string, DmContentSystemsCustomDraftState> = {};
      for (const source of payload.custom_entry_source_rows) {
        for (const entry of source.entries) {
          next[entry.slug] = current[entry.slug] ?? buildSystemsCustomDraftFromEntry(entry);
        }
      }
      return next;
    });
    setCustomCreateDraft((current) => {
      if (current.title || current.bodyMarkdown || current.provenance || current.searchMetadata) {
        return current;
      }
      return {
        ...current,
        entryType: payload.custom_entry_type_choices.some((choice) => choice.value === current.entryType)
          ? current.entryType
          : payload.custom_entry_type_choices[0]?.value ?? current.entryType,
        visibility: current.visibility || payload.custom_entry_default_visibility,
      };
    });
  }, [systemsQuery.data]);

  const updateSourcesMutation = useMutation({
    mutationFn: () => {
      const payload = systemsQuery.data;
      if (!payload) {
        throw new Error("Systems payload is not loaded.");
      }
      return apiClient.updateSystemsSources(campaignSlug, {
        acknowledge_proprietary: acknowledgeProprietary,
        updates: payload.source_rows.map((source) => {
          const draft = sourceDrafts[source.source_id] ?? {
            isEnabled: source.is_enabled,
            defaultVisibility: source.default_visibility,
          };
          return {
            source_id: source.source_id,
            is_enabled: draft.isEnabled,
            default_visibility: draft.defaultVisibility,
          };
        }),
      });
    },
    onSuccess: () => {
      setSystemsMessage("Systems source policy saved.");
      setSystemsError(null);
      setAcknowledgeProprietary(false);
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const updateOverrideMutation = useMutation({
    mutationFn: () => {
      const entryKey = overrideDraft.entryKey.trim();
      if (!entryKey) {
        throw new Error("Entry key is required.");
      }
      const enablement = overrideDraft.enablementOverride === "enabled"
        ? true
        : overrideDraft.enablementOverride === "disabled"
          ? false
          : null;
      return apiClient.updateSystemsEntryOverride(campaignSlug, entryKey, {
        visibility_override: overrideDraft.visibilityOverride || null,
        is_enabled_override: enablement,
      });
    },
    onSuccess: () => {
      setSystemsMessage("Systems entry override saved.");
      setSystemsError(null);
      setOverrideDraft({ entryKey: "", visibilityOverride: "", enablementOverride: "" });
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const createCustomMutation = useMutation({
    mutationFn: () => apiClient.createSystemsCustomEntry(campaignSlug, buildCustomSystemsPayload(customCreateDraft)),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry created: ${response.entry.title}.`);
      setSystemsError(null);
      setCustomCreateDraft(buildInitialSystemsCustomDraft(response.systems));
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const updateCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => {
      const draft = customEditDrafts[entry.slug] ?? buildSystemsCustomDraftFromEntry(entry);
      return apiClient.updateSystemsCustomEntry(campaignSlug, entry.slug, buildCustomSystemsPayload(draft));
    },
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry updated: ${response.entry.title}.`);
      setSystemsError(null);
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const archiveCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => apiClient.archiveSystemsCustomEntry(campaignSlug, entry.slug),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry archived: ${response.entry.title}.`);
      setSystemsError(null);
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const restoreCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => apiClient.restoreSystemsCustomEntry(campaignSlug, entry.slug),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry restored: ${response.entry.title}.`);
      setSystemsError(null);
      void systemsQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSystemsError(apiErrorMessage(error));
      setSystemsMessage(null);
    },
  });

  const payload = systemsQuery.data;
  const pageError = getApiErrorMessage(systemsQuery.error);
  const canManageSystems = Boolean(payload?.permissions.can_manage_systems);
  const allCustomEntries = useMemo(() => {
    const entries = (payload?.custom_entry_source_rows ?? []).flatMap((source) => source.entries);
    const query = customQuery.trim().toLowerCase();
    if (!query) {
      return entries;
    }
    return entries.filter((entry) => (
      [
        entry.title,
        entry.entry_key,
        entry.entry_type_label,
        entry.source_id,
        entry.visibility_label,
        entry.status_label,
        entry.provenance,
        entry.search_metadata,
        entry.body_markdown,
      ].join(" ").toLowerCase().includes(query)
    ));
  }, [customQuery, payload?.custom_entry_source_rows]);

  const renderCustomFields = ({
    idPrefix,
    draft,
    setDraft,
    includeSlug,
    disabled,
  }: {
    idPrefix: string;
    draft: DmContentSystemsCustomDraftState;
    setDraft: (next: DmContentSystemsCustomDraftState) => void;
    includeSlug: boolean;
    disabled: boolean;
  }) => {
    const updateDraft = (updates: Partial<DmContentSystemsCustomDraftState>) => setDraft({ ...draft, ...updates });
    return (
      <>
        <div className="builder-field-grid">
          <label htmlFor={`${idPrefix}-title`} className="field">
            <span>Title</span>
            <input
              id={`${idPrefix}-title`}
              value={draft.title}
              disabled={disabled}
              maxLength={200}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ title: event.currentTarget.value })}
            />
          </label>
          {includeSlug ? (
            <label htmlFor={`${idPrefix}-slug`} className="field">
              <span>URL slug</span>
              <input
                id={`${idPrefix}-slug`}
                value={draft.slugLeaf}
                disabled={disabled}
                maxLength={120}
                placeholder="harbor-spark"
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ slugLeaf: event.currentTarget.value })}
              />
            </label>
          ) : null}
          <label htmlFor={`${idPrefix}-type`} className="field">
            <span>Entry type</span>
            <select
              id={`${idPrefix}-type`}
              value={draft.entryType}
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft({ entryType: event.currentTarget.value })}
            >
              {(payload?.custom_entry_type_choices ?? [{ value: "rule", label: "Rule" }]).map((choice) => (
                <option key={choice.value} value={choice.value}>{choice.label}</option>
              ))}
            </select>
          </label>
          <label htmlFor={`${idPrefix}-visibility`} className="field">
            <span>Visibility</span>
            <select
              id={`${idPrefix}-visibility`}
              value={draft.visibility}
              disabled={disabled}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft({ visibility: event.currentTarget.value })}
            >
              {(payload?.custom_entry_visibility_choices ?? []).map((choice) => (
                <option key={choice.value} value={choice.value}>{choice.label}</option>
              ))}
            </select>
          </label>
        </div>
        <label htmlFor={`${idPrefix}-provenance`} className="field">
          <span>Source/provenance</span>
          <input
            id={`${idPrefix}-provenance`}
            value={draft.provenance}
            disabled={disabled}
            maxLength={500}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ provenance: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-search`} className="field">
          <span>Searchable metadata</span>
          <textarea
            id={`${idPrefix}-search`}
            rows={3}
            value={draft.searchMetadata}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ searchMetadata: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-body`} className="field">
          <span>Rendered body</span>
          <textarea
            id={`${idPrefix}-body`}
            rows={10}
            value={draft.bodyMarkdown}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ bodyMarkdown: event.currentTarget.value })}
          />
        </label>
      </>
    );
  };

  if (systemsQuery.isLoading) {
    return <p className="status status-neutral">Loading Systems management ...</p>;
  }

  if (pageError) {
    return (
      <ApiErrorNotice
        isLoading={systemsQuery.isLoading}
        message={pageError}
        onAuth={() => setAuthRequired(true)}
      />
    );
  }

  if (!payload) {
    return <p className="status status-error">Systems management could not be loaded.</p>;
  }

  return (
    <div className="dm-content-systems-lane">
      {systemsError ? <p className="status status-error">{systemsError}</p> : null}
      {systemsMessage ? <p className="status status-neutral">{systemsMessage}</p> : null}

      <section className="card" id="systems-source-enablement">
        <div className="section-heading">
          <div>
            <h2>Source Enablement</h2>
            <p className="meta">Systems Policy</p>
            <p className="meta">Library: {payload.systems_library || "Not configured"}</p>
            <p className="meta">Systems scope visibility: {payload.systems_scope_visibility_label}</p>
          </div>
        </div>
        {payload.has_proprietary_sources ? (
          <p className="meta">
            Proprietary-source acknowledgement: {payload.policy.proprietary_acknowledged ? "recorded" : "not yet recorded in the systems policy"}
          </p>
        ) : null}
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            updateSourcesMutation.mutate();
          }}
        >
          {payload.source_rows.map((source: SystemsSourceRow) => {
            const draft = sourceDrafts[source.source_id] ?? {
              isEnabled: source.is_enabled,
              defaultVisibility: source.default_visibility,
            };
            return (
              <div className="field" key={source.source_id}>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={draft.isEnabled}
                    disabled={!canManageSystems}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      const checked = event.currentTarget.checked;
                      setSourceDrafts((current) => ({
                        ...current,
                        [source.source_id]: {
                          ...(current[source.source_id] ?? draft),
                          isEnabled: checked,
                        },
                      }));
                    }}
                  />
                  {source.title} ({source.source_id})
                </label>
                <p className="meta">{source.license_class_label}</p>
                <p className="meta">{source.entry_count} imported entr{source.entry_count === 1 ? "y" : "ies"}</p>
                <label htmlFor={`systems-source-${source.source_id}-visibility`} className="field">
                  <span>Default visibility</span>
                  <select
                    id={`systems-source-${source.source_id}-visibility`}
                    value={draft.defaultVisibility}
                    disabled={!canManageSystems}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                      const visibility = event.currentTarget.value;
                      setSourceDrafts((current) => ({
                        ...current,
                        [source.source_id]: {
                          ...(current[source.source_id] ?? draft),
                          defaultVisibility: visibility,
                        },
                      }));
                    }}
                  >
                    {(source.choices ?? []).map((choice) => (
                      <option key={choice.value} value={choice.value} disabled={choice.disabled}>
                        {choice.label}{choice.disabled ? " (not allowed)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                {!source.public_visibility_allowed ? (
                  <p className="meta">This source is restricted from public visibility by policy.</p>
                ) : null}
              </div>
            );
          })}
          {payload.has_proprietary_sources && !payload.policy.proprietary_acknowledged ? (
            <label className="field">
              <span>Proprietary-source acknowledgement</span>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={acknowledgeProprietary}
                  disabled={!canManageSystems}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setAcknowledgeProprietary(event.currentTarget.checked)}
                />
                I understand proprietary systems sources are for private campaign use only and must not be made public or redistributed.
              </label>
            </label>
          ) : null}
          <button type="submit" disabled={!canManageSystems || updateSourcesMutation.isPending}>
            {updateSourcesMutation.isPending ? "Saving..." : "Save systems sources"}
          </button>
        </form>
      </section>

      <section className="card" id="systems-shared-core-permission">
        <div className="section-heading">
          <div>
            <h2>Shared/Core Editing</h2>
            <p className="meta">
              Campaign DM editing is {payload.policy.allow_dm_shared_core_entry_edits ? "enabled" : "disabled"} for shared-library Systems entries.
            </p>
          </div>
        </div>
        <p className="meta">
          When enabled by an app admin, DMs for this campaign can use the same shared/core editor as app admins.
          This changes the shared library row itself, not only this campaign's override.
        </p>
        {payload.permissions.can_manage_shared_core_entry_edit_permission ? (
          <a className="ghost-button" href={`${payload.links.flask_systems_control_url}#systems-shared-core-permission`}>
            Open shared/core permission form
          </a>
        ) : (
          <p className="meta">Only app admins can change whether campaign DMs may edit shared/core Systems entries.</p>
        )}
      </section>

      <section className="card" id="systems-entry-overrides">
        <div className="section-heading">
          <h2>Entry Overrides</h2>
          <p className="meta">{payload.entry_override_count} saved override{payload.entry_override_count === 1 ? "" : "s"}</p>
        </div>
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            updateOverrideMutation.mutate();
          }}
        >
          <label htmlFor="systems-entry-override-key" className="field">
            <span>Entry key</span>
            <input
              id="systems-entry-override-key"
              value={overrideDraft.entryKey}
              placeholder="dnd-5e|spell|phb|fireball"
              disabled={!canManageSystems}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setOverrideDraft({ ...overrideDraft, entryKey: event.currentTarget.value })}
            />
          </label>
          <label htmlFor="systems-entry-override-visibility" className="field">
            <span>Visibility override</span>
            <select
              id="systems-entry-override-visibility"
              value={overrideDraft.visibilityOverride}
              disabled={!canManageSystems}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => setOverrideDraft({ ...overrideDraft, visibilityOverride: event.currentTarget.value })}
            >
              <option value="">Inherit source default</option>
              {payload.custom_entry_visibility_choices.map((choice) => (
                <option key={choice.value} value={choice.value}>{choice.label}</option>
              ))}
            </select>
          </label>
          <label htmlFor="systems-entry-override-enabled" className="field">
            <span>Enablement override</span>
            <select
              id="systems-entry-override-enabled"
              value={overrideDraft.enablementOverride}
              disabled={!canManageSystems}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => setOverrideDraft({ ...overrideDraft, enablementOverride: event.currentTarget.value })}
            >
              <option value="">Inherit source enablement</option>
              <option value="enabled">Enabled</option>
              <option value="disabled">Disabled</option>
            </select>
          </label>
          <button type="submit" disabled={!canManageSystems || updateOverrideMutation.isPending}>
            {updateOverrideMutation.isPending ? "Saving..." : "Save entry override"}
          </button>
        </form>
        {payload.entry_override_rows.length ? (
          <div className="dm-content-list systems-override-list">
            {payload.entry_override_rows.map((override) => (
              <article className="dm-content-item" key={override.entry_key}>
                <div className="dm-content-item__header">
                  <div>
                    <h3>{override.entry_href ? <a href={override.entry_href}>{override.entry_title}</a> : override.entry_title}</h3>
                    <p className="meta">{override.entry_key}</p>
                    {override.source_label ? (
                      <p className="meta">{override.source_label}{override.entry_type_label ? ` | ${override.entry_type_label}` : ""}</p>
                    ) : null}
                  </div>
                  <div className="badge-list">
                    <span className="meta-badge">{override.visibility_label}</span>
                    <span className="meta-badge">{override.enablement_label}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="status status-neutral">No campaign-specific Systems entry overrides have been saved yet.</p>
        )}
      </section>

      <section className="card" id="systems-custom-entries">
        <div className="section-heading">
          <h2>Custom Entries</h2>
          <p className="meta">{payload.custom_entry_count} custom campaign entr{payload.custom_entry_count === 1 ? "y" : "ies"}</p>
        </div>
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            createCustomMutation.mutate();
          }}
        >
          {renderCustomFields({
            idPrefix: "systems-custom-create",
            draft: customCreateDraft,
            setDraft: setCustomCreateDraft,
            includeSlug: true,
            disabled: !canManageSystems,
          })}
          <button type="submit" disabled={!canManageSystems || createCustomMutation.isPending}>
            {createCustomMutation.isPending ? "Saving..." : "Create custom entry"}
          </button>
        </form>

        <form className="search-form" onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}>
          <label htmlFor="systems-custom-search">Search custom entries</label>
          <input
            id="systems-custom-search"
            type="search"
            value={customQuery}
            placeholder="Title, type, status, source, body"
            onChange={(event: ChangeEvent<HTMLInputElement>) => setCustomQuery(event.currentTarget.value)}
          />
        </form>

        {allCustomEntries.length ? (
          <div className="dm-content-list systems-custom-list">
            {allCustomEntries.map((entry) => {
              const draft = customEditDrafts[entry.slug] ?? buildSystemsCustomDraftFromEntry(entry);
              return (
                <article className="dm-content-item" key={entry.entry_key}>
                  <div className="dm-content-item__header">
                    <div>
                      <h3>{entry.title}</h3>
                      <p className="meta">{entry.source_id} | {entry.visibility_label} | {entry.status_label}</p>
                    </div>
                    <div className="badge-list">
                      <span className="meta-badge">{entry.entry_type_label}</span>
                    </div>
                  </div>
                  <div className="dm-content-item__actions">
                    {entry.href ? (
                      <a className="ghost-button" href={entry.href}>
                        Open entry
                      </a>
                    ) : null}
                    {entry.is_archived ? (
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={!canManageSystems || restoreCustomMutation.isPending}
                        onClick={() => restoreCustomMutation.mutate(entry)}
                      >
                        {restoreCustomMutation.isPending ? "Restoring..." : "Restore"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={!canManageSystems || archiveCustomMutation.isPending}
                        onClick={() => archiveCustomMutation.mutate(entry)}
                      >
                        {archiveCustomMutation.isPending ? "Archiving..." : "Archive"}
                      </button>
                    )}
                  </div>
                  <details className="feature-detail">
                    <summary>Review or edit custom entry</summary>
                    {entry.provenance ? <p className="meta">Source/provenance: {entry.provenance}</p> : null}
                    {entry.search_metadata ? <p className="meta">Search metadata: {entry.search_metadata}</p> : null}
                    {entry.body_markdown ? <pre className="dm-content-preview dm-content-preview--compact">{entry.body_markdown}</pre> : null}
                    <form
                      className="stack-form"
                      onSubmit={(event: FormEvent<HTMLFormElement>) => {
                        event.preventDefault();
                        updateCustomMutation.mutate(entry);
                      }}
                    >
                      {renderCustomFields({
                        idPrefix: `systems-custom-edit-${entry.id}`,
                        draft,
                        setDraft: (next) => setCustomEditDrafts((current) => ({ ...current, [entry.slug]: next })),
                        includeSlug: false,
                        disabled: !canManageSystems,
                      })}
                      <div className="badge-list">
                        <button type="submit" disabled={!canManageSystems || updateCustomMutation.isPending}>
                          {updateCustomMutation.isPending ? "Saving..." : "Update custom entry"}
                        </button>
                      </div>
                    </form>
                  </details>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="status status-neutral">
            {customQuery ? "No custom Systems entries matched that search." : "No custom campaign Systems entries have been authored yet."}
          </p>
        )}
      </section>

      <section className="card" id="systems-shared-imports">
        <div className="section-heading">
          <h2>Shared Source Imports</h2>
          <p className="meta">DND-5E ZIP import remains on the permission-gated Flask form for this slice.</p>
        </div>
        {payload.permissions.can_import_shared_systems && payload.supports_dnd5e_import ? (
          <a className="ghost-button" href={`${payload.links.flask_systems_lane_url}#systems-shared-imports`}>
            Open admin import form
          </a>
        ) : (
          <p className="status status-neutral">
            Shared-source ZIP imports are limited to app admins. Campaign DMs can review import runs and manage campaign policy here.
          </p>
        )}
      </section>

      <section className="card" id="systems-import-history">
        <div className="section-heading">
          <h2>Import-Run History</h2>
          <p className="meta">{payload.import_run_count} recent shared-library run{payload.import_run_count === 1 ? "" : "s"}</p>
        </div>
        {payload.import_run_rows.length ? (
          <div className="dm-content-list systems-import-history">
            {payload.import_run_rows.map((run) => (
              <article className="dm-content-item" key={run.id}>
                <div className="dm-content-item__header">
                  <div>
                    <h3>{run.source_id} import #{run.id}</h3>
                    <p className="meta">Started {formatTimestamp(run.started_at)}{run.completed_at ? ` | Completed ${formatTimestamp(run.completed_at)}` : ""}</p>
                    {run.import_version ? <p className="meta">Import version: {run.import_version}</p> : null}
                    {run.type_summary.length ? (
                      <p className="meta">{run.type_summary.map((item) => `${item.entry_type_label}: ${item.count}`).join(", ")}</p>
                    ) : null}
                    {run.error ? <p className="meta">Error: {run.error}</p> : null}
                  </div>
                  <div className="badge-list">
                    <span className="meta-badge">{run.status}</span>
                    {run.imported_count !== null ? <span className="meta-badge">{run.imported_count} entries</span> : null}
                    {run.source_file_count !== null ? <span className="meta-badge">{run.source_file_count} files</span> : null}
                  </div>
                </div>
                {run.source_files.length ? (
                  <details className="feature-detail">
                    <summary>Review imported files and entry counts</summary>
                    <ul className="plain-list">
                      {run.source_files.map((sourceFile) => <li className="meta" key={sourceFile}>{sourceFile}</li>)}
                    </ul>
                  </details>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="status status-neutral">No Systems import runs have been recorded yet.</p>
        )}
      </section>
    </div>
  );
}
