import { createFileRoute } from "@tanstack/react-router";

import { SessionPage } from "../../../pages/SessionPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/session")({
  component: SessionPage,
});
