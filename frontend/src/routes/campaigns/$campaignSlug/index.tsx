import { createFileRoute } from "@tanstack/react-router";

import { WikiHomePage } from "../../../pages/WikiRoutes";

export const Route = createFileRoute("/campaigns/$campaignSlug/")({
  component: WikiHomePage,
});
