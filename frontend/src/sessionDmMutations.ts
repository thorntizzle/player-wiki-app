import type { Dispatch, SetStateAction } from "react";
import { useMutation } from "@tanstack/react-query";

import { apiErrorMessage, type CampaignApiClient } from "./api/client";
import type { SessionArticleCreatePayload, SessionArticleUpdatePayload } from "./api/types";
import { isAuthRequiredFromError as isAuthError } from "./sessionRouteState";
import {
  buildEmptyManualArticleDraft,
  type ManualArticleDraftState,
} from "./sessionArticleDrafts";

interface UseSessionDmMutationsOptions {
  apiClient: CampaignApiClient;
  campaignSlug: string;
  selectedLogSessionId: number | null;
  setAuthRequired: (required: boolean) => void;
  setUiMessage: Dispatch<SetStateAction<string | null>>;
  setPaneError: Dispatch<SetStateAction<string | null>>;
  setManualDraft: Dispatch<SetStateAction<ManualArticleDraftState>>;
  setSelectedLogSessionId: Dispatch<SetStateAction<number | null>>;
  refetch: () => void;
}

export function useSessionDmMutations({
  apiClient,
  campaignSlug,
  selectedLogSessionId,
  setAuthRequired,
  setUiMessage,
  setPaneError,
  setManualDraft,
  setSelectedLogSessionId,
  refetch,
}: UseSessionDmMutationsOptions) {
  const handleMutationError = (error: unknown) => {
    if (isAuthError(error)) {
      setAuthRequired(true);
    }
    setPaneError(apiErrorMessage(error));
    setUiMessage(null);
  };

  const startSessionMutation = useMutation({
    mutationFn: () => apiClient.startSession(campaignSlug),
    onSuccess: () => {
      setPaneError(null);
      setUiMessage("Session started.");
      refetch();
    },
    onError: handleMutationError,
  });

  const closeSessionMutation = useMutation({
    mutationFn: () => apiClient.closeSession(campaignSlug),
    onSuccess: () => {
      setPaneError(null);
      setUiMessage("Session closed.");
      refetch();
    },
    onError: handleMutationError,
  });

  const createArticleMutation = useMutation({
    mutationFn: (payload: SessionArticleCreatePayload) => apiClient.createSessionArticle(campaignSlug, payload),
    onSuccess: () => {
      setUiMessage("Article created.");
      setPaneError(null);
      setManualDraft(buildEmptyManualArticleDraft());
      refetch();
    },
    onError: handleMutationError,
  });

  const updateArticleMutation = useMutation({
    mutationFn: (args: { id: number; payload: SessionArticleUpdatePayload }) =>
      apiClient.updateSessionArticle(campaignSlug, args.id, args.payload),
    onSuccess: () => {
      setUiMessage("Article updated.");
      setPaneError(null);
      refetch();
    },
    onError: handleMutationError,
  });

  const revealArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.revealSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article revealed.");
      setPaneError(null);
      refetch();
    },
    onError: handleMutationError,
  });

  const deleteArticleMutation = useMutation({
    mutationFn: (articleId: number) => apiClient.deleteSessionArticle(campaignSlug, articleId),
    onSuccess: () => {
      setUiMessage("Article deleted.");
      setPaneError(null);
      refetch();
    },
    onError: handleMutationError,
  });

  const clearRevealedMutation = useMutation({
    mutationFn: () => apiClient.clearRevealedSessionArticles(campaignSlug),
    onSuccess: () => {
      setUiMessage("Revealed articles cleared.");
      setPaneError(null);
      refetch();
    },
    onError: handleMutationError,
  });

  const deleteLogMutation = useMutation({
    mutationFn: (sessionId: number) => apiClient.deleteSessionLog(campaignSlug, sessionId),
    onSuccess: (_data, sessionId) => {
      setUiMessage("Session log deleted.");
      setPaneError(null);
      if (selectedLogSessionId === sessionId) {
        setSelectedLogSessionId(null);
      }
      refetch();
    },
    onError: handleMutationError,
  });

  return {
    clearRevealedMutation,
    closeSessionMutation,
    createArticleMutation,
    deleteArticleMutation,
    deleteLogMutation,
    revealArticleMutation,
    startSessionMutation,
    updateArticleMutation,
  };
}
