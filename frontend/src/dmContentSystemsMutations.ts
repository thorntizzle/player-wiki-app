import type { Dispatch, SetStateAction } from "react";
import { useMutation } from "@tanstack/react-query";

import { apiErrorMessage, type CampaignApiClient } from "./api/client";
import type { CustomSystemsEntry, DmContentSystemsResponse } from "./api/types";
import { isAuthRequiredFromError as isAuthError } from "./sessionRouteState";
import {
  buildCustomSystemsPayload,
  buildInitialSystemsCustomDraft,
  buildSystemsCustomDraftFromEntry,
  type DmContentSystemsCustomDraftState,
} from "./dmContentUtils";

type StatusReporter = (message: string | null) => void;

export interface DmContentSystemsSourceDraftState {
  isEnabled: boolean;
  defaultVisibility: string;
}

export interface DmContentSystemsOverrideDraftState {
  entryKey: string;
  visibilityOverride: string;
  enablementOverride: string;
}

interface UseDmContentSystemsMutationsOptions {
  apiClient: CampaignApiClient;
  campaignSlug: string;
  payload?: DmContentSystemsResponse;
  sourceDrafts: Record<string, DmContentSystemsSourceDraftState>;
  acknowledgeProprietary: boolean;
  overrideDraft: DmContentSystemsOverrideDraftState;
  customCreateDraft: DmContentSystemsCustomDraftState;
  customEditDrafts: Record<string, DmContentSystemsCustomDraftState>;
  setAuthRequired: (required: boolean) => void;
  setSystemsMessage: StatusReporter;
  setSystemsError: Dispatch<SetStateAction<string | null>>;
  setAcknowledgeProprietary: Dispatch<SetStateAction<boolean>>;
  setOverrideDraft: Dispatch<SetStateAction<DmContentSystemsOverrideDraftState>>;
  setCustomCreateDraft: Dispatch<SetStateAction<DmContentSystemsCustomDraftState>>;
  refetchSystems: () => void;
}

export function useDmContentSystemsMutations({
  apiClient,
  campaignSlug,
  payload,
  sourceDrafts,
  acknowledgeProprietary,
  overrideDraft,
  customCreateDraft,
  customEditDrafts,
  setAuthRequired,
  setSystemsMessage,
  setSystemsError,
  setAcknowledgeProprietary,
  setOverrideDraft,
  setCustomCreateDraft,
  refetchSystems,
}: UseDmContentSystemsMutationsOptions) {
  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setSystemsError(apiErrorMessage(error));
    setSystemsMessage(null);
  };

  const updateSourcesMutation = useMutation({
    mutationFn: () => {
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
      refetchSystems();
    },
    onError: handleMutationError,
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
      refetchSystems();
    },
    onError: handleMutationError,
  });

  const createCustomMutation = useMutation({
    mutationFn: () => apiClient.createSystemsCustomEntry(campaignSlug, buildCustomSystemsPayload(customCreateDraft)),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry created: ${response.entry.title}.`);
      setSystemsError(null);
      setCustomCreateDraft(buildInitialSystemsCustomDraft(response.systems));
      refetchSystems();
    },
    onError: handleMutationError,
  });

  const updateCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => {
      const draft = customEditDrafts[entry.slug] ?? buildSystemsCustomDraftFromEntry(entry);
      return apiClient.updateSystemsCustomEntry(campaignSlug, entry.slug, buildCustomSystemsPayload(draft));
    },
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry updated: ${response.entry.title}.`);
      setSystemsError(null);
      refetchSystems();
    },
    onError: handleMutationError,
  });

  const archiveCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => apiClient.archiveSystemsCustomEntry(campaignSlug, entry.slug),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry archived: ${response.entry.title}.`);
      setSystemsError(null);
      refetchSystems();
    },
    onError: handleMutationError,
  });

  const restoreCustomMutation = useMutation({
    mutationFn: (entry: CustomSystemsEntry) => apiClient.restoreSystemsCustomEntry(campaignSlug, entry.slug),
    onSuccess: (response) => {
      setSystemsMessage(`Custom Systems entry restored: ${response.entry.title}.`);
      setSystemsError(null);
      refetchSystems();
    },
    onError: handleMutationError,
  });

  return {
    archiveCustomMutation,
    createCustomMutation,
    restoreCustomMutation,
    updateCustomMutation,
    updateOverrideMutation,
    updateSourcesMutation,
  };
}
