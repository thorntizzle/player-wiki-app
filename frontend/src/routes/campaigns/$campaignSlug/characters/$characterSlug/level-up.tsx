import { createFileRoute } from "@tanstack/react-router";

import { CharacterLevelUpPage } from "../../../../../pages/CharacterLevelUpPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/level-up")({
  component: CharacterLevelUpPage,
});
