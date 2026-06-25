export function CharacterPersonalSection({
  personalBackgroundHtml,
  physicalDescriptionHtml,
  sectionId = "character-personal",
}: {
  personalBackgroundHtml: string;
  physicalDescriptionHtml: string;
  sectionId?: string;
}) {
  return (
    <section className="read-section" id={sectionId}>
      <div className="section-heading">
        <h2>Personal</h2>
      </div>
      <div className="reference-stack">
        {physicalDescriptionHtml ? (
          <article className="detail-card">
            <h3>Physical Description</h3>
            <div
              className="article-body article-body--compact"
              dangerouslySetInnerHTML={{ __html: physicalDescriptionHtml }}
            />
          </article>
        ) : null}
        {personalBackgroundHtml ? (
          <article className="detail-card">
            <h3>Background</h3>
            <div className="article-body article-body--compact" dangerouslySetInnerHTML={{ __html: personalBackgroundHtml }} />
          </article>
        ) : null}
        {!physicalDescriptionHtml && !personalBackgroundHtml ? (
          <article className="detail-card">
            <p className="meta">No personal details yet.</p>
          </article>
        ) : null}
      </div>
    </section>
  );
}
