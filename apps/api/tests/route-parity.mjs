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

const allowedMethods = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
const allowedMissingResourceContentTypes = new Set(["application/json"]);
const routeFamilyPattern = /^[a-z][a-z0-9_]*$/;
const errorCodePattern = /^[a-z][a-z0-9_]*$/;
const templatePathPattern = /\/:[^/]+|\*|<[^>]+>/;
const routeFamilyCoverage = new Map();

function routeKey(route) {
  return `${route.method.toUpperCase()} ${route.path}`;
}

function assertNonEmptyString(value, fieldName, routeLabel) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${routeLabel} has invalid ${fieldName}; expected a non-empty string.`);
  }
}

function assertPathShape(value, fieldName, routeLabel) {
  assertNonEmptyString(value, fieldName, routeLabel);
  if (!value.startsWith("/")) {
    throw new Error(`${routeLabel} has invalid ${fieldName} '${value}'; paths must start with '/'.`);
  }
  if (/\s/.test(value)) {
    throw new Error(`${routeLabel} has invalid ${fieldName} '${value}'; paths must not contain whitespace.`);
  }
}

function assertMethod(value, fieldName, routeLabel) {
  assertNonEmptyString(value, fieldName, routeLabel);
  if (!allowedMethods.has(value)) {
    throw new Error(`${routeLabel} has invalid ${fieldName} '${value}'.`);
  }
}

function recordRouteFamily(route) {
  const current = routeFamilyCoverage.get(route.routeFamily) || {
    total: 0,
    dynamic: 0,
    missingResource: 0,
  };
  current.total += 1;
  if (route.honoPath.includes(":") || route.honoPath.includes("*")) {
    current.dynamic += 1;
  }
  if (route.missingResource) {
    current.missingResource += 1;
  }
  routeFamilyCoverage.set(route.routeFamily, current);
}

for (const route of IMPLEMENTED_ROUTES) {
  const routeLabel = `${route.method} ${route.honoPath}`;
  assertMethod(route.method, "method", routeLabel);
  assertPathShape(route.honoPath, "honoPath", routeLabel);
  assertPathShape(route.snapshotPath, "snapshotPath", routeLabel);
  assertPathShape(route.seedPath, "seedPath", routeLabel);
  assertNonEmptyString(route.routeFamily, "routeFamily", routeLabel);
  if (!routeFamilyPattern.test(route.routeFamily)) {
    throw new Error(`${routeLabel} has invalid routeFamily '${route.routeFamily}'.`);
  }
  if (route.snapshotMethod) {
    assertMethod(route.snapshotMethod, "snapshotMethod", routeLabel);
  }
  recordRouteFamily(route);

  const snapshotRoutes = snapshotCollections[route.snapshotFamily];
  if (!snapshotRoutes) {
    throw new Error(`Unknown snapshot family '${route.snapshotFamily}' for ${route.honoPath}.`);
  }

  const expected = `${route.snapshotMethod || route.method} ${route.snapshotPath}`;
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

for (const route of IMPLEMENTED_ROUTES.filter((item) => item.missingResource)) {
  const routeLabel = `${route.method} ${route.honoPath}`;
  const probe = route.missingResource;
  assertMethod(probe.method, "missingResource.method", routeLabel);
  if (probe.method !== route.method) {
    throw new Error(
      `${routeLabel} has missingResource.method '${probe.method}' but the implemented method is '${route.method}'.`,
    );
  }
  assertPathShape(probe.path, "missingResource.path", routeLabel);
  if (templatePathPattern.test(probe.path)) {
    throw new Error(
      `${routeLabel} has non-concrete missingResource.path '${probe.path}'; use a real fixture probe path.`,
    );
  }
  if (!Number.isInteger(probe.status) || probe.status < 400 || probe.status > 599) {
    throw new Error(`${routeLabel} has invalid missingResource.status '${probe.status}'.`);
  }
  if (!allowedMissingResourceContentTypes.has(probe.contentType)) {
    throw new Error(
      `${routeLabel} has unsupported missingResource.contentType '${probe.contentType}'.`,
    );
  }
  assertNonEmptyString(probe.errorCode, "missingResource.errorCode", routeLabel);
  if (!errorCodePattern.test(probe.errorCode)) {
    throw new Error(`${routeLabel} has invalid missingResource.errorCode '${probe.errorCode}'.`);
  }
}

for (const [routeFamily, coverage] of routeFamilyCoverage) {
  if (coverage.dynamic > 0 && coverage.missingResource === 0) {
    throw new Error(
      `Route family '${routeFamily}' has ${coverage.dynamic} dynamic routes but no missing-resource probes.`,
    );
  }
}
