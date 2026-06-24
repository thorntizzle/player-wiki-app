import { useEffect, useMemo, useState } from "react";
import { useLocation, useParams } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { FormEvent, ReactElement } from "react";
import { apiErrorMessage } from "../api/client";
import type {
  ContentPageFileSummary,
  ContentPageUpsertPayload,
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
} from "../api/types";
import {
  isAuthRequiredFromError as isAuthError,
  resolveSessionLivePayload,
} from "../sessionRouteState";
import { useApiClient } from "../apiClientContext";
import { getApiErrorMessage } from "../apiErrors";
import { ApiErrorNotice } from "../components/feedback";
import { DmContentSystemsLane } from "./DmContentSystemsLane";
import { DmConditionsLane } from "../components/DmConditionsLane";
import { DmContentHero } from "../components/DmContentHero";
import { DmPlayerWikiLane } from "../components/DmPlayerWikiLane";
import { DmStagedArticlesLane } from "../components/DmStagedArticlesLane";
import { DmStatblocksLane } from "../components/DmStatblocksLane";
import {
  buildEmptyManualArticleDraft,
  type ArticleMode,
  type EmbeddedImageInput,
  type ManualArticleDraftState,
} from "../sessionArticleDrafts";
import {
  buildInitialConditionDraft,
  buildInitialPlayerWikiDraft,
  buildInitialStatblockDraft,
  buildInitialStagedArticleDraft,
  buildPageRefFromDraft,
  buildPlayerWikiAssetRef,
  buildPlayerWikiDraftFromRecord,
  buildPlayerWikiMetadata,
  type DmContentConditionDraftState,
  type DmContentLane,
  type DmContentStatblockDraftState,
  type DmPlayerWikiDraftState,
  type StagedArticleDraftState,
} from "../dmContentUtils";
export function DmContentPage(): ReactElement {
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
        next[article.id] = existing ?? buildInitialStagedArticleDraft(article);
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

  const updateStagedDraft = (
    article: SessionArticle,
    fallbackDraft: StagedArticleDraftState,
    updates: Partial<StagedArticleDraftState>,
  ) => {
    setStagedDrafts((current) => ({
      ...current,
      [article.id]: {
        ...(current[article.id] ?? fallbackDraft),
        ...updates,
      },
    }));
  };

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

  const updateStatblockDraft = (statblock: DmContentStatblock, updates: Partial<DmContentStatblockDraftState>) => {
    setStatblockDrafts((current) => ({
      ...current,
      [statblock.id]: {
        ...(current[statblock.id] ?? buildInitialStatblockDraft(statblock)),
        ...updates,
      },
    }));
  };

  const updateConditionDraft = (
    condition: DmContentConditionDefinition,
    updates: Partial<DmContentConditionDraftState>,
  ) => {
    setConditionDrafts((current) => ({
      ...current,
      [condition.id]: {
        ...(current[condition.id] ?? buildInitialConditionDraft(condition)),
        ...updates,
      },
    }));
  };

  const submitPlayerWikiEditDraft = (pageRef: string, draft: DmPlayerWikiDraftState) => {
    if (!draft.title.trim()) {
      setPaneError("Player Wiki page title is required.");
      setUiMessage(null);
      return;
    }
    savePlayerWikiPageMutation.mutate({
      mode: "edit",
      pageRef,
      draft,
    });
  };

  const submitPlayerWikiCreateDraft = (draft: DmPlayerWikiDraftState) => {
    if (!draft.title.trim()) {
      setPaneError("Player Wiki page title is required.");
      setUiMessage(null);
      return;
    }
    savePlayerWikiPageMutation.mutate({
      mode: "create",
      pageRef: buildPageRefFromDraft(draft),
      draft,
    });
  };

  return (
    <>
      <DmContentHero
        activeLane={activeLane}
        encodedCampaignSlug={encodedCampaignSlug}
        laneCounts={dmContentLaneCounts}
        lede={dmContentLede}
      />

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
        <DmStatblocksLane
          canManageDmContent={canManageDmContent}
          filteredStatblocks={filteredStatblocks}
          isCreating={createStatblockMutation.isPending}
          isDeleting={deleteStatblockMutation.isPending}
          isLoading={dmContentQuery.isLoading}
          isUpdating={updateStatblockMutation.isPending}
          onCreate={(payload) => createStatblockMutation.mutate(payload)}
          onDelete={(id) => deleteStatblockMutation.mutate(id)}
          onDraftChange={updateStatblockDraft}
          onFileReadStatus={(errorMessage) => {
            setPaneError(errorMessage);
            setUiMessage(null);
          }}
          onUpdate={(id, payload) => updateStatblockMutation.mutate({ id, payload })}
          setStatblockCreateDraft={setStatblockCreateDraft}
          setStatblockQuery={setStatblockQuery}
          statblockCreateDraft={statblockCreateDraft}
          statblockDrafts={statblockDrafts}
          statblockQuery={statblockQuery}
          statblockSubsectionGroups={statblockSubsectionGroups}
          topLevelStatblocks={topLevelStatblocks}
        />
      ) : activeLane === "conditions" ? (
        <DmConditionsLane
          canManageDmContent={canManageDmContent}
          conditionCreateDraft={conditionCreateDraft}
          conditionDrafts={conditionDrafts}
          conditionQuery={conditionQuery}
          filteredConditions={filteredConditions}
          isCreating={createConditionMutation.isPending}
          isDeleting={deleteConditionMutation.isPending}
          isLoading={dmContentQuery.isLoading}
          isUpdating={updateConditionMutation.isPending}
          onCreate={(payload) => createConditionMutation.mutate(payload)}
          onDelete={(id) => deleteConditionMutation.mutate(id)}
          onDraftChange={updateConditionDraft}
          onUpdate={(id, payload) => updateConditionMutation.mutate({ id, payload })}
          onValidationError={(message) => {
            setPaneError(message);
            setUiMessage(null);
          }}
          setConditionCreateDraft={setConditionCreateDraft}
          setConditionQuery={setConditionQuery}
        />
      ) : activeLane === "player-wiki" ? (
        <DmPlayerWikiLane
          canManagePlayerWiki={canManagePlayerWiki}
          deleteConfirm={playerWikiDeleteConfirm}
          editDrafts={playerWikiEditDrafts}
          encodedCampaignSlug={encodedCampaignSlug}
          filteredPlayerWikiPages={filteredPlayerWikiPages}
          isArchiving={archivePlayerWikiPageMutation.isPending}
          isDeleting={deletePlayerWikiPageMutation.isPending}
          isLoading={contentPagesQuery.isLoading}
          isSaving={savePlayerWikiPageMutation.isPending}
          onArchive={(pageRef) => archivePlayerWikiPageMutation.mutate(pageRef)}
          onCreateDraft={submitPlayerWikiCreateDraft}
          onDelete={(pageRef) => deletePlayerWikiPageMutation.mutate(pageRef)}
          onDeleteConfirmChange={(pageRef, checked) => {
            setPlayerWikiDeleteConfirm((current) => ({
              ...current,
              [pageRef]: checked,
            }));
          }}
          onDraftChange={(pageRef, next) => {
            setPlayerWikiEditDrafts((current) => ({
              ...current,
              [pageRef]: next,
            }));
          }}
          onImageReadStatus={(errorMessage) => {
            setPaneError(errorMessage);
            if (errorMessage) {
              setUiMessage(null);
            }
          }}
          onLoadEditDraft={loadPlayerWikiEditDraft}
          onSaveEditDraft={submitPlayerWikiEditDraft}
          playerWikiCreateDraft={playerWikiCreateDraft}
          playerWikiPages={playerWikiPages}
          playerWikiQuery={playerWikiQuery}
          setPlayerWikiCreateDraft={setPlayerWikiCreateDraft}
          setPlayerWikiQuery={setPlayerWikiQuery}
        />
      ) : activeLane === "systems" ? (
        <DmContentSystemsLane campaignSlug={resolvedCampaignSlug} />
      ) : (
        <DmStagedArticlesLane
          campaignSlug={resolvedCampaignSlug}
          canManageSession={canManageSession}
          isCreating={createArticleMutation.isPending}
          isDeleting={deleteArticleMutation.isPending}
          isUpdating={updateArticleMutation.isPending}
          manualDraft={manualDraft}
          mode={mode}
          onCreate={(payload) => {
            clearArticleStatus();
            createArticleMutation.mutate(payload);
          }}
          onDeleteArticle={(articleId) => deleteArticleMutation.mutate(articleId)}
          onDraftChange={updateStagedDraft}
          onSearchSources={searchSources}
          onUpdateArticle={(args) => updateArticleMutation.mutate(args)}
          selectedSourceRef={selectedSourceRef}
          setManualDraft={(next) => {
            clearArticleStatus();
            setManualDraft(next);
          }}
          setMode={(next) => {
            clearArticleStatus();
            setMode(next);
          }}
          setSelectedSourceRef={(next) => {
            setSelectedSourceRef(next);
            setSourceStatus(null);
          }}
          setSourceQuery={setSourceQuery}
          setSourceStatus={setSourceStatus}
          setUploadDraft={(next) => {
            clearArticleStatus();
            setUploadDraft(next);
          }}
          sourceQuery={sourceQuery}
          sourceResults={sourceResults}
          sourceStatus={sourceStatus}
          stagedArticles={stagedArticles}
          stagedDrafts={stagedDrafts}
          uploadDraft={uploadDraft}
        />
      )}
    </>
  );
}

