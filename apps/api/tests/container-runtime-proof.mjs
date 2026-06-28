import { spawn, spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const apiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(apiRoot, "..", "..");
const proofRoot = path.join(repoRoot, ".task-temp", "ts-ops-container-runtime-proof");
const campaignsDir = path.join(proofRoot, "campaigns");
const dbPath = path.join(proofRoot, "player_wiki.sqlite3");
const summaryPath = path.join(proofRoot, "summary.json");
const sourceCampaignsDir = path.join(repoRoot, "tests", "fixtures", "sample_campaigns");
const distServerPath = path.join(apiRoot, "dist", "server.js");
const assetRoute = "/campaigns/linden-pass/assets/lore/trade-coast-map.png";
const appNextRoute = "/app-next/";
const imageTag = "campaign-player-wiki-ts-proof:local";

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: "utf8",
    ...options,
  });
  if (result.error) {
    throw result.error;
  }
  return result;
}

function runChecked(command, args, options = {}) {
  const result = run(command, args, options);
  if (result.status !== 0) {
    throw new Error(
      [
        `Command failed: ${command} ${args.join(" ")}`,
        result.stdout ? `STDOUT:\n${result.stdout}` : "",
        result.stderr ? `STDERR:\n${result.stderr}` : "",
      ]
        .filter(Boolean)
        .join("\n"),
    );
  }
  return result;
}

function resolvePythonCommand() {
  const explicit = [
    process.env.CPW_PYTHON_PATH,
    process.env.PLAYER_WIKI_PYTHON,
    process.env.CPW_PYTHON_BIN,
  ].filter(Boolean);
  for (const candidate of explicit) {
    if (existsSync(candidate)) {
      return { command: candidate, argsPrefix: [] };
    }
  }

  for (const command of ["python", "py"]) {
    try {
      const version = run(command, ["--version"]);
      if (version.status === 0) {
        return { command, argsPrefix: [] };
      }
    } catch {
      // Try the next Python launcher candidate.
    }
  }

  throw new Error("Python was not found. Run through local.ps1 or set CPW_PYTHON_PATH.");
}

function prepareScratchData() {
  rmSync(proofRoot, { recursive: true, force: true });
  mkdirSync(proofRoot, { recursive: true });
  cpSync(sourceCampaignsDir, campaignsDir, { recursive: true });

  const python = resolvePythonCommand();
  runChecked(python.command, [...python.argsPrefix, path.join(repoRoot, "manage.py"), "init-db"], {
    env: {
      ...process.env,
      PLAYER_WIKI_ENV: "production",
      PLAYER_WIKI_DB_PATH: dbPath,
      PLAYER_WIKI_CAMPAIGNS_DIR: campaignsDir,
    },
  });
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

function requestBuffer(port, route) {
  return new Promise((resolve, reject) => {
    const request = http.get(
      {
        hostname: "127.0.0.1",
        port,
        path: route,
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          resolve({
            status: response.statusCode,
            headers: response.headers,
            body: Buffer.concat(chunks),
          });
        });
      },
    );
    request.on("error", reject);
    request.setTimeout(2000, () => {
      request.destroy(new Error(`Timed out requesting ${route}`));
    });
  });
}

async function requestJson(port, route) {
  const response = await requestBuffer(port, route);
  let payload;
  try {
    payload = JSON.parse(response.body.toString("utf8"));
  } catch {
    throw new Error(`Expected JSON from ${route}, got ${response.status}: ${response.body.toString("utf8")}`);
  }
  return { ...response, payload };
}

async function waitForReady(port, output, timeoutMs = 10000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await requestJson(port, "/healthz");
      if (response.status === 200 && response.payload?.status === "ok") {
        return;
      }
    } catch {
      // Server is not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for TypeScript API readiness.\n${output()}`);
}

function stopProcess(child) {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) {
      resolve();
      return;
    }
    child.once("exit", () => resolve());
    child.kill("SIGTERM");
    setTimeout(() => {
      if (child.exitCode === null && child.signalCode === null) {
        child.kill("SIGKILL");
      }
    }, 2000);
  });
}

function assertCommonResponses(label, port, expected) {
  return (async () => {
    const health = await requestJson(port, "/healthz");
    if (health.status !== 200 || health.payload?.status !== "ok") {
      throw new Error(`${label}: expected /healthz 200 ok, got ${health.status}`);
    }
    if (health.payload?.environment !== "production") {
      throw new Error(`${label}: expected production environment, got ${health.payload?.environment}`);
    }
    if (health.payload?.campaign_count !== 1) {
      throw new Error(`${label}: expected one copied fixture campaign, got ${health.payload?.campaign_count}`);
    }
    if (health.payload?.data?.campaigns_dir !== expected.campaignsDir) {
      throw new Error(`${label}: unexpected health campaigns_dir ${health.payload?.data?.campaigns_dir}`);
    }

    const appState = await requestJson(port, "/api/v1/app");
    if (appState.status !== 200 || appState.payload?.ok !== true) {
      throw new Error(`${label}: expected /api/v1/app 200 ok, got ${appState.status}`);
    }
    if (appState.payload?.app?.runtime !== expected.runtime) {
      throw new Error(`${label}: expected runtime ${expected.runtime}, got ${appState.payload?.app?.runtime}`);
    }
    if (appState.payload?.app?.db_path !== expected.dbPath) {
      throw new Error(`${label}: unexpected app db_path ${appState.payload?.app?.db_path}`);
    }
    if (appState.payload?.app?.campaigns_dir !== expected.campaignsDir) {
      throw new Error(`${label}: unexpected app campaigns_dir ${appState.payload?.app?.campaigns_dir}`);
    }
    if (appState.payload?.app?.git_dirty !== false) {
      throw new Error(`${label}: expected clean proof metadata, got git_dirty=${appState.payload?.app?.git_dirty}`);
    }

    const asset = await requestBuffer(port, assetRoute);
    if (asset.status !== 200) {
      throw new Error(`${label}: expected representative asset 200, got ${asset.status}`);
    }
    const contentType = String(asset.headers["content-type"] || "").toLowerCase();
    if (!contentType.startsWith("image/png")) {
      throw new Error(`${label}: expected image/png asset content type, got ${contentType}`);
    }
    if (asset.body.byteLength === 0) {
      throw new Error(`${label}: expected non-empty representative asset body`);
    }

    const appNext = await requestBuffer(port, appNextRoute);
    if (appNext.status !== 404) {
      throw new Error(
        `${label}: expected ${appNextRoute} to remain unserved by the API-only TypeScript proof runtime, got ${appNext.status}`,
      );
    }

    return {
      health_status: health.payload.status,
      health_environment: health.payload.environment,
      health_campaign_count: health.payload.campaign_count,
      app_ok: appState.payload.ok,
      app_runtime: appState.payload.app.runtime,
      app_db_path: appState.payload.app.db_path,
      app_campaigns_dir: appState.payload.app.campaigns_dir,
      asset_status: asset.status,
      asset_content_type: contentType,
      asset_bytes: asset.body.byteLength,
      app_next_status: appNext.status,
      app_next_boundary: "not_served_by_api_only_typescript_runtime",
    };
  })();
}

async function runCompiledRuntimeProof() {
  if (!existsSync(distServerPath)) {
    throw new Error(`Compiled server artifact is missing at ${distServerPath}. Run npm --prefix apps/api run build first.`);
  }

  const port = await findFreePort();
  let output = "";
  const child = spawn(process.execPath, [distServerPath], {
    cwd: repoRoot,
    env: {
      ...process.env,
      NODE_ENV: "production",
      PORT: String(port),
      CPW_DB_PATH: dbPath,
      CPW_CAMPAIGNS_DIR: campaignsDir,
      PLAYER_WIKI_ENV: "production",
      PLAYER_WIKI_RUNTIME: "typescript-container-proof",
      PLAYER_WIKI_BUILD_ID: "ts-ops-container-runtime-proof",
      PLAYER_WIKI_GIT_SHA: "container-proof",
      PLAYER_WIKI_GIT_DIRTY: "false",
      PLAYER_WIKI_BASE_URL: `http://127.0.0.1:${port}`,
      PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS: "999999",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => {
    output += chunk.toString();
  });
  child.stderr.on("data", (chunk) => {
    output += chunk.toString();
  });

  try {
    await waitForReady(port, () => output);
    return {
      port,
      ...(await assertCommonResponses("compiled runtime", port, {
        runtime: "typescript-container-proof",
        dbPath,
        campaignsDir,
      })),
    };
  } finally {
    await stopProcess(child);
  }
}

function dockerCliStatus() {
  let commandProbe;
  try {
    commandProbe = run("docker", ["--version"]);
  } catch (error) {
    return {
      available: false,
      reason: error instanceof Error ? error.message : "docker executable not found on PATH",
    };
  }
  if (commandProbe.status !== 0) {
    return {
      available: false,
      reason: "docker executable not found on PATH",
    };
  }

  let daemonProbe;
  try {
    daemonProbe = run("docker", ["version", "--format", "{{.Server.Version}}"]);
  } catch (error) {
    return {
      available: false,
      reason: error instanceof Error ? error.message : "docker daemon unavailable",
    };
  }
  if (daemonProbe.status !== 0) {
    return {
      available: false,
      reason: `docker daemon unavailable: ${(daemonProbe.stderr || daemonProbe.stdout || "").trim()}`,
    };
  }

  return {
    available: true,
    cli: commandProbe.stdout.trim(),
    server: daemonProbe.stdout.trim(),
  };
}

async function runDockerRuntimeProof(dockerStatus) {
  if (!dockerStatus.available) {
    return {
      status: "skipped",
      reason: dockerStatus.reason,
    };
  }

  runChecked("docker", ["build", "--pull=false", "--target", "ts-api-runtime-proof", "-t", imageTag, "."], {
    stdio: "inherit",
  });

  const port = await findFreePort();
  const containerName = `cpw-ts-proof-${Date.now()}`;
  let containerStarted = false;
  try {
    const runResult = runChecked(
      "docker",
      [
        "run",
        "--rm",
        "-d",
        "--name",
        containerName,
        "-p",
        `127.0.0.1:${port}:8080`,
        "-e",
        "PLAYER_WIKI_ENV=production",
        "-e",
        "PLAYER_WIKI_RUNTIME=typescript-image-proof",
        "-e",
        "PLAYER_WIKI_BUILD_ID=ts-ops-container-runtime-proof",
        "-e",
        "PLAYER_WIKI_GIT_SHA=container-proof",
        "-e",
        "PLAYER_WIKI_GIT_DIRTY=false",
        "-e",
        "PLAYER_WIKI_DB_PATH=/proof-data/player_wiki.sqlite3",
        "-e",
        "PLAYER_WIKI_CAMPAIGNS_DIR=/proof-data/campaigns",
        "-e",
        "PLAYER_WIKI_PORT=8080",
        "-e",
        `PLAYER_WIKI_BASE_URL=http://127.0.0.1:${port}`,
        "-v",
        `${proofRoot}:/proof-data`,
        imageTag,
      ],
    );
    containerStarted = true;
    await waitForReady(port, () => run("docker", ["logs", containerName]).stdout || "");
    return {
      status: "passed",
      image_tag: imageTag,
      container_id: runResult.stdout.trim(),
      port,
      ...(await assertCommonResponses("docker runtime", port, {
        runtime: "typescript-image-proof",
        dbPath: "/proof-data/player_wiki.sqlite3",
        campaignsDir: "/proof-data/campaigns",
      })),
    };
  } catch (error) {
    const logs = containerStarted ? run("docker", ["logs", containerName]).stdout : "";
    throw new Error(`${error instanceof Error ? error.message : String(error)}${logs ? `\nContainer logs:\n${logs}` : ""}`);
  } finally {
    if (containerStarted) {
      run("docker", ["stop", containerName]);
    }
  }
}

prepareScratchData();

const compiled = await runCompiledRuntimeProof();
const dockerStatus = dockerCliStatus();
const docker = await runDockerRuntimeProof(dockerStatus);

const summary = {
  proof: "ts-ops-container-runtime-proof",
  no_deploy: true,
  scratch_root: proofRoot,
  copied_campaigns_dir: campaignsDir,
  sqlite_db_path: dbPath,
  compiled_runtime: compiled,
  docker,
};

writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);

console.log("TypeScript API container runtime proof passed.");
console.log(`Scratch root: ${proofRoot}`);
console.log(`Compiled runtime: /healthz ok, /api/v1/app ok, ${assetRoute} ${compiled.asset_content_type}`);
console.log(`Compiled runtime: ${appNextRoute} ${compiled.app_next_status} (expected API-only boundary)`);
if (docker.status === "skipped") {
  console.log(`Docker runtime: skipped (${docker.reason})`);
} else {
  console.log(`Docker runtime: ${docker.status} (${docker.image_tag})`);
}
console.log(`Summary: ${summaryPath}`);
