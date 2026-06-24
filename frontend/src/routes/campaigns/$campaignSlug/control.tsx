import { createFileRoute } from "@tanstack/react-router";

import { CampaignControlPage } from "../../../pages/CampaignControlPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/control")({
  component: CampaignControlPage,
});
