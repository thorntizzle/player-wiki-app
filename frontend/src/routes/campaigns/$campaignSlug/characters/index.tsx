import { createFileRoute } from "@tanstack/react-router";

import { CharacterRosterPage } from "../../../../pages/CharacterRosterPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/characters/")({
  component: CharacterRosterPage,
});
