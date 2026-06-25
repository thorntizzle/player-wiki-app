import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_CAMPAIGNS_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "tests",
  "fixtures",
  "sample_campaigns",
);

export type ApiRuntimeEnvironment = "fixture";

export interface ApiConfig {
  campaignsDir: string;
  environment: string;
  runtimeMode: ApiRuntimeEnvironment;
}

export function getApiConfig(): ApiConfig {
  const env = (process.env.CPW_CAMPAIGNS_DIR || "").trim();
  return {
    campaignsDir: env ? path.resolve(process.cwd(), env) : DEFAULT_CAMPAIGNS_DIR,
    environment: process.env.NODE_ENV || "development",
    runtimeMode: "fixture",
  };
}
