import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { apiErrorMessage } from "../api/client";
import type {
  CombatAvailableCharacterChoice,
  CombatAvailableStatblockChoice,
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
import { CombatPlayerWorkspace } from "../components/CombatPlayerWorkspace";
import { resolveCombatLivePayload } from "../combatLiveUtils";
import {
  CombatantCarousel,
  CombatSummaryBand,
  CombatViewSwitch,
  type CombatView,
} from "../components/CombatChrome";

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

interface CombatPlayerSeedDraft {
  characterSlug: string;
  turnValue: string;
  initiativePriority: string;
}

interface CombatNpcSeedDraft {
  displayName: string;
  turnValue: string;
  initiativeBonus: string;
  dexterityModifier: string;
  initiativePriority: string;
  currentHp: string;
  maxHp: string;
  tempHp: string;
  movementTotal: string;
}

interface CombatStatblockSeedDraft {
  statblockId: string;
  displayName: string;
  turnValue: string;
  initiativePriority: string;
}

interface CombatSystemsSeedDraft {
  entryKey: string;
  displayName: string;
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
  const [combatAddMode, setCombatAddMode] = useState<"player" | "systems" | "dm-content" | "custom">(
    "player",
  );
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
  const availableCharacters: CombatAvailableCharacterChoice[] = payload?.available_character_choices ?? [];
  const availableStatblocks: CombatAvailableStatblockChoice[] = payload?.available_statblock_choices ?? [];
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

  const searchSystemsMonsters = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
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

  const renderDmStatus = () => {
    if (!canManageCombat) {
      return (
        <article className="card">
          <p>DM combat status requires combat management access.</p>
        </article>
      );
    }
    if (!selectedCombatant) {
      return (
        <article className="card">
          <h3>No selected combatant</h3>
          <p>Add combatants in DM Controls, then select one from the turn order.</p>
        </article>
      );
    }
    const isPlayerCharacter = Boolean(selectedCombatant.character_slug);
    const vitalsPayload = (): CombatVitalsPatchPayload => {
      const base: CombatVitalsPatchPayload = {
        current_hp: vitalsDraft.currentHp,
        temp_hp: vitalsDraft.tempHp,
      };
      if (isPlayerCharacter) {
        base.expected_revision = selectedCombatant.state_revision;
      } else {
        base.expected_combatant_revision = selectedCombatant.combatant_revision;
        base.max_hp = vitalsDraft.maxHp;
        base.movement_total = vitalsDraft.movementTotal;
      }
      return base;
    };

    return (
      <>
        <section className="combat-dm-grid" aria-label="DM tactical controls">
          <article className="card combat-control-card">
            <div className="section-heading combat-status-snapshot__heading">
              <div>
                <p className="card-kicker">Authority</p>
                <h2>Turn Focus</h2>
              </div>
              <div className="combatant-badges">
                <span className="combat-badge">Round {tracker?.round_number ?? "?"}</span>
                <span className="combat-badge">Turn {selectedCombatant.turn_value}</span>
                {selectedCombatant.is_current_turn ? (
                  <span className="combat-badge combat-badge--active">Current turn</span>
                ) : (
                  <button
                    type="button"
                    className="combat-badge combat-badge--button combat-status-snapshot__set-current"
                    onClick={() => setCurrentMutation.mutate()}
                    disabled={setCurrentMutation.isPending}
                  >
                    {setCurrentMutation.isPending ? "Setting..." : "Set current"}
                  </button>
                )}
              </div>
            </div>
            <form
              className="stack-form combat-status-authority-form"
              onSubmit={(event) => {
                event.preventDefault();
                updateTurnMutation.mutate({
                  expected_combatant_revision: selectedCombatant.combatant_revision,
                  turn_value: turnDraft.turnValue,
                  initiative_priority: turnDraft.initiativePriority,
                });
              }}
            >
              <label className="field">
                <span>Turn value</span>
                <input
                  type="number"
                  value={turnDraft.turnValue}
                  onChange={(event) => setTurnDraft({ ...turnDraft, turnValue: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Priority</span>
                <input
                  type="number"
                  min="1"
                  value={turnDraft.initiativePriority}
                  onChange={(event) =>
                    setTurnDraft({ ...turnDraft, initiativePriority: event.currentTarget.value })
                  }
                />
              </label>
              <button type="submit" disabled={updateTurnMutation.isPending}>
                {updateTurnMutation.isPending ? "Saving..." : "Save turn"}
              </button>
            </form>
            <div className="hero-actions combat-turn-actions">
              <button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>
                {advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}
              </button>
            </div>
          </article>

          <article className="card combat-control-card">
            <div>
              <p className="meta">Snapshot</p>
              <h3>Vitals</h3>
            </div>
            <div className="combat-summary-grid combat-summary-grid--snapshot">
              <form
                className="combat-stat combat-stat--editable"
                onSubmit={(event) => {
                  event.preventDefault();
                  updateVitalsMutation.mutate(vitalsPayload());
                }}
              >
                <span className="meta">HP</span>
                <div className="combat-inline-value">
                  <input
                    className="combat-stat-input combat-stat-input--number"
                    aria-label="DM Current HP"
                    type="number"
                    value={vitalsDraft.currentHp}
                    onChange={(event) => setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })}
                  />
                  <span className="combat-inline-divider">/</span>
                  <strong>{vitalsDraft.maxHp}</strong>
                </div>
              </form>
              <form
                className="combat-stat combat-stat--editable"
                onSubmit={(event) => {
                  event.preventDefault();
                  updateVitalsMutation.mutate(vitalsPayload());
                }}
              >
                <span className="meta">Temp HP</span>
                <input
                  className="combat-stat-input combat-stat-input--single"
                  aria-label="DM Temp HP"
                  type="number"
                  min="0"
                  value={vitalsDraft.tempHp}
                  onChange={(event) => setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })}
                />
              </form>
              {!isPlayerCharacter ? (
                <>
                  <label className="field">
                    <span>Max HP</span>
                    <input
                      aria-label="DM Max HP"
                      type="number"
                      min="0"
                      value={vitalsDraft.maxHp}
                      onChange={(event) => setVitalsDraft({ ...vitalsDraft, maxHp: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Movement total</span>
                    <input
                      aria-label="DM Movement total"
                      type="number"
                      min="0"
                      value={vitalsDraft.movementTotal}
                      onChange={(event) =>
                        setVitalsDraft({ ...vitalsDraft, movementTotal: event.currentTarget.value })
                      }
                    />
                  </label>
                </>
              ) : null}
              <button type="button" onClick={() => updateVitalsMutation.mutate(vitalsPayload())} aria-label="Save DM vitals" disabled={updateVitalsMutation.isPending}>
                {updateVitalsMutation.isPending ? "Saving..." : "Save vitals"}
              </button>
            </div>
          </article>

          <article className="card combat-control-card">
            <div>
              <p className="meta">Round tools</p>
              <h3>Action Economy</h3>
            </div>
            <form
              className="combat-resource-strip combat-inline-resource-form"
              onSubmit={(event) => {
                event.preventDefault();
                updateResourcesMutation.mutate({
                  expected_combatant_revision: selectedCombatant.combatant_revision,
                  movement_remaining: resourcesDraft.movementRemaining,
                  has_action: resourcesDraft.hasAction,
                  has_bonus_action: resourcesDraft.hasBonusAction,
                  has_reaction: resourcesDraft.hasReaction,
                });
              }}
            >
              <label className="combat-stat">
                <span className="meta">Movement</span>
                <div className="combat-inline-value">
                  <input
                    className="combat-stat-input combat-stat-input--number"
                    aria-label="DM Movement Remaining"
                    type="number"
                    min="0"
                    value={resourcesDraft.movementRemaining}
                    onChange={(event) =>
                      setResourcesDraft({ ...resourcesDraft, movementRemaining: event.currentTarget.value })
                    }
                  />
                  <span className="combat-inline-divider">/</span>
                  <strong>{vitalsDraft.movementTotal}</strong>
                </div>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasAction}
                  onChange={(event) => setResourcesDraft({ ...resourcesDraft, hasAction: event.currentTarget.checked })}
                />
                <span className="combat-resource">Action</span>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasBonusAction}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, hasBonusAction: event.currentTarget.checked })
                  }
                />
                <span className="combat-resource">Bonus action</span>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasReaction}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, hasReaction: event.currentTarget.checked })
                  }
                />
                <span className="combat-resource">Reaction</span>
              </label>
              <button type="submit" disabled={updateResourcesMutation.isPending}>
                {updateResourcesMutation.isPending ? "Saving..." : "Save economy"}
              </button>
            </form>
          </article>

          <article className="card combat-control-card">
            <datalist id="gen2-combat-condition-options">
              {conditionOptions.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
            <section className="combat-conditions combat-conditions--compact combat-status-conditions">
              <div className="section-heading">
                <h3>Conditions</h3>
                <details className="combat-condition-editor combat-condition-editor--add">
                  <summary>Add condition</summary>
                  <form
                    className="combat-condition-editor__form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      addConditionMutation.mutate(conditionDraft);
                    }}
                  >
                    <label className="field">
                      <span>Condition</span>
                      <input
                        type="text"
                        list="gen2-combat-condition-options"
                        value={conditionDraft.name}
                        onChange={(event) => setConditionDraft({ ...conditionDraft, name: event.currentTarget.value })}
                      />
                    </label>
                    <label className="field">
                      <span>Duration</span>
                      <input
                        type="text"
                        value={conditionDraft.durationText}
                        onChange={(event) =>
                          setConditionDraft({ ...conditionDraft, durationText: event.currentTarget.value })
                        }
                      />
                    </label>
                    <button type="submit" disabled={addConditionMutation.isPending}>
                      {addConditionMutation.isPending ? "Adding..." : "Add condition"}
                    </button>
                  </form>
                </details>
              </div>
              {selectedCombatant.conditions.length ? (
                <div className="combat-condition-list">
                  {selectedCombatant.conditions.map((condition) => (
                    <div className="combat-condition-item" key={condition.id}>
                      <div>
                        <strong>{condition.name}</strong>
                        {condition.duration_text ? <p className="meta">{condition.duration_text}</p> : null}
                      </div>
                      <div className="combat-condition-actions">
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => deleteConditionMutation.mutate(condition)}
                          disabled={deleteConditionMutation.isPending}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="meta">No conditions are active on this combatant.</p>
              )}
            </section>
          </article>
        </section>

        <section className="card combat-danger-card">
          <div>
            <p className="meta">Cleanup</p>
            <h3>Selected combatant</h3>
          </div>
          <button type="button" className="ghost-button" onClick={() => deleteCombatantMutation.mutate()}>
            {deleteCombatantMutation.isPending ? "Removing..." : "Remove selected combatant"}
          </button>
        </section>
      </>
    );
  };

  const renderDmControls = () => {
    if (!canManageCombat) {
      return (
        <article className="card">
          <p>DM combat controls require combat management access.</p>
        </article>
      );
    }
    return (
      <section className="combat-controls-layout" aria-label="DM combat controls">
        <article className="card combat-control-card">
          <div>
            <p className="meta">Encounter controls</p>
            <h3>Tracker</h3>
          </div>
          <button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>
            {advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}
          </button>
        </article>

        <section className="card sidebar-card">
          <h2>Add combatant</h2>
          <div className="combat-add-combatant-mode-switcher" role="radiogroup" aria-label="Add combatant type">
            <input
              className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--player"
              id="combat-add-mode-player"
              name="combat-add-mode"
              type="radio"
              value="player"
              checked={combatAddMode === "player"}
              onChange={() => setCombatAddMode("player")}
            />
            {canAccessSystems ? (
              <input
                className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--systems"
                id="combat-add-mode-systems"
                name="combat-add-mode"
                type="radio"
                value="systems"
                checked={combatAddMode === "systems"}
                onChange={() => setCombatAddMode("systems")}
              />
            ) : null}
            {canAccessDmContent ? (
              <input
                className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--dm-content"
                id="combat-add-mode-dm-content"
                name="combat-add-mode"
                type="radio"
                value="dm-content"
                checked={combatAddMode === "dm-content"}
                onChange={() => setCombatAddMode("dm-content")}
              />
            ) : null}
            <input
              className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--custom"
              id="combat-add-mode-custom"
              name="combat-add-mode"
              type="radio"
              value="custom"
              checked={combatAddMode === "custom"}
              onChange={() => setCombatAddMode("custom")}
            />
            <div className="combat-add-combatant-mode-toggle">
              <label className="ghost-button" htmlFor="combat-add-mode-player">
                Add player character
              </label>
              {canAccessSystems ? (
                <label className="ghost-button" htmlFor="combat-add-mode-systems">
                  Add NPC from Systems
                </label>
              ) : null}
              {canAccessDmContent ? (
                <label className="ghost-button" htmlFor="combat-add-mode-dm-content">
                  Add NPC from DM Content
                </label>
              ) : null}
              <label className="ghost-button" htmlFor="combat-add-mode-custom">
                Add custom combatant
              </label>
            </div>

            <div
              className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--player ${
                combatAddMode === "player" ? "combat-add-combatant-mode-panel--active" : ""
              }`}
            >
              {availableCharacters.length ? (
                <form
                  className="stack-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    addPlayerMutation.mutate();
                  }}
                >
                  <label className="field">
                    <span>Character</span>
                    <select
                      value={playerSeedDraft.characterSlug}
                      onChange={(event) => setPlayerSeedDraft({ ...playerSeedDraft, characterSlug: event.currentTarget.value })}
                    >
                      <option value="">Choose character</option>
                      {availableCharacters.map((choice) => (
                        <option key={choice.slug} value={choice.slug}>
                          {choice.name} {choice.subtitle ? `- ${choice.subtitle}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Turn value</span>
                    <input
                      type="number"
                      value={playerSeedDraft.turnValue}
                      onChange={(event) => setPlayerSeedDraft({ ...playerSeedDraft, turnValue: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Priority</span>
                    <input
                      type="number"
                      min="1"
                      value={playerSeedDraft.initiativePriority}
                      onChange={(event) =>
                        setPlayerSeedDraft({ ...playerSeedDraft, initiativePriority: event.currentTarget.value })
                      }
                    />
                  </label>
                  <button type="submit" disabled={addPlayerMutation.isPending}>
                    {addPlayerMutation.isPending ? "Adding..." : "Add player character"}
                  </button>
                </form>
              ) : (
                <p className="meta">All visible player characters are already in the tracker.</p>
              )}
            </div>

            {canAccessSystems ? (
              <div
                className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--systems ${
                  combatAddMode === "systems" ? "combat-add-combatant-mode-panel--active" : ""
                }`}
              >
                <form className="stack-form" onSubmit={searchSystemsMonsters}>
                  <label className="field">
                    <span>Search monsters</span>
                    <input
                      type="search"
                      value={systemsSearchQuery}
                      onChange={(event) => setSystemsSearchQuery(event.currentTarget.value)}
                    />
                  </label>
                  <button type="submit">Search</button>
                </form>
                {systemsSearchStatus ? <p className="status status-neutral">{systemsSearchStatus}</p> : null}
                <div className="combat-systems-results">
                  {systemsSearchResults.map((result) => (
                    <article className="compact-card" key={result.entry_key}>
                      <div>
                        <strong>{result.title}</strong>
                        <p className="meta">
                          {result.source_id} - {result.subtitle} - Init {result.initiative_bonus}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => addSystemsMonsterMutation.mutate(result.entry_key)}
                        disabled={addSystemsMonsterMutation.isPending}
                      >
                        Add
                      </button>
                    </article>
                  ))}
                </div>
                <div className="stack-form">
                  <label className="field">
                    <span>Display name</span>
                    <input
                      type="text"
                      value={systemsSeedDraft.displayName}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, displayName: event.currentTarget.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Turn value</span>
                    <input
                      type="number"
                      value={systemsSeedDraft.turnValue}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, turnValue: event.currentTarget.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Priority</span>
                    <input
                      type="number"
                      min="1"
                      value={systemsSeedDraft.initiativePriority}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, initiativePriority: event.currentTarget.value })
                      }
                    />
                  </label>
                </div>
              </div>
            ) : null}

            {canAccessDmContent ? (
              <div
                className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--dm-content ${
                  combatAddMode === "dm-content" ? "combat-add-combatant-mode-panel--active" : ""
                }`}
              >
                {availableStatblocks.length ? (
                  <form
                    className="stack-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      addStatblockMutation.mutate();
                    }}
                  >
                    <label className="field">
                      <span>Statblock</span>
                      <select
                        value={statblockSeedDraft.statblockId}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, statblockId: event.currentTarget.value })
                        }
                      >
                        <option value="">Choose statblock</option>
                        {availableStatblocks.map((choice) => (
                          <option key={choice.id} value={choice.id}>
                            {choice.title} - {choice.subtitle}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Display name override</span>
                      <input
                        type="text"
                        value={statblockSeedDraft.displayName}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, displayName: event.currentTarget.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Turn override</span>
                      <input
                        type="number"
                        value={statblockSeedDraft.turnValue}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, turnValue: event.currentTarget.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Priority</span>
                      <input
                        type="number"
                        min="1"
                        value={statblockSeedDraft.initiativePriority}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, initiativePriority: event.currentTarget.value })
                        }
                      />
                    </label>
                    <button type="submit" disabled={addStatblockMutation.isPending}>
                      {addStatblockMutation.isPending ? "Adding..." : "Add statblock"}
                    </button>
                  </form>
                ) : (
                  <p className="meta">Upload statblocks on the DM Content page to use them here.</p>
                )}
              </div>
            ) : null}

            <div
              className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--custom ${
                combatAddMode === "custom" ? "combat-add-combatant-mode-panel--active" : ""
              }`}
            >
              <form
                className="stack-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  addNpcMutation.mutate();
                }}
              >
                <label className="field">
                  <span>Name</span>
                  <input
                    type="text"
                    value={npcSeedDraft.displayName}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, displayName: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Turn value</span>
                  <input
                    type="number"
                    value={npcSeedDraft.turnValue}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, turnValue: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Initiative bonus</span>
                  <input
                    type="number"
                    value={npcSeedDraft.initiativeBonus}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, initiativeBonus: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Dex mod</span>
                  <input
                    type="number"
                    value={npcSeedDraft.dexterityModifier}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, dexterityModifier: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Current HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.currentHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, currentHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Max HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.maxHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, maxHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Temp HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.tempHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, tempHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Movement</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.movementTotal}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, movementTotal: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Priority</span>
                  <input
                    type="number"
                    min="1"
                    value={npcSeedDraft.initiativePriority}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, initiativePriority: event.currentTarget.value })
                    }
                  />
                </label>
                <button type="submit" disabled={addNpcMutation.isPending}>
                  {addNpcMutation.isPending ? "Adding..." : "Add NPC combatant"}
                </button>
              </form>
            </div>
          </div>
        </section>

        <section className="card sidebar-card">
          <h2>Encounter cleanup</h2>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={confirmClearTracker}
              onChange={(event) => setConfirmClearTracker(event.currentTarget.checked)}
            />
            Confirm clear tracker
          </label>
          <button
            type="button"
            className="ghost-button"
            onClick={() => clearCombatMutation.mutate()}
            disabled={!confirmClearTracker || clearCombatMutation.isPending}
          >
            {clearCombatMutation.isPending ? "Clearing..." : "Clear tracker"}
          </button>
        </section>
      </section>
    );
  };

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

          {effectiveCombatView === "status" ? renderDmStatus() : null}
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

