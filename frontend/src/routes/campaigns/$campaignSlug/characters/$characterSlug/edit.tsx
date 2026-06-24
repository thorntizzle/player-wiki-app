import { createFileRoute } from "@tanstack/react-router";

import { CharacterAdvancedEditorPage } from "../../../../../pages/CharacterAdvancedEditorPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/characters/$characterSlug/edit")({
  component: CharacterAdvancedEditorPage,
});
