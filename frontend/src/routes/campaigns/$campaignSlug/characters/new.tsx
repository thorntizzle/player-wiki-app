import { createFileRoute } from "@tanstack/react-router";

import { CharacterCreatePage } from "../../../../pages/CharacterCreatePage";

export const Route = createFileRoute("/campaigns/$campaignSlug/characters/new")({
  component: CharacterCreatePage,
});
