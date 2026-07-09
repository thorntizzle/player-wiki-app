import { existsSync } from "node:fs";
import Database from "better-sqlite3";
import { listCampaigns } from "../campaigns/repository.js";
import { listCampaignContentCharacters } from "../content/repository.js";
const AUDIT_PAGE_SIZE = 10;
const EVENT_TITLES = {
    api_token_issued: "API token issued",
    api_token_revoked: "API token revoked",
    campaign_systems_entry_override_updated: "Systems entry override updated",
    campaign_systems_policy_updated: "Systems policy updated",
    campaign_systems_shared_entry_updated: "Shared Systems entry updated",
    campaign_systems_source_updated: "Systems source updated",
    campaign_visibility_updated: "Campaign visibility updated",
    campaign_wiki_page_created: "Wiki page created",
    campaign_wiki_page_deleted: "Wiki page deleted",
    campaign_wiki_page_unpublished: "Wiki page unpublished",
    campaign_wiki_page_updated: "Wiki page updated",
    character_assignment_created: "Character assigned",
    character_assignment_removed: "Character assignment removed",
    character_deleted: "Character deleted",
    membership_created: "Membership created",
    membership_removed: "Membership removed",
    membership_role_changed: "Membership updated",
    password_reset_completed: "Password reset completed",
    password_reset_issued: "Password reset issued",
    user_activated: "Account activated",
    user_created: "User created",
    user_deleted: "User deleted",
    user_disabled: "User disabled",
    user_enabled: "User re-enabled",
    user_invited: "Invite issued",
};
const SOURCE_LABELS = {
    admin_screen: "admin screen",
    campaign_control_panel: "campaign control panel",
    campaign_systems_control_panel: "systems control panel",
    campaign_systems_shared_entry_editor: "shared Systems entry editor",
    character_controls: "character controls",
    dm_content_player_wiki: "DM Content player wiki",
    invite: "invite setup",
    "manage.py": "CLI",
    reset_token: "reset link",
};
function openReadonlyDatabase(dbPath) {
    if (!existsSync(dbPath)) {
        return null;
    }
    try {
        return new Database(dbPath, { fileMustExist: true, readonly: true });
    }
    catch {
        return null;
    }
}
function tableExists(database, tableName) {
    const row = database
        .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?")
        .get(tableName);
    return Boolean(row);
}
function serializeUser(row) {
    return {
        id: Number(row.id),
        email: String(row.email),
        display_name: String(row.display_name),
        is_admin: Boolean(Number(row.is_admin)),
        status: String(row.status),
        created_at: String(row.created_at),
        updated_at: String(row.updated_at),
    };
}
function nullableString(value) {
    if (value === null || value === undefined) {
        return null;
    }
    return String(value);
}
function titleize(value) {
    const words = value.replace(/[_-]+/g, " ").trim();
    return words
        ? words.replace(/\b\w/g, (letter) => letter.toUpperCase())
        : value;
}
function parseMetadata(rawValue) {
    try {
        const parsed = JSON.parse(rawValue || "{}");
        return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
            ? parsed
            : {};
    }
    catch {
        return {};
    }
}
function formatTimestamp(value) {
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) {
        return value;
    }
    const date = new Date(timestamp);
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    const day = String(date.getUTCDate()).padStart(2, "0");
    const hour = String(date.getUTCHours()).padStart(2, "0");
    const minute = String(date.getUTCMinutes()).padStart(2, "0");
    return `${year}-${month}-${day} ${hour}:${minute} UTC`;
}
function summarizeAuditEvent(metadata) {
    const detailBits = [];
    if (metadata.is_admin === true) {
        detailBits.push("app admin");
    }
    for (const key of ["role", "status", "scope"]) {
        const value = metadata[key];
        if (typeof value === "string" && value.trim()) {
            detailBits.push(`${key} ${value.trim()}`);
        }
    }
    const visibility = metadata.visibility;
    if (typeof visibility === "string" && visibility.trim()) {
        detailBits.push(`visibility ${visibility.trim()}`);
    }
    const sourceId = metadata.source_id;
    if (typeof sourceId === "string" && sourceId.trim()) {
        detailBits.push(`source ${sourceId.trim()}`);
    }
    const librarySlug = metadata.library_slug;
    if (typeof librarySlug === "string" && librarySlug.trim()) {
        detailBits.push(`library ${librarySlug.trim()}`);
    }
    const entryKey = metadata.entry_key;
    if (typeof entryKey === "string" && entryKey.trim()) {
        detailBits.push(`entry ${entryKey.trim()}`);
    }
    const email = metadata.email;
    if (typeof email === "string" && email.trim()) {
        detailBits.push(`user ${email.trim()}`);
    }
    if (metadata.is_enabled === true) {
        detailBits.push("enabled");
    }
    else if (metadata.is_enabled === false) {
        detailBits.push("disabled");
    }
    const assignmentType = metadata.assignment_type;
    if (typeof assignmentType === "string" && assignmentType.trim()) {
        detailBits.push(`assignment ${assignmentType.trim()}`);
    }
    if (metadata.previous_user_id !== null && metadata.previous_user_id !== undefined) {
        detailBits.push("reassigned");
    }
    const sourceKey = metadata.source || metadata.via;
    if (typeof sourceKey === "string" && sourceKey.trim()) {
        detailBits.push(`via ${SOURCE_LABELS[sourceKey] || sourceKey.replace(/_/g, " ")}`);
    }
    return detailBits.join(" | ");
}
function buildUserReference(userId, displayName, email) {
    if (userId === null || !email) {
        return null;
    }
    const label = displayName || email;
    return {
        label,
        meta: displayName && displayName !== email ? email : "",
        href: `/app-next/admin/users/${userId}`,
        flask_href: `/admin/users/${userId}`,
    };
}
function serializeAuditEvent(row, campaignLookup) {
    const campaignSlug = row.campaign_slug ? String(row.campaign_slug) : "";
    const characterSlug = row.character_slug ? String(row.character_slug) : "";
    const scopeBits = [];
    if (campaignSlug) {
        scopeBits.push(campaignLookup[campaignSlug] || campaignSlug);
    }
    if (characterSlug) {
        scopeBits.push(characterSlug);
    }
    const metadata = parseMetadata(String(row.metadata_json || "{}"));
    return {
        id: Number(row.id),
        event_type: String(row.event_type),
        title: EVENT_TITLES[row.event_type] || titleize(row.event_type),
        timestamp: formatTimestamp(String(row.created_at || "")),
        actor: buildUserReference(row.actor_user_id === null ? null : Number(row.actor_user_id), row.actor_display_name, row.actor_email),
        target: buildUserReference(row.target_user_id === null ? null : Number(row.target_user_id), row.target_display_name, row.target_email),
        actor_email: row.actor_email || "",
        target_email: row.target_email || "",
        campaign_slug: campaignSlug,
        character_slug: characterSlug,
        scope: scopeBits.join(" / "),
        details: summarizeAuditEvent(metadata),
    };
}
function queryString(parameters) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(parameters)) {
        if (String(value).trim()) {
            searchParams.set(key, String(value));
        }
    }
    return searchParams.toString();
}
function activityParams(filters, page) {
    const parameters = {};
    if (filters.query) {
        parameters.audit_q = filters.query;
    }
    if (filters.event_type) {
        parameters.audit_event_type = filters.event_type;
    }
    if (filters.campaign_slug) {
        parameters.audit_campaign_slug = filters.campaign_slug;
    }
    const pageValue = page ?? filters.page;
    if (pageValue > 1) {
        parameters.audit_page = pageValue;
    }
    return parameters;
}
function activityUrl(path, filters, page) {
    const query = queryString(activityParams(filters, page));
    return query ? `${path}?${query}` : path;
}
function auditFiltersFromQuery(query, campaignChoices) {
    const campaignSlugs = new Set(campaignChoices.map((campaign) => campaign.slug));
    const queryValue = String(query.audit_q || "").trim();
    const eventType = String(query.audit_event_type || "").trim();
    const campaignSlug = String(query.audit_campaign_slug || "").trim();
    const rawPage = Number(String(query.audit_page || "").trim());
    return {
        query: queryValue,
        event_type: Object.hasOwn(EVENT_TITLES, eventType) ? eventType : "",
        campaign_slug: campaignSlugs.has(campaignSlug) ? campaignSlug : "",
        page: Number.isInteger(rawPage) && rawPage > 0 ? rawPage : 1,
    };
}
function buildAuditClause(filters, userId) {
    const clauses = [];
    const parameters = [];
    if (userId !== undefined) {
        clauses.push("(log.actor_user_id = ? OR log.target_user_id = ?)");
        parameters.push(userId, userId);
    }
    if (filters.query) {
        const likeQuery = `%${filters.query.toLowerCase()}%`;
        clauses.push(`(
      LOWER(log.event_type) LIKE ?
      OR LOWER(COALESCE(log.campaign_slug, '')) LIKE ?
      OR LOWER(COALESCE(log.character_slug, '')) LIKE ?
      OR LOWER(COALESCE(actor.display_name, '')) LIKE ?
      OR LOWER(COALESCE(actor.email, '')) LIKE ?
      OR LOWER(COALESCE(target.display_name, '')) LIKE ?
      OR LOWER(COALESCE(target.email, '')) LIKE ?
      OR LOWER(COALESCE(log.metadata_json, '')) LIKE ?
    )`);
        parameters.push(likeQuery, likeQuery, likeQuery, likeQuery, likeQuery, likeQuery, likeQuery, likeQuery);
    }
    if (filters.event_type) {
        clauses.push("log.event_type = ?");
        parameters.push(filters.event_type);
    }
    if (filters.campaign_slug) {
        clauses.push("log.campaign_slug = ?");
        parameters.push(filters.campaign_slug);
    }
    return {
        whereClause: clauses.length ? `WHERE ${clauses.join(" AND ")}` : "",
        parameters,
    };
}
function emptyAuditContext(filters, basePath, exportPath) {
    const effectiveFilters = { ...filters, page: 1 };
    return {
        activity_filters: effectiveFilters,
        pagination: {
            current_page: 1,
            page_size: AUDIT_PAGE_SIZE,
            total_events: 0,
            total_pages: 1,
            has_previous: false,
            has_next: false,
            previous_url: "",
            next_url: "",
        },
        export_url: activityUrl(exportPath, effectiveFilters, 1),
        recent_audit_events: [],
    };
}
function loadAuditContext(database, campaignLookup, filters, basePath, exportPath, userId) {
    if (!database || !tableExists(database, "auth_audit_log") || !tableExists(database, "users")) {
        return emptyAuditContext(filters, basePath, exportPath);
    }
    const clause = buildAuditClause(filters, userId);
    const countRow = database
        .prepare(`SELECT COUNT(*) AS count
       FROM auth_audit_log AS log
       LEFT JOIN users AS actor ON actor.id = log.actor_user_id
       LEFT JOIN users AS target ON target.id = log.target_user_id
       ${clause.whereClause}`)
        .get(...clause.parameters);
    const totalEvents = Number(countRow?.count || 0);
    const totalPages = Math.max(1, Math.ceil(totalEvents / AUDIT_PAGE_SIZE));
    const currentPage = Math.min(filters.page, totalPages);
    const effectiveFilters = { ...filters, page: currentPage };
    const rows = database
        .prepare(`SELECT
        log.*,
        actor.display_name AS actor_display_name,
        actor.email AS actor_email,
        target.display_name AS target_display_name,
        target.email AS target_email
       FROM auth_audit_log AS log
       LEFT JOIN users AS actor ON actor.id = log.actor_user_id
       LEFT JOIN users AS target ON target.id = log.target_user_id
       ${clause.whereClause}
       ORDER BY log.created_at DESC, log.id DESC
       LIMIT ? OFFSET ?`)
        .all(...clause.parameters, AUDIT_PAGE_SIZE, (currentPage - 1) * AUDIT_PAGE_SIZE);
    return {
        activity_filters: effectiveFilters,
        pagination: {
            current_page: currentPage,
            page_size: AUDIT_PAGE_SIZE,
            total_events: totalEvents,
            total_pages: totalPages,
            has_previous: currentPage > 1,
            has_next: currentPage < totalPages,
            previous_url: currentPage > 1 ? activityUrl(basePath, effectiveFilters, currentPage - 1) : "",
            next_url: currentPage < totalPages ? activityUrl(basePath, effectiveFilters, currentPage + 1) : "",
        },
        export_url: activityUrl(exportPath, effectiveFilters, 1),
        recent_audit_events: rows.map((row) => serializeAuditEvent(row, campaignLookup)),
    };
}
function loadUsers(database) {
    if (!database || !tableExists(database, "users")) {
        return [];
    }
    const rows = database.prepare("SELECT * FROM users ORDER BY lower(email) ASC").all();
    return rows.map(serializeUser);
}
function loadUser(database, userId) {
    if (!database || !tableExists(database, "users")) {
        return null;
    }
    const row = database.prepare("SELECT * FROM users WHERE id = ?").get(userId);
    return row ? serializeUser(row) : null;
}
function loadMembershipsForUser(database, userId) {
    if (!database || !tableExists(database, "campaign_memberships")) {
        return [];
    }
    const rows = database
        .prepare("SELECT * FROM campaign_memberships WHERE user_id = ? ORDER BY campaign_slug ASC")
        .all(userId);
    return rows.filter((membership) => ["active", "invited", "removed"].includes(String(membership.status)));
}
function loadMembership(database, userId, campaignSlug) {
    if (!database || !tableExists(database, "campaign_memberships")) {
        return null;
    }
    const row = database
        .prepare("SELECT * FROM campaign_memberships WHERE user_id = ? AND campaign_slug = ?")
        .get(userId, campaignSlug);
    return row || null;
}
function loadAssignmentsForUser(database, userId) {
    if (!database || !tableExists(database, "character_assignments")) {
        return [];
    }
    return database
        .prepare("SELECT * FROM character_assignments WHERE user_id = ? ORDER BY campaign_slug, character_slug")
        .all(userId);
}
function serializeMembership(membership, campaignLookup) {
    return {
        id: Number(membership.id),
        campaign_slug: String(membership.campaign_slug),
        campaign_title: campaignLookup[membership.campaign_slug] || String(membership.campaign_slug),
        role: String(membership.role),
        status: String(membership.status),
        created_at: nullableString(membership.created_at),
        updated_at: nullableString(membership.updated_at),
    };
}
function assignmentLabel(assignment, assignmentLabelLookup) {
    const assignmentRef = `${assignment.campaign_slug}::${assignment.character_slug}`;
    const choiceLabel = assignmentLabelLookup[assignmentRef] || "";
    if (choiceLabel) {
        const separatorIndex = choiceLabel.indexOf(" | ");
        return separatorIndex >= 0 ? choiceLabel.slice(separatorIndex + 3).trim() : choiceLabel;
    }
    return String(assignment.character_slug);
}
function serializeAssignment(assignment, campaignLookup, assignmentLabelLookup) {
    return {
        id: Number(assignment.id),
        user_id: Number(assignment.user_id),
        campaign_slug: String(assignment.campaign_slug),
        campaign_title: campaignLookup[assignment.campaign_slug] || String(assignment.campaign_slug),
        character_slug: String(assignment.character_slug),
        character_label: assignmentLabel(assignment, assignmentLabelLookup),
        assignment_type: String(assignment.assignment_type || "owner"),
        created_at: nullableString(assignment.created_at),
        updated_at: nullableString(assignment.updated_at),
    };
}
function assignmentSummary(assignment, campaignLookup, assignmentLabelLookup) {
    const campaignTitle = campaignLookup[assignment.campaign_slug] || String(assignment.campaign_slug);
    return `${campaignTitle} | ${assignmentLabel(assignment, assignmentLabelLookup)}`;
}
function buildUserCards(database, users, campaignLookup, assignmentLabelLookup) {
    return users
        .map((user) => {
        const memberships = loadMembershipsForUser(database, user.id);
        const assignments = loadAssignmentsForUser(database, user.id);
        return {
            id: user.id,
            email: user.email,
            display_name: user.display_name,
            status: user.status,
            is_admin: user.is_admin,
            href: `/app-next/admin/users/${user.id}`,
            flask_href: `/admin/users/${user.id}`,
            membership_summary: memberships.map((membership) => `${campaignLookup[membership.campaign_slug] || membership.campaign_slug} | ${membership.role} (${membership.status})`),
            assignment_summary: assignments.map((assignment) => assignmentSummary(assignment, campaignLookup, assignmentLabelLookup)),
        };
    })
        .sort((left, right) => left.email.localeCompare(right.email));
}
async function listCampaignChoices(config) {
    const campaigns = await listCampaigns(config);
    return campaigns.map((campaign) => ({ slug: campaign.slug, title: campaign.title }));
}
async function listCharacterChoices(config, campaigns) {
    const choices = [];
    for (const campaign of campaigns) {
        const records = await listCampaignContentCharacters(config, campaign.slug);
        for (const record of records || []) {
            const rawName = record.definition.name;
            const name = typeof rawName === "string" && rawName.trim() ? rawName.trim() : record.character_slug;
            choices.push({
                campaign_slug: campaign.slug,
                character_slug: record.character_slug,
                label: `${campaign.title} | ${name}`,
                value: `${campaign.slug}::${record.character_slug}`,
            });
        }
    }
    return choices.sort((left, right) => left.label.localeCompare(right.label));
}
function campaignLookup(campaigns) {
    return Object.fromEntries(campaigns.map((campaign) => [campaign.slug, campaign.title]));
}
function assignmentLabelLookup(characterChoices) {
    return Object.fromEntries(characterChoices.map((choice) => [choice.value, choice.label]));
}
function inviteFormDefaults(campaigns) {
    return {
        user_type: campaigns.length ? "player" : "admin",
        campaign_slug: campaigns[0]?.slug || "",
    };
}
function membershipFormDefaults(database, query, userId, campaigns) {
    const requestedCampaignSlug = String(query.edit_membership_campaign_slug || "").trim();
    if (requestedCampaignSlug) {
        const membership = loadMembership(database, userId, requestedCampaignSlug);
        if (membership) {
            return {
                campaign_slug: String(membership.campaign_slug),
                role: String(membership.role),
                status: String(membership.status),
            };
        }
    }
    return {
        campaign_slug: campaigns[0]?.slug || "",
        role: "player",
        status: "active",
    };
}
function assignmentFormDefaults(query, characterChoices) {
    const requestedCampaignSlug = String(query.edit_assignment_campaign_slug || "").trim();
    const requestedCharacterSlug = String(query.edit_assignment_character_slug || "").trim();
    const requestedRef = requestedCampaignSlug && requestedCharacterSlug ? `${requestedCampaignSlug}::${requestedCharacterSlug}` : "";
    const availableRefs = new Set(characterChoices.map((choice) => choice.value));
    return {
        character_ref: requestedRef && availableRefs.has(requestedRef) ? requestedRef : characterChoices[0]?.value || "",
    };
}
function auditEventTypeChoices() {
    return Object.keys(EVENT_TITLES)
        .sort()
        .map((eventType) => ({
        value: eventType,
        label: EVENT_TITLES[eventType] || titleize(eventType),
    }));
}
export async function buildAdminDashboardPayload(config, currentAdminUser, query) {
    const campaigns = await listCampaignChoices(config);
    const characters = await listCharacterChoices(config, campaigns);
    const campaignTitles = campaignLookup(campaigns);
    const characterLabels = assignmentLabelLookup(characters);
    const database = openReadonlyDatabase(config.dbPath);
    try {
        const filters = auditFiltersFromQuery(query, campaigns);
        const auditContext = loadAuditContext(database, campaignTitles, filters, "/app-next/admin", "/admin/activity/export.csv");
        return {
            ok: true,
            admin_user: currentAdminUser,
            campaign_choices: campaigns,
            invite_form_defaults: inviteFormDefaults(campaigns),
            audit_event_type_choices: auditEventTypeChoices(),
            user_cards: buildUserCards(database, loadUsers(database), campaignTitles, characterLabels),
            links: {
                gen2_admin_url: "/app-next/admin",
                flask_admin_url: "/admin",
            },
            ...auditContext,
        };
    }
    finally {
        database?.close();
    }
}
export async function buildAdminUserDetailPayload(config, currentAdminUser, userId, query) {
    const campaigns = await listCampaignChoices(config);
    const characters = await listCharacterChoices(config, campaigns);
    const campaignTitles = campaignLookup(campaigns);
    const characterLabels = assignmentLabelLookup(characters);
    const database = openReadonlyDatabase(config.dbPath);
    try {
        const user = loadUser(database, userId);
        if (!user) {
            return null;
        }
        const filters = auditFiltersFromQuery(query, campaigns);
        const auditContext = loadAuditContext(database, campaignTitles, filters, `/app-next/admin/users/${user.id}`, `/admin/users/${user.id}/activity/export.csv`, user.id);
        const memberships = loadMembershipsForUser(database, user.id);
        const assignments = loadAssignmentsForUser(database, user.id);
        return {
            ok: true,
            managed_user: user,
            campaign_choices: campaigns,
            character_choices: characters,
            memberships: memberships.map((membership) => serializeMembership(membership, campaignTitles)),
            assignments: assignments.map((assignment) => serializeAssignment(assignment, campaignTitles, characterLabels)),
            audit_event_type_choices: auditEventTypeChoices(),
            membership_form_defaults: membershipFormDefaults(database, query, user.id, campaigns),
            assignment_form_defaults: assignmentFormDefaults(query, characters),
            can_manage_account: currentAdminUser !== null && currentAdminUser.id !== user.id,
            links: {
                gen2_admin_url: "/app-next/admin",
                flask_admin_url: "/admin",
                gen2_user_url: `/app-next/admin/users/${user.id}`,
                flask_user_url: `/admin/users/${user.id}`,
            },
            ...auditContext,
        };
    }
    finally {
        database?.close();
    }
}
