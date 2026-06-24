import { createFileRoute } from "@tanstack/react-router";

import { CharacterXianxiaManualImportPage } from "../../../../../pages/CharacterXianxiaManualImportPage";

export const Route = createFileRoute("/campaigns/$campaignSlug/characters/import/xianxia-manual")({
  component: CharacterXianxiaManualImportPage,
});
