import { createFileRoute } from "@tanstack/react-router";

import { CampaignListPage } from "../pages/CampaignPickerPage";

export const Route = createFileRoute("/")({
  component: CampaignListPage,
});
