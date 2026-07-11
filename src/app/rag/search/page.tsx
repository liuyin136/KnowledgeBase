"use client";

import { useEffect, useState } from "react";
import { pollJobUntilAwaitingOrDone, pollJobUntilDone, type JobStatusResponse } from "@/lib/api/jobs";
import {
  confirmRerank,
  searchDocuments,
  type FusionMeta,
  type RerankPreviewMeta,
  type SearchHit,
  type SearchRequest,
  type WorkflowPhase,
  type WorkflowPhaseName,
} from "@/lib/api/search";
import { listFolders, type VaultFolder } from "@/lib/api/vault";
import { FusionControls } from "@/components/rag/FusionControls";
import { RerankConfirmDialog } from "@/components/rag/RerankConfirmDialog";
import { SearchPanel, SearchSkeleton } from "@/components/rag/SearchPanel";
import { SearchResults } from "@/components/rag/SearchResults";
import {
  SearchScopeFilters,
  defaultSearchScope,
  type SearchScopeValue,
} from "@/components/rag/SearchScopeFilters";
import { SearchWorkflowLog } from "@/components/rag/SearchWorkflowLog";

function scopeIsActive(scope: SearchScopeValue): boolean {
  return (
    scope.folderIds.length > 0 ||
    Boolean(scope.createdAfter) ||
    Boolean(scope.createdBefore) ||
    !scope.indexedOnly
  );
}

function scopeToRequest(scope: SearchScopeValue): Partial<SearchRequest> {
  const payload: Partial<SearchRequest> = {};
  if (scope.folderIds.length > 0) payload.folder_ids = scope.folderIds;
  if (scope.createdAfter) payload.created_after = scope.createdAfter;
  if (scope.createdBefore) payload.created_before = scope.createdBefore;
  if (!scope.indexedOnly) payload.indexed_only = false;
  return payload;
}

function previewFromJob(
  jobPreview: RerankPreviewMeta | null | undefined,
  result: JobStatusResponse["result"]
): RerankPreviewMeta | null {
  if (jobPreview) return jobPreview;
  if (!result?.rerank_token_count) return null;
  return {
    rerank_token_count: result.rerank_token_count,
    rerank_ctx_limit: result.rerank_ctx_limit ?? 131072,
    rerank_doc_count: result.rerank_doc_count ?? 0,
    rerank_k: result.fusion_meta?.rerank_k ?? 10,
  };
}

export default function RagSearchPage() {
  const [query, setQuery] = useState("");
  const [w1, setW1] = useState(0.7);
  const [coarseDim, setCoarseDim] = useState<256 | 512>(256);
  const [scope, setScope] = useState<SearchScopeValue>(defaultSearchScope);
  const [folders, setFolders] = useState<VaultFolder[]>([]);
  const [foldersLoading, setFoldersLoading] = useState(true);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [cached, setCached] = useState(false);
  const [spanId, setSpanId] = useState<string | null>(null);
  const [workflowLog, setWorkflowLog] = useState<WorkflowPhase[] | null>(null);
  const [activePhase, setActivePhase] = useState<WorkflowPhaseName | null>(null);
  const [fusionMeta, setFusionMeta] = useState<FusionMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [reranking, setReranking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fusionJobId, setFusionJobId] = useState<string | null>(null);
  const [awaitingRerank, setAwaitingRerank] = useState(false);
  const [rerankPreview, setRerankPreview] = useState<RerankPreviewMeta | null>(null);
  const [confirmingRerank, setConfirmingRerank] = useState(false);
  const [showRerankScores, setShowRerankScores] = useState(false);

  useEffect(() => {
    listFolders()
      .then(setFolders)
      .catch(() => setFolders([]))
      .finally(() => setFoldersLoading(false));
  }, []);

  function applyProgressFromJob(job: JobStatusResponse) {
    const progress = job.progress;
    if (!progress) return;
    setWorkflowLog(progress.workflow_log);
    setActivePhase(progress.active_phase);
    if (progress.span_id) setSpanId(progress.span_id);
  }

  function applySearchResult(result: {
    hits?: SearchHit[];
    workflow_log?: WorkflowPhase[] | null;
    fusion_meta?: FusionMeta | null;
    span_id?: string | null;
    cached?: boolean;
    withRerank?: boolean;
  }) {
    setHits(result.hits ?? []);
    setWorkflowLog(result.workflow_log ?? null);
    setFusionMeta(result.fusion_meta ?? null);
    if (result.span_id) setSpanId(result.span_id);
    if (result.cached !== undefined) setCached(result.cached);
    setShowRerankScores(result.withRerank ?? false);
    setActivePhase(null);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim().length < 2) {
      setError("Query must be at least 2 characters");
      return;
    }
    setLoading(true);
    setReranking(false);
    setError(null);
    setHits([]);
    setWorkflowLog([]);
    setActivePhase(scopeIsActive(scope) ? "vault_scope" : "query_embed");
    setFusionMeta(null);
    setFusionJobId(null);
    setAwaitingRerank(false);
    setRerankPreview(null);
    setShowRerankScores(false);
    try {
      const res = await searchDocuments({
        query: query.trim(),
        w1,
        w2: 1 - w1,
        coarse_dim: coarseDim,
        ...scopeToRequest(scope),
      });
      setSpanId(res.span_id);
      if (res.hits !== undefined && res.hits !== null && !res.job_id) {
        applySearchResult({
          hits: res.hits,
          workflow_log: res.workflow_log,
          fusion_meta: res.fusion_meta,
          span_id: res.span_id,
          cached: res.cached,
          withRerank: true,
        });
        return;
      }
      if (res.cached && res.hits) {
        applySearchResult({
          hits: res.hits,
          workflow_log: res.workflow_log,
          fusion_meta: res.fusion_meta,
          span_id: res.span_id,
          cached: true,
          withRerank: true,
        });
        return;
      }
      if (!res.job_id) {
        throw new Error("Missing job_id from search API");
      }
      setFusionJobId(res.job_id);
      const job = await pollJobUntilAwaitingOrDone(res.job_id, {
        onProgress: applyProgressFromJob,
      });
      if (job.status === "failed") {
        throw new Error(job.error || "Search job failed");
      }
      const result = job.result;
      if (job.status === "awaiting_rerank" && result) {
        applySearchResult({
          hits: result.hits,
          workflow_log: result.workflow_log,
          fusion_meta: result.fusion_meta,
          span_id: result.span_id,
          cached: false,
          withRerank: false,
        });
        setAwaitingRerank(true);
        setRerankPreview(previewFromJob(job.rerank_preview, result));
        return;
      }
      applySearchResult({
        hits: result?.hits,
        workflow_log: result?.workflow_log,
        fusion_meta: result?.fusion_meta,
        span_id: result?.span_id,
        cached: false,
        withRerank: Boolean(result?.workflow_log?.some((p) => p.phase === "rerank")),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  async function onConfirmRerank() {
    if (!fusionJobId) return;
    setConfirmingRerank(true);
    setError(null);
    try {
      const confirmRes = await confirmRerank(fusionJobId, true);
      if (!confirmRes.rerank_job_id) {
        throw new Error("Missing rerank_job_id");
      }
      setAwaitingRerank(false);
      setReranking(true);
      setActivePhase("rerank");
      const rerankJob = await pollJobUntilDone(confirmRes.rerank_job_id, {
        timeoutMs: 300_000,
        onProgress: applyProgressFromJob,
      });
      if (rerankJob.status === "failed") {
        throw new Error(rerankJob.error || "Rerank job failed");
      }
      const result = rerankJob.result;
      applySearchResult({
        hits: result?.hits,
        workflow_log: result?.workflow_log,
        fusion_meta: result?.fusion_meta,
        span_id: result?.span_id ?? confirmRes.span_id ?? undefined,
        cached: false,
        withRerank: true,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rerank failed");
    } finally {
      setConfirmingRerank(false);
      setReranking(false);
    }
  }

  async function onSkipRerank() {
    if (!fusionJobId) return;
    setConfirmingRerank(true);
    setError(null);
    try {
      const confirmRes = await confirmRerank(fusionJobId, false);
      setAwaitingRerank(false);
      applySearchResult({
        hits: confirmRes.hits,
        workflow_log: confirmRes.workflow_log,
        fusion_meta: confirmRes.fusion_meta,
        span_id: confirmRes.span_id ?? undefined,
        cached: false,
        withRerank: false,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Skip rerank failed");
    } finally {
      setConfirmingRerank(false);
    }
  }

  const workflowLoading = loading || reranking;
  const showVaultScope = scopeIsActive(scope);

  return (
    <>
      <SearchPanel
        query={query}
        loading={loading || confirmingRerank || reranking}
        onQueryChange={setQuery}
        onSubmit={onSubmit}
      >
        <SearchScopeFilters
          folders={folders}
          value={scope}
          onChange={setScope}
          loadingFolders={foldersLoading}
        />
        <FusionControls
          w1={w1}
          coarseDim={coarseDim}
          onW1Change={setW1}
          onCoarseDimChange={setCoarseDim}
        />
      </SearchPanel>

      <SearchWorkflowLog
        workflowLog={workflowLog}
        fusionMeta={fusionMeta}
        cached={cached}
        loading={workflowLoading}
        activePhase={activePhase}
        showVaultScope={showVaultScope}
        awaitingRerank={awaitingRerank}
        rerankPreview={rerankPreview}
      />

      {error && <div className="rag-error">{error}</div>}

      {workflowLoading ? (
        <SearchSkeleton />
      ) : (
        <SearchResults hits={hits} cached={cached} showRerankScores={showRerankScores} />
      )}

      <RerankConfirmDialog
        open={awaitingRerank}
        preview={rerankPreview}
        confirming={confirmingRerank}
        onConfirm={onConfirmRerank}
        onSkip={onSkipRerank}
        onClose={() => setAwaitingRerank(false)}
      />

      {spanId && (
        <footer className="rag-footer">
          span_id: <code>{spanId}</code>
        </footer>
      )}
    </>
  );
}
