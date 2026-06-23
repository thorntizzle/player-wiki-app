import type { SessionArticle } from "../api/types";

export function resolveArticleImage(slug: string, article: SessionArticle): string {
  if (article.image?.url) {
    return article.image.url;
  }
  return `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/${article.id}/image`;
}

export function renderArticleBody(article: SessionArticle, extraClassName = ""): JSX.Element {
  const className = `article-body${extraClassName ? ` ${extraClassName}` : ""}`;
  if (article.body_format === "html") {
    return <div className={`${className} html-body`} dangerouslySetInnerHTML={{ __html: article.body_markdown }} />;
  }
  return <pre className={`${className} markdown-body`}>{article.body_markdown}</pre>;
}

function getArticleUrl(value: string | null | undefined): string {
  return typeof value === "string" && value.trim() ? value : "";
}

function getArticleSourceKindLabel(article: SessionArticle): string {
  if (article.source?.label) {
    return article.source.label;
  }
  if (article.source_kind === "page") {
    return "published wiki page";
  }
  if (article.source_kind === "systems") {
    return "Systems entry";
  }
  return article.source_kind || "";
}

export function SessionArticleSourceLine({ article }: { article: SessionArticle }) {
  const sourceTitle = article.source?.title?.trim() || "";
  const sourceKind = article.source_kind?.trim() || "";
  const sourceUrl = getArticleUrl(article.links?.source_url);
  const sourceLabel = getArticleSourceKindLabel(article);

  if (sourceTitle) {
    return (
      <p className="article-context">
        Pulled from {sourceLabel || "source"}:{" "}
        {sourceUrl ? <a href={sourceUrl}>{sourceTitle}</a> : sourceTitle}
      </p>
    );
  }

  if (sourceKind && article.source?.missing_message) {
    return <p className="article-context">{article.source.missing_message}</p>;
  }

  return null;
}

export function SessionArticleReferenceActions({
  article,
  includePromotionLinks,
}: {
  article: SessionArticle;
  includePromotionLinks: boolean;
}) {
  const sourceUrl = getArticleUrl(article.links?.source_url);
  const sourceKind = article.source_kind?.trim() || "";
  if (sourceUrl) {
    return (
      <a className="ghost-button" href={sourceUrl}>
        {article.source?.action_label || "View source"}
      </a>
    );
  }

  if (sourceKind) {
    return article.source?.missing_message ? <span className="meta">{article.source.missing_message}</span> : null;
  }

  const publishedPageUrl = getArticleUrl(article.links?.published_page_url);
  if (publishedPageUrl) {
    return (
      <a className="ghost-button" href={publishedPageUrl}>
        View published page
      </a>
    );
  }

  const convertedTitle = article.converted_page?.title?.trim() || "";
  if (convertedTitle) {
    const revealAfterSession = article.converted_page?.reveal_after_session;
    return (
      <span className="meta">
        Converted to {convertedTitle}
        {revealAfterSession !== null && revealAfterSession !== undefined ? `; visible after session ${revealAfterSession}` : ""}.
      </span>
    );
  }

  if (!includePromotionLinks) {
    return null;
  }

  const editorUrl = getArticleUrl(article.links?.player_wiki_editor_url);
  const convertUrl = getArticleUrl(article.links?.convert_url);

  return (
    <>
      {editorUrl ? (
        <a className="ghost-button" href={editorUrl}>
          Open in Player Wiki editor
        </a>
      ) : null}
      {convertUrl ? (
        <a className="ghost-button" href={convertUrl}>
          Convert to wiki page
        </a>
      ) : null}
    </>
  );
}
