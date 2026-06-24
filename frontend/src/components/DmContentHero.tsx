import type { DmContentLane } from "../dmContentUtils";

export type DmContentLaneCounts = {
  statblocks: number;
  stagedArticles: number;
  conditions: number;
  playerWiki: number;
  systems: number;
};

export function DmContentHero({
  activeLane,
  encodedCampaignSlug,
  laneCounts,
  lede,
}: {
  activeLane: DmContentLane;
  encodedCampaignSlug: string;
  laneCounts: DmContentLaneCounts;
  lede: string;
}) {
  return (
    <section className="hero compact dm-content-hero">
      <p className="eyebrow">DM content</p>
      <h1>DM Content</h1>
      <p className="lede">{lede}</p>
      <nav className="character-subpage-nav dm-content-subpage-nav" aria-label="DM Content subpages">
        <a
          className={activeLane === "statblocks" ? "button-link" : "ghost-button"}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content`}
        >
          <span>Statblocks</span>
          <span className="meta-badge">{laneCounts.statblocks}</span>
        </a>
        <a
          className={activeLane === "staged-articles" ? "button-link" : "ghost-button"}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=staged-articles`}
        >
          <span>Staged Articles</span>
          <span className="meta-badge">{laneCounts.stagedArticles}</span>
        </a>
        <a
          className={activeLane === "conditions" ? "button-link" : "ghost-button"}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=conditions`}
        >
          <span>Conditions</span>
          <span className="meta-badge">{laneCounts.conditions}</span>
        </a>
        <a
          className={activeLane === "player-wiki" ? "button-link" : "ghost-button"}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=player-wiki`}
        >
          <span>Player Wiki</span>
          <span className="meta-badge">{laneCounts.playerWiki}</span>
        </a>
        <a
          className={activeLane === "systems" ? "button-link" : "ghost-button"}
          href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=systems`}
        >
          <span>Systems</span>
          <span className="meta-badge">{laneCounts.systems}</span>
        </a>
      </nav>
    </section>
  );
}
