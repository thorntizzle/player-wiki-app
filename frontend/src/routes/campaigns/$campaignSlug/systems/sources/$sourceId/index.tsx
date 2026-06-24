import { createFileRoute } from "@tanstack/react-router";

import { SystemsSourcePage } from "../../../../../../pages/SystemsRoutes";

export const Route = createFileRoute("/campaigns/$campaignSlug/systems/sources/$sourceId/")({
  component: SystemsSourcePage,
});
