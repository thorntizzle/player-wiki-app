import { existsSync } from "node:fs";
import Database from "better-sqlite3";
const VISIBILITY_SCOPES = ["campaign", "wiki", "systems", "session", "combat", "characters", "dm_content"];
const VISIBILITY_LABELS = {
    public: "Public",
    players: "Players",
    dm: "DM",
    private: "Private",
};
const VISIBILITY_ORDER = {
    public: 0,
    players: 1,
    dm: 2,
    private: 3,
};
const VISIBILITY_SCOPE_LABELS = {
    campaign: "Campaign",
    wiki: "Player Wiki",
    systems: "Systems",
    session: "Session",
    combat: "Combat",
    characters: "Characters",
    dm_content: "DM Content",
};
const DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE = {
    campaign: "public",
    wiki: "public",
    systems: "players",
    session: "players",
    combat: "players",
    characters: "dm",
    dm_content: "dm",
};
function normalizeSystemKey(value) {
    return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}
function normalizeVisibility(value) {
    const visibility = String(value || "").trim().toLowerCase();
    return Object.hasOwn(VISIBILITY_ORDER, visibility) ? visibility : "";
}
function isVisibilityScope(value) {
    return VISIBILITY_SCOPES.includes(value);
}
function mostPrivateVisibility(left, right) {
    return (VISIBILITY_ORDER[left] ?? -1) >= (VISIBILITY_ORDER[right] ?? -1) ? left : right;
}
function roleSatisfiesVisibility(role, visibility) {
    if (role === "admin") {
        return true;
    }
    if (visibility === "public") {
        return true;
    }
    if (visibility === "players") {
        return role === "player" || role === "dm";
    }
    if (visibility === "dm") {
        return role === "dm";
    }
    return false;
}
function utcIsoTimestamp() {
    return new Date().toISOString().replace("Z", "+00:00");
}
function campaignDefaultVisibility(campaign) {
    const defaults = { ...DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE };
    if (normalizeSystemKey(campaign.system) === "xianxia") {
        defaults.systems = "dm";
    }
    return defaults;
}
function readVisibilitySettingsFromDatabase(database, campaignSlug) {
    const settings = new Map();
    const rows = database
        .prepare("SELECT scope, visibility FROM campaign_visibility_settings WHERE campaign_slug = ?")
        .all(campaignSlug);
    for (const row of rows) {
        const scope = String(row.scope || "").trim().toLowerCase();
        const visibility = normalizeVisibility(row.visibility);
        if (isVisibilityScope(scope) && visibility) {
            settings.set(scope, visibility);
        }
    }
    return settings;
}
function readVisibilitySettings(dbPath, campaignSlug) {
    const settings = new Map();
    if (!existsSync(dbPath)) {
        return settings;
    }
    const database = new Database(dbPath, { fileMustExist: true, readonly: true });
    try {
        return readVisibilitySettingsFromDatabase(database, campaignSlug);
    }
    catch (error) {
        if (error instanceof Error && (error.message.includes("no such table") || error.message.includes("no such column"))) {
            return settings;
        }
        throw error;
    }
    finally {
        database.close();
    }
    return settings;
}
function writeAuditEvent(database, { actorUserId, campaignSlug, scope, visibility, now, }) {
    database
        .prepare(`INSERT INTO auth_audit_log (
        actor_user_id,
        target_user_id,
        campaign_slug,
        character_slug,
        event_type,
        metadata_json,
        created_at
      ) VALUES (?, NULL, ?, NULL, ?, ?, ?)`)
        .run(actorUserId, campaignSlug, "campaign_visibility_updated", JSON.stringify({
        scope,
        source: "campaign_control_api",
        visibility,
    }), now);
}
export function updateCampaignVisibilitySettings(dbPath, campaign, role, actorUserId, rawVisibility) {
    const defaults = campaignDefaultVisibility(campaign);
    const database = new Database(dbPath, { fileMustExist: true });
    try {
        const settings = readVisibilitySettingsFromDatabase(database, campaign.slug);
        const changedScopes = [];
        const now = utcIsoTimestamp();
        const upsertSetting = database.prepare(`INSERT INTO campaign_visibility_settings (
        campaign_slug,
        scope,
        visibility,
        updated_at,
        updated_by_user_id
      ) VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(campaign_slug, scope) DO UPDATE SET
        visibility = excluded.visibility,
        updated_at = excluded.updated_at,
        updated_by_user_id = excluded.updated_by_user_id`);
        const writeChanges = database.transaction(() => {
            for (const scope of VISIBILITY_SCOPES) {
                const currentVisibility = settings.get(scope) || "";
                const defaultVisibility = defaults[scope];
                const submittedVisibility = Object.hasOwn(rawVisibility, scope)
                    ? rawVisibility[scope]
                    : currentVisibility || defaultVisibility;
                const selectedVisibility = normalizeVisibility(submittedVisibility);
                if (!selectedVisibility) {
                    return {
                        status: "validation_error",
                        message: `Choose a valid visibility for ${VISIBILITY_SCOPE_LABELS[scope]}.`,
                    };
                }
                if (selectedVisibility === "private" && role !== "admin") {
                    return {
                        status: "validation_error",
                        message: "Private visibility is reserved for app admins.",
                    };
                }
                if (currentVisibility && currentVisibility === selectedVisibility) {
                    continue;
                }
                if (!currentVisibility && defaultVisibility === selectedVisibility) {
                    continue;
                }
                upsertSetting.run(campaign.slug, scope, selectedVisibility, now, actorUserId);
                writeAuditEvent(database, {
                    actorUserId,
                    campaignSlug: campaign.slug,
                    scope,
                    visibility: selectedVisibility,
                    now,
                });
                changedScopes.push(VISIBILITY_SCOPE_LABELS[scope]);
            }
            return {
                status: "ok",
                changedScopes,
            };
        });
        return writeChanges();
    }
    finally {
        database.close();
    }
}
function getScopeVisibility(scope, defaults, settings) {
    return settings.get(scope) || defaults[scope];
}
function getEffectiveVisibility(scope, defaults, settings) {
    const campaignVisibility = getScopeVisibility("campaign", defaults, settings);
    if (scope === "campaign") {
        return campaignVisibility;
    }
    return mostPrivateVisibility(campaignVisibility, getScopeVisibility(scope, defaults, settings));
}
function visibilityChoices(includePrivate) {
    const choices = [
        { value: "public", label: VISIBILITY_LABELS.public },
        { value: "players", label: VISIBILITY_LABELS.players },
        { value: "dm", label: VISIBILITY_LABELS.dm },
    ];
    if (includePrivate) {
        choices.push({ value: "private", label: VISIBILITY_LABELS.private });
    }
    return choices;
}
export function campaignRoleCanManageVisibility(dbPath, campaign, role) {
    if (role === "admin") {
        return true;
    }
    if (role !== "dm") {
        return false;
    }
    const defaults = campaignDefaultVisibility(campaign);
    const settings = readVisibilitySettings(dbPath, campaign.slug);
    return roleSatisfiesVisibility(role, getEffectiveVisibility("campaign", defaults, settings));
}
export function campaignRoleCanAccessScope(dbPath, campaign, role, scope) {
    const defaults = campaignDefaultVisibility(campaign);
    const settings = readVisibilitySettings(dbPath, campaign.slug);
    return roleSatisfiesVisibility(role, getEffectiveVisibility(scope, defaults, settings));
}
export function campaignScopeIsPublic(dbPath, campaign, scope) {
    const defaults = campaignDefaultVisibility(campaign);
    const settings = readVisibilitySettings(dbPath, campaign.slug);
    return getEffectiveVisibility(scope, defaults, settings) === "public";
}
export function buildCampaignControlPayload(dbPath, campaign, role) {
    const includePrivate = role === "admin";
    const defaults = campaignDefaultVisibility(campaign);
    const settings = readVisibilitySettings(dbPath, campaign.slug);
    const campaignEffectiveVisibility = getEffectiveVisibility("campaign", defaults, settings);
    return {
        ok: true,
        campaign,
        visibility_rows: VISIBILITY_SCOPES.map((scope) => {
            const configuredVisibility = settings.get(scope) || "";
            const effectiveVisibility = getEffectiveVisibility(scope, defaults, settings);
            const defaultVisibility = defaults[scope];
            const selectedVisibility = configuredVisibility || defaultVisibility;
            return {
                scope,
                label: VISIBILITY_SCOPE_LABELS[scope],
                selected_visibility: selectedVisibility,
                selected_visibility_label: VISIBILITY_LABELS[selectedVisibility] || selectedVisibility,
                configured_visibility: configuredVisibility,
                configured_visibility_label: configuredVisibility ? VISIBILITY_LABELS[configuredVisibility] || configuredVisibility : "",
                default_visibility: defaultVisibility,
                default_visibility_label: VISIBILITY_LABELS[defaultVisibility] || defaultVisibility,
                effective_visibility: effectiveVisibility,
                effective_visibility_label: VISIBILITY_LABELS[effectiveVisibility],
                choices: visibilityChoices(includePrivate),
                is_overridden_by_campaign: scope !== "campaign" &&
                    effectiveVisibility !== configuredVisibility &&
                    effectiveVisibility === campaignEffectiveVisibility,
            };
        }),
        can_set_private_visibility: includePrivate,
        rules: [
            { label: "Public", description: "Anyone can see it." },
            { label: "Players", description: "Only the DM and players in the campaign can see it." },
            { label: "DM", description: "Only the campaign DM can see it." },
            { label: "Private", description: "Only an app admin can see it." },
        ],
        notes: [
            "Campaign-level visibility acts as a floor for every campaign section.",
            "Systems also apply source-level and article-level access rules on top of the Systems scope.",
            ...(includePrivate
                ? []
                : ["Private visibility is reserved for admins even though admins can still access everything."]),
        ],
        links: {
            flask_control_url: `/campaigns/${campaign.slug}/control-panel`,
            gen2_control_url: `/app-next/campaigns/${campaign.slug}/control`,
        },
    };
}
