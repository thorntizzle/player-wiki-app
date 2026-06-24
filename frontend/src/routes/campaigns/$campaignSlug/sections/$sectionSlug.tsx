import { createFileRoute } from "@tanstack/react-router";

import { WikiSectionPage } from "../../../../pages/WikiRoutes";

export const Route = createFileRoute("/campaigns/$campaignSlug/sections/$sectionSlug")({
  component: WikiSectionPage,
});
