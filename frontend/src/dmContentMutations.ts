import type { Dispatch, SetStateAction } from "react";
import { useMutation } from "@tanstack/react-query";

import { apiErrorMessage, type CampaignApiClient } from "./api/client";
import type {
  ContentPageUpsertPayload,
  DmContentConditionCreatePayload,
  DmContentConditionUpdatePayload,
  DmContentStatblockCreatePayload,
  DmContentStatblockUpdatePayload,
  SessionArticleCreatePayload,
  SessionArticleUpdatePayload,
} from "./api/types";
import { isAuthRequiredFromError as isAuthError } from "./sessionRouteState";
import {
  buildEmptyManualArticleDraft,
  type EmbeddedImageInput,
  type ManualArticleDraftState,
} from "./sessionArticleDrafts";
import {
  buildInitialPlayerWikiDraft,
  buildPlayerWikiAssetRef,
  buildPlayerWikiDraftFromRecord,
  buildPlayerWikiMetadata,
  type DmContentConditionDraftState,
  type DmContentStatblockDraftState,
  type DmPlayerWikiDraftState,
  type StagedArticleDraftState,
} from "./dmContentUtils";

type StatusReporter = (message: string | null) => void;

export interface DmContentUploadDraftState {
  filename: string;
  markdown: string;
  image: EmbeddedImageInput | null;
}

interface UseDmContentMutationsOptions {
  apiClient: CampaignApiClient;
  campaignSlug: string;
  setAuthRequired: (required: boolean) => void;
  showToastMessage: StatusReporter;
  setUiMessage: Dispatch<SetStateAction<string | null>>;
  setPaneError: Dispatch<SetStateAction<string | null>>;
  setStatblockCreateDraft: Dispatch<SetStateAction<DmContentStatblockDraftState>>;
  setConditionCreateDraft: Dispatch<SetStateAction<DmContentConditionDraftState>>;
  setPlayerWikiCreateDraft: Dispatch<SetStateAction<DmPlayerWikiDraftState>>;
  setPlayerWikiEditDrafts: Dispatch<SetStateAction<Record<string, DmPlayerWikiDraftState>>>;
  setPlayerWikiDeleteConfirm: Dispatch<SetStateAction<Record<string, boolean>>>;
  setManualDraft: Dispatch<SetStateAction<ManualArticleDraftState>>;
  setUploadDraft: Dispatch<SetStateAction<DmContentUploadDraftState>>;
  setSelectedSourceRef: Dispatch<SetStateAction<string>>;
  setStagedDrafts: Dispatch<SetStateAction<Record<number, StagedArticleDraftState>>>;
  refetchDmContent: () => void;
  refetchContentPages: () => void;
  refetchSession: () => void;
}

export function useDmContentMutations({
  apiClient,
  campaignSlug,
  setAuthRequired,
  showToastMessage,
  setUiMessage,
  setPaneError,
  setStatblockCreateDraft,
  setConditionCreateDraft,
  setPlayerWikiCreateDraft,
  setPlayerWikiEditDrafts,
  setPlayerWikiDeleteConfirm,
  setManualDraft,
  setUploadDraft,
  setSelectedSourceRef,
  setStagedDrafts,
  refetchDmContent,
  refetchContentPages,
  refetchSession,
}: UseDmContentMutationsOptions) {
  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setPaneError(apiErrorMessage(error));
    setUiMessage(null);
    showToastMessage(null);
  };

  const createStatblockMutation = useMutation({
    mutationFn: (payload: DmContentStatblockCreatePayload) => apiClient.createDmContentStatblock(campaignSlug, payload),
    onSuccess: (response) => {
      showToastMessage(`Statblock saved: ${response.statblock.title}. ${response.statblock.parser_feedback.summary}`);
      setUiMessage(null);
      setPaneError(null);
      setStatblockCreateDraft({ filename: "gen2-statblock.md", subsection: "", markdown: "" });
      refetchDmContent();
    },
    onError: handleMutationError,
  });

  const updateStatblockMutation = useMutation({
    mutationFn: (args: { id: number; payload: DmContentStatblockUpdatePayload }) =>
      apiClient.updateDmContentStatblock(campaignSlug, args.id, args.payload),
    onSuccess: (response) => {
      showToastMessage(`Statblock updated: ${response.statblock.title}. ${response.statblock.parser_feedback.summary}`);
      setUiMessage(null);
      setPaneError(null);
      refetchDmContent();
    },
    onError: handleMutationError,
  });

  const deleteStatblockMutation = useMutation({
    mutationFn: (statblockId: number) => apiClient.deleteDmContentStatblock(campaignSlug, statblockId),
    onSuccess: (response) => {
      showToastMessage(`Statblock deleted: ${response.statblock.title}.`);
      setUiMessage(null);
      setPaneError(null);
      refetchDmContent();
    },
    onError: handleMutationError,
  });

  const createConditionMutation = useMutation({
    mutationFn: (payload: DmContentConditionCreatePayload) => apiClient.createDmContentCondition(campaignSlug, payload),
    onSuccess: (response) => {
      showToastMessage(`Condition saved: ${response.condition.name}.`);
      setUiMessage(null);
      setPaneError(null);
      setConditionCreateDraft({ name: "", description: "" });
      refetchDmContent();
    },
    onError: handleMutationError,
  });

  const updateConditionMutation = useMutation({
    mutationFn: (args: { id: number; payload: DmContentConditionUpdatePayload }) =>
      apiClient.updateDmContentCondition(campaignSlug, args.id, args.payload),
    onSuccess: (response) => {
      showToastMessage(`Condition updated: ${response.condition.name}.`);
      setUiMessage(null);
      setPaneError(null);
      refetchDmContent();
    },
    onError: handleMutationError,
  });

  const deleteConditionMutation = useMutation({
    mutationFn: (conditionId: number) => apiClient.deleteDmContentCondition(campaignSlug, conditionId),
    onSuccess: (response) => {
      showToastMessage(`Condition deleted: ${response.condition.name}.`);
      setUiMessage(null);
      setPaneError(null);
      refetchDmContent();
    },
    onError: handleMutationError,
  });

  const savePlayerWikiPageMutation = useMutation({
    mutationFn: async (args: { mode: "create" | "edit"; pageRef: string; draft: DmPlayerWikiDraftState }) => {
      let imageRef = args.draft.image.trim();
      if (args.draft.imageUpload) {
        imageRef = buildPlayerWikiAssetRef(args.pageRef, args.draft.imageUpload);
        await apiClient.upsertContentAsset(campaignSlug, imageRef, {
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
      return apiClient.upsertContentPage(campaignSlug, args.pageRef, payload);
    },
    onSuccess: (response, args) => {
      const title = response.page_file.page.title || args.pageRef;
      showToastMessage(args.mode === "create" ? `Player Wiki page created: ${title}.` : `Player Wiki page updated: ${title}.`);
      setUiMessage(null);
      setPaneError(null);
      if (args.mode === "create") {
        setPlayerWikiCreateDraft(buildInitialPlayerWikiDraft());
      }
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      refetchContentPages();
    },
    onError: handleMutationError,
  });

  const archivePlayerWikiPageMutation = useMutation({
    mutationFn: async (pageRef: string) => {
      const detail = await apiClient.getContentPage(campaignSlug, pageRef);
      const draft = {
        ...buildPlayerWikiDraftFromRecord(detail.page_file),
        published: false,
        imageUpload: null,
      };
      const payload: ContentPageUpsertPayload = {
        metadata: buildPlayerWikiMetadata(draft, detail.page_file.page_ref, draft.image),
        body_markdown: draft.bodyMarkdown,
      };
      return apiClient.upsertContentPage(campaignSlug, detail.page_file.page_ref, payload);
    },
    onSuccess: (response) => {
      showToastMessage(`Player Wiki page archived: ${response.page_file.page.title}.`);
      setUiMessage(null);
      setPaneError(null);
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      refetchContentPages();
    },
    onError: handleMutationError,
  });

  const deletePlayerWikiPageMutation = useMutation({
    mutationFn: (pageRef: string) => apiClient.deleteContentPage(campaignSlug, pageRef),
    onSuccess: (response) => {
      const pageRef = response.deleted.page_ref;
      showToastMessage(`Player Wiki page deleted: ${pageRef}.`);
      setUiMessage(null);
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
      refetchContentPages();
    },
    onError: handleMutationError,
  });

  const loadPlayerWikiEditDraft = async (pageRef: string) => {
    setPaneError(null);
    showToastMessage(null);
    setUiMessage("Loading Player Wiki editor...");
    try {
      const response = await apiClient.getContentPage(campaignSlug, pageRef);
      setPlayerWikiEditDrafts((current) => ({
        ...current,
        [response.page_file.page_ref]: buildPlayerWikiDraftFromRecord(response.page_file),
      }));
      showToastMessage(`Editor loaded: ${response.page_file.page.title}.`);
      setUiMessage(null);
    } catch (error) {
      handleMutationError(error);
    }
  };

  const createArticleMutation = useMutation({
    mutationFn: (payload: SessionArticleCreatePayload) => apiClient.createSessionArticle(campaignSlug, payload),
    onSuccess: () => {
      showToastMessage("Article staged.");
      setUiMessage(null);
      setPaneError(null);
      setManualDraft(buildEmptyManualArticleDraft());
      setUploadDraft({ filename: "", markdown: "", image: null });
      setSelectedSourceRef("");
      refetchSession();
    },
    onError: handleMutationError,
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
      return apiClient.updateSessionArticle(campaignSlug, args.id, articlePayload);
    },
    onSuccess: (_response, args) => {
      showToastMessage("Article updated.");
      setUiMessage(null);
      setPaneError(null);
      setStagedDrafts((current) => ({
        ...current,
        [args.id]: {
          ...current[args.id],
          image: null,
        },
      }));
      refetchSession();
    },
    onError: handleMutationError,
  });

  const deleteArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.deleteSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      showToastMessage("Article removed.");
      setUiMessage(null);
      setPaneError(null);
      refetchSession();
    },
    onError: handleMutationError,
  });

  return {
    archivePlayerWikiPageMutation,
    createArticleMutation,
    createConditionMutation,
    createStatblockMutation,
    deleteArticleMutation,
    deleteConditionMutation,
    deletePlayerWikiPageMutation,
    deleteStatblockMutation,
    loadPlayerWikiEditDraft,
    savePlayerWikiPageMutation,
    updateArticleMutation,
    updateConditionMutation,
    updateStatblockMutation,
  };
}
