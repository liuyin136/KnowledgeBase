"use client";

/**
 * DashboardView — system health + quick-start cards + recent activity.
 * Frontend_Workflow_Mapping v1.1 §3 (Dashboard).
 *
 * Server state: TanStack Query ("dashboard").
 * Local state: none (seed functionality removed).
 */

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard,
  FlaskConical,
  FileText,
  Boxes,
  Search as SearchIcon,
  Brain,
  ShoppingCart,
  Upload,
  ArrowRight,
  Sparkles,
  Clock,
  CheckCircle2,
  XCircle,
  Activity,
  Cpu,
  Layers,
  Server,
  Database,
  ServerOff,
  RefreshCw,
  Terminal,
  AlertTriangle,
  Zap,
} from "lucide-react";

import { api, APIError } from "@/lib/api-client";
import { useUIStore } from "@/store/use-ui-store";
import { ViewHeader, ViewBody } from "@/components/rag/shared/view-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ─── Types (typed inline since dashboard returns a loose shape) ─────────────

interface DashboardStats {
  // experiments stat removed (no :Experiment node)
  documents: number;
  chunks: number;
  searches: number;
  memories: number;
  carts: number;
}

// RecentExperiment interface removed (no more experiment concept)

interface RecentSearch {
  id: string;
  rawQuery: string;
  hybridAlpha: number;
  autoTuneWeights: boolean;
  bestAlpha: number | null;
  resultCount: number;
  searchTimeMs: number;
  createdAt: string;
}

interface DashboardData {
  stats: DashboardStats;
  recentExperiments: any[]; // removed, kept for shape
  recentSearches: RecentSearch[];
  system: {
    embeddingModel: string;
    embeddingDim: number;
    stack: string;
    v1Scope: string;
  };
  health: {
    backend: {
      status: "online" | "offline";
      configured: boolean;
      detail?: unknown; // can be {status: "ok"} object from backend /health
    };
    neo4j: {
      status: "online" | "offline";
      uri: string;
      user: string;
      error?: string;
    };
  };
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.max(1, Math.floor((now - then) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  const diffWk = Math.floor(diffDay / 7);
  if (diffWk < 5) return `${diffWk}w ago`;
  return new Date(iso).toLocaleDateString();
}

function formatMs(ms: number): string {
  if (!ms || ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function statusTone(status: string): { className: string; label: string } {
  switch (status) {
    case "completed":
      return { label: "completed", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" };
    case "failed":
      return { label: "failed", className: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400" };
    case "running":
      return { label: "running", className: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400" };
    case "pending":
    default:
      return { label: status || "pending", className: "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-400" };
  }
}

function truncate(text: string, n: number): string {
  if (!text) return "";
  return text.length > n ? text.slice(0, n) + "…" : text;
}

// ─── Stat card meta ─────────────────────────────────────────────────────────

interface StatMeta {
  key: keyof DashboardStats | "documentsTotal";
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  subLabel: (s: DashboardStats) => string;
  value: (s: DashboardStats) => number;
}

const STAT_META: StatMeta[] = [
  // experiments stat removed (no :Experiment node)
  { key: "documents", label: "Documents", icon: FileText, value: (s) => s.documents, subLabel: () => "uploaded source files" },
  { key: "chunks", label: "Chunks", icon: Boxes, value: (s) => s.chunks, subLabel: () => "embedded children" },
  { key: "searches", label: "Searches", icon: SearchIcon, value: (s) => s.searches, subLabel: () => "hybrid runs" },
  { key: "memories", label: "Memories", icon: Brain, value: (s) => s.memories, subLabel: () => "curated hits" },
  { key: "carts", label: "Memory Carts", icon: ShoppingCart, value: (s) => s.carts, subLabel: () => "collections" },
];

const QUICK_START = [
  { key: "ingest", title: "Ingest", desc: "Upload a document, pick a chunking + embedding config, and watch per-chunk metadata stream in.", icon: Upload },
  { key: "search", title: "Hybrid Search", desc: "Run vector + BM25 retrieval with manual or adaptive alpha fusion and optional reranker.", icon: SearchIcon },
  { key: "memory", title: "Memory Cart", desc: "Curate search hits into named carts for evaluation across documents.", icon: ShoppingCart },
  { key: "documents", title: "Documents", desc: "All uploaded, ingested & chunked files (from :Knowledge records).", icon: FileText },
] as const;

// ─── Component ──────────────────────────────────────────────────────────────

export function DashboardView() {
  const setView = useUIStore((s) => s.setView);
  const setActiveDocument = useUIStore((s) => s.setActiveDocument);
  const qc = useQueryClient();

  const { data, isLoading, isError, error, refetch } = useQuery<DashboardData>({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });
  // observation (browser): what dashboard received from proxy (stats experiments/documents, from neo4j). ponytail: effect to avoid render spam
  React.useEffect(() => { if (data && typeof window !== "undefined") console.debug("[obs:dashboard]", { stats: data.stats, health: data.health }); }, [data]);

  // POST /api/v1/neo4j/init — initialize the Neo4j schema (constraints +
  // vector + fulltext indexes). Idempotent. Only meaningful once Neo4j is up.
  const neo4jInitMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/v1/neo4j/init", { method: "POST" });
      const text = await res.text();
      const body = text ? JSON.parse(text) : null;
      if (!res.ok) {
        throw new APIError(body, res.status);
      }
      return body as {
        applied: string[];
        errors: { step: string; error: string }[];
        embeddingDim: number;
        indexes: { name: string; type: string }[];
      };
    },
    onSuccess: (res) => {
      const errCount = res.errors?.length ?? 0;
      if (errCount === 0) {
        toast.success(
          `Neo4j schema initialized — ${res.indexes?.length ?? 0} indexes present`,
        );
      } else {
        toast.warning(`Neo4j init: ${res.errors.length} step(s) failed`, {
          description: res.errors.map((e) => `${e.step}: ${e.error}`).join(" · "),
        });
      }
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => {
      const msg = err instanceof APIError ? err.message : "Failed to init Neo4j schema";
      toast.error("Neo4j init failed", { description: msg });
    },
  });

  const stats = data?.stats;
  const health = data?.health;
  const backendOffline = health?.backend.status === "offline";
  const neo4jOffline = health?.neo4j.status === "offline";
  const anyOffline = backendOffline || neo4jOffline;
  const isEmpty =
    !!stats &&
    stats.documents === 0 &&
    stats.chunks === 0 &&
    stats.searches === 0 &&
    stats.memories === 0 &&
    stats.carts === 0 &&
    (data?.recentExperiments.length ?? 0) === 0 &&
    (data?.recentSearches.length ?? 0) === 0;

  return (
    <>
      <ViewHeader
        title="Dashboard"
        description="System health & quick stats"
        icon={LayoutDashboard}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              aria-label="Refresh dashboard"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
          </div>
        }
      />
      <ViewBody className="space-y-8">
        {/* Offline banner */}
        {anyOffline && !isLoading && (
          <Alert className="border-amber-500/40 bg-amber-500/5">
            <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
            <AlertTitle className="text-amber-900 dark:text-amber-100">
              Backend services offline
            </AlertTitle>
            <AlertDescription className="text-amber-900/80 dark:text-amber-200/80">
              <p className="leading-relaxed">
                Start the Docker stack (
                <code className="font-mono text-xs">docker compose up -d</code>
                ) to enable data operations. The UI is viewable but ingest /
                search / documents will return errors until both the FastAPI
                backend and Neo4j are healthy.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => refetch()}
                  className="gap-1.5 border-amber-500/40 text-amber-900 hover:bg-amber-500/10 dark:text-amber-100"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Re-check health
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={neo4jOffline || neo4jInitMutation.isPending}
                  onClick={() => neo4jInitMutation.mutate()}
                  className="gap-1.5 border-amber-500/40 text-amber-900 hover:bg-amber-500/10 dark:text-amber-100"
                  title={
                    neo4jOffline
                      ? "Neo4j must be online before initializing the schema."
                      : "Initialize Neo4j schema (constraints + vector + fulltext indexes)"
                  }
                >
                  <Zap className="h-3.5 w-3.5" />
                  {neo4jInitMutation.isPending ? "Initializing…" : "Init Neo4j schema"}
                </Button>
                <a
                  href="/api/v1/neo4j/init"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/40 px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-500/10 dark:text-amber-100"
                >
                  <Terminal className="h-3 w-3" />
                  /api/v1/neo4j/init
                </a>
              </div>
            </AlertDescription>
          </Alert>
        )}

        {isError && (
          <Card className="border-red-500/30 bg-red-500/5">
            <CardContent className="py-4 text-sm text-red-700 dark:text-red-400 flex items-center justify-between gap-3">
              <span>Failed to load dashboard: {error instanceof APIError ? error.message : "Unknown error"}</span>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Retry
              </Button>
            </CardContent>
          </Card>
        )}

        {/* System Connections — health cards (top, prominent) */}
        <section aria-label="System connections">
          <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Server className="h-4 w-4" /> System Connections
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <BackendHealthCard
              loading={isLoading}
              status={health?.backend.status}
              configured={health?.backend.configured}
              detail={health?.backend.detail ?? null}
            />
            <Neo4jHealthCard
              loading={isLoading}
              status={health?.neo4j.status}
              uri={health?.neo4j.uri}
              user={health?.neo4j.user}
              error={health?.neo4j.error}
              onInit={() => neo4jInitMutation.mutate()}
              initPending={neo4jInitMutation.isPending}
              initDisabled={neo4jOffline}
            />
          </div>
        </section>

        {/* Empty state */}
        {isEmpty && !isLoading && !anyOffline && (
          <Card className="border-dashed">
            <CardContent className="py-12 flex flex-col items-center text-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Sparkles className="h-7 w-7" />
              </div>
              <div className="space-y-1">
                <h2 className="text-lg font-semibold">Welcome to RAG Lab v1</h2>
                <p className="text-sm text-muted-foreground max-w-md">
                  Your local-first RAG platform is empty. Go to the Ingest view to upload .md documents
                  and start creating knowledge records.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stat cards */}
        <section aria-label="System stats">
          <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4" /> System Stats
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
            {isLoading || !stats
              ? Array.from({ length: 6 }).map((_, i) => (
                  <Card key={i} className="py-4">
                    <CardContent className="space-y-2">
                      <Skeleton className="h-8 w-8 rounded-md" />
                      <Skeleton className="h-3 w-16" />
                      <Skeleton className="h-7 w-12" />
                      <Skeleton className="h-3 w-24" />
                    </CardContent>
                  </Card>
                ))
              : STAT_META.map((m) => {
                  const Icon = m.icon;
                  return (
                    <Card key={m.key} className="py-4 hover:shadow-md transition-shadow">
                      <CardContent className="space-y-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="text-xs text-muted-foreground">{m.label}</div>
                        <div className="text-2xl font-semibold tracking-tight tabular-nums">
                          {m.value(stats)}
                        </div>
                        <div className="text-[11px] text-muted-foreground">{m.subLabel(stats)}</div>
                      </CardContent>
                    </Card>
                  );
                })}
          </div>
        </section>

        {/* Quick Start */}
        <section aria-label="Quick start">
          <h2 className="text-sm font-medium text-muted-foreground mb-3">Quick Start</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {QUICK_START.map((q) => {
              const Icon = q.icon;
              return (
                <button
                  key={q.key}
                  type="button"
                  onClick={() => setView(q.key)}
                  className="text-left"
                  aria-label={`Open ${q.title}`}
                >
                  <Card className="py-4 h-full hover:shadow-md hover:border-primary/40 transition-all group cursor-pointer">
                    <CardContent className="space-y-3">
                      <div className="flex items-start justify-between">
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <Icon className="h-5 w-5" />
                        </div>
                        <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold">{q.title}</div>
                        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{q.desc}</p>
                      </div>
                    </CardContent>
                  </Card>
                </button>
              );
            })}
          </div>
        </section>

        {/* Recent activity grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent Experiments */}
          <section aria-label="Recent experiments">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <FileText className="h-4 w-4" /> Recent Documents
              </h2>
              <Button variant="ghost" size="sm" onClick={() => setView("documents")}>
                View all <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
            <Card className="py-0">
              <CardContent className="p-0">
                {isLoading ? (
                  <div className="p-4 space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-12 w-full" />
                    ))}
                  </div>
                ) : (data?.recentExperiments.length ?? 0) === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground">
                    No documents yet. Start by <button className="text-primary hover:underline" onClick={() => setView("ingest")}>uploading in Ingest</button>.
                  </div>
                ) : (
                  <div className="p-6 text-center text-sm text-muted-foreground">
                    Recent documents now managed in Documents view.
                  </div>
                )}
              </CardContent>
            </Card>
          </section>

          {/* Recent Searches */}
          <section aria-label="Recent searches">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <SearchIcon className="h-4 w-4" /> Recent Searches
              </h2>
              <Button variant="ghost" size="sm" onClick={() => setView("search")}>
                New search <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </div>
            <Card className="py-0">
              <CardContent className="p-0">
                {isLoading ? (
                  <div className="p-4 space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-12 w-full" />
                    ))}
                  </div>
                ) : (data?.recentSearches.length ?? 0) === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground">
                    No searches yet. <button className="text-primary hover:underline" onClick={() => setView("search")}>Run your first hybrid search</button>.
                  </div>
                ) : (
                  <ul className="divide-y max-h-80 overflow-y-auto thin-scroll">
                    {data!.recentSearches.slice(0, 5).map((s) => (
                      <li key={s.id} className="px-4 py-3 hover:bg-accent/50 transition-colors">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium truncate">{truncate(s.rawQuery, 64)}</div>
                            <div className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-2 flex-wrap">
                              <span className="font-mono">α={s.hybridAlpha.toFixed(1)}</span>
                              {s.autoTuneWeights && s.bestAlpha !== null && (
                                <>
                                  <span>·</span>
                                  <span className="text-primary font-mono">best α={s.bestAlpha.toFixed(1)}</span>
                                </>
                              )}
                              <span>·</span>
                              <span>{s.resultCount} results</span>
                              <span>·</span>
                              <span className="font-mono">{formatMs(s.searchTimeMs)}</span>
                            </div>
                          </div>
                          <span className="text-[10px] text-muted-foreground flex items-center gap-1 shrink-0">
                            <Clock className="h-2.5 w-2.5" />
                            {timeAgo(s.createdAt)}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </section>
        </div>

        {/* System info */}
        <section aria-label="System info">
          <h2 className="text-sm font-medium text-muted-foreground mb-3">System</h2>
          <Card>
            <CardContent className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <SystemRow icon={Cpu} label="Embedding Model" value={data?.system.embeddingModel ?? "—"} />
              <SystemRow icon={Layers} label="Embedding Dim" value={data ? String(data.system.embeddingDim) : "—"} />
              <SystemRow icon={Activity} label="Stack" value={data?.system.stack ?? "—"} />
              <div className="sm:col-span-2 lg:col-span-3 text-[11px] text-muted-foreground italic border-t pt-3 mt-1">
                v1 scope: {data?.system.v1Scope ?? "—"}
              </div>
            </CardContent>
          </Card>
        </section>
      </ViewBody>
    </>
  );
}

function SystemRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted text-muted-foreground shrink-0">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <div className="text-[11px] text-muted-foreground uppercase tracking-wide">{label}</div>
        <div className="text-sm font-medium mt-0.5 break-words">{value}</div>
      </div>
    </div>
  );
}

// ─── Health cards (v1.2 system connections) ──────────────────────────────────

function StatusBadge({ status }: { status: "online" | "offline" | undefined }) {
  if (!status) {
    return (
      <Badge variant="outline" className="text-[10px] gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
        unknown
      </Badge>
    );
  }
  if (status === "online") {
    return (
      <Badge variant="outline" className="text-[10px] gap-1 border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
        online
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="text-[10px] gap-1 border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400">
      <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
      offline
    </Badge>
  );
}

function BackendHealthCard({
  loading,
  status,
  configured,
  detail,
}: {
  loading: boolean;
  status: "online" | "offline" | undefined;
  configured: boolean | undefined;
  detail?: unknown; // was string | null — backend /health returns {status: "ok"} object
}) {
  const offline = status === "offline";

  // Safe rendering: stringify objects (e.g. {status: "ok"}) to prevent React #31
  // "Objects are not valid as a React child (found: object with keys {status})"
  const detailStr = detail == null
    ? null
    : typeof detail === "string"
      ? detail
      : JSON.stringify(detail);

  return (
    <Card className={cn(offline ? "border-red-500/30 bg-red-500/5" : "border-emerald-500/20")}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg shrink-0",
                offline
                  ? "bg-red-500/10 text-red-600 dark:text-red-400"
                  : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
              )}
            >
              {offline ? <ServerOff className="h-5 w-5" /> : <Server className="h-5 w-5" />}
            </div>
            <div>
              <div className="text-sm font-semibold">FastAPI Backend</div>
              <div className="text-[10px] text-muted-foreground">
                BGE-M3 embeddings · hybrid retrieval · reranker
              </div>
            </div>
          </div>
          {loading ? (
            <Skeleton className="h-5 w-16 rounded-full" />
          ) : (
            <StatusBadge status={status} />
          )}
        </div>
        {loading ? (
          <div className="space-y-1.5">
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        ) : (
          <dl className="space-y-1 text-xs">
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-muted-foreground">Configured</dt>
              <dd className="font-mono">
                {configured ? "yes (BACKEND_URL set)" : "no (BACKEND_URL missing)"}
              </dd>
            </div>
            {detailStr != null && (
              <div className="flex items-baseline justify-between gap-2 min-w-0">
                <dt className="text-muted-foreground shrink-0">Detail</dt>
                <dd className="font-mono text-right truncate" title={detailStr}>
                  {detailStr}
                </dd>
              </div>
            )}
            {offline && (
              <div className="text-[11px] text-red-700/80 dark:text-red-300/80 mt-2 pt-2 border-t border-red-500/20">
                Start the backend: <code className="font-mono">docker compose up -d backend</code>
              </div>
            )}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function Neo4jHealthCard({
  loading,
  status,
  uri,
  user,
  error,
  onInit,
  initPending,
  initDisabled,
}: {
  loading: boolean;
  status: "online" | "offline" | undefined;
  uri: string | undefined;
  user: string | undefined;
  error?: string;
  onInit: () => void;
  initPending: boolean;
  initDisabled: boolean;
}) {
  const offline = status === "offline";
  return (
    <Card className={cn(offline ? "border-red-500/30 bg-red-500/5" : "border-emerald-500/20")}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg shrink-0",
                offline
                  ? "bg-red-500/10 text-red-600 dark:text-red-400"
                  : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
              )}
            >
              <Database className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold">Neo4j Database</div>
              <div className="text-[10px] text-muted-foreground">
                Knowledge graph · vector index · BM25 fulltext
              </div>
            </div>
          </div>
          {loading ? (
            <Skeleton className="h-5 w-16 rounded-full" />
          ) : (
            <StatusBadge status={status} />
          )}
        </div>
        {loading ? (
          <div className="space-y-1.5">
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        ) : (
          <dl className="space-y-1 text-xs">
            <div className="flex items-baseline justify-between gap-2 min-w-0">
              <dt className="text-muted-foreground shrink-0">URI</dt>
              <dd className="font-mono text-right truncate" title={uri ?? ""}>
                {uri ?? "—"}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-muted-foreground">User</dt>
              <dd className="font-mono">{user ?? "—"}</dd>
            </div>
            {error && (
              <div className="text-[11px] text-red-700/80 dark:text-red-300/80 mt-2 pt-2 border-t border-red-500/20 break-words">
                <span className="font-medium">Error: </span>
                <span className="font-mono">{error}</span>
              </div>
            )}
            {!offline && (
              <div className="flex justify-end mt-2 pt-2 border-t">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onInit}
                  disabled={initPending || initDisabled}
                  className="gap-1.5 h-7 text-xs"
                >
                  {initPending ? (
                    <RefreshCw className="h-3 w-3 animate-spin" />
                  ) : (
                    <Zap className="h-3 w-3" />
                  )}
                  {initPending ? "Initializing…" : "Init schema"}
                </Button>
              </div>
            )}
            {offline && (
              <div className="text-[11px] text-red-700/80 dark:text-red-300/80 mt-2 pt-2 border-t border-red-500/20">
                Start Neo4j: <code className="font-mono">docker compose up -d neo4j</code>
              </div>
            )}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
