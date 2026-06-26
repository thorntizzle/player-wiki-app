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

const requestJson = async (path, headers = {}) => {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    headers,
  });
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

const appState = await requestJson("/api/v1/app");
if (appState.status !== 200 || appState.payload?.ok !== true) {
  throw new Error(`Expected app state endpoint 200 ok, got ${appState.status}`);
}
for (const key of ["version", "build_id", "git_sha", "runtime", "instance_name", "environment", "base_url", "db_path", "campaigns_dir"]) {
  if (typeof appState.payload?.app?.[key] !== "string" || !appState.payload.app[key]) {
    throw new Error(`Expected app state string field ${key}, got ${appState.payload?.app?.[key]}`);
  }
}
if (typeof appState.payload?.app?.git_dirty !== "boolean") {
  throw new Error(`Expected app state git_dirty boolean, got ${appState.payload?.app?.git_dirty}`);
}
if (appState.payload.app.campaigns_dir !== campaignsDir) {
  throw new Error(`Expected app state campaigns_dir ${campaignsDir}, got ${appState.payload.app.campaigns_dir}`);
}

const campaignList = await requestJson("/api/v1/campaigns");
if (campaignList.status !== 200) {
  throw new Error(`Expected campaign list endpoint 200, got ${campaignList.status}`);
}
if (!Array.isArray(campaignList.payload?.campaigns) || campaignList.payload.campaigns.length !== 1) {
  throw new Error(`Expected one fixture campaign in list, got ${campaignList.payload?.campaigns?.length}`);
}
if (campaignList.payload.campaigns[0]?.campaign?.slug !== "linden-pass") {
  throw new Error(`Expected campaign list to include linden-pass, got ${campaignList.payload.campaigns[0]?.campaign?.slug}`);
}
if (campaignList.payload.campaigns[0]?.role !== "fixture_reader") {
  throw new Error(`Expected fixture_reader campaign list role, got ${campaignList.payload.campaigns[0]?.role}`);
}
if (campaignList.payload?.auth?.mode !== "fixture_read_only") {
  throw new Error(`Expected campaign list fixture auth, got ${campaignList.payload?.auth?.mode}`);
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

const campaignConfig = await requestJson("/api/v1/campaigns/linden-pass/content/config");
if (campaignConfig.status !== 200) {
  throw new Error(`Expected content config endpoint 200, got ${campaignConfig.status}`);
}
if (campaignConfig.payload?.config_file?.campaign_slug !== "linden-pass") {
  throw new Error(`Expected content config campaign_slug linden-pass, got ${campaignConfig.payload?.config_file?.campaign_slug}`);
}
if (campaignConfig.payload?.config_file?.config?.current_session !== 2) {
  throw new Error(
    `Expected content config current_session 2, got ${campaignConfig.payload?.config_file?.config?.current_session}`,
  );
}
if (campaignConfig.payload?.config_file?.config?.title !== "Echoes of the Alloy Coast") {
  throw new Error(`Expected content config title, got ${campaignConfig.payload?.config_file?.config?.title}`);
}
if (!Array.isArray(campaignConfig.payload?.config_file?.config?.systems_sources)) {
  throw new Error(
    `Expected content config to include systems_sources array, got ${JSON.stringify(campaignConfig.payload?.config_file?.config?.systems_sources)}`,
  );
}
const editableFields = campaignConfig.payload?.config_file?.editable_fields;
const expectedEditableFields = [
  "current_session",
  "source_wiki_root",
  "summary",
  "system",
  "systems_library",
  "title",
];
if (!Array.isArray(editableFields) || editableFields.join("|") !== expectedEditableFields.join("|")) {
  throw new Error(`Expected exact editable fields ${JSON.stringify(expectedEditableFields)}, got ${JSON.stringify(editableFields)}`);
}
if (typeof campaignConfig.payload?.config_file?.updated_at !== "string" || !campaignConfig.payload?.config_file?.updated_at) {
  throw new Error(`Expected non-empty updated_at string, got ${campaignConfig.payload?.config_file?.updated_at}`);
}

const contentCharacters = await requestJson("/api/v1/campaigns/linden-pass/content/characters");
if (contentCharacters.status !== 200) {
  throw new Error(`Expected content characters list endpoint 200, got ${contentCharacters.status}`);
}
if (!Array.isArray(contentCharacters.payload?.characters) || contentCharacters.payload.characters.length !== 3) {
  throw new Error(`Expected 3 fixture content characters, got ${contentCharacters.payload?.characters?.length}`);
}
if (contentCharacters.payload.characters.map((item) => item.character_slug).join("|") !== "arden-march|selene-brook|tobin-slate") {
  throw new Error(
    `Expected fixture content characters to be sorted by slug, got ${JSON.stringify(contentCharacters.payload.characters)}`,
  );
}
const ardenSummary = contentCharacters.payload.characters[0];
if (ardenSummary.name !== "Arden March" || ardenSummary.status !== "active" || ardenSummary.import_status !== "clean") {
  throw new Error(`Unexpected Arden content character summary: ${JSON.stringify(ardenSummary)}`);
}
if (typeof ardenSummary.updated_at !== "string" || !ardenSummary.updated_at) {
  throw new Error(`Expected Arden content character summary updated_at, got ${ardenSummary.updated_at}`);
}

const contentCharacter = await requestJson("/api/v1/campaigns/linden-pass/content/characters/arden-march");
if (contentCharacter.status !== 200) {
  throw new Error(`Expected content character detail endpoint 200, got ${contentCharacter.status}`);
}
if (contentCharacter.payload?.character_file?.character_slug !== "arden-march") {
  throw new Error(`Expected Arden character detail, got ${contentCharacter.payload?.character_file?.character_slug}`);
}
if (contentCharacter.payload?.character_file?.state_created !== false) {
  throw new Error(`Expected read-only fixture character state_created false, got ${contentCharacter.payload?.character_file?.state_created}`);
}
if (contentCharacter.payload?.character_file?.definition?.system !== "DND-5E") {
  throw new Error(`Expected Arden definition system DND-5E, got ${contentCharacter.payload?.character_file?.definition?.system}`);
}
if (contentCharacter.payload?.character_file?.definition?.proficiencies?.tool_expertise?.length !== 0) {
  throw new Error(
    `Expected Arden definition normalized tool_expertise array, got ${JSON.stringify(contentCharacter.payload?.character_file?.definition?.proficiencies)}`,
  );
}
if (contentCharacter.payload?.character_file?.import_metadata?.parser_version !== "fixture") {
  throw new Error(
    `Expected Arden import metadata parser_version fixture, got ${contentCharacter.payload?.character_file?.import_metadata?.parser_version}`,
  );
}

const missingContentCharacter = await requestJson("/api/v1/campaigns/linden-pass/content/characters/missing-character");
if (missingContentCharacter.status !== 404 || missingContentCharacter.payload?.error?.code !== "content_character_not_found") {
  throw new Error(
    `Expected missing content character JSON 404, got ${missingContentCharacter.status} ${missingContentCharacter.payload?.error?.code}`,
  );
}

const contentAssets = await requestJson("/api/v1/campaigns/linden-pass/content/assets");
if (contentAssets.status !== 200) {
  throw new Error(`Expected content assets list endpoint 200, got ${contentAssets.status}`);
}
if (!Array.isArray(contentAssets.payload?.assets) || contentAssets.payload.assets.length !== 2) {
  throw new Error(`Expected 2 fixture content assets, got ${contentAssets.payload?.assets?.length}`);
}
const lyraAsset = contentAssets.payload.assets.find((item) => item.asset_ref === "npcs/captain-lyra-vale.png");
if (!lyraAsset) {
  throw new Error("Expected Captain Lyra Vale fixture asset in content asset list.");
}
if (lyraAsset.relative_path !== "npcs/captain-lyra-vale.png") {
  throw new Error(`Unexpected Captain Lyra asset relative_path: ${lyraAsset.relative_path}`);
}
if (lyraAsset.size_bytes !== 69) {
  throw new Error(`Expected Captain Lyra asset size 69, got ${lyraAsset.size_bytes}`);
}
if (lyraAsset.media_type !== "image/png") {
  throw new Error(`Expected Captain Lyra asset media_type image/png, got ${lyraAsset.media_type}`);
}
if (lyraAsset.url !== "/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png") {
  throw new Error(`Unexpected Captain Lyra asset URL: ${lyraAsset.url}`);
}
if (Object.hasOwn(lyraAsset, "data_base64")) {
  throw new Error("Expected content asset list payload to omit data_base64.");
}

const contentAsset = await requestJson("/api/v1/campaigns/linden-pass/content/assets/npcs/captain-lyra-vale.png");
if (contentAsset.status !== 200) {
  throw new Error(`Expected content asset detail endpoint 200, got ${contentAsset.status}`);
}
if (contentAsset.payload?.asset_file?.asset_ref !== "npcs/captain-lyra-vale.png") {
  throw new Error(`Expected Captain Lyra asset detail, got ${contentAsset.payload?.asset_file?.asset_ref}`);
}
if (contentAsset.payload?.asset_file?.media_type !== "image/png") {
  throw new Error(`Expected Captain Lyra asset detail PNG media type, got ${contentAsset.payload?.asset_file?.media_type}`);
}
const assetBytes = Buffer.from(contentAsset.payload?.asset_file?.data_base64 || "", "base64");
if (assetBytes.length !== 69) {
  throw new Error(`Expected Captain Lyra asset detail to include 69 bytes, got ${assetBytes.length}`);
}

const missingContentAsset = await requestJson("/api/v1/campaigns/linden-pass/content/assets/definitely-not-an-asset.png");
if (missingContentAsset.status !== 404 || missingContentAsset.payload?.error?.code !== "content_asset_not_found") {
  throw new Error(
    `Expected missing content asset JSON 404, got ${missingContentAsset.status} ${missingContentAsset.payload?.error?.code}`,
  );
}

const contentPages = await requestJson("/api/v1/campaigns/linden-pass/content/pages");
if (contentPages.status !== 200) {
  throw new Error(`Expected content pages list endpoint 200, got ${contentPages.status}`);
}
if (!Array.isArray(contentPages.payload?.pages) || contentPages.payload.pages.length !== 29) {
  throw new Error(`Expected 29 fixture content pages, got ${contentPages.payload?.pages?.length}`);
}
for (const page of contentPages.payload.pages) {
  if (Object.hasOwn(page, "body_markdown")) {
    throw new Error(`Expected content page list payload to omit body_markdown for ${page.page_ref}`);
  }
}
const portMeridianInList = contentPages.payload.pages.find((item) => item.page_ref === "locations/port-meridian");
if (!portMeridianInList) {
  throw new Error("Expected Port Meridian content page in fixture list payload.");
}
if (portMeridianInList.relative_path !== "locations/port-meridian.md") {
  throw new Error(`Unexpected Port Meridian relative_path: ${portMeridianInList.relative_path}`);
}
if (portMeridianInList.page?.route_slug !== "locations/port-meridian") {
  throw new Error(`Unexpected Port Meridian route slug: ${portMeridianInList.page?.route_slug}`);
}
if (portMeridianInList.can_hard_delete !== true) {
  throw new Error(`Expected fixture Port Meridian hard-delete to be available, got ${portMeridianInList.can_hard_delete}`);
}
if (!Array.isArray(portMeridianInList.hard_delete_blockers) || portMeridianInList.hard_delete_blockers.length !== 0) {
  throw new Error(`Expected no Port Meridian hard-delete blockers, got ${JSON.stringify(portMeridianInList.hard_delete_blockers)}`);
}
if (portMeridianInList.removal_status_label !== "Hard delete available") {
  throw new Error(`Expected hard delete availability label, got ${portMeridianInList.removal_status_label}`);
}
if (portMeridianInList.removal_guidance !== "Hard delete is available after confirmation.") {
  throw new Error(`Expected hard delete guidance label, got ${portMeridianInList.removal_guidance}`);
}

const contentPage = await requestJson("/api/v1/campaigns/linden-pass/content/pages/locations/port-meridian");
if (contentPage.status !== 200) {
  throw new Error(`Expected content page detail endpoint 200, got ${contentPage.status}`);
}
if (!contentPage.payload?.page_file || typeof contentPage.payload.page_file.body_markdown !== "string" || !contentPage.payload.page_file.body_markdown) {
  throw new Error("Expected content page detail payload to include non-empty body_markdown.");
}
if (contentPage.payload.page_file.page?.route_slug !== "locations/port-meridian") {
  throw new Error(`Expected Port Meridian content detail route slug, got ${contentPage.payload.page_file?.page?.route_slug}`);
}
if (!contentPage.payload.page_file.can_hard_delete) {
  throw new Error(`Expected fixture Port Meridian hard-delete to be available, got ${contentPage.payload.page_file.can_hard_delete}`);
}
if (typeof contentPage.payload.page_file.body_markdown !== "string" || !contentPage.payload.page_file.body_markdown.includes("Port Meridian is a layered trade city")) {
  throw new Error(`Unexpected Port Meridian body markdown: ${contentPage.payload.page_file?.body_markdown}`);
}

const missingContentPage = await requestJson("/api/v1/campaigns/linden-pass/content/pages/definitely-not-a-page");
if (missingContentPage.status !== 404 || missingContentPage.payload?.error?.code !== "content_page_not_found") {
  throw new Error(`Expected missing content page JSON 404, got ${missingContentPage.status} ${missingContentPage.payload?.error?.code}`);
}

const missing = await requestJson("/api/v1/campaigns/definitely-not-a-campaign");
if (missing.status !== 404) {
  throw new Error(`Expected missing campaign to return 404, got ${missing.status}`);
}
if (missing.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected campaign_not_found error code, got ${missing.payload?.error?.code}`);
}

const wikiHome = await requestJson("/api/v1/campaigns/linden-pass/wiki");
if (wikiHome.status !== 200) {
  throw new Error(`Expected wiki home 200, got ${wikiHome.status}`);
}
if (wikiHome.payload?.result_count !== 25) {
  throw new Error(`Expected 25 visible fixture wiki pages, got ${wikiHome.payload?.result_count}`);
}
if (wikiHome.payload?.overview_page !== null) {
  throw new Error("Expected deprecated Overview page to stay hidden from wiki home.");
}
if (wikiHome.payload?.latest_session_summary?.route_slug !== "sessions/session-2-the-brass-vault") {
  throw new Error(
    `Expected latest session summary route slug, got ${wikiHome.payload?.latest_session_summary?.route_slug}`,
  );
}
const wikiSections = wikiHome.payload?.section_navigation || [];
if (wikiSections[0]?.section_name !== "Sessions" || wikiSections[2]?.section_name !== "Locations") {
  throw new Error(`Expected Flask-compatible wiki section ordering, got ${JSON.stringify(wikiSections.slice(0, 3))}`);
}

const wikiSection = await requestJson("/api/v1/campaigns/linden-pass/wiki/sections/locations");
if (wikiSection.status !== 200) {
  throw new Error(`Expected wiki section 200, got ${wikiSection.status}`);
}
if (wikiSection.payload?.section_name !== "Locations" || wikiSection.payload?.page_count !== 5) {
  throw new Error(`Expected Locations section with five pages, got ${JSON.stringify(wikiSection.payload)}`);
}
if (wikiSection.payload?.show_subsections !== true) {
  throw new Error("Expected Locations section to expose subsection grouping.");
}
if (wikiSection.payload?.pages?.[0]?.route_slug !== "locations/harbor-row") {
  throw new Error(`Expected Harbor Row first in Locations section, got ${wikiSection.payload?.pages?.[0]?.route_slug}`);
}

const wikiPage = await requestJson("/api/v1/campaigns/linden-pass/wiki/pages/locations/port-meridian");
if (wikiPage.status !== 200) {
  throw new Error(`Expected wiki page 200, got ${wikiPage.status}`);
}
if (wikiPage.payload?.page?.route_slug !== "locations/port-meridian") {
  throw new Error(`Expected Port Meridian page, got ${wikiPage.payload?.page?.route_slug}`);
}
if (
  wikiPage.payload?.page?.body_html !==
  "<p>Port Meridian is a layered trade city of piers, markets, guild offices, and storm channels cut into the cliff.</p>"
) {
  throw new Error(`Unexpected Port Meridian body_html: ${wikiPage.payload?.page?.body_html}`);
}
if (wikiPage.payload?.page?.image !== null) {
  throw new Error("Expected Port Meridian to have no image payload.");
}

const imagePage = await requestJson("/api/v1/campaigns/linden-pass/wiki/pages/npcs/captain-lyra-vale");
if (imagePage.status !== 200) {
  throw new Error(`Expected Captain Lyra Vale page 200, got ${imagePage.status}`);
}
if (imagePage.payload?.page?.image?.media_type !== "image/png") {
  throw new Error(`Expected PNG image metadata, got ${JSON.stringify(imagePage.payload?.page?.image)}`);
}
if (imagePage.payload?.page?.image?.url !== "/campaigns/linden-pass/assets/npcs/captain-lyra-vale.png") {
  throw new Error(`Expected Flask asset URL, got ${imagePage.payload?.page?.image?.url}`);
}

const missingWikiCampaign = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/wiki");
if (missingWikiCampaign.status !== 404 || missingWikiCampaign.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing wiki campaign JSON 404, got ${missingWikiCampaign.status}`);
}

const missingWikiSection = await requestJson("/api/v1/campaigns/linden-pass/wiki/sections/definitely-not-a-section");
if (missingWikiSection.status !== 404 || missingWikiSection.payload?.error?.code !== "wiki_section_not_found") {
  throw new Error(`Expected missing wiki section JSON 404, got ${missingWikiSection.status}`);
}

const missingWikiPage = await requestJson("/api/v1/campaigns/linden-pass/wiki/pages/definitely-not-a-page");
if (missingWikiPage.status !== 404 || missingWikiPage.payload?.error?.code !== "wiki_page_not_found") {
  throw new Error(`Expected missing wiki page JSON 404, got ${missingWikiPage.status}`);
}

const session = await requestJson("/api/v1/campaigns/linden-pass/session");
if (session.status !== 200 || session.payload?.ok !== true) {
  throw new Error(`Expected session endpoint 200 ok, got ${session.status}`);
}
if (session.payload?.campaign?.slug !== "linden-pass") {
  throw new Error(`Expected session campaign slug linden-pass, got ${session.payload?.campaign?.slug}`);
}
if (session.payload?.permissions?.can_manage_session !== false) {
  throw new Error(`Expected read-only session permissions, got ${session.payload?.permissions?.can_manage_session}`);
}
if (session.payload?.permissions?.can_post_messages !== false) {
  throw new Error(`Expected can_post_messages false, got ${session.payload?.permissions?.can_post_messages}`);
}
if (session.payload?.active_session !== null) {
  throw new Error(`Expected active_session null in fixture session response, got ${JSON.stringify(session.payload?.active_session)}`);
}
if (!Array.isArray(session.payload?.messages) || session.payload.messages.length !== 0) {
  throw new Error(`Expected empty messages array in fixture session response, got ${JSON.stringify(session.payload?.messages)}`);
}
if (session.payload?.session_message_recipient_player_choices?.length !== 0) {
  throw new Error("Expected no recipient choices in fixture session read mode.");
}
if (session.payload?.show_session_dm_passive_scores !== false) {
  throw new Error("Expected show_session_dm_passive_scores false in fixture session response.");
}
if (typeof session.payload?.session_revision !== "number" || session.payload.session_revision < 0) {
  throw new Error(`Expected non-negative numeric session_revision, got ${session.payload?.session_revision}`);
}
if (typeof session.payload?.session_view_token !== "string" || !/^[0-9a-f]{12}$/i.test(session.payload.session_view_token)) {
  throw new Error(`Expected 12-char hex session_view_token, got ${session.payload?.session_view_token}`);
}
if (session.payload?.staged_articles !== undefined) {
  throw new Error("Expected fixture read-only session response to omit staged_articles.");
}
if (session.payload?.revealed_articles !== undefined) {
  throw new Error("Expected fixture read-only session response to omit revealed_articles.");
}
if (session.payload?.session_logs !== undefined) {
  throw new Error("Expected fixture read-only session response to omit session_logs.");
}
if (session.payload?.session_dm_passive_scores !== undefined) {
  throw new Error("Expected fixture read-only session response to omit session_dm_passive_scores.");
}

const unchangedSession = await requestJson("/api/v1/campaigns/linden-pass/session", {
  "X-Live-Revision": String(session.payload?.session_revision),
  "X-Live-View-Token": String(session.payload?.session_view_token),
});
if (unchangedSession.status !== 200) {
  throw new Error(`Expected unchanged session short-circuit request 200, got ${unchangedSession.status}`);
}
if (
  unchangedSession.payload?.ok !== true ||
  unchangedSession.payload?.changed !== false ||
  unchangedSession.payload?.session_revision !== session.payload?.session_revision ||
  unchangedSession.payload?.session_view_token !== session.payload?.session_view_token ||
  Object.keys(unchangedSession.payload || {}).length !== 4
) {
  throw new Error(`Expected Flask-style unchanged payload, got ${JSON.stringify(unchangedSession.payload)}`);
}

const missingSession = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/session");
if (missingSession.status !== 404 || missingSession.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing session campaign JSON 404, got ${missingSession.status}`);
}

const missingCampaignConfig = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/content/config");
if (missingCampaignConfig.status !== 404 || missingCampaignConfig.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing content config campaign JSON 404, got ${missingCampaignConfig.status}`);
}
const missingContentPages = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/content/pages");
if (missingContentPages.status !== 404 || missingContentPages.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing content pages campaign JSON 404, got ${missingContentPages.status}`);
}
const missingContentCharacters = await requestJson("/api/v1/campaigns/definitely-not-a-campaign/content/characters");
if (missingContentCharacters.status !== 404 || missingContentCharacters.payload?.error?.code !== "campaign_not_found") {
  throw new Error(`Expected missing content characters campaign JSON 404, got ${missingContentCharacters.status}`);
}

ensureStopped();
process.exit(0);
