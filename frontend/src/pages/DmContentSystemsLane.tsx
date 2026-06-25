import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import type { CampaignItemMechanicsReview, CampaignItemPageRow, SystemsSourceRow } from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { ApiErrorNotice, ToastNotice, useToastNotice } from "../components/feedback";
import {
  buildInitialSystemsCustomDraft,
  buildSystemsCustomDraftFromEntry,
  type DmContentSystemsCustomDraftState,
} from "../dmContentUtils";
import {
  useDmContentSystemsMutations,
  type DmContentSystemsOverrideDraftState,
  type DmContentSystemsSourceDraftState,
} from "../dmContentSystemsMutations";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { formatTimestamp } from "../timeFormatting";

const ITEM_MECHANICS_REVIEW_STATUS_CHOICES = [
  { value: "draft", label: "Draft" },
  { value: "approved", label: "Approved" },
  { value: "reference_only", label: "Reference Only" },
  { value: "manual_review", label: "Manual Review" },
];

export function DmContentSystemsLane({ campaignSlug }: { campaignSlug: string }) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [sourceDrafts, setSourceDrafts] = useState<Record<string, DmContentSystemsSourceDraftState>>({});
  const [acknowledgeProprietary, setAcknowledgeProprietary] = useState(false);
  const [overrideDraft, setOverrideDraft] = useState<DmContentSystemsOverrideDraftState>({
    entryKey: "",
    visibilityOverride: "",
    enablementOverride: "",
  });
  const [customCreateDraft, setCustomCreateDraft] = useState<DmContentSystemsCustomDraftState>(() => buildInitialSystemsCustomDraft());
  const [customEditDrafts, setCustomEditDrafts] = useState<Record<string, DmContentSystemsCustomDraftState>>({});
  const [customArchiveConfirm, setCustomArchiveConfirm] = useState<Record<string, boolean>>({});
  const [itemImportReviewStatus, setItemImportReviewStatus] = useState<Record<string, string>>({});
  const [customQuery, setCustomQuery] = useState("");
  const [systemsError, setSystemsError] = useState<string | null>(null);
  const { showToast, toastMessage, toastTone } = useToastNotice();

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
    setItemImportReviewStatus((current) => {
      const next: Record<string, string> = {};
      for (const row of payload.campaign_item_page_rows) {
        next[row.page_ref] = current[row.page_ref] ?? row.item_mechanics?.review_status ?? "draft";
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

  const payload = systemsQuery.data;
  const {
    archiveCustomMutation,
    createCustomMutation,
    importItemMechanicsMutation,
    restoreCustomMutation,
    updateCustomMutation,
    updateOverrideMutation,
    updateSourcesMutation,
  } = useDmContentSystemsMutations({
    apiClient,
    campaignSlug,
    payload,
    sourceDrafts,
    acknowledgeProprietary,
    overrideDraft,
    customCreateDraft,
    customEditDrafts,
    setAuthRequired,
    setSystemsMessage: showToast,
    setSystemsError,
    setAcknowledgeProprietary,
    setOverrideDraft,
    setCustomCreateDraft,
    refetchSystems: () => {
      void systemsQuery.refetch();
    },
  });
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
        entry.linked_published_page_ref,
        entry.item_mechanics?.review_status,
        entry.item_mechanics?.support_state,
        entry.item_mechanics?.modeled_fields?.join(" "),
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
    const isItemEntry = draft.entryType === "item";
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
              <span>URL name</span>
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
        {isItemEntry ? (
          <>
            <div className="builder-field-grid">
              <label htmlFor={`${idPrefix}-item-source-page`} className="field">
                <span>Published item page</span>
                <select
                  id={`${idPrefix}-item-source-page`}
                  value={draft.sourcePageRef}
                  disabled={disabled}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft({ sourcePageRef: event.currentTarget.value })}
                >
                  <option value="">No linked page</option>
                  {(payload?.campaign_item_page_rows ?? []).map((row: CampaignItemPageRow) => (
                    <option key={row.page_ref} value={row.page_ref}>{row.title}</option>
                  ))}
                </select>
              </label>
              <label htmlFor={`${idPrefix}-item-review-status`} className="field">
                <span>Mechanics review</span>
                <select
                  id={`${idPrefix}-item-review-status`}
                  value={draft.itemMechanicsReviewStatus}
                  disabled={disabled}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft({ itemMechanicsReviewStatus: event.currentTarget.value })}
                >
                  {ITEM_MECHANICS_REVIEW_STATUS_CHOICES.map((choice) => (
                    <option key={choice.value} value={choice.value}>{choice.label}</option>
                  ))}
                </select>
              </label>
              <label htmlFor={`${idPrefix}-item-base`} className="field">
                <span>Base weapon/armor</span>
                <input
                  id={`${idPrefix}-item-base`}
                  value={draft.itemBaseItem}
                  disabled={disabled}
                  placeholder="longsword"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemBaseItem: event.currentTarget.value })}
                />
              </label>
              <label htmlFor={`${idPrefix}-item-rarity`} className="field">
                <span>Rarity</span>
                <input
                  id={`${idPrefix}-item-rarity`}
                  value={draft.itemRarity}
                  disabled={disabled}
                  placeholder="rare"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemRarity: event.currentTarget.value })}
                />
              </label>
            </div>
            <div className="builder-field-grid">
              <label htmlFor={`${idPrefix}-item-bonus-weapon`} className="field">
                <span>Weapon +X</span>
                <input
                  id={`${idPrefix}-item-bonus-weapon`}
                  value={draft.itemBonusWeapon}
                  disabled={disabled}
                  inputMode="numeric"
                  placeholder="1"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemBonusWeapon: event.currentTarget.value })}
                />
              </label>
              <label htmlFor={`${idPrefix}-item-bonus-ac`} className="field">
                <span>AC +X</span>
                <input
                  id={`${idPrefix}-item-bonus-ac`}
                  value={draft.itemBonusAc}
                  disabled={disabled}
                  inputMode="numeric"
                  placeholder="1"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemBonusAc: event.currentTarget.value })}
                />
              </label>
              <label htmlFor={`${idPrefix}-item-armor-type`} className="field">
                <span>Armor type</span>
                <input
                  id={`${idPrefix}-item-armor-type`}
                  value={draft.itemArmorType}
                  disabled={disabled}
                  placeholder="LA, MA, HA, S"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemArmorType: event.currentTarget.value })}
                />
              </label>
              <label htmlFor={`${idPrefix}-item-armor-ac`} className="field">
                <span>Armor AC</span>
                <input
                  id={`${idPrefix}-item-armor-ac`}
                  value={draft.itemArmorAc}
                  disabled={disabled}
                  inputMode="numeric"
                  placeholder="12"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemArmorAc: event.currentTarget.value })}
                />
              </label>
            </div>
            <div className="builder-field-grid">
              <label htmlFor={`${idPrefix}-item-damage`} className="field">
                <span>Damage</span>
                <input
                  id={`${idPrefix}-item-damage`}
                  value={draft.itemDamage}
                  disabled={disabled}
                  placeholder="1d8"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemDamage: event.currentTarget.value })}
                />
              </label>
              <label htmlFor={`${idPrefix}-item-versatile`} className="field">
                <span>Versatile</span>
                <input
                  id={`${idPrefix}-item-versatile`}
                  value={draft.itemVersatileDamage}
                  disabled={disabled}
                  placeholder="1d10"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemVersatileDamage: event.currentTarget.value })}
                />
              </label>
              <label htmlFor={`${idPrefix}-item-range`} className="field">
                <span>Range</span>
                <input
                  id={`${idPrefix}-item-range`}
                  value={draft.itemRange}
                  disabled={disabled}
                  placeholder="20/60"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemRange: event.currentTarget.value })}
                />
              </label>
              <label htmlFor={`${idPrefix}-item-properties`} className="field">
                <span>Properties</span>
                <input
                  id={`${idPrefix}-item-properties`}
                  value={draft.itemProperties}
                  disabled={disabled}
                  placeholder="V, Ammunition"
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemProperties: event.currentTarget.value })}
                />
              </label>
            </div>
            <label htmlFor={`${idPrefix}-item-attunement`} className="field">
              <span>Attunement</span>
              <input
                id={`${idPrefix}-item-attunement`}
                value={draft.itemAttunement}
                disabled={disabled}
                placeholder="requires attunement"
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ itemAttunement: event.currentTarget.value })}
              />
            </label>
          </>
        ) : null}
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

  const renderItemMechanicsReview = (review?: CampaignItemMechanicsReview | null) => {
    if (!review) {
      return null;
    }
    return (
      <div className="systems-item-review">
        <div className="badge-list">
          <span className="meta-badge">{review.review_status.replace(/_/g, " ")}</span>
          {review.support_state ? <span className="meta-badge">{review.support_state.replace(/_/g, " ")}</span> : null}
          {review.source_page_ref ? <span className="meta-badge">{review.source_page_ref}</span> : null}
        </div>
        {review.modeled_fields.length ? (
          <p className="meta">Modeled fields: {review.modeled_fields.join(", ")}</p>
        ) : null}
        {review.flags.length ? (
          <ul className="plain-list">
            {review.flags.map((flag, index) => (
              <li className="meta" key={`${flag.code || "flag"}-${index}`}>
                {flag.message || flag.code || "Needs review"}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
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
      <ToastNotice message={toastMessage} tone={toastTone} />

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

      <section className="card" id="systems-campaign-item-mechanics">
        <div className="section-heading">
          <h2>Campaign Item Mechanics</h2>
          <p className="meta">{payload.campaign_item_page_rows.length} published item page{payload.campaign_item_page_rows.length === 1 ? "" : "s"}</p>
        </div>
        {payload.campaign_item_page_rows.length ? (
          <div className="dm-content-list systems-campaign-item-list">
            {payload.campaign_item_page_rows.map((row) => {
              const reviewStatus = itemImportReviewStatus[row.page_ref] ?? row.item_mechanics?.review_status ?? "draft";
              return (
                <article className="dm-content-item" key={row.page_ref}>
                  <div className="dm-content-item__header">
                    <div>
                      <h3>{row.title}</h3>
                      <p className="meta">{row.page_ref}</p>
                      {row.source_ref ? <p className="meta">{row.source_ref}</p> : null}
                    </div>
                    <div className="badge-list">
                      <span className="meta-badge">{row.has_structured_item ? "Structured" : "Page only"}</span>
                      {row.entry_slug ? <span className="meta-badge">{row.entry_slug}</span> : null}
                    </div>
                  </div>
                  {renderItemMechanicsReview(row.item_mechanics)}
                  <div className="builder-field-grid">
                    <label htmlFor={`systems-item-import-${row.page_ref}`} className="field">
                      <span>Review status</span>
                      <select
                        id={`systems-item-import-${row.page_ref}`}
                        value={reviewStatus}
                        disabled={!canManageSystems}
                        onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                          const status = event.currentTarget.value;
                          setItemImportReviewStatus((current) => ({ ...current, [row.page_ref]: status }));
                        }}
                      >
                        {ITEM_MECHANICS_REVIEW_STATUS_CHOICES.map((choice) => (
                          <option key={choice.value} value={choice.value}>{choice.label}</option>
                        ))}
                      </select>
                    </label>
                    <div className="field">
                      <span>Systems row</span>
                      <button
                        type="button"
                        disabled={!canManageSystems || importItemMechanicsMutation.isPending}
                        onClick={() => importItemMechanicsMutation.mutate({
                          pageRef: row.page_ref,
                          reviewStatus,
                          visibility: payload.custom_entry_default_visibility,
                        })}
                      >
                        {importItemMechanicsMutation.isPending
                          ? "Saving..."
                          : row.has_structured_item
                            ? "Refresh item mechanics"
                            : "Import item mechanics"}
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="status status-neutral">No published item pages are available for structured item mechanics.</p>
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
                      <form
                        className="confirmed-action"
                        onSubmit={(event: FormEvent<HTMLFormElement>) => {
                          event.preventDefault();
                          archiveCustomMutation.mutate(entry);
                          setCustomArchiveConfirm((current) => ({ ...current, [entry.slug]: false }));
                        }}
                      >
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={Boolean(customArchiveConfirm[entry.slug])}
                            disabled={!canManageSystems || archiveCustomMutation.isPending}
                            onChange={(event: ChangeEvent<HTMLInputElement>) =>
                              setCustomArchiveConfirm((current) => ({
                                ...current,
                                [entry.slug]: event.currentTarget.checked,
                              }))
                            }
                          />
                          Confirm archive
                        </label>
                        <button
                          type="submit"
                          className="ghost-button"
                          disabled={!canManageSystems || archiveCustomMutation.isPending || !customArchiveConfirm[entry.slug]}
                        >
                          {archiveCustomMutation.isPending ? "Archiving..." : "Archive"}
                        </button>
                      </form>
                    )}
                  </div>
                  <details className="feature-detail">
                    <summary>Review or edit custom entry</summary>
                    {entry.provenance ? <p className="meta">Source/provenance: {entry.provenance}</p> : null}
                    {entry.search_metadata ? <p className="meta">Search metadata: {entry.search_metadata}</p> : null}
                    {entry.linked_published_page_ref ? <p className="meta">Published item page: {entry.linked_published_page_ref}</p> : null}
                    {renderItemMechanicsReview(entry.item_mechanics)}
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
          <p className="meta">Use the admin import form to add or refresh shared DND-5E source data.</p>
        </div>
        {payload.permissions.can_import_shared_systems && payload.supports_dnd5e_import ? (
          <a className="ghost-button" href={`${payload.links.flask_systems_lane_url}#systems-shared-imports`}>
            Open import form
          </a>
        ) : (
          <p className="status status-neutral">
            Shared-source ZIP imports are limited to app admins. Campaign DMs can review import history and manage campaign policy here.
          </p>
        )}
      </section>

      <section className="card" id="systems-import-history">
        <div className="section-heading">
          <h2>Import History</h2>
          <p className="meta">{payload.import_run_count} recent shared-library import{payload.import_run_count === 1 ? "" : "s"}</p>
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
          <p className="status status-neutral">No Systems imports have been recorded yet.</p>
        )}
      </section>
    </div>
  );
}
