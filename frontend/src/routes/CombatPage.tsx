import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiErrorMessage } from "../api/client";
import type {
  CombatSystemsMonsterSearchResult,
  CombatPayload,
  CombatCondition,
  CombatAddNpcPayload,
  CombatTurnPatchPayload,
  CombatVitalsPatchPayload,
  CombatResourcesPatchPayload,
  CombatantSummary,
} from "../api/types";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { queryClient, useApiClient } from "../apiClientContext";
import { getApiErrorMessage } from "../apiErrors";
import { ApiErrorNotice } from "../components/feedback";
import { readNumber } from "../characterValueUtils";
import { CombatDmStatusPanel } from "../components/CombatDmStatusPanel";
import { CombatPlayerWorkspace } from "../components/CombatPlayerWorkspace";
import { resolveCombatLivePayload } from "../combatLiveUtils";
import {
  CombatantCarousel,
  CombatSummaryBand,
  CombatViewSwitch,
  type CombatView,
} from "../components/CombatChrome";
import {
  CombatDmControlsPanel,
  type CombatAddMode,
  type CombatNpcSeedDraft,
  type CombatPlayerSeedDraft,
  type CombatStatblockSeedDraft,
  type CombatSystemsSeedDraft,
} from "../components/CombatDmControlsPanel";

interface CombatVitalsDraft {
  currentHp: string;
  maxHp: string;
  tempHp: string;
  movementTotal: string;
}

interface CombatResourcesDraft {
  movementRemaining: string;
  hasAction: boolean;
  hasBonusAction: boolean;
  hasReaction: boolean;
}

interface CombatTurnDraft {
  turnValue: string;
  initiativePriority: string;
}

interface CombatConditionDraft {
  name: string;
  durationText: string;
}

export function CombatPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/combat",
  });
  const location = useLocation();
  const navigate = useNavigate();
  const campaignSlug = params.campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const readSearchView = (search: string): CombatView => {
    const requested = new URLSearchParams(search).get("view");
    return requested === "status" || requested === "controls" ? requested : "player";
  };
  const readSearchCombatantId = (search: string): number | null => {
    const parsed = Number(new URLSearchParams(search).get("combatant") || "");
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  };
  const [selectedCombatantId, setSelectedCombatantId] = useState<number | null>(() => {
    return readSearchCombatantId(window.location.search);
  });
  const [activeCombatView, setActiveCombatView] = useState<CombatView>(() => readSearchView(window.location.search));
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [vitalsDraft, setVitalsDraft] = useState<CombatVitalsDraft>({
    currentHp: "",
    maxHp: "",
    tempHp: "",
    movementTotal: "",
  });
  const [resourcesDraft, setResourcesDraft] = useState<CombatResourcesDraft>({
    movementRemaining: "",
    hasAction: false,
    hasBonusAction: false,
    hasReaction: false,
  });
  const [turnDraft, setTurnDraft] = useState<CombatTurnDraft>({ turnValue: "", initiativePriority: "1" });
  const [conditionDraft, setConditionDraft] = useState<CombatConditionDraft>({ name: "", durationText: "" });
  const [playerSeedDraft, setPlayerSeedDraft] = useState<CombatPlayerSeedDraft>({
    characterSlug: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [npcSeedDraft, setNpcSeedDraft] = useState<CombatNpcSeedDraft>({
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
  const [statblockSeedDraft, setStatblockSeedDraft] = useState<CombatStatblockSeedDraft>({
    statblockId: "",
    displayName: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [systemsSeedDraft, setSystemsSeedDraft] = useState<CombatSystemsSeedDraft>({
    entryKey: "",
    displayName: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [combatAddMode, setCombatAddMode] = useState<CombatAddMode>("player");
  const [systemsSearchQuery, setSystemsSearchQuery] = useState("");
  const [systemsSearchStatus, setSystemsSearchStatus] = useState<string | null>(null);
  const [systemsSearchResults, setSystemsSearchResults] = useState<CombatSystemsMonsterSearchResult[]>([]);
  const [confirmClearTracker, setConfirmClearTracker] = useState(false);

  useEffect(() => {
    const currentSearch = window.location.search;
    setSelectedCombatantId(readSearchCombatantId(currentSearch));
    setActiveCombatView(readSearchView(currentSearch));
  }, [location.href]);

  const combatQuery = useQuery({
    queryKey: ["combat", campaignSlug, activeCombatView, selectedCombatantId],
    queryFn: async () => {
      const previous = queryClient.getQueryData<CombatPayload>([
        "combat",
        campaignSlug,
        activeCombatView,
        selectedCombatantId,
      ]);
      if (!previous) {
        return apiClient.getCombat(campaignSlug, selectedCombatantId);
      }
      const liveResponse = await apiClient.getCombatLiveState(campaignSlug, {
        liveRevision: previous.live_revision,
        liveViewToken: previous.live_view_token,
        combatantId: selectedCombatantId,
      });
      const resolved = resolveCombatLivePayload(previous, liveResponse);
      return resolved ?? apiClient.getCombat(campaignSlug, selectedCombatantId);
    },
    enabled: Boolean(campaignSlug),
    placeholderData: (previousData) => previousData,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && !data.combat_system_supported) {
        return false;
      }
      return data?.poll_settings?.active_interval_ms ?? 3000;
    },
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(combatQuery.error)) {
      setAuthRequired(true);
    }
  }, [combatQuery.error, setAuthRequired]);

  const payload = combatQuery.data;
  const tracker = payload?.tracker;
  const focusedCombatantFromTracker =
    selectedCombatantId && tracker?.combatants
      ? tracker.combatants.find((combatant) => combatant.id === selectedCombatantId) ?? null
      : null;
  const selectedCombatant =
    focusedCombatantFromTracker && payload?.selected_combatant?.id !== selectedCombatantId
      ? focusedCombatantFromTracker
      : payload?.selected_combatant ?? focusedCombatantFromTracker;
  const selectedCombatantMeta = selectedCombatant
    ? selectedCombatant.subtitle || selectedCombatant.source_label || selectedCombatant.type_label
    : "";
  const selectedPlayerCharacter = payload?.selected_player_character ?? null;
  const selectedCharacterSlug = selectedPlayerCharacter?.character_slug || null;
  const selectedCombatantKicker =
    selectedCombatant?.character_slug && selectedCombatant.character_slug === selectedCharacterSlug
      ? "Combat workspace"
      : "Combat snapshot";
  const canManageCombat = Boolean(payload?.permissions.can_manage_combat);
  const canAccessDmContent = Boolean(payload?.permissions.can_access_dm_content);
  const canAccessSystems = Boolean(payload?.permissions.can_access_systems);
  const effectiveCombatView: CombatView = canManageCombat
    ? activeCombatView === "controls"
      ? "controls"
      : "status"
    : "player";
  const paneError = getApiErrorMessage(combatQuery.error);
  const availableCharacters = payload?.available_character_choices ?? [];
  const availableStatblocks = payload?.available_statblock_choices ?? [];
  const conditionOptions = payload?.combat_condition_options ?? [];
  const encodedCampaignSlug = encodeURIComponent(campaignSlug);

  useEffect(() => {
    if (!canAccessSystems && combatAddMode === "systems") {
      setCombatAddMode("player");
    } else if (!canAccessDmContent && combatAddMode === "dm-content") {
      setCombatAddMode("player");
    }
  }, [canAccessSystems, canAccessDmContent, combatAddMode]);

  const setCombatUrl = (view: CombatView, combatantId: number | null) => {
    const params = new URLSearchParams();
    if (view !== "player") {
      params.set("view", view);
    }
    if (combatantId) {
      params.set("combatant", String(combatantId));
    }
    const query = params.toString();
    const nextPath = `/campaigns/${encodedCampaignSlug}/combat${query ? `?${query}` : ""}`;
    void navigate({ to: nextPath as never });
  };

  const syncCombatantDrafts = (combatant: CombatantSummary) => {
    setVitalsDraft({
      currentHp: String(readNumber(combatant.current_hp)),
      maxHp: String(readNumber(combatant.max_hp)),
      tempHp: String(readNumber(combatant.temp_hp)),
      movementTotal: String(readNumber(combatant.movement_total)),
    });
    setResourcesDraft({
      movementRemaining: String(readNumber(combatant.movement_remaining)),
      hasAction: Boolean(combatant.has_action),
      hasBonusAction: Boolean(combatant.has_bonus_action),
      hasReaction: Boolean(combatant.has_reaction),
    });
    setTurnDraft({
      turnValue: String(readNumber(combatant.turn_value)),
      initiativePriority: String(readNumber(combatant.initiative_priority, 1)),
    });
    setConditionDraft({ name: "", durationText: "" });
  };

  useEffect(() => {
    if (!payload?.permissions.can_manage_combat) {
      return;
    }
    if (activeCombatView === "player") {
      setActiveCombatView("status");
      setCombatUrl("status", selectedCombatantId);
    }
  }, [payload?.permissions.can_manage_combat]);

  useEffect(() => {
    if (!selectedCombatant) {
      return;
    }
    syncCombatantDrafts(selectedCombatant);
  }, [selectedCombatant?.id]);

  const selectCombatant = (combatantId: number) => {
    const focusedCombatant = tracker?.combatants.find((combatant) => combatant.id === combatantId);
    if (focusedCombatant) {
      syncCombatantDrafts(focusedCombatant);
    }
    setSelectedCombatantId(combatantId);
    setCombatUrl(effectiveCombatView, combatantId);
  };

  const selectCombatView = (view: CombatView) => {
    setActiveCombatView(view);
    setCombatUrl(view, selectedCombatantId);
  };

  const selectCharacterTarget = (characterSlug: string) => {
    const target = payload?.player_character_targets.find((item) => item.character_slug === characterSlug);
    if (target?.combatant_id) {
      selectCombatant(target.combatant_id);
    }
  };

  const replaceCombatPayload = (response: CombatPayload, message: string) => {
    queryClient.setQueryData(["combat", campaignSlug, activeCombatView, selectedCombatantId], response);
    setStatusMessage(message);
    setErrorMessage(null);
    void combatQuery.refetch();
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

  const renderDmControls = () => (
    <CombatDmControlsPanel
      canManageCombat={canManageCombat}
      canAccessSystems={canAccessSystems}
      canAccessDmContent={canAccessDmContent}
      combatAddMode={combatAddMode}
      availableCharacters={availableCharacters}
      availableStatblocks={availableStatblocks}
      playerSeedDraft={playerSeedDraft}
      npcSeedDraft={npcSeedDraft}
      statblockSeedDraft={statblockSeedDraft}
      systemsSeedDraft={systemsSeedDraft}
      systemsSearchQuery={systemsSearchQuery}
      systemsSearchStatus={systemsSearchStatus}
      systemsSearchResults={systemsSearchResults}
      confirmClearTracker={confirmClearTracker}
      isAdvancingTurn={advanceTurnMutation.isPending}
      isAddingPlayer={addPlayerMutation.isPending}
      isAddingNpc={addNpcMutation.isPending}
      isAddingStatblock={addStatblockMutation.isPending}
      isAddingSystemsMonster={addSystemsMonsterMutation.isPending}
      isClearingCombat={clearCombatMutation.isPending}
      onCombatAddModeChange={setCombatAddMode}
      onPlayerSeedDraftChange={(updates) => setPlayerSeedDraft((current) => ({ ...current, ...updates }))}
      onNpcSeedDraftChange={(updates) => setNpcSeedDraft((current) => ({ ...current, ...updates }))}
      onStatblockSeedDraftChange={(updates) => setStatblockSeedDraft((current) => ({ ...current, ...updates }))}
      onSystemsSeedDraftChange={(updates) => setSystemsSeedDraft((current) => ({ ...current, ...updates }))}
      onSystemsSearchQueryChange={setSystemsSearchQuery}
      onConfirmClearTrackerChange={setConfirmClearTracker}
      onAdvanceTurn={() => advanceTurnMutation.mutate()}
      onAddPlayer={() => addPlayerMutation.mutate()}
      onAddNpc={() => addNpcMutation.mutate()}
      onAddStatblock={() => addStatblockMutation.mutate()}
      onAddSystemsMonster={(entryKey) => addSystemsMonsterMutation.mutate(entryKey)}
      onSearchSystemsMonsters={searchSystemsMonsters}
      onClearCombat={() => clearCombatMutation.mutate()}
    />
  );

  return (
    <>
      <section className="hero compact combat-hero">
        <p className="eyebrow">
          {effectiveCombatView === "status"
            ? "DM status"
            : effectiveCombatView === "controls"
              ? "Encounter controls"
              : "Combat tracker"}
        </p>
        <h1>
          {effectiveCombatView === "status"
            ? "DM status"
            : effectiveCombatView === "controls"
              ? "Encounter controls"
              : "Combat"}
        </h1>
        <p className="lede">
          {effectiveCombatView === "status" || effectiveCombatView === "controls"
            ? "Encounter setup, seeding, cleanup, and authority changes."
            : selectedPlayerCharacter
              ? "Keep your tracked character open as your in-combat workspace."
              : "Live encounter tracker."}
        </p>
        {canManageCombat && effectiveCombatView !== "player" ? (
          <CombatViewSwitch effectiveCombatView={effectiveCombatView} onSelect={selectCombatView} />
        ) : null}
      </section>

      <ApiErrorNotice
        isLoading={combatQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}

      {payload && !payload.combat_system_supported ? (
        <section className="card auth-card">
          <h2>Combat tracker not configured for {payload.campaign.system || "this system"} yet</h2>
          <p>
            This route is a placeholder for the campaign system lane. The current combat tracker is
            DND-5E-only, so no encounter automation is available here for {payload.campaign.system || "this system"} yet.
          </p>
          <div className="hero-actions">
            <a className="button-link" href={payload.links?.flask_campaign_url || `/campaigns/${encodeURIComponent(campaignSlug)}`}>
              Open Campaign Home
            </a>
            {payload.links?.flask_characters_url ? (
              <a className="ghost-button" href={payload.links.flask_characters_url}>
                Open Characters
              </a>
            ) : null}
            {payload.links?.flask_session_url ? (
              <a className="ghost-button" href={payload.links.flask_session_url}>
                Open Session
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {payload?.combat_system_supported ? (
        <>
          <CombatSummaryBand
            roundNumber={tracker?.round_number}
            currentTurnLabel={tracker?.current_turn_label}
            combatantCount={tracker?.combatant_count}
          />

          {tracker?.combatants.length ? (
            <CombatantCarousel
              combatants={tracker.combatants}
              selectedCombatantId={selectedCombatant?.id}
              onSelectCombatant={selectCombatant}
            />
          ) : (
            <section className="card">
              <h3>No combatants</h3>
              <p>The tracker is empty. Use the Encounter controls or DM controls to seed the encounter for now.</p>
            </section>
          )}

          {selectedCombatant ? (
            <section className="combat-selected-snapshot card combat-character-snapshot">
              <div className="section-heading">
                <div>
                  <p className="card-kicker">{selectedCombatantKicker}</p>
                  <h2>{selectedCombatant.name}</h2>
                  {selectedCombatantMeta ? (
                    <p className="meta">{selectedCombatantMeta}</p>
                  ) : null}
                </div>
                <div className="combatant-badges">
                  <span className="combat-badge">Round {tracker?.round_number ?? 1}</span>
                  <span className="combat-badge">Turn {selectedCombatant.turn_value}</span>
                  {selectedCombatant.initiative_bonus_label !== "0" ? (
                    <span className="combat-badge combat-badge--muted">Init {selectedCombatant.initiative_bonus_label}</span>
                  ) : null}
                  {selectedCombatant.is_current_turn ? (
                    <span className="combat-badge combat-badge--active">Current turn</span>
                  ) : null}
                </div>
              </div>
              {selectedCombatant.show_detail ? (
                <div className="combat-selected-snapshot__stats">
                  <span>HP {readNumber(selectedCombatant.current_hp)} / {readNumber(selectedCombatant.max_hp)}</span>
                  <span>Move {readNumber(selectedCombatant.movement_remaining)} / {readNumber(selectedCombatant.movement_total)}</span>
                  <span>{selectedCombatant.has_action ? "Action" : "No action"}</span>
                  <span>{selectedCombatant.has_bonus_action ? "Bonus" : "No bonus"}</span>
                  <span>{selectedCombatant.has_reaction ? "Reaction" : "No reaction"}</span>
                </div>
              ) : (
                <p className="meta">Detailed stats are currently hidden from players.</p>
              )}
            </section>
          ) : null}

          {effectiveCombatView === "status" ? (
            <CombatDmStatusPanel
              canManageCombat={canManageCombat}
              selectedCombatant={selectedCombatant}
              trackerRoundNumber={tracker?.round_number ?? null}
              conditionOptions={conditionOptions}
              turnDraft={turnDraft}
              vitalsDraft={vitalsDraft}
              resourcesDraft={resourcesDraft}
              conditionDraft={conditionDraft}
              isUpdatingTurn={updateTurnMutation.isPending}
              isUpdatingVitals={updateVitalsMutation.isPending}
              isUpdatingResources={updateResourcesMutation.isPending}
              isAddingCondition={addConditionMutation.isPending}
              isDeletingCondition={deleteConditionMutation.isPending}
              isSettingCurrent={setCurrentMutation.isPending}
              isAdvancingTurn={advanceTurnMutation.isPending}
              isDeletingCombatant={deleteCombatantMutation.isPending}
              onTurnDraftChange={(updates) => setTurnDraft((current) => ({ ...current, ...updates }))}
              onVitalsDraftChange={(updates) => setVitalsDraft((current) => ({ ...current, ...updates }))}
              onResourcesDraftChange={(updates) => setResourcesDraft((current) => ({ ...current, ...updates }))}
              onConditionDraftChange={(updates) => setConditionDraft((current) => ({ ...current, ...updates }))}
              onUpdateTurn={(draft) => updateTurnMutation.mutate(draft)}
              onUpdateVitals={(draft) => updateVitalsMutation.mutate(draft)}
              onUpdateResources={(draft) => updateResourcesMutation.mutate(draft)}
              onAddCondition={(draft) => addConditionMutation.mutate(draft)}
              onDeleteCondition={(condition) => deleteConditionMutation.mutate(condition)}
              onSetCurrent={() => setCurrentMutation.mutate()}
              onAdvanceTurn={() => advanceTurnMutation.mutate()}
              onDeleteCombatant={() => deleteCombatantMutation.mutate()}
            />
          ) : null}
          {effectiveCombatView === "controls" ? renderDmControls() : null}
          {effectiveCombatView === "player" ? (
            <CombatPlayerWorkspace
              campaignSlug={campaignSlug}
              selectedCharacterSlug={selectedCharacterSlug}
              selectedPlayerCharacter={selectedPlayerCharacter}
              playerCharacterTargets={payload?.player_character_targets ?? []}
              onSelectCombatant={selectCombatant}
              onSelectedCharacterChange={selectCharacterTarget}
            />
          ) : null}
        </>
      ) : null}
    </>
  );
}

