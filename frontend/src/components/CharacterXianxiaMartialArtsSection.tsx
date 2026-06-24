import type { CharacterPresentedXianxia } from "../api/types";
import {
  asRecord,
  asRecordArray,
  boolFromUnknown,
  numberFromUnknown,
  readString,
  stringFromUnknown,
} from "../characterValueUtils";
import { draftKey, joinDisplay } from "../characterPaneUtils";

export function CharacterXianxiaMartialArtsSection({
  martialArts,
}: {
  martialArts: CharacterPresentedXianxia["martial_arts"];
}) {
  const records = asRecordArray(martialArts);

  return (
    <section className="read-section" id="xianxia-martial-arts">
      <div className="section-heading">
        <h2>Martial Arts</h2>
      </div>
      {records.length ? (
        <div className="feature-groups">
          <section className="feature-group">
            <div className="feature-stack">
              {records.map((rawArt, artIndex) => {
                const art = asRecord(rawArt);
                const rankProgress = asRecord(art.rank_progress);
                const rankProgressSteps = asRecordArray(rankProgress.steps);
                const learnedRanks = asRecordArray(art.learned_rank_refs);
                const rankProgressSummary = readString(rankProgress.summary);
                const rankProgressIncompleteNote = readString(rankProgress.incomplete_note);
                const hasRankProgress = Boolean(
                  rankProgressSummary || rankProgressIncompleteNote || rankProgressSteps.length,
                );
                const bodyHtml = readString(art.body_html);
                const artHref = readString(art.href);
                return (
                  <article
                    className="feature-row"
                    key={draftKey(readString(art.name, "Martial Art"), stringFromUnknown(art.key), artIndex)}
                  >
                    <div className="feature-row__header">
                      <h3>
                        {artHref ? (
                          <a href={artHref}>{readString(art.name, "Martial Art")}</a>
                        ) : (
                          readString(art.name, "Martial Art")
                        )}
                      </h3>
                      <p className="meta">
                        {joinDisplay([
                          readString(art.current_rank) ? `Current rank: ${readString(art.current_rank)}` : "Rank not recorded",
                          boolFromUnknown(art.starting_package) ? "Starting package" : "",
                          boolFromUnknown(art.custom) ? "Custom Martial Art" : "",
                        ])}
                      </p>
                    </div>
                    {bodyHtml ? (
                      <div className="detail-cluster">
                        <details className="detail-card">
                          <summary>Martial Art details</summary>
                          <article dangerouslySetInnerHTML={{ __html: bodyHtml }} />
                        </details>
                      </div>
                    ) : null}
                    {hasRankProgress ? (
                      <div className="detail-cluster">
                        <div>
                          <h4>Rank progress</h4>
                          {rankProgressSummary ? <p className="meta">{rankProgressSummary}</p> : null}
                          {rankProgressIncompleteNote ? (
                            <p className="meta">
                              <strong>Intentional draft content:</strong> {rankProgressIncompleteNote}
                            </p>
                          ) : null}
                          {rankProgressSteps.length ? (
                            <div className="skill-grid">
                              {rankProgressSteps.map((rawStep) => {
                                const step = asRecord(rawStep);
                                const stepHref = readString(step.href);
                                return (
                                  <div
                                    className={boolFromUnknown(step.is_learned) ? "skill-pill skill-pill--proficient" : "skill-pill"}
                                    key={readString(step.key, readString(step.label))}
                                  >
                                    {stepHref ? (
                                      <a href={stepHref}>{readString(step.label, "Rank step")}</a>
                                    ) : (
                                      <span>{readString(step.label, "Rank step")}</span>
                                    )}
                                    <span className="meta">{readString(step.status_label)}</span>
                                  </div>
                                );
                              })}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    ) : null}
                    {learnedRanks.length ? (
                      <div className="detail-cluster">
                        <details className="detail-card">
                          <summary>Learned rank abilities</summary>
                          <div className="feature-stack">
                            <div className="detail-cluster">
                              <p>
                                <strong>Learned ranks</strong>
                              </p>
                              <div className="skill-grid">
                                {learnedRanks.map((rawRank, rankIndex) => {
                                  const rank = asRecord(rawRank);
                                  const rankHref = readString(rank.href);
                                  return (
                                    <div
                                      className={!boolFromUnknown(rank.is_incomplete) ? "skill-pill skill-pill--proficient" : "skill-pill"}
                                      key={draftKey(readString(rank.key, readString(rank.label)), rankIndex)}
                                    >
                                      {rankHref ? (
                                        <a href={rankHref}>{readString(rank.label, "Learned rank")}</a>
                                      ) : (
                                        <span>{readString(rank.label, "Learned rank")}</span>
                                      )}
                                      <span className="meta">{readString(rank.status_label)}</span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                            {learnedRanks.map((rawRank, rankIndex) => {
                              const rank = asRecord(rawRank);
                              const rankAbilities = asRecordArray(rank.abilities);
                              const rankLabel = readString(rank.label, "Rank");
                              const rankInsightCost = numberFromUnknown(rank.insight_cost);
                              if (!rankAbilities.length) {
                                return null;
                              }
                              return (
                                <div className="detail-cluster" key={draftKey(readString(rank.key), rankLabel, rankIndex)}>
                                  <p>
                                    <strong>{`${rankLabel} Rank`}</strong>
                                  </p>
                                  <ul className="plain-list">
                                    {readString(rank.energy_bonus_text) ? (
                                      <li className="meta">{`Energy bonuses: ${readString(rank.energy_bonus_text)}`}</li>
                                    ) : null}
                                    {rankInsightCost ? <li className="meta">{`Insight cost: ${rankInsightCost}`}</li> : null}
                                    {readString(rank.prerequisite_text) ? (
                                      <li className="meta">{`Prerequisite: ${readString(rank.prerequisite_text)}`}</li>
                                    ) : null}
                                    {readString(rank.teacher_breakthrough_note) ? (
                                      <li className="meta">{`Teacher/breakthrough: ${readString(rank.teacher_breakthrough_note)}`}</li>
                                    ) : null}
                                    {readString(rank.legendary_prerequisite_note) ? (
                                      <li className="meta">{`Legendary prerequisite: ${readString(rank.legendary_prerequisite_note)}`}</li>
                                    ) : null}
                                  </ul>
                                  <p>
                                    <strong>{`${rankLabel} abilities`}</strong>
                                  </p>
                                  {rankAbilities.map((rawAbility) => {
                                    const ability = asRecord(rawAbility);
                                    const abilityHref = readString(ability.href);
                                    const abilityText = readString(ability.text);
                                    return (
                                      <details className="feature-detail" key={draftKey(readString(ability.key), readString(ability.name))}>
                                        <summary>
                                          <div className="feature-row__header">
                                            <h4>
                                              {abilityHref ? (
                                                <a href={abilityHref}>{readString(ability.name, "Ability")}</a>
                                              ) : (
                                                readString(ability.name, "Ability")
                                              )}
                                            </h4>
                                            <p className="meta">
                                              {joinDisplay([
                                                readString(ability.rank_label) ? `Rank: ${readString(ability.rank_label)}` : "",
                                                readString(ability.kind) ? `Kind: ${readString(ability.kind)}` : "",
                                                readString(ability.support_label) ? `Support: ${readString(ability.support_label)}` : "",
                                              ])}
                                            </p>
                                          </div>
                                        </summary>
                                        <article>
                                          {readString(ability.resource_cost_text) ? (
                                            <p className="meta">
                                              <strong>Costs:</strong> {readString(ability.resource_cost_text)}
                                            </p>
                                          ) : null}
                                          {readString(ability.range_text) ? (
                                            <p className="meta">
                                              <strong>Range:</strong> {readString(ability.range_text)}
                                            </p>
                                          ) : null}
                                          {readString(ability.damage_effort_text) ? (
                                            <p className="meta">
                                              <strong>Damage/Effort:</strong> {readString(ability.damage_effort_text)}
                                            </p>
                                          ) : null}
                                          {readString(ability.duration_text) ? (
                                            <p className="meta">
                                              <strong>Duration:</strong> {readString(ability.duration_text)}
                                            </p>
                                          ) : null}
                                          {abilityText ? (
                                            <div className="article-body article-body--compact">
                                              <p>{abilityText}</p>
                                            </div>
                                          ) : null}
                                          {boolFromUnknown(ability.is_incomplete_rank) ? (
                                            <p className="meta">
                                              <strong>Incomplete draft:</strong>
                                              {readString(ability.incomplete_rank_status)}
                                              {readString(ability.incomplete_rank_status) && readString(ability.incomplete_rank_note) ? " - " : ""}
                                              {readString(ability.incomplete_rank_note)}
                                            </p>
                                          ) : null}
                                        </article>
                                      </details>
                                    );
                                  })}
                                </div>
                              );
                            })}
                          </div>
                        </details>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      ) : (
        <article className="detail-card">
          <p className="meta">No Martial Arts are recorded on this sheet yet.</p>
        </article>
      )}
    </section>
  );
}
