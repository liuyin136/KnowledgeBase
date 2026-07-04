"use client";

/**
 * DashboardView — system health + quick-start cards + recent activity.
 * Frontend_Workflow_Mapping v1.1 §3 (Dashboard).
 *
 * Server state: TanStack Query ("dashboard").
 * Local state: none beyond the seed mutation.
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
} from "lucide-react";

import { api, APIError } from "@/lib/api-client";
import { useUIStore } from "@/store/use-ui-store";
import { ViewHeader, ViewBody } from "@/components/rag/shared/view-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

// ─── Types (typed inline since dashboard returns a loose shape) ─────────────

interface DashboardStats {
  experiments: { total: number; completed: number; failed: number };
  documents: number;
  chunks: number;
  searches: number;
  memories: number;
  carts: number;
}

interface RecentExperiment {
  id: string;
  description: string;
  embeddingApproach: string;
  chunkMethod: string;
  status: string;
  totalChunks: number;
  totalTimeMs: number;
  sourceFile: string | null;
  createdAt: string;
}

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
  recentExperiments: RecentExperiment[];
  recentSearches: RecentSearch[];
  system: {
    embeddingModel: string;
    embeddingDim: number;
    stack: string;
    v1Scope: string;
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
  key: keyof Omit<DashboardStats, "experiments"> | "experimentsTotal" | "experimentsCompleted" | "experimentsFailed";
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  subLabel: (s: DashboardStats) => string;
  value: (s: DashboardStats) => number;
}

const STAT_META: StatMeta[] = [
  { key: "experimentsTotal", label: "Experiments", icon: FlaskConical, value: (s) => s.experiments.total, subLabel: (s) => `${s.experiments.completed} done · ${s.experiments.failed} failed` },
  { key: "documents", label: "Documents", icon: FileText, value: (s) => s.documents, subLabel: () => "uploaded source files" },
  { key: "chunks", label: "Chunks", icon: Boxes, value: (s) => s.chunks, subLabel: () => "embedded children" },
  { key: "searches", label: "Searches", icon: SearchIcon, value: (s) => s.searches, subLabel: () => "hybrid runs" },
  { key: "memories", label: "Memories", icon: Brain, value: (s) => s.memories, subLabel: () => "curated hits" },
  { key: "carts", label: "Memory Carts", icon: ShoppingCart, value: (s) => s.carts, subLabel: () => "collections" },
];

const QUICK_START = [
  { key: "ingest", title: "Ingest", desc: "Upload a document, pick a chunking + embedding config, and watch per-chunk metadata stream in.", icon: Upload },
  { key: "search", title: "Hybrid Search", desc: "Run vector + BM25 retrieval with manual or adaptive alpha fusion and optional reranker.", icon: SearchIcon },
  { key: "memory", title: "Memory Cart", desc: "Curate search hits into named carts for evaluation across experiments.", icon: ShoppingCart },
  { key: "experiments", title: "Experiments", desc: "Inspect every ingest / search run with full observability metadata.", icon: FlaskConical },
] as const;

// ─── Component ──────────────────────────────────────────────────────────────

export function DashboardView() {
  const setView = useUIStore((s) => s.setView);
  const setActiveExperiment = useUIStore((s) => s.setActiveExperiment);
  const qc = useQueryClient();

  const { data, isLoading, isError, error, refetch } = useQuery<DashboardData>({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  const seedMutation = useMutation({
    mutationFn: api.seed,
    onSuccess: (res) => {
      toast.success(`Seeded ${res.created} sample document${res.created === 1 ? "" : "s"}${res.skipped.length ? ` · ${res.skipped.length} already existed` : ""}`);
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (err) => {
      const msg = err instanceof APIError ? err.message : "Failed to seed sample documents";
      toast.error(msg);
    },
  });

  const stats = data?.stats;
  const isEmpty =
    !!stats &&
    stats.experiments.total === 0 &&
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
          <Button
            variant="outline"
            size="sm"
            onClick={() => seedMutation.mutate()}
            disabled={seedMutation.isPending}
          >
            <Sparkles className="h-4 w-4" />
            {seedMutation.isPending ? "Seeding…" : "Seed sample docs"}
          </Button>
        }
      />
      <ViewBody className="space-y-8">
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

        {/* Empty state */}
        {isEmpty && !isLoading && (
          <Card className="border-dashed">
            <CardContent className="py-12 flex flex-col items-center text-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Sparkles className="h-7 w-7" />
              </div>
              <div className="space-y-1">
                <h2 className="text-lg font-semibold">Welcome to RAG Lab v1</h2>
                <p className="text-sm text-muted-foreground max-w-md">
                  Your local-first RAG experimentation platform is empty. Seed a few sample documents to explore ingest,
                  hybrid search, and per-chunk observability in seconds.
                </p>
              </div>
              <Button onClick={() => seedMutation.mutate()} disabled={seedMutation.isPending}>
                <Sparkles className="h-4 w-4" />
                {seedMutation.isPending ? "Seeding…" : "Seed sample documents"}
              </Button>
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
                <FlaskConical className="h-4 w-4" /> Recent Experiments
              </h2>
              <Button variant="ghost" size="sm" onClick={() => setView("experiments")}>
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
                    No experiments yet. Start by <button className="text-primary hover:underline" onClick={() => setView("ingest")}>ingesting a document</button>.
                  </div>
                ) : (
                  <ul className="divide-y max-h-80 overflow-y-auto thin-scroll">
                    {data!.recentExperiments.slice(0, 5).map((exp) => {
                      const tone = statusTone(exp.status);
                      return (
                        <li key={exp.id}>
                          <button
                            type="button"
                            onClick={() => {
                              setActiveExperiment(exp.id);
                              setView("experiments");
                            }}
                            className="w-full text-left px-4 py-3 hover:bg-accent/50 transition-colors flex items-center gap-3"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="text-sm font-medium truncate">{truncate(exp.description, 60)}</div>
                              <div className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-2 flex-wrap">
                                <span className="font-mono">{exp.embeddingApproach}</span>
                                <span>·</span>
                                <span>{exp.chunkMethod}</span>
                                <span>·</span>
                                <span>{exp.totalChunks} chunks</span>
                                {exp.sourceFile && (
                                  <>
                                    <span>·</span>
                                    <span className="truncate">{exp.sourceFile}</span>
                                  </>
                                )}
                              </div>
                            </div>
                            <div className="flex flex-col items-end gap-1 shrink-0">
                              <Badge variant="outline" className={tone.className}>
                                {exp.status === "completed" && <CheckCircle2 className="h-3 w-3" />}
                                {exp.status === "failed" && <XCircle className="h-3 w-3" />}
                                {tone.label}
                              </Badge>
                              <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                                <Clock className="h-2.5 w-2.5" />
                                {timeAgo(exp.createdAt)}
                              </span>
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
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
