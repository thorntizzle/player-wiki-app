import React from "react";

import type { CharacterCultivationContext } from "../api/types";
import {
  boolFromUnknown,
  numberFromUnknown,
  recordFromUnknown,
  recordListFromUnknown,
  stringFromUnknown,
} from "../characterValueUtils";

export type RenderCultivationActionForm = (
  action: string,
  buttonLabel: string,
  children: React.ReactNode,
  options?: { disabled?: boolean },
) => React.ReactNode;

function CultivationHistoryRecords({ records }: { records: Array<Record<string, unknown>> }) {
  return records.length ? (
    <div className="feature-stack">
      {records.map((record, index) => (
        <article className="feature-row" key={`${stringFromUnknown(record.action, "record")}-${index}`}>
          <div className="feature-row__header">
            <h3>{stringFromUnknown(record.action || record.status || "Record").replace(/_/g, " ")}</h3>
            {record.target_realm ? <p className="meta">Target {stringFromUnknown(record.target_realm)}</p> : null}
          </div>
          <ul className="plain-list slot-list">
            {Object.entries(record)
              .filter(([key, value]) => {
                if (["snapshot", "pre_ascension_snapshot", "post_ascension_snapshot"].includes(key)) {
                  return false;
                }
                return value !== null && value !== undefined && String(value).trim() !== "";
              })
              .slice(0, 12)
              .map(([key, value]) => (
                <li key={key}>
                  <strong>{key.replace(/_/g, " ")}:</strong> {stringFromUnknown(value)}
                </li>
              ))}
          </ul>
        </article>
      ))}
    </div>
  ) : null;
}

export function CharacterCultivationRealmAscension({
  context,
  renderActionForm,
}: {
  context: CharacterCultivationContext;
  renderActionForm: RenderCultivationActionForm;
}) {
  const ascension = recordFromUnknown(context.realm_ascension);
  const target = recordFromUnknown(ascension.target);
  const statPrerequisite = recordFromUnknown(ascension.stat_prerequisite);
  const attributes = recordFromUnknown(ascension.attributes);
  const efforts = recordFromUnknown(ascension.efforts);
  const attributeRows = recordListFromUnknown(attributes.rows);
  const effortRows = recordListFromUnknown(efforts.rows);
  const trade = recordFromUnknown(ascension.hp_stance_trade);
  const pendingConfirmation = recordFromUnknown(ascension.pending_confirmation_rebuild);
  const targetRealm = stringFromUnknown(target.target_realm || pendingConfirmation.target_realm);
  const rebuildAction = targetRealm === "Divine" ? "apply_divine_realm_rebuild" : "apply_immortal_realm_rebuild";

  return (
    <section className="read-section" id="xianxia-cultivation-realm-ascension">
      <div className="section-heading">
        <h2>Realm Ascension</h2>
      </div>
      <div className="glance-grid">
        <div className="glance-card">
          <span className="meta">Current Realm</span>
          <strong>{stringFromUnknown(ascension.current_realm, "Unknown")}</strong>
        </div>
        {boolFromUnknown(ascension.available) ? (
          <>
            <div className="glance-card">
              <span className="meta">Target Realm</span>
              <strong>{stringFromUnknown(target.target_realm)}</strong>
            </div>
            <div className="glance-card">
              <span className="meta">Seclusion</span>
              <strong>{stringFromUnknown(target.seclusion_time)}</strong>
            </div>
            <div className="glance-card">
              <span className="meta">Rebuild</span>
              <strong>{numberFromUnknown(target.rebuild_budget)} points</strong>
              <span className="meta">Max {numberFromUnknown(target.stat_cap)} per Stat</span>
            </div>
            <div className="glance-card">
              <span className="meta">Stat prerequisite</span>
              <strong>{boolFromUnknown(statPrerequisite.is_met) ? "Met" : "Not met"}</strong>
              <span className="meta">{stringFromUnknown(statPrerequisite.requirement_text)}</span>
            </div>
          </>
        ) : (
          <div className="glance-card">
            <span className="meta">Target Realm</span>
            <strong>None</strong>
          </div>
        )}
      </div>
      <article className="detail-card">
        <div className="detail-grid">
          <div>
            <h3>Attributes</h3>
            <p className="meta">Current total {numberFromUnknown(attributes.total)}</p>
            <ul className="plain-list slot-list">
              {attributeRows.map((stat) => (
                <li key={stringFromUnknown(stat.key || stat.label)}>
                  <strong>{stringFromUnknown(stat.label)}:</strong> {numberFromUnknown(stat.score)}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3>Efforts</h3>
            <p className="meta">Current total {numberFromUnknown(efforts.total)}</p>
            <ul className="plain-list slot-list">
              {effortRows.map((stat) => (
                <li key={stringFromUnknown(stat.key || stat.label)}>
                  <strong>{stringFromUnknown(stat.label)}:</strong> {numberFromUnknown(stat.score)}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </article>
      {boolFromUnknown(ascension.available) ? (
        <article className="detail-card session-card">
          {!boolFromUnknown(ascension.can_start_review) ? (
            <p className="meta">
              {stringFromUnknown(ascension.confirmation_blocking_message || statPrerequisite.failure_message)}
            </p>
          ) : null}
          {renderActionForm(
            "start_realm_ascension_review",
            "Start Realm Review",
            <>
              <input type="hidden" name="target_realm" value={stringFromUnknown(target.target_realm)} />
              <label className="field">
                <span>GM review note</span>
                <textarea name="realm_ascension_gm_review_note" rows={3} required />
              </label>
              <label className="field">
                <span>Seclusion notes</span>
                <textarea name="realm_ascension_seclusion_notes" rows={2} />
              </label>
              <label className="field">
                <span>HP/Stance trade notes</span>
                <textarea name="realm_ascension_hp_stance_trade_notes" rows={2} />
              </label>
            </>,
            { disabled: !boolFromUnknown(ascension.can_start_review) },
          )}
        </article>
      ) : (
        <article className="detail-card">
          <p className="meta">{stringFromUnknown(ascension.message)}</p>
        </article>
      )}
      <CultivationHistoryRecords
        records={[
          recordFromUnknown(ascension.latest_review),
          recordFromUnknown(ascension.latest_reset),
          recordFromUnknown(ascension.latest_rebuild),
          recordFromUnknown(ascension.latest_confirmation),
        ].filter((record) => Object.keys(record).length > 0)}
      />
      {boolFromUnknown(ascension.can_reset_stats) ? (
        <article className="detail-card session-card">
          <h3>Reset Rebuild Stats</h3>
          {renderActionForm(
            "reset_realm_ascension_stats",
            "Reset Attributes and Efforts",
            <>
              <input type="hidden" name="target_realm" value={targetRealm} />
              <label className="field">
                <span>Reset notes</span>
                <textarea name="realm_ascension_reset_notes" rows={2} />
              </label>
              <div className="confirmed-action">
                <label className="checkbox-label">
                  <input type="checkbox" name="realm_ascension_reset_confirmed" required />
                  <span>Confirm reset</span>
                </label>
              </div>
            </>,
          )}
        </article>
      ) : null}
      {boolFromUnknown(ascension.can_apply_rebuild) ? (
        <article className="detail-card session-card">
          <h3>Apply {targetRealm} Rebuild</h3>
          {renderActionForm(
            rebuildAction,
            `Apply ${targetRealm} Rebuild`,
            <>
              <input type="hidden" name="target_realm" value={targetRealm} />
              <div className="detail-grid">
                <div>
                  <h4>Attributes</h4>
                  <div className="builder-field-grid">
                    {attributeRows.map((stat) => (
                      <label className="field" key={stringFromUnknown(stat.key)}>
                        <span>{stringFromUnknown(stat.label)}</span>
                        <input
                          type="number"
                          min={0}
                          max={numberFromUnknown(target.stat_cap)}
                          name={`realm_rebuild_attribute_${stringFromUnknown(stat.key)}`}
                          defaultValue={numberFromUnknown(stat.score)}
                          required
                        />
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <h4>Efforts</h4>
                  <div className="builder-field-grid">
                    {effortRows.map((stat) => (
                      <label className="field" key={stringFromUnknown(stat.key)}>
                        <span>{stringFromUnknown(stat.label)}</span>
                        <input
                          type="number"
                          min={0}
                          max={numberFromUnknown(target.stat_cap)}
                          name={`realm_rebuild_effort_${stringFromUnknown(stat.key)}`}
                          defaultValue={numberFromUnknown(stat.score)}
                          required
                        />
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <div className="detail-grid">
                <label className="field">
                  <span>HP maximum traded</span>
                  <input
                    type="number"
                    min={0}
                    max={numberFromUnknown(trade.hp_maximum_trade)}
                    step={numberFromUnknown(trade.unit, 10)}
                    name="realm_ascension_trade_hp"
                    defaultValue={0}
                    disabled={!numberFromUnknown(trade.hp_maximum_trade)}
                  />
                </label>
                <label className="field">
                  <span>Stance maximum traded</span>
                  <input
                    type="number"
                    min={0}
                    max={numberFromUnknown(trade.stance_maximum_trade)}
                    step={numberFromUnknown(trade.unit, 10)}
                    name="realm_ascension_trade_stance"
                    defaultValue={0}
                    disabled={!numberFromUnknown(trade.stance_maximum_trade)}
                  />
                </label>
              </div>
              <label className="field">
                <span>Rebuild notes</span>
                <textarea name="realm_ascension_rebuild_notes" rows={2} />
              </label>
              <div className="confirmed-action">
                <label className="checkbox-label">
                  <input type="checkbox" name="realm_ascension_rebuild_confirmed" required />
                  <span>Confirm rebuild</span>
                </label>
              </div>
            </>,
          )}
        </article>
      ) : null}
      {boolFromUnknown(ascension.can_confirm_rebuild) && Object.keys(pendingConfirmation).length ? (
        <article className="detail-card session-card">
          <h3>Confirm {targetRealm} Ascension</h3>
          {renderActionForm(
            "confirm_realm_ascension",
            "Confirm Realm Ascension",
            <>
              <input type="hidden" name="target_realm" value={targetRealm} />
              <label className="field">
                <span>GM confirmation note</span>
                <textarea name="realm_ascension_gm_confirmation_note" rows={3} required />
              </label>
              <div className="confirmed-action">
                <label className="checkbox-label">
                  <input type="checkbox" name="realm_ascension_final_confirmed" required />
                  <span>Confirm ascension</span>
                </label>
              </div>
            </>,
          )}
        </article>
      ) : null}
    </section>
  );
}
