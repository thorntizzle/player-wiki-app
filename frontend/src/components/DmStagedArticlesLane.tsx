import type { FormEvent } from "react";

import type {
  SessionArticle,
  SessionArticleCreatePayload,
  SessionArticleSourceResult,
} from "../api/types";
import type { StagedArticleDraftState } from "../dmContentUtils";
import type {
  ArticleMode,
  ManualArticleDraftState,
  UploadArticleDraftState,
} from "../sessionArticleDrafts";
import { DmArticleCreator } from "./DmArticleCreator";
import { DmStagedArticleQueue } from "./DmStagedArticleQueue";

interface DmStagedArticlesLaneProps {
  campaignSlug: string;
  canManageSession: boolean;
  isCreating: boolean;
  isDeleting: boolean;
  isUpdating: boolean;
  manualDraft: ManualArticleDraftState;
  mode: ArticleMode;
  onCreate: (payload: SessionArticleCreatePayload) => void;
  onDeleteArticle: (articleId: number) => void;
  onDraftChange: (
    article: SessionArticle,
    fallbackDraft: StagedArticleDraftState,
    updates: Partial<StagedArticleDraftState>,
  ) => void;
  onSearchSources: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onUpdateArticle: (args: { id: number; payload: StagedArticleDraftState; hasExistingImage: boolean }) => void;
  selectedSourceRef: string;
  setManualDraft: (next: ManualArticleDraftState) => void;
  setMode: (next: ArticleMode) => void;
  setSelectedSourceRef: (next: string) => void;
  setSourceQuery: (next: string) => void;
  setSourceStatus: (next: string | null) => void;
  setUploadDraft: (next: UploadArticleDraftState) => void;
  sourceQuery: string;
  sourceResults: SessionArticleSourceResult[];
  sourceStatus: string | null;
  stagedArticles: SessionArticle[];
  stagedDrafts: Record<number, StagedArticleDraftState>;
  uploadDraft: UploadArticleDraftState;
}

export function DmStagedArticlesLane({
  campaignSlug,
  canManageSession,
  isCreating,
  isDeleting,
  isUpdating,
  manualDraft,
  mode,
  onCreate,
  onDeleteArticle,
  onDraftChange,
  onSearchSources,
  onUpdateArticle,
  selectedSourceRef,
  setManualDraft,
  setMode,
  setSelectedSourceRef,
  setSourceQuery,
  setSourceStatus,
  setUploadDraft,
  sourceQuery,
  sourceResults,
  sourceStatus,
  stagedArticles,
  stagedDrafts,
  uploadDraft,
}: DmStagedArticlesLaneProps) {
  return (
    <div className="split-grid dm-content-staged-grid">
      <DmArticleCreator
        className="card"
        id="dm-content-staged-article-store"
        mode={mode}
        setMode={setMode}
        sourceQuery={sourceQuery}
        setSourceQuery={setSourceQuery}
        sourceStatus={sourceStatus}
        setSourceStatus={setSourceStatus}
        sourceResults={sourceResults}
        selectedSourceRef={selectedSourceRef}
        setSelectedSourceRef={setSelectedSourceRef}
        manualDraft={manualDraft}
        setManualDraft={setManualDraft}
        uploadDraft={uploadDraft}
        setUploadDraft={setUploadDraft}
        onSearchSources={onSearchSources}
        onCreate={onCreate}
        isCreating={isCreating}
      />

      <DmStagedArticleQueue
        campaignSlug={campaignSlug}
        stagedArticles={stagedArticles}
        stagedDrafts={stagedDrafts}
        canManageSession={canManageSession}
        isUpdating={isUpdating}
        isDeleting={isDeleting}
        onDraftChange={onDraftChange}
        onUpdateArticle={onUpdateArticle}
        onDeleteArticle={onDeleteArticle}
      />
    </div>
  );
}
