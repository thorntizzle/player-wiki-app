import { createFileRoute } from "@tanstack/react-router";

import { CharacterProgressionRepairPage } from "../../../../../pages/CharacterProgressionRepairPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/progression-repair")({
  component: CharacterProgressionRepairPage,
});
