import React, { useState, useEffect, useMemo, useContext, createContext, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  Link,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
  useParams,
} from "@tanstack/react-router";
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FormEvent } from "react";
import "./styles.css";
import {
  CampaignApiClient,
  apiErrorMessage,
  isApiError,
} from "./api/client";
import type {
  CampaignEntry,
  CharacterCurrencyPatchPayload,
  CharacterDetailResponse,
  CharacterEquipmentRow,
  CharacterEquipmentStatePatchPayload,
  CharacterFeatureStatePatchPayload,
  CharacterInventoryPatchPayload,
  CharacterPresentedInventoryItem,
  CharacterPresentedSpell,
  CharacterPresentedXianxia,
  CharacterRecord,
  CharacterXianxiaInventoryItem,
  CharacterXianxiaInventoryItemPayload,
  CharacterXianxiaNamedRecord,
  CharacterNotesPatchPayload,
  CharacterResourcePatchPayload,
  CharacterRestApplyResponse,
  CharacterRestPreviewResponse,
  CharacterSpellSlotsPatchPayload,
  CharacterSummary,
  CharacterVitalsPatchPayload,
  SessionArticle,
  SessionArticleCreatePayload,
  SessionArticleCreatePayloadManual,
  SessionArticleCreatePayloadUpload,
  SessionArticleCreatePayloadWiki,
  SessionArticleSourceResult,
  SessionLogSummary,
  SessionMessage,
  SessionPayload,
  SessionWikiLookupPreviewResponse,
  SessionWikiLookupSearchResult,
} from "./api/types";

interface ApiMessageEnvelope {
  status: number;
  message: string;
}

interface EmbeddedImageInput {
  filename: string;
  data_base64: string;
  media_type: string;
}

interface CharacterVitalsDraft {
  expectedRevision: number;
  currentHp: string;
  tempHp: string;
}

interface CharacterXianxiaVitalsDraft extends CharacterVitalsDraft {
  currentStance: string;
  tempStance: string;
  currentJing: string;
  currentQi: string;
  currentShen: string;
  currentYin: string;
  currentYang: string;
  currentDao: string;
}

type CharacterXianxiaVitalsField = Exclude<keyof CharacterXianxiaVitalsDraft, "expectedRevision">;

interface CharacterXianxiaActiveStateDraft {
  expectedRevision: number;
  activeStanceName: string;
  activeAuraName: string;
}

interface CharacterXianxiaInventoryDraft {
  name: string;
  quantity: string;
  itemNature: string;
  itemType: string;
  notes: string;
  tags: string;
  catalogRef: string;
  equippable: boolean;
  isEquipped: boolean;
}

interface CharacterNotesDraft {
  expectedRevision: number;
  notes: string;
}

interface CharacterEquipmentDraft {
  isEquipped: boolean;
  isAttuned: boolean;
  weaponWieldMode: string;
}

interface DetailFact {
  label: string;
  value: string;
}

interface CharacterDetailDialogState {
  eyebrow: string;
  title: string;
  html: string;
  notes?: string;
  href?: string;
  facts?: DetailFact[];
  badges?: string[];
}

type CharacterSection =
  | "overview"
  | "quick-reference"
  | "martial-arts"
  | "resources"
  | "spells"
  | "techniques"
  | "equipment"
  | "inventory"
  | "abilities"
  | "skills"
  | "personal"
  | "notes";
type PaneName = "session" | "character" | "dm";
type ArticleMode = "manual" | "upload" | "wiki";

interface ApiClientContextValue {
  apiClient: CampaignApiClient;
  apiToken: string;
  setApiToken: (token: string) => void;
  authRequired: boolean;
  setAuthRequired: (required: boolean) => void;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2500,
      refetchOnWindowFocus: false,
    },
  },
});

const ApiClientContext = createContext<ApiClientContextValue | null>(null);

function useApiClient(): ApiClientContextValue {
  const context = useContext(ApiClientContext);
  if (context === null) {
    throw new Error("CampaignApiClient context is missing.");
  }
  return context;
}

function isAuthError(error: unknown): boolean {
  return isApiError(error) && error.status === 401;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
}

function readString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function readNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function draftKey(...parts: Array<string | number | null | undefined>): string {
  return parts.map((part) => String(part ?? "")).join("::");
}

function collectPresentedSpells(character: CharacterRecord | undefined): CharacterPresentedSpell[] {
  const spellcasting = character?.presented_spellcasting;
  const sections =
    spellcasting?.current_row_sections?.length
      ? spellcasting.current_row_sections
      : spellcasting?.row_sections ?? [];
  const spells: CharacterPresentedSpell[] = [];
  const seen = new Set<string>();

  const addSpell = (spell: CharacterPresentedSpell) => {
    const key = draftKey(spell.class_row_id, spell.name, spell.level_label).toLowerCase();
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    spells.push(spell);
  };

  for (const section of sections) {
    for (const spell of section.spells ?? []) {
      addSpell(spell);
    }
    for (const levelSection of section.spell_level_sections ?? []) {
      for (const group of levelSection.groups ?? []) {
        for (const spell of group.spells ?? []) {
          addSpell(spell);
        }
      }
    }
  }

  return spells;
}

function spellDetailFacts(spell: CharacterPresentedSpell): DetailFact[] {
  const levelAndSchool = [spell.level_label, spell.school ? `(${spell.school})` : ""].filter(Boolean).join(" ");
  return [
    { label: "Level", value: levelAndSchool },
    { label: "Casting time", value: spell.casting_time },
    { label: "Range", value: spell.range },
    { label: "Duration", value: spell.duration },
    { label: "Components", value: spell.components },
    { label: "Save / attack", value: spell.save_or_hit },
  ].filter((fact) => fact.value && fact.value !== "--");
}

function characterSystem(character: CharacterRecord | undefined): string {
  return readString(character?.definition?.system, "DND-5E");
}

function isDndCharacter(character: CharacterRecord | undefined): boolean {
  return characterSystem(character).toLowerCase() === "dnd-5e";
}

function isXianxiaCharacter(character: CharacterRecord | undefined): boolean {
  return characterSystem(character).toLowerCase() === "xianxia";
}

const dndCharacterSections: Array<{ id: CharacterSection; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "resources", label: "Resources" },
  { id: "spells", label: "Spells" },
  { id: "equipment", label: "Equipment" },
  { id: "inventory", label: "Inventory" },
  { id: "abilities", label: "Abilities and Skills" },
  { id: "notes", label: "Notes" },
];

const xianxiaCharacterSections: Array<{ id: CharacterSection; label: string }> = [
  { id: "quick-reference", label: "Quick Reference" },
  { id: "martial-arts", label: "Martial Arts" },
  { id: "techniques", label: "Techniques" },
  { id: "resources", label: "Resources" },
  { id: "skills", label: "Skills" },
  { id: "equipment", label: "Equipment" },
  { id: "inventory", label: "Inventory" },
  { id: "personal", label: "Personal" },
  { id: "notes", label: "Notes" },
];

const xianxiaVitalsFields: Array<{ key: CharacterXianxiaVitalsField; label: string }> = [
  { key: "currentHp", label: "Current HP" },
  { key: "tempHp", label: "Temp HP" },
  { key: "currentStance", label: "Current Stance" },
  { key: "tempStance", label: "Temp Stance" },
  { key: "currentJing", label: "Jing" },
  { key: "currentQi", label: "Qi" },
  { key: "currentShen", label: "Shen" },
  { key: "currentYin", label: "Yin" },
  { key: "currentYang", label: "Yang" },
  { key: "currentDao", label: "Dao" },
];

function joinDisplay(values: Array<string | number | null | undefined>): string {
  return values.map((value) => String(value ?? "").trim()).filter(Boolean).join(" | ");
}

function normalizeTagsInput(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function xianxiaInventoryDraftFromItem(item?: CharacterXianxiaInventoryItem): CharacterXianxiaInventoryDraft {
  return {
    name: item?.name ?? "",
    quantity: String(item?.quantity ?? 1),
    itemNature: item?.item_nature || "Mundane",
    itemType: item?.item_type || "Miscellaneous",
    notes: item?.notes ?? "",
    tags: (item?.tags ?? []).join(", "),
    catalogRef: item?.catalog_ref ?? "",
    equippable: Boolean(item?.equippable),
    isEquipped: Boolean(item?.is_equipped),
  };
}

function xianxiaInventoryPayloadFromDraft(draft: CharacterXianxiaInventoryDraft): CharacterXianxiaInventoryItemPayload {
  const quantity = Number(draft.quantity);
  return {
    name: draft.name.trim(),
    quantity: Number.isFinite(quantity) ? quantity : 1,
    item_nature: draft.itemNature.trim() || "Mundane",
    item_type: draft.itemType.trim() || "Miscellaneous",
    notes: draft.notes.trim(),
    tags: normalizeTagsInput(draft.tags),
    catalog_ref: draft.catalogRef.trim(),
    equippable: draft.equippable,
    is_equipped: draft.isEquipped,
  };
}

function getApiErrorMessage(error: unknown): ApiMessageEnvelope | null {
  if (isApiError(error)) {
    return { status: error.status, message: error.message };
  }
  if (error instanceof Error) {
    return { status: 0, message: error.message };
  }
  return null;
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "N/A";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function resolveArticleImage(slug: string, article: SessionArticle): string {
  if (article.image?.url) {
    return article.image.url;
  }
  return `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/${article.id}/image`;
}

function renderArticleBody(article: SessionArticle): JSX.Element {
  if (article.body_format === "html") {
    return <div className="article-body html-body" dangerouslySetInnerHTML={{ __html: article.body_markdown }} />;
  }
  return <pre className="article-body markdown-body">{article.body_markdown}</pre>;
}

function CharacterDetailDialog({
  detail,
  onClose,
}: {
  detail: CharacterDetailDialogState | null;
  onClose: () => void;
}) {
  if (!detail) {
    return null;
  }
  return (
    <div className="detail-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="detail-modal"
        role="dialog"
        aria-modal="true"
        aria-label={detail.title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="detail-modal-header">
          <div>
            <p className="meta">{detail.eyebrow}</p>
            <h3>{detail.title}</h3>
          </div>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </header>
        {detail.badges?.length ? (
          <div className="badge-list">
            {detail.badges.map((badge) => (
              <span className="meta-badge" key={badge}>
                {badge}
              </span>
            ))}
          </div>
        ) : null}
        {detail.facts?.length ? (
          <dl className="detail-facts">
            {detail.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {detail.href ? (
          <p className="meta">
            <a href={detail.href}>Open source entry</a>
          </p>
        ) : null}
        {detail.notes ? <p>{detail.notes}</p> : null}
        {detail.html ? (
          <div className="article-body html-body detail-html" dangerouslySetInnerHTML={{ __html: detail.html }} />
        ) : (
          <p className="meta">No linked detail text is available yet.</p>
        )}
      </section>
    </div>
  );
}

function ApiErrorNotice({
  isLoading,
  message,
  onAuth,
}: {
  isLoading: boolean;
  message: ApiMessageEnvelope | null;
  onAuth: () => void;
}) {
  if (isLoading) {
    return <p className="status status-neutral">Loading ...</p>;
  }
  if (!message) {
    return null;
  }
  if (message.status === 401) {
    return (
      <p className="status status-error">
        {message.message}
        <button type="button" className="link-like-button" onClick={onAuth}>
          Open sign-in
        </button>
      </p>
    );
  }
  return <p className="status status-error">{message.message}</p>;
}

function AuthNotice() {
  const { authRequired, setApiToken } = useApiClient();
  const signInHref = `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;

  if (!authRequired) {
    return null;
  }

  return (
    <section className="panel auth-notice">
      <h3>Authentication required</h3>
      <p className="status status-error">
        Your cookie or API token did not authenticate this request. Sign in to restore session.
      </p>
      <a className="button button-secondary" href={signInHref}>
        Sign in
      </a>
      <button type="button" className="button" onClick={() => setApiToken("")}>
        Continue without token
      </button>
    </section>
  );
}

function AppShell() {
  const [apiToken, setApiToken] = useState(() => {
    try {
      return localStorage.getItem("cpw-pilot-api-token") || "";
    } catch {
      return "";
    }
  });
  const [authRequired, setAuthRequired] = useState(false);
  const hasMounted = useRef(false);

  const apiClient = useMemo(() => {
    return new CampaignApiClient({
      bearerToken: apiToken,
    });
  }, [apiToken]);

  useEffect(() => {
    if (!hasMounted.current) {
      hasMounted.current = true;
      return;
    }
    void queryClient.invalidateQueries();
  }, [apiToken]);

  const setStoredToken = (next: string) => {
    const trimmed = next.trim();
    setApiToken(trimmed);
    try {
      if (trimmed) {
        localStorage.setItem("cpw-pilot-api-token", trimmed);
      } else {
        localStorage.removeItem("cpw-pilot-api-token");
      }
    } catch {
      // localStorage may be unavailable in private mode.
    }
    if (authRequired) {
      setAuthRequired(false);
    }
  };

  return (
    <ApiClientContext.Provider value={{ apiClient, apiToken, setApiToken: setStoredToken, authRequired, setAuthRequired }}>
      <div className="session-shell">
        <header className="topbar">
          <div className="brand-block">
            <Link to="/" className="brand-link">
              Session Companion
            </Link>
            <p className="subtitle">app-next / /app-next/campaigns/.../session</p>
          </div>
          <label className="token-row" htmlFor="pilot-api-token">
            <span>API token (optional)</span>
            <input
              id="pilot-api-token"
              type="password"
              value={apiToken}
              placeholder="Bearer token for API-only testing"
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                setStoredToken(event.currentTarget.value);
              }}
            />
          </label>
          <a
            className="button button-secondary sign-in-link"
            href={`/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`}
          >
            Sign in
          </a>
        </header>
        <AuthNotice />
        <main className="main-shell">
          <Outlet />
        </main>
      </div>
    </ApiClientContext.Provider>
  );
}

function CampaignListPage() {
  const { apiClient, setAuthRequired } = useApiClient();

  const appQuery = useQuery({
    queryKey: ["app"],
    queryFn: () => apiClient.getAppState(),
    retry: false,
  });

  const campaignsQuery = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiClient.getCampaigns(),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(appQuery.error) || isAuthError(campaignsQuery.error)) {
      setAuthRequired(true);
    }
  }, [appQuery.error, campaignsQuery.error, setAuthRequired]);

  const appError = getApiErrorMessage(appQuery.error);
  const campaignError = getApiErrorMessage(campaignsQuery.error);
  const campaigns: CampaignEntry[] = campaignsQuery.data?.campaigns ?? [];

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Available Campaigns</h2>
      </div>
      <ApiErrorNotice
        isLoading={appQuery.isLoading || campaignsQuery.isLoading}
        message={appError ?? campaignError}
        onAuth={() => setAuthRequired(true)}
      />
      {appQuery.data?.app ? (
        <p className="subtitle">
          Runtime: {appQuery.data.app.runtime}
          {appQuery.data.app.version ? ` - ${appQuery.data.app.version}` : ""}
        </p>
      ) : null}
      <div className="campaign-grid">
        {campaigns.map((entry) => (
          <article className="card" key={entry.campaign.slug}>
            <h3>{entry.campaign.title}</h3>
            <p className="subtitle">{entry.campaign.slug}</p>
            <p>{entry.campaign.summary}</p>
            <p>
              <strong>System:</strong> {entry.campaign.system}
            </p>
            <p>
              <strong>Role:</strong> {entry.role}
            </p>
            <Link to="/campaigns/$campaignSlug/session" params={{ campaignSlug: entry.campaign.slug }} className="button">
              Open Session
            </Link>
          </article>
        ))}
        {!appQuery.isLoading && !campaignsQuery.isLoading && !campaigns.length && !campaignError ? (
          <p className="status status-neutral">No campaigns are visible to this account.</p>
        ) : null}
      </div>
    </section>
  );
}
function SessionArticlesPanel({
  campaignSlug,
  articles,
  title,
  emptyText,
}: {
  campaignSlug: string;
  articles: SessionArticle[];
  title: string;
  emptyText: string;
}) {
  return (
    <article className="panel panel-nested">
      <div className="panel-header">
        <h3>{title}</h3>
        <span className="pill">{articles.length} article(s)</span>
      </div>
      {articles.length ? (
        <div className="article-stack">
          {articles.map((article) => (
            <details className="article-card" key={article.id}>
              <summary>
                <strong>{article.title}</strong>
                <span className="article-kind">{article.source_kind || "unclassified"}</span>
              </summary>
              <div className="article-meta">
                {article.image ? (
                  <img
                    className="article-image"
                    src={resolveArticleImage(campaignSlug, article)}
                    alt={article.image.alt_text || "Session article image"}
                  />
                ) : null}
                {article.created_at ? <time>{formatTimestamp(article.created_at)}</time> : null}
              </div>
              {renderArticleBody(article)}
            </details>
          ))}
        </div>
      ) : (
        <p className="status status-neutral">{emptyText}</p>
      )}
    </article>
  );
}

function SessionPaneChat({
  payload,
  messageDraft,
  setMessageDraft,
  sendError,
  onSend,
  isSending,
}: {
  payload: SessionPayload | undefined;
  messageDraft: string;
  setMessageDraft: (value: string) => void;
  sendError: string | null;
  onSend: (event: FormEvent<HTMLFormElement>) => void;
  isSending: boolean;
}) {
  const messages: SessionMessage[] = payload?.messages ?? [];

  return (
    <article className="panel panel-nested">
      <div className="panel-header">
        <h3>Session chat</h3>
        <span className="pill">{payload?.active_session ? `Session #${payload.active_session.id}` : "No active session"}</span>
      </div>
      <div className="chat-list">
        {messages.length ? (
          messages.map((message) => (
            <article key={message.id} className="chat-item">
              <p className="chat-meta">
                {message.author_display_name} - {formatTimestamp(message.created_at)}
              </p>
              <p>{message.body_text}</p>
            </article>
          ))
        ) : (
          <p className="status status-neutral">No messages yet.</p>
        )}
      </div>
      {payload?.permissions.can_post_messages ? (
        <form onSubmit={onSend} className="chat-composer">
          <label htmlFor="session-message-body" className="chat-label">
            Post Session Message
          </label>
          <textarea
            id="session-message-body"
            rows={5}
            value={messageDraft}
            placeholder="Type chat text"
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setMessageDraft(event.currentTarget.value);
            }}
          />
          <div className="chat-actions">
            <button type="submit" disabled={isSending || payload?.active_session === null}>
              {isSending ? "Sending..." : "Send"}
            </button>
            <span>{payload?.permissions.can_manage_session ? "DM view" : "Player view"}</span>
          </div>
          {sendError ? <p className="status status-error">{sendError}</p> : null}
        </form>
      ) : (
        <p className="status status-neutral">You do not have permission to post messages.</p>
      )}
    </article>
  );
}

function SessionPaneWikiLookup({
  canShow,
  query,
  setQuery,
  queryStatus,
  results,
  onSearch,
  previewRef,
  onSelectPreview,
  previewLoading,
  previewHtml,
  previewError,
  clearStatus,
}: {
  canShow: boolean;
  query: string;
  setQuery: (value: string) => void;
  queryStatus: string | null;
  results: SessionWikiLookupSearchResult[];
  onSearch: (event: FormEvent<HTMLFormElement>) => void;
  previewRef: string | null;
  onSelectPreview: (pageRef: string) => void;
  previewLoading: boolean;
  previewHtml: string;
  previewError: string | null;
  clearStatus: () => void;
}) {
  if (!canShow) {
    return <p className="status status-neutral">This campaign does not expose wiki lookup.</p>;
  }

  return (
    <article className="panel panel-nested">
      <h3>Player wiki lookup</h3>
      <form onSubmit={onSearch} className="wiki-search">
        <label htmlFor="wiki-search-query" className="chat-label">
          Search published pages / systems
        </label>
        <div className="search-row">
          <input
            id="wiki-search-query"
            value={query}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setQuery(event.currentTarget.value);
              clearStatus();
            }}
            placeholder="harbor, rules, artifact"
          />
          <button type="submit">Search</button>
        </div>
      </form>
      {queryStatus ? <p className="status status-neutral">{queryStatus}</p> : null}
      {results.length ? (
        <div className="wiki-result-stack">
          {results.map((result) => {
            const pageRef = result.page_ref || result.source_ref || "";
            return (
              <button
                className="wiki-result-row"
                type="button"
                key={pageRef}
                onClick={() => onSelectPreview(pageRef)}
                disabled={!pageRef}
              >
                <strong>{result.title}</strong>
                <p>{result.subtitle}</p>
              </button>
            );
          })}
        </div>
      ) : null}
      {previewRef ? (
        <div className="wiki-preview">
          <div className="preview-title">Preview: {previewRef}</div>
          {previewLoading ? <p className="status status-neutral">Loading preview ...</p> : null}
          {previewError ? <p className="status status-error">{previewError}</p> : null}
          {previewHtml ? <div className="wiki-preview-html" dangerouslySetInnerHTML={{ __html: previewHtml }} /> : null}
        </div>
      ) : null}
    </article>
  );
}

function readBinaryAsBase64(file: File, callback: (payload: EmbeddedImageInput | null) => void): void {
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    const data = reader.result;
    if (typeof data !== "string") {
      callback(null);
      return;
    }
    callback({
      filename: file.name,
      data_base64: data.split(",", 2)[1] || "",
      media_type: file.type || "application/octet-stream",
    });
  });
  reader.addEventListener("error", () => callback(null));
  reader.readAsDataURL(file);
}

function DmArticleCreator({
  mode,
  setMode,
  sourceQuery,
  setSourceQuery,
  sourceStatus,
  setSourceStatus,
  sourceResults,
  selectedSourceRef,
  setSelectedSourceRef,
  manualDraft,
  setManualDraft,
  uploadDraft,
  setUploadDraft,
  onSearchSources,
  onCreate,
  isCreating,
}: {
  mode: ArticleMode;
  setMode: (mode: ArticleMode) => void;
  sourceQuery: string;
  setSourceQuery: (value: string) => void;
  sourceStatus: string | null;
  setSourceStatus: (value: string | null) => void;
  sourceResults: SessionArticleSourceResult[];
  selectedSourceRef: string;
  setSelectedSourceRef: (value: string) => void;
  manualDraft: { title: string; body: string };
  setManualDraft: (state: { title: string; body: string }) => void;
  uploadDraft: { filename: string; markdown: string; image: EmbeddedImageInput | null };
  setUploadDraft: (state: { filename: string; markdown: string; image: EmbeddedImageInput | null }) => void;
  onSearchSources: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCreate: (payload: SessionArticleCreatePayload) => void;
  isCreating: boolean;
}) {
  const instructions =
    mode === "manual"
      ? "Use title and markdown body and create an unrevealed article."
      : mode === "upload"
        ? "Upload mode needs a filename and markdown body."
        : "Search and select a source, then pull into staged articles.";

  return (
    <article className="panel panel-nested">
      <h3>Stage an article</h3>
      <div className="segmented">
        <button
          type="button"
          className={mode === "manual" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("manual")}
        >
          Manual
        </button>
        <button
          type="button"
          className={mode === "upload" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("upload")}
        >
          Upload
        </button>
        <button
          type="button"
          className={mode === "wiki" ? "segmented-button active" : "segmented-button"}
          onClick={() => setMode("wiki")}
        >
          Wiki / Systems
        </button>
      </div>
      <p className="status status-neutral">{instructions}</p>

      {mode === "manual" ? (
        <section className="session-form">
          <label htmlFor="dm-manual-title" className="chat-label">Title</label>
          <input
            id="dm-manual-title"
            value={manualDraft.title}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setManualDraft({ ...manualDraft, title: event.currentTarget.value });
            }}
          />
          <label htmlFor="dm-manual-body" className="chat-label">Markdown body</label>
          <textarea
            id="dm-manual-body"
            rows={8}
            value={manualDraft.body}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setManualDraft({ ...manualDraft, body: event.currentTarget.value });
            }}
          />
          <button
            type="button"
            className="button"
            disabled={isCreating || !manualDraft.title.trim() || !manualDraft.body.trim()}
            onClick={() =>
              onCreate({
                mode: "manual",
                title: manualDraft.title.trim(),
                body_markdown: manualDraft.body,
              } satisfies SessionArticleCreatePayloadManual)
            }
          >
            {isCreating ? "Creating..." : "Create"}
          </button>
        </section>
      ) : null}

      {mode === "upload" ? (
        <section className="session-form">
          <label htmlFor="dm-upload-filename" className="chat-label">Source filename</label>
          <input
            id="dm-upload-filename"
            value={uploadDraft.filename}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setUploadDraft({ ...uploadDraft, filename: event.currentTarget.value });
            }}
            placeholder="notes.md"
          />
          <label htmlFor="dm-upload-markdown" className="chat-label">Markdown text</label>
          <textarea
            id="dm-upload-markdown"
            rows={8}
            value={uploadDraft.markdown}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
              setUploadDraft({ ...uploadDraft, markdown: event.currentTarget.value });
            }}
          />
          <label className="chat-label">Referenced image (optional)</label>
          <input
            type="file"
            accept=".png,.jpg,.jpeg,.webp,.gif"
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              const file = event.currentTarget.files?.item(0);
              if (!file) {
                setUploadDraft({ ...uploadDraft, image: null });
                return;
              }
              readBinaryAsBase64(file, (payload) => {
                setUploadDraft({ ...uploadDraft, image: payload });
              });
            }}
          />
          <button
            type="button"
            disabled={isCreating || !uploadDraft.filename.trim() || !uploadDraft.markdown.trim()}
            onClick={() =>
              onCreate({
                mode: "upload",
                filename: uploadDraft.filename.trim(),
                markdown_text: uploadDraft.markdown,
                referenced_image: uploadDraft.image ?? undefined,
              } satisfies SessionArticleCreatePayloadUpload)
            }
          >
            {isCreating ? "Creating..." : "Create"}
          </button>
        </section>
      ) : null}

      {mode === "wiki" ? (
        <section className="session-form">
          <form onSubmit={onSearchSources} className="wiki-search">
            <label htmlFor="dm-wiki-search" className="chat-label">Search wiki / systems</label>
            <div className="search-row">
              <input
                id="dm-wiki-search"
                value={sourceQuery}
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setSourceQuery(event.currentTarget.value);
                  setSourceStatus(null);
                  setSelectedSourceRef("");
                }}
              />
              <button type="submit">Search</button>
            </div>
          </form>
          {sourceStatus ? <p className="status status-neutral">{sourceStatus}</p> : null}
          {sourceResults.length ? (
            <div className="wiki-result-stack">
              {sourceResults.map((result) => (
                <button
                  key={result.source_ref}
                  type="button"
                  className="wiki-result-row"
                  onClick={() => setSelectedSourceRef(result.source_ref)}
                >
                  <strong>{result.title}</strong>
                  <p>{result.subtitle}</p>
                </button>
              ))}
            </div>
          ) : null}
          <div className="wiki-selection">
            <p className="status status-neutral">{selectedSourceRef ? `Source selected: ${selectedSourceRef}` : "No source selected"}</p>
            <button
              type="button"
              disabled={isCreating || !selectedSourceRef}
              onClick={() =>
                onCreate({
                  mode: "wiki",
                  source_ref: selectedSourceRef,
                } satisfies SessionArticleCreatePayloadWiki)
              }
            >
              {isCreating ? "Creating..." : "Pull source"}
            </button>
          </div>
        </section>
      ) : null}
    </article>
  );
}
function SessionPane({
  campaignSlug,
  payload,
  refetch,
  setAuthRequired,
}: {
  campaignSlug: string;
  payload: SessionPayload | undefined;
  refetch: () => void;
  setAuthRequired: (required: boolean) => void;
}) {
  const { apiClient } = useApiClient();
  const [messageDraft, setMessageDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);

  const [wikiQuery, setWikiQuery] = useState("");
  const [wikiStatus, setWikiStatus] = useState<string | null>(null);
  const [wikiResults, setWikiResults] = useState<SessionWikiLookupSearchResult[]>([]);
  const [wikiPreviewRef, setWikiPreviewRef] = useState<string | null>(null);
  const [wikiPreviewLoading, setWikiPreviewLoading] = useState(false);
  const [wikiPreviewHtml, setWikiPreviewHtml] = useState("");
  const [wikiPreviewError, setWikiPreviewError] = useState<string | null>(null);

  const postMessage = useMutation({
    mutationFn: (body: string) => apiClient.postSessionMessage(campaignSlug, body),
    onSuccess: () => {
      setMessageDraft("");
      setSendError(null);
      refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSendError(apiErrorMessage(error));
    },
  });

  const doSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = wikiQuery.trim();
    if (!query) {
      setWikiStatus("Enter a search query first.");
      return;
    }
    setWikiStatus("Searching ...");
    try {
      const result = await apiClient.searchPlayerSessionWiki(campaignSlug, query);
      setWikiResults(result.results);
      setWikiStatus(result.message || "Search complete.");
      if (!result.results.length) {
        setWikiPreviewRef(null);
        setWikiPreviewHtml("");
      }
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setWikiResults([]);
      setWikiStatus(null);
      setWikiPreviewError(apiErrorMessage(error));
    }
  };

  const doPreview = async (pageRef: string) => {
    setWikiPreviewRef(pageRef);
    setWikiPreviewLoading(true);
    setWikiPreviewError(null);
    try {
      const response: SessionWikiLookupPreviewResponse = await apiClient.previewPlayerSessionWiki(campaignSlug, pageRef);
      setWikiPreviewHtml(response.preview_html || "");
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setWikiPreviewHtml("");
      setWikiPreviewError(apiErrorMessage(error));
    } finally {
      setWikiPreviewLoading(false);
    }
  };

  const sendMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = messageDraft.trim();
    if (!body) {
      setSendError("Type a message first.");
      return;
    }
    if (!payload?.permissions.can_post_messages) {
      setSendError("You do not have permission to post messages.");
      return;
    }
    if (!payload?.active_session) {
      setSendError("No active session.");
      return;
    }
    postMessage.mutate(body);
  };

  const canShowWikiLookup = payload?.permissions.can_access_wiki_lookup ?? true;

  return (
    <div className="session-pane-content">
      <section className="panel">
        <div className="panel-header">
          <h2>Session: {payload?.campaign.title ?? campaignSlug}</h2>
          <span className="pill">Player</span>
        </div>
        <div className="status-row">
          <article className="stat-card">
            <h3>Session</h3>
            <p>{payload?.active_session ? payload.active_session.status : "inactive"}</p>
          </article>
          <article className="stat-card">
            <h3>Messages</h3>
            <p>{payload?.messages.length ?? 0}</p>
          </article>
          <article className="stat-card">
            <h3>Session ID</h3>
            <p>{payload?.active_session?.id ?? "none"}</p>
          </article>
        </div>
      </section>

      <div className="split-grid">
        <SessionArticlesPanel
          campaignSlug={campaignSlug}
          articles={payload?.revealed_articles ?? []}
          title="Revealed articles"
          emptyText="No revealed articles yet."
        />
        <SessionPaneWikiLookup
          canShow={canShowWikiLookup}
          query={wikiQuery}
          setQuery={setWikiQuery}
          queryStatus={wikiStatus}
          results={wikiResults}
          onSearch={doSearch}
          previewRef={wikiPreviewRef}
          onSelectPreview={doPreview}
          previewLoading={wikiPreviewLoading}
          previewHtml={wikiPreviewHtml}
          previewError={wikiPreviewError}
          clearStatus={() => {
            setWikiPreviewError(null);
            setWikiStatus(null);
          }}
        />
      </div>
      <SessionPaneChat
        payload={payload}
        messageDraft={messageDraft}
        setMessageDraft={setMessageDraft}
        sendError={sendError}
        onSend={sendMessage}
        isSending={postMessage.isPending}
      />
    </div>
  );
}

function CharacterPane({ campaignSlug }: { campaignSlug: string }) {
  const { apiClient, setAuthRequired } = useApiClient();
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [activeCharacterSection, setActiveCharacterSection] = useState<CharacterSection>("overview");
  const [vitalsDraft, setVitalsDraft] = useState<CharacterVitalsDraft>({
    expectedRevision: 0,
    currentHp: "",
    tempHp: "",
  });
  const [xianxiaVitalsDraft, setXianxiaVitalsDraft] = useState<CharacterXianxiaVitalsDraft>({
    expectedRevision: 0,
    currentHp: "",
    tempHp: "",
    currentStance: "",
    tempStance: "",
    currentJing: "",
    currentQi: "",
    currentShen: "",
    currentYin: "",
    currentYang: "",
    currentDao: "",
  });
  const [xianxiaActiveDraft, setXianxiaActiveDraft] = useState<CharacterXianxiaActiveStateDraft>({
    expectedRevision: 0,
    activeStanceName: "",
    activeAuraName: "",
  });
  const [notesDraft, setNotesDraft] = useState<CharacterNotesDraft>({ expectedRevision: 0, notes: "" });
  const [resourceDrafts, setResourceDrafts] = useState<Record<string, string>>({});
  const [spellSlotDrafts, setSpellSlotDrafts] = useState<Record<string, string>>({});
  const [inventoryDrafts, setInventoryDrafts] = useState<Record<string, string>>({});
  const [equipmentDrafts, setEquipmentDrafts] = useState<Record<string, CharacterEquipmentDraft>>({});
  const [xianxiaInventoryDrafts, setXianxiaInventoryDrafts] = useState<Record<string, CharacterXianxiaInventoryDraft>>({});
  const [newXianxiaInventoryDraft, setNewXianxiaInventoryDraft] = useState<CharacterXianxiaInventoryDraft>(
    xianxiaInventoryDraftFromItem(),
  );
  const [arcaneArmorDraft, setArcaneArmorDraft] = useState(false);
  const [currencyDraft, setCurrencyDraft] = useState<Record<string, string>>({});
  const [restPreview, setRestPreview] = useState<CharacterRestPreviewResponse["preview"] | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [detailDialog, setDetailDialog] = useState<CharacterDetailDialogState | null>(null);

  const listQuery = useQuery({
    queryKey: ["characters", campaignSlug],
    queryFn: () => apiClient.getCharacters(campaignSlug),
    enabled: Boolean(campaignSlug),
    retry: false,
  });

  const characterList: CharacterSummary[] = listQuery.data?.characters ?? [];

  useEffect(() => {
    if (!selectedSlug && characterList.length > 0) {
      setSelectedSlug(characterList[0].slug);
    }
  }, [characterList, selectedSlug]);

  const detailQuery = useQuery({
    queryKey: ["character-detail", campaignSlug, selectedSlug],
    queryFn: () => {
      if (!selectedSlug) {
        throw new Error("No character selected");
      }
      return apiClient.getCharacter(campaignSlug, selectedSlug);
    },
    enabled: Boolean(campaignSlug) && Boolean(selectedSlug),
    retry: false,
  });

  useEffect(() => {
    if (listQuery.error && isAuthError(listQuery.error)) {
      setAuthRequired(true);
    }
  }, [listQuery.error, setAuthRequired]);

  useEffect(() => {
    if (detailQuery.error && isAuthError(detailQuery.error)) {
      setAuthRequired(true);
    }
  }, [detailQuery.error, setAuthRequired]);

  useEffect(() => {
    if (!detailDialog) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDetailDialog(null);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [detailDialog]);

  useEffect(() => {
    if (!detailQuery.data) {
      return;
    }
    const character = detailQuery.data.character;
    const state = asRecord(character.state_record.state);
    const vitals = asRecord(state.vitals);
    const xianxiaState = asRecord(state.xianxia);
    const xianxiaVitals = asRecord(xianxiaState.vitals);
    const xianxiaEnergies = asRecord(xianxiaState.energies);
    const xianxiaYinYang = asRecord(xianxiaState.yin_yang);
    const xianxiaDao = asRecord(xianxiaState.dao);
    const presentedXianxia = character.presented_xianxia;
    const notes = asRecord(state.notes);
    const nextResourceDrafts: Record<string, string> = {};
    for (const resource of asRecordArray(state.resources)) {
      const id = readString(resource.id);
      if (id) {
        nextResourceDrafts[id] = String(readNumber(resource.current));
      }
    }
    const nextSpellSlotDrafts: Record<string, string> = {};
    for (const slot of asRecordArray(state.spell_slots)) {
      const key = draftKey(readNumber(slot.level), readString(slot.slot_lane_id));
      nextSpellSlotDrafts[key] = String(readNumber(slot.used));
    }
    const nextInventoryDrafts: Record<string, string> = {};
    for (const item of asRecordArray(state.inventory)) {
      const id = readString(item.id);
      if (id) {
        nextInventoryDrafts[id] = String(readNumber(item.quantity, 1));
      }
    }
    const nextXianxiaInventoryDrafts: Record<string, CharacterXianxiaInventoryDraft> = {};
    for (const item of presentedXianxia?.inventory?.quantities ?? []) {
      if (item.id) {
        nextXianxiaInventoryDrafts[item.id] = xianxiaInventoryDraftFromItem(item);
        nextInventoryDrafts[item.id] = String(readNumber(item.quantity, 1));
      }
    }
    const equipmentState = detailQuery.data.character.equipment_state;
    const nextEquipmentDrafts: Record<string, CharacterEquipmentDraft> = {};
    for (const item of equipmentState?.rows ?? []) {
      if (item.id) {
        nextEquipmentDrafts[item.id] = {
          isEquipped: Boolean(item.is_equipped),
          isAttuned: Boolean(item.is_attuned),
          weaponWieldMode: item.weapon_wield_mode || "",
        };
      }
    }
    setEquipmentDrafts(nextEquipmentDrafts);
    setXianxiaInventoryDrafts(nextXianxiaInventoryDrafts);
    setArcaneArmorDraft(Boolean((detailQuery.data.character.arcane_armor_state ?? equipmentState?.arcane_armor_state)?.enabled));
    const currency = isXianxiaCharacter(character) ? asRecord(xianxiaState.currency) : asRecord(state.currency);
    const nextCurrencyDraft: Record<string, string> = {};
    for (const key of ["cp", "sp", "ep", "gp", "pp", "coin", "supply", "spirit_stones"]) {
      if (currency[key] !== undefined) {
        nextCurrencyDraft[key] = String(readNumber(currency[key]));
      }
    }
    setVitalsDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      currentHp: String(readNumber(vitals.current_hp, 0)),
      tempHp: String(readNumber(vitals.temp_hp, 0)),
    });
    setXianxiaVitalsDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      currentHp: String(readNumber(vitals.current_hp, readNumber(xianxiaVitals.current_hp, 0))),
      tempHp: String(readNumber(vitals.temp_hp, readNumber(xianxiaVitals.temp_hp, 0))),
      currentStance: String(readNumber(xianxiaVitals.current_stance, 0)),
      tempStance: String(readNumber(xianxiaVitals.temp_stance, 0)),
      currentJing: String(readNumber(asRecord(xianxiaEnergies.jing).current, 0)),
      currentQi: String(readNumber(asRecord(xianxiaEnergies.qi).current, 0)),
      currentShen: String(readNumber(asRecord(xianxiaEnergies.shen).current, 0)),
      currentYin: String(readNumber(xianxiaYinYang.yin_current, 0)),
      currentYang: String(readNumber(xianxiaYinYang.yang_current, 0)),
      currentDao: String(readNumber(xianxiaDao.current, 0)),
    });
    setXianxiaActiveDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      activeStanceName: presentedXianxia?.active_state?.stance?.name ?? "",
      activeAuraName: presentedXianxia?.active_state?.aura?.name ?? "",
    });
    setNotesDraft({
      expectedRevision: detailQuery.data.character.state_record.revision,
      notes: readString(notes.player_notes_markdown),
    });
    setResourceDrafts(nextResourceDrafts);
    setSpellSlotDrafts(nextSpellSlotDrafts);
    setInventoryDrafts(nextInventoryDrafts);
    setCurrencyDraft(nextCurrencyDraft);
  }, [detailQuery.data?.character.state_record.revision, selectedSlug]);

  const detail = detailQuery.data as CharacterDetailResponse | undefined;
  const detailRecord = detail?.character;
  const selected = characterList.find((item) => item.slug === selectedSlug);
  const permissions = detailRecord?.permissions;
  const canEdit = Boolean(permissions?.can_edit_session);
  const isDnd = isDndCharacter(detailRecord);
  const isXianxia = isXianxiaCharacter(detailRecord);
  const definition = asRecord(detailRecord?.definition);
  const profile = asRecord(definition.profile);
  const stats = asRecord(definition.stats);
  const spellcasting = asRecord(definition.spellcasting);
  const state = asRecord(detailRecord?.state_record.state);
  const xianxiaState = asRecord(state.xianxia);
  const vitals = asRecord(state.vitals);
  const resources = asRecordArray(state.resources);
  const spellSlots = asRecordArray(state.spell_slots);
  const inventory = asRecordArray(state.inventory);
  const currency = isXianxia ? asRecord(xianxiaState.currency) : asRecord(state.currency);
  const notes = asRecord(state.notes);
  const abilityScores = asRecord(stats.ability_scores);
  const spells = asRecordArray(spellcasting.spells);
  const equipmentState = detailRecord?.equipment_state;
  const equipmentRows = equipmentState?.rows ?? [];
  const arcaneArmorState = detailRecord?.arcane_armor_state ?? equipmentState?.arcane_armor_state;
  const revision = detailRecord?.state_record.revision ?? 0;
  const presentedXianxia: CharacterPresentedXianxia = detailRecord?.presented_xianxia ?? {};
  const xianxiaInventory = presentedXianxia.inventory?.quantities ?? [];
  const xianxiaCurrency = presentedXianxia.inventory?.currency ?? [];
  const xianxiaDurability = presentedXianxia.resources?.durability ?? [];
  const xianxiaEnergies = presentedXianxia.resources?.energies ?? [];
  const xianxiaYinYang = presentedXianxia.resources?.yin_yang ?? [];
  const xianxiaDao = presentedXianxia.resources?.dao;
  const xianxiaInsight = presentedXianxia.resources?.insight;
  const presentedSpells = collectPresentedSpells(detailRecord);
  const presentedInventory = detailRecord?.presented_inventory ?? [];
  const presentedInventoryByKey = useMemo(() => {
    const lookup = new Map<string, CharacterPresentedInventoryItem>();
    for (const item of presentedInventory) {
      for (const key of [item.id, item.item_ref]) {
        if (key) {
          lookup.set(key, item);
        }
      }
    }
    return lookup;
  }, [presentedInventory]);

  useEffect(() => {
    if (isXianxia && activeCharacterSection === "overview") {
      setActiveCharacterSection("quick-reference");
    }
    if (isDnd && activeCharacterSection === "quick-reference") {
      setActiveCharacterSection("overview");
    }
  }, [activeCharacterSection, isDnd, isXianxia]);

  const handleMutationSuccess = (response: { character: CharacterRecord }, message: string) => {
    if (selectedSlug) {
      queryClient.setQueryData<CharacterDetailResponse>(["character-detail", campaignSlug, selectedSlug], {
        ok: true,
        character: response.character,
      });
    }
    void listQuery.refetch();
    setStatusMessage(message);
    setErrorMessage(null);
  };

  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage(null);
    setErrorMessage(apiErrorMessage(error));
  };

  const patchVitals = useMutation({
    mutationFn: (payload: CharacterVitalsPatchPayload) =>
      apiClient.patchCharacterVitals(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Vitals saved."),
    onError: handleMutationError,
  });

  const patchResource = useMutation({
    mutationFn: ({ resourceId, payload }: { resourceId: string; payload: CharacterResourcePatchPayload }) =>
      apiClient.patchCharacterResource(campaignSlug, selectedSlug || "", resourceId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Resource saved."),
    onError: handleMutationError,
  });

  const patchSpellSlot = useMutation({
    mutationFn: ({ level, payload }: { level: number; payload: CharacterSpellSlotsPatchPayload }) =>
      apiClient.patchCharacterSpellSlots(campaignSlug, selectedSlug || "", level, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Spell slots saved."),
    onError: handleMutationError,
  });

  const patchInventory = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: CharacterInventoryPatchPayload }) =>
      apiClient.patchCharacterInventory(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory saved."),
    onError: handleMutationError,
  });

  const patchEquipmentState = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: CharacterEquipmentStatePatchPayload }) =>
      apiClient.patchCharacterEquipmentState(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Equipment state saved."),
    onError: handleMutationError,
  });

  const patchFeatureState = useMutation({
    mutationFn: ({ featureKey, payload }: { featureKey: string; payload: CharacterFeatureStatePatchPayload }) =>
      apiClient.patchCharacterFeatureState(campaignSlug, selectedSlug || "", featureKey, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Feature state saved."),
    onError: handleMutationError,
  });

  const patchXianxiaActiveState = useMutation({
    mutationFn: (payload: { expected_revision: number; active_stance_name?: string; active_aura_name?: string }) =>
      apiClient.patchCharacterXianxiaActiveState(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Active Stance and Aura saved."),
    onError: handleMutationError,
  });

  const addXianxiaInventoryItem = useMutation({
    mutationFn: (payload: { expected_revision: number; item: CharacterXianxiaInventoryItemPayload }) =>
      apiClient.addCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => {
      setNewXianxiaInventoryDraft(xianxiaInventoryDraftFromItem());
      handleMutationSuccess(response, "Inventory item added.");
    },
    onError: handleMutationError,
  });

  const patchXianxiaInventoryItem = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: { expected_revision: number; item: CharacterXianxiaInventoryItemPayload } }) =>
      apiClient.patchCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory item saved."),
    onError: handleMutationError,
  });

  const removeXianxiaInventoryItem = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: { expected_revision: number } }) =>
      apiClient.removeCharacterXianxiaInventoryItem(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Inventory item removed."),
    onError: handleMutationError,
  });

  const patchXianxiaInventoryEquipped = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: { expected_revision: number; is_equipped: boolean } }) =>
      apiClient.patchCharacterXianxiaInventoryEquipped(campaignSlug, selectedSlug || "", itemId, payload),
    onSuccess: (response) => handleMutationSuccess(response, "Equipment state saved."),
    onError: handleMutationError,
  });

  const patchCurrency = useMutation({
    mutationFn: (payload: CharacterCurrencyPatchPayload) =>
      apiClient.patchCharacterCurrency(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Currency saved."),
    onError: handleMutationError,
  });

  const patchNotes = useMutation({
    mutationFn: (payload: CharacterNotesPatchPayload) =>
      apiClient.patchCharacterNotes(campaignSlug, selectedSlug || "", payload),
    onSuccess: (response) => handleMutationSuccess(response, "Notes saved."),
    onError: handleMutationError,
  });

  const previewRest = useMutation({
    mutationFn: (restType: "short" | "long") => apiClient.getCharacterRestPreview(campaignSlug, selectedSlug || "", restType),
    onSuccess: (response) => {
      setRestPreview(response.preview);
      setStatusMessage(`${response.preview.label} preview loaded.`);
      setErrorMessage(null);
    },
    onError: handleMutationError,
  });

  const applyRest = useMutation({
    mutationFn: ({ restType, payload }: { restType: "short" | "long"; payload: { expected_revision: number } }) =>
      apiClient.applyCharacterRest(campaignSlug, selectedSlug || "", restType, payload),
    onSuccess: (response: CharacterRestApplyResponse) => {
      setRestPreview(null);
      handleMutationSuccess(response, "Rest applied.");
    },
    onError: handleMutationError,
  });

  const parseNumberInput = (value: string, label: string): number | null => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      setErrorMessage(`Enter a valid ${label}.`);
      setStatusMessage(null);
      return null;
    }
    return parsed;
  };

  const openItemDetail = (item: { name: string; href?: string; description_html?: string; notes?: string }) => {
    setDetailDialog({
      eyebrow: "Item details",
      title: item.name || "Item",
      html: item.description_html || "",
      notes: item.notes || "",
      href: item.href || "",
    });
  };

  const openSpellDetail = (spell: CharacterPresentedSpell) => {
    const source = [spell.source, spell.reference].filter(Boolean).join(" | ");
    setDetailDialog({
      eyebrow: [spell.level_label, spell.school].filter(Boolean).join(" | ") || "Spell details",
      title: spell.name || "Spell",
      html: spell.description_html || "",
      notes: spell.management_note || "",
      href: spell.href || "",
      facts: [...spellDetailFacts(spell), ...(source ? [{ label: "Source", value: source }] : [])],
      badges: spell.badges ?? [],
    });
  };

  const submitVitals = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const currentHp = parseNumberInput(vitalsDraft.currentHp, "current HP");
    const tempHp = parseNumberInput(vitalsDraft.tempHp, "temp HP");

    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (currentHp === null || tempHp === null) {
      return;
    }

    setStatusMessage("Saving...");
    patchVitals.mutate({
      expected_revision: revision,
      current_hp: currentHp,
      temp_hp: tempHp,
    });
  };

  const submitXianxiaVitals = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fields = [
      ["current HP", xianxiaVitalsDraft.currentHp],
      ["temp HP", xianxiaVitalsDraft.tempHp],
      ["current Stance", xianxiaVitalsDraft.currentStance],
      ["temp Stance", xianxiaVitalsDraft.tempStance],
      ["current Jing", xianxiaVitalsDraft.currentJing],
      ["current Qi", xianxiaVitalsDraft.currentQi],
      ["current Shen", xianxiaVitalsDraft.currentShen],
      ["current Yin", xianxiaVitalsDraft.currentYin],
      ["current Yang", xianxiaVitalsDraft.currentYang],
      ["current Dao", xianxiaVitalsDraft.currentDao],
    ] as const;
    const parsed = new Map<string, number>();
    for (const [label, value] of fields) {
      const numberValue = parseNumberInput(value, label);
      if (numberValue === null) {
        return;
      }
      parsed.set(label, numberValue);
    }
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }

    setStatusMessage("Saving...");
    patchVitals.mutate({
      expected_revision: revision,
      current_hp: parsed.get("current HP"),
      temp_hp: parsed.get("temp HP"),
      current_stance: parsed.get("current Stance"),
      temp_stance: parsed.get("temp Stance"),
      current_jing: parsed.get("current Jing"),
      current_qi: parsed.get("current Qi"),
      current_shen: parsed.get("current Shen"),
      current_yin: parsed.get("current Yin"),
      current_yang: parsed.get("current Yang"),
      current_dao: parsed.get("current Dao"),
    });
  };

  const submitXianxiaActiveState = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchXianxiaActiveState.mutate({
      expected_revision: revision,
      active_stance_name: xianxiaActiveDraft.activeStanceName,
      active_aura_name: xianxiaActiveDraft.activeAuraName,
    });
  };

  const submitResource = (event: FormEvent<HTMLFormElement>, resourceId: string) => {
    event.preventDefault();
    const current = parseNumberInput(resourceDrafts[resourceId] ?? "", "resource value");
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (current === null) {
      return;
    }
    setStatusMessage("Saving...");
    patchResource.mutate({ resourceId, payload: { expected_revision: revision, current } });
  };

  const submitSpellSlot = (event: FormEvent<HTMLFormElement>, slot: Record<string, unknown>) => {
    event.preventDefault();
    const level = readNumber(slot.level);
    const slotLaneId = readString(slot.slot_lane_id);
    const key = draftKey(level, slotLaneId);
    const used = parseNumberInput(spellSlotDrafts[key] ?? "", "used slot count");
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (used === null) {
      return;
    }
    setStatusMessage("Saving...");
    patchSpellSlot.mutate({
      level,
      payload: { expected_revision: revision, slot_lane_id: slotLaneId, used },
    });
  };

  const submitInventory = (event: FormEvent<HTMLFormElement>, itemId: string) => {
    event.preventDefault();
    const quantity = parseNumberInput(inventoryDrafts[itemId] ?? "", "quantity");
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (quantity === null) {
      return;
    }
    setStatusMessage("Saving...");
    patchInventory.mutate({ itemId, payload: { expected_revision: revision, quantity } });
  };

  const submitXianxiaInventoryAdd = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (!newXianxiaInventoryDraft.name.trim()) {
      setErrorMessage("Enter an item name.");
      setStatusMessage(null);
      return;
    }
    setStatusMessage("Saving...");
    addXianxiaInventoryItem.mutate({
      expected_revision: revision,
      item: xianxiaInventoryPayloadFromDraft(newXianxiaInventoryDraft),
    });
  };

  const submitXianxiaInventoryUpdate = (event: FormEvent<HTMLFormElement>, item: CharacterXianxiaInventoryItem) => {
    event.preventDefault();
    const draft = xianxiaInventoryDrafts[item.id] ?? xianxiaInventoryDraftFromItem(item);
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    if (!draft.name.trim()) {
      setErrorMessage("Enter an item name.");
      setStatusMessage(null);
      return;
    }
    setStatusMessage("Saving...");
    patchXianxiaInventoryItem.mutate({
      itemId: item.id,
      payload: {
        expected_revision: revision,
        item: {
          ...xianxiaInventoryPayloadFromDraft(draft),
          id: item.id,
        },
      },
    });
  };

  const toggleXianxiaInventoryEquipped = (item: CharacterXianxiaInventoryItem, isEquipped: boolean) => {
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchXianxiaInventoryEquipped.mutate({
      itemId: item.id,
      payload: {
        expected_revision: revision,
        is_equipped: isEquipped,
      },
    });
  };

  const removeXianxiaInventory = (item: CharacterXianxiaInventoryItem) => {
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    removeXianxiaInventoryItem.mutate({
      itemId: item.id,
      payload: { expected_revision: revision },
    });
  };

  const submitEquipmentState = (event: FormEvent<HTMLFormElement>, item: CharacterEquipmentRow) => {
    event.preventDefault();
    const draft = equipmentDrafts[item.id] ?? {
      isEquipped: Boolean(item.is_equipped),
      isAttuned: Boolean(item.is_attuned),
      weaponWieldMode: item.weapon_wield_mode || "",
    };
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchEquipmentState.mutate({
      itemId: item.id,
      payload: {
        expected_revision: revision,
        is_equipped: draft.isEquipped,
        is_attuned: draft.isAttuned,
        weapon_wield_mode: item.supports_weapon_wield_mode ? draft.weaponWieldMode : "",
      },
    });
  };

  const submitArcaneArmorState = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const featureKey = readString(arcaneArmorState?.feature_key, "arcane_armor");
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchFeatureState.mutate({
      featureKey,
      payload: {
        expected_revision: revision,
        enabled: arcaneArmorDraft,
      },
    });
  };

  const submitCurrency = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    const payload: CharacterCurrencyPatchPayload = { expected_revision: revision };
    const currencyKeys = isXianxia ? ["coin", "supply", "spirit_stones"] : ["cp", "sp", "ep", "gp", "pp"];
    for (const key of currencyKeys) {
      if (currencyDraft[key] !== undefined) {
        const value = parseNumberInput(currencyDraft[key], key.replace("_", " ").toUpperCase());
        if (value === null) {
          return;
        }
        payload[key as "cp" | "sp" | "ep" | "gp" | "pp" | "coin" | "supply" | "spirit_stones"] = value;
      }
    }
    setStatusMessage("Saving...");
    patchCurrency.mutate(payload);
  };

  const submitNotes = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected || !canEdit) {
      setErrorMessage("No character selected or permission denied.");
      return;
    }
    setStatusMessage("Saving...");
    patchNotes.mutate({
      expected_revision: revision,
      player_notes_markdown: notesDraft.notes,
    });
  };

  const openXianxiaRecordDetail = (record: CharacterXianxiaNamedRecord, eyebrow: string) => {
    setDetailDialog({
      eyebrow,
      title: record.name || "Xianxia record",
      html: readString(record.body_html, readString(record.description_html)),
      notes: readString(record.notes),
      href: readString(record.href),
      facts: [
        { label: "Rank", value: readString(record.current_rank_label) },
        { label: "Status", value: readString(record.status) },
        { label: "Type", value: readString(record.type) },
        { label: "Source", value: readString(record.source_label) },
      ].filter((fact) => fact.value),
    });
  };

  const renderXianxiaRecordCard = (record: CharacterXianxiaNamedRecord, eyebrow: string) => (
    <article className="character-state-card" key={draftKey(eyebrow, record.name, record.href)}>
      <p className="meta">{joinDisplay([record.current_rank_label, record.status, record.type, record.source_label]) || eyebrow}</p>
      <h4>{record.name || "Unnamed record"}</h4>
      {record.reason ? <p className="meta">{record.reason}</p> : null}
      {record.rank_progress_label ? <p className="meta">{record.rank_progress_label}</p> : null}
      {record.body_html || record.description_html || record.notes || record.href ? (
        <button type="button" className="button button-secondary detail-button" onClick={() => openXianxiaRecordDetail(record, eyebrow)}>
          Details
        </button>
      ) : null}
    </article>
  );

  const renderXianxiaPoolCards = (pools: Array<{ key: string; label: string; current: number; max: number; temp?: number }>) => (
    <div className="character-card-grid">
      {pools.map((pool) => (
        <article className="character-state-card" key={pool.key}>
          <h4>{pool.label}</h4>
          <p>
            {pool.current} / {pool.max}
            {pool.temp !== undefined ? ` +${pool.temp} temp` : ""}
          </p>
        </article>
      ))}
    </div>
  );

  return (
    <div className="session-pane-content">
      <section className="panel">
        <div className="panel-header">
          <h2>Session Character</h2>
          <a href={`/campaigns/${campaignSlug}/characters`} className="button button-secondary">
            Character route
          </a>
        </div>

        <label className="chat-label" htmlFor="character-selector">
          Character
        </label>
        <select
          id="character-selector"
          value={selectedSlug || ""}
          onChange={(event) => {
            setSelectedSlug(event.currentTarget.value || null);
            setActiveCharacterSection("overview");
            setRestPreview(null);
            setStatusMessage(null);
            setErrorMessage(null);
            setDetailDialog(null);
          }}
        >
          {characterList.map((item) => (
            <option key={item.slug} value={item.slug}>
              {item.name} ({item.slug})
            </option>
          ))}
        </select>

        {listQuery.isLoading ? <p className="status status-neutral">Loading characters...</p> : null}
        {detailQuery.isLoading ? <p className="status status-neutral">Loading character...</p> : null}

        {selected ? (
          <article className="character-summary">
            <h3>
              {selected.name} ({selected.slug})
            </h3>
            <p>
              HP: {readNumber(vitals.current_hp, selected.current_hp)} / {readNumber(stats.max_hp, selected.max_hp)}
            </p>
            <p>Temp HP: {readNumber(vitals.temp_hp, selected.temp_hp)}</p>
            <p>Class: {selected.class_level_text || "Unknown"}</p>
            <p>System: {characterSystem(detailRecord)}</p>
            <p>Status: {selected.status}</p>
            <p>Revision: {revision || selected.revision}</p>
          </article>
        ) : null}

        {selected && detailRecord ? (
          <>
            <section className="session-character-form">
              <div className="panel-header compact-header">
                <h3>Vitals</h3>
                <div className="button-row">
                  <button
                    type="button"
                    className="button button-secondary"
                    disabled={previewRest.isPending || !canEdit}
                    onClick={() => previewRest.mutate("short")}
                  >
                    Short rest
                  </button>
                  <button
                    type="button"
                    className="button button-secondary"
                    disabled={previewRest.isPending || !canEdit}
                    onClick={() => previewRest.mutate("long")}
                  >
                    Long rest
                  </button>
                </div>
              </div>
              {isXianxia ? (
                <form onSubmit={submitXianxiaVitals} className="inline-two-col">
                  {xianxiaVitalsFields.map((field) => (
                    <React.Fragment key={field.key}>
                      <label htmlFor={`xianxia-${field.key}`} className="chat-label">
                        {field.label}
                      </label>
                      <input
                        id={`xianxia-${field.key}`}
                        type="number"
                        value={xianxiaVitalsDraft[field.key]}
                        disabled={!canEdit}
                        onChange={(event: ChangeEvent<HTMLInputElement>) =>
                          setXianxiaVitalsDraft({
                            ...xianxiaVitalsDraft,
                            [field.key]: event.currentTarget.value,
                          })
                        }
                      />
                    </React.Fragment>
                  ))}
                  <div />
                  <button type="submit" disabled={patchVitals.isPending || !canEdit}>
                    {patchVitals.isPending ? "Saving..." : "Save Xianxia pools"}
                  </button>
                </form>
              ) : (
                <form onSubmit={submitVitals} className="inline-two-col">
                  <label htmlFor="character-current-hp" className="chat-label">
                    Current HP
                  </label>
                  <input
                    id="character-current-hp"
                    type="number"
                    value={vitalsDraft.currentHp}
                    disabled={!canEdit}
                    onChange={(event: ChangeEvent<HTMLInputElement>) =>
                      setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })
                    }
                  />
                  <label htmlFor="character-temp-hp" className="chat-label">
                    Temp HP
                  </label>
                  <input
                    id="character-temp-hp"
                    type="number"
                    value={vitalsDraft.tempHp}
                    disabled={!canEdit}
                    onChange={(event: ChangeEvent<HTMLInputElement>) =>
                      setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })
                    }
                  />
                  <div />
                  <button type="submit" disabled={patchVitals.isPending || !canEdit}>
                    {patchVitals.isPending ? "Saving..." : "Save vitals"}
                  </button>
                </form>
              )}
              {restPreview ? (
                <div className="rest-preview">
                  <div className="panel-header compact-header">
                    <h4>{restPreview.label}</h4>
                    <button
                      type="button"
                      disabled={applyRest.isPending || !canEdit}
                      onClick={() =>
                        applyRest.mutate({
                          restType: restPreview.rest_type === "short" ? "short" : "long",
                          payload: { expected_revision: revision },
                        })
                      }
                    >
                      {applyRest.isPending ? "Applying..." : "Apply"}
                    </button>
                  </div>
                  <ul className="plain-list compact-list">
                    {restPreview.changes.map((change) => (
                      <li key={`${change.label}-${change.from_value}-${change.to_value}`}>
                        <strong>{change.label}</strong>: {change.from_value} {"->"} {change.to_value}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>

            {isDnd ? (
              <div className="section-tabs" role="tablist" aria-label="Session character sections">
                {dndCharacterSections.map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    className={activeCharacterSection === section.id ? "active" : ""}
                    onClick={() => setActiveCharacterSection(section.id)}
                  >
                    {section.label}
                  </button>
                ))}
              </div>
            ) : null}
            {isXianxia ? (
              <div className="section-tabs" role="tablist" aria-label="Xianxia session character sections">
                {xianxiaCharacterSections.map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    className={activeCharacterSection === section.id ? "active" : ""}
                    onClick={() => setActiveCharacterSection(section.id)}
                  >
                    {section.label}
                  </button>
                ))}
              </div>
            ) : null}

            {isXianxia && activeCharacterSection === "quick-reference" ? (
              <section className="session-character-form">
                <h3>Quick Reference</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Realm</strong>
                    <span>{String(presentedXianxia.identity?.realm ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Actions per turn</strong>
                    <span>{String(presentedXianxia.identity?.actions_per_turn ?? "--")}</span>
                    {asRecord(presentedXianxia.quick_reference?.actions).formula ? (
                      <p className="meta">{readString(asRecord(presentedXianxia.quick_reference?.actions).formula)}</p>
                    ) : null}
                  </article>
                  <article>
                    <strong>Defense</strong>
                    <span>{String(asRecord(presentedXianxia.quick_reference?.defense).value ?? presentedXianxia.equipment?.defense ?? "--")}</span>
                    {asRecord(presentedXianxia.quick_reference?.defense).formula ? (
                      <p className="meta">Defense = {readString(asRecord(presentedXianxia.quick_reference?.defense).formula)}</p>
                    ) : null}
                  </article>
                  <article>
                    <strong>Honor</strong>
                    <span>{String(presentedXianxia.identity?.honor ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Reputation</strong>
                    <span>{String(presentedXianxia.identity?.reputation ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Insight</strong>
                    <span>
                      {xianxiaInsight ? `${xianxiaInsight.available} available / ${xianxiaInsight.spent} spent` : "--"}
                    </span>
                  </article>
                </div>
                {asRecord(presentedXianxia.quick_reference?.check_formula).summary ? (
                  <article className="character-state-card">
                    <h4>Check formula</h4>
                    <p>{readString(asRecord(presentedXianxia.quick_reference?.check_formula).summary)}</p>
                  </article>
                ) : null}
                {asRecord(presentedXianxia.quick_reference?.difficulty_states).summary ? (
                  <article className="character-state-card">
                    <h4>Difficulty states</h4>
                    <p>{readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).summary)}</p>
                    <p className="meta">{readString(asRecord(presentedXianxia.quick_reference?.difficulty_states).resolution_note)}</p>
                  </article>
                ) : null}
                {asRecordArray(asRecord(presentedXianxia.quick_reference?.effort_damage).entries).length ? (
                  <div className="character-card-grid">
                    {asRecordArray(asRecord(presentedXianxia.quick_reference?.effort_damage).entries).map((entry) => (
                      <article className="character-state-card" key={readString(entry.key, readString(entry.label))}>
                        <h4>{readString(entry.label, "Effort")}</h4>
                        <p>{readString(entry.damage, "--")}</p>
                        <p className="meta">Score {String(entry.score ?? "--")}</p>
                      </article>
                    ))}
                  </div>
                ) : null}
                {asRecordArray(presentedXianxia.quick_reference?.active_state_reminders).length ? (
                  <div className="character-card-grid">
                    {asRecordArray(presentedXianxia.quick_reference?.active_state_reminders).map((reminder) => (
                      <article className="character-state-card" key={readString(reminder.label)}>
                        <h4>{readString(reminder.title, readString(reminder.label))}</h4>
                        <p>{readString(reminder.status_label)}</p>
                        {asStringArray(reminder.reference_lines).length ? (
                          <ul className="plain-list compact-list">
                            {asStringArray(reminder.reference_lines).map((line, index) => (
                              <li key={`${readString(reminder.label)}-${index}`}>{line}</li>
                            ))}
                          </ul>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "martial-arts" ? (
              <section className="session-character-form">
                <h3>Martial Arts</h3>
                {presentedXianxia.martial_arts?.length ? (
                  <div className="character-card-grid">
                    {presentedXianxia.martial_arts.map((record) => renderXianxiaRecordCard(record, "Martial Art"))}
                  </div>
                ) : (
                  <p className="status status-neutral">No martial arts recorded.</p>
                )}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "techniques" ? (
              <section className="session-character-form">
                <h3>Techniques</h3>
                {presentedXianxia.generic_techniques?.length ? (
                  <div className="character-card-grid">
                    {presentedXianxia.generic_techniques.map((record) => renderXianxiaRecordCard(record, "Generic Technique"))}
                  </div>
                ) : (
                  <p className="status status-neutral">No generic techniques recorded.</p>
                )}
                {presentedXianxia.basic_actions?.length ? (
                  <>
                    <h4>Basic actions</h4>
                    <div className="character-card-grid">
                      {presentedXianxia.basic_actions.map((record) => renderXianxiaRecordCard(record, "Basic Action"))}
                    </div>
                  </>
                ) : null}
                {presentedXianxia.approval?.status_groups?.length ? (
                  <>
                    <h4>Approvals</h4>
                    {presentedXianxia.approval.status_groups.map((group) => (
                      <article className="character-state-card" key={group.key}>
                        <h4>{group.title}</h4>
                        {group.records.length ? (
                          <div className="spell-card-list">
                            {group.records.map((record) => renderXianxiaRecordCard(record, group.title))}
                          </div>
                        ) : (
                          <p className="meta">{group.empty_message}</p>
                        )}
                      </article>
                    ))}
                  </>
                ) : null}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "resources" ? (
              <section className="session-character-form">
                <h3>Resources</h3>
                {xianxiaDurability.length ? renderXianxiaPoolCards(xianxiaDurability) : null}
                {xianxiaEnergies.length ? renderXianxiaPoolCards(xianxiaEnergies) : null}
                {xianxiaYinYang.length ? renderXianxiaPoolCards(xianxiaYinYang) : null}
                {xianxiaDao ? (
                  <article className="character-state-card">
                    <h4>Dao</h4>
                    <p>
                      {xianxiaDao.current} / {xianxiaDao.max}
                    </p>
                  </article>
                ) : null}
                <form onSubmit={submitXianxiaActiveState} className="inline-two-col">
                  <label htmlFor="xianxia-active-stance" className="chat-label">
                    Active Stance
                  </label>
                  <input
                    id="xianxia-active-stance"
                    value={xianxiaActiveDraft.activeStanceName}
                    disabled={!canEdit}
                    onChange={(event) => setXianxiaActiveDraft({ ...xianxiaActiveDraft, activeStanceName: event.currentTarget.value })}
                  />
                  <label htmlFor="xianxia-active-aura" className="chat-label">
                    Active Aura
                  </label>
                  <input
                    id="xianxia-active-aura"
                    value={xianxiaActiveDraft.activeAuraName}
                    disabled={!canEdit}
                    onChange={(event) => setXianxiaActiveDraft({ ...xianxiaActiveDraft, activeAuraName: event.currentTarget.value })}
                  />
                  <div />
                  <button type="submit" disabled={patchXianxiaActiveState.isPending || !canEdit}>
                    {patchXianxiaActiveState.isPending ? "Saving..." : "Save active state"}
                  </button>
                </form>
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "skills" ? (
              <section className="session-character-form">
                <h3>Skills</h3>
                <div className="ability-grid">
                  {presentedXianxia.attributes?.map((attribute) => (
                    <article className="character-state-card" key={attribute.key}>
                      <h4>{attribute.label}</h4>
                      <p>Score {attribute.score}</p>
                    </article>
                  ))}
                  {presentedXianxia.efforts?.map((effort) => (
                    <article className="character-state-card" key={effort.key}>
                      <h4>{effort.label}</h4>
                      <p>Score {effort.score}</p>
                      {effort.damage ? <p className="meta">{effort.damage}</p> : null}
                    </article>
                  ))}
                </div>
                {presentedXianxia.skills?.trained?.length ? (
                  <ul className="plain-list compact-list">
                    {presentedXianxia.skills.trained.map((skill) => (
                      <li key={skill.name}>{skill.name}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="status status-neutral">No trained skills recorded.</p>
                )}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "equipment" ? (
              <section className="session-character-form">
                <h3>Equipment</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Defense</strong>
                    <span>{String(presentedXianxia.equipment?.defense ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Manual armor bonus</strong>
                    <span>{String(presentedXianxia.equipment?.manual_armor_bonus ?? 0)}</span>
                  </article>
                </div>
                {presentedXianxia.equipment?.equipped_items?.length ? (
                  <div className="character-card-grid">
                    {presentedXianxia.equipment.equipped_items.map((item) => (
                      <article className="character-state-card" key={item.id}>
                        <h4>{item.name}</h4>
                        <p className="meta">{joinDisplay([item.item_nature, item.item_type, item.is_equipped ? "Equipped" : ""])}</p>
                        {item.notes ? <p className="meta">{item.notes}</p> : null}
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="status status-neutral">No equipped Xianxia weapons, armor, or artifacts.</p>
                )}
                {presentedXianxia.equipment?.necessary_weapons?.length ? (
                  <>
                    <h4>Necessary weapons</h4>
                    <div className="character-card-grid">
                      {presentedXianxia.equipment.necessary_weapons.map((record) => renderXianxiaRecordCard(record, "Necessary Weapon"))}
                    </div>
                  </>
                ) : null}
                {presentedXianxia.equipment?.necessary_tools?.length ? (
                  <>
                    <h4>Necessary tools</h4>
                    <div className="character-card-grid">
                      {presentedXianxia.equipment.necessary_tools.map((record) => renderXianxiaRecordCard(record, "Necessary Tool"))}
                    </div>
                  </>
                ) : null}
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "inventory" ? (
              <section className="session-character-form">
                <h3>Inventory</h3>
                {xianxiaInventory.length ? (
                  <div className="character-card-grid">
                    {xianxiaInventory.map((item) => {
                      const draft = xianxiaInventoryDrafts[item.id] ?? xianxiaInventoryDraftFromItem(item);
                      return (
                        <article className="character-state-card" key={item.id}>
                          <h4>{item.name}</h4>
                          <p className="meta">{joinDisplay([`Qty ${item.quantity}`, item.item_nature, item.item_type, item.is_equipped ? "Equipped" : ""])}</p>
                          {item.tags.length ? <p className="meta">{item.tags.join(", ")}</p> : null}
                          {item.notes ? <p className="meta">{item.notes}</p> : null}
                          {canEdit ? (
                            <form onSubmit={(event) => submitXianxiaInventoryUpdate(event, item)} className="equipment-state-form">
                              <label className="chat-label" htmlFor={`xianxia-inventory-name-${item.id}`}>
                                Name
                                <input
                                  id={`xianxia-inventory-name-${item.id}`}
                                  value={draft.name}
                                  onChange={(event) =>
                                    setXianxiaInventoryDrafts({
                                      ...xianxiaInventoryDrafts,
                                      [item.id]: { ...draft, name: event.currentTarget.value },
                                    })
                                  }
                                />
                              </label>
                              <label className="chat-label" htmlFor={`xianxia-inventory-quantity-${item.id}`}>
                                Quantity
                                <input
                                  id={`xianxia-inventory-quantity-${item.id}`}
                                  type="number"
                                  min="0"
                                  value={draft.quantity}
                                  onChange={(event) =>
                                    setXianxiaInventoryDrafts({
                                      ...xianxiaInventoryDrafts,
                                      [item.id]: { ...draft, quantity: event.currentTarget.value },
                                    })
                                  }
                                />
                              </label>
                              <label className="chat-label" htmlFor={`xianxia-inventory-nature-${item.id}`}>
                                Nature
                                <select
                                  id={`xianxia-inventory-nature-${item.id}`}
                                  value={draft.itemNature}
                                  onChange={(event) =>
                                    setXianxiaInventoryDrafts({
                                      ...xianxiaInventoryDrafts,
                                      [item.id]: { ...draft, itemNature: event.currentTarget.value },
                                    })
                                  }
                                >
                                  <option value="Mundane">Mundane</option>
                                  <option value="Relic">Relic</option>
                                </select>
                              </label>
                              <label className="chat-label" htmlFor={`xianxia-inventory-type-${item.id}`}>
                                Type
                                <select
                                  id={`xianxia-inventory-type-${item.id}`}
                                  value={draft.itemType}
                                  onChange={(event) =>
                                    setXianxiaInventoryDrafts({
                                      ...xianxiaInventoryDrafts,
                                      [item.id]: { ...draft, itemType: event.currentTarget.value },
                                    })
                                  }
                                >
                                  <option value="Weapon">Weapon</option>
                                  <option value="Armor">Armor</option>
                                  <option value="Artifact">Artifact</option>
                                  <option value="Consumable">Consumable</option>
                                  <option value="Miscellaneous">Miscellaneous</option>
                                </select>
                              </label>
                              <label className="chat-label" htmlFor={`xianxia-inventory-tags-${item.id}`}>
                                Tags
                                <input
                                  id={`xianxia-inventory-tags-${item.id}`}
                                  value={draft.tags}
                                  onChange={(event) =>
                                    setXianxiaInventoryDrafts({
                                      ...xianxiaInventoryDrafts,
                                      [item.id]: { ...draft, tags: event.currentTarget.value },
                                    })
                                  }
                                />
                              </label>
                              <label className="chat-label" htmlFor={`xianxia-inventory-notes-${item.id}`}>
                                Notes
                                <textarea
                                  id={`xianxia-inventory-notes-${item.id}`}
                                  rows={3}
                                  value={draft.notes}
                                  onChange={(event) =>
                                    setXianxiaInventoryDrafts({
                                      ...xianxiaInventoryDrafts,
                                      [item.id]: { ...draft, notes: event.currentTarget.value },
                                    })
                                  }
                                />
                              </label>
                              <label className="toggle-row">
                                <input
                                  type="checkbox"
                                  checked={draft.equippable}
                                  onChange={(event) =>
                                    setXianxiaInventoryDrafts({
                                      ...xianxiaInventoryDrafts,
                                      [item.id]: { ...draft, equippable: event.currentTarget.checked },
                                    })
                                  }
                                />
                                Equippable
                              </label>
                              {draft.equippable ? (
                                <label className="toggle-row">
                                  <input
                                    type="checkbox"
                                    checked={draft.isEquipped}
                                    onChange={(event) => {
                                      const isEquipped = event.currentTarget.checked;
                                      setXianxiaInventoryDrafts({
                                        ...xianxiaInventoryDrafts,
                                        [item.id]: { ...draft, isEquipped },
                                      });
                                      toggleXianxiaInventoryEquipped(item, isEquipped);
                                    }}
                                  />
                                  Equipped
                                </label>
                              ) : null}
                              <button type="submit" disabled={patchXianxiaInventoryItem.isPending}>
                                {patchXianxiaInventoryItem.isPending ? "Saving..." : "Save item"}
                              </button>
                              <button
                                type="button"
                                className="button-danger"
                                disabled={removeXianxiaInventoryItem.isPending}
                                onClick={() => removeXianxiaInventory(item)}
                              >
                                {removeXianxiaInventoryItem.isPending ? "Removing..." : "Remove"}
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="status status-neutral">No Xianxia inventory items.</p>
                )}
                {canEdit ? (
                  <form onSubmit={submitXianxiaInventoryAdd} className="equipment-state-form">
                    <h4>Add item</h4>
                    <label className="chat-label" htmlFor="xianxia-new-item-name">
                      Name
                      <input
                        id="xianxia-new-item-name"
                        value={newXianxiaInventoryDraft.name}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, name: event.currentTarget.value })}
                      />
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-quantity">
                      Quantity
                      <input
                        id="xianxia-new-item-quantity"
                        type="number"
                        min="0"
                        value={newXianxiaInventoryDraft.quantity}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, quantity: event.currentTarget.value })}
                      />
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-nature">
                      Nature
                      <select
                        id="xianxia-new-item-nature"
                        value={newXianxiaInventoryDraft.itemNature}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, itemNature: event.currentTarget.value })}
                      >
                        <option value="Mundane">Mundane</option>
                        <option value="Relic">Relic</option>
                      </select>
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-type">
                      Type
                      <select
                        id="xianxia-new-item-type"
                        value={newXianxiaInventoryDraft.itemType}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, itemType: event.currentTarget.value })}
                      >
                        <option value="Weapon">Weapon</option>
                        <option value="Armor">Armor</option>
                        <option value="Artifact">Artifact</option>
                        <option value="Consumable">Consumable</option>
                        <option value="Miscellaneous">Miscellaneous</option>
                      </select>
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-tags">
                      Tags
                      <input
                        id="xianxia-new-item-tags"
                        value={newXianxiaInventoryDraft.tags}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, tags: event.currentTarget.value })}
                      />
                    </label>
                    <label className="chat-label" htmlFor="xianxia-new-item-notes">
                      Notes
                      <textarea
                        id="xianxia-new-item-notes"
                        rows={3}
                        value={newXianxiaInventoryDraft.notes}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, notes: event.currentTarget.value })}
                      />
                    </label>
                    <label className="toggle-row">
                      <input
                        type="checkbox"
                        checked={newXianxiaInventoryDraft.equippable}
                        onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, equippable: event.currentTarget.checked })}
                      />
                      Equippable
                    </label>
                    {newXianxiaInventoryDraft.equippable ? (
                      <label className="toggle-row">
                        <input
                          type="checkbox"
                          checked={newXianxiaInventoryDraft.isEquipped}
                          onChange={(event) => setNewXianxiaInventoryDraft({ ...newXianxiaInventoryDraft, isEquipped: event.currentTarget.checked })}
                        />
                        Equipped
                      </label>
                    ) : null}
                    <button type="submit" disabled={addXianxiaInventoryItem.isPending}>
                      {addXianxiaInventoryItem.isPending ? "Adding..." : "Add item"}
                    </button>
                  </form>
                ) : null}
                <form onSubmit={submitCurrency} className="currency-grid">
                  {(xianxiaCurrency.length ? xianxiaCurrency : [
                    { key: "coin", label: "Coin", amount: readNumber(currency.coin) },
                    { key: "supply", label: "Supply", amount: readNumber(currency.supply) },
                    { key: "spirit_stones", label: "Spirit Stones", amount: readNumber(currency.spirit_stones) },
                  ]).map((entry) => (
                    <label key={entry.key} className="chat-label" htmlFor={`currency-${entry.key}`}>
                      {entry.label}
                      <input
                        id={`currency-${entry.key}`}
                        type="number"
                        min="0"
                        value={currencyDraft[entry.key] ?? String(entry.amount ?? 0)}
                        disabled={!canEdit}
                        onChange={(event) => setCurrencyDraft({ ...currencyDraft, [entry.key]: event.currentTarget.value })}
                      />
                    </label>
                  ))}
                  <button type="submit" disabled={patchCurrency.isPending || !canEdit}>
                    {patchCurrency.isPending ? "Saving..." : "Save currency"}
                  </button>
                </form>
              </section>
            ) : null}

            {isXianxia && activeCharacterSection === "personal" ? (
              <section className="session-character-form">
                <h3>Personal</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Species</strong>
                    <span>{readString(profile.species, selected.species || "--")}</span>
                  </article>
                  <article>
                    <strong>Background</strong>
                    <span>{readString(profile.background, selected.background || "--")}</span>
                  </article>
                </div>
                {readString(profile.biography_markdown) ? <pre className="article-body markdown-body">{readString(profile.biography_markdown)}</pre> : null}
                {readString(profile.personality_markdown) ? <pre className="article-body markdown-body">{readString(profile.personality_markdown)}</pre> : null}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "overview" ? (
              <section className="session-character-form">
                <h3>Overview</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Armor Class</strong>
                    <span>{String(stats.armor_class ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Initiative</strong>
                    <span>{String(stats.initiative_bonus ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Speed</strong>
                    <span>{String(stats.speed ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Proficiency</strong>
                    <span>{String(stats.proficiency_bonus ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Species</strong>
                    <span>{readString(profile.species, selected.species || "--")}</span>
                  </article>
                  <article>
                    <strong>Background</strong>
                    <span>{readString(profile.background, selected.background || "--")}</span>
                  </article>
                </div>
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "resources" ? (
              <section className="session-character-form">
                <h3>Resources</h3>
                {resources.length ? (
                  <div className="character-card-grid">
                    {resources.map((resource) => {
                      const id = readString(resource.id);
                      return (
                        <article className="character-state-card" key={id || readString(resource.label)}>
                          <h4>{readString(resource.label, id || "Resource")}</h4>
                          <p>
                            {readNumber(resource.current)} / {readNumber(resource.max)}
                          </p>
                          {resource.notes ? <p className="meta">{readString(resource.notes)}</p> : null}
                          {canEdit && id ? (
                            <form onSubmit={(event) => submitResource(event, id)} className="compact-state-form">
                              <label className="chat-label" htmlFor={`resource-${id}`}>
                                Current
                              </label>
                              <input
                                id={`resource-${id}`}
                                type="number"
                                min="0"
                                value={resourceDrafts[id] ?? ""}
                                onChange={(event) =>
                                  setResourceDrafts({ ...resourceDrafts, [id]: event.currentTarget.value })
                                }
                              />
                              <button type="submit" disabled={patchResource.isPending}>
                                Save
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="status status-neutral">No tracked resources.</p>
                )}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "spells" ? (
              <section className="session-character-form">
                <h3>Spells</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Ability</strong>
                    <span>{String(spellcasting.spellcasting_ability ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Save DC</strong>
                    <span>{String(spellcasting.spell_save_dc ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Attack</strong>
                    <span>{String(spellcasting.spell_attack_bonus ?? "--")}</span>
                  </article>
                </div>
                {spellSlots.length ? (
                  <div className="character-card-grid">
                    {spellSlots.map((slot) => {
                      const level = readNumber(slot.level);
                      const slotLaneId = readString(slot.slot_lane_id);
                      const key = draftKey(level, slotLaneId);
                      return (
                        <article className="character-state-card" key={key}>
                          <h4>Level {level}</h4>
                          <p>
                            Used {readNumber(slot.used)} / {readNumber(slot.max)}
                          </p>
                          {canEdit ? (
                            <form onSubmit={(event) => submitSpellSlot(event, slot)} className="compact-state-form">
                              <label className="chat-label" htmlFor={`spell-slot-${key}`}>
                                Used
                              </label>
                              <input
                                id={`spell-slot-${key}`}
                                type="number"
                                min="0"
                                max={readNumber(slot.max)}
                                value={spellSlotDrafts[key] ?? ""}
                                onChange={(event) =>
                                  setSpellSlotDrafts({ ...spellSlotDrafts, [key]: event.currentTarget.value })
                                }
                              />
                              <button type="submit" disabled={patchSpellSlot.isPending}>
                                Save
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : null}
                {presentedSpells.length ? (
                  <div className="spell-card-list">
                    {presentedSpells.map((spell) => (
                      <article className="character-state-card" key={draftKey(spell.class_row_id, spell.name, spell.level_label)}>
                        <p className="meta">
                          {[spell.level_label, spell.school].filter(Boolean).join(" | ") || "Spell"}
                        </p>
                        <h4>{spell.name || "Spell"}</h4>
                        {spell.badges?.length ? (
                          <div className="badge-list">
                            {spell.badges.map((badge) => (
                              <span className="meta-badge" key={badge}>
                                {badge}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        <p className="meta">
                          {[spell.casting_time, spell.range].filter((value) => value && value !== "--").join(" | ")}
                        </p>
                        {spell.description_html || spell.href ? (
                          <button type="button" className="button button-secondary detail-button" onClick={() => openSpellDetail(spell)}>
                            Details
                          </button>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : spells.length ? (
                  <div className="spell-card-list">
                    {spells.map((spell) => (
                      <article className="character-state-card" key={readString(spell.id, readString(spell.name))}>
                        <h4>{readString(spell.name, "Spell")}</h4>
                        <p className="meta">
                          {[spell.mark, spell.casting_time, spell.range].map((value) => readString(value)).filter(Boolean).join(" | ")}
                        </p>
                      </article>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "equipment" ? (
              <section className="session-character-form">
                <h3>Equipment</h3>
                {equipmentState ? (
                  <div className="stat-grid">
                    <article>
                      <strong>Attuned items</strong>
                      <span>
                        {equipmentState.attuned_count} / {equipmentState.max_attuned_items}
                      </span>
                      {equipmentState.over_attunement_limit ? (
                        <p className="meta">This sheet is currently over the normal attunement limit.</p>
                      ) : null}
                    </article>
                    <article>
                      <strong>Equipped items</strong>
                      <span>{equipmentState.equipped_count}</span>
                    </article>
                  </div>
                ) : null}
                {arcaneArmorState?.available ? (
                  <article className="character-state-card">
                    <h4>{readString(arcaneArmorState.label, "Arcane Armor")}</h4>
                    <p className="meta">
                      {[arcaneArmorState.status_label, arcaneArmorState.hands_label].map((value) => readString(value)).filter(Boolean).join(" | ")}
                    </p>
                    {canEdit ? (
                      <form onSubmit={submitArcaneArmorState} className="equipment-state-form">
                        <label className="toggle-row">
                          <input
                            type="checkbox"
                            checked={arcaneArmorDraft}
                            onChange={(event) => setArcaneArmorDraft(event.currentTarget.checked)}
                          />
                          Enabled
                        </label>
                        <button type="submit" disabled={patchFeatureState.isPending}>
                          {patchFeatureState.isPending ? "Saving..." : "Save feature state"}
                        </button>
                      </form>
                    ) : null}
                  </article>
                ) : null}
                {equipmentRows.length ? (
                  <div className="character-card-grid">
                    {equipmentRows.map((item) => {
                      const draft = equipmentDrafts[item.id] ?? {
                        isEquipped: Boolean(item.is_equipped),
                        isAttuned: Boolean(item.is_attuned),
                        weaponWieldMode: item.weapon_wield_mode || "",
                      };
                      return (
                        <article className="character-state-card" key={item.id || item.name}>
                          <h4>{item.name || "Item"}</h4>
                          <p className="meta">
                            {[item.equipped_label, item.is_attuned ? "Attuned" : item.requires_attunement ? "Not attuned" : "", item.source_label]
                              .filter(Boolean)
                              .join(" | ")}
                          </p>
                          {item.tags.length ? <p className="meta">{item.tags.join(", ")}</p> : null}
                          {item.description_html || item.notes || item.href ? (
                            <button type="button" className="button button-secondary detail-button" onClick={() => openItemDetail(item)}>
                              Item details
                            </button>
                          ) : null}
                          {canEdit ? (
                            <form onSubmit={(event) => submitEquipmentState(event, item)} className="equipment-state-form">
                              {item.supports_weapon_wield_mode ? (
                                <label className="chat-label" htmlFor={`equipment-wield-${item.id}`}>
                                  Wielding
                                  <select
                                    id={`equipment-wield-${item.id}`}
                                    value={draft.weaponWieldMode}
                                    onChange={(event) =>
                                      setEquipmentDrafts({
                                        ...equipmentDrafts,
                                        [item.id]: { ...draft, weaponWieldMode: event.currentTarget.value },
                                      })
                                    }
                                  >
                                    <option value="">Not equipped</option>
                                    {item.weapon_wield_options.map((option) => (
                                      <option value={option.value} key={option.value}>
                                        {option.label}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                              ) : (
                                <label className="toggle-row">
                                  <input
                                    type="checkbox"
                                    checked={draft.isEquipped}
                                    onChange={(event) =>
                                      setEquipmentDrafts({
                                        ...equipmentDrafts,
                                        [item.id]: { ...draft, isEquipped: event.currentTarget.checked },
                                      })
                                    }
                                  />
                                  Equipped
                                </label>
                              )}
                              {item.requires_attunement ? (
                                <label className="toggle-row">
                                  <input
                                    type="checkbox"
                                    checked={draft.isAttuned}
                                    onChange={(event) =>
                                      setEquipmentDrafts({
                                        ...equipmentDrafts,
                                        [item.id]: { ...draft, isAttuned: event.currentTarget.checked },
                                      })
                                    }
                                  />
                                  Attuned
                                </label>
                              ) : null}
                              {item.attunement_hint && item.attunement_hint !== "Requires attunement" ? (
                                <p className="meta">{item.attunement_hint}</p>
                              ) : null}
                              <button type="submit" disabled={patchEquipmentState.isPending}>
                                {patchEquipmentState.isPending ? "Saving..." : "Save equipment state"}
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="status status-neutral">No equipment state rows.</p>
                )}
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "inventory" ? (
              <section className="session-character-form">
                <h3>Inventory</h3>
                {inventory.length ? (
                  <div className="character-card-grid">
                    {inventory.map((item) => {
                      const id = readString(item.id);
                      const itemRef = readString(item.catalog_ref, id);
                      const presentedItem = presentedInventoryByKey.get(itemRef) ?? presentedInventoryByKey.get(id);
                      const itemName = readString(presentedItem?.name, readString(item.name, "Item"));
                      const itemNotes = readString(presentedItem?.notes, readString(item.notes));
                      const itemHref = readString(presentedItem?.href);
                      const itemDescriptionHtml = readString(presentedItem?.description_html);
                      const itemTags = presentedItem?.tags?.length ? presentedItem.tags : [];
                      return (
                        <article className="character-state-card" key={id || itemRef || itemName}>
                          <h4>{itemName}</h4>
                          <p className="meta">
                            Qty {readNumber(item.quantity, 1)}
                            {item.weight ? ` | ${readString(item.weight)}` : ""}
                          </p>
                          {itemTags.length ? <p className="meta">{itemTags.join(", ")}</p> : null}
                          {itemDescriptionHtml || itemNotes || itemHref ? (
                            <button
                              type="button"
                              className="button button-secondary detail-button"
                              onClick={() =>
                                openItemDetail({
                                  name: itemName,
                                  href: itemHref,
                                  description_html: itemDescriptionHtml,
                                  notes: itemNotes,
                                })
                              }
                            >
                              Item details
                            </button>
                          ) : null}
                          {canEdit && id ? (
                            <form onSubmit={(event) => submitInventory(event, id)} className="compact-state-form">
                              <label className="chat-label" htmlFor={`inventory-${id}`}>
                                Quantity
                              </label>
                              <input
                                id={`inventory-${id}`}
                                type="number"
                                min="0"
                                value={inventoryDrafts[id] ?? ""}
                                onChange={(event) =>
                                  setInventoryDrafts({ ...inventoryDrafts, [id]: event.currentTarget.value })
                                }
                              />
                              <button type="submit" disabled={patchInventory.isPending}>
                                Save
                              </button>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : null}
                <form onSubmit={submitCurrency} className="currency-grid">
                  {["cp", "sp", "ep", "gp", "pp"].map((key) => (
                    <label key={key} className="chat-label" htmlFor={`currency-${key}`}>
                      {key.toUpperCase()}
                      <input
                        id={`currency-${key}`}
                        type="number"
                        min="0"
                        value={currencyDraft[key] ?? "0"}
                        disabled={!canEdit}
                        onChange={(event) => setCurrencyDraft({ ...currencyDraft, [key]: event.currentTarget.value })}
                      />
                    </label>
                  ))}
                  <button type="submit" disabled={patchCurrency.isPending || !canEdit}>
                    {patchCurrency.isPending ? "Saving..." : "Save currency"}
                  </button>
                </form>
              </section>
            ) : null}

            {isDnd && activeCharacterSection === "abilities" ? (
              <section className="session-character-form">
                <h3>Abilities and Skills</h3>
                <div className="ability-grid">
                  {Object.entries(abilityScores).map(([key, value]) => {
                    const ability = asRecord(value);
                    return (
                      <article className="character-state-card" key={key}>
                        <h4>{key}</h4>
                        <p>Score {String(ability.score ?? "--")}</p>
                        <p>Modifier {String(ability.modifier ?? "--")}</p>
                        <p>Save {String(ability.save_bonus ?? "--")}</p>
                      </article>
                    );
                  })}
                </div>
                <div className="stat-grid">
                  <article>
                    <strong>Passive Perception</strong>
                    <span>{String(stats.passive_perception ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Passive Insight</strong>
                    <span>{String(stats.passive_insight ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Passive Investigation</strong>
                    <span>{String(stats.passive_investigation ?? "--")}</span>
                  </article>
                </div>
              </section>
            ) : null}

            {((isDnd || isXianxia) ? activeCharacterSection === "notes" : !isDnd) ? (
              <section className="session-character-form">
                <h3>Player notes</h3>
                <form onSubmit={submitNotes}>
                  <label htmlFor="character-player-notes" className="chat-label">
                    Player notes
                  </label>
                  <textarea
                    id="character-player-notes"
                    rows={8}
                    value={notesDraft.notes}
                    disabled={!canEdit}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                      setNotesDraft({ ...notesDraft, notes: event.currentTarget.value })
                    }
                  />
                  <button type="submit" disabled={patchNotes.isPending || !canEdit}>
                    {patchNotes.isPending ? "Saving..." : "Save notes"}
                  </button>
                </form>
              </section>
            ) : null}

            {!isDnd && !isXianxia ? (
              <section className="session-character-form">
                <h3>{characterSystem(detailRecord)}</h3>
                <div className="stat-grid">
                  <article>
                    <strong>Current HP</strong>
                    <span>{String(vitals.current_hp ?? "--")}</span>
                  </article>
                  <article>
                    <strong>Temp HP</strong>
                    <span>{String(vitals.temp_hp ?? "--")}</span>
                  </article>
                </div>
              </section>
            ) : null}
          </>
        ) : null}

        {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}
        {statusMessage ? <p className="status status-neutral">{statusMessage}</p> : null}
      </section>
      <CharacterDetailDialog detail={detailDialog} onClose={() => setDetailDialog(null)} />
    </div>
  );
}

interface StagedArticleDraftState {
  title: string;
  body: string;
  imageAltText: string;
  imageCaption: string;
}

function DmPane({
  campaignSlug,
  payload,
  refetch,
  setAuthRequired,
}: {
  campaignSlug: string;
  payload: SessionPayload | undefined;
  refetch: () => void;
  setAuthRequired: (required: boolean) => void;
}) {
  const { apiClient } = useApiClient();
  const stagedArticles: SessionArticle[] = payload?.staged_articles ?? [];
  const revealedArticles: SessionArticle[] = payload?.revealed_articles ?? [];
  const sessionLogs: SessionLogSummary[] = payload?.session_logs ?? [];
  const [mode, setMode] = useState<ArticleMode>("manual");
  const [manualDraft, setManualDraft] = useState({ title: "", body: "" });
  const [uploadDraft, setUploadDraft] = useState({ filename: "", markdown: "", image: null as EmbeddedImageInput | null });
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceResults, setSourceResults] = useState<SessionArticleSourceResult[]>([]);
  const [sourceStatus, setSourceStatus] = useState<string | null>(null);
  const [selectedSourceRef, setSelectedSourceRef] = useState("");
  const [stagedDrafts, setStagedDrafts] = useState<Record<number, StagedArticleDraftState>>({});
  const [uiMessage, setUiMessage] = useState<string | null>(null);
  const [paneError, setPaneError] = useState<string | null>(null);
  const [selectedLogSessionId, setSelectedLogSessionId] = useState<number | null>(null);

  useEffect(() => {
    setStagedDrafts((current) => {
      const next: Record<number, StagedArticleDraftState> = {};
      for (const article of stagedArticles) {
        const existing = current[article.id];
        next[article.id] = existing ?? {
          title: article.title,
          body: article.body_markdown,
          imageAltText: article.image?.alt_text || "",
          imageCaption: article.image?.caption || "",
        };
      }
      return next;
    });
  }, [stagedArticles]);

  useEffect(() => {
    if (!sessionLogs.length) {
      setSelectedLogSessionId(null);
      return;
    }
    if (selectedLogSessionId !== null && !sessionLogs.some((entry) => entry.session.id === selectedLogSessionId)) {
      setSelectedLogSessionId(sessionLogs[0]?.session.id ?? null);
    }
  }, [sessionLogs, selectedLogSessionId]);

  const startSessionMutation = useMutation({
    mutationFn: () => apiClient.startSession(campaignSlug),
    onSuccess: () => {
      setPaneError(null);
      setUiMessage("Session started.");
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const closeSessionMutation = useMutation({
    mutationFn: () => apiClient.closeSession(campaignSlug),
    onSuccess: () => {
      setPaneError(null);
      setUiMessage("Session closed.");
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const createArticleMutation = useMutation({
    mutationFn: (payload: SessionArticleCreatePayload) => apiClient.createSessionArticle(campaignSlug, payload),
    onSuccess: () => {
      setUiMessage("Article created.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const updateArticleMutation = useMutation({
    mutationFn: (args: { id: number; payload: { title: string; body_markdown: string; image_alt_text?: string; image_caption?: string } }) =>
      apiClient.updateSessionArticle(campaignSlug, args.id, {
        title: args.payload.title,
        body_markdown: args.payload.body_markdown,
        image_alt_text: args.payload.image_alt_text,
        image_caption: args.payload.image_caption,
      }),
    onSuccess: () => {
      setUiMessage("Article updated.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setUiMessage(null);
      setPaneError(apiErrorMessage(error));
    },
  });

  const revealArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.revealSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article revealed.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.deleteSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article deleted.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const clearRevealedMutation = useMutation({
    mutationFn: () => apiClient.clearRevealedSessionArticles(campaignSlug),
    onSuccess: () => {
      setUiMessage("Revealed articles cleared.");
      setPaneError(null);
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteLogMutation = useMutation({
    mutationFn: (sessionId: number) => apiClient.deleteSessionLog(campaignSlug, sessionId),
    onSuccess: (_data, sessionId) => {
      setUiMessage("Session log deleted.");
      setPaneError(null);
      if (selectedLogSessionId === sessionId) {
        setSelectedLogSessionId(null);
      }
      void refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const logQuery = useQuery({
    queryKey: ["session-log-detail", campaignSlug, selectedLogSessionId],
    queryFn: () => {
      if (selectedLogSessionId === null) {
        throw new Error("No session selected.");
      }
      return apiClient.getSessionLog(campaignSlug, selectedLogSessionId);
    },
    enabled: Boolean(campaignSlug) && selectedLogSessionId !== null,
    retry: false,
  });

  useEffect(() => {
    if (logQuery.error && isAuthError(logQuery.error)) {
      setAuthRequired(true);
    }
  }, [logQuery.error, setAuthRequired]);

  const searchSources = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = sourceQuery.trim();
    if (!query) {
      setSourceStatus("Search with a query.");
      return;
    }
    setSourceStatus("Searching ...");
    try {
      const response = await apiClient.searchSessionArticleSources(campaignSlug, query);
      setSourceResults(response.results);
      setSourceStatus(response.message || "Search complete.");
      if (!response.results.length) {
        setSelectedSourceRef("");
      }
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setSourceResults([]);
      setSourceStatus(null);
      setPaneError(apiErrorMessage(error));
    }
  };

  const createArticle = (createPayload: SessionArticleCreatePayload) => {
    setPaneError(null);
    createArticleMutation.mutate(createPayload);
  };

  const clearArticleStatus = () => {
    setPaneError(null);
    setUiMessage(null);
  };

  const statusText = startSessionMutation.isPending ? "Starting session..." : closeSessionMutation.isPending ? "Closing session..." : null;

  return (
    <div className="session-pane-content">
      <section className="panel">
        <div className="panel-header">
          <h2>DM controls</h2>
          <span className="pill">{payload?.active_session ? `Session #${payload.active_session.id}` : "No active session"}</span>
        </div>
        <div className="status-row">
          <article className="stat-card">
            <h3>Session state</h3>
            <p>{payload?.active_session ? payload.active_session.status : "inactive"}</p>
          </article>
          <article className="stat-card">
            <h3>Controls</h3>
            <div className="session-actions-row">
              <button type="button" onClick={() => startSessionMutation.mutate()} disabled={startSessionMutation.isPending}>
                {startSessionMutation.isPending ? "Starting..." : "Begin session"}
              </button>
              <button
                type="button"
                onClick={() => closeSessionMutation.mutate()}
                disabled={closeSessionMutation.isPending || !payload?.active_session}
              >
                {closeSessionMutation.isPending ? "Closing..." : "Close session"}
              </button>
            </div>
          </article>
          <article className="stat-card">
            <h3>Lifecycle</h3>
            <p>{statusText || uiMessage || "Ready."}</p>
          </article>
        </div>
        {startSessionMutation.error ? <p className="status status-error">{apiErrorMessage(startSessionMutation.error)}</p> : null}
        {closeSessionMutation.error ? <p className="status status-error">{apiErrorMessage(closeSessionMutation.error)}</p> : null}
        {paneError ? <p className="status status-error">{paneError}</p> : null}
        {uiMessage ? <p className="status status-neutral">{uiMessage}</p> : null}
      </section>

      <div className="split-grid">
        <DmArticleCreator
          mode={mode}
          setMode={(next) => {
            clearArticleStatus();
            setMode(next);
          }}
          sourceQuery={sourceQuery}
          setSourceQuery={setSourceQuery}
          sourceStatus={sourceStatus}
          setSourceStatus={setSourceStatus}
          sourceResults={sourceResults}
          selectedSourceRef={selectedSourceRef}
          setSelectedSourceRef={(next) => {
            setSelectedSourceRef(next);
            setSourceStatus(`Source selected: ${next}`);
          }}
          manualDraft={manualDraft}
          setManualDraft={(next) => {
            clearArticleStatus();
            setManualDraft(next);
          }}
          uploadDraft={uploadDraft}
          setUploadDraft={(next) => {
            clearArticleStatus();
            setUploadDraft(next);
          }}
          onSearchSources={searchSources}
          onCreate={createArticle}
          isCreating={createArticleMutation.isPending}
        />
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Staged articles</h3>
            <span className="pill">{stagedArticles.length}</span>
          </div>
          <p className="status status-neutral">Unrevealed staged articles are editable and ready for reveal.</p>
          {stagedArticles.length ? (
            <div className="article-stack">
              {stagedArticles.map((article) => {
                const draft = stagedDrafts[article.id] ?? {
                  title: article.title,
                  body: article.body_markdown,
                  imageAltText: article.image?.alt_text || "",
                  imageCaption: article.image?.caption || "",
                };

                return (
                  <details className="article-card" key={article.id}>
                    <summary>
                      <strong>{article.title}</strong>
                    </summary>
                    <label htmlFor={`dm-stage-title-${article.id}`} className="chat-label">
                      Title
                    </label>
                    <input
                      id={`dm-stage-title-${article.id}`}
                      value={draft.title}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => {
                        setStagedDrafts({
                          ...stagedDrafts,
                          [article.id]: {
                            ...draft,
                            title: event.currentTarget.value,
                          },
                        });
                      }}
                    />
                    <label htmlFor={`dm-stage-body-${article.id}`} className="chat-label">
                      Body (markdown or html)
                    </label>
                    <textarea
                      id={`dm-stage-body-${article.id}`}
                      rows={6}
                      value={draft.body}
                      onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                        setStagedDrafts({
                          ...stagedDrafts,
                          [article.id]: {
                            ...draft,
                            body: event.currentTarget.value,
                          },
                        });
                      }}
                    />
                    <label htmlFor={`dm-stage-alt-${article.id}`} className="chat-label">
                      Image alt text (optional)
                    </label>
                    <input
                      id={`dm-stage-alt-${article.id}`}
                      value={draft.imageAltText}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => {
                        setStagedDrafts({
                          ...stagedDrafts,
                          [article.id]: {
                            ...draft,
                            imageAltText: event.currentTarget.value,
                          },
                        });
                      }}
                    />
                    <label htmlFor={`dm-stage-caption-${article.id}`} className="chat-label">
                      Image caption (optional)
                    </label>
                    <input
                      id={`dm-stage-caption-${article.id}`}
                      value={draft.imageCaption}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => {
                        setStagedDrafts({
                          ...stagedDrafts,
                          [article.id]: {
                            ...draft,
                            imageCaption: event.currentTarget.value,
                          },
                        });
                      }}
                    />
                    <div className="article-actions">
                      <button
                        type="button"
                        disabled={updateArticleMutation.isPending}
                        onClick={() =>
                          updateArticleMutation.mutate({
                            id: article.id,
                            payload: {
                              title: draft.title,
                              body_markdown: draft.body,
                              image_alt_text: draft.imageAltText || "",
                              image_caption: draft.imageCaption || "",
                            },
                          })
                        }
                      >
                        {updateArticleMutation.isPending ? "Saving..." : "Save draft"}
                      </button>
                      <button
                        type="button"
                        className="button-danger"
                        disabled={revealArticleMutation.isPending}
                        onClick={() => revealArticleMutation.mutate(article.id)}
                      >
                        {revealArticleMutation.isPending ? "Revealing..." : "Reveal"}
                      </button>
                      <button
                        type="button"
                        className="button-danger"
                        disabled={deleteArticleMutation.isPending}
                        onClick={() => deleteArticleMutation.mutate(article.id)}
                      >
                        {deleteArticleMutation.isPending ? "Deleting..." : "Delete"}
                      </button>
                    </div>
                  </details>
                );
              })}
            </div>
          ) : (
            <p className="status status-neutral">No staged articles.</p>
          )}
        </section>
      </div>

      <section className="split-grid">
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Revealed articles</h3>
            <span className="pill">{revealedArticles.length}</span>
          </div>
          <div className="session-surface-subhead">
            <button
              type="button"
              className="button-danger"
              disabled={clearRevealedMutation.isPending || !revealedArticles.length}
              onClick={() => clearRevealedMutation.mutate()}
            >
              {clearRevealedMutation.isPending ? "Clearing..." : "Clear all revealed"}
            </button>
          </div>
          {revealedArticles.length ? (
            <div className="article-stack">
              {revealedArticles.map((article) => (
                <details className="article-card" key={article.id}>
                  <summary>
                    <strong>{article.title}</strong>
                    <span className="article-kind">{article.source_kind || "unclassified"}</span>
                  </summary>
                  {article.image ? (
                    <img className="article-image" src={resolveArticleImage(campaignSlug, article)} alt={article.image.alt_text || "Article image"} />
                  ) : null}
                  {renderArticleBody(article)}
                  <div className="article-actions">
                    <button
                      type="button"
                      className="button-danger"
                      onClick={() => deleteArticleMutation.mutate(article.id)}
                      disabled={deleteArticleMutation.isPending}
                    >
                      {deleteArticleMutation.isPending ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <p className="status status-neutral">No revealed articles.</p>
          )}
        </section>
        <section className="panel panel-nested">
          <div className="panel-header">
            <h3>Session logs</h3>
            <span className="pill">{sessionLogs.length}</span>
          </div>
          {sessionLogs.length ? (
            <div className="session-log-row">
              <div className="session-log-list">
                {sessionLogs.map((entry) => (
                  <button
                    type="button"
                    key={entry.session.id}
                    className={`session-log-list-row ${entry.session.id === selectedLogSessionId ? "active" : ""}`}
                    onClick={() => setSelectedLogSessionId(entry.session.id)}
                  >
                    <strong>Session {entry.session.id}</strong>
                    <span>{entry.message_count} messages</span>
                    <small>{formatTimestamp(entry.last_message_at)}</small>
                  </button>
                ))}
              </div>
              <div className="session-log-detail">
                {logQuery.isLoading ? (
                  <p className="status status-neutral">Loading log detail...</p>
                ) : null}
                {logQuery.error ? <p className="status status-error">Unable to load log details.</p> : null}
                {logQuery.data ? (
                  <div>
                    <div className="session-log-detail-head">
                      <h4>Messages</h4>
                      <button
                        type="button"
                        className="button-danger"
                        onClick={() => deleteLogMutation.mutate(logQuery.data.session.id)}
                        disabled={deleteLogMutation.isPending}
                      >
                        {deleteLogMutation.isPending ? "Deleting..." : "Delete this log"}
                      </button>
                    </div>
                    <ol className="log-messages">
                      {logQuery.data.messages.map((entry) => (
                        <li key={entry.id}>
                          <strong>{entry.author_display_name}</strong> [{formatTimestamp(entry.created_at)}]
                          <p>{entry.body_text}</p>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : (
                  <p className="status status-neutral">Select a log to inspect.</p>
                )}
              </div>
            </div>
          ) : (
            <p className="status status-neutral">No closed session logs.</p>
          )}
        </section>
      </section>
    </div>
  );
}

function SessionPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/session",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { setAuthRequired } = useApiClient();
  const { apiClient } = useApiClient();
  const [activePane, setActivePane] = useState<PaneName>("session");

  const sessionQuery = useQuery({
    queryKey: ["session", resolvedCampaignSlug],
    queryFn: () => apiClient.getSession(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug),
    refetchInterval: (query) => {
      return query.state.data?.active_session?.is_active ? 3000 : 8000;
    },
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(sessionQuery.error)) {
      setAuthRequired(true);
    }
  }, [sessionQuery.error, setAuthRequired]);

  const payload = sessionQuery.data;
  const canManage = payload?.permissions.can_manage_session ?? false;

  useEffect(() => {
    if (!canManage && activePane === "dm") {
      setActivePane("session");
    }
  }, [activePane, canManage]);

  const paneError = getApiErrorMessage(sessionQuery.error);

  return (
    <section className="panel">
      <div className="panel-header">
        <Link to="/" className="button button-secondary">
          Back to list
        </Link>
        <h2>Session: {payload?.campaign.title ?? resolvedCampaignSlug}</h2>
        {canManage ? <span className="pill">DM+</span> : null}
      </div>

      <ApiErrorNotice
        isLoading={sessionQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />

      <div className="session-tab-strip">
        <button
          type="button"
          className={activePane === "session" ? "tab-button active" : "tab-button"}
          onClick={() => setActivePane("session")}
        >
          Session
        </button>
        <button
          type="button"
          className={activePane === "character" ? "tab-button active" : "tab-button"}
          onClick={() => setActivePane("character")}
        >
          Character
        </button>
        {canManage ? (
          <button
            type="button"
            className={activePane === "dm" ? "tab-button active" : "tab-button"}
            onClick={() => setActivePane("dm")}
          >
            DM
          </button>
        ) : null}
      </div>

      <div className="pane-stack">
        <div className={activePane === "session" ? "pane pane-visible" : "pane pane-hidden"}>
          <SessionPane
            campaignSlug={resolvedCampaignSlug}
            payload={payload}
            refetch={() => sessionQuery.refetch()}
            setAuthRequired={setAuthRequired}
          />
        </div>
        <div className={activePane === "character" ? "pane pane-visible" : "pane pane-hidden"}>
          <CharacterPane campaignSlug={resolvedCampaignSlug} />
        </div>
        {canManage ? (
          <div className={activePane === "dm" ? "pane pane-visible" : "pane pane-hidden"}>
            <DmPane
              campaignSlug={resolvedCampaignSlug}
              payload={payload}
              refetch={() => sessionQuery.refetch()}
              setAuthRequired={setAuthRequired}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}

const rootRoute = createRootRoute({
  component: AppShell,
});

const campaignsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: CampaignListPage,
});

const campaignSessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/session",
  component: SessionPage,
});

const routeTree = rootRoute.addChildren([campaignsRoute, campaignSessionRoute]);
const router = createRouter({
  routeTree,
  basepath: "/app-next",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (root !== null) {
  createRoot(root).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
