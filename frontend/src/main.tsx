import React from "react";
import { createRoot } from "react-dom/client";
import {
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import "./styles.css";
import { queryClient } from "./apiClientContext";
import { AppShell } from "./AppShell";

const AccountSettingsPage = React.lazy(() =>
  import("./routes/AccountSettingsPage").then((module) => ({ default: module.AccountSettingsPage })),
);
const CampaignControlPage = React.lazy(() =>
  import("./routes/CampaignControlPage").then((module) => ({ default: module.CampaignControlPage })),
);
const CampaignHelpPage = React.lazy(() =>
  import("./routes/CampaignHelpPage").then((module) => ({ default: module.CampaignHelpPage })),
);
const WikiArticlePage = React.lazy(() =>
  import("./routes/WikiRoutes").then((module) => ({ default: module.WikiArticlePage })),
);
const WikiHomePage = React.lazy(() =>
  import("./routes/WikiRoutes").then((module) => ({ default: module.WikiHomePage })),
);
const WikiSectionPage = React.lazy(() =>
  import("./routes/WikiRoutes").then((module) => ({ default: module.WikiSectionPage })),
);
const SystemsEntryPage = React.lazy(() =>
  import("./routes/SystemsRoutes").then((module) => ({ default: module.SystemsEntryPage })),
);
const SystemsIndexPage = React.lazy(() =>
  import("./routes/SystemsRoutes").then((module) => ({ default: module.SystemsIndexPage })),
);
const SystemsSourceCategoryPage = React.lazy(() =>
  import("./routes/SystemsRoutes").then((module) => ({ default: module.SystemsSourceCategoryPage })),
);
const SystemsSourcePage = React.lazy(() =>
  import("./routes/SystemsRoutes").then((module) => ({ default: module.SystemsSourcePage })),
);
const AdminDashboardPage = React.lazy(() =>
  import("./routes/AdminRoutes").then((module) => ({ default: module.AdminDashboardPage })),
);
const AdminUserDetailPage = React.lazy(() =>
  import("./routes/AdminRoutes").then((module) => ({ default: module.AdminUserDetailPage })),
);
const CampaignListPage = React.lazy(() =>
  import("./routes/CampaignPickerPage").then((module) => ({ default: module.CampaignListPage })),
);
const CharacterAdvancedEditorPage = React.lazy(() =>
  import("./routes/CharacterAdvancedEditorPage").then((module) => ({ default: module.CharacterAdvancedEditorPage })),
);
const CharacterCreatePage = React.lazy(() =>
  import("./routes/CharacterCreatePage").then((module) => ({ default: module.CharacterCreatePage })),
);
const CharacterCultivationPage = React.lazy(() =>
  import("./routes/CharacterCultivationPage").then((module) => ({ default: module.CharacterCultivationPage })),
);
const CharacterDetailPage = React.lazy(() =>
  import("./routes/CharacterDetailPage").then((module) => ({ default: module.CharacterDetailPage })),
);
const CharacterLevelUpPage = React.lazy(() =>
  import("./routes/CharacterLevelUpPage").then((module) => ({ default: module.CharacterLevelUpPage })),
);
const CharacterProgressionRepairPage = React.lazy(() =>
  import("./routes/CharacterProgressionRepairPage").then((module) => ({ default: module.CharacterProgressionRepairPage })),
);
const CharacterRetrainingPage = React.lazy(() =>
  import("./routes/CharacterRetrainingPage").then((module) => ({ default: module.CharacterRetrainingPage })),
);
const CharacterXianxiaManualImportPage = React.lazy(() =>
  import("./routes/CharacterXianxiaManualImportPage").then((module) => ({ default: module.CharacterXianxiaManualImportPage })),
);
const CharacterRosterPage = React.lazy(() =>
  import("./routes/CharacterRosterPage").then((module) => ({ default: module.CharacterRosterPage })),
);
const CombatPage = React.lazy(() =>
  import("./routes/CombatPage").then((module) => ({ default: module.CombatPage })),
);
const DmContentPage = React.lazy(() =>
  import("./routes/DmContentPage").then((module) => ({ default: module.DmContentPage })),
);
const SessionPage = React.lazy(() =>
  import("./routes/SessionPage").then((module) => ({ default: module.SessionPage })),
);

declare global {
  interface Window {
    __cpwAppLoadingBegin?: () => void;
    __cpwAppLoadingReady?: () => void;
  }
}

const rootRoute = createRootRoute({
  component: AppShell,
});

const campaignsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: CampaignListPage,
});

const accountSettingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/account",
  component: AccountSettingsPage,
});

const adminDashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  component: AdminDashboardPage,
});

const adminUserDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/users/$userId",
  component: AdminUserDetailPage,
});

const campaignHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug",
  component: WikiHomePage,
});

const campaignHelpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/help",
  component: CampaignHelpPage,
});

const campaignControlRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/control",
  component: CampaignControlPage,
});

const campaignWikiSectionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/sections/$sectionSlug",
  component: WikiSectionPage,
});

const campaignWikiPageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/pages/$",
  component: WikiArticlePage,
});

const campaignSystemsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems",
  component: SystemsIndexPage,
});

const campaignSystemsSourceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/sources/$sourceId",
  component: SystemsSourcePage,
});

const campaignSystemsSourceCategoryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/sources/$sourceId/types/$entryType",
  component: SystemsSourceCategoryPage,
});

const campaignSystemsEntryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/entries/$entrySlug",
  component: SystemsEntryPage,
});

const campaignCharacterRosterRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters",
  component: CharacterRosterPage,
});

const campaignCharacterCreateRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/new",
  component: CharacterCreatePage,
});

const campaignCharacterXianxiaManualImportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/import/xianxia-manual",
  component: CharacterXianxiaManualImportPage,
});

const campaignCharacterAdvancedEditorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/edit",
  component: CharacterAdvancedEditorPage,
});

const campaignCharacterRetrainingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/retraining",
  component: CharacterRetrainingPage,
});

const campaignCharacterLevelUpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/level-up",
  component: CharacterLevelUpPage,
});

const campaignCharacterProgressionRepairRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/progression-repair",
  component: CharacterProgressionRepairPage,
});

const campaignCharacterCultivationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/cultivation",
  component: CharacterCultivationPage,
});

const campaignCharacterDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug",
  component: CharacterDetailPage,
});

const campaignCombatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/combat",
  component: CombatPage,
});

const campaignSessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/session",
  component: SessionPage,
});

const campaignDmContentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/dm-content",
  component: DmContentPage,
});

const routeTree = rootRoute.addChildren([
  campaignsRoute,
  accountSettingsRoute,
  adminDashboardRoute,
  adminUserDetailRoute,
  campaignHomeRoute,
  campaignHelpRoute,
  campaignControlRoute,
  campaignWikiSectionRoute,
  campaignWikiPageRoute,
  campaignSystemsRoute,
  campaignSystemsSourceRoute,
  campaignSystemsSourceCategoryRoute,
  campaignSystemsEntryRoute,
  campaignCharacterRosterRoute,
  campaignCharacterCreateRoute,
  campaignCharacterXianxiaManualImportRoute,
  campaignCharacterAdvancedEditorRoute,
  campaignCharacterRetrainingRoute,
  campaignCharacterLevelUpRoute,
  campaignCharacterProgressionRepairRoute,
  campaignCharacterCultivationRoute,
  campaignCharacterDetailRoute,
  campaignCombatRoute,
  campaignSessionRoute,
  campaignDmContentRoute,
]);
const router = createRouter({
  routeTree,
  basepath: "/app-next",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (root !== null) {
  createRoot(root).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
