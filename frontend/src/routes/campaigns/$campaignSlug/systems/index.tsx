import { createFileRoute } from "@tanstack/react-router";

import { SystemsIndexPage } from "../../../../pages/SystemsRoutes";

export const Route = createFileRoute("/campaigns/$campaignSlug/systems/")({
  component: SystemsIndexPage,
});
