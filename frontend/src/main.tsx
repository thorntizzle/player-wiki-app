import React, { useState, useEffect, useMemo } from "react";
import { createRoot } from "react-dom/client";
import {
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
  useLocation,
  useParams,
} from "@tanstack/react-router";
import { QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FormEvent } from "react";
import "./styles.css";
import { apiErrorMessage } from "./api/client";
import type {
  ContentPageFileSummary,
  ContentPageUpsertPayload,
  CombatAvailableCharacterChoice,
  CombatAvailableStatblockChoice,
  CombatSystemsMonsterSearchResult,
  CombatPayload,
  CombatCondition,
  CombatAddNpcPayload,
  CombatTurnPatchPayload,
  CombatVitalsPatchPayload,
  CombatResourcesPatchPayload,
  CombatantSummary,
  DmContentStatblock,
  DmContentStatblockCreatePayload,
  DmContentStatblockUpdatePayload,
  DmContentConditionCreatePayload,
  DmContentConditionDefinition,
  DmContentConditionUpdatePayload,
  SessionArticle,
  SessionArticleCreatePayload,
  SessionArticleSourceResult,
  SessionArticleUpdatePayload,
  SessionPayload,
} from "./api/types";
import {
  coerceSessionPane,
  isAuthRequiredFromError as isAuthError,
  resolveSessionLivePayload,
  type SessionRoutePane,
} from "./sessionRouteState";
import {
  queryClient,
  useApiClient,
} from "./apiClientContext";
import { getApiErrorMessage } from "./apiErrors";
import { ApiErrorNotice } from "./components/feedback";
import { readNumber } from "./characterValueUtils";
import { AccountSettingsPage } from "./routes/AccountSettingsPage";
import { CampaignControlPage } from "./routes/CampaignControlPage";
import { CampaignHelpPage } from "./routes/CampaignHelpPage";
import { WikiArticlePage, WikiHomePage, WikiSectionPage } from "./routes/WikiRoutes";
import {
  SystemsEntryPage,
  SystemsIndexPage,
  SystemsSourceCategoryPage,
  SystemsSourcePage,
} from "./routes/SystemsRoutes";
import { AdminDashboardPage, AdminUserDetailPage } from "./routes/AdminRoutes";
import { CampaignListPage } from "./routes/CampaignPickerPage";
import {
  CharacterAdvancedEditorPage,
  CharacterCreatePage,
  CharacterCultivationPage,
  CharacterLevelUpPage,
  CharacterProgressionRepairPage,
  CharacterRetrainingPage,
  CharacterXianxiaManualImportPage,
} from "./routes/CharacterAuthoringRoutes";
import { DmContentSystemsLane } from "./routes/DmContentSystemsLane";
import { CharacterPane } from "./routes/CharacterPane";
import { DmPane } from "./routes/SessionDmPane";
import { AppShell } from "./AppShell";
import { CharacterRosterPage } from "./routes/CharacterRosterPage";
import { SessionPane } from "./routes/SessionRoutes";
import { DmArticleCreator } from "./components/DmArticleCreator";
import {
  renderArticleBody,
  resolveArticleImage,
  SessionArticleReferenceActions,
  SessionArticleSourceLine,
} from "./components/SessionArticleDisplay";
import { normalizeCharacterSection } from "./characterPaneUtils";
import {
  buildEmptyManualArticleDraft,
  readBinaryAsBase64,
  readTextFile,
  type ArticleMode,
  type EmbeddedImageInput,
  type ManualArticleDraftState,
} from "./sessionArticleDrafts";
import {
  PLAYER_WIKI_SECTION_CHOICES,
  buildInitialConditionDraft,
  buildInitialPlayerWikiDraft,
  buildInitialStatblockDraft,
  buildPageRefFromDraft,
  buildPlayerWikiAssetRef,
  buildPlayerWikiDraftFromRecord,
  buildPlayerWikiMetadata,
  formatInitiativeBonus,
  playerWikiRemovalSafety,
  playerWikiStatusLabel,
  sectionChoiceForLabel,
  simpleSlug,
  type DmContentConditionDraftState,
  type DmContentLane,
  type DmContentStatblockDraftState,
  type DmPlayerWikiDraftState,
  type StagedArticleDraftState,
} from "./dmContentUtils";
import { resolveCombatLivePayload } from "./combatLiveUtils";
import { formatTimestamp } from "./timeFormatting";

declare global {
  interface Window {
    __cpwAppLoadingBegin?: () => void;
    __cpwAppLoadingReady?: () => void;
  }
}

type PaneName = SessionRoutePane;
type CombatView = "player" | "status" | "controls";

interface CombatVitalsDraft {
  currentHp: string;
  maxHp: string;
  tempHp: string;
  movementTotal: string;
}

interface CombatResourcesDraft {
  movementRemaining: string;
  hasAction: boolean;
  hasBonusAction: boolean;
  hasReaction: boolean;
}

interface CombatTurnDraft {
  turnValue: string;
  initiativePriority: string;
}

interface CombatConditionDraft {
  name: string;
  durationText: string;
}

interface CombatPlayerSeedDraft {
  characterSlug: string;
  turnValue: string;
  initiativePriority: string;
}

interface CombatNpcSeedDraft {
  displayName: string;
  turnValue: string;
  initiativeBonus: string;
  dexterityModifier: string;
  initiativePriority: string;
  currentHp: string;
  maxHp: string;
  tempHp: string;
  movementTotal: string;
}

interface CombatStatblockSeedDraft {
  statblockId: string;
  displayName: string;
  turnValue: string;
  initiativePriority: string;
}

interface CombatSystemsSeedDraft {
  entryKey: string;
  displayName: string;
  turnValue: string;
  initiativePriority: string;
}

function DmContentPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/dm-content",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const encodedCampaignSlug = encodeURIComponent(resolvedCampaignSlug);
  const location = useLocation();
  const requestedLane = new URLSearchParams(location.search).get("lane");
  const activeLane: DmContentLane = requestedLane === "staged-articles"
    ? "staged-articles"
    : requestedLane === "conditions"
      ? "conditions"
      : requestedLane === "player-wiki"
        ? "player-wiki"
        : requestedLane === "systems"
          ? "systems"
          : "statblocks";
  const { apiClient, setAuthRequired } = useApiClient();
  const [statblockCreateDraft, setStatblockCreateDraft] = useState<DmContentStatblockDraftState>({
    filename: "gen2-statblock.md",
    subsection: "",
    markdown: "",
  });
  const [statblockQuery, setStatblockQuery] = useState("");
  const [statblockDrafts, setStatblockDrafts] = useState<Record<number, DmContentStatblockDraftState>>({});
  const [mode, setMode] = useState<ArticleMode>("manual");
  const [manualDraft, setManualDraft] = useState<ManualArticleDraftState>(buildEmptyManualArticleDraft);
  const [uploadDraft, setUploadDraft] = useState({
    filename: "",
    markdown: "",
    image: null as EmbeddedImageInput | null,
  });
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceResults, setSourceResults] = useState<SessionArticleSourceResult[]>([]);
  const [sourceStatus, setSourceStatus] = useState<string | null>(null);
  const [selectedSourceRef, setSelectedSourceRef] = useState("");
  const [stagedDrafts, setStagedDrafts] = useState<Record<number, StagedArticleDraftState>>({});
  const [conditionCreateDraft, setConditionCreateDraft] = useState<DmContentConditionDraftState>({
    name: "",
    description: "",
  });
  const [conditionQuery, setConditionQuery] = useState("");
  const [conditionDrafts, setConditionDrafts] = useState<Record<number, DmContentConditionDraftState>>({});
  const [playerWikiCreateDraft, setPlayerWikiCreateDraft] = useState<DmPlayerWikiDraftState>(() => buildInitialPlayerWikiDraft());
  const [playerWikiQuery, setPlayerWikiQuery] = useState("");
  const [playerWikiEditDrafts, setPlayerWikiEditDrafts] = useState<Record<string, DmPlayerWikiDraftState>>({});
  const [playerWikiDeleteConfirm, setPlayerWikiDeleteConfirm] = useState<Record<string, boolean>>({});
  const [uiMessage, setUiMessage] = useState<string | null>(null);
  const [paneError, setPaneError] = useState<string | null>(null);

  const dmContentQuery = useQuery({
    queryKey: ["dm-content", resolvedCampaignSlug],
    queryFn: () => apiClient.getDmContent(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  const sessionQuery = useQuery({
    queryKey: ["dm-content-staged-articles", resolvedCampaignSlug],
    queryFn: async () => {
      const response = await apiClient.getSessionLiveState(resolvedCampaignSlug);
      const resolved = resolveSessionLivePayload(undefined, response);
      if (resolved.state === "full" || resolved.state === "reuse") {
        return resolved.payload;
      }
      throw new Error("Unable to load staged articles.");
    },
    enabled: Boolean(resolvedCampaignSlug) && activeLane === "staged-articles",
    retry: false,
  });

  const contentPagesQuery = useQuery({
    queryKey: ["dm-content-player-wiki-pages", resolvedCampaignSlug],
    queryFn: () => apiClient.getContentPages(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug) && activeLane === "player-wiki",
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(dmContentQuery.error) || isAuthError(sessionQuery.error) || isAuthError(contentPagesQuery.error)) {
      setAuthRequired(true);
    }
  }, [contentPagesQuery.error, dmContentQuery.error, sessionQuery.error, setAuthRequired]);

  const statblocks: DmContentStatblock[] = dmContentQuery.data?.statblocks ?? [];
  const conditions: DmContentConditionDefinition[] = dmContentQuery.data?.conditions ?? [];
  const canManageDmContent = dmContentQuery.data?.permissions.can_manage_dm_content ?? false;

  const stagedArticles: SessionArticle[] = sessionQuery.data?.staged_articles ?? [];
  const canManageSession = sessionQuery.data?.permissions.can_manage_session ?? false;
  const playerWikiPages: ContentPageFileSummary[] = contentPagesQuery.data?.pages ?? [];
  const canManagePlayerWiki = Boolean(contentPagesQuery.data?.ok);

  useEffect(() => {
    setStatblockDrafts((current) => {
      const next: Record<number, DmContentStatblockDraftState> = {};
      for (const statblock of statblocks) {
        next[statblock.id] = current[statblock.id] ?? buildInitialStatblockDraft(statblock);
      }
      return next;
    });
  }, [statblocks]);

  useEffect(() => {
    setConditionDrafts((current) => {
      const next: Record<number, DmContentConditionDraftState> = {};
      for (const condition of conditions) {
        next[condition.id] = current[condition.id] ?? buildInitialConditionDraft(condition);
      }
      return next;
    });
  }, [conditions]);

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
          image: null,
        };
      }
      return next;
    });
  }, [stagedArticles]);

  const filteredStatblocks = useMemo(() => {
    const query = statblockQuery.trim().toLowerCase();
    if (!query) {
      return statblocks;
    }
    return statblocks.filter((statblock) => (
      statblock.title.toLowerCase().includes(query)
      || statblock.subsection.toLowerCase().includes(query)
      || statblock.source_filename.toLowerCase().includes(query)
      || statblock.body_markdown.toLowerCase().includes(query)
    ));
  }, [statblocks, statblockQuery]);

  const topLevelStatblocks = filteredStatblocks.filter((statblock) => !statblock.subsection);
  const statblockSubsectionGroups = useMemo(() => {
    const groups = new Map<string, DmContentStatblock[]>();
    for (const statblock of filteredStatblocks) {
      if (!statblock.subsection) {
        continue;
      }
      const current = groups.get(statblock.subsection) ?? [];
      current.push(statblock);
      groups.set(statblock.subsection, current);
    }
    return Array.from(groups.entries()).map(([name, groupedStatblocks]) => ({
      name,
      statblocks: groupedStatblocks,
    }));
  }, [filteredStatblocks]);

  const filteredConditions = useMemo(() => {
    const query = conditionQuery.trim().toLowerCase();
    if (!query) {
      return conditions;
    }
    return conditions.filter(
      (condition) =>
        condition.name.toLowerCase().includes(query)
        || condition.description_markdown.toLowerCase().includes(query),
    );
  }, [conditions, conditionQuery]);

  const filteredPlayerWikiPages = useMemo(() => {
    const query = playerWikiQuery.trim().toLowerCase();
    if (!query) {
      return playerWikiPages;
    }
    return playerWikiPages.filter((pageFile) => {
      const searchText = [
        pageFile.page_ref,
        pageFile.page.title,
        pageFile.page.section,
        pageFile.page.subsection,
        pageFile.page.page_type,
        pageFile.page.summary,
        pageFile.page.source_ref,
        pageFile.page.image_path,
      ].join(" ").toLowerCase();
      return searchText.includes(query);
    });
  }, [playerWikiPages, playerWikiQuery]);

  const createStatblockMutation = useMutation({
    mutationFn: (payload: DmContentStatblockCreatePayload) => apiClient.createDmContentStatblock(resolvedCampaignSlug, payload),
    onSuccess: (response) => {
      setUiMessage(`Statblock saved: ${response.statblock.title}. ${response.statblock.parser_feedback.summary}`);
      setPaneError(null);
      setStatblockCreateDraft({ filename: "gen2-statblock.md", subsection: "", markdown: "" });
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const updateStatblockMutation = useMutation({
    mutationFn: (args: { id: number; payload: DmContentStatblockUpdatePayload }) =>
      apiClient.updateDmContentStatblock(resolvedCampaignSlug, args.id, args.payload),
    onSuccess: (response) => {
      setUiMessage(`Statblock updated: ${response.statblock.title}. ${response.statblock.parser_feedback.summary}`);
      setPaneError(null);
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteStatblockMutation = useMutation({
    mutationFn: (statblockId: number) => apiClient.deleteDmContentStatblock(resolvedCampaignSlug, statblockId),
    onSuccess: (response) => {
      setUiMessage(`Statblock deleted: ${response.statblock.title}.`);
      setPaneError(null);
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const createConditionMutation = useMutation({
    mutationFn: (payload: DmContentConditionCreatePayload) => apiClient.createDmContentCondition(resolvedCampaignSlug, payload),
    onSuccess: (response) => {
      setUiMessage(`Condition saved: ${response.condition.name}.`);
      setPaneError(null);
      setConditionCreateDraft({ name: "", description: "" });
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const updateConditionMutation = useMutation({
    mutationFn: (args: { id: number; payload: DmContentConditionUpdatePayload }) =>
      apiClient.updateDmContentCondition(resolvedCampaignSlug, args.id, args.payload),
    onSuccess: (response) => {
      setUiMessage(`Condition updated: ${response.condition.name}.`);
      setPaneError(null);
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deleteConditionMutation = useMutation({
    mutationFn: (conditionId: number) => apiClient.deleteDmContentCondition(resolvedCampaignSlug, conditionId),
    onSuccess: (response) => {
      setUiMessage(`Condition deleted: ${response.condition.name}.`);
      setPaneError(null);
      void dmContentQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const savePlayerWikiPageMutation = useMutation({
    mutationFn: async (args: { mode: "create" | "edit"; pageRef: string; draft: DmPlayerWikiDraftState }) => {
      let imageRef = args.draft.image.trim();
      if (args.draft.imageUpload) {
        imageRef = buildPlayerWikiAssetRef(args.pageRef, args.draft.imageUpload);
        await apiClient.upsertContentAsset(resolvedCampaignSlug, imageRef, {
          asset_file: {
            filename: args.draft.imageUpload.filename,
            data_base64: args.draft.imageUpload.data_base64,
            media_type: args.draft.imageUpload.media_type,
          },
        });
      }
      const payload: ContentPageUpsertPayload = {
        metadata: buildPlayerWikiMetadata(args.draft, args.pageRef, imageRef),
        body_markdown: args.draft.bodyMarkdown,
      };
      return apiClient.upsertContentPage(resolvedCampaignSlug, args.pageRef, payload);
    },
    onSuccess: (response, args) => {
      const title = response.page_file.page.title || args.pageRef;
      setUiMessage(args.mode === "create" ? `Player Wiki page created: ${title}.` : `Player Wiki page updated: ${title}.`);
      setPaneError(null);
      if (args.mode === "create") {
        setPlayerWikiCreateDraft(buildInitialPlayerWikiDraft());
      }
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      void contentPagesQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const archivePlayerWikiPageMutation = useMutation({
    mutationFn: async (pageRef: string) => {
      const detail = await apiClient.getContentPage(resolvedCampaignSlug, pageRef);
      const draft = {
        ...buildPlayerWikiDraftFromRecord(detail.page_file),
        published: false,
        imageUpload: null,
      };
      const payload: ContentPageUpsertPayload = {
        metadata: buildPlayerWikiMetadata(draft, detail.page_file.page_ref, draft.image),
        body_markdown: draft.bodyMarkdown,
      };
      return apiClient.upsertContentPage(resolvedCampaignSlug, detail.page_file.page_ref, payload);
    },
    onSuccess: (response) => {
      setUiMessage(`Player Wiki page archived: ${response.page_file.page.title}.`);
      setPaneError(null);
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      void contentPagesQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const deletePlayerWikiPageMutation = useMutation({
    mutationFn: (pageRef: string) => apiClient.deleteContentPage(resolvedCampaignSlug, pageRef),
    onSuccess: (response) => {
      const pageRef = response.deleted.page_ref;
      setUiMessage(`Player Wiki page deleted: ${pageRef}.`);
      setPaneError(null);
      setPlayerWikiDeleteConfirm((current) => ({
        ...current,
        [pageRef]: false,
      }));
      setPlayerWikiEditDrafts((current) => {
        const next = { ...current };
        delete next[pageRef];
        return next;
      });
      void contentPagesQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const loadPlayerWikiEditDraft = async (pageRef: string) => {
    setPaneError(null);
    setUiMessage("Loading Player Wiki editor...");
    try {
      const response = await apiClient.getContentPage(resolvedCampaignSlug, pageRef);
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      setUiMessage(`Editor loaded: ${response.page_file.page.title}.`);
    } catch (error) {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    }
  };

  const createArticleMutation = useMutation({
    mutationFn: (payload: SessionArticleCreatePayload) => apiClient.createSessionArticle(resolvedCampaignSlug, payload),
    onSuccess: () => {
      setUiMessage("Article staged.");
      setPaneError(null);
      setManualDraft(buildEmptyManualArticleDraft());
      setUploadDraft({ filename: "", markdown: "", image: null });
      setSelectedSourceRef("");
      void sessionQuery.refetch();
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
    mutationFn: (args: { id: number; payload: StagedArticleDraftState; hasExistingImage: boolean }) => {
      const imagePayload = args.payload.image
        ? {
            ...args.payload.image,
            alt_text: args.payload.imageAltText || null,
            caption: args.payload.imageCaption || null,
          }
        : undefined;
      const articlePayload: SessionArticleUpdatePayload = {
        title: args.payload.title,
        body_markdown: args.payload.body,
      };
      if (imagePayload) {
        articlePayload.image = imagePayload;
      } else if (args.hasExistingImage) {
        articlePayload.image_alt_text = args.payload.imageAltText || "";
        articlePayload.image_caption = args.payload.imageCaption || "";
      }
      return apiClient.updateSessionArticle(resolvedCampaignSlug, args.id, articlePayload);
    },
    onSuccess: (_response, args) => {
      setUiMessage("Article updated.");
      setPaneError(null);
      setStagedDrafts((current) => ({
        ...current,
        [args.id]: {
          ...current[args.id],
          image: null,
        },
      }));
      void sessionQuery.refetch();
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
    mutationFn: (articleId: number) => apiClient.deleteSessionArticle(resolvedCampaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article removed.");
      setPaneError(null);
      void sessionQuery.refetch();
    },
    onError: (error) => {
      if (isAuthError(error)) {
        setAuthRequired(true);
      }
      setPaneError(apiErrorMessage(error));
      setUiMessage(null);
    },
  });

  const searchSources = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = sourceQuery.trim();
    if (!query) {
      setSourceStatus("Search with a query.");
      return;
    }
    setSourceStatus("Searching ...");
    try {
      const response = await apiClient.searchSessionArticleSources(resolvedCampaignSlug, query);
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

  const clearArticleStatus = () => {
    setPaneError(null);
    setUiMessage(null);
  };
  const pageError = activeLane === "staged-articles"
    ? getApiErrorMessage(sessionQuery.error)
    : activeLane === "player-wiki"
      ? getApiErrorMessage(contentPagesQuery.error)
      : activeLane === "systems"
        ? null
      : getApiErrorMessage(dmContentQuery.error);
  const dmContentSystemsQuery = useQuery({
    queryKey: ["dm-content-systems", resolvedCampaignSlug],
    queryFn: () => apiClient.getDmContentSystems(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug) && activeLane === "systems",
    retry: false,
  });
  const dmContentLede = activeLane === "staged-articles"
    ? "Session reveal article prep."
    : activeLane === "systems"
      ? "Systems policy, custom entries, imports, and history."
      : activeLane === "conditions"
        ? "Custom combat conditions."
        : activeLane === "player-wiki"
          ? "Published player wiki page management."
          : "DM-side statblocks for Combat NPC seeding.";
  const dmContentLaneCounts = {
    statblocks: dmContentQuery.data?.subpage_counts?.statblocks ?? (dmContentQuery.data?.statblocks.length ?? 0),
    conditions: dmContentQuery.data?.subpage_counts?.conditions ?? (dmContentQuery.data?.conditions.length ?? 0),
    stagedArticles: dmContentQuery.data?.subpage_counts?.staged_articles ?? stagedArticles.length,
    playerWiki: dmContentQuery.data?.subpage_counts?.player_wiki ?? playerWikiPages.length,
    systems: dmContentQuery.data?.subpage_counts?.systems ?? (dmContentSystemsQuery.data?.source_count ?? 0),
  };
  const pageIsLoading = activeLane === "staged-articles"
    ? sessionQuery.isLoading
    : activeLane === "player-wiki"
      ? contentPagesQuery.isLoading
      : activeLane === "systems"
        ? false
      : dmContentQuery.isLoading;

  const renderPlayerWikiDraftFields = ({
    idPrefix,
    draft,
    setDraft,
    includeSlug,
    disabled,
  }: {
    idPrefix: string;
    draft: DmPlayerWikiDraftState;
    setDraft: (next: DmPlayerWikiDraftState) => void;
    includeSlug: boolean;
    disabled: boolean;
  }) => {
    const updateDraft = (updates: Partial<DmPlayerWikiDraftState>) => setDraft({ ...draft, ...updates });
    const targetPageRef = buildPageRefFromDraft(draft);
    return (
      <>
        <label htmlFor={`${idPrefix}-title`} className="field">
          <span>Title</span>
          <input
            id={`${idPrefix}-title`}
            name="title"
            maxLength={200}
            value={draft.title}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ title: event.currentTarget.value })}
          />
        </label>
        {includeSlug ? (
          <>
            <label htmlFor={`${idPrefix}-slug`} className="field">
              <span>Slug</span>
              <input
                id={`${idPrefix}-slug`}
                name="slug_leaf"
                maxLength={120}
                value={draft.slugLeaf}
                placeholder="field-report"
                disabled={disabled}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ slugLeaf: event.currentTarget.value })}
              />
            </label>
            <p className="meta">Page file: {targetPageRef}.md</p>
          </>
        ) : null}
        <label htmlFor={`${idPrefix}-section`} className="field">
          <span>Section</span>
          <select
            id={`${idPrefix}-section`}
            name="section"
            value={draft.section}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLSelectElement>) => {
              const section = event.currentTarget.value;
              const currentDefaultType = sectionChoiceForLabel(draft.section).defaultType;
              const nextDefaultType = sectionChoiceForLabel(section).defaultType;
              updateDraft({
                section,
                pageType: draft.pageType && draft.pageType !== currentDefaultType ? draft.pageType : nextDefaultType,
              });
            }}
          >
            {PLAYER_WIKI_SECTION_CHOICES.map((choice) => (
              <option key={choice.label} value={choice.label}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor={`${idPrefix}-type`} className="field">
          <span>Page type</span>
          <input
            id={`${idPrefix}-type`}
            name="page_type"
            maxLength={80}
            value={draft.pageType}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ pageType: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-subsection`} className="field">
          <span>Subsection</span>
          <input
            id={`${idPrefix}-subsection`}
            name="subsection"
            maxLength={120}
            value={draft.subsection}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ subsection: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-summary`} className="field">
          <span>Summary</span>
          <textarea
            id={`${idPrefix}-summary`}
            name="summary"
            rows={3}
            maxLength={400}
            value={draft.summary}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ summary: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-aliases`} className="field">
          <span>Aliases</span>
          <textarea
            id={`${idPrefix}-aliases`}
            name="aliases"
            rows={3}
            value={draft.aliases}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ aliases: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-reveal-after-session`} className="field">
          <span>Reveal after session</span>
          <input
            id={`${idPrefix}-reveal-after-session`}
            name="reveal_after_session"
            type="number"
            min={0}
            value={draft.revealAfterSession}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ revealAfterSession: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-display-order`} className="field">
          <span>Display order</span>
          <input
            id={`${idPrefix}-display-order`}
            name="display_order"
            type="number"
            min={0}
            value={draft.displayOrder}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ displayOrder: event.currentTarget.value })}
          />
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            name="published"
            checked={draft.published}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ published: event.currentTarget.checked })}
          />
          Published
        </label>
        <label htmlFor={`${idPrefix}-source-ref`} className="field">
          <span>Source reference</span>
          <input
            id={`${idPrefix}-source-ref`}
            name="source_ref"
            value={draft.sourceRef}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ sourceRef: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-image`} className="field">
          <span>Image path</span>
          <input
            id={`${idPrefix}-image`}
            name="image"
            value={draft.image}
            placeholder="npcs/example.webp"
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ image: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-image-upload`} className="field">
          <span>Upload image</span>
          <input
            id={`${idPrefix}-image-upload`}
            type="file"
            accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp"
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              const file = event.currentTarget.files?.item(0);
              if (!file) {
                updateDraft({ imageUpload: null });
                return;
              }
              readBinaryAsBase64(file, (payload) => {
                if (!payload) {
                  setPaneError("Unable to read that image file.");
                  setUiMessage(null);
                  return;
                }
                setPaneError(null);
                updateDraft({ imageUpload: payload });
              });
            }}
          />
        </label>
        {draft.imageUpload ? <p className="status status-neutral">Selected image: {draft.imageUpload.filename}</p> : null}
        <label htmlFor={`${idPrefix}-image-alt`} className="field">
          <span>Image alt text</span>
          <input
            id={`${idPrefix}-image-alt`}
            name="image_alt"
            value={draft.imageAlt}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ imageAlt: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-image-caption`} className="field">
          <span>Image caption</span>
          <input
            id={`${idPrefix}-image-caption`}
            name="image_caption"
            value={draft.imageCaption}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft({ imageCaption: event.currentTarget.value })}
          />
        </label>
        <label htmlFor={`${idPrefix}-body`} className="field">
          <span>Markdown body</span>
          <textarea
            id={`${idPrefix}-body`}
            name="body_markdown"
            rows={18}
            value={draft.bodyMarkdown}
            disabled={disabled}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft({ bodyMarkdown: event.currentTarget.value })}
          />
        </label>
      </>
    );
  };

  const renderStatblockCard = (statblock: DmContentStatblock) => {
    const draft = statblockDrafts[statblock.id] ?? buildInitialStatblockDraft(statblock);
    return (
      <article className="dm-content-item dm-statblock-card" id={`dm-statblock-${statblock.id}`} key={statblock.id}>
        <div className="dm-content-item__header">
          <div>
            <h3>{statblock.title}</h3>
            <p className="meta">Source file: {statblock.source_filename}</p>
          </div>
          <div className="badge-list dm-statblock-badges">
            {statblock.armor_class !== null ? <span className="meta-badge">AC {statblock.armor_class}</span> : null}
            <span className="meta-badge">HP {statblock.max_hp}</span>
            <span className="meta-badge">Speed {statblock.speed_text}</span>
            <span className="meta-badge">Init {formatInitiativeBonus(statblock.initiative_bonus)}</span>
          </div>
        </div>
        <p className="status status-neutral">{statblock.parser_feedback.summary}</p>
        <p className="meta">Combat seed source: dm_statblock:{statblock.id}.</p>
        <details className="feature-detail">
          <summary>View statblock text</summary>
          <pre className="dm-content-preview">{statblock.body_markdown}</pre>
        </details>
        {canManageDmContent ? (
          <>
            <details className="feature-detail">
              <summary>Edit statblock source</summary>
              <form
                className="stack-form"
                onSubmit={(event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  updateStatblockMutation.mutate({
                    id: statblock.id,
                    payload: {
                      subsection: String(formData.get("subsection") || ""),
                      markdown_text: String(formData.get("markdown_text") || ""),
                    },
                  });
                }}
              >
                <label className="field">
                  <span>Subsection</span>
                  <input
                    id={`dm-statblock-subsection-${statblock.id}`}
                    name="subsection"
                    value={draft.subsection}
                    disabled={!canManageDmContent}
                    maxLength={80}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      const subsection = event.currentTarget.value;
                      setStatblockDrafts((current) => ({
                        ...current,
                        [statblock.id]: {
                          ...(current[statblock.id] ?? draft),
                          subsection,
                        },
                      }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>Source markdown body</span>
                  <textarea
                    id={`dm-statblock-markdown-${statblock.id}`}
                    name="markdown_text"
                    rows={12}
                    value={draft.markdown}
                    disabled={!canManageDmContent}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                      const markdown = event.currentTarget.value;
                      setStatblockDrafts((current) => ({
                        ...current,
                        [statblock.id]: {
                          ...(current[statblock.id] ?? draft),
                          markdown,
                        },
                      }));
                    }}
                  />
                </label>
                <button type="submit" disabled={!canManageDmContent || updateStatblockMutation.isPending}>
                  {updateStatblockMutation.isPending ? "Saving..." : "Save statblock"}
                </button>
              </form>
            </details>
            <div className="dm-content-item__actions">
              <button
                type="button"
                className="ghost-button"
                disabled={!canManageDmContent || deleteStatblockMutation.isPending}
                onClick={() => deleteStatblockMutation.mutate(statblock.id)}
              >
                {deleteStatblockMutation.isPending ? "Deleting..." : "Delete statblock"}
              </button>
            </div>
          </>
        ) : null}
      </article>
    );
  };

  const renderConditionCard = (condition: DmContentConditionDefinition) => {
    const draft = conditionDrafts[condition.id] ?? buildInitialConditionDraft(condition);
    const hasDescription = condition.description_markdown.trim().length > 0;
    return (
      <article className="dm-content-item dm-condition-card" id={`dm-condition-${condition.id}`} key={condition.id}>
        <div className="dm-content-item__header">
          <div>
            <h3>{condition.name}</h3>
          </div>
        </div>
        {hasDescription ? (
          <pre className="dm-content-preview dm-content-preview--compact">{condition.description_markdown}</pre>
        ) : (
          <p className="meta">No description saved.</p>
        )}
        {canManageDmContent ? (
          <details className="feature-detail">
            <summary>Edit condition</summary>
              <form
                className="stack-form"
                onSubmit={(event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  const updatedName = String(formData.get("name") || "").trim();
                  const description = String(formData.get("description_markdown") || "");
                  updateConditionMutation.mutate({
                    id: condition.id,
                    payload: {
                      name: updatedName || condition.name,
                      description_markdown: description,
                    },
                  });
                }}
              >
                <label className="field">
                  <span>Condition name</span>
                  <input
                    id={`dm-condition-name-${condition.id}`}
                    name="name"
                    value={draft.name}
                    disabled={!canManageDmContent}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      const name = event.currentTarget.value;
                      setConditionDrafts((current) => ({
                        ...current,
                        [condition.id]: {
                          ...(current[condition.id] ?? draft),
                          name,
                        },
                      }));
                    }}
                  />
                </label>
                <label className="field">
                  <span>Description</span>
                  <textarea
                    id={`dm-condition-description-${condition.id}`}
                    name="description_markdown"
                    rows={8}
                    value={draft.description}
                    disabled={!canManageDmContent}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                      const description = event.currentTarget.value;
                      setConditionDrafts((current) => ({
                        ...current,
                        [condition.id]: {
                          ...(current[condition.id] ?? draft),
                          description,
                        },
                      }));
                    }}
                  />
                </label>
                <button type="submit" disabled={!canManageDmContent || updateConditionMutation.isPending}>
                  {updateConditionMutation.isPending ? "Saving..." : "Save condition"}
                </button>
              </form>
          </details>
        ) : null}
        {canManageDmContent ? (
          <div className="dm-content-item__actions">
            <button
              type="button"
              className="ghost-button"
              disabled={!canManageDmContent || deleteConditionMutation.isPending}
              onClick={() => deleteConditionMutation.mutate(condition.id)}
            >
              {deleteConditionMutation.isPending ? "Deleting..." : "Delete condition"}
            </button>
          </div>
        ) : null}
      </article>
    );
  };

  const renderPlayerWikiPageCard = (pageFile: ContentPageFileSummary) => {
    const safety = playerWikiRemovalSafety(pageFile);
    const editDraft = playerWikiEditDrafts[pageFile.page_ref];
    const deleteConfirmed = Boolean(playerWikiDeleteConfirm[pageFile.page_ref]);
    const encodedPageRef = pageFile.page_ref
      .split("/")
      .map((part) => encodeURIComponent(part))
      .join("/");
    const isDeleting = deletePlayerWikiPageMutation.isPending;
    const pageId = `wiki-page-${simpleSlug(pageFile.page_ref)}`;
    return (
      <article
        className="dm-content-item dm-player-wiki-card"
        key={pageFile.page_ref}
        id={pageId}
      >
        <div className="dm-content-item__header">
          <div>
            <h3>{pageFile.page.title || pageFile.page_ref}</h3>
            <p className="meta">{pageFile.page_ref}.md</p>
            {pageFile.page.summary ? <p className="meta">{pageFile.page.summary}</p> : null}
          </div>
          <div className="badge-list">
            <span className="meta-badge">{playerWikiStatusLabel(pageFile)}</span>
            <span className="meta-badge">{pageFile.page.section || "Unsectioned"}</span>
            {pageFile.page.subsection ? <span className="meta-badge">{pageFile.page.subsection}</span> : null}
            {pageFile.page.image_path ? <span className="meta-badge">Image</span> : null}
            <span className="meta-badge">{safety.removal_status_label}</span>
          </div>
        </div>
        {pageFile.page.source_ref ? <p className="meta">Source: {pageFile.page.source_ref}</p> : null}
        <div className="dm-content-removal-safety">
          <p className="meta">
            <strong>Removal safety:</strong> {safety.removal_guidance}
          </p>
          {safety.hard_delete_blockers.length ? (
            <ul className="plain-list">
              {safety.hard_delete_blockers.map((blocker) => (
                <li className="meta" key={blocker}>
                  {blocker}
            </li>
          ))}
        </ul>
      ) : null}
        </div>
        <div className="dm-content-item__actions">
          <button
            type="button"
            className="ghost-button"
            disabled={!canManagePlayerWiki}
            onClick={() => void loadPlayerWikiEditDraft(pageFile.page_ref)}
          >
            Edit
          </button>
          {pageFile.page.is_visible ? (
            <a
              className="ghost-button"
              href={`/app-next/campaigns/${encodedCampaignSlug}/pages/${encodedPageRef}`}
            >
              Open
            </a>
          ) : null}
          <button
            type="button"
            className="ghost-button"
            disabled={!canManagePlayerWiki || archivePlayerWikiPageMutation.isPending || !pageFile.page.published}
            onClick={() => archivePlayerWikiPageMutation.mutate(pageFile.page_ref)}
          >
            {archivePlayerWikiPageMutation.isPending ? "Archiving..." : "Unpublish/archive"}
          </button>
          {safety.can_hard_delete ? (
            <form className="dm-content-delete-form">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={deleteConfirmed}
                  disabled={!canManagePlayerWiki || !safety.can_hard_delete}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const checked = event.currentTarget.checked;
                    setPlayerWikiDeleteConfirm((current) => ({
                      ...current,
                      [pageFile.page_ref]: checked,
                    }));
                  }}
                />
                Confirm hard delete
              </label>
              <button
                type="button"
                className="ghost-button"
                disabled={!canManagePlayerWiki || !safety.can_hard_delete || !deleteConfirmed || isDeleting}
                onClick={() => deletePlayerWikiPageMutation.mutate(pageFile.page_ref)}
              >
                {isDeleting ? "Deleting..." : "Delete file"}
              </button>
            </form>
          ) : null}
        </div>
        {editDraft ? (
          <form
            className="stack-form dm-content-wiki-form"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              if (!editDraft.title.trim()) {
                setPaneError("Player Wiki page title is required.");
                setUiMessage(null);
                return;
              }
              savePlayerWikiPageMutation.mutate({
                mode: "edit",
                pageRef: pageFile.page_ref,
                draft: editDraft,
              });
            }}
          >
            <p className="meta">Page file: {pageFile.page_ref}.md</p>
            {renderPlayerWikiDraftFields({
              idPrefix: `dm-player-wiki-edit-${simpleSlug(pageFile.page_ref)}`,
              draft: editDraft,
              setDraft: (next) => {
                setPlayerWikiEditDrafts((current) => ({
                  ...current,
                  [pageFile.page_ref]: next,
                }));
              },
              includeSlug: false,
              disabled: !canManagePlayerWiki,
            })}
            <div className="dm-content-item__actions">
              <button type="submit" disabled={!canManagePlayerWiki || savePlayerWikiPageMutation.isPending}>
                {savePlayerWikiPageMutation.isPending ? "Saving..." : "Save wiki page"}
              </button>
            </div>
          </form>
        ) : null}
      </article>
    );
  };

  return (
    <>
      <section className="hero compact dm-content-hero">
        <p className="eyebrow">DM content</p>
        <h1>DM Content</h1>
        <p className="lede">{dmContentLede}</p>
        <nav className="character-subpage-nav dm-content-subpage-nav" aria-label="DM Content subpages">
          <a
            className={activeLane === "statblocks" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content`}
          >
            <span>Statblocks</span>
            <span className="meta-badge">{dmContentLaneCounts.statblocks}</span>
          </a>
          <a
            className={activeLane === "staged-articles" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=staged-articles`}
          >
            <span>Staged Articles</span>
            <span className="meta-badge">{dmContentLaneCounts.stagedArticles}</span>
          </a>
          <a
            className={activeLane === "conditions" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=conditions`}
          >
            <span>Conditions</span>
            <span className="meta-badge">{dmContentLaneCounts.conditions}</span>
          </a>
          <a
            className={activeLane === "player-wiki" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=player-wiki`}
          >
            <span>Player Wiki</span>
            <span className="meta-badge">{dmContentLaneCounts.playerWiki}</span>
          </a>
          <a
            className={activeLane === "systems" ? "button-link" : "ghost-button"}
            href={`/app-next/campaigns/${encodedCampaignSlug}/dm-content?lane=systems`}
          >
            <span>Systems</span>
            <span className="meta-badge">{dmContentLaneCounts.systems}</span>
          </a>
        </nav>
      </section>

      <ApiErrorNotice
        isLoading={pageIsLoading}
        message={pageError}
        onAuth={() => setAuthRequired(true)}
      />

      {paneError ? <p className="status status-error">{paneError}</p> : null}
      {uiMessage ? <p className="status status-neutral">{uiMessage}</p> : null}
      {activeLane === "statblocks" && !canManageDmContent && !dmContentQuery.isLoading ? (
        <p className="status status-error">You do not have permission to manage DM Content statblocks.</p>
      ) : null}
      {activeLane === "conditions" && !canManageDmContent && !dmContentQuery.isLoading ? (
        <p className="status status-error">You do not have permission to manage DM Content conditions.</p>
      ) : null}
      {activeLane === "staged-articles" && !canManageSession && !sessionQuery.isLoading ? (
        <p className="status status-error">You do not have permission to manage staged articles.</p>
      ) : null}
      {activeLane === "player-wiki" && !canManagePlayerWiki && !contentPagesQuery.isLoading ? (
        <p className="status status-error">You do not have permission to manage Player Wiki pages.</p>
      ) : null}

      {activeLane === "statblocks" ? (
        <div className="split-grid dm-content-staged-grid">
          <section className="card dm-statblock-create">
            <div className="section-heading">
              <h2>Create statblock</h2>
              <p className="meta">Upload or paste markdown for DM-side encounter prep.</p>
            </div>
            <form
              className="stack-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                createStatblockMutation.mutate({
                  filename: String(formData.get("filename") || "gen2-statblock.md").trim() || "gen2-statblock.md",
                  subsection: String(formData.get("subsection") || ""),
                  markdown_text: String(formData.get("markdown_text") || ""),
                });
              }}
            >
              <label className="field">
                <span>Import markdown file</span>
                <input
                  id="dm-statblock-create-file-import"
                  type="file"
                  accept=".md,.markdown,text/markdown,text/plain"
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const file = event.currentTarget.files?.item(0);
                    if (!file) {
                      return;
                    }
                    readTextFile(file, (payload) => {
                      if (!payload) {
                        setPaneError("Unable to read that markdown file.");
                        setUiMessage(null);
                        return;
                      }
                      setPaneError(null);
                      setUiMessage(null);
                      setStatblockCreateDraft((current) => ({
                        ...current,
                        filename: payload.filename,
                        markdown: payload.text,
                      }));
                    });
                  }}
                />
              </label>
              <label className="field">
                <span>Source filename</span>
                <input
                  id="dm-statblock-create-filename"
                  name="filename"
                  value={statblockCreateDraft.filename}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const filename = event.currentTarget.value;
                    setStatblockCreateDraft((current) => ({
                      ...current,
                      filename,
                    }));
                  }}
                />
              </label>
              <label className="field">
                <span>Subsection</span>
                <input
                  id="dm-statblock-create-subsection"
                  name="subsection"
                  maxLength={80}
                  value={statblockCreateDraft.subsection}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const subsection = event.currentTarget.value;
                    setStatblockCreateDraft((current) => ({
                      ...current,
                      subsection,
                    }));
                  }}
                />
              </label>
              <label className="field">
                <span>Source markdown body</span>
                <textarea
                  id="dm-statblock-create-markdown"
                  name="markdown_text"
                  rows={16}
                  value={statblockCreateDraft.markdown}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                    const markdown = event.currentTarget.value;
                    setStatblockCreateDraft((current) => ({
                      ...current,
                      markdown,
                    }));
                  }}
                />
              </label>
              <button type="submit" disabled={!canManageDmContent || createStatblockMutation.isPending}>
                {createStatblockMutation.isPending ? "Saving..." : "Save statblock"}
              </button>
            </form>
          </section>

          <section className="card dm-statblock-library">
            <div className="section-heading">
              <div>
                <h2>Statblock library</h2>
                <p className="meta">Uploaded here for DM-side encounter prep. Campaigns can pull these directly into Combat.</p>
              </div>
            </div>
            <form
              className="search-form dm-statblock-search"
              onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
            >
              <label htmlFor="dm-statblock-search">Search statblocks</label>
              <input
                id="dm-statblock-search"
                type="search"
                value={statblockQuery}
                placeholder="Title, subsection, source, text"
                onChange={(event: ChangeEvent<HTMLInputElement>) => setStatblockQuery(event.currentTarget.value)}
              />
            </form>
            {dmContentQuery.isLoading ? <p className="status status-neutral">Loading statblocks ...</p> : null}
            {!dmContentQuery.isLoading && filteredStatblocks.length ? (
              <div className="dm-content-list dm-statblock-groups">
                {topLevelStatblocks.map(renderStatblockCard)}
                {statblockSubsectionGroups.map((group) => (
                  <details className="section-block section-block--collapsible" key={group.name} open>
                    <summary className="section-toggle-summary">
                      <span className="section-toggle-summary__content">
                        <span className="section-title">{group.name}</span>
                        <span className="meta">{group.statblocks.length} statblock{group.statblocks.length === 1 ? "" : "s"}</span>
                      </span>
                      <span className="section-toggle-chevron" aria-hidden="true" />
                    </summary>
                    <div className="section-block__body">
                      <div className="dm-content-list">
                        {group.statblocks.map(renderStatblockCard)}
                      </div>
                    </div>
                  </details>
                ))}
              </div>
            ) : null}
            {!dmContentQuery.isLoading && !filteredStatblocks.length ? (
              <p className="status status-neutral">
                {statblockQuery ? "No statblocks matched that search." : "No DM statblocks have been uploaded yet."}
              </p>
            ) : null}
          </section>
        </div>
      ) : activeLane === "conditions" ? (
        <div className="split-grid dm-content-staged-grid">
          <section className="card dm-condition-create">
            <div className="section-heading">
              <h2>Create condition</h2>
              <p className="meta">Custom combat condition reminder.</p>
            </div>
            <form
              className="stack-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                const name = String(formData.get("name") || "").trim();
                const description = String(formData.get("description_markdown") || "");
                if (!name) {
                  setPaneError("Condition name is required.");
                  setUiMessage(null);
                  return;
                }
                createConditionMutation.mutate({
                  name,
                  description_markdown: description,
                });
              }}
            >
              <label className="field">
                <span>Condition name</span>
                <input
                  id="dm-condition-create-name"
                  name="name"
                  value={conditionCreateDraft.name}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => {
                    const name = event.currentTarget.value;
                    setConditionCreateDraft((current) => ({
                      ...current,
                      name,
                    }));
                  }}
                />
              </label>
              <label className="field">
                <span>Description</span>
                <textarea
                  id="dm-condition-create-description"
                  name="description_markdown"
                  rows={10}
                  value={conditionCreateDraft.description}
                  disabled={!canManageDmContent}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                    const description = event.currentTarget.value;
                    setConditionCreateDraft((current) => ({
                      ...current,
                      description,
                    }));
                  }}
                />
              </label>
              <button type="submit" disabled={!canManageDmContent || createConditionMutation.isPending}>
                {createConditionMutation.isPending ? "Saving..." : "Save condition"}
              </button>
            </form>
          </section>

          <section className="card dm-condition-library">
            <div className="section-heading">
              <div>
                <h2>Custom conditions</h2>
                <p className="meta">These names appear in the combat condition picker alongside the standard DND-5E condition list.</p>
              </div>
            </div>
            <form
              className="search-form dm-condition-search"
              onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
            >
              <label htmlFor="dm-condition-search">Search conditions</label>
              <input
                id="dm-condition-search"
                type="search"
                value={conditionQuery}
                placeholder="Name or description"
                onChange={(event: ChangeEvent<HTMLInputElement>) => setConditionQuery(event.currentTarget.value)}
              />
            </form>
            {dmContentQuery.isLoading ? <p className="status status-neutral">Loading conditions ...</p> : null}
            {!dmContentQuery.isLoading && filteredConditions.length ? (
              <div className="dm-content-list dm-condition-list">
                {filteredConditions.map(renderConditionCard)}
              </div>
            ) : null}
            {!dmContentQuery.isLoading && !filteredConditions.length ? (
              <p className="status status-neutral">
                {conditionQuery ? "No conditions matched that search." : "No custom conditions have been created yet."}
              </p>
            ) : null}
          </section>
        </div>
      ) : activeLane === "player-wiki" ? (
        <div className="split-grid dm-content-staged-grid">
          <section className="card dm-player-wiki-create">
            <div className="section-heading">
              <h2>Create player wiki page</h2>
              <p className="meta">Direct authoring for durable player-facing reference pages.</p>
            </div>
            <form
              className="stack-form dm-content-wiki-form"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                if (!playerWikiCreateDraft.title.trim()) {
                  setPaneError("Player Wiki page title is required.");
                  setUiMessage(null);
                  return;
                }
                savePlayerWikiPageMutation.mutate({
                  mode: "create",
                  pageRef: buildPageRefFromDraft(playerWikiCreateDraft),
                  draft: playerWikiCreateDraft,
                });
              }}
            >
              {renderPlayerWikiDraftFields({
                idPrefix: "dm-player-wiki-create",
                draft: playerWikiCreateDraft,
                setDraft: setPlayerWikiCreateDraft,
                includeSlug: true,
                disabled: !canManagePlayerWiki,
              })}
              <button type="submit" disabled={!canManagePlayerWiki || savePlayerWikiPageMutation.isPending}>
                {savePlayerWikiPageMutation.isPending ? "Saving..." : "Create wiki page"}
              </button>
            </form>
          </section>

          <section className="card dm-player-wiki-library">
            <div className="section-heading">
              <h2>Player wiki pages</h2>
              <p className="meta">{playerWikiPages.length} page{playerWikiPages.length === 1 ? "" : "s"}</p>
            </div>
            <form
              className="search-form dm-player-wiki-search"
              onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
            >
              <label htmlFor="dm-player-wiki-search">Search pages</label>
              <input
                id="dm-player-wiki-search"
                type="search"
                value={playerWikiQuery}
                placeholder="Title, section, path, summary"
                onChange={(event: ChangeEvent<HTMLInputElement>) => setPlayerWikiQuery(event.currentTarget.value)}
              />
            </form>
            {contentPagesQuery.isLoading ? <p className="status status-neutral">Loading Player Wiki pages ...</p> : null}
            {!contentPagesQuery.isLoading && filteredPlayerWikiPages.length ? (
              <div className="dm-content-list dm-player-wiki-list">
                {filteredPlayerWikiPages.map(renderPlayerWikiPageCard)}
              </div>
            ) : null}
            {!contentPagesQuery.isLoading && !filteredPlayerWikiPages.length ? (
              <p className="status status-neutral">
                {playerWikiQuery ? "No Player Wiki pages matched that search." : "No Player Wiki pages have been published yet."}
              </p>
            ) : null}
          </section>
        </div>
      ) : activeLane === "systems" ? (
        <DmContentSystemsLane campaignSlug={resolvedCampaignSlug} />
      ) : (
        <div className="split-grid dm-content-staged-grid">
          <DmArticleCreator
            className="card"
            id="dm-content-staged-article-store"
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
              setSourceStatus(null);
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
            onCreate={(payload) => {
              clearArticleStatus();
              createArticleMutation.mutate(payload);
            }}
            isCreating={createArticleMutation.isPending}
          />

          <article className="card" id="dm-content-staged-articles-queue">
            <div className="section-heading">
              <div>
                <h2>Session reveal queue</h2>
                <p className="meta">Articles created here go straight into the same staged queue used on Session DM.</p>
              </div>
              <p className="meta">{stagedArticles.length}</p>
            </div>
            {stagedArticles.length ? (
              <div className="session-article-stack">
                {stagedArticles.map((article) => {
                  const draft = stagedDrafts[article.id] ?? {
                    title: article.title,
                    body: article.body_markdown,
                    imageAltText: article.image?.alt_text || "",
                    imageCaption: article.image?.caption || "",
                    image: null,
                  };
                  const savedLabel = article.created_at ? `Saved ${formatTimestamp(article.created_at)}` : null;
                  return (
                    <details
                      className="feature-detail session-article-detail"
                      data-session-article-id={article.id}
                      key={article.id}
                    >
                      <summary>
                        <span>{article.title}</span>
                        {savedLabel ? <span className="meta">{savedLabel}</span> : null}
                      </summary>
                      {article.image ? (
                        <figure className="article-figure">
                          <img
                            className="article-image"
                            src={resolveArticleImage(resolvedCampaignSlug, article)}
                            alt={article.image.alt_text || "Article image"}
                          />
                          {article.image.caption ? <figcaption className="meta article-image__caption">{article.image.caption}</figcaption> : null}
                        </figure>
                      ) : null}
                      <SessionArticleSourceLine article={article} />
                      {renderArticleBody(article, "article-body--compact")}
                      <details className="session-article-edit-detail">
                        <summary>Edit prep draft</summary>
                        <form
                          className="stack-form session-article-edit-form"
                          onSubmit={(event: FormEvent<HTMLFormElement>) => {
                            event.preventDefault();
                            const formData = new FormData(event.currentTarget);
                            const currentDraft = stagedDrafts[article.id] ?? draft;
                            updateArticleMutation.mutate({
                              id: article.id,
                              hasExistingImage: Boolean(article.image),
                              payload: {
                                title: String(formData.get("title") || ""),
                                body: String(formData.get("body_markdown") || ""),
                                imageAltText: String(formData.get("image_alt_text") || ""),
                                imageCaption: String(formData.get("image_caption") || ""),
                                image: currentDraft.image ?? null,
                              },
                            });
                          }}
                        >
                          <label className="field">
                            <span>Title</span>
                            <input
                              id={`dm-content-stage-title-${article.id}`}
                              name="title"
                              value={draft.title}
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                                const title = event.currentTarget.value;
                                setStagedDrafts((current) => ({
                                  ...current,
                                  [article.id]: {
                                    ...(current[article.id] ?? draft),
                                    title,
                                  },
                                }));
                              }}
                            />
                          </label>
                          <label className="field">
                            <span>Body</span>
                            <textarea
                              id={`dm-content-stage-body-${article.id}`}
                              name="body_markdown"
                              rows={8}
                              value={draft.body}
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => {
                                const body = event.currentTarget.value;
                                setStagedDrafts((current) => ({
                                  ...current,
                                  [article.id]: {
                                    ...(current[article.id] ?? draft),
                                    body,
                                  },
                                }));
                              }}
                            />
                          </label>
                          <div className="field session-file-field">
                            <span>{article.image ? "Replace image" : "Image"}</span>
                            <input
                              id={`dm-content-stage-image-${article.id}`}
                              className="session-file-input"
                              type="file"
                              accept=".png,.jpg,.jpeg,.webp,.gif"
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                                const file = event.currentTarget.files?.item(0);
                                if (!file) {
                                  setStagedDrafts((current) => ({
                                    ...current,
                                    [article.id]: {
                                      ...(current[article.id] ?? draft),
                                      image: null,
                                    },
                                  }));
                                  return;
                                }
                                readBinaryAsBase64(file, (payload) => {
                                  setStagedDrafts((current) => ({
                                    ...current,
                                    [article.id]: {
                                      ...(current[article.id] ?? draft),
                                      image: payload,
                                    },
                                  }));
                                });
                              }}
                            />
                            <label className="session-file-dropzone" htmlFor={`dm-content-stage-image-${article.id}`} tabIndex={0}>
                              <span>Drag and drop a file here</span>
                              <span className="meta">or use Browse to choose one</span>
                              <span className="session-file-dropzone__browse">Browse</span>
                              <span className="meta session-file-dropzone__name">No file selected.</span>
                            </label>
                          </div>
                          <label className="field">
                            <span>Image alt text</span>
                            <input
                              id={`dm-content-stage-alt-${article.id}`}
                              name="image_alt_text"
                              value={draft.imageAltText}
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                                const imageAltText = event.currentTarget.value;
                                setStagedDrafts((current) => ({
                                  ...current,
                                  [article.id]: {
                                    ...(current[article.id] ?? draft),
                                    imageAltText,
                                  },
                                }));
                              }}
                            />
                          </label>
                          <label className="field">
                            <span>Image caption</span>
                            <input
                              id={`dm-content-stage-caption-${article.id}`}
                              name="image_caption"
                              value={draft.imageCaption}
                              disabled={!canManageSession}
                              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                                const imageCaption = event.currentTarget.value;
                                setStagedDrafts((current) => ({
                                  ...current,
                                  [article.id]: {
                                    ...(current[article.id] ?? draft),
                                    imageCaption,
                                  },
                                }));
                              }}
                            />
                          </label>
                          {draft.image ? <p className="status status-neutral">Selected image: {draft.image.filename}</p> : null}
                          <button
                            type="submit"
                            className="ghost-button"
                            disabled={!canManageSession || updateArticleMutation.isPending}
                          >
                            {updateArticleMutation.isPending ? "Saving..." : "Update prep draft"}
                          </button>
                        </form>
                      </details>
                      <div className="session-article-detail__actions">
                        <SessionArticleReferenceActions article={article} includePromotionLinks />
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={!canManageSession || deleteArticleMutation.isPending}
                          onClick={() => deleteArticleMutation.mutate(article.id)}
                        >
                          {deleteArticleMutation.isPending ? "Deleting..." : "Delete article"}
                        </button>
                      </div>
                    </details>
                );
              })}
            </div>
          ) : (
            <p className="status status-neutral">No staged articles.</p>
          )}
          </article>
      </div>
      )}
    </>
  );
}

function CharacterDetailPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/characters/$characterSlug",
  });
  const location = useLocation();
  const campaignSlug = params.campaignSlug ?? "";
  const characterSlug = params.characterSlug ?? "";
  const initialSection = normalizeCharacterSection(new URLSearchParams(location.search).get("page"));

  return (
    <CharacterPane
      campaignSlug={campaignSlug}
      initialCharacterSlug={characterSlug}
      initialSection={initialSection}
      surface="read"
      onSelectedCharacterChange={(nextSlug) => {
        window.history.pushState(
          null,
          "",
          `/app-next/campaigns/${encodeURIComponent(campaignSlug)}/characters/${encodeURIComponent(nextSlug)}`,
        );
      }}
    />
  );
}

function CombatPage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/combat",
  });
  const location = useLocation();
  const campaignSlug = params.campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const readSearchView = (search: string): CombatView => {
    const requested = new URLSearchParams(search).get("view");
    return requested === "status" || requested === "controls" ? requested : "player";
  };
  const [selectedCombatantId, setSelectedCombatantId] = useState<number | null>(() => {
    const parsed = Number(new URLSearchParams(window.location.search).get("combatant") || "");
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  });
  const [activeCombatView, setActiveCombatView] = useState<CombatView>(() => readSearchView(window.location.search));
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [vitalsDraft, setVitalsDraft] = useState<CombatVitalsDraft>({
    currentHp: "",
    maxHp: "",
    tempHp: "",
    movementTotal: "",
  });
  const [resourcesDraft, setResourcesDraft] = useState<CombatResourcesDraft>({
    movementRemaining: "",
    hasAction: false,
    hasBonusAction: false,
    hasReaction: false,
  });
  const [turnDraft, setTurnDraft] = useState<CombatTurnDraft>({ turnValue: "", initiativePriority: "1" });
  const [conditionDraft, setConditionDraft] = useState<CombatConditionDraft>({ name: "", durationText: "" });
  const [playerSeedDraft, setPlayerSeedDraft] = useState<CombatPlayerSeedDraft>({
    characterSlug: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [npcSeedDraft, setNpcSeedDraft] = useState<CombatNpcSeedDraft>({
    displayName: "",
    turnValue: "",
    initiativeBonus: "0",
    dexterityModifier: "",
    initiativePriority: "1",
    currentHp: "",
    maxHp: "",
    tempHp: "0",
    movementTotal: "30",
  });
  const [statblockSeedDraft, setStatblockSeedDraft] = useState<CombatStatblockSeedDraft>({
    statblockId: "",
    displayName: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [systemsSeedDraft, setSystemsSeedDraft] = useState<CombatSystemsSeedDraft>({
    entryKey: "",
    displayName: "",
    turnValue: "",
    initiativePriority: "1",
  });
  const [combatAddMode, setCombatAddMode] = useState<"player" | "systems" | "dm-content" | "custom">(
    "player",
  );
  const [systemsSearchQuery, setSystemsSearchQuery] = useState("");
  const [systemsSearchStatus, setSystemsSearchStatus] = useState<string | null>(null);
  const [systemsSearchResults, setSystemsSearchResults] = useState<CombatSystemsMonsterSearchResult[]>([]);
  const [confirmClearTracker, setConfirmClearTracker] = useState(false);

  useEffect(() => {
    const currentSearch = window.location.search;
    const params = new URLSearchParams(currentSearch);
    const parsed = Number(params.get("combatant") || "");
    setSelectedCombatantId(Number.isFinite(parsed) && parsed > 0 ? parsed : null);
    setActiveCombatView(readSearchView(currentSearch));
  }, [location.href]);

  const combatQuery = useQuery({
    queryKey: ["combat", campaignSlug, activeCombatView, selectedCombatantId],
    queryFn: async () => {
      const previous = queryClient.getQueryData<CombatPayload>([
        "combat",
        campaignSlug,
        activeCombatView,
        selectedCombatantId,
      ]);
      if (!previous) {
        return apiClient.getCombat(campaignSlug, selectedCombatantId);
      }
      const liveResponse = await apiClient.getCombatLiveState(campaignSlug, {
        liveRevision: previous.live_revision,
        liveViewToken: previous.live_view_token,
        combatantId: selectedCombatantId,
      });
      const resolved = resolveCombatLivePayload(previous, liveResponse);
      return resolved ?? apiClient.getCombat(campaignSlug, selectedCombatantId);
    },
    enabled: Boolean(campaignSlug),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && !data.combat_system_supported) {
        return false;
      }
      return data?.poll_settings?.active_interval_ms ?? 3000;
    },
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(combatQuery.error)) {
      setAuthRequired(true);
    }
  }, [combatQuery.error, setAuthRequired]);

  const payload = combatQuery.data;
  const tracker = payload?.tracker;
  const selectedCombatant = payload?.selected_combatant ?? null;
  const selectedCombatantMeta = selectedCombatant
    ? selectedCombatant.subtitle || selectedCombatant.source_label || selectedCombatant.type_label
    : "";
  const selectedPlayerCharacter = payload?.selected_player_character ?? null;
  const selectedCharacterSlug = selectedPlayerCharacter?.character_slug || null;
  const selectedCombatantKicker =
    selectedCombatant?.character_slug && selectedCombatant.character_slug === selectedCharacterSlug
      ? "Combat workspace"
      : "Combat snapshot";
  const canManageCombat = Boolean(payload?.permissions.can_manage_combat);
  const canAccessDmContent = Boolean(payload?.permissions.can_access_dm_content);
  const canAccessSystems = Boolean(payload?.permissions.can_access_systems);
  const effectiveCombatView: CombatView = canManageCombat ? activeCombatView : "player";
  const paneError = getApiErrorMessage(combatQuery.error);
  const availableCharacters: CombatAvailableCharacterChoice[] = payload?.available_character_choices ?? [];
  const availableStatblocks: CombatAvailableStatblockChoice[] = payload?.available_statblock_choices ?? [];
  const conditionOptions = payload?.combat_condition_options ?? [];
  const encodedCampaignSlug = encodeURIComponent(campaignSlug);

  useEffect(() => {
    if (!canAccessSystems && combatAddMode === "systems") {
      setCombatAddMode("player");
    } else if (!canAccessDmContent && combatAddMode === "dm-content") {
      setCombatAddMode("player");
    }
  }, [canAccessSystems, canAccessDmContent, combatAddMode]);

  const setCombatUrl = (view: CombatView, combatantId: number | null) => {
    const params = new URLSearchParams();
    if (view !== "player") {
      params.set("view", view);
    }
    if (combatantId) {
      params.set("combatant", String(combatantId));
    }
    const query = params.toString();
    window.history.pushState(null, "", `/app-next/campaigns/${encodedCampaignSlug}/combat${query ? `?${query}` : ""}`);
  };

  useEffect(() => {
    if (!payload?.permissions.can_manage_combat) {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (!params.has("view") && activeCombatView === "player") {
      setActiveCombatView("status");
      setCombatUrl("status", selectedCombatantId);
    }
  }, [payload?.permissions.can_manage_combat]);

  useEffect(() => {
    if (!selectedCombatant) {
      return;
    }
    setVitalsDraft({
      currentHp: String(readNumber(selectedCombatant.current_hp)),
      maxHp: String(readNumber(selectedCombatant.max_hp)),
      tempHp: String(readNumber(selectedCombatant.temp_hp)),
      movementTotal: String(readNumber(selectedCombatant.movement_total)),
    });
    setResourcesDraft({
      movementRemaining: String(readNumber(selectedCombatant.movement_remaining)),
      hasAction: Boolean(selectedCombatant.has_action),
      hasBonusAction: Boolean(selectedCombatant.has_bonus_action),
      hasReaction: Boolean(selectedCombatant.has_reaction),
    });
    setTurnDraft({
      turnValue: String(readNumber(selectedCombatant.turn_value)),
      initiativePriority: String(readNumber(selectedCombatant.initiative_priority, 1)),
    });
    setConditionDraft({ name: "", durationText: "" });
  }, [selectedCombatant?.id]);

  const selectCombatant = (combatantId: number) => {
    setSelectedCombatantId(combatantId);
    setCombatUrl(effectiveCombatView, combatantId);
  };

  const selectCombatView = (view: CombatView) => {
    setActiveCombatView(view);
    setCombatUrl(view, selectedCombatantId);
  };

  const selectCharacterTarget = (characterSlug: string) => {
    const target = payload?.player_character_targets.find((item) => item.character_slug === characterSlug);
    if (target?.combatant_id) {
      selectCombatant(target.combatant_id);
    }
  };

  const replaceCombatPayload = (response: CombatPayload, message: string) => {
    queryClient.setQueryData(["combat", campaignSlug, activeCombatView, selectedCombatantId], response);
    setStatusMessage(message);
    setErrorMessage(null);
    void combatQuery.refetch();
  };

  const handleCombatMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setStatusMessage(null);
    setErrorMessage(apiErrorMessage(error));
  };

  const updateTurnMutation = useMutation({
    mutationFn: (draft: CombatTurnPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantTurn(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Turn order saved."),
    onError: handleCombatMutationError,
  });

  const updateVitalsMutation = useMutation({
    mutationFn: (draft: CombatVitalsPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantVitals(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Vitals saved."),
    onError: handleCombatMutationError,
  });

  const updateResourcesMutation = useMutation({
    mutationFn: (draft: CombatResourcesPatchPayload) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.patchCombatantResources(campaignSlug, selectedCombatant.id, draft);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Action economy saved."),
    onError: handleCombatMutationError,
  });

  const addConditionMutation = useMutation({
    mutationFn: (draft: CombatConditionDraft) => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.addCombatCondition(campaignSlug, selectedCombatant.id, {
        name: draft.name.trim(),
        duration_text: draft.durationText.trim(),
      });
    },
    onSuccess: (response) => {
      setConditionDraft({ name: "", durationText: "" });
      replaceCombatPayload(response, "Condition added.");
    },
    onError: handleCombatMutationError,
  });

  const deleteConditionMutation = useMutation({
    mutationFn: (condition: CombatCondition) =>
      apiClient.deleteCombatCondition(campaignSlug, condition.id, selectedCombatant?.id ?? null),
    onSuccess: (response) => replaceCombatPayload(response, "Condition removed."),
    onError: handleCombatMutationError,
  });

  const setCurrentMutation = useMutation({
    mutationFn: () => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.setCurrentCombatant(campaignSlug, selectedCombatant.id);
    },
    onSuccess: (response) => replaceCombatPayload(response, "Current turn set."),
    onError: handleCombatMutationError,
  });

  const advanceTurnMutation = useMutation({
    mutationFn: () => apiClient.advanceCombatTurn(campaignSlug, selectedCombatant?.id ?? null),
    onSuccess: (response) => replaceCombatPayload(response, "Turn advanced."),
    onError: handleCombatMutationError,
  });

  const clearCombatMutation = useMutation({
    mutationFn: () => apiClient.clearCombat(campaignSlug),
    onSuccess: (response) => {
      setSelectedCombatantId(null);
      setConfirmClearTracker(false);
      replaceCombatPayload(response, "Combat tracker cleared.");
    },
    onError: handleCombatMutationError,
  });

  const deleteCombatantMutation = useMutation({
    mutationFn: () => {
      if (!selectedCombatant) {
        throw new Error("Choose a combatant first.");
      }
      return apiClient.deleteCombatant(campaignSlug, selectedCombatant.id);
    },
    onSuccess: (response) => {
      setSelectedCombatantId(response.selected_combatant_id ?? null);
      replaceCombatPayload(response, "Combatant removed.");
    },
    onError: handleCombatMutationError,
  });

  const addPlayerMutation = useMutation({
    mutationFn: () =>
      apiClient.addCombatPlayer(
        campaignSlug,
        {
          character_slug: playerSeedDraft.characterSlug,
          turn_value: playerSeedDraft.turnValue,
          initiative_priority: playerSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setPlayerSeedDraft({ characterSlug: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "Player character added.");
    },
    onError: handleCombatMutationError,
  });

  const addNpcMutation = useMutation({
    mutationFn: () => {
      const payload: CombatAddNpcPayload = {
        display_name: npcSeedDraft.displayName.trim(),
        turn_value: npcSeedDraft.turnValue,
        initiative_bonus: npcSeedDraft.initiativeBonus,
        dexterity_modifier: npcSeedDraft.dexterityModifier,
        initiative_priority: npcSeedDraft.initiativePriority,
        current_hp: npcSeedDraft.currentHp,
        max_hp: npcSeedDraft.maxHp,
        temp_hp: npcSeedDraft.tempHp,
        movement_total: npcSeedDraft.movementTotal,
      };
      return apiClient.addCombatNpc(campaignSlug, payload, selectedCombatantId);
    },
    onSuccess: (response) => {
      setNpcSeedDraft({
        displayName: "",
        turnValue: "",
        initiativeBonus: "0",
        dexterityModifier: "",
        initiativePriority: "1",
        currentHp: "",
        maxHp: "",
        tempHp: "0",
        movementTotal: "30",
      });
      replaceCombatPayload(response, "NPC added.");
    },
    onError: handleCombatMutationError,
  });

  const addStatblockMutation = useMutation({
    mutationFn: () =>
      apiClient.addCombatStatblock(
        campaignSlug,
        {
          statblock_id: statblockSeedDraft.statblockId,
          display_name: statblockSeedDraft.displayName.trim(),
          turn_value: statblockSeedDraft.turnValue,
          initiative_priority: statblockSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setStatblockSeedDraft({ statblockId: "", displayName: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "DM Content statblock added.");
    },
    onError: handleCombatMutationError,
  });

  const addSystemsMonsterMutation = useMutation({
    mutationFn: (entryKey: string) =>
      apiClient.addCombatSystemsMonster(
        campaignSlug,
        {
          entry_key: entryKey,
          display_name: systemsSeedDraft.displayName.trim(),
          turn_value: systemsSeedDraft.turnValue,
          initiative_priority: systemsSeedDraft.initiativePriority,
        },
        selectedCombatantId,
      ),
    onSuccess: (response) => {
      setSystemsSeedDraft({ entryKey: "", displayName: "", turnValue: "", initiativePriority: "1" });
      replaceCombatPayload(response, "Systems monster added.");
    },
    onError: handleCombatMutationError,
  });

  const searchSystemsMonsters = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = systemsSearchQuery.trim();
    if (query.length < 2) {
      setSystemsSearchStatus("Type at least 2 letters to search Systems monsters.");
      setSystemsSearchResults([]);
      return;
    }
    setSystemsSearchStatus("Searching Systems monsters ...");
    try {
      const response = await apiClient.searchCombatSystemsMonsters(campaignSlug, query);
      setSystemsSearchResults(response.results);
      setSystemsSearchStatus(response.message);
      setErrorMessage(null);
    } catch (error) {
      handleCombatMutationError(error);
      setSystemsSearchResults([]);
      setSystemsSearchStatus(null);
    }
  };

  const renderCombatantCard = (combatant: CombatantSummary) => {
    const isSelected = selectedCombatant?.id === combatant.id;
    return (
      <button
        type="button"
        className={isSelected ? "combatant-card combatant-card--selected" : "combatant-card"}
        key={combatant.id}
        onClick={() => selectCombatant(combatant.id)}
        aria-pressed={isSelected}
      >
        <span className="combatant-card__topline">
          <strong>{combatant.name}</strong>
          {combatant.is_current_turn ? <span className="pill">Current</span> : null}
        </span>
        <span className="meta">{combatant.subtitle || combatant.type_label}</span>
        <span className="combatant-card__stats">
          <span>Turn {combatant.turn_value}</span>
          {combatant.show_detail ? (
            <span>
              HP {readNumber(combatant.current_hp)} / {readNumber(combatant.max_hp)}
              {readNumber(combatant.temp_hp) ? ` +${readNumber(combatant.temp_hp)} temp` : ""}
            </span>
          ) : (
            <span>Hidden detail</span>
          )}
        </span>
        {combatant.conditions.length ? (
          <span className="combatant-card__conditions">
            {combatant.conditions.map((condition) => condition.name).join(", ")}
          </span>
        ) : null}
      </button>
    );
  };

  const renderCombatViewSwitch = () => {
    if (!canManageCombat) {
      return null;
    }
    return (
      <nav aria-label="DM encounter subview">
        {[
          { id: "status" as CombatView, label: "DM status", activeClass: "button-link", inactiveClass: "ghost-button" },
          { id: "controls" as CombatView, label: "Controls", activeClass: "button-link", inactiveClass: "ghost-button" },
        ].map((view) => (
          <button
            type="button"
            key={view.id}
            className={effectiveCombatView === view.id ? view.activeClass : view.inactiveClass}
            onClick={() => selectCombatView(view.id)}
          >
            {view.label}
          </button>
        ))}
      </nav>
    );
  };

  const renderDmStatus = () => {
    if (!canManageCombat) {
      return (
        <article className="card">
          <p>DM combat status requires combat management access.</p>
        </article>
      );
    }
    if (!selectedCombatant) {
      return (
        <article className="card">
          <h3>No selected combatant</h3>
          <p>Add combatants in DM Controls, then select one from the turn order.</p>
        </article>
      );
    }
    const isPlayerCharacter = Boolean(selectedCombatant.character_slug);
    const vitalsPayload = (): CombatVitalsPatchPayload => {
      const base: CombatVitalsPatchPayload = {
        current_hp: vitalsDraft.currentHp,
        temp_hp: vitalsDraft.tempHp,
      };
      if (isPlayerCharacter) {
        base.expected_revision = selectedCombatant.state_revision;
      } else {
        base.expected_combatant_revision = selectedCombatant.combatant_revision;
        base.max_hp = vitalsDraft.maxHp;
        base.movement_total = vitalsDraft.movementTotal;
      }
      return base;
    };

    return (
      <>
        <section className="combat-dm-grid" aria-label="DM tactical controls">
          <article className="card combat-control-card">
            <div className="section-heading combat-status-snapshot__heading">
              <div>
                <p className="card-kicker">Authority</p>
                <h2>Turn Focus</h2>
              </div>
              <div className="combatant-badges">
                <span className="combat-badge">Round {tracker?.round_number ?? "?"}</span>
                <span className="combat-badge">Turn {selectedCombatant.turn_value}</span>
                {selectedCombatant.is_current_turn ? (
                  <span className="combat-badge combat-badge--active">Current turn</span>
                ) : (
                  <button
                    type="button"
                    className="combat-badge combat-badge--button combat-status-snapshot__set-current"
                    onClick={() => setCurrentMutation.mutate()}
                    disabled={setCurrentMutation.isPending}
                  >
                    {setCurrentMutation.isPending ? "Setting..." : "Set current"}
                  </button>
                )}
              </div>
            </div>
            <form
              className="stack-form combat-status-authority-form"
              onSubmit={(event) => {
                event.preventDefault();
                updateTurnMutation.mutate({
                  expected_combatant_revision: selectedCombatant.combatant_revision,
                  turn_value: turnDraft.turnValue,
                  initiative_priority: turnDraft.initiativePriority,
                });
              }}
            >
              <label className="field">
                <span>Turn value</span>
                <input
                  type="number"
                  value={turnDraft.turnValue}
                  onChange={(event) => setTurnDraft({ ...turnDraft, turnValue: event.currentTarget.value })}
                />
              </label>
              <label className="field">
                <span>Priority</span>
                <input
                  type="number"
                  min="1"
                  value={turnDraft.initiativePriority}
                  onChange={(event) =>
                    setTurnDraft({ ...turnDraft, initiativePriority: event.currentTarget.value })
                  }
                />
              </label>
              <button type="submit" disabled={updateTurnMutation.isPending}>
                {updateTurnMutation.isPending ? "Saving..." : "Save turn"}
              </button>
            </form>
            <div className="hero-actions combat-turn-actions">
              <button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>
                {advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}
              </button>
            </div>
          </article>

          <article className="card combat-control-card">
            <div>
              <p className="meta">Snapshot</p>
              <h3>Vitals</h3>
            </div>
            <div className="combat-summary-grid combat-summary-grid--snapshot">
              <form
                className="combat-stat combat-stat--editable"
                onSubmit={(event) => {
                  event.preventDefault();
                  updateVitalsMutation.mutate(vitalsPayload());
                }}
              >
                <span className="meta">HP</span>
                <div className="combat-inline-value">
                  <input
                    className="combat-stat-input combat-stat-input--number"
                    aria-label="DM Current HP"
                    type="number"
                    value={vitalsDraft.currentHp}
                    onChange={(event) => setVitalsDraft({ ...vitalsDraft, currentHp: event.currentTarget.value })}
                  />
                  <span className="combat-inline-divider">/</span>
                  <strong>{vitalsDraft.maxHp}</strong>
                </div>
              </form>
              <form
                className="combat-stat combat-stat--editable"
                onSubmit={(event) => {
                  event.preventDefault();
                  updateVitalsMutation.mutate(vitalsPayload());
                }}
              >
                <span className="meta">Temp HP</span>
                <input
                  className="combat-stat-input combat-stat-input--single"
                  aria-label="DM Temp HP"
                  type="number"
                  min="0"
                  value={vitalsDraft.tempHp}
                  onChange={(event) => setVitalsDraft({ ...vitalsDraft, tempHp: event.currentTarget.value })}
                />
              </form>
              {!isPlayerCharacter ? (
                <>
                  <label className="field">
                    <span>Max HP</span>
                    <input
                      aria-label="DM Max HP"
                      type="number"
                      min="0"
                      value={vitalsDraft.maxHp}
                      onChange={(event) => setVitalsDraft({ ...vitalsDraft, maxHp: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Movement total</span>
                    <input
                      aria-label="DM Movement total"
                      type="number"
                      min="0"
                      value={vitalsDraft.movementTotal}
                      onChange={(event) =>
                        setVitalsDraft({ ...vitalsDraft, movementTotal: event.currentTarget.value })
                      }
                    />
                  </label>
                </>
              ) : null}
              <button type="button" onClick={() => updateVitalsMutation.mutate(vitalsPayload())} aria-label="Save DM vitals" disabled={updateVitalsMutation.isPending}>
                {updateVitalsMutation.isPending ? "Saving..." : "Save vitals"}
              </button>
            </div>
          </article>

          <article className="card combat-control-card">
            <div>
              <p className="meta">Round tools</p>
              <h3>Action Economy</h3>
            </div>
            <form
              className="combat-resource-strip combat-inline-resource-form"
              onSubmit={(event) => {
                event.preventDefault();
                updateResourcesMutation.mutate({
                  expected_combatant_revision: selectedCombatant.combatant_revision,
                  movement_remaining: resourcesDraft.movementRemaining,
                  has_action: resourcesDraft.hasAction,
                  has_bonus_action: resourcesDraft.hasBonusAction,
                  has_reaction: resourcesDraft.hasReaction,
                });
              }}
            >
              <label className="combat-stat">
                <span className="meta">Movement</span>
                <div className="combat-inline-value">
                  <input
                    className="combat-stat-input combat-stat-input--number"
                    aria-label="DM Movement Remaining"
                    type="number"
                    min="0"
                    value={resourcesDraft.movementRemaining}
                    onChange={(event) =>
                      setResourcesDraft({ ...resourcesDraft, movementRemaining: event.currentTarget.value })
                    }
                  />
                  <span className="combat-inline-divider">/</span>
                  <strong>{vitalsDraft.movementTotal}</strong>
                </div>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasAction}
                  onChange={(event) => setResourcesDraft({ ...resourcesDraft, hasAction: event.currentTarget.checked })}
                />
                <span className="combat-resource">Action</span>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasBonusAction}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, hasBonusAction: event.currentTarget.checked })
                  }
                />
                <span className="combat-resource">Bonus action</span>
              </label>
              <label className="combat-resource-toggle">
                <input
                  type="checkbox"
                  checked={resourcesDraft.hasReaction}
                  onChange={(event) =>
                    setResourcesDraft({ ...resourcesDraft, hasReaction: event.currentTarget.checked })
                  }
                />
                <span className="combat-resource">Reaction</span>
              </label>
              <button type="submit" disabled={updateResourcesMutation.isPending}>
                {updateResourcesMutation.isPending ? "Saving..." : "Save economy"}
              </button>
            </form>
          </article>

          <article className="card combat-control-card">
            <datalist id="gen2-combat-condition-options">
              {conditionOptions.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
            <section className="combat-conditions combat-conditions--compact combat-status-conditions">
              <div className="section-heading">
                <h3>Conditions</h3>
                <details className="combat-condition-editor combat-condition-editor--add">
                  <summary>Add condition</summary>
                  <form
                    className="combat-condition-editor__form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      addConditionMutation.mutate(conditionDraft);
                    }}
                  >
                    <label className="field">
                      <span>Condition</span>
                      <input
                        type="text"
                        list="gen2-combat-condition-options"
                        value={conditionDraft.name}
                        onChange={(event) => setConditionDraft({ ...conditionDraft, name: event.currentTarget.value })}
                      />
                    </label>
                    <label className="field">
                      <span>Duration</span>
                      <input
                        type="text"
                        value={conditionDraft.durationText}
                        onChange={(event) =>
                          setConditionDraft({ ...conditionDraft, durationText: event.currentTarget.value })
                        }
                      />
                    </label>
                    <button type="submit" disabled={addConditionMutation.isPending}>
                      {addConditionMutation.isPending ? "Adding..." : "Add condition"}
                    </button>
                  </form>
                </details>
              </div>
              {selectedCombatant.conditions.length ? (
                <div className="combat-condition-list">
                  {selectedCombatant.conditions.map((condition) => (
                    <div className="combat-condition-item" key={condition.id}>
                      <div>
                        <strong>{condition.name}</strong>
                        {condition.duration_text ? <p className="meta">{condition.duration_text}</p> : null}
                      </div>
                      <div className="combat-condition-actions">
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => deleteConditionMutation.mutate(condition)}
                          disabled={deleteConditionMutation.isPending}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="meta">No conditions are active on this combatant.</p>
              )}
            </section>
          </article>
        </section>

        {selectedCombatant.character_slug ? (
          <section className="combat-pc-workspace">
            <div className="section-heading">
              <div>
                <p className="meta">Selected PC detail</p>
                <h2>{selectedCombatant.name}</h2>
              </div>
            </div>
            <CharacterPane campaignSlug={campaignSlug} initialCharacterSlug={selectedCombatant.character_slug} surface="combat" />
          </section>
        ) : null}

        <section className="card combat-danger-card">
          <div>
            <p className="meta">Cleanup</p>
            <h3>Selected combatant</h3>
          </div>
          <button type="button" className="ghost-button" onClick={() => deleteCombatantMutation.mutate()}>
            {deleteCombatantMutation.isPending ? "Removing..." : "Remove selected combatant"}
          </button>
        </section>
      </>
    );
  };

  const renderDmControls = () => {
    if (!canManageCombat) {
      return (
        <article className="card">
          <p>DM combat controls require combat management access.</p>
        </article>
      );
    }
    return (
      <section className="combat-controls-layout" aria-label="DM combat controls">
        <article className="card combat-control-card">
          <div>
            <p className="meta">Encounter controls</p>
            <h3>Tracker</h3>
          </div>
          <button type="button" onClick={() => advanceTurnMutation.mutate()} disabled={advanceTurnMutation.isPending}>
            {advanceTurnMutation.isPending ? "Advancing..." : "Advance turn"}
          </button>
        </article>

        <section className="card sidebar-card">
          <h2>Add combatant</h2>
          <div className="combat-add-combatant-mode-switcher" role="radiogroup" aria-label="Add combatant type">
            <input
              className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--player"
              id="combat-add-mode-player"
              name="combat-add-mode"
              type="radio"
              value="player"
              checked={combatAddMode === "player"}
              onChange={() => setCombatAddMode("player")}
            />
            {canAccessSystems ? (
              <input
                className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--systems"
                id="combat-add-mode-systems"
                name="combat-add-mode"
                type="radio"
                value="systems"
                checked={combatAddMode === "systems"}
                onChange={() => setCombatAddMode("systems")}
              />
            ) : null}
            {canAccessDmContent ? (
              <input
                className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--dm-content"
                id="combat-add-mode-dm-content"
                name="combat-add-mode"
                type="radio"
                value="dm-content"
                checked={combatAddMode === "dm-content"}
                onChange={() => setCombatAddMode("dm-content")}
              />
            ) : null}
            <input
              className="combat-add-combatant-mode-radio combat-add-combatant-mode-radio--custom"
              id="combat-add-mode-custom"
              name="combat-add-mode"
              type="radio"
              value="custom"
              checked={combatAddMode === "custom"}
              onChange={() => setCombatAddMode("custom")}
            />
            <div className="combat-add-combatant-mode-toggle">
              <label className="ghost-button" htmlFor="combat-add-mode-player">
                Add player character
              </label>
              {canAccessSystems ? (
                <label className="ghost-button" htmlFor="combat-add-mode-systems">
                  Add NPC from Systems
                </label>
              ) : null}
              {canAccessDmContent ? (
                <label className="ghost-button" htmlFor="combat-add-mode-dm-content">
                  Add NPC from DM Content
                </label>
              ) : null}
              <label className="ghost-button" htmlFor="combat-add-mode-custom">
                Add custom combatant
              </label>
            </div>

            <div
              className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--player ${
                combatAddMode === "player" ? "combat-add-combatant-mode-panel--active" : ""
              }`}
            >
              {availableCharacters.length ? (
                <form
                  className="stack-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    addPlayerMutation.mutate();
                  }}
                >
                  <label className="field">
                    <span>Character</span>
                    <select
                      value={playerSeedDraft.characterSlug}
                      onChange={(event) => setPlayerSeedDraft({ ...playerSeedDraft, characterSlug: event.currentTarget.value })}
                    >
                      <option value="">Choose character</option>
                      {availableCharacters.map((choice) => (
                        <option key={choice.slug} value={choice.slug}>
                          {choice.name} {choice.subtitle ? `- ${choice.subtitle}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Turn value</span>
                    <input
                      type="number"
                      value={playerSeedDraft.turnValue}
                      onChange={(event) => setPlayerSeedDraft({ ...playerSeedDraft, turnValue: event.currentTarget.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Priority</span>
                    <input
                      type="number"
                      min="1"
                      value={playerSeedDraft.initiativePriority}
                      onChange={(event) =>
                        setPlayerSeedDraft({ ...playerSeedDraft, initiativePriority: event.currentTarget.value })
                      }
                    />
                  </label>
                  <button type="submit" disabled={addPlayerMutation.isPending}>
                    {addPlayerMutation.isPending ? "Adding..." : "Add player character"}
                  </button>
                </form>
              ) : (
                <p className="meta">All visible player characters are already in the tracker.</p>
              )}
            </div>

            {canAccessSystems ? (
              <div
                className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--systems ${
                  combatAddMode === "systems" ? "combat-add-combatant-mode-panel--active" : ""
                }`}
              >
                <form className="stack-form" onSubmit={searchSystemsMonsters}>
                  <label className="field">
                    <span>Search monsters</span>
                    <input
                      type="search"
                      value={systemsSearchQuery}
                      onChange={(event) => setSystemsSearchQuery(event.currentTarget.value)}
                    />
                  </label>
                  <button type="submit">Search</button>
                </form>
                {systemsSearchStatus ? <p className="status status-neutral">{systemsSearchStatus}</p> : null}
                <div className="combat-systems-results">
                  {systemsSearchResults.map((result) => (
                    <article className="compact-card" key={result.entry_key}>
                      <div>
                        <strong>{result.title}</strong>
                        <p className="meta">
                          {result.source_id} - {result.subtitle} - Init {result.initiative_bonus}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => addSystemsMonsterMutation.mutate(result.entry_key)}
                        disabled={addSystemsMonsterMutation.isPending}
                      >
                        Add
                      </button>
                    </article>
                  ))}
                </div>
                <div className="stack-form">
                  <label className="field">
                    <span>Display name</span>
                    <input
                      type="text"
                      value={systemsSeedDraft.displayName}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, displayName: event.currentTarget.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Turn value</span>
                    <input
                      type="number"
                      value={systemsSeedDraft.turnValue}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, turnValue: event.currentTarget.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Priority</span>
                    <input
                      type="number"
                      min="1"
                      value={systemsSeedDraft.initiativePriority}
                      onChange={(event) =>
                        setSystemsSeedDraft({ ...systemsSeedDraft, initiativePriority: event.currentTarget.value })
                      }
                    />
                  </label>
                </div>
              </div>
            ) : null}

            {canAccessDmContent ? (
              <div
                className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--dm-content ${
                  combatAddMode === "dm-content" ? "combat-add-combatant-mode-panel--active" : ""
                }`}
              >
                {availableStatblocks.length ? (
                  <form
                    className="stack-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      addStatblockMutation.mutate();
                    }}
                  >
                    <label className="field">
                      <span>Statblock</span>
                      <select
                        value={statblockSeedDraft.statblockId}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, statblockId: event.currentTarget.value })
                        }
                      >
                        <option value="">Choose statblock</option>
                        {availableStatblocks.map((choice) => (
                          <option key={choice.id} value={choice.id}>
                            {choice.title} - {choice.subtitle}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Display name override</span>
                      <input
                        type="text"
                        value={statblockSeedDraft.displayName}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, displayName: event.currentTarget.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Turn override</span>
                      <input
                        type="number"
                        value={statblockSeedDraft.turnValue}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, turnValue: event.currentTarget.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Priority</span>
                      <input
                        type="number"
                        min="1"
                        value={statblockSeedDraft.initiativePriority}
                        onChange={(event) =>
                          setStatblockSeedDraft({ ...statblockSeedDraft, initiativePriority: event.currentTarget.value })
                        }
                      />
                    </label>
                    <button type="submit" disabled={addStatblockMutation.isPending}>
                      {addStatblockMutation.isPending ? "Adding..." : "Add statblock"}
                    </button>
                  </form>
                ) : (
                  <p className="meta">Upload statblocks on the DM Content page to use them here.</p>
                )}
              </div>
            ) : null}

            <div
              className={`combat-add-combatant-mode-panel combat-add-combatant-mode-panel--custom ${
                combatAddMode === "custom" ? "combat-add-combatant-mode-panel--active" : ""
              }`}
            >
              <form
                className="stack-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  addNpcMutation.mutate();
                }}
              >
                <label className="field">
                  <span>Name</span>
                  <input
                    type="text"
                    value={npcSeedDraft.displayName}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, displayName: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Turn value</span>
                  <input
                    type="number"
                    value={npcSeedDraft.turnValue}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, turnValue: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Initiative bonus</span>
                  <input
                    type="number"
                    value={npcSeedDraft.initiativeBonus}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, initiativeBonus: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Dex mod</span>
                  <input
                    type="number"
                    value={npcSeedDraft.dexterityModifier}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, dexterityModifier: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Current HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.currentHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, currentHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Max HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.maxHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, maxHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Temp HP</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.tempHp}
                    onChange={(event) => setNpcSeedDraft({ ...npcSeedDraft, tempHp: event.currentTarget.value })}
                  />
                </label>
                <label className="field">
                  <span>Movement</span>
                  <input
                    type="number"
                    min="0"
                    value={npcSeedDraft.movementTotal}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, movementTotal: event.currentTarget.value })
                    }
                  />
                </label>
                <label className="field">
                  <span>Priority</span>
                  <input
                    type="number"
                    min="1"
                    value={npcSeedDraft.initiativePriority}
                    onChange={(event) =>
                      setNpcSeedDraft({ ...npcSeedDraft, initiativePriority: event.currentTarget.value })
                    }
                  />
                </label>
                <button type="submit" disabled={addNpcMutation.isPending}>
                  {addNpcMutation.isPending ? "Adding..." : "Add NPC combatant"}
                </button>
              </form>
            </div>
          </div>
        </section>

        <section className="card sidebar-card">
          <h2>Encounter cleanup</h2>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={confirmClearTracker}
              onChange={(event) => setConfirmClearTracker(event.currentTarget.checked)}
            />
            Confirm clear tracker
          </label>
          <button
            type="button"
            className="ghost-button"
            onClick={() => clearCombatMutation.mutate()}
            disabled={!confirmClearTracker || clearCombatMutation.isPending}
          >
            {clearCombatMutation.isPending ? "Clearing..." : "Clear tracker"}
          </button>
        </section>
      </section>
    );
  };

  const renderPlayerWorkspace = () => (
    <section className="combat-pc-workspace">
      <div className="section-heading">
        <div>
          <p className="meta">Selected PC workspace</p>
          <h2>{selectedPlayerCharacter?.name ?? "No tracked PC in combat"}</h2>
        </div>
        {payload?.player_character_targets.length ? (
          <div className="combat-target-list">
            {payload.player_character_targets.map((target) => (
              <React.Fragment key={target.combatant_id}>
                <button
                  type="button"
                  className={target.is_selected ? "button-link" : "ghost-button"}
                  onClick={() => selectCombatant(target.combatant_id)}
                >
                  {target.name}
                </button>
                {target.subtitle ? <p className="meta">{target.subtitle}</p> : null}
              </React.Fragment>
            ))}
          </div>
        ) : null}
      </div>
      {selectedCharacterSlug ? (
        <CharacterPane
          campaignSlug={campaignSlug}
          initialCharacterSlug={selectedCharacterSlug}
          surface="combat"
          onSelectedCharacterChange={selectCharacterTarget}
        />
      ) : (
        <section className="card auth-card">
          <h2>No tracked player character available</h2>
          <p>
            There is not currently a tracked player character you can open from combat.
            Once a DM adds your character to the tracker, it will appear here.
          </p>
        </section>
      )}
    </section>
  );

  return (
    <>
      <section className="hero compact combat-hero">
        <p className="eyebrow">
          {effectiveCombatView === "status"
            ? "DM status"
            : effectiveCombatView === "controls"
              ? "Encounter controls"
              : "Combat tracker"}
        </p>
        <h1>
          {effectiveCombatView === "status"
            ? "DM status"
            : effectiveCombatView === "controls"
              ? "Encounter controls"
              : "Combat"}
        </h1>
        <p className="lede">
          {effectiveCombatView === "status" || effectiveCombatView === "controls"
            ? "Encounter setup, seeding, cleanup, and authority changes."
            : selectedPlayerCharacter
              ? "Keep your tracked character open as your in-combat workspace."
              : "Live encounter tracker."}
        </p>
        {canManageCombat && effectiveCombatView !== "player" ? renderCombatViewSwitch() : null}
      </section>

      <ApiErrorNotice
        isLoading={combatQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />
      {statusMessage ? <p className="status status-success">{statusMessage}</p> : null}
      {errorMessage ? <p className="status status-error">{errorMessage}</p> : null}

      {payload && !payload.combat_system_supported ? (
        <section className="card auth-card">
          <h2>Combat tracker not configured for {payload.campaign.system || "this system"} yet</h2>
          <p>
            This route is a placeholder for the campaign system lane. The current combat tracker is
            DND-5E-only, so no encounter automation is available here for {payload.campaign.system || "this system"} yet.
          </p>
          <div className="hero-actions">
            <a className="button-link" href={payload.links?.flask_campaign_url || `/campaigns/${encodeURIComponent(campaignSlug)}`}>
              Open Campaign Home
            </a>
            {payload.links?.flask_characters_url ? (
              <a className="ghost-button" href={payload.links.flask_characters_url}>
                Open Characters
              </a>
            ) : null}
            {payload.links?.flask_session_url ? (
              <a className="ghost-button" href={payload.links.flask_session_url}>
                Open Session
              </a>
            ) : null}
          </div>
        </section>
      ) : null}

      {payload?.combat_system_supported ? (
        <>
          <section className="combat-summary-band" aria-label="Encounter summary">
            <article>
              <span className="meta">Round</span>
              <strong>{tracker?.round_number ?? 1}</strong>
            </article>
            <article>
              <span className="meta">Current turn</span>
              <strong>{tracker?.current_turn_label || "None"}</strong>
            </article>
            <article>
              <span className="meta">Combatants</span>
              <strong>{tracker?.combatant_count ?? 0}</strong>
            </article>
          </section>

          {tracker?.combatants.length ? (
            <section className="combat-carousel" aria-label="Combatant carousel">
              <div className="section-heading">
                <div>
                  <h2>Turn Order</h2>
                  <p className="meta">Initiative is pinned here while the main panel shows your tracked character.</p>
                </div>
              </div>
              <div className="combat-carousel-track">
                {tracker.combatants.map((combatant) => renderCombatantCard(combatant))}
              </div>
              <div className="combat-turn-order-jump">
                <label className="combat-turn-order-jump__label" htmlFor="combat-turn-order-jump-select">
                  Jump to combatant
                </label>
                <select
                  id="combat-turn-order-jump-select"
                  className="combat-turn-order-jump__select"
                  value={selectedCombatant?.id ?? ""}
                  onChange={(event) => selectCombatant(Number(event.currentTarget.value))}
                >
                  {tracker.combatants.map((combatant) => (
                    <option key={combatant.id} value={combatant.id}>
                      {combatant.name} - turn {combatant.turn_value}
                    </option>
                  ))}
                </select>
              </div>
            </section>
          ) : (
            <section className="card">
              <h3>No combatants</h3>
              <p>The tracker is empty. Use the Encounter controls or DM controls to seed the encounter for now.</p>
            </section>
          )}

          {selectedCombatant ? (
            <section className="combat-selected-snapshot card combat-character-snapshot">
              <div className="section-heading">
                <div>
                  <p className="card-kicker">{selectedCombatantKicker}</p>
                  <h2>{selectedCombatant.name}</h2>
                  {selectedCombatantMeta ? (
                    <p className="meta">{selectedCombatantMeta}</p>
                  ) : null}
                </div>
                <div className="combatant-badges">
                  <span className="combat-badge">Round {tracker?.round_number ?? 1}</span>
                  <span className="combat-badge">Turn {selectedCombatant.turn_value}</span>
                  {selectedCombatant.initiative_bonus_label !== "0" ? (
                    <span className="combat-badge combat-badge--muted">Init {selectedCombatant.initiative_bonus_label}</span>
                  ) : null}
                  {selectedCombatant.is_current_turn ? (
                    <span className="combat-badge combat-badge--active">Current turn</span>
                  ) : null}
                </div>
              </div>
              {selectedCombatant.show_detail ? (
                <div className="combat-selected-snapshot__stats">
                  <span>HP {readNumber(selectedCombatant.current_hp)} / {readNumber(selectedCombatant.max_hp)}</span>
                  <span>Move {readNumber(selectedCombatant.movement_remaining)} / {readNumber(selectedCombatant.movement_total)}</span>
                  <span>{selectedCombatant.has_action ? "Action" : "No action"}</span>
                  <span>{selectedCombatant.has_bonus_action ? "Bonus" : "No bonus"}</span>
                  <span>{selectedCombatant.has_reaction ? "Reaction" : "No reaction"}</span>
                </div>
              ) : (
                <p className="meta">Detailed stats are currently hidden from players.</p>
              )}
            </section>
          ) : null}

          {effectiveCombatView === "status" ? renderDmStatus() : null}
          {effectiveCombatView === "controls" ? renderDmControls() : null}
          {effectiveCombatView === "player" ? renderPlayerWorkspace() : null}
        </>
      ) : null}
    </>
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
    queryFn: async () => {
      const previous = queryClient.getQueryData<SessionPayload>(["session", resolvedCampaignSlug]);
      const response = await apiClient.getSessionLiveState(
        resolvedCampaignSlug,
        previous
          ? {
              sessionRevision: previous.session_revision,
              sessionViewToken: previous.session_view_token,
            }
          : undefined,
      );
      const resolution = resolveSessionLivePayload(previous, response);
      if (resolution.state === "needs-refresh") {
        return apiClient.getSession(resolvedCampaignSlug);
      }
      return resolution.payload;
    },
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
  const sessionIsActive = Boolean(payload?.active_session?.is_active);
  const sessionStatusLabel = sessionIsActive ? "Session active" : "Session inactive";

  useEffect(() => {
    setActivePane((previousActivePane) => coerceSessionPane(previousActivePane, canManage));
  }, [canManage]);

  const paneError = getApiErrorMessage(sessionQuery.error);

  return (
    <section className="session-page-shell">
      <section className="hero compact session-hero">
        <p className="eyebrow">Session Workspace</p>
        <div className="session-hero__title-row">
          <h1>Session</h1>
          <span
            className={
              sessionIsActive
                ? "session-hero__status session-hero__status--active"
                : "session-hero__status session-hero__status--inactive"
            }
            data-session-header-status
          >
            <span className="session-hero__status-dot" aria-hidden="true" />
            {sessionStatusLabel}
          </span>
        </div>
        <p className="lede">Live play workspace.</p>
        <div className="hero-actions session-tab-strip">
          <button
            type="button"
            className={activePane === "session" ? "tab-button button-link" : "tab-button ghost-button"}
            onClick={() => setActivePane("session")}
          >
            Session
          </button>
          <button
            type="button"
            className={activePane === "character" ? "tab-button button-link" : "tab-button ghost-button"}
            onClick={() => setActivePane("character")}
          >
            Character
          </button>
          {canManage ? (
            <button
              type="button"
              className={activePane === "dm" ? "tab-button button-link" : "tab-button ghost-button"}
              onClick={() => setActivePane("dm")}
            >
              DM
            </button>
          ) : null}
        </div>
      </section>

      <ApiErrorNotice
        isLoading={sessionQuery.isLoading}
        message={paneError}
        onAuth={() => setAuthRequired(true)}
      />

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

const accountSettingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/account",
  component: AccountSettingsPage,
});

const adminDashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  component: AdminDashboardPage,
});

const adminUserDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/users/$userId",
  component: AdminUserDetailPage,
});

const campaignHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug",
  component: WikiHomePage,
});

const campaignHelpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/help",
  component: CampaignHelpPage,
});

const campaignControlRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/control",
  component: CampaignControlPage,
});

const campaignWikiSectionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/sections/$sectionSlug",
  component: WikiSectionPage,
});

const campaignWikiPageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/pages/$",
  component: WikiArticlePage,
});

const campaignSystemsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems",
  component: SystemsIndexPage,
});

const campaignSystemsSourceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/sources/$sourceId",
  component: SystemsSourcePage,
});

const campaignSystemsSourceCategoryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/sources/$sourceId/types/$entryType",
  component: SystemsSourceCategoryPage,
});

const campaignSystemsEntryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/systems/entries/$entrySlug",
  component: SystemsEntryPage,
});

const campaignCharacterRosterRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters",
  component: CharacterRosterPage,
});

const campaignCharacterCreateRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/new",
  component: CharacterCreatePage,
});

const campaignCharacterXianxiaManualImportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/import/xianxia-manual",
  component: CharacterXianxiaManualImportPage,
});

const campaignCharacterAdvancedEditorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/edit",
  component: CharacterAdvancedEditorPage,
});

const campaignCharacterRetrainingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/retraining",
  component: CharacterRetrainingPage,
});

const campaignCharacterLevelUpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/level-up",
  component: CharacterLevelUpPage,
});

const campaignCharacterProgressionRepairRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/progression-repair",
  component: CharacterProgressionRepairPage,
});

const campaignCharacterCultivationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug/cultivation",
  component: CharacterCultivationPage,
});

const campaignCharacterDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/characters/$characterSlug",
  component: CharacterDetailPage,
});

const campaignCombatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/combat",
  component: CombatPage,
});

const campaignSessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/session",
  component: SessionPage,
});

const campaignDmContentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/campaigns/$campaignSlug/dm-content",
  component: DmContentPage,
});

const routeTree = rootRoute.addChildren([
  campaignsRoute,
  accountSettingsRoute,
  adminDashboardRoute,
  adminUserDetailRoute,
  campaignHomeRoute,
  campaignHelpRoute,
  campaignControlRoute,
  campaignWikiSectionRoute,
  campaignWikiPageRoute,
  campaignSystemsRoute,
  campaignSystemsSourceRoute,
  campaignSystemsSourceCategoryRoute,
  campaignSystemsEntryRoute,
  campaignCharacterRosterRoute,
  campaignCharacterCreateRoute,
  campaignCharacterXianxiaManualImportRoute,
  campaignCharacterAdvancedEditorRoute,
  campaignCharacterRetrainingRoute,
  campaignCharacterLevelUpRoute,
  campaignCharacterProgressionRepairRoute,
  campaignCharacterCultivationRoute,
  campaignCharacterDetailRoute,
  campaignCombatRoute,
  campaignSessionRoute,
  campaignDmContentRoute,
]);
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
