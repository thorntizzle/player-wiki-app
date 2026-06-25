import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import type {
  CombatSystemsMonsterSearchResult,
  CombatPayload,
  CombatantSummary,
} from "../api/types";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";
import { queryClient, useApiClient } from "../apiClientContext";
import { getApiErrorMessage } from "../apiErrors";
import { ApiErrorNotice, ToastNotice, useToastNotice } from "../components/feedback";
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
import { useCombatMutations, type CombatConditionDraft } from "../combatMutations";

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

type CombatNpcResourceDrafts = Record<string, string>;

interface CombatTurnDraft {
  turnValue: string;
  initiativePriority: string;
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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const { showToast, toastMessage, toastTone } = useToastNotice({ defaultTone: "success" });
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
  const [workspaceVitalsDraft, setWorkspaceVitalsDraft] = useState<CombatVitalsDraft>({
    currentHp: "",
    maxHp: "",
    tempHp: "",
    movementTotal: "",
  });
  const [workspaceResourcesDraft, setWorkspaceResourcesDraft] = useState<CombatResourcesDraft>({
    movementRemaining: "",
    hasAction: false,
    hasBonusAction: false,
    hasReaction: false,
  });
  const [npcResourceDrafts, setNpcResourceDrafts] = useState<CombatNpcResourceDrafts>({});
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
    const currentSearch = location.searchStr;
    setSelectedCombatantId(readSearchCombatantId(currentSearch));
    setActiveCombatView(readSearchView(currentSearch));
  }, [location.searchStr]);

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
  const campaignHomeHref = `/app-next/campaigns/${encodedCampaignSlug}`;
  const campaignCharactersHref = `${campaignHomeHref}/characters`;
  const campaignSessionHref = `${campaignHomeHref}/session`;

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
    void navigate({ to: nextPath as never, resetScroll: false });
  };

  const buildVitalsDraftFromCombatant = (combatant: CombatantSummary): CombatVitalsDraft => ({
      currentHp: String(readNumber(combatant.current_hp)),
      maxHp: String(readNumber(combatant.max_hp)),
      tempHp: String(readNumber(combatant.temp_hp)),
      movementTotal: String(readNumber(combatant.movement_total)),
    });
  const buildResourcesDraftFromCombatant = (combatant: CombatantSummary): CombatResourcesDraft => ({
      movementRemaining: String(readNumber(combatant.movement_remaining)),
      hasAction: Boolean(combatant.has_action),
      hasBonusAction: Boolean(combatant.has_bonus_action),
      hasReaction: Boolean(combatant.has_reaction),
    });

  const syncCombatantDrafts = (combatant: CombatantSummary) => {
    setVitalsDraft(buildVitalsDraftFromCombatant(combatant));
    setResourcesDraft(buildResourcesDraftFromCombatant(combatant));
    setNpcResourceDrafts(
      Object.fromEntries(
        (combatant.npc_resource_counters ?? []).map((counter) => [
          counter.resource_key,
          String(readNumber(counter.current_value)),
        ]),
      ),
    );
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

  useEffect(() => {
    if (!selectedPlayerCharacter) {
      return;
    }
    setWorkspaceVitalsDraft(buildVitalsDraftFromCombatant(selectedPlayerCharacter));
    setWorkspaceResourcesDraft(buildResourcesDraftFromCombatant(selectedPlayerCharacter));
  }, [selectedPlayerCharacter?.id]);

  const selectCombatant = (combatantId: number) => {
    const focusedCombatant = tracker?.combatants.find((combatant) => combatant.id === combatantId);
    if (focusedCombatant) {
      syncCombatantDrafts(focusedCombatant);
    }
    setSelectedCombatantId(combatantId);
    if (effectiveCombatView === "player") {
      return;
    }
    setCombatUrl(effectiveCombatView, combatantId);
  };

  const selectCombatView = (view: CombatView) => {
    setActiveCombatView(view);
    setCombatUrl(view, selectedCombatantId ?? selectedCombatant?.id ?? null);
  };

  const selectCharacterTarget = (characterSlug: string) => {
    const target = payload?.player_character_targets.find((item) => item.character_slug === characterSlug);
    if (target?.combatant_id) {
      selectCombatant(target.combatant_id);
    }
  };

  const {
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
    updateNpcResourcesMutation,
    updateResourcesMutation,
    updateTurnMutation,
    updateVitalsMutation,
  } = useCombatMutations({
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
    setStatusMessage: showToast,
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
    refetchCombat: combatQuery.refetch,
  });

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
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
      <ToastNotice message={toastMessage} tone={toastTone} />

      {payload && !payload.combat_system_supported ? (
        <section className="card auth-card">
          <h2>Combat tracker not configured for {payload.campaign.system || "this system"} yet</h2>
          <p>
            This route is a placeholder for the campaign system lane. The current combat tracker is
            DND-5E-only, so no encounter automation is available here for {payload.campaign.system || "this system"} yet.
          </p>
          <div className="hero-actions">
            <a className="button-link" href={campaignHomeHref}>
              Open Campaign Home
            </a>
            <a className="ghost-button" href={campaignCharactersHref}>
              Open Characters
            </a>
            <a className="ghost-button" href={campaignSessionHref}>
              Open Session
            </a>
          </div>
        </section>
      ) : null}

      {payload?.combat_system_supported ? (
        <>
          <CombatSummaryBand
            roundNumber={tracker?.round_number}
            currentTurnLabel={tracker?.current_turn_label}
            combatantCount={tracker?.combatant_count}
            isAdvancingTurn={advanceTurnMutation.isPending}
            onAdvanceTurn={
              canManageCombat && effectiveCombatView !== "player" ? () => advanceTurnMutation.mutate() : undefined
            }
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
                <div className="combat-selected-snapshot__stats" aria-label="Selected combatant tactical values">
                  <div className="combat-stat-tile">
                    <span className="combat-stat-tile__label">HP</span>
                    <strong className="combat-stat-tile__value">
                      {readNumber(selectedCombatant.current_hp)} / {readNumber(selectedCombatant.max_hp)}
                    </strong>
                  </div>
                  <div className="combat-stat-tile">
                    <span className="combat-stat-tile__label">Move</span>
                    <strong className="combat-stat-tile__value">
                      {readNumber(selectedCombatant.movement_remaining)} / {readNumber(selectedCombatant.movement_total)}
                    </strong>
                  </div>
                  <div className={selectedCombatant.has_action ? "combat-stat-tile" : "combat-stat-tile combat-stat-tile--spent"}>
                    <span className="combat-stat-tile__label">Action</span>
                    <strong className="combat-stat-tile__value">{selectedCombatant.has_action ? "Available" : "Spent"}</strong>
                  </div>
                  <div className={selectedCombatant.has_bonus_action ? "combat-stat-tile" : "combat-stat-tile combat-stat-tile--spent"}>
                    <span className="combat-stat-tile__label">Bonus</span>
                    <strong className="combat-stat-tile__value">{selectedCombatant.has_bonus_action ? "Available" : "Spent"}</strong>
                  </div>
                  <div className={selectedCombatant.has_reaction ? "combat-stat-tile" : "combat-stat-tile combat-stat-tile--spent"}>
                    <span className="combat-stat-tile__label">Reaction</span>
                    <strong className="combat-stat-tile__value">{selectedCombatant.has_reaction ? "Available" : "Spent"}</strong>
                  </div>
                </div>
              ) : (
                <p className="meta">Detailed stats are currently hidden from players.</p>
              )}
              <div className="combat-selected-snapshot__conditions" aria-label="Selected combatant conditions">
                <span className="combat-stat-tile__label">Conditions</span>
                {selectedCombatant.conditions.length ? (
                  <div className="badge-list">
                    {selectedCombatant.conditions.map((condition) => (
                      <span className="meta-badge" key={condition.id}>
                        {condition.name}
                        {condition.duration_text ? `: ${condition.duration_text}` : ""}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="meta">No active conditions.</p>
                )}
              </div>
              {selectedCombatant.show_detail &&
              ((selectedCombatant.npc_resource_counters ?? []).length ||
                (selectedCombatant.npc_resource_notes ?? []).length) ? (
                <div className="combat-selected-snapshot__npc-resources" aria-label="Selected NPC source resources">
                  <span className="combat-stat-tile__label">Source resources</span>
                  {(selectedCombatant.npc_resource_counters ?? []).length ? (
                    <div className="combat-npc-resource-chip-grid">
                      {(selectedCombatant.npc_resource_counters ?? []).map((counter) => (
                        <div className="combat-npc-resource-chip" key={counter.resource_key}>
                          <strong>{counter.label}</strong>
                          <span>
                            {readNumber(counter.current_value)} / {readNumber(counter.max_value)}
                          </span>
                          <p className="meta">
                            {[counter.reset_label, counter.source_label].filter(Boolean).join(" | ")}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {(selectedCombatant.npc_resource_notes ?? []).length ? (
                    <div className="combat-npc-resource-notes combat-npc-resource-notes--snapshot">
                      {(selectedCombatant.npc_resource_notes ?? []).map((note) => (
                        <div className="combat-npc-resource-note" key={`${note.label}-${note.note}`}>
                          <strong>{note.label}</strong>
                          <p className="meta">{note.note}</p>
                          {note.source_label ? <span className="meta">{note.source_label}</span> : null}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
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
                  npcResourceDrafts={npcResourceDrafts}
                  conditionDraft={conditionDraft}
                  isUpdatingTurn={updateTurnMutation.isPending}
                  isUpdatingVitals={updateVitalsMutation.isPending}
                  isUpdatingResources={updateResourcesMutation.isPending}
                  isUpdatingNpcResources={updateNpcResourcesMutation.isPending}
                  isAddingCondition={addConditionMutation.isPending}
                  isDeletingCondition={deleteConditionMutation.isPending}
                  isSettingCurrent={setCurrentMutation.isPending}
                  isDeletingCombatant={deleteCombatantMutation.isPending}
                  onTurnDraftChange={(updates) => setTurnDraft((current) => ({ ...current, ...updates }))}
                  onVitalsDraftChange={(updates) => setVitalsDraft((current) => ({ ...current, ...updates }))}
                  onResourcesDraftChange={(updates) => setResourcesDraft((current) => ({ ...current, ...updates }))}
                  onNpcResourceDraftChange={(resourceKey, value) =>
                    setNpcResourceDrafts((current) => ({ ...current, [resourceKey]: value }))
                  }
                  onConditionDraftChange={(updates) => setConditionDraft((current) => ({ ...current, ...updates }))}
                  onUpdateTurn={(draft) => updateTurnMutation.mutate(draft)}
                  onUpdateVitals={(draft) => updateVitalsMutation.mutate(draft)}
                  onUpdateResources={(draft) => updateResourcesMutation.mutate(draft)}
                  onUpdateNpcResources={(draft) => updateNpcResourcesMutation.mutate(draft)}
                  onAddCondition={(draft) => addConditionMutation.mutate(draft)}
                  onDeleteCondition={(condition) => deleteConditionMutation.mutate(condition)}
                  onSetCurrent={() => setCurrentMutation.mutate()}
                  onDeleteCombatant={() => deleteCombatantMutation.mutate()}
                />
              ) : null}
            </section>
          ) : null}

          {effectiveCombatView === "status" && selectedCombatant?.character_slug ? (
            <CombatPlayerWorkspace
              campaignSlug={campaignSlug}
              selectedCharacterSlug={selectedCombatant.character_slug}
              selectedCombatant={selectedCombatant}
              playerCharacterTargets={payload?.player_character_targets ?? []}
              combatSections={payload?.selected_player_combat_sections ?? []}
              vitalsDraft={vitalsDraft}
              resourcesDraft={resourcesDraft}
              isUpdatingResources={updateResourcesMutation.isPending}
              onSelectCombatant={selectCombatant}
              onSelectedCharacterChange={selectCharacterTarget}
              onResourcesDraftChange={(updates) => setResourcesDraft((current) => ({ ...current, ...updates }))}
              onUpdateResources={(combatant, payload) =>
                updateResourcesMutation.mutate({
                  combatant,
                  focusCombatantId: selectedCombatant?.id ?? selectedCombatantId,
                  payload,
                })
              }
            />
          ) : null}

          {effectiveCombatView === "controls" ? renderDmControls() : null}
          {effectiveCombatView === "player" ? (
            <CombatPlayerWorkspace
              campaignSlug={campaignSlug}
              selectedCharacterSlug={selectedCharacterSlug}
              selectedCombatant={selectedPlayerCharacter}
              playerCharacterTargets={payload?.player_character_targets ?? []}
              combatSections={payload?.selected_player_combat_sections ?? []}
              vitalsDraft={workspaceVitalsDraft}
              resourcesDraft={workspaceResourcesDraft}
              isUpdatingResources={updateResourcesMutation.isPending}
              onSelectCombatant={selectCombatant}
              onSelectedCharacterChange={selectCharacterTarget}
              onResourcesDraftChange={(updates) =>
                setWorkspaceResourcesDraft((current) => ({ ...current, ...updates }))
              }
              onUpdateResources={(combatant, payload) =>
                updateResourcesMutation.mutate({
                  combatant,
                  focusCombatantId: selectedCombatant?.id ?? selectedCombatantId,
                  payload,
                })
              }
            />
          ) : null}
        </>
      ) : null}
    </>
  );
}

