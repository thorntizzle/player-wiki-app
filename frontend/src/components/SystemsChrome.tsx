import type {
  SystemsEntrySummary,
  SystemsRulesReferenceResult,
  SystemsSourceBrowseGroup,
} from "../api/types";

export function systemsIndexHref(campaignSlug: string): string {
  return `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/systems`;
}

export function systemsSourceHref(campaignSlug: string, sourceId: string): string {
  return `${systemsIndexHref(campaignSlug)}/sources/${encodeURIComponent(sourceId)}`;
}

export function systemsSourceCategoryHref(campaignSlug: string, sourceId: string, entryType: string): string {
  return `${systemsSourceHref(campaignSlug, sourceId)}/types/${encodeURIComponent(entryType)}`;
}

export function systemsEntryHref(campaignSlug: string, entrySlug: string): string {
  return `${systemsIndexHref(campaignSlug)}/entries/${encodeURIComponent(entrySlug)}`;
}

export function SystemsManageLink({ campaignSlug, canManage }: { campaignSlug: string; canManage: boolean }) {
  return canManage ? (
    <a
      className="ghost-button"
      href={`/app-next/campaigns/${encodeURIComponent(campaignSlug)}/dm-content?lane=systems`}
    >
      Systems settings
    </a>
  ) : null;
}

export function SystemsEntryList({
  campaignSlug,
  entries,
  emptyText,
  showMeta = true,
}: {
  campaignSlug: string;
  entries: SystemsEntrySummary[];
  emptyText: string;
  showMeta?: boolean;
}) {
  if (!entries.length) {
    return <p className="meta">{emptyText}</p>;
  }
  return (
    <ul className="plain-list systems-entry-list">
      {entries.map((entry) => (
        <li className="systems-list-row" key={entry.entry_key}>
          <a href={systemsEntryHref(campaignSlug, entry.slug)}>{entry.title}</a>
          {showMeta ? (
            <span className="meta systems-list-row__meta">
              {entry.entry_type_label}
              {entry.source_page ? ` | p. ${entry.source_page}` : ""}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function SystemsRulesReferenceList({
  campaignSlug,
  results,
  emptyText,
}: {
  campaignSlug: string;
  results: SystemsRulesReferenceResult[];
  emptyText: string;
}) {
  if (!results.length) {
    return <p className="meta">{emptyText}</p>;
  }
  return (
    <ul className="plain-list systems-entry-list">
      {results.map((entry) => (
        <li className="systems-list-row" key={`${entry.source_id}-${entry.slug}`}>
          <a href={systemsEntryHref(campaignSlug, entry.slug)}>{entry.title}</a>
          <span className="meta systems-list-row__meta">
            {entry.entry_type_label}
            {entry.reference_scope ? ` | ${entry.reference_scope}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function SystemsCategoryList({
  campaignSlug,
  sourceId,
  groups,
  emptyText,
}: {
  campaignSlug: string;
  sourceId: string;
  groups: SystemsSourceBrowseGroup[];
  emptyText: string;
}) {
  if (!groups.length) {
    return <p className="meta">{emptyText}</p>;
  }
  return (
    <ul className="plain-list systems-entry-list">
      {groups.map((group) => (
        <li className="systems-list-row" key={group.entry_type}>
          <a href={systemsSourceCategoryHref(campaignSlug, sourceId, group.entry_type)}>
            {group.entry_type_label}
          </a>
          <span className="meta systems-list-row__meta">
            {group.count} entr{group.count === 1 ? "y" : "ies"}
          </span>
        </li>
      ))}
    </ul>
  );
}
