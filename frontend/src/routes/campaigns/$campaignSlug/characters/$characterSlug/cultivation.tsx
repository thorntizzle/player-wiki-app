import { createFileRoute } from "@tanstack/react-router";

import { CharacterCultivationPage } from "../../../../../pages/CharacterCultivationPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/cultivation")({
  component: CharacterCultivationPage,
});
