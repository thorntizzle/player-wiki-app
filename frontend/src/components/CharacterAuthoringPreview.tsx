import { asStringArray, stringFromUnknown } from "../characterValueUtils";

function PreviewSidebar({
  emptyMessage,
  facts,
  listSections,
}: {
  emptyMessage?: string;
  facts: Array<[string, unknown]>;
  listSections: Array<[string, string[]]>;
}) {
  return (
    <aside className="sidebar character-authoring-sidebar">
      <section className="card sidebar-card">
        <h2>Preview</h2>
        {facts.length ? (
          <div className="builder-preview-list">
            {facts.map(([label, value]) => (
              <div key={label}>
                <span className="meta">{label}</span>
                <strong>{stringFromUnknown(value, "Not set")}</strong>
              </div>
            ))}
          </div>
        ) : emptyMessage ? (
          <p className="meta">{emptyMessage}</p>
        ) : null}
      </section>
      {listSections.map(([label, values]) => (
        <section className="card sidebar-card character-authoring-preview-section" key={label}>
          <h3>{label}</h3>
          <ul className="plain-list resource-preview-list">
            {values.map((item) => (
              <li key={`${label}-${item}`}>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}

export function CharacterPreviewList({ preview }: { preview: Record<string, unknown> }) {
  const facts = ([
    ["Class / level", preview.class_level_text],
    ["Max HP", preview.max_hp],
    ["Speed", preview.speed],
    ["Size", preview.size],
    ["Carrying", preview.carrying_capacity],
    ["Push / drag / lift", preview.push_drag_lift],
    ["Currency", preview.starting_currency],
  ] as Array<[string, unknown]>).filter(([, value]) => value !== undefined && value !== null && String(value).trim());
  const listSections = ([
    ["Saving throws", asStringArray(preview.saving_throws)],
    ["Languages", asStringArray(preview.languages)],
    ["Features", asStringArray(preview.features)],
    ["Resources", asStringArray(preview.resources)],
    ["Equipment", asStringArray(preview.equipment)],
    ["Attacks", asStringArray(preview.attacks)],
    ["Spells", asStringArray(preview.spells)],
  ] as Array<[string, string[]]>).filter(([, values]) => values.length);

  return (
    <PreviewSidebar
      emptyMessage="Choose core options to populate the preview."
      facts={facts}
      listSections={listSections}
    />
  );
}

export function CharacterLevelUpPreviewList({ preview }: { preview: Record<string, unknown> }) {
  const facts = ([
    ["Class", preview.class_level_text],
    ["Max HP", preview.max_hp],
    ["Carry", preview.carrying_capacity],
    ["Push / Drag / Lift", preview.push_drag_lift],
  ] as Array<[string, unknown]>).filter(([, value]) => value !== undefined && value !== null && String(value).trim());
  const listSections = ([
    ["Class Rows", asStringArray(preview.class_rows)],
    ["Gained Features", asStringArray(preview.gained_features)],
    ["Resources", asStringArray(preview.resources)],
    ["Attacks", asStringArray(preview.attacks)],
    ["Spell Slots", asStringArray(preview.spell_slots)],
    ["New Spells", asStringArray(preview.new_spells)],
  ] as Array<[string, string[]]>).filter(([, values]) => values.length);

  return <PreviewSidebar facts={facts} listSections={listSections} />;
}
