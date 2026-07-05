"use client";

/**
 * SettingsView — v1.3 model selection read-only display.
 *
 * v1.3 model migration: the default embedding is now Jina Embeddings v5 (small)
 * and the default reranker is Jina Reranker v3. BGE-M3 / BGE-reranker-base
 * remain available as toggleable alternatives.
 *
 * DESIGN DECISION (v1.3 — read-only settings):
 *   Model selection is env-var driven (`EMBEDDING_MODEL`, `RERANKER_MODEL`) and
 *   is set at container start. The frontend Settings view is READ-ONLY — it shows
 *   the currently active model (from the dashboard `system` field) and provides
 *   clear instructions for switching. This avoids the runtime model-reload
 *   complexity (which is risky with GPU memory and would also require
 *   re-ingesting documents since vectors are model-specific).
 *
 *   Switching models requires:
 *     1. Edit docker/.env (or docker-compose env block) — set
 *        EMBEDDING_MODEL=bge-m3 (or jina-v5-small to switch back).
 *     2. Optionally also set RERANKER_MODEL=bge-reranker-base (or jina-v3).
 *     3. `docker compose up -d --force-recreate backend api-worker`
 *     4. Re-ingest documents (vectors are model-specific — old vectors
 *        were produced by the previous model and are NOT compatible).
 *
 *   The Neo4j vector indexes themselves stay 1024-dim cosine for BOTH models —
 *   Jina v5 small uses Matryoshka truncation to 1024, BGE-M3 is natively 1024.
 *   So you do NOT need to re-create the Neo4j schema when switching models.
 */

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Settings as SettingsIcon,
  Cpu,
  Layers,
  Boxes,
  RefreshCw,
  Info,
  CheckCircle2,
  AlertTriangle,
  ServerOff,
  Terminal,
  BookOpen,
  Lightbulb,
} from "lucide-react";

import { api } from "@/lib/api-client";
import { ViewHeader, ViewBody } from "@/components/rag/shared/view-header";
import { BackendOffline } from "@/components/rag/shared/backend-offline";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

// ─── Dashboard `system` shape (loosely typed — backend returns extra fields too) ─

interface SystemInfo {
  embeddingModel?: string;
  embeddingModelLogical?: string;
  embeddingDim?: number;
  embeddingNativeDim?: number;
  rerankerModel?: string;
  rerankerModelLogical?: string;
  rerankerMaxLength?: number;
  stack?: string;
  v1Scope?: string;
}

interface DashboardData {
  system?: SystemInfo;
  health?: {
    backend?: { status?: "online" | "offline"; configured?: boolean; detail?: string | null };
    neo4j?: { status?: "online" | "offline"; uri?: string; user?: string; error?: string };
  };
}

// ─── Model metadata (v1.3) ────────────────────────────────────────────────────
// Display-only metadata for each selectable model. The "active" badge is computed
// by comparing the dashboard's `embeddingModelLogical` / `rerankerModelLogical`
// to these keys.

const EMBEDDING_OPTIONS = [
  {
    logicalId: "jina-v5-small",
    name: "Jina Embeddings v5 — Text Small",
    repo: "jinaai/jina-embeddings-v5-text-small",
    nativeDim: 1536,
    isDefault: true,
    description:
      "Task-conditioned Matryoshka-capable model. v1.3 default. Outputs 1024-dim vectors into Neo4j (truncated from native 1536) so the existing HNSW indexes work unchanged. Passes task='retrieval.query' for search and task='retrieval.passages' for indexing.",
    highlights: ["Task-conditioned", "Matryoshka → 1024", "Long-context", "v1.3 default"],
  },
  {
    logicalId: "bge-m3",
    name: "BGE-M3",
    repo: "BAAI/bge-m3",
    nativeDim: 1024,
    isDefault: false,
    description:
      "Multi-function (dense + sparse + multi-vector) embedding. Natively 1024-dim. No task conditioning — the is_query flag is ignored. Kept as a toggleable alternative for backward compatibility with v1.2 ingests.",
    highlights: ["1024-dim native", "Multi-function", "v1.2 fallback"],
  },
];

const RERANKER_OPTIONS = [
  {
    logicalId: "jina-v3",
    name: "Jina Reranker v3",
    repo: "jinaai/jina-reranker-v3",
    maxLength: 8192,
    isDefault: true,
    description:
      "Long-context cross-encoder reranker (8192 max tokens). v1.3 default. Works with the sentence-transformers CrossEncoder API; loaded with trust_remote_code=True.",
    highlights: ["8192 max tokens", "Long context", "v1.3 default"],
  },
  {
    logicalId: "bge-reranker-base",
    name: "BGE Reranker base",
    repo: "BAAI/bge-reranker-base",
    maxLength: 512,
    isDefault: false,
    description:
      "Lightweight cross-encoder reranker (512 max tokens). Kept as a toggleable alternative. Same CrossEncoder.predict() API as Jina v3 — the only differences are the model repo and max_length.",
    highlights: ["512 max tokens", "Lightweight", "v1.2 fallback"],
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export function SettingsView() {
  const { data, isLoading, isError, error, refetch } = useQuery<DashboardData>({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  const system = data?.system;
  const health = data?.health;
  const backendOffline = health?.backend?.status === "offline";

  const activeEmbeddingLogical = system?.embeddingModelLogical ?? "jina-v5-small";
  const activeRerankerLogical = system?.rerankerModelLogical ?? "jina-v3";
  const embeddingDim = system?.embeddingDim ?? 1024;
  const embeddingNativeDim = system?.embeddingNativeDim ?? 1536;
  const rerankerMaxLength = system?.rerankerMaxLength ?? 8192;

  return (
    <>
      <ViewHeader
        title="Settings"
        description="v1.3 model selection — Jina v5 default + BGE-M3 toggle (read-only)"
        icon={SettingsIcon}
        actions={
          <button
            type="button"
            onClick={() => refetch()}
            aria-label="Refresh settings"
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        }
      />
      <ViewBody className="space-y-6">
        {/* Backend offline banner */}
        {backendOffline && (
          <BackendOffline
            title="Backend offline — settings unavailable"
            message="The active model information is read from the FastAPI backend's /api/v1/dashboard endpoint. Start the Docker stack to view the current embedding + reranker models."
            onRetry={() => refetch()}
            showHint={true}
          />
        )}

        {/* v1.3 decision card: read-only + how-to-switch */}
        <Alert className="border-primary/30 bg-primary/5">
          <Info className="h-4 w-4 text-primary" />
          <AlertTitle className="flex items-center gap-2">
            v1.3 model selection is environment-driven (read-only UI)
            <Badge variant="outline" className="text-[10px] font-mono">
              env vars
            </Badge>
          </AlertTitle>
          <AlertDescription className="text-sm leading-relaxed">
            <p>
              The active embedding + reranker models are selected at container start via the{" "}
              <code className="font-mono text-xs">EMBEDDING_MODEL</code> and{" "}
              <code className="font-mono text-xs">RERANKER_MODEL</code> environment variables. This
              view is <strong>read-only</strong> — switching models requires editing{" "}
              <code className="font-mono text-xs">docker/.env</code> (or the compose env block) and
              recreating the backend containers. We deliberately avoid runtime model reloads because
              they are risky with GPU memory and because persisted vectors are model-specific.
            </p>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div className="rounded-md border border-primary/20 bg-background/60 p-2.5">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground mb-1">
                  <BookOpen className="h-3 w-3" /> Why read-only?
                </div>
                <p className="text-xs leading-relaxed">
                  Vectors stored in Neo4j are produced by the active embedding model. Switching
                  models requires re-ingesting documents so the persisted vectors match.
                </p>
              </div>
              <div className="rounded-md border border-primary/20 bg-background/60 p-2.5">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground mb-1">
                  <Lightbulb className="h-3 w-3" /> Indexes stay 1024-dim
                </div>
                <p className="text-xs leading-relaxed">
                  Jina v5 small uses Matryoshka truncation to 1024 dims; BGE-M3 is natively 1024.
                  The Neo4j vector indexes do NOT need re-creation when switching models.
                </p>
              </div>
            </div>
          </AlertDescription>
        </Alert>

        {/* Active model summary */}
        <section aria-label="Active models">
          <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Cpu className="h-4 w-4" /> Active Models
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <ActiveModelCard
              loading={isLoading}
              icon={Cpu}
              label="Embedding"
              repoId={system?.embeddingModel}
              logicalId={activeEmbeddingLogical}
              dim={embeddingDim}
              nativeDim={embeddingNativeDim}
              tooltip="The model currently loaded in the FastAPI backend's EmbeddingModule singleton."
            />
            <ActiveModelCard
              loading={isLoading}
              icon={Boxes}
              label="Reranker"
              repoId={system?.rerankerModel}
              logicalId={activeRerankerLogical}
              dim={rerankerMaxLength}
              dimLabel="max tokens"
              tooltip="The cross-encoder reranker currently loaded (lazy) by the RetrievalModule."
            />
          </div>
        </section>

        {/* Embedding model selector (display-only) */}
        <section aria-label="Embedding model options">
          <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Layers className="h-4 w-4" /> Embedding Model Options
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {EMBEDDING_OPTIONS.map((opt) => {
              const isActive = opt.logicalId === activeEmbeddingLogical;
              return (
                <ModelOptionCard
                  key={opt.logicalId}
                  name={opt.name}
                  repo={opt.repo}
                  logicalId={opt.logicalId}
                  description={opt.description}
                  highlights={opt.highlights}
                  isActive={isActive}
                  isDefault={opt.isDefault}
                  footer={
                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                      <span>
                        native dim:{" "}
                        <span className="font-mono text-foreground">{opt.nativeDim}</span>
                      </span>
                      <span>
                        → Neo4j dim:{" "}
                        <span className="font-mono text-foreground">{embeddingDim}</span>
                      </span>
                      {opt.logicalId === "jina-v5-small" && (
                        <Badge variant="outline" className="text-[10px] font-mono">
                          Matryoshka
                        </Badge>
                      )}
                    </div>
                  }
                />
              );
            })}
          </div>
        </section>

        {/* Reranker model selector (display-only) */}
        <section aria-label="Reranker model options">
          <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Layers className="h-4 w-4" /> Reranker Model Options
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {RERANKER_OPTIONS.map((opt) => {
              const isActive = opt.logicalId === activeRerankerLogical;
              return (
                <ModelOptionCard
                  key={opt.logicalId}
                  name={opt.name}
                  repo={opt.repo}
                  logicalId={opt.logicalId}
                  description={opt.description}
                  highlights={opt.highlights}
                  isActive={isActive}
                  isDefault={opt.isDefault}
                  footer={
                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                      <span>
                        max length:{" "}
                        <span className="font-mono text-foreground">{opt.maxLength}</span> tokens
                      </span>
                    </div>
                  }
                />
              );
            })}
          </div>
        </section>

        {/* How to switch models (instructions card) */}
        <section aria-label="How to switch">
          <h2 className="text-sm font-medium text-muted-foreground mb-3">How to Switch Models</h2>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Terminal className="h-4 w-4" />
                Switch via env var + container recreate
              </CardTitle>
              <CardDescription className="text-xs">
                Example: switch from the v1.3 default (Jina v5 + Jina Reranker v3) to BGE-M3 + BGE
                Reranker base.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ol className="space-y-3 text-sm">
                <SwitchStep
                  n={1}
                  title="Edit docker/.env (or the compose env block)"
                  body={
                    <>
                      <p className="mb-2">
                        Set the logical model ids for the embedding + reranker you want to use:
                      </p>
                      <pre className="rounded-md border bg-muted/40 p-3 text-xs font-mono overflow-x-auto thin-scroll">
{`# docker/.env  (or the environment: block in docker-compose.yml)
EMBEDDING_MODEL=bge-m3
RERANKER_MODEL=bge-reranker-base
EMBEDDING_DIM=1024   # stays 1024 for BOTH models (Jina uses Matryoshka truncation)`}
                      </pre>
                    </>
                  }
                />
                <SwitchStep
                  n={2}
                  title="Recreate the backend + api-worker containers"
                  body={
                    <>
                      <p className="mb-2">
                        The model is loaded once at startup, so a force-recreate is required to
                        pick up the new env var:
                      </p>
                      <pre className="rounded-md border bg-muted/40 p-3 text-xs font-mono overflow-x-auto thin-scroll">
{`docker compose up -d --force-recreate backend api-worker`}
                      </pre>
                    </>
                  }
                />
                <SwitchStep
                  n={3}
                  title="Re-ingest your documents"
                  body={
                    <Alert className="border-amber-500/40 bg-amber-500/5">
                      <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                      <AlertDescription className="text-xs leading-relaxed text-amber-900/80 dark:text-amber-200/80 pl-2">
                        Vectors stored in Neo4j are produced by the <em>previously active</em>{" "}
                        embedding model. They are NOT compatible with the new model. Re-ingest all
                        documents so the persisted vectors match the new embedder. The Neo4j vector
                        <strong> indexes</strong> themselves stay 1024-dim and do NOT need
                        re-creation (Jina uses Matryoshka truncation; BGE-M3 is natively 1024).
                      </AlertDescription>
                    </Alert>
                  }
                />
                <SwitchStep
                  n={4}
                  title="Verify via the Dashboard"
                  body={
                    <p className="text-xs leading-relaxed">
                      Open the Dashboard and check the <em>Embedding Model</em> row in the System
                      card — it should now show <code className="font-mono">BAAI/bge-m3</code>. Or
                      hit <code className="font-mono">GET /api/v1/dashboard</code> and inspect{" "}
                      <code className="font-mono">system.embeddingModel</code>.
                    </p>
                  }
                />
              </ol>
              <div className="border-t pt-3 mt-2">
                <div className="flex items-start gap-2 text-[11px] text-muted-foreground">
                  <Info className="h-3 w-3 mt-0.5 shrink-0" />
                  <p className="leading-relaxed">
                    To switch back to the v1.3 default, set{" "}
                    <code className="font-mono">EMBEDDING_MODEL=jina-v5-small</code> +{" "}
                    <code className="font-mono">RERANKER_MODEL=jina-v3</code> and repeat steps 2–3.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Pre-download BGE (so the toggle is instant) */}
        <section aria-label="Pre-download">
          <h2 className="text-sm font-medium text-muted-foreground mb-3">Pre-downloading BGE-M3</h2>
          <Card>
            <CardContent className="space-y-3 text-sm">
              <p className="leading-relaxed">
                The Docker image ships with Jina v5 + Jina Reranker v3 pre-downloaded by default (per{" "}
                <code className="font-mono">scripts/download_models.py</code>). To make the
                BGE-M3 toggle work without a re-download at runtime, run the download script with{" "}
                <code className="font-mono">DOWNLOAD_BGE=1</code>:
              </p>
              <pre className="rounded-md border bg-muted/40 p-3 text-xs font-mono overflow-x-auto thin-scroll">
{`# From the project root (one-time):
docker compose run --rm backend \\
  env DOWNLOAD_BGE=1 python scripts/download_models.py`}
              </pre>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                This saves <code className="font-mono">BAAI/bge-m3</code> +{" "}
                <code className="font-mono">BAAI/bge-reranker-base</code> into the{" "}
                <code className="font-mono">MODEL_PATH</code> volume so toggling{" "}
                <code className="font-mono">EMBEDDING_MODEL=bge-m3</code> doesn't require an outbound
                HuggingFace fetch on container start.
              </p>
            </CardContent>
          </Card>
        </section>

        {/* v1.3 architecture footnote */}
        <section aria-label="Architecture notes">
          <Card className="border-dashed">
            <CardContent className="text-xs text-muted-foreground space-y-2 leading-relaxed">
              <div className="flex items-center gap-1.5 text-foreground font-medium">
                <Info className="h-3.5 w-3.5" /> v1.3 architecture notes
              </div>
              <ul className="list-disc pl-5 space-y-1.5">
                <li>
                  <strong>Construction note #1 (float32 cast)</strong> is preserved on every encode
                  path for <em>both</em> models — Jina on GPU may also output bfloat16.
                </li>
                <li>
                  <strong>Jina task conditioning</strong>: the orchestrator passes{" "}
                  <code className="font-mono">is_query=True</code> for queries (task=&quot;retrieval.query&quot;)
                  and <code className="font-mono">is_query=False</code> for documents
                  (task=&quot;retrieval.passages&quot;). BGE-M3 ignores the flag.
                </li>
                <li>
                  <strong>Matryoshka truncation</strong>: Jina v5 small is loaded with{" "}
                  <code className="font-mono">truncate_dim=1024</code> so it produces 1024-dim
                  vectors — the same dim as BGE-M3 — and writes into the same Neo4j vector indexes.
                </li>
                <li>
                  <strong>Reranker</strong>: Jina Reranker v3 (max_length=8192) and BGE-reranker-base
                  (max_length=512) both use the sentence-transformers{" "}
                  <code className="font-mono">CrossEncoder</code> API; only the loading kwargs differ.
                </li>
                <li>
                  <strong>Switching models ≠ switching indexes</strong>: the 1024-dim Neo4j vector
                  indexes are model-agnostic, but the vectors inside them are not. Re-ingest
                  documents after every model switch.
                </li>
              </ul>
            </CardContent>
          </Card>
        </section>
      </ViewBody>
    </>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ActiveModelCard({
  loading,
  icon: Icon,
  label,
  repoId,
  logicalId,
  dim,
  nativeDim,
  dimLabel = "dim → Neo4j",
  tooltip,
}: {
  loading: boolean;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  repoId?: string;
  logicalId: string;
  dim: number;
  nativeDim?: number;
  dimLabel?: string;
  tooltip?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold">{label}</div>
              <div className="text-[10px] text-muted-foreground">{tooltip ?? "Active model"}</div>
            </div>
          </div>
          <Badge variant="outline" className="border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-[10px] gap-1">
            <CheckCircle2 className="h-3 w-3" />
            active
          </Badge>
        </div>
        {loading ? (
          <div className="space-y-1.5">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        ) : (
          <dl className="space-y-1 text-xs">
            <div className="flex items-baseline justify-between gap-2 min-w-0">
              <dt className="text-muted-foreground shrink-0">Repo</dt>
              <dd className="font-mono text-right truncate" title={repoId ?? ""}>
                {repoId ?? "—"}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-muted-foreground">Logical id</dt>
              <dd className="font-mono">{logicalId}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-muted-foreground">{dimLabel}</dt>
              <dd className="font-mono">{dim}</dd>
            </div>
            {nativeDim !== undefined && (
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-muted-foreground">Native dim</dt>
                <dd className="font-mono">{nativeDim}</dd>
              </div>
            )}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function ModelOptionCard({
  name,
  repo,
  logicalId,
  description,
  highlights,
  isActive,
  isDefault,
  footer,
}: {
  name: string;
  repo: string;
  logicalId: string;
  description: string;
  highlights: string[];
  isActive: boolean;
  isDefault: boolean;
  footer?: React.ReactNode;
}) {
  return (
    <Card
      className={cn(
        "transition-colors",
        isActive
          ? "border-emerald-500/40 bg-emerald-500/5"
          : "border-border hover:border-primary/30",
      )}
    >
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-semibold">{name}</h3>
              {isDefault && (
                <Badge variant="outline" className="text-[10px] gap-1 border-primary/30 bg-primary/10 text-primary">
                  v1.3 default
                </Badge>
              )}
              {isActive && (
                <Badge variant="outline" className="text-[10px] gap-1 border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  active
                </Badge>
              )}
            </div>
            <div className="text-[11px] font-mono text-muted-foreground mt-1 truncate" title={repo}>
              {repo}
            </div>
          </div>
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
        <div className="flex flex-wrap gap-1.5">
          {highlights.map((h) => (
            <Badge key={h} variant="secondary" className="text-[10px] font-mono">
              {h}
            </Badge>
          ))}
        </div>
        {footer}
        <div className="pt-2 border-t text-[11px] text-muted-foreground">
          {isActive ? (
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
              Currently loaded — no action needed.
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              <ServerOff className="h-3 w-3" />
              Set <code className="font-mono">EMBEDDING_MODEL={logicalId}</code>
              {logicalId.startsWith("bge") || logicalId === "bge-reranker-base" ? (
                <> (or <code className="font-mono">RERANKER_MODEL={logicalId}</code>)</>
              ) : null}
              {" "}+ recreate containers to activate.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function SwitchStep({
  n,
  title,
  body,
}: {
  n: number;
  title: string;
  body: React.ReactNode;
}) {
  return (
    <li className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
        {n}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="text-sm font-medium">{title}</div>
        <div className="text-xs text-muted-foreground">{body}</div>
      </div>
    </li>
  );
}
