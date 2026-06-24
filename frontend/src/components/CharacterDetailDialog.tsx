import { useEffect, useId, useRef } from "react";

export interface DetailFact {
  label: string;
  value: string;
}

export interface CharacterDetailDialogState {
  eyebrow: string;
  title: string;
  html: string;
  notes?: string;
  href?: string;
  facts?: DetailFact[];
  badges?: string[];
}

export function CharacterDetailDialog({
  detail,
  onClose,
}: {
  detail: CharacterDetailDialogState | null;
  onClose: () => void;
}) {
  const titleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!detail) {
      return;
    }
    window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus({ preventScroll: true });
    });
  }, [detail]);

  if (!detail) {
    return null;
  }
  return (
    <div className="detail-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="detail-modal-header">
          <div>
            <p className="meta">{detail.eyebrow}</p>
            <h3 id={titleId}>{detail.title}</h3>
          </div>
          <button type="button" className="ghost-button" ref={closeButtonRef} onClick={onClose}>
            Close
          </button>
        </header>
        {detail.badges?.length ? (
          <div className="badge-list">
            {detail.badges.map((badge) => (
              <span className="meta-badge" key={badge}>
                {badge}
              </span>
            ))}
          </div>
        ) : null}
        {detail.facts?.length ? (
          <dl className="detail-facts">
            {detail.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {detail.href ? (
          <p className="meta">
            <a href={detail.href}>Open source entry</a>
          </p>
        ) : null}
        {detail.notes ? <p>{detail.notes}</p> : null}
        {detail.html ? (
          <div className="article-body html-body detail-html" dangerouslySetInnerHTML={{ __html: detail.html }} />
        ) : (
          <p className="meta">No linked detail text is available yet.</p>
        )}
      </section>
    </div>
  );
}
