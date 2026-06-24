import { createFileRoute } from "@tanstack/react-router";

import { CombatPage } from "../../../pages/CombatPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/combat")({
  component: CombatPage,
});
