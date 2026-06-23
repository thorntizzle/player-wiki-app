import { asRecord, asRecordArray, asStringArray, readNumber, readString } from "../characterValueUtils";

export function CharacterDndAbilitySkillsSection({
  abilities,
  hasContent,
  proficiencyGroups,
}: {
  abilities: Record<string, unknown>[];
  hasContent: boolean;
  proficiencyGroups: Record<string, unknown>[];
}) {
  return (
    <section className="read-section" id="character-quick-abilities-skills">
      <div className="section-heading">
        <h2>Abilities and Skills</h2>
      </div>
      {hasContent ? (
        <>
          <div className="ability-grid ability-grid--skills">
            {abilities.map((ability, abilityIndex) => {
              const abilityRecord = asRecord(ability);
              const abilitySkills = asRecordArray(abilityRecord.skills);
              const abilityScoreValue = readNumber(abilityRecord.score, NaN);
              const abilityScore = Number.isNaN(abilityScoreValue) ? "--" : String(abilityScoreValue);
              const abilityName = readString(abilityRecord.name);
              return (
                <article
                  className="ability-card ability-card--skills"
                  key={readString(abilityRecord.key, `ability-${abilityIndex}`)}
                >
                  <div className="ability-card__summary">
                    <h3 className="ability-card__name">{abilityName || readString(abilityRecord.key, "Ability")}</h3>
                    <strong className="ability-card__score">{abilityScore}</strong>
                    <div className="ability-card__values">
                      <span className="ability-card__value">
                        <span>Modifier</span>
                        <strong>{readString(abilityRecord.modifier)}</strong>
                      </span>
                      <span className="ability-card__value">
                        <span>Save</span>
                        <strong>{readString(abilityRecord.save_bonus)}</strong>
                      </span>
                    </div>
                  </div>
                  {abilitySkills.length ? (
                    <ul className="plain-list ability-skill-list">
                      {abilitySkills.map((skill, skillIndex) => {
                        const skillRecord = asRecord(skill);
                        const isProficient = Boolean(skillRecord.is_proficient);
                        const proficiencyLabel = readString(skillRecord.proficiency_label);
                        const normalizedProficiency = proficiencyLabel.toLowerCase();
                        const proficiencyClass =
                          normalizedProficiency === "expertise"
                            ? "ability-skill-list__item--expertise"
                            : isProficient
                              ? "ability-skill-list__item--proficient"
                              : "";
                        const skillName = readString(skillRecord.name);
                        const skillBonus = readString(skillRecord.bonus);
                        return (
                          <li
                            className={["ability-skill-list__item", proficiencyClass].filter(Boolean).join(" ")}
                            key={readString(skillRecord.name, `skill-${abilityIndex}-${skillIndex}`)}
                          >
                            <span className="ability-skill-list__pill">
                              <span className="ability-skill-list__name">{skillName}</span>
                              <strong className="ability-skill-list__bonus">{skillBonus}</strong>
                              {proficiencyLabel && proficiencyLabel !== "None" ? (
                                <span className="visually-hidden">{proficiencyLabel}</span>
                              ) : null}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="meta">No linked skills</p>
                  )}
                </article>
              );
            })}
          </div>

          {proficiencyGroups.length ? (
            <div className="detail-cluster">
              <div>
                <h3>Proficiencies</h3>
                <div className="detail-grid">
                  {proficiencyGroups.map((group) => {
                    const groupRecord = asRecord(group);
                    return (
                      <article className="detail-card" key={readString(groupRecord.title)}>
                        <h4>{readString(groupRecord.title)}</h4>
                        <p>{asStringArray(groupRecord.values_list).join(", ")}</p>
                      </article>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <article className="detail-card">
          <p className="meta">No ability or skill details are recorded on this sheet yet.</p>
        </article>
      )}
    </section>
  );
}
