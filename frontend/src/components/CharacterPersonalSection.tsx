import type { CharacterPortrait } from "../api/types";

export function CharacterPersonalSection({
  personalBackgroundHtml,
  physicalDescriptionHtml,
  portrait,
}: {
  personalBackgroundHtml: string;
  physicalDescriptionHtml: string;
  portrait: CharacterPortrait | null | undefined;
}) {
  return (
    <section className="read-section" id="xianxia-personal">
      <div className="section-heading">
        <h2>Personal</h2>
      </div>
      <div className="reference-stack">
        {portrait ? (
          <article className="detail-card" id="character-personal-portrait">
            <figure>
              <img className="article-image" src={portrait.url} alt={portrait.alt_text || "Character portrait"} />
              {portrait.caption ? <figcaption className="meta article-image__caption">{portrait.caption}</figcaption> : null}
            </figure>
          </article>
        ) : null}
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
        {!portrait && !physicalDescriptionHtml && !personalBackgroundHtml ? (
          <article className="detail-card">
            <p className="meta">No personal details yet.</p>
          </article>
        ) : null}
      </div>
    </section>
  );
}
