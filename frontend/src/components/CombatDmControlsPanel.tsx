import type {
  CombatAvailableCharacterChoice,
  CombatAvailableStatblockChoice,
  CombatSystemsMonsterSearchResult,
} from "../api/types";

export type CombatAddMode = "player" | "systems" | "dm-content" | "custom";

export interface CombatPlayerSeedDraft {
  characterSlug: string;
  turnValue: string;
  initiativePriority: string;
}

export interface CombatNpcSeedDraft {
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

export interface CombatStatblockSeedDraft {
  statblockId: string;
  displayName: string;
  turnValue: string;
  initiativePriority: string;
}

export interface CombatSystemsSeedDraft {
  entryKey: string;
  displayName: string;
  turnValue: string;
  initiativePriority: string;
}

interface CombatDmControlsPanelProps {
  canManageCombat: boolean;
  canAccessSystems: boolean;
  canAccessDmContent: boolean;
  combatAddMode: CombatAddMode;
  availableCharacters: CombatAvailableCharacterChoice[];
  availableStatblocks: CombatAvailableStatblockChoice[];
  playerSeedDraft: CombatPlayerSeedDraft;
  npcSeedDraft: CombatNpcSeedDraft;
  statblockSeedDraft: CombatStatblockSeedDraft;
  systemsSeedDraft: CombatSystemsSeedDraft;
  systemsSearchQuery: string;
  systemsSearchStatus: string | null;
  systemsSearchResults: CombatSystemsMonsterSearchResult[];
  confirmClearTracker: boolean;
  isAddingPlayer: boolean;
  isAddingNpc: boolean;
  isAddingStatblock: boolean;
  isAddingSystemsMonster: boolean;
  isClearingCombat: boolean;
  onCombatAddModeChange: (mode: CombatAddMode) => void;
  onPlayerSeedDraftChange: (updates: Partial<CombatPlayerSeedDraft>) => void;
  onNpcSeedDraftChange: (updates: Partial<CombatNpcSeedDraft>) => void;
  onStatblockSeedDraftChange: (updates: Partial<CombatStatblockSeedDraft>) => void;
  onSystemsSeedDraftChange: (updates: Partial<CombatSystemsSeedDraft>) => void;
  onSystemsSearchQueryChange: (query: string) => void;
  onConfirmClearTrackerChange: (confirmed: boolean) => void;
  onAddPlayer: () => void;
  onAddNpc: () => void;
  onAddStatblock: () => void;
  onAddSystemsMonster: (entryKey: string) => void;
  onSearchSystemsMonsters: () => void;
  onClearCombat: () => void;
}

export function CombatDmControlsPanel({
  canManageCombat,
  canAccessSystems,
  canAccessDmContent,
  combatAddMode,
  availableCharacters,
  availableStatblocks,
  playerSeedDraft,
  npcSeedDraft,
  statblockSeedDraft,
  systemsSeedDraft,
  systemsSearchQuery,
  systemsSearchStatus,
  systemsSearchResults,
  confirmClearTracker,
  isAddingPlayer,
  isAddingNpc,
  isAddingStatblock,
  isAddingSystemsMonster,
  isClearingCombat,
  onCombatAddModeChange,
  onPlayerSeedDraftChange,
  onNpcSeedDraftChange,
  onStatblockSeedDraftChange,
  onSystemsSeedDraftChange,
  onSystemsSearchQueryChange,
  onConfirmClearTrackerChange,
  onAddPlayer,
  onAddNpc,
  onAddStatblock,
  onAddSystemsMonster,
  onSearchSystemsMonsters,
  onClearCombat,
}: CombatDmControlsPanelProps) {
  if (!canManageCombat) {
    return (
      <article className="card">
        <p>DM combat controls require combat management access.</p>
      </article>
    );
  }

  const clearTrackerHint = !confirmClearTracker
    ? "Check Confirm clear tracker to enable this action."
    : isClearingCombat
      ? "Tracker clear is already in progress."
      : "";

  return (
    <section className="combat-controls-layout" aria-label="DM combat controls">
      <section className="card combat-control-card">
        <h2>Add combatant</h2>
        <div className="combat-add-combatant-mode-switcher" role="radiogroup" aria-label="Add combatant type">
          <input
            className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--player"
            id="combat-add-mode-player"
            name="combat-add-mode"
            type="radio"
            value="player"
            checked={combatAddMode === "player"}
            onChange={() => onCombatAddModeChange("player")}
          />
          {canAccessSystems ? (
            <input
              className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--systems"
              id="combat-add-mode-systems"
              name="combat-add-mode"
              type="radio"
              value="systems"
              checked={combatAddMode === "systems"}
              onChange={() => onCombatAddModeChange("systems")}
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
              onChange={() => onCombatAddModeChange("dm-content")}
            />
          ) : null}
          <input
            className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--custom"
            id="combat-add-mode-custom"
            name="combat-add-mode"
            type="radio"
            value="custom"
            checked={combatAddMode === "custom"}
            onChange={() => onCombatAddModeChange("custom")}
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
                  onAddPlayer();
                }}
              >
                <label className="field">
                  <span>Character</span>
                  <select
                    value={playerSeedDraft.characterSlug}
                    onChange={(event) => onPlayerSeedDraftChange({ characterSlug: event.currentTarget.value })}
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
                    onChange={(event) => onPlayerSeedDraftChange({ turnValue: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Priority</span>
                  <input
                    type="number"
                    min="1"
                    value={playerSeedDraft.initiativePriority}
                    onChange={(event) => onPlayerSeedDraftChange({ initiativePriority: event.currentTarget.value })}
                  />
                </label>
                <button type="submit" disabled={isAddingPlayer}>
                  {isAddingPlayer ? "Adding..." : "Add player character"}
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
              <form
                className="stack-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  onSearchSystemsMonsters();
                }}
              >
                <label className="field">
                  <span>Search monsters</span>
                  <input
                    type="search"
                    value={systemsSearchQuery}
                    onChange={(event) => onSystemsSearchQueryChange(event.currentTarget.value)}
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
                      onClick={() => onAddSystemsMonster(result.entry_key)}
                      disabled={isAddingSystemsMonster}
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
                    onChange={(event) => onSystemsSeedDraftChange({ displayName: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Turn value</span>
                  <input
                    type="number"
                    value={systemsSeedDraft.turnValue}
                    onChange={(event) => onSystemsSeedDraftChange({ turnValue: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Priority</span>
                  <input
                    type="number"
                    min="1"
                    value={systemsSeedDraft.initiativePriority}
                    onChange={(event) => onSystemsSeedDraftChange({ initiativePriority: event.currentTarget.value })}
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
                    onAddStatblock();
                  }}
                >
                  <label className="field">
                    <span>Statblock</span>
                    <select
                      value={statblockSeedDraft.statblockId}
                      onChange={(event) => onStatblockSeedDraftChange({ statblockId: event.currentTarget.value })}
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
                      onChange={(event) => onStatblockSeedDraftChange({ displayName: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Turn override</span>
                    <input
                      type="number"
                      value={statblockSeedDraft.turnValue}
                      onChange={(event) => onStatblockSeedDraftChange({ turnValue: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Priority</span>
                    <input
                      type="number"
                      min="1"
                      value={statblockSeedDraft.initiativePriority}
                      onChange={(event) =>
                        onStatblockSeedDraftChange({ initiativePriority: event.currentTarget.value })
                      }
                    />
                  </label>
                  <button type="submit" disabled={isAddingStatblock}>
                    {isAddingStatblock ? "Adding..." : "Add statblock"}
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
                onAddNpc();
              }}
            >
              <label className="field">
                <span>Name</span>
                <input
                  type="text"
                  value={npcSeedDraft.displayName}
                  onChange={(event) => onNpcSeedDraftChange({ displayName: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Turn value</span>
                <input
                  type="number"
                  value={npcSeedDraft.turnValue}
                  onChange={(event) => onNpcSeedDraftChange({ turnValue: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Initiative bonus</span>
                <input
                  type="number"
                  value={npcSeedDraft.initiativeBonus}
                  onChange={(event) => onNpcSeedDraftChange({ initiativeBonus: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Dex mod</span>
                <input
                  type="number"
                  value={npcSeedDraft.dexterityModifier}
                  onChange={(event) => onNpcSeedDraftChange({ dexterityModifier: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Current HP</span>
                <input
                  type="number"
                  min="0"
                  value={npcSeedDraft.currentHp}
                  onChange={(event) => onNpcSeedDraftChange({ currentHp: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Max HP</span>
                <input
                  type="number"
                  min="0"
                  value={npcSeedDraft.maxHp}
                  onChange={(event) => onNpcSeedDraftChange({ maxHp: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Temp HP</span>
                <input
                  type="number"
                  min="0"
                  value={npcSeedDraft.tempHp}
                  onChange={(event) => onNpcSeedDraftChange({ tempHp: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Movement</span>
                <input
                  type="number"
                  min="0"
                  value={npcSeedDraft.movementTotal}
                  onChange={(event) => onNpcSeedDraftChange({ movementTotal: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Priority</span>
                <input
                  type="number"
                  min="1"
                  value={npcSeedDraft.initiativePriority}
                  onChange={(event) => onNpcSeedDraftChange({ initiativePriority: event.currentTarget.value })}
                />
              </label>
              <button type="submit" disabled={isAddingNpc}>
                {isAddingNpc ? "Adding..." : "Add NPC combatant"}
              </button>
            </form>
          </div>
        </div>
      </section>

      <section className="card combat-control-card">
        <h2>Encounter cleanup</h2>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={confirmClearTracker}
            onChange={(event) => onConfirmClearTrackerChange(event.currentTarget.checked)}
          />
          Confirm clear tracker
        </label>
        <button
          type="button"
          className="ghost-button"
          onClick={onClearCombat}
          disabled={!confirmClearTracker || isClearingCombat}
          aria-describedby={clearTrackerHint ? "combat-clear-tracker-hint" : undefined}
        >
          {isClearingCombat ? "Clearing..." : "Clear tracker"}
        </button>
        {clearTrackerHint ? (
          <p id="combat-clear-tracker-hint" className="meta">
            {clearTrackerHint}
          </p>
        ) : null}
      </section>
    </section>
  );
}
