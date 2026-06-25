import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { IMPLEMENTED_ROUTES } from "../dist/routes.js";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const snapshotPath = new URL("../../../docs/typescript-backend-rewrite/route-snapshots.json", import.meta.url);
const seedPath = new URL("../../../docs/typescript-backend-rewrite/typescript-route-seed.json", import.meta.url);

const snapshots = JSON.parse(await readFile(snapshotPath, "utf-8"));
const seed = JSON.parse(await readFile(seedPath, "utf-8"));

const snapshotCollections = {
  api_v1: snapshots.api_v1_routes || [],
  flask: snapshots.flask_routes || [],
};

function routeKey(route) {
  return `${route.method.toUpperCase()} ${route.path}`;
}

for (const route of IMPLEMENTED_ROUTES) {
  const snapshotRoutes = snapshotCollections[route.snapshotFamily];
  if (!snapshotRoutes) {
    throw new Error(`Unknown snapshot family '${route.snapshotFamily}' for ${route.honoPath}.`);
  }

  const expected = `${route.method} ${route.snapshotPath}`;
  const hasSnapshot = snapshotRoutes.some((snapshotRoute) => routeKey(snapshotRoute) === expected);
  if (!hasSnapshot) {
    throw new Error(`Implemented TypeScript route ${expected} is missing from ${repoRoot} route snapshot.`);
  }
}

const implementedSeedRoutes = (seed.routes || []).filter((route) =>
  String(route.status || "").startsWith("implemented"),
);

for (const seedRoute of implementedSeedRoutes) {
  const hasImplementation = IMPLEMENTED_ROUTES.some(
    (route) => route.method === seedRoute.method && route.seedPath === seedRoute.path,
  );
  if (!hasImplementation) {
    throw new Error(
      `Implemented TypeScript route seed ${seedRoute.method} ${seedRoute.path} has no route manifest entry.`,
    );
  }
}

for (const route of IMPLEMENTED_ROUTES.filter((item) => item.honoPath.includes(":"))) {
  if (!route.missingResource) {
    throw new Error(`Dynamic route ${route.method} ${route.honoPath} needs a missing-resource check.`);
  }
}
