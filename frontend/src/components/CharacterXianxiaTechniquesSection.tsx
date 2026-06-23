import { Fragment } from "react";
import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { CharacterPresentedXianxia, CharacterXianxiaNamedRecord } from "../api/types";
import type { CharacterXianxiaDaoUseRequestDraft } from "../characterPaneDrafts";
import {
  asRecord,
  asRecordArray,
  boolFromUnknown,
  readNumber,
  readString,
} from "../characterValueUtils";
import {
  asCharacterXianxiaNamedRecord,
  draftKey,
  joinDisplay,
  xianxiaDaoUseRecordDraftKey,
} from "../characterPaneUtils";

function renderXianxiaRecordBody(record: unknown): string {
  const source = asRecord(record);
  return readString(source.body_html, readString(source.description_html));
}

function renderXianxiaRecordHtml(record: unknown) {
  const bodyHtml = renderXianxiaRecordBody(record);
  if (!bodyHtml) {
    return null;
  }
  return <div className="article-body article-body--compact" dangerouslySetInnerHTML={{ __html: bodyHtml }} />;
}

export function CharacterXianxiaTechniquesSection({
  approval,
  basicActions,
  canEdit,
  canRecordXianxiaDaoUse,
  genericTechniques,
  isDaoUseRecordSaving,
  isDaoUseRequestSaving,
  setXianxiaDaoRequestDraft,
  setXianxiaDaoUseNotesDrafts,
  submitXianxiaDaoUseRecord,
  submitXianxiaDaoUseRequest,
  xianxiaDaoRequestDraft,
  xianxiaDaoUseNotesDrafts,
  xianxiaInsight,
}: {
  approval: CharacterPresentedXianxia["approval"];
  basicActions: CharacterPresentedXianxia["basic_actions"];
  canEdit: boolean;
  canRecordXianxiaDaoUse: boolean;
  genericTechniques: CharacterPresentedXianxia["generic_techniques"];
  isDaoUseRecordSaving: boolean;
  isDaoUseRequestSaving: boolean;
  setXianxiaDaoRequestDraft: Dispatch<SetStateAction<CharacterXianxiaDaoUseRequestDraft>>;
  setXianxiaDaoUseNotesDrafts: Dispatch<SetStateAction<Record<string, string>>>;
  submitXianxiaDaoUseRecord: (event: FormEvent<HTMLFormElement>, record: CharacterXianxiaNamedRecord) => void;
  submitXianxiaDaoUseRequest: (event: FormEvent<HTMLFormElement>) => void;
  xianxiaDaoRequestDraft: CharacterXianxiaDaoUseRequestDraft;
  xianxiaDaoUseNotesDrafts: Record<string, string>;
  xianxiaInsight?: { available: number; spent: number };
}) {
  const preparedRecords = asRecordArray(approval?.dao_immolating_prepared);

  return (
    <section className="read-section" id="xianxia-techniques">
      <div className="section-heading">
        <h2>Techniques</h2>
      </div>
      <div className="detail-grid">
        <article className="detail-card">
          <h3>Known Generic Techniques</h3>
          {asRecordArray(genericTechniques).length ? (
            <ul className="plain-list slot-list">
              {asRecordArray(genericTechniques).map((data, index) => {
                const techniqueName = readString(data.name, "Unnamed technique");
                const techniqueHref = readString(data.href);
                const techniqueBody = renderXianxiaRecordBody(data);
                const supportLabel = readString(data.support_label);
                const insightCost = readNumber(data.insight_cost);
                const prerequisites = readString(data.prerequisites);
                const resourceCosts = readString(data.resource_costs);
                const rangeTags = readString(data.range_tags);
                const effortTags = readString(data.effort_tags);
                const resetCadence = readString(data.reset_cadence);
                const learnableWithoutMaster = boolFromUnknown(data.learnable_without_master);
                const requiresMaster = boolFromUnknown(data.requires_master);
                const metaLine = [
                  rangeTags ? `Range: ${rangeTags}` : "",
                  effortTags ? `Effort: ${effortTags}` : "",
                  resetCadence ? `Reset: ${resetCadence}` : "",
                ]
                  .filter(Boolean)
                  .join(" | ");

                const detailsKey = draftKey("xianxia-generic-technique", techniqueName, techniqueHref);
                return (
                  <Fragment key={`${detailsKey}-${index}`}>
                    <li>
                      {techniqueHref ? <a href={techniqueHref}>{techniqueName}</a> : <span>{techniqueName}</span>}
                      {supportLabel ? <strong>{supportLabel}</strong> : null}
                      {insightCost ? <span className="meta">Insight {insightCost}</span> : null}
                    </li>
                    {techniqueBody ? (
                      <li>
                        <details className="detail-card">
                          <summary>Technique details</summary>
                          <article>{renderXianxiaRecordHtml(data)}</article>
                        </details>
                      </li>
                    ) : null}
                    {prerequisites ? <li className="meta">Prerequisites: {prerequisites}</li> : null}
                    {resourceCosts ? <li className="meta">Resource Costs: {resourceCosts}</li> : null}
                    {metaLine ? <li className="meta">{metaLine}</li> : null}
                    {learnableWithoutMaster || requiresMaster ? (
                      <li className="meta">
                        {learnableWithoutMaster ? "Learnable without a Master" : requiresMaster ? "Master required" : null}
                      </li>
                    ) : null}
                  </Fragment>
                );
              })}
            </ul>
          ) : (
            <p className="meta">No Generic Techniques are recorded on this sheet yet.</p>
          )}
        </article>
        <article className="detail-card">
          <h3>Basic Actions</h3>
          {asRecordArray(basicActions).length ? (
            <ul className="plain-list slot-list">
              {asRecordArray(basicActions).map((data, index) => {
                const actionName = readString(data.title, readString(data.name, "Unnamed action"));
                const actionHref = readString(data.href);
                const supportLabel = readString(data.support_label);
                const actionBody = renderXianxiaRecordBody(data);
                const rangeTags = readString(data.range_tags);
                const timingTags = readString(data.timing_tags);
                const metaLine = [rangeTags ? `Range: ${rangeTags}` : "", timingTags ? `Timing: ${timingTags}` : ""]
                  .filter(Boolean)
                  .join(" | ");
                const detailKey = draftKey("xianxia-basic-action", actionName, actionHref);

                return (
                  <Fragment key={`${detailKey}-${index}`}>
                    <li>
                      {actionHref ? <a href={actionHref}>{actionName}</a> : <span>{actionName}</span>}
                      {supportLabel ? <strong>{supportLabel}</strong> : null}
                    </li>
                    {actionBody ? (
                      <li>
                        <details className="detail-card">
                          <summary>Action details</summary>
                          <article>{renderXianxiaRecordHtml(data)}</article>
                        </details>
                      </li>
                    ) : null}
                    {metaLine ? <li className="meta">{metaLine}</li> : null}
                  </Fragment>
                );
              })}
            </ul>
          ) : (
            <p className="meta">No Basic Action Systems entries are available for this campaign.</p>
          )}
        </article>
        {asRecordArray(approval?.status_groups).map((group, groupIndex) => {
          const groupKey = readString(group.key);
          const groupTitle = readString(group.title, "Approval records");
          const groupId = groupKey ? `xianxia-approval-${groupKey.replace(/_/g, "-")}` : undefined;
          const approvalRecords = asRecordArray(group.records);
          const isDaoImmolatingUseRecords = groupKey === "dao_immolating_use_records";
          const canRecordThisDaoUse =
            isDaoImmolatingUseRecords &&
            canRecordXianxiaDaoUse &&
            approvalRecords.some(
              (record) =>
                readString(record.status_key) === "approved" &&
                !boolFromUnknown(record.used) &&
                record.use_record_index !== undefined,
            );

          return (
            <article className="detail-card" key={groupKey || draftKey("xianxia-approval-group", groupIndex)} id={groupId}>
              <h3>{groupTitle}</h3>
              {approvalRecords.length ? (
                <ul className="plain-list slot-list">
                  {approvalRecords.map((record, recordIndex) => {
                    const data = asCharacterXianxiaNamedRecord(record);
                    const recordName = readString(data.name, "Unnamed record");
                    const statusLabel = readString(data.status_label, readString(data.status, "Unknown"));
                    const statusKey = readString(data.status_key, "unknown");
                    const typeLabel = readString(data.type_label, readString(data.type));
                    const sourceLabel = readString(data.source_label);
                    const approvalTimestamp = readString(data.approval_timestamp);
                    const notes = readString(data.notes);
                    const baseAbilityRef = readString(data.base_ability_ref);
                    const baseAbilityKind = readString(data.base_ability_kind);
                    const techniqueAnchor = readString(data.technique_anchor_label);
                    const techniqueAnchorWarning = readString(data.technique_anchor_warning);
                    const insightCost = isDaoImmolatingUseRecords
                      ? readNumber(data.insight_cost, 10)
                      : readNumber(data.insight_cost);
                    const preparedRecordName = readString(data.prepared_record_name);
                    const preparedRecordIndex = readNumber(data.prepared_record_index, 0);
                    const preparedRecordNotes = readString(data.prepared_record_notes);
                    const oneUseUsed = boolFromUnknown(data.used);
                    const insightSpent = readNumber(data.insight_spent);
                    const useRecordDraftKey = xianxiaDaoUseRecordDraftKey(data);
                    const useNotes = xianxiaDaoUseNotesDrafts[useRecordDraftKey] ?? "";
                    const spendDisabled = insightCost > (xianxiaInsight?.available ?? 0);
                    const canRecordThisRecord =
                      isDaoImmolatingUseRecords &&
                      canRecordThisDaoUse &&
                      readString(data.status_key) === "approved" &&
                      !boolFromUnknown(data.used) &&
                      data.use_record_index !== undefined;

                    return (
                      <Fragment key={`${groupKey ?? "approval"}-${recordName}-${data.use_record_index ?? recordIndex}-${recordIndex}`}>
                        <li className="approval-record__heading">
                          <span>{recordName}</span>
                          <span className={`meta-badge approval-state-badge approval-state-badge--${statusKey}`}>
                            Approval state: {statusLabel}
                          </span>
                        </li>
                        {(typeLabel || sourceLabel) ? <li className="meta">{joinDisplay([typeLabel, sourceLabel])}</li> : null}
                        {notes ? <li className="meta">{notes}</li> : null}
                        {approvalTimestamp ? <li className="meta">Approval timestamp: {approvalTimestamp}</li> : null}
                        {groupKey && ["karmic_constraints", "ascendant_arts"].includes(groupKey) ? (
                          <>
                            {baseAbilityRef ? <li className="meta">Base ability ref: {baseAbilityRef}</li> : null}
                            {baseAbilityKind ? <li className="meta">Base ability kind: {baseAbilityKind}</li> : null}
                            {techniqueAnchor ? <li className="meta">Technique anchor: {techniqueAnchor}</li> : null}
                            {techniqueAnchorWarning ? <li className="meta">{techniqueAnchorWarning}</li> : null}
                          </>
                        ) : null}
                        {isDaoImmolatingUseRecords ? (
                          <>
                            <li className="meta">Insight cost: {insightCost}</li>
                            {(preparedRecordName || preparedRecordNotes || data.prepared_record_index !== undefined) ? (
                              <li className="meta">
                                Prepared support: {preparedRecordName || `Prepared note #${preparedRecordIndex + 1}`}
                              </li>
                            ) : null}
                            {preparedRecordNotes ? <li className="meta">{preparedRecordNotes}</li> : null}
                            {oneUseUsed ? (
                              <li className="meta">One-use history: used; Insight spent {insightSpent}</li>
                            ) : (
                              <li className="meta">One-use history: not recorded yet</li>
                            )}
                            {data.use_notes && oneUseUsed ? <li className="meta">{data.use_notes}</li> : null}
                            {canRecordThisRecord ? (
                              <li>
                                <form
                                  onSubmit={(event) => submitXianxiaDaoUseRecord(event, data)}
                                  className="session-vitals-form"
                                >
                                  <label htmlFor={`xianxia-dao-use-notes-${useRecordDraftKey}`} className="session-field">
                                    <span>Use notes</span>
                                    <textarea
                                      id={`xianxia-dao-use-notes-${useRecordDraftKey}`}
                                      rows={2}
                                      value={useNotes}
                                      onChange={(event) =>
                                        setXianxiaDaoUseNotesDrafts({
                                          ...xianxiaDaoUseNotesDrafts,
                                          [useRecordDraftKey]: event.currentTarget.value,
                                        })
                                      }
                                    />
                                  </label>
                                  {spendDisabled ? <p className="meta">Needs {insightCost} Insight.</p> : null}
                                  <button type="submit" className="button-link" disabled={isDaoUseRecordSaving || spendDisabled}>
                                    {isDaoUseRecordSaving ? "Saving..." : "Record one-use spend"}
                                  </button>
                                </form>
                              </li>
                            ) : null}
                          </>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </ul>
              ) : (
                <p className="meta">{readString(group.empty_message)}</p>
              )}
            </article>
          );
        })}
        <article className="detail-card">
          <h3>Prepared Dao Immolating Techniques</h3>
          {preparedRecords.length ? (
            <ul className="plain-list slot-list">
              {preparedRecords.map((data, index) => {
                const recordName = readString(data.name, `Prepared note ${index + 1}`);
                const supportLabel = readString(data.status, readString(data.type));
                return (
                  <Fragment key={`xianxia-dao-immolating-prepared-${recordName}-${index}`}>
                    <li>
                      <span>{recordName}</span>
                      {supportLabel ? <strong>{supportLabel}</strong> : null}
                    </li>
                    {readString(data.notes) ? <li className="meta">{readString(data.notes)}</li> : null}
                  </Fragment>
                );
              })}
            </ul>
          ) : (
            <p className="meta">No prepared Dao Immolating Technique notes yet.</p>
          )}
        </article>
        {canEdit ? (
          <article className="detail-card" id="xianxia-dao-immolating-use-request">
            <h3>Ad Hoc Dao Immolating Use Request</h3>
            <form onSubmit={submitXianxiaDaoUseRequest} className="session-vitals-form">
              <label className="session-field" htmlFor="xianxia-dao-request-name">
                <span>Request name</span>
                <input
                  id="xianxia-dao-request-name"
                  value={xianxiaDaoRequestDraft.requestName}
                  required={!(preparedRecords.length > 0)}
                  disabled={isDaoUseRequestSaving}
                  onChange={(event) =>
                    setXianxiaDaoRequestDraft({
                      ...xianxiaDaoRequestDraft,
                      requestName: event.currentTarget.value,
                    })
                  }
                />
              </label>
              {preparedRecords.length ? (
                <>
                  <label className="session-field" htmlFor="xianxia-dao-prepared-record">
                    <span>Prepared note</span>
                    <select
                      id="xianxia-dao-prepared-record"
                      value={xianxiaDaoRequestDraft.preparedRecordIndex}
                      disabled={isDaoUseRequestSaving}
                      onChange={(event) =>
                        setXianxiaDaoRequestDraft({
                          ...xianxiaDaoRequestDraft,
                          preparedRecordIndex: event.currentTarget.value,
                        })
                      }
                    >
                      <option value="">No prepared note</option>
                      {preparedRecords.map((record, index) => {
                        const preparedRecordName = readString(record.name, `Prepared note ${index + 1}`);
                        return (
                          <option key={draftKey(preparedRecordName, index)} value={String(index)}>
                            {preparedRecordName}
                          </option>
                        );
                      })}
                    </select>
                  </label>
                </>
              ) : null}
              <label className="session-field" htmlFor="xianxia-dao-request-notes">
                <span>Request notes</span>
                <textarea
                  id="xianxia-dao-request-notes"
                  rows={3}
                  value={xianxiaDaoRequestDraft.notes}
                  disabled={isDaoUseRequestSaving}
                  onChange={(event) =>
                    setXianxiaDaoRequestDraft({
                      ...xianxiaDaoRequestDraft,
                      notes: event.currentTarget.value,
                    })
                  }
                />
              </label>
              <button type="submit" className="button-link" disabled={isDaoUseRequestSaving}>
                {isDaoUseRequestSaving ? "Saving..." : "Record use request"}
              </button>
            </form>
          </article>
        ) : null}
      </div>
    </section>
  );
}
