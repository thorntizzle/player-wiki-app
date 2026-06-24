import { createFileRoute } from "@tanstack/react-router";

import { SystemsEntryPage } from "../../../../../pages/SystemsRoutes";

export const Route = createFileRoute("/campaigns/$campaignSlug/systems/entries/$entrySlug")({
  component: SystemsEntryPage,
});
