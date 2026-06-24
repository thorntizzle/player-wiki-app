import type { Dispatch, SetStateAction } from "react";
import { useMutation } from "@tanstack/react-query";

import { apiErrorMessage, type CampaignApiClient } from "./api/client";
import type {
  CombatAddNpcPayload,
  CombatCondition,
  CombatPayload,
  CombatResourcesPatchPayload,
  CombatSystemsMonsterSearchResult,
  CombatTurnPatchPayload,
  CombatVitalsPatchPayload,
  CombatantSummary,
} from "./api/types";
import { queryClient } from "./apiClientContext";
import type { CombatView } from "./components/CombatChrome";
import type {
  CombatNpcSeedDraft,
  CombatPlayerSeedDraft,
  CombatStatblockSeedDraft,
  CombatSystemsSeedDraft,
} from "./components/CombatDmControlsPanel";
import { isAuthRequiredFromError as isAuthError } from "./sessionRouteState";

export interface CombatConditionDraft {
  name: string;
  durationText: string;
}

type StatusReporter = (message: string | null) => void;

interface UseCombatMutationsOptions {
  apiClient: CampaignApiClient;
  campaignSlug: string;
  activeCombatView: CombatView;
  selectedCombatantId: number | null;
  selectedCombatant: CombatantSummary | null | undefined;
  playerSeedDraft: CombatPlayerSeedDraft;
  npcSeedDraft: CombatNpcSeedDraft;
  statblockSeedDraft: CombatStatblockSeedDraft;
  systemsSeedDraft: CombatSystemsSeedDraft;
  systemsSearchQuery: string;
  setAuthRequired: (required: boolean) => void;
  setStatusMessage: StatusReporter;
  setErrorMessage: Dispatch<SetStateAction<string | null>>;
  setConditionDraft: Dispatch<SetStateAction<CombatConditionDraft>>;
  setSelectedCombatantId: Dispatch<SetStateAction<number | null>>;
  setConfirmClearTracker: Dispatch<SetStateAction<boolean>>;
  setPlayerSeedDraft: Dispatch<SetStateAction<CombatPlayerSeedDraft>>;
  setNpcSeedDraft: Dispatch<SetStateAction<CombatNpcSeedDraft>>;
  setStatblockSeedDraft: Dispatch<SetStateAction<CombatStatblockSeedDraft>>;
  setSystemsSeedDraft: Dispatch<SetStateAction<CombatSystemsSeedDraft>>;
  setSystemsSearchStatus: Dispatch<SetStateAction<string | null>>;
  setSystemsSearchResults: Dispatch<SetStateAction<CombatSystemsMonsterSearchResult[]>>;
  refetchCombat: () => unknown;
}

export function useCombatMutations({
  apiClient,
  campaignSlug,
  activeCombatView,
  selectedCombatantId,
  selectedCombatant,
  playerSeedDraft,
  npcSeedDraft,
  statblockSeedDraft,
  systemsSeedDraft,
  systemsSearchQuery,
  setAuthRequired,
  setStatusMessage,
  setErrorMessage,
  setConditionDraft,
  setSelectedCombatantId,
  setConfirmClearTracker,
  setPlayerSeedDraft,
  setNpcSeedDraft,
  setStatblockSeedDraft,
  setSystemsSeedDraft,
  setSystemsSearchStatus,
  setSystemsSearchResults,
  refetchCombat,
}: UseCombatMutationsOptions) {
  const replaceCombatPayload = (response: CombatPayload, message: string) => {
    queryClient.setQueryData(["combat", campaignSlug, activeCombatView, selectedCombatantId], response);
    setStatusMessage(message);
    setErrorMessage(null);
    void refetchCombat();
  };

  const handleCombatMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage(null);
    setErrorMessage(apiErrorMessage(error));
  };

  const updateTurnMutation = useMutation({
    mutationFn: (draft: CombatTurnPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantTurn(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Turn order saved."),
    onError: handleCombatMutationError,
  });

  const updateVitalsMutation = useMutation({
    mutationFn: (draft: CombatVitalsPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantVitals(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Vitals saved."),
    onError: handleCombatMutationError,
  });

  const updateResourcesMutation = useMutation({
    mutationFn: (draft: CombatResourcesPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantResources(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Action economy saved."),
    onError: handleCombatMutationError,
  });

  const addConditionMutation = useMutation({
    mutationFn: (draft: CombatConditionDraft) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.addCombatCondition(campaignSlug, selectedCombatant.id, {
        name: draft.name.trim(),
        duration_text: draft.durationText.trim(),
      });
    },
    onSuccess: (response) => {
      setConditionDraft({ name: "", durationText: "" });
      replaceCombatPayload(response, "Condition added.");
    },
    onError: handleCombatMutationError,
  });

  const deleteConditionMutation = useMutation({
    mutationFn: (condition: CombatCondition) =>
      apiClient.deleteCombatCondition(campaignSlug, condition.id, selectedCombatant?.id ?? null),
    onSuccess: (response) => replaceCombatPayload(response, "Condition removed."),
    onError: handleCombatMutationError,
  });

  const setCurrentMutation = useMutation({
    mutationFn: () => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.setCurrentCombatant(campaignSlug, selectedCombatant.id);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Current turn set."),
    onError: handleCombatMutationError,
  });

  const advanceTurnMutation = useMutation({
    mutationFn: () => apiClient.advanceCombatTurn(campaignSlug, selectedCombatant?.id ?? null),
    onSuccess: (response) => replaceCombatPayload(response, "Turn advanced."),
    onError: handleCombatMutationError,
  });

  const clearCombatMutation = useMutation({
    mutationFn: () => apiClient.clearCombat(campaignSlug),
    onSuccess: (response) => {
      setSelectedCombatantId(null);
      setConfirmClearTracker(false);
      replaceCombatPayload(response, "Combat tracker cleared.");
    },
    onError: handleCombatMutationError,
  });

  const deleteCombatantMutation = useMutation({
    mutationFn: () => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.deleteCombatant(campaignSlug, selectedCombatant.id);
    },
    onSuccess: (response) => {
      setSelectedCombatantId(response.selected_combatant_id ?? null);
      replaceCombatPayload(response, "Combatant removed.");
    },
    onError: handleCombatMutationError,
  });

  const addPlayerMutation = useMutation({
    mutationFn: () =>
      apiClient.addCombatPlayer(
        campaignSlug,
        {
          character_slug: playerSeedDraft.characterSlug,
          turn_value: playerSeedDraft.turnValue,
          initiative_priority: playerSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setPlayerSeedDraft({ characterSlug: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "Player character added.");
    },
    onError: handleCombatMutationError,
  });

  const addNpcMutation = useMutation({
    mutationFn: () => {
      const payload: CombatAddNpcPayload = {
        display_name: npcSeedDraft.displayName.trim(),
        turn_value: npcSeedDraft.turnValue,
        initiative_bonus: npcSeedDraft.initiativeBonus,
        dexterity_modifier: npcSeedDraft.dexterityModifier,
        initiative_priority: npcSeedDraft.initiativePriority,
        current_hp: npcSeedDraft.currentHp,
        max_hp: npcSeedDraft.maxHp,
        temp_hp: npcSeedDraft.tempHp,
        movement_total: npcSeedDraft.movementTotal,
      };
      return apiClient.addCombatNpc(campaignSlug, payload, selectedCombatantId);
    },
    onSuccess: (response) => {
      setNpcSeedDraft({
        displayName: "",
        turnValue: "",
        initiativeBonus: "0",
        dexterityModifier: "",
        initiativePriority: "1",
        currentHp: "",
        maxHp: "",
        tempHp: "0",
        movementTotal: "30",
      });
      replaceCombatPayload(response, "NPC added.");
    },
    onError: handleCombatMutationError,
  });

  const addStatblockMutation = useMutation({
    mutationFn: () =>
      apiClient.addCombatStatblock(
        campaignSlug,
        {
          statblock_id: statblockSeedDraft.statblockId,
          display_name: statblockSeedDraft.displayName.trim(),
          turn_value: statblockSeedDraft.turnValue,
          initiative_priority: statblockSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setStatblockSeedDraft({ statblockId: "", displayName: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "DM Content statblock added.");
    },
    onError: handleCombatMutationError,
  });

  const addSystemsMonsterMutation = useMutation({
    mutationFn: (entryKey: string) =>
      apiClient.addCombatSystemsMonster(
        campaignSlug,
        {
          entry_key: entryKey,
          display_name: systemsSeedDraft.displayName.trim(),
          turn_value: systemsSeedDraft.turnValue,
          initiative_priority: systemsSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setSystemsSeedDraft({ entryKey: "", displayName: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "Systems monster added.");
    },
    onError: handleCombatMutationError,
  });

  const searchSystemsMonsters = async () => {
    const query = systemsSearchQuery.trim();
    if (query.length < 2) {
      setSystemsSearchStatus("Type at least 2 letters to search Systems monsters.");
      setSystemsSearchResults([]);
      return;
    }
    setSystemsSearchStatus("Searching Systems monsters ...");
    try {
      const response = await apiClient.searchCombatSystemsMonsters(campaignSlug, query);
      setSystemsSearchResults(response.results);
      setSystemsSearchStatus(response.message);
      setErrorMessage(null);
    } catch (error) {
      handleCombatMutationError(error);
      setSystemsSearchResults([]);
      setSystemsSearchStatus(null);
    }
  };

  return {
    addConditionMutation,
    addNpcMutation,
    addPlayerMutation,
    addStatblockMutation,
    addSystemsMonsterMutation,
    advanceTurnMutation,
    clearCombatMutation,
    deleteCombatantMutation,
    deleteConditionMutation,
    searchSystemsMonsters,
    setCurrentMutation,
    updateResourcesMutation,
    updateTurnMutation,
    updateVitalsMutation,
  };
}
