import { createFileRoute } from "@tanstack/react-router";

import { CharacterRetrainingPage } from "../../../../../pages/CharacterRetrainingPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/retraining")({
  component: CharacterRetrainingPage,
});
