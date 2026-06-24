import { createFileRoute } from "@tanstack/react-router";

import { SystemsSourceCategoryPage } from "../../../../../../../pages/SystemsRoutes";

export const Route = createFileRoute("/campaigns/$campaignSlug/systems/sources/$sourceId/types/$entryType")({
  component: SystemsSourceCategoryPage,
});
