function campaignHomeSurface(campaignSlug) {
    return {
        anchor: "campaign-home",
        label: "Campaign Home",
        summary: "Published player-facing wiki hub and header search.",
        status_label: "Open",
        access_note: "You can browse published wiki content here. Current Wiki visibility: Public.",
        capabilities: [
            "Browse published sections and article pages from the campaign hub.",
            "Use the header search to match titles, aliases, summaries, and page body text.",
            "Treat this as the safest player-facing starting point for campaign reference.",
        ],
        limits: [
            "Only published player-safe content appears here.",
            "GM vault notes, Inbox drafts, and other unpublished material do not surface here.",
            "This route is read-only; publishing and reveal timing happen on other surfaces.",
        ],
        links: [
            {
                label: "Open Campaign Home",
                href: `/campaigns/${campaignSlug}`,
            },
        ],
        guidance_cards: [],
    };
}
export function buildCampaignHelpPayload(campaign) {
    const surfaces = [campaignHomeSurface(campaign.slug)];
    return {
        ok: true,
        campaign,
        viewer_role_label: "Public visitor",
        viewer_role_summary: "You are viewing the public portion of this campaign. Member-only surfaces stay hidden until you sign in with the right campaign access.",
        campaign_system_label: campaign.system || "Unspecified",
        is_authenticated: false,
        available_surface_labels: surfaces.map((surface) => surface.label),
        cross_cutting_limits: [
            "Campaign visibility can hide a feature even when the route exists for other roles.",
        ],
        visibility_rows: [
            {
                label: "Campaign",
                visibility_label: "Public",
                viewer_can_open: true,
            },
            {
                label: "Player Wiki",
                visibility_label: "Public",
                viewer_can_open: true,
            },
        ],
        surfaces,
        account_note: "Sign in to save theme preferences, choose a live Session chat order, and open member-only surfaces.",
        links: {
            flask_help_url: `/campaigns/${campaign.slug}/help`,
            gen2_help_url: `/app-next/campaigns/${campaign.slug}/help`,
            account_url: "/app-next/account",
            flask_account_url: "/account",
            sign_in_url: `/sign-in?next=/campaigns/${campaign.slug}/help`,
        },
    };
}
