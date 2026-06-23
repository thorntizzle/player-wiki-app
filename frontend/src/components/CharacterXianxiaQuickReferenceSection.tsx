import type { CharacterPresentedXianxia } from "../api/types";
import { asRecord, asRecordArray, asStringArray, readString, stringFromUnknown } from "../characterValueUtils";

export function CharacterXianxiaQuickReferenceSection({
  hasSkillUseGuardrail,
  hasXianxiaHonorInteractions,
  hasXianxiaStanceBreak,
  presentedXianxia,
  skillUseGuardrailReferenceLines,
  skillUseGuardrailRuleHref,
  skillUseGuardrailRuleTitle,
  xianxiaActionReference,
  xianxiaDefenseReference,
  xianxiaHonorContexts,
  xianxiaHonorInteractions,
  xianxiaHonorReferenceLines,
  xianxiaInsight,
  xianxiaRuleTextReferences,
  xianxiaStanceBreak,
  xianxiaStanceBreakRecoveryLines,
  xianxiaStanceBreakReferenceLines,
}: {
  hasSkillUseGuardrail: boolean;
  hasXianxiaHonorInteractions: boolean;
  hasXianxiaStanceBreak: boolean;
  presentedXianxia: CharacterPresentedXianxia;
  skillUseGuardrailReferenceLines: string[];
  skillUseGuardrailRuleHref: string;
  skillUseGuardrailRuleTitle: string;
  xianxiaActionReference: Record<string, unknown>;
  xianxiaDefenseReference: Record<string, unknown>;
  xianxiaHonorContexts: Record<string, unknown>[];
  xianxiaHonorInteractions: Record<string, unknown>;
  xianxiaHonorReferenceLines: string[];
  xianxiaInsight: NonNullable<CharacterPresentedXianxia["resources"]>["insight"];
  xianxiaRuleTextReferences: Record<string, unknown>[];
  xianxiaStanceBreak: Record<string, unknown>;
  xianxiaStanceBreakRecoveryLines: string[];
  xianxiaStanceBreakReferenceLines: string[];
}) {
  return (
    <section className="read-section" id="xianxia-quick-reference">
      <div className="section-heading">
        <h2>Quick Reference</h2>
      </div>
      <div className="glance-grid">
        <article className="glance-card">
          <span className="meta">Realm</span>
          <strong>{readString(xianxiaActionReference.realm, readString(presentedXianxia.identity?.realm, "--"))}</strong>
        </article>
        <article className="glance-card">
          <span className="meta">Actions per turn</span>
          <strong>
            {readString(
              xianxiaActionReference.actions_per_turn,
              stringFromUnknown(presentedXianxia.identity?.actions_per_turn, "--"),
            )}
          </strong>
        </article>
        <article className="glance-card">
          <span className="meta">Defense</span>
          <strong>
            {stringFromUnknown(
              xianxiaDefenseReference.value,
              stringFromUnknown(presentedXianxia.equipment?.defense, "--"),
            )}
          </strong>
        </article>
        <article className="glance-card">
          <span className="meta">Honor</span>
          <strong>{readString(presentedXianxia.identity?.honor, "--")}</strong>
        </article>
        <article className="glance-card">
          <span className="meta">Reputation</span>
          <strong>{readString(presentedXianxia.identity?.reputation, "--")}</strong>
        </article>
        <article className="glance-card">
          <span className="meta">Insight</span>
          <strong>{xianxiaInsight ? `${xianxiaInsight.available} available / ${xianxiaInsight.spent} spent` : "--"}</strong>
        </article>
      </div>
      <section className="read-section" id="xianxia-action-count">
        <div className="section-heading">
          <h2>Action count</h2>
        </div>
        <div className="glance-grid">
          <article className="glance-card">
            <span className="meta">Realm</span>
            <strong>{readString(xianxiaActionReference.realm, readString(presentedXianxia.identity?.realm, "--"))}</strong>
          </article>
          <article className="glance-card">
            <span className="meta">Actions per turn</span>
            <strong>
              {readString(
                xianxiaActionReference.actions_per_turn,
                stringFromUnknown(presentedXianxia.identity?.actions_per_turn, "--"),
              )}
            </strong>
          </article>
        </div>
        {readString(xianxiaActionReference.formula) ? (
          <p className="meta">Actions per turn = {readString(xianxiaActionReference.formula)}</p>
        ) : null}
      </section>
      <section className="read-section" id="xianxia-defense-derivation">
        <div className="section-heading">
          <h2>Defense calculation</h2>
        </div>
        <div className="glance-grid">
          <article className="glance-card">
            <span className="meta">Base</span>
            <strong>{stringFromUnknown(xianxiaDefenseReference.base, "--")}</strong>
          </article>
          <article className="glance-card">
            <span className="meta">Manual armor bonus</span>
            <strong>{stringFromUnknown(xianxiaDefenseReference.manual_armor_bonus, "--")}</strong>
          </article>
          <article className="glance-card">
            <span className="meta">Constitution</span>
            <strong>{stringFromUnknown(xianxiaDefenseReference.constitution, "--")}</strong>
          </article>
          <article className="glance-card">
            <span className="meta">Defense</span>
            <strong>
              {stringFromUnknown(xianxiaDefenseReference.value, stringFromUnknown(presentedXianxia.equipment?.defense, "--"))}
            </strong>
          </article>
        </div>
        {readString(xianxiaDefenseReference.formula) ? (
          <p className="meta">Defense = {readString(xianxiaDefenseReference.formula)}</p>
        ) : null}
      </section>
      {(
        readString(asRecord(presentedXianxia.quick_reference?.check_formula).formula) ||
        readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus) ||
        readString(asRecord(presentedXianxia.quick_reference?.check_formula).summary)
      ) ? (
        <section className="read-section" id="xianxia-check-formula">
          <div className="section-heading">
            <h2>Check formula</h2>
          </div>
          <div className="glance-grid">
            {readString(asRecord(presentedXianxia.quick_reference?.check_formula).formula) ? (
              <article className="glance-card">
                <span className="meta">Check</span>
                <strong>{readString(asRecord(presentedXianxia.quick_reference?.check_formula).formula)}</strong>
              </article>
            ) : null}
            {(readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus) ||
            readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus_detail)) ? (
              <article className="glance-card">
                <span className="meta">Spend bonus</span>
                <strong>{readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus, "--")}</strong>
                {readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus_detail) ? (
                  <span className="meta">
                    {readString(asRecord(presentedXianxia.quick_reference?.check_formula).spend_bonus_detail)}
                  </span>
                ) : null}
              </article>
            ) : null}
          </div>
          {readString(asRecord(presentedXianxia.quick_reference?.check_formula).summary) ? (
            <p className="meta">
              Check formula = {readString(asRecord(presentedXianxia.quick_reference?.check_formula).summary)}
            </p>
          ) : null}
        </section>
      ) : null}
      {(
        asRecordArray(asRecord(presentedXianxia.quick_reference?.difficulty_states).states).length ||
        readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).summary)
      ) ? (
        <section className="read-section" id="xianxia-difficulty-states">
          <div className="section-heading">
            <h2>Difficulty states</h2>
          </div>
          <div className="glance-grid">
            {asRecordArray(asRecord(presentedXianxia.quick_reference?.difficulty_states).states).map((state) => (
              <article className="glance-card" key={readString(state.key, readString(state.label))}>
                <span className="meta">{readString(state.label)}</span>
                <strong>{readString(state.adjustment_label)}</strong>
                <span className="meta">Final DC adjustment</span>
              </article>
            ))}
          </div>
          {readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).summary) ? (
            <p className="meta">
              Difficulty states = {readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).summary)}.
            </p>
          ) : null}
          {readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).resolution_note) ? (
            <p className="meta">
              {readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).resolution_note)}
            </p>
          ) : null}
        </section>
      ) : null}
      {hasXianxiaHonorInteractions ? (
        <section className="read-section" id="xianxia-honor-interactions">
          <div className="section-heading">
            <h2>Honor interactions</h2>
            {readString(xianxiaHonorInteractions.rule_href) ? (
              <a className="button-link subtle" href={readString(xianxiaHonorInteractions.rule_href)}>
                {`${readString(xianxiaHonorInteractions.rule_title, "Honor")} rule`}
              </a>
            ) : null}
          </div>
          {xianxiaHonorContexts.length ? (
            <div className="glance-grid">
              {xianxiaHonorContexts.map((context) => (
                <article className="glance-card" key={readString(context.key, readString(context.label))}>
                  <span className="meta">{readString(context.label)}</span>
                  <strong>{readString(context.modifier_label, "--")}</strong>
                  <span className="meta">Interaction modifier</span>
                </article>
              ))}
            </div>
          ) : null}
          <article className="detail-card">
            <div className="section-heading">
              <h3>Honor context</h3>
              {readString(xianxiaHonorInteractions.status_label, readString(xianxiaHonorInteractions.status)) ? (
                <span className="meta">
                  {readString(xianxiaHonorInteractions.status_label, readString(xianxiaHonorInteractions.status))}
                </span>
              ) : null}
            </div>
            {(readString(xianxiaHonorInteractions.support) || readString(xianxiaHonorInteractions.support_label)) ? (
              <p className="meta">
                {readString(xianxiaHonorInteractions.support, readString(xianxiaHonorInteractions.support_label))}
              </p>
            ) : null}
            {xianxiaHonorReferenceLines.map((line, index) => (
              <p key={`${line}-${index}`}>{line}</p>
            ))}
            {readString(xianxiaHonorInteractions.summary) ? (
              <p className="meta">Honor interactions = {readString(xianxiaHonorInteractions.summary)}.</p>
            ) : null}
          </article>
        </section>
      ) : null}
      {hasSkillUseGuardrail ? (
        <section className="read-section" id="xianxia-skill-use-guardrails">
          <div className="section-heading">
            <h2>Skill use guardrails</h2>
            {skillUseGuardrailRuleHref ? (
              <a className="button-link subtle" href={skillUseGuardrailRuleHref}>
                {`${skillUseGuardrailRuleTitle} rule`}
              </a>
            ) : null}
          </div>
          <article className="detail-card">
            {skillUseGuardrailReferenceLines.map((line, index) => (
              <p key={`${line}-${index}`}>{line}</p>
            ))}
          </article>
        </section>
      ) : null}
      {xianxiaRuleTextReferences.length ? (
        <section className="read-section" id="xianxia-rule-text-references">
          <div className="section-heading">
            <h2>Rules text references</h2>
          </div>
          <div className="detail-grid">
            {xianxiaRuleTextReferences.map((reference) => (
              <article className="detail-card" key={readString(reference.key, readString(reference.title))}>
                <div className="section-heading">
                  <h3>{readString(reference.title, "Rule text reference")}</h3>
                  {readString(reference.support) || readString(reference.support_label) ? (
                    <span className="meta">
                      {readString(reference.support, readString(reference.support_label))}
                    </span>
                  ) : null}
                </div>
                {readString(reference.rule_href) ? (
                  <p>
                    <a href={readString(reference.rule_href)}>{`${readString(reference.title, "Rule")} rule`}</a>
                  </p>
                ) : null}
                {asStringArray(reference.reference_lines).map((line, index) => (
                  <p key={`${readString(reference.title, "Rule")}-${index}`}>{line}</p>
                ))}
              </article>
            ))}
          </div>
        </section>
      ) : null}
      {hasXianxiaStanceBreak ? (
        <section className="read-section" id="xianxia-stance-break">
          <div className="section-heading">
            <h2>Stance Break</h2>
            {readString(xianxiaStanceBreak.rule_href) ? (
              <a className="button-link subtle" href={readString(xianxiaStanceBreak.rule_href)}>
                {`${readString(xianxiaStanceBreak.rule_title, "Stance Break")} rule`}
              </a>
            ) : null}
          </div>
          <article className="detail-card">
            <div className="section-heading">
              <h3>Current Stance</h3>
              {readString(xianxiaStanceBreak.status_label, readString(xianxiaStanceBreak.status)) ? (
                <span className="meta">
                  {readString(xianxiaStanceBreak.status_label, readString(xianxiaStanceBreak.status))}
                </span>
              ) : null}
            </div>
            {xianxiaStanceBreakReferenceLines.map((line, index) => (
              <p key={`${line}-${index}`}>{line}</p>
            ))}
            {xianxiaStanceBreakRecoveryLines.map((line, index) => (
              <p key={`${line}-${index}`} className="meta">
                {line}
              </p>
            ))}
          </article>
        </section>
      ) : null}
      {asRecordArray(asRecord(presentedXianxia.quick_reference?.effort_damage).entries).length ? (
        <section className="read-section" id="xianxia-effort-damage">
          <div className="section-heading">
            <h2>Effort damage</h2>
          </div>
          <div className="glance-grid">
            {asRecordArray(asRecord(presentedXianxia.quick_reference?.effort_damage).entries).map((entry) => (
              <article className="glance-card" key={readString(entry.key, readString(entry.label))}>
                <span className="meta">{readString(entry.label, "Effort")}</span>
                <strong>{readString(entry.damage, "--")}</strong>
                <span className="meta">Score {stringFromUnknown(entry.score, "--")}</span>
              </article>
            ))}
          </div>
        </section>
      ) : null}
      {asRecordArray(presentedXianxia.quick_reference?.active_state_reminders).length ? (
        <section className="read-section" id="xianxia-active-state-reminders">
          <div className="section-heading">
            <h2>Active Stance and Aura</h2>
          </div>
          <div className="detail-grid">
            {asRecordArray(presentedXianxia.quick_reference?.active_state_reminders).map((reminder) => (
              <article className="detail-card" key={readString(reminder.label, readString(reminder.title))}>
                <div className="section-heading">
                  <h3>{readString(reminder.title, readString(reminder.label))}</h3>
                  {readString(reminder.status_label) ? (
                    <span className="meta">{readString(reminder.status_label)}</span>
                  ) : null}
                </div>
                {readString(reminder.rule_href) ? (
                  <p>
                    <a href={readString(reminder.rule_href)}>{`${readString(reminder.title, "Active stance and aura")} rule`}</a>
                  </p>
                ) : null}
                {readString(reminder.support_label) ? (
                  <p className="meta">{readString(reminder.support_label)}</p>
                ) : null}
                {asStringArray(reminder.reference_lines).map((line, index) => (
                  <p key={`${readString(reminder.label)}-${index}`}>{line}</p>
                ))}
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
