import { useMutation } from "@tanstack/react-query";
import type { Dispatch, RefObject, SetStateAction } from "react";

import { apiErrorMessage } from "./api/client";
import type {
  CharacterCurrencyPatchPayload,
  CharacterArtificerInfusionsPatchPayload,
  CharacterDetailResponse,
  CharacterEquipmentStatePatchPayload,
  CharacterFeatureStatePatchPayload,
  CharacterInventoryPatchPayload,
  CharacterNotesPatchPayload,
  CharacterPortraitUpsertPayload,
  CharacterRecord,
  CharacterResourcePatchPayload,
  CharacterRestApplyResponse,
  CharacterRestPreviewResponse,
  CharacterSpellSlotsPatchPayload,
  CharacterVitalsPatchPayload,
  CharacterXianxiaDaoUseRecordPayload,
  CharacterXianxiaDaoUseRequestPayload,
  CharacterXianxiaInventoryItemPayload,
} from "./api/types";
import { queryClient, useApiClient } from "./apiClientContext";
import {
  emptyCharacterPortraitDraft,
  emptyCharacterXianxiaDaoUseRequestDraft,
  type CharacterControlsDraft,
  type CharacterPortraitDraft,
  type CharacterXianxiaDaoUseRequestDraft,
} from "./characterPaneDrafts";
import { xianxiaInventoryDraftFromItem, type CharacterXianxiaInventoryDraft } from "./characterPaneUtils";
import { isAuthRequiredFromError as isAuthError } from "./sessionRouteState";

export function useCharacterPaneMutations({
  campaignSlug,
  selectedSlug,
  refetchCharacterList,
  setControlsDraft,
  setErrorMessage,
  setNewXianxiaInventoryDraft,
  setPortraitDraft,
  setRestPreview,
  setStatusMessage,
  setXianxiaDaoRequestDraft,
  portraitFileInputRef,
}: {
  campaignSlug: string;
  selectedSlug: string | null;
  refetchCharacterList: () => unknown;
  setControlsDraft: Dispatch<SetStateAction<CharacterControlsDraft>>;
  setErrorMessage: Dispatch<SetStateAction<string | null>>;
  setNewXianxiaInventoryDraft: Dispatch<SetStateAction<CharacterXianxiaInventoryDraft>>;
  setPortraitDraft: Dispatch<SetStateAction<CharacterPortraitDraft>>;
  setRestPreview: Dispatch<SetStateAction<CharacterRestPreviewResponse["preview"] | null>>;
  setStatusMessage: Dispatch<SetStateAction<string | null>>;
  setXianxiaDaoRequestDraft: Dispatch<SetStateAction<CharacterXianxiaDaoUseRequestDraft>>;
  portraitFileInputRef: RefObject<HTMLInputElement | null>;
}) {
  const { apiClient, setAuthRequired } = useApiClient();

  const handleMutationSuccess = (response: { character: CharacterRecord }, message: string) => {
    if (selectedSlug) {
      const previousDetail = queryClient.getQueryData<CharacterDetailResponse>([
        "character-detail",
        campaignSlug,
        selectedSlug,
      ]);
      queryClient.setQueryData<CharacterDetailResponse>(["character-detail", campaignSlug, selectedSlug], {
        ok: true,
        character: response.character,
        links: previousDetail?.links,
      });
    }
    void refetchCharacterList();
    setStatusMessage(message);
    setErrorMessage(null);
  };

  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage(null);
    setErrorMessage(apiErrorMessage(error));
  };

  const patchVitals = useMutation({
    mutationFn: (payload: CharacterVitalsPatchPayload) =>
      apiClient.patchCharacterVitals(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Vitals saved."),
    onError: handleMutationError,
  });

  const patchResource = useMutation({
    mutationFn: ({ resourceId, payload }: { resourceId: string; payload: CharacterResourcePatchPayload }) =>
      apiClient.patchCharacterResource(campaignSlug, selectedSlug || "", resourceId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Resource saved."),
    onError: handleMutationError,
  });

  const patchSpellSlot = useMutation({
    mutationFn: ({ level, payload }: { level: number; payload: CharacterSpellSlotsPatchPayload }) =>
      apiClient.patchCharacterSpellSlots(campaignSlug, selectedSlug || "", level, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Spell slots saved."),
    onError: handleMutationError,
  });

  const patchInventory = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: CharacterInventoryPatchPayload }) =>
      apiClient.patchCharacterInventory(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory saved."),
    onError: handleMutationError,
  });

  const patchEquipmentState = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: CharacterEquipmentStatePatchPayload }) =>
      apiClient.patchCharacterEquipmentState(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Equipment state saved."),
    onError: handleMutationError,
  });

  const patchFeatureState = useMutation({
    mutationFn: ({ featureKey, payload }: { featureKey: string; payload: CharacterFeatureStatePatchPayload }) =>
      apiClient.patchCharacterFeatureState(campaignSlug, selectedSlug || "", featureKey, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Feature state saved."),
    onError: handleMutationError,
  });

  const patchArtificerInfusions = useMutation({
    mutationFn: (payload: CharacterArtificerInfusionsPatchPayload) =>
      apiClient.patchCharacterArtificerInfusions(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Artificer infusions saved."),
    onError: handleMutationError,
  });

  const patchXianxiaActiveState = useMutation({
    mutationFn: (payload: { expected_revision: number; active_stance_name?: string; active_aura_name?: string }) =>
      apiClient.patchCharacterXianxiaActiveState(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Active Stance and Aura saved."),
    onError: handleMutationError,
  });

  const postXianxiaDaoUseRequest = useMutation({
    mutationFn: (payload: CharacterXianxiaDaoUseRequestPayload) =>
      apiClient.postCharacterXianxiaDaoUseRequest(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      setXianxiaDaoRequestDraft(emptyCharacterXianxiaDaoUseRequestDraft());
      handleMutationSuccess(response, "Dao Immolating use request recorded.");
    },
    onError: handleMutationError,
  });

  const postXianxiaDaoUseRecord = useMutation({
    mutationFn: (payload: CharacterXianxiaDaoUseRecordPayload) =>
      apiClient.postCharacterXianxiaDaoUseRecord(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Dao Immolating one-use spend recorded."),
    onError: handleMutationError,
  });

  const addXianxiaInventoryItem = useMutation({
    mutationFn: (payload: { expected_revision: number; item: CharacterXianxiaInventoryItemPayload }) =>
      apiClient.addCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      setNewXianxiaInventoryDraft(xianxiaInventoryDraftFromItem());
      handleMutationSuccess(response, "Inventory item added.");
    },
    onError: handleMutationError,
  });

  const patchXianxiaInventoryItem = useMutation({
    mutationFn: ({
      itemId,
      payload,
    }: {
      itemId: string;
      payload: { expected_revision: number; item: CharacterXianxiaInventoryItemPayload };
    }) => apiClient.patchCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory item saved."),
    onError: handleMutationError,
  });

  const removeXianxiaInventoryItem = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: { expected_revision: number } }) =>
      apiClient.removeCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory item removed."),
    onError: handleMutationError,
  });

  const patchXianxiaInventoryEquipped = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: { expected_revision: number; is_equipped: boolean } }) =>
      apiClient.patchCharacterXianxiaInventoryEquipped(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Equipment state saved."),
    onError: handleMutationError,
  });

  const patchCurrency = useMutation({
    mutationFn: (payload: CharacterCurrencyPatchPayload) =>
      apiClient.patchCharacterCurrency(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Currency saved."),
    onError: handleMutationError,
  });

  const patchNotes = useMutation({
    mutationFn: (payload: CharacterNotesPatchPayload) =>
      apiClient.patchCharacterNotes(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Notes saved."),
    onError: handleMutationError,
  });

  const upsertPortrait = useMutation({
    mutationFn: (payload: CharacterPortraitUpsertPayload) =>
      apiClient.upsertCharacterPortrait(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      handleMutationSuccess(response, "Portrait saved.");
      setPortraitDraft((current) => ({ ...current, file: null, fileName: "" }));
      if (portraitFileInputRef.current) {
        portraitFileInputRef.current.value = "";
      }
    },
    onError: handleMutationError,
  });

  const deletePortrait = useMutation({
    mutationFn: (payload: { expected_revision: number }) =>
      apiClient.deleteCharacterPortrait(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      handleMutationSuccess(response, "Portrait removed.");
      setPortraitDraft(emptyCharacterPortraitDraft());
      if (portraitFileInputRef.current) {
        portraitFileInputRef.current.value = "";
      }
    },
    onError: handleMutationError,
  });

  const assignCharacterOwner = useMutation({
    mutationFn: (payload: { user_id: number }) =>
      apiClient.assignCharacterOwner(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, response.message || "Assignment saved."),
    onError: handleMutationError,
  });

  const clearCharacterOwner = useMutation({
    mutationFn: () => apiClient.clearCharacterOwner(campaignSlug, selectedSlug || ""),
    onSuccess: (response) => {
      setControlsDraft((current) => ({ ...current, assignedUserId: "" }));
      handleMutationSuccess(response, response.message || "Assignment cleared.");
    },
    onError: handleMutationError,
  });

  const deleteCharacterMutation = useMutation({
    mutationFn: (payload: { confirm_character_slug: string }) =>
      apiClient.deleteCharacter(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      setStatusMessage(response.message || "Character deleted.");
      setErrorMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["characters", campaignSlug] });
      window.location.assign(response.links?.gen2_roster_url || `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters`);
    },
    onError: handleMutationError,
  });

  const previewRest = useMutation({
    mutationFn: (restType: "short" | "long") =>
      apiClient.getCharacterRestPreview(campaignSlug, selectedSlug || "", restType),
    onSuccess: (response) => {
      setRestPreview(response.preview);
      setStatusMessage(null);
      setErrorMessage(null);
    },
    onError: handleMutationError,
  });

  const applyRest = useMutation({
    mutationFn: ({ restType, payload }: { restType: "short" | "long"; payload: { expected_revision: number } }) =>
      apiClient.applyCharacterRest(campaignSlug, selectedSlug || "", restType, payload),
    onSuccess: (response: CharacterRestApplyResponse) => {
      setRestPreview(null);
      handleMutationSuccess(response, "Rest applied.");
    },
    onError: handleMutationError,
  });

  return {
    addXianxiaInventoryItem,
    applyRest,
    assignCharacterOwner,
    clearCharacterOwner,
    deleteCharacterMutation,
    deletePortrait,
    patchCurrency,
    patchEquipmentState,
    patchFeatureState,
    patchArtificerInfusions,
    patchInventory,
    patchNotes,
    patchResource,
    patchSpellSlot,
    patchVitals,
    patchXianxiaActiveState,
    patchXianxiaInventoryEquipped,
    patchXianxiaInventoryItem,
    postXianxiaDaoUseRecord,
    postXianxiaDaoUseRequest,
    previewRest,
    removeXianxiaInventoryItem,
    upsertPortrait,
  };
}
