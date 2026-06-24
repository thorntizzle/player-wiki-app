import { createFileRoute } from "@tanstack/react-router";

import { AdminUserDetailPage } from "../../../pages/AdminRoutes";

export const Route = createFileRoute("/admin/users/$userId")({
  component: AdminUserDetailPage,
});
