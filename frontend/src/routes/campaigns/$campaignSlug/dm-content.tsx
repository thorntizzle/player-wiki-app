import { createFileRoute } from "@tanstack/react-router";

import { DmContentPage } from "../../../pages/DmContentPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/dm-content")({
  component: DmContentPage,
});
