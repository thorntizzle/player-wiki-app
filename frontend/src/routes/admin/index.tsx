import { createFileRoute } from "@tanstack/react-router";

import { AdminDashboardPage } from "../../pages/AdminRoutes";

export const Route = createFileRoute("/admin/")({
  component: AdminDashboardPage,
});
