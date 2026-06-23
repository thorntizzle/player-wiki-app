import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { CharacterXianxiaPool } from "../api/types";
import type { CharacterXianxiaActiveStateDraft } from "../characterPaneDrafts";
import { readNumber } from "../characterValueUtils";

function renderXianxiaPoolCards(
  pools: CharacterXianxiaPool[],
  options?: {
    className?: string;
    keyPrefix?: string;
  },
) {
  return pools.map((pool) => (
    <article className={options?.className ?? "resource-card"} key={options?.keyPrefix ? `${options.keyPrefix}-${pool.key}` : pool.key}>
      <h3>{pool.label}</h3>
      <p className="resource-card__value">
        Current {pool.current} / Max {pool.max}
      </p>
      {pool.temp ? <p className="meta">Temporary {pool.label}: {pool.temp}</p> : null}
    </article>
  ));
}

export function CharacterXianxiaResourcesSection({
  activeStateStatus,
  canEdit,
  durability,
  energies,
  insight,
  isActiveStateSaving,
  setXianxiaActiveDraft,
  submitXianxiaActiveState,
  xianxiaActiveDraft,
  xianxiaDao,
  yinYang,
}: {
  activeStateStatus: string;
  canEdit: boolean;
  durability: CharacterXianxiaPool[];
  energies: CharacterXianxiaPool[];
  insight?: { available: number; spent: number };
  isActiveStateSaving: boolean;
  setXianxiaActiveDraft: Dispatch<SetStateAction<CharacterXianxiaActiveStateDraft>>;
  submitXianxiaActiveState: (event: FormEvent<HTMLFormElement>) => void;
  xianxiaActiveDraft: CharacterXianxiaActiveStateDraft;
  xianxiaDao?: { current: number; max: number };
  yinYang: CharacterXianxiaPool[];
}) {
  return (
    <section className="read-section" id="xianxia-resources">
      <div className="section-heading">
        <h2>Resources</h2>
      </div>
      <div className="resource-grid">
        {durability.length ? renderXianxiaPoolCards(durability, { keyPrefix: "durability" }) : null}
        {energies.length ? renderXianxiaPoolCards(energies, { keyPrefix: "energies" }) : null}
        {yinYang.length ? renderXianxiaPoolCards(yinYang, { keyPrefix: "yin-yang" }) : null}
        {xianxiaDao ? (
          <article className="resource-card">
            <h3>Dao</h3>
            <p className="resource-card__value">
              Current {xianxiaDao.current} / Max {xianxiaDao.max}
            </p>
          </article>
        ) : null}
        {insight ? (
          <article className="resource-card">
            <h3>Insight</h3>
            <p className="resource-card__value">{readNumber(insight.available, 0)}</p>
            <p className="meta">Spent {readNumber(insight.spent, 0)}</p>
          </article>
        ) : null}
      </div>
      <article className="detail-card" id="session-active-state">
        <div className="section-heading">
          <h3>Active Stance and Aura</h3>
          {activeStateStatus ? <p className="meta">{activeStateStatus}</p> : null}
        </div>
        <form onSubmit={submitXianxiaActiveState} className="session-vitals-form">
          <label className="session-field" htmlFor="xianxia-active-stance">
            <span>Active Stance</span>
            <input
              id="xianxia-active-stance"
              value={xianxiaActiveDraft.activeStanceName}
              disabled={!canEdit}
              onChange={(event) => setXianxiaActiveDraft({ ...xianxiaActiveDraft, activeStanceName: event.currentTarget.value })}
            />
          </label>
          <label className="session-field" htmlFor="xianxia-active-aura">
            <span>Active Aura</span>
            <input
              id="xianxia-active-aura"
              value={xianxiaActiveDraft.activeAuraName}
              disabled={!canEdit}
              onChange={(event) => setXianxiaActiveDraft({ ...xianxiaActiveDraft, activeAuraName: event.currentTarget.value })}
            />
          </label>
          <button type="submit" className="button-link" disabled={isActiveStateSaving || !canEdit}>
            {isActiveStateSaving ? "Saving..." : "Save Active Stance and Aura"}
          </button>
        </form>
      </article>
    </section>
  );
}
