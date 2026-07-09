function asString(value) {
    if (typeof value !== "string") {
        return "";
    }
    return value.trim();
}
function asNumber(value) {
    if (typeof value === "number" && Number.isFinite(value)) {
        return Math.trunc(value);
    }
    if (typeof value === "string" && value.trim() !== "") {
        const parsed = Number(value.trim());
        if (Number.isFinite(parsed)) {
            return Math.trunc(parsed);
        }
    }
    return null;
}
export function normalizeCampaignPayload(payload) {
    const slug = asString(payload.slug);
    const title = asString(payload.title);
    const summary = asString(payload.summary);
    const system = asString(payload.system);
    const systemsLibrarySlug = asString(payload.systems_library);
    return {
        slug,
        title,
        summary,
        system,
        current_session: asNumber(payload.current_session),
        systems_library_slug: systemsLibrarySlug || null,
    };
}
export function isCompleteCampaign(payload) {
    return payload.slug.length > 0 && payload.title.length > 0 && payload.system.length > 0;
}
