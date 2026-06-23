export function CharacterSystemSummarySection({
  currentHp,
  systemLabel,
  tempHp,
}: {
  currentHp: unknown;
  systemLabel: string;
  tempHp: unknown;
}) {
  return (
    <section className="read-section" id="character-system-summary">
      <div className="section-heading">
        <h2>{systemLabel}</h2>
      </div>
      <div className="detail-grid">
        <article className="detail-card">
          <h3>Current HP</h3>
          <strong>{String(currentHp ?? "--")}</strong>
        </article>
        <article className="detail-card">
          <h3>Temp HP</h3>
          <strong>{String(tempHp ?? "--")}</strong>
        </article>
      </div>
    </section>
  );
}
