import { useEffect, useMemo, useState } from "react";

import type {
  CombatCharacterWorkspaceFeature,
  CombatCharacterWorkspaceSection,
} from "../api/types";

function CombatFeatureRow({ feature }: { feature: CombatCharacterWorkspaceFeature }) {
  return (
    <article className="feature-row">
      <div className="feature-row__header">
        <div>
          <h3>
            {feature.href ? <a href={feature.href}>{feature.name}</a> : feature.name}
          </h3>
          {feature.group_title ? <p className="meta">{feature.group_title}</p> : null}
        </div>
        {feature.metadata.length ? <p className="meta">{feature.metadata.join(" | ")}</p> : null}
      </div>
      {feature.description_html ? (
        <div
          className="article-body article-body--compact"
          dangerouslySetInnerHTML={{ __html: feature.description_html }}
        />
      ) : null}
    </article>
  );
}

function CombatWorkspacePanel({ section }: { section: CombatCharacterWorkspaceSection }) {
  const features = section.features ?? [];
  const attacks = section.attacks ?? [];
  const hiddenAttacks = section.hidden_attacks ?? [];
  const featureGroups = section.feature_groups ?? [];

  return (
    <section className="read-section combat-workspace-panel">
      <div className="section-heading">
        <h2>{section.label}</h2>
      </div>

      {features.length ? (
        <div className="feature-stack">
          {features.map((feature, index) => (
            <CombatFeatureRow key={`${feature.name}-${index}`} feature={feature} />
          ))}
        </div>
      ) : null}

      {attacks.length ? (
        <div className="detail-grid">
          {attacks.map((attack, index) => (
            <article className="detail-card" key={`${attack.name}-${index}`}>
              <h3>{attack.name}</h3>
              <dl className="compact-stat-list">
                {attack.attack_bonus ? (
                  <div>
                    <dt>Attack</dt>
                    <dd>{attack.attack_bonus}</dd>
                  </div>
                ) : null}
                {attack.damage ? (
                  <div>
                    <dt>Damage</dt>
                    <dd>{attack.damage}</dd>
                  </div>
                ) : null}
                {attack.range ? (
                  <div>
                    <dt>Range</dt>
                    <dd>{attack.range}</dd>
                  </div>
                ) : null}
              </dl>
              {attack.notes ? <p className="meta">{attack.notes}</p> : null}
            </article>
          ))}
        </div>
      ) : null}

      {hiddenAttacks.length ? (
        <div className="detail-grid">
          {hiddenAttacks.map((attack, index) => (
            <article className="detail-card" key={`${attack.name}-${index}`}>
              <h3>{attack.href ? <a href={attack.href}>{attack.name}</a> : attack.name}</h3>
              <p className="meta">Unavailable until the matching equipment or feature state is active.</p>
            </article>
          ))}
        </div>
      ) : null}

      {featureGroups.length ? (
        <div className="feature-stack">
          {featureGroups.map((group) => (
            <section className="detail-card" key={group.title}>
              <h3>{group.title}</h3>
              {group.features.length ? (
                <div className="feature-stack">
                  {group.features.map((feature, index) => (
                    <CombatFeatureRow key={`${group.title}-${feature.name}-${index}`} feature={feature} />
                  ))}
                </div>
              ) : (
                <p className="meta">{section.empty_message}</p>
              )}
            </section>
          ))}
        </div>
      ) : null}

      {!features.length && !attacks.length && !hiddenAttacks.length && !featureGroups.length ? (
        <article className="detail-card">
          <p className="meta">{section.empty_message}</p>
        </article>
      ) : null}
    </section>
  );
}

export function CombatCharacterSections({
  sections,
}: {
  sections: CombatCharacterWorkspaceSection[];
}) {
  const availableSections = useMemo(() => sections.filter((section) => section.slug), [sections]);
  const [activeSectionSlug, setActiveSectionSlug] = useState(() => availableSections[0]?.slug ?? "");

  useEffect(() => {
    if (!availableSections.length) {
      setActiveSectionSlug("");
      return;
    }
    if (!availableSections.some((section) => section.slug === activeSectionSlug)) {
      setActiveSectionSlug(availableSections[0].slug);
    }
  }, [activeSectionSlug, availableSections]);

  if (!availableSections.length) {
    return null;
  }

  const activeSection = availableSections.find((section) => section.slug === activeSectionSlug) ?? availableSections[0];

  return (
    <div data-combat-workspace-root>
      <section className="card combat-workspace-card">
        <div className="section-heading">
          <div>
            <h2>Combat sections</h2>
          </div>
        </div>
        <nav className="combat-workspace-nav" aria-label="Combat workspace sections">
          {availableSections.map((section) => (
            <button
              type="button"
              className={
                section.slug === activeSection.slug
                  ? "ghost-button combat-workspace-button combat-workspace-button--active"
                  : "ghost-button combat-workspace-button"
              }
              aria-pressed={section.slug === activeSection.slug}
              key={section.slug}
              onClick={() => setActiveSectionSlug(section.slug)}
            >
              <span>{section.label}</span>
              {section.count ? <span className="meta-badge">{section.count}</span> : null}
            </button>
          ))}
        </nav>
      </section>
      <CombatWorkspacePanel section={activeSection} />
    </div>
  );
}
