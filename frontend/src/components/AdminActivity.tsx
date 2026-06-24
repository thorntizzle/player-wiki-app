import type { AdminAuditEvent, AdminDashboardResponse } from "../api/types";

export function AdminActivityFilters({
  action,
  clearHref,
  data,
}: {
  action: string;
  clearHref: string;
  data: Pick<AdminDashboardResponse, "activity_filters" | "audit_event_type_choices" | "campaign_choices" | "export_url">;
}) {
  return (
    <form method="get" action={action} className="audit-filter-form admin-filter-form">
      <label className="field">
        <span>Search</span>
        <input
          type="text"
          name="audit_q"
          defaultValue={data.activity_filters.query}
          placeholder="user, campaign, character, event"
        />
      </label>
      <label className="field">
        <span>Event</span>
        <select name="audit_event_type" defaultValue={data.activity_filters.event_type}>
          <option value="">All events</option>
          {data.audit_event_type_choices.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Campaign</span>
        <select name="audit_campaign_slug" defaultValue={data.activity_filters.campaign_slug}>
          <option value="">All campaigns</option>
          {data.campaign_choices.map((campaign) => (
            <option key={campaign.slug} value={campaign.slug}>
              {campaign.title}
            </option>
          ))}
        </select>
      </label>
      <div className="audit-filter-form__actions">
        <button type="submit" className="button">
          Filter activity
        </button>
        <a className="ghost-button" href={clearHref}>
          Clear
        </a>
        <a className="ghost-button" href={data.export_url}>
          Export CSV
        </a>
      </div>
    </form>
  );
}

export function AdminActivityList({ events }: { events: AdminAuditEvent[] }) {
  if (!events.length) {
    return <p className="meta">No audit activity matched the current filters.</p>;
  }

  return (
    <ul className="plain-list audit-list admin-audit-list">
      {events.map((event) => (
        <li
          key={event.id}
          className="audit-row admin-audit-row"
          data-event-type={event.event_type}
          data-campaign-slug={event.campaign_slug}
          data-character-slug={event.character_slug}
          data-actor-email={event.actor_email}
          data-target-email={event.target_email}
        >
          <div className="audit-row__header">
            <strong>{event.title}</strong>
            <span className="meta">{event.timestamp}</span>
          </div>
          <p className="meta">
            {event.actor ? (
              <>
                <a href={event.actor.href}>{event.actor.label}</a>
                {event.actor.meta ? <span> {event.actor.meta}</span> : null}
              </>
            ) : (
              "System"
            )}
            {event.target && (!event.actor || event.target.href !== event.actor.href) ? (
              <>
                {" -> "}
                <a href={event.target.href}>{event.target.label}</a>
                {event.target.meta ? <span> {event.target.meta}</span> : null}
              </>
            ) : null}
          </p>
          {event.scope ? <p className="meta">{event.scope}</p> : null}
          {event.details ? <p>{event.details}</p> : null}
        </li>
      ))}
    </ul>
  );
}

export function AdminPagination({ pagination }: Pick<AdminDashboardResponse, "pagination">) {
  return (
    <div className="pagination-bar admin-pagination">
      <p className="meta">
        Page {pagination.current_page} of {pagination.total_pages}
      </p>
      <div className="pagination-bar__actions">
        {pagination.has_previous ? (
          <a className="ghost-button" href={pagination.previous_url}>
            Previous
          </a>
        ) : null}
        {pagination.has_next ? (
          <a className="ghost-button" href={pagination.next_url}>
            Next
          </a>
        ) : null}
      </div>
    </div>
  );
}
