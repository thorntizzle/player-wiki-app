import { readString } from "../characterValueUtils";

export function CharacterDndOverviewSection({
  hasOverviewStatRows,
  overviewStatRows,
  overviewStats,
}: {
  hasOverviewStatRows: boolean;
  overviewStatRows: Record<string, unknown>[][];
  overviewStats: Record<string, unknown>[];
}) {
  return (
    <section className="read-section" id="character-overview">
      <div className="section-heading">
        <h2>At a glance</h2>
      </div>
      {hasOverviewStatRows ? (
        <>
          {overviewStatRows.map((row, rowIndex) => (
            <div className={`glance-grid glance-grid--row glance-grid--quick-row-${rowIndex + 1}`} key={`glance-row-${rowIndex}`}>
              {row.map((stat) => (
                <div className="glance-card" key={`${rowIndex}-${readString(stat.label)}`}>
                  <span className="meta">{readString(stat.label, "--")}</span>
                  <strong>{readString(stat.value, "--")}</strong>
                </div>
              ))}
            </div>
          ))}
        </>
      ) : (
        <div className="glance-grid">
          {overviewStats.map((stat) => (
            <div className="glance-card" key={readString(stat.label, "overview-stat")}>
              <span className="meta">{readString(stat.label, "--")}</span>
              <strong>{readString(stat.value, "--")}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
