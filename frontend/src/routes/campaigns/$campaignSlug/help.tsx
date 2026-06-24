import { createFileRoute } from "@tanstack/react-router";

import { CampaignHelpPage } from "../../../pages/CampaignHelpPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/help")({
  component: CampaignHelpPage,
});
