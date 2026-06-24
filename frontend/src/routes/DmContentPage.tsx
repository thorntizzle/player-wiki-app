import { useEffect, useMemo, useState } from "react";
import { useLocation, useParams } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { ChangeEvent, FormEvent } from "react";
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
import { DmArticleCreator } from "../components/DmArticleCreator";
import { DmContentConditionCard, DmContentStatblockCard } from "../components/DmContentCards";
import { DmPlayerWikiDraftFields } from "../components/DmPlayerWikiDraftFields";
import {
  renderArticleBody,
  resolveArticleImage,
  SessionArticleReferenceActions,
  SessionArticleSourceLine,
} from "../components/SessionArticleDisplay";
import {
  buildEmptyManualArticleDraft,
  readBinaryAsBase64,
  readTextFile,
  type ArticleMode,
  type EmbeddedImageInput,
  type ManualArticleDraftState,
} from "../sessionArticleDrafts";
import {
  buildInitialConditionDraft,
  buildInitialPlayerWikiDraft,
  buildInitialStatblockDraft,
  buildPageRefFromDraft,
  buildPlayerWikiAssetRef,
  buildPlayerWikiDraftFromRecord,
  buildPlayerWikiMetadata,
  playerWikiRemovalSafety,
  playerWikiStatusLabel,
  simpleSlug,
  type DmContentConditionDraftState,
  type DmContentLane,
  type DmContentStatblockDraftState,
  type DmPlayerWikiDraftState,
  type StagedArticleDraftState,
} from "../dmContentUtils";
import { formatTimestamp } from "../timeFormatting";
export function DmContentPage() {
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

  const renderStatblockCard = (statblock: DmContentStatblock) => {
    const draft = statblockDrafts[statblock.id] ?? buildInitialStatblockDraft(statblock);
    return (
      <DmContentStatblockCard
        key={statblock.id}
        statblock={statblock}
        draft={draft}
        canManageDmContent={canManageDmContent}
        isUpdating={updateStatblockMutation.isPending}
        isDeleting={deleteStatblockMutation.isPending}
        onDraftChange={updateStatblockDraft}
        onUpdate={(id, payload) => updateStatblockMutation.mutate({ id, payload })}
        onDelete={(id) => deleteStatblockMutation.mutate(id)}
      />
    );
  };

  const renderConditionCard = (condition: DmContentConditionDefinition) => {
    const draft = conditionDrafts[condition.id] ?? buildInitialConditionDraft(condition);
    return (
      <DmContentConditionCard
        key={condition.id}
        condition={condition}
        draft={draft}
        canManageDmContent={canManageDmContent}
        isUpdating={updateConditionMutation.isPending}
        isDeleting={deleteConditionMutation.isPending}
        onDraftChange={updateConditionDraft}
        onUpdate={(id, payload) => updateConditionMutation.mutate({ id, payload })}
        onDelete={(id) => deleteConditionMutation.mutate(id)}
      />
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
            <DmPlayerWikiDraftFields
              idPrefix={`dm-player-wiki-edit-${simpleSlug(pageFile.page_ref)}`}
              draft={editDraft}
              setDraft={(next) => {
                setPlayerWikiEditDrafts((current) => ({
                  ...current,
                  [pageFile.page_ref]: next,
                }));
              }}
              includeSlug={false}
              disabled={!canManagePlayerWiki}
              onImageReadStatus={(errorMessage) => {
                setPaneError(errorMessage);
                if (errorMessage) {
                  setUiMessage(null);
                }
              }}
            />
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
              <DmPlayerWikiDraftFields
                idPrefix="dm-player-wiki-create"
                draft={playerWikiCreateDraft}
                setDraft={setPlayerWikiCreateDraft}
                includeSlug={true}
                disabled={!canManagePlayerWiki}
                onImageReadStatus={(errorMessage) => {
                  setPaneError(errorMessage);
                  if (errorMessage) {
                    setUiMessage(null);
                  }
                }}
              />
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

