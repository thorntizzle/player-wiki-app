import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const DEFAULT_PORT = 39873;
const port = Number(process.env.CPW_SMOKE_PORT || DEFAULT_PORT);
const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const campaignsDir =
  process.env.CPW_CAMPAIGNS_DIR ||
  fileURLToPath(new URL("../../../tests/fixtures/sample_campaigns", import.meta.url));

const nodePath = fileURLToPath(new URL("../dist/server.js", import.meta.url));
const child = spawn(process.execPath, [nodePath], {
  env: {
    ...process.env,
    PORT: String(port),
    NODE_ENV: "test",
    CPW_CAMPAIGNS_DIR: campaignsDir,
  },
  stdio: ["ignore", "pipe", "pipe"],
});

const ensureStopped = () => {
  if (!child.killed) {
    child.kill("SIGINT");
  }
};

process.on("exit", ensureStopped);
process.on("SIGINT", ensureStopped);
process.on("SIGTERM", ensureStopped);

let output = "";
const logLine = (chunk) => {
  output += chunk.toString();
};
child.stdout.on("data", logLine);
child.stderr.on("data", logLine);

const requestJson = async (path) => {
  const response = await fetch(`http://127.0.0.1:${port}${path}`);
  const payload = await response.json();
  return { status: response.status, payload };
};

const waitForReady = async () => {
  const timeout = Number(process.env.CPW_SMOKE_TIMEOUT_MS || 5000);
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const response = await requestJson("/healthz");
      if (response.status === 200 && response.payload?.status === "ok") {
        return;
      }
    } catch {
      // server not yet ready
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Timed out waiting for API readiness. Output: ${output}`);
};

await waitForReady();

const health = await requestJson("/healthz");
if (health.status !== 200 || health.payload?.status !== "ok") {
  throw new Error(`Expected /healthz ok, got ${health.status}`);
}
if (health.payload?.runtime_mode !== "fixture") {
  throw new Error(`Expected fixture runtime, got ${health.payload?.runtime_mode}`);
}
if (health.payload?.campaign_count < 1) {
  throw new Error(`Expected at least one campaign fixture under ${repoRoot}.`);
}

const campaign = await requestJson("/api/v1/campaigns/linden-pass");
if (campaign.status !== 200) {
  throw new Error(`Expected campaign endpoint 200, got ${campaign.status}`);
}
if (campaign.payload?.campaign?.slug !== "linden-pass") {
  throw new Error(`Expected campaign slug to be linden-pass, got ${campaign.payload?.campaign?.slug}`);
}
if (campaign.payload?.campaign?.systems_library_slug !== "DND-5E") {
  throw new Error(`Expected systems_library_slug to be DND-5E, got ${campaign.payload?.campaign?.systems_library_slug}`);
}
if (campaign.payload?.auth?.mode !== "fixture_read_only") {
  throw new Error(`Expected fixture auth mode, got ${campaign.payload?.auth?.mode}`);
}
if (campaign.payload?.permissions?.can_manage_dm_content !== false) {
  throw new Error("Expected read-only permissions in campaign response.");
}

const missing = await requestJson("/api/v1/campaigns/definitely-not-a-campaign");
if (missing.status !== 404) {
  throw new Error(`Expected missing campaign to return 404, got ${missing.status}`);
}
if (missing.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected campaign_not_found error code, got ${missing.payload?.error?.code}`);
}

ensureStopped();
process.exit(0);
