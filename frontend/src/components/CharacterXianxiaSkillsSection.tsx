export function CharacterXianxiaSkillsSection({
  hasSkillUseGuardrail,
  skillUseGuardrailReferenceLines,
  skillUseGuardrailRuleHref,
  skillUseGuardrailRuleTitle,
  trainedSkills,
}: {
  hasSkillUseGuardrail: boolean;
  skillUseGuardrailReferenceLines: string[];
  skillUseGuardrailRuleHref: string;
  skillUseGuardrailRuleTitle: string;
  trainedSkills: Array<{ name: string }>;
}) {
  return (
    <section className="read-section" id="xianxia-skills">
      <div className="section-heading">
        <h2>Skills</h2>
      </div>
      {trainedSkills.length ? (
        <div className="skill-grid">
          {trainedSkills.map((skill) => (
            <div className="skill-pill skill-pill--proficient" key={skill.name}>
              <span>{skill.name}</span>
              <span className="meta">Trained</span>
            </div>
          ))}
        </div>
      ) : (
        <article className="detail-card">
          <p className="meta">No trained skills are recorded on this sheet yet.</p>
        </article>
      )}
      {hasSkillUseGuardrail ? (
        <div className="detail-cluster" id="xianxia-skills-guardrail">
          <div className="section-heading">
            <h3>Skill use guardrails</h3>
            {skillUseGuardrailRuleHref ? (
              <a className="button-link subtle" href={skillUseGuardrailRuleHref}>
                {`${skillUseGuardrailRuleTitle} rule`}
              </a>
            ) : null}
          </div>
          {skillUseGuardrailReferenceLines.length ? (
            <article className="detail-card">
              {skillUseGuardrailReferenceLines.map((line, index) => (
                <p key={`${line}-${index}`}>{line}</p>
              ))}
            </article>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
