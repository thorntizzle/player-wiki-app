/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CPW_TYPESCRIPT_CAMPAIGN_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
