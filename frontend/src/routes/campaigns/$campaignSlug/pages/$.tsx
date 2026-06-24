import { createFileRoute } from "@tanstack/react-router";

import { WikiArticlePage } from "../../../../pages/WikiRoutes";

export const Route = createFileRoute("/campaigns/$campaignSlug/pages/$")({
  component: WikiArticlePage,
});
