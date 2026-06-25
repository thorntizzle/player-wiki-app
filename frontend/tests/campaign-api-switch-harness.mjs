import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const appShellPath = resolve(frontendDir, "src/AppShell.tsx");
const clientPath = resolve(frontendDir, "src/api/client.ts");

const appShellSource = readFileSync(appShellPath, "utf8");
const clientSource = readFileSync(clientPath, "utf8");

const findings = [];
let failures = 0;

function assert(condition, message) {
  if (!condition) {
    failures += 1;
    console.error(`FAIL: ${message}`);
    return;
  }
  findings.push(`PASS: ${message}`);
}

assert(
  /campaignDetailBaseUrl\s*\?:\s*string;/.test(clientSource),
  "client options include campaignDetailBaseUrl",
);
assert(
  /const baseUrl = this\.campaignDetailBaseUrl \|\| this\.baseUrl;[\s\S]*this\.requestJson<CampaignDetailResponse>\([^;]+baseUrl\)/.test(clientSource),
  "getCampaign uses campaignDetailBaseUrl with baseUrl fallback",
);
assert(
  /this\.requestJson<CampaignsResponse>\(/.test(clientSource),
  "a non-campaign-detail client method still uses default requestJson baseUrl",
);
assert(
  /VITE_CPW_TYPESCRIPT_CAMPAIGN_API_BASE_URL/.test(appShellSource),
  "AppShell passes env override variable",
);

if (failures > 0) {
  throw new Error(`${failures} assertion(s) failed`);
}

findings.forEach((line) => console.log(line));
console.log(`Campaign API switch verification passed for ${frontendDir}`);
