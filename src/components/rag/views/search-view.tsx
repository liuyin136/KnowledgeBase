"use client";

/**
 * Hybrid Search view (Frontend_Workflow_Mapping v1.1 §3)
 *
 * Layout: two-column on lg (left = query + SearchConfig, right = results),
 * stacked on mobile. Past searches history in a collapsible below.
 *
 * Server state → TanStack Query (experiments, history, carts, job poll).
 * Client state → useState (rawQuery, config, jobId, selectedChunkIds, etc.).
 */

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  Sparkles,
  RotateCcw,
  ShoppingCart,
  X,
  Loader2,
  History,
  ChevronDown,
  ChevronRight,
  Plus,
  FileText,
  Info,
  Layers,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";

import { api, APIError } from "@/lib/api-client";
import type {
  SearchConfig,
  SearchResult,
  SearchResponse,
  JobStatusResponse,
  Memory,
} from "@/lib/rag/types";
import { useUIStore } from "@/store/use-ui-store";
import { ViewHeader, ViewBody } from "@/components/rag/shared/view-header";

import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";

// ─── Defaults (mirror SearchConfigSchema defaults) ──────────────────────────

const DEFAULT_CONFIG: SearchConfig = {
  hybridAlpha: 0.7,
  useBm25: true,
  topKVector: 10,
  topNRerank: 5,
  useReranker: false,
  parentContextLevels: 1,
  autoTuneWeights: false,
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtMs(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1) return `${ms.toFixed(2)}ms`;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "—";
  const diff = Date.now() - then;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

function deriveStatus(job: JobStatusResponse | undefined, useReranker: boolean): string {
  if (!job) return "Starting…";
  if (job.status === "queued") return "Queued…";
  if (job.status === "completed") return "Done";
  if (job.status === "failed") return "Failed";
  // running — derive from the latest event stage if present
  const last = job.events[job.events.length - 1];
  if (last?.stage === "embedding") return "Embedding query…";
  if (last?.stage === "persisting") return "Persisting memories…";
  // fall back to a progress-based heuristic
  if (job.progress < 33) return "Embedding query…";
  if (useReranker && job.progress >= 80) return "Reranking…";
  return "Searching…";
}

// ─── Small presentational components ────────────────────────────────────────

function RankBadge({ rank }: { rank: number }) {
  const top3 = rank <= 3;
  return (
    <Badge
      variant={top3 ? "default" : "secondary"}
      className={top3 ? "font-mono" : "font-mono bg-muted text-muted-foreground"}
    >
      #{rank}
    </Badge>
  );
}

function ScoreBadge({
  label,
  value,
  prominent,
}: {
  label: string;
  value: number | null;
  prominent?: boolean;
}) {
  const text = value == null ? "—" : value.toFixed(4);
  return (
    <Badge
      variant={prominent ? "default" : "outline"}
      className={`font-mono text-[10px] gap-1 ${prominent ? "" : "text-muted-foreground"}`}
      title={`${label}: ${value == null ? "n/a" : value}`}
    >
      <span className="opacity-70">{label}</span>
      <span>{text}</span>
    </Badge>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/20 p-2">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className="font-mono text-xs mt-0.5 break-all">{value}</div>
    </div>
  );
}

function TimingCell({ label, ms }: { label: string; ms: number }) {
  return (
    <div className="rounded-md border bg-muted/30 p-2">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className="font-mono text-xs mt-0.5">{fmtMs(ms)}</div>
    </div>
  );
}

// ─── SearchConfigPanel ──────────────────────────────────────────────────────

function SearchConfigPanel({
  config,
  onChange,
}: {
  config: SearchConfig;
  onChange: (next: SearchConfig) => void;
}) {
  const update = <K extends keyof SearchConfig>(k: K, v: SearchConfig[K]) =>
    onChange({ ...config, [k]: v });
  const alpha = config.hybridAlpha;
  const beta = 1 - alpha;

  return (
    <Card className="p-4 gap-4">
      <CardTitle className="text-sm flex items-center gap-2 px-0">
        <Layers className="h-4 w-4 text-primary" /> Search configuration
      </CardTitle>

      {/* Adaptive auto-tune — visually prominent (teal-tinted when active) */}
      <div
        className={`rounded-lg border p-3 transition-colors ${
          config.autoTuneWeights
            ? "border-primary/60 bg-primary/5"
            : "border-border"
        }`}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <Sparkles className="h-4 w-4 text-primary shrink-0" />
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <Label htmlFor="auto-tune" className="text-sm font-medium cursor-pointer">
                  Adaptive α/β sweep
                </Label>
                {config.autoTuneWeights && (
                  <Badge
                    className="bg-primary/15 text-primary border-primary/30"
                    variant="outline"
                  >
                    ADAPTIVE
                  </Badge>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Tests α∈&#123;0.1..0.9&#125;, picks best top-1 similarity
              </p>
            </div>
          </div>
          <Switch
            id="auto-tune"
            checked={config.autoTuneWeights}
            onCheckedChange={(v) => update("autoTuneWeights", v)}
            aria-label="Adaptive alpha beta sweep"
          />
        </div>
      </div>

      {/* Hybrid alpha */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-sm">Hybrid α (vector weight)</Label>
          <span className="font-mono text-xs text-muted-foreground">
            {config.autoTuneWeights
              ? "auto"
              : `α=${alpha.toFixed(2)} · β=${beta.toFixed(2)}`}
          </span>
        </div>
        <Slider
          min={0}
          max={1}
          step={0.05}
          value={[alpha]}
          onValueChange={(v) => update("hybridAlpha", v[0])}
          disabled={config.autoTuneWeights}
          aria-label="Hybrid alpha"
        />
        {config.autoTuneWeights && (
          <p className="text-[11px] text-primary/80 flex items-center gap-1">
            <Info className="h-3 w-3" /> Adaptive sweep active — alpha will be
            auto-selected
          </p>
        )}
      </div>

      {/* topKVector */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-sm">Top-K (vector candidates)</Label>
          <span className="font-mono text-xs text-muted-foreground">
            {config.topKVector}
          </span>
        </div>
        <Slider
          min={1}
          max={50}
          step={1}
          value={[config.topKVector]}
          onValueChange={(v) => update("topKVector", v[0])}
          aria-label="Top K vector candidates"
        />
      </div>

      {/* parentContextLevels */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-sm">Parent context levels</Label>
          <span className="font-mono text-xs text-muted-foreground">
            {config.parentContextLevels}
          </span>
        </div>
        <Slider
          min={0}
          max={3}
          step={1}
          value={[config.parentContextLevels]}
          onValueChange={(v) => update("parentContextLevels", v[0])}
          aria-label="Parent context levels"
        />
      </div>

      {/* BM25 */}
      <div className="flex items-start justify-between gap-3 rounded-lg border p-3">
        <div className="min-w-0">
          <Label htmlFor="bm25-switch" className="text-sm font-medium cursor-pointer">
            BM25 lexical
          </Label>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Adds Okapi BM25 sparse retrieval
          </p>
        </div>
        <Switch
          id="bm25-switch"
          checked={config.useBm25}
          onCheckedChange={(v) => update("useBm25", v)}
          aria-label="BM25 lexical"
        />
      </div>

      {/* Reranker */}
      <div className="space-y-3 rounded-lg border p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Label htmlFor="rerank-switch" className="text-sm font-medium cursor-pointer">
              LLM Reranker
            </Label>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Re-scores top-N via z-ai LLM
            </p>
          </div>
          <Switch
            id="rerank-switch"
            checked={config.useReranker}
            onCheckedChange={(v) => update("useReranker", v)}
            aria-label="LLM reranker"
          />
        </div>
        <div
          className={`space-y-2 transition-opacity ${
            config.useReranker ? "" : "opacity-50 pointer-events-none"
          }`}
        >
          <div className="flex items-center justify-between">
            <Label className="text-xs">Top-N rerank</Label>
            <span className="font-mono text-xs text-muted-foreground">
              {config.topNRerank}
            </span>
          </div>
          <Slider
            min={0}
            max={20}
            step={1}
            value={[config.topNRerank]}
            onValueChange={(v) => update("topNRerank", v[0])}
            disabled={!config.useReranker}
            aria-label="Top N rerank"
          />
        </div>
      </div>
    </Card>
  );
}

// ─── Metadata summary card ──────────────────────────────────────────────────

function MetadataSummary({ result }: { result: SearchResponse }) {
  const m = result.metadata;
  const c = m.config;
  return (
    <Card className="p-4 gap-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="text-sm font-medium flex items-center gap-2">
            <Info className="h-4 w-4 text-primary" /> Search metadata
          </div>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            {result.results.length} result{result.results.length === 1 ? "" : "s"} · total{" "}
            <span className="font-mono">{fmtMs(m.totalSearchTimeMs)}</span>
          </p>
        </div>
        {m.bestAlpha != null && (
          <Badge
            className="bg-primary/15 text-primary border-primary/30"
            variant="outline"
          >
            <Sparkles className="h-3 w-3" /> Adaptive α = {m.bestAlpha.toFixed(2)}
          </Badge>
        )}
      </div>

      {/* Timing breakdown */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <TimingCell label="Query embed" ms={m.queryEmbeddingTimeMs} />
        <TimingCell label="Vector search" ms={m.vectorSearchTimeMs} />
        <TimingCell label="BM25" ms={m.bm25SearchTimeMs} />
        <TimingCell label="Rerank" ms={m.rerankTimeMs} />
      </div>

      {/* Candidates flow */}
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="font-mono">{m.candidatesBeforeRerank}</span>
        <span>candidates</span>
        <ChevronRight className="h-3 w-3" />
        <span className="font-mono">{m.resultsAfterRerank}</span>
        <span>after rerank</span>
      </div>

      {/* Config snapshot */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="font-mono text-[10px]">
          α={c.hybridAlpha.toFixed(2)}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px]">
          β={(1 - c.hybridAlpha).toFixed(2)}
        </Badge>
        <Badge
          variant="outline"
          className={`font-mono text-[10px] ${
            c.useBm25 ? "border-primary/40 text-primary" : ""
          }`}
        >
          BM25 {c.useBm25 ? "on" : "off"}
        </Badge>
        <Badge
          variant="outline"
          className={`font-mono text-[10px] ${
            c.useReranker ? "border-primary/40 text-primary" : ""
          }`}
        >
          Rerank {c.useReranker ? "on" : "off"}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px]">
          topK={c.topKVector}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px]">
          topN={c.topNRerank}
        </Badge>
        {c.autoTuneWeights && (
          <Badge
            className="bg-primary/15 text-primary border-primary/30"
            variant="outline"
          >
            ADAPTIVE
          </Badge>
        )}
      </div>
    </Card>
  );
}

// ─── ResultCard ─────────────────────────────────────────────────────────────

function ResultCard({
  result,
  selected,
  onToggleSelected,
  onOpen,
}: {
  result: SearchResult;
  selected: boolean;
  onToggleSelected: () => void;
  onOpen: () => void;
}) {
  return (
    <Card
      className={`p-4 gap-3 transition-colors ${
        selected ? "border-primary/50 bg-primary/[0.03]" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <RankBadge rank={result.rank} />
          {result.section && (
            <Badge variant="outline" className="text-[10px] font-mono">
              {result.section}
            </Badge>
          )}
        </div>
        <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer select-none shrink-0">
          <Checkbox
            checked={selected}
            onCheckedChange={onToggleSelected}
            aria-label={`Select result ${result.rank}`}
          />
          Select
        </label>
      </div>

      {/* Score row */}
      <div className="flex flex-wrap items-center gap-1.5">
        <ScoreBadge label="vec" value={result.vectorScore} />
        <ScoreBadge label="bm25" value={result.bm25Score} />
        <ScoreBadge label="fused" value={result.fusedScore} />
        <ScoreBadge label="rerank" value={result.rerankerScore} />
        <ScoreBadge label="final" value={result.finalScore} prominent />
        <Badge
          variant="outline"
          className="font-mono text-[10px] text-muted-foreground"
        >
          α={result.alphaUsed.toFixed(2)}·β={result.betaUsed.toFixed(2)}
        </Badge>
      </div>

      {/* Chunk text — clickable to open detail */}
      <button
        type="button"
        onClick={onOpen}
        className="block w-full text-left rounded-md border bg-muted/30 hover:bg-muted/60 hover:border-primary/30 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`Open detail for result ${result.rank}`}
      >
        <ScrollArea className="h-48 w-full">
          <pre className="text-xs font-mono whitespace-pre-wrap break-words p-3 leading-relaxed">
            {result.text}
          </pre>
        </ScrollArea>
      </button>

      {/* Parent context */}
      <div className="rounded-md border border-dashed bg-muted/20 p-2.5">
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground mb-1">
          <FileText className="h-3 w-3" /> Parent context
        </div>
        <div className="text-[11px] font-mono text-muted-foreground truncate">
          {result.parentSourceFile}
        </div>
        <p className="text-xs text-muted-foreground/80 mt-1 line-clamp-2">
          {result.parentTextPreview}
        </p>
      </div>

      {/* Metadata badges */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="font-mono text-[10px]">
          {result.chunkMethod}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px]">
          {result.embeddingMethod}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px]">
          {result.tokenCount} tok
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px]">
          chunk {fmtMs(result.chunkingTimeMs)}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px]">
          embed {fmtMs(result.embeddingTimeMs)}
        </Badge>
      </div>
    </Card>
  );
}

// ─── Main SearchView ────────────────────────────────────────────────────────

export function SearchView() {
  const queryClient = useQueryClient();
  const { activeExperimentId, setActiveExperiment } = useUIStore();

  // ── Local state ──────────────────────────────────────────────────────────
  const [rawQuery, setRawQuery] = useState("");
  const [config, setConfig] = useState<SearchConfig>(DEFAULT_CONFIG);
  const [jobId, setJobId] = useState<string | null>(null);
  const [selectedChunkIds, setSelectedChunkIds] = useState<Set<string>>(
    new Set(),
  );
  const [detailResult, setDetailResult] = useState<SearchResult | null>(null);
  const [cartDialogOpen, setCartDialogOpen] = useState(false);
  const [cartMode, setCartMode] = useState<"new" | "existing">("new");
  const [newCartName, setNewCartName] = useState("");
  const [existingCartId, setExistingCartId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  // ── Queries ──────────────────────────────────────────────────────────────
  const experimentsQuery = useQuery({
    queryKey: ["experiments", "ingest"],
    queryFn: () =>
      api.experiments.list({ page: 1, pageSize: 50, kind: "ingest" }),
  });

  const historyQuery = useQuery({
    queryKey: ["search-history"],
    queryFn: () => api.search.history({ page: 1, pageSize: 10 }),
  });

  const cartsQuery = useQuery({
    queryKey: ["memory-carts"],
    queryFn: () => api.memoryCarts.list(),
  });

  // Job polling — stops cleanly on completed/failed
  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.jobs.get(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "queued" || s === "running" ? 800 : false;
    },
  });

  const job = jobQuery.data;
  const jobStatus = job?.status;
  const isPolling =
    !!jobId && jobStatus !== "completed" && jobStatus !== "failed";
  const searchResult: SearchResponse | null =
    job?.status === "completed" ? job.result : null;
  const searchError: string | null =
    job?.status === "failed" ? job.errorMessage || "Search failed" : null;

  // Invalidate history + dashboard when a search completes; toast on failure
  useEffect(() => {
    if (jobStatus === "completed") {
      queryClient.invalidateQueries({ queryKey: ["search-history"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    }
    if (jobStatus === "failed") {
      toast.error(searchError || "Search failed");
    }
  }, [jobStatus, searchError, queryClient]);

  // ── Start search mutation ────────────────────────────────────────────────
  const startMutation = useMutation({
    mutationFn: (vars: {
      rawQuery: string;
      config: SearchConfig;
      experimentId?: string;
    }) => api.search.start(vars),
    onSuccess: (data) => {
      setJobId(data.jobId);
      setSelectedChunkIds(new Set());
      toast.success("Search queued");
    },
    onError: (err) => {
      const msg = err instanceof APIError ? err.message : "Failed to start search";
      toast.error(msg);
    },
  });

  const handleSearch = () => {
    if (!rawQuery.trim()) {
      toast.error("Please enter a query first");
      return;
    }
    startMutation.mutate({
      rawQuery: rawQuery.trim(),
      config,
      experimentId: activeExperimentId ?? undefined,
    });
  };

  const handleRerun = (run: any) => {
    if (!run?.rawQuery?.trim()) {
      toast.error("Cannot re-run: empty query in history");
      return;
    }
    const nextConfig: SearchConfig = {
      hybridAlpha: run.hybridAlpha,
      useBm25: run.useBm25,
      topKVector: run.topKVector,
      topNRerank: run.topNRerank,
      useReranker: run.useReranker,
      parentContextLevels: run.parentContextLevels,
      autoTuneWeights: run.autoTuneWeights,
    };
    setRawQuery(run.rawQuery);
    setConfig(nextConfig);
    setActiveExperiment(run.experimentId ?? null);
    startMutation.mutate({
      rawQuery: run.rawQuery,
      config: nextConfig,
      experimentId: run.experimentId ?? undefined,
    });
  };

  const toggleSelected = (chunkId: string) => {
    setSelectedChunkIds((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  };

  // ── Add to memory cart mutation ──────────────────────────────────────────
  const addCartMutation = useMutation({
    mutationFn: async (vars: {
      mode: "new" | "existing";
      newCartName: string;
      existingCartId: string | null;
      selectedChunkIds: Set<string>;
      experimentId?: string;
    }) => {
      // 1. Resolve cart id (create if "new")
      let cartId: string;
      if (vars.mode === "new") {
        const name = vars.newCartName.trim() || "Untitled cart";
        const created = await api.memoryCarts.create({ name });
        cartId = created.id;
      } else {
        if (!vars.existingCartId) {
          throw new Error("No existing cart selected");
        }
        cartId = vars.existingCartId;
      }
      // 2. Fetch memories filtered by experimentId; match by chunkId
      const memRes = await api.memories.list({
        page: 1,
        pageSize: 200,
        experimentId: vars.experimentId,
      });
      const matched: string[] = [];
      for (const m of memRes.items as Memory[]) {
        if (m.chunkId && vars.selectedChunkIds.has(m.chunkId)) {
          matched.push(m.id);
        }
      }
      if (matched.length === 0) {
        throw new Error(
          "No matching memories found — try re-running the search first",
        );
      }
      // 3. Patch the cart with matched memory ids
      await api.memoryCarts.patch(cartId, { addMemoryIds: matched });
      return { cartId, matched: matched.length };
    },
    onSuccess: ({ matched }) => {
      toast.success(
        `Added ${matched} ${matched === 1 ? "memory" : "memories"} to cart`,
      );
      setCartDialogOpen(false);
      setSelectedChunkIds(new Set());
      setNewCartName("");
      setExistingCartId(null);
      setCartMode("new");
      queryClient.invalidateQueries({ queryKey: ["memory-carts"] });
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "Failed to add to cart";
      toast.error(msg);
    },
  });

  const handleAddToCart = () => {
    if (selectedChunkIds.size === 0) return;
    if (cartMode === "new" && !newCartName.trim()) {
      toast.error("Enter a cart name");
      return;
    }
    if (cartMode === "existing" && !existingCartId) {
      toast.error("Select an existing cart");
      return;
    }
    addCartMutation.mutate({
      mode: cartMode,
      newCartName,
      existingCartId,
      selectedChunkIds,
      experimentId: activeExperimentId ?? undefined,
    });
  };

  const statusText = deriveStatus(job, config.useReranker);

  // ── Results section ──────────────────────────────────────────────────────
  const renderResults = () => {
    if (startMutation.isPending && !job) {
      return (
        <Card className="p-4 gap-3">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-24 w-full" />
        </Card>
      );
    }
    if (isPolling) {
      return (
        <Card className="p-4 gap-3">
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span>{statusText}</span>
            <span className="font-mono text-[11px] text-muted-foreground ml-auto">
              {job?.progress ?? 0}%
            </span>
          </div>
          <Progress value={job?.progress ?? 0} />
          <p className="text-[11px] text-muted-foreground">
            Polling job <span className="font-mono">{jobId}</span> every 800ms.
          </p>
        </Card>
      );
    }
    if (searchError) {
      return (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Search failed</AlertTitle>
          <AlertDescription>
            {searchError}
            {job?.errorCode && (
              <span className="font-mono text-[10px] block mt-1 opacity-80">
                code: {job.errorCode}
              </span>
            )}
          </AlertDescription>
        </Alert>
      );
    }
    if (!searchResult) {
      return (
        <Card className="p-8 text-center text-sm text-muted-foreground gap-2">
          <Search className="h-8 w-8 mx-auto opacity-40" />
          <div>Run a search to see results here.</div>
          <div className="text-[11px]">
            Tip: enable <span className="text-primary font-medium">Adaptive α/β sweep</span>{" "}
            to auto-tune hybrid weights.
          </div>
        </Card>
      );
    }
    if (searchResult.results.length === 0) {
      return (
        <Card className="p-8 text-center text-sm text-muted-foreground gap-2">
          <Search className="h-8 w-8 mx-auto opacity-40" />
          <div>No results — try a different query or config.</div>
        </Card>
      );
    }
    return (
      <>
        <MetadataSummary result={searchResult} />
        <div className="space-y-3">
          {searchResult.results.map((r) => (
            <ResultCard
              key={`${r.chunkId}-${r.rank}`}
              result={r}
              selected={selectedChunkIds.has(r.chunkId)}
              onToggleSelected={() => toggleSelected(r.chunkId)}
              onOpen={() => setDetailResult(r)}
            />
          ))}
        </div>
      </>
    );
  };

  return (
    <>
      <ViewHeader
        title="Hybrid Search"
        description="Tunable retrieval with parent-child awareness"
        icon={Search}
      />
      <ViewBody className="space-y-6">
        <div className="grid gap-6 lg:grid-cols-[380px_1fr] items-start">
          {/* ── Left column: query + config + button ─────────────────────── */}
          <div className="space-y-4 lg:sticky lg:top-24">
            {/* Query input + experiment selector */}
            <Card className="p-4 gap-3">
              <CardTitle className="text-sm flex items-center gap-2 px-0">
                <Search className="h-4 w-4 text-primary" /> Query
              </CardTitle>
              <Textarea
                placeholder="Ask anything — e.g. 'How does the orchestrator handle retries?'"
                value={rawQuery}
                onChange={(e) => setRawQuery(e.target.value)}
                className="min-h-[100px] resize-y"
                aria-label="Search query"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    handleSearch();
                  }
                }}
              />
              <div className="space-y-1.5">
                <Label htmlFor="exp-select" className="text-xs text-muted-foreground">
                  Experiment scope
                </Label>
                <Select
                  value={activeExperimentId ?? "__all__"}
                  onValueChange={(v) =>
                    setActiveExperiment(v === "__all__" ? null : v)
                  }
                >
                  <SelectTrigger id="exp-select" className="w-full">
                    <SelectValue placeholder="All experiments" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">All experiments</SelectItem>
                    {experimentsQuery.isLoading && (
                      <SelectItem value="__loading" disabled>
                        Loading…
                      </SelectItem>
                    )}
                    {(experimentsQuery.data?.items ?? []).map((exp: any) => (
                      <SelectItem key={exp.id} value={exp.id}>
                        {exp.description} ({exp.embeddingApproach}/
                        {exp.chunkMethod})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {experimentsQuery.isError && (
                  <p className="text-[11px] text-destructive">
                    Failed to load experiments
                  </p>
                )}
              </div>
            </Card>

            <SearchConfigPanel config={config} onChange={setConfig} />

            <Button
              className="w-full"
              onClick={handleSearch}
              disabled={isPolling || startMutation.isPending}
            >
              {isPolling || startMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Searching…
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" /> Search
                </>
              )}
            </Button>
            <p className="text-[10px] text-muted-foreground text-center -mt-2">
              Tip:{" "}
              <kbd className="font-mono px-1 py-0.5 rounded border bg-muted">
                ⌘/Ctrl
              </kbd>{" "}
              +{" "}
              <kbd className="font-mono px-1 py-0.5 rounded border bg-muted">
                Enter
              </kbd>{" "}
              to search
            </p>
          </div>

          {/* ── Right column: results + action bar ───────────────────────── */}
          <div className="space-y-4 relative min-h-[300px]">
            {renderResults()}

            {/* Sticky multi-select action bar */}
            {selectedChunkIds.size > 0 && (
              <div className="sticky bottom-4 z-20 mt-4">
                <div className="flex items-center gap-2 rounded-lg border bg-background/95 backdrop-blur shadow-md p-2.5">
                  <Badge variant="secondary" className="font-mono">
                    {selectedChunkIds.size} selected
                  </Badge>
                  <div className="flex-1" />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedChunkIds(new Set())}
                  >
                    <X className="h-3.5 w-3.5" /> Clear
                  </Button>
                  <Button size="sm" onClick={() => setCartDialogOpen(true)}>
                    <ShoppingCart className="h-3.5 w-3.5" /> Add to Memory Cart
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Past searches history (collapsible) ─────────────────────────── */}
        <Collapsible open={historyOpen} onOpenChange={setHistoryOpen}>
          <Card className="p-0 gap-0 overflow-hidden">
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-muted/40 transition-colors text-left"
                aria-expanded={historyOpen}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <History className="h-4 w-4 text-primary shrink-0" />
                  <span className="text-sm font-medium">Past searches</span>
                  {historyQuery.data?.total != null && (
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {historyQuery.data.total}
                    </Badge>
                  )}
                </div>
                {historyOpen ? (
                  <ChevronDown className="h-4 w-4 shrink-0" />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0" />
                )}
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="border-t">
                {historyQuery.isLoading ? (
                  <div className="p-4 space-y-2">
                    <Skeleton className="h-6 w-full" />
                    <Skeleton className="h-6 w-full" />
                    <Skeleton className="h-6 w-full" />
                  </div>
                ) : historyQuery.isError ? (
                  <div className="p-4 text-sm text-destructive">
                    Failed to load search history
                  </div>
                ) : (historyQuery.data?.items ?? []).length === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground">
                    No past searches yet.
                  </div>
                ) : (
                  <div className="max-h-96 overflow-y-auto thin-scroll">
                    <Table>
                      <TableHeader className="sticky top-0 bg-card z-10">
                        <TableRow>
                          <TableHead>Query</TableHead>
                          <TableHead>Scope</TableHead>
                          <TableHead>α</TableHead>
                          <TableHead>BM25</TableHead>
                          <TableHead>Rerank</TableHead>
                          <TableHead>Adaptive</TableHead>
                          <TableHead>Best α</TableHead>
                          <TableHead>Results</TableHead>
                          <TableHead>Top</TableHead>
                          <TableHead>Time</TableHead>
                          <TableHead>When</TableHead>
                          <TableHead className="text-right">Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(historyQuery.data?.items ?? []).map((run: any) => (
                          <TableRow
                            key={run.id}
                            className="cursor-pointer"
                            onClick={() => handleRerun(run)}
                          >
                            <TableCell className="max-w-[200px] truncate font-mono text-xs">
                              {run.rawQuery || "(empty)"}
                            </TableCell>
                            <TableCell className="text-xs">
                              {run.experimentId ? (
                                <span className="font-mono text-[10px] text-muted-foreground">
                                  {String(run.experimentId).slice(0, 8)}…
                                </span>
                              ) : (
                                <span className="text-muted-foreground">all</span>
                              )}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {run.hybridAlpha != null
                                ? Number(run.hybridAlpha).toFixed(2)
                                : "—"}
                            </TableCell>
                            <TableCell className="text-xs">
                              {run.useBm25 ? "on" : "off"}
                            </TableCell>
                            <TableCell className="text-xs">
                              {run.useReranker ? "on" : "off"}
                            </TableCell>
                            <TableCell className="text-xs">
                              {run.autoTuneWeights ? "yes" : "no"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {run.bestAlpha != null
                                ? Number(run.bestAlpha).toFixed(2)
                                : "—"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {run.resultCount ?? 0}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {run.topScore != null
                                ? Number(run.topScore).toFixed(4)
                                : "—"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {fmtMs(run.searchTimeMs || 0)}
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground">
                              {relativeTime(run.createdAt)}
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={isPolling || startMutation.isPending}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRerun(run);
                                }}
                              >
                                <RotateCcw className="h-3 w-3" /> Re-run
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </CollapsibleContent>
          </Card>
        </Collapsible>

        {/* ── Result detail sheet ─────────────────────────────────────────── */}
        <Sheet
          open={!!detailResult}
          onOpenChange={(o) => !o && setDetailResult(null)}
        >
          <SheetContent
            side="right"
            className="w-full sm:max-w-lg overflow-y-auto thin-scroll"
          >
            {detailResult && (
              <>
                <SheetHeader>
                  <SheetTitle className="flex items-center gap-2">
                    <RankBadge rank={detailResult.rank} /> Result detail
                  </SheetTitle>
                  <SheetDescription className="font-mono text-[10px]">
                    {detailResult.chunkId}
                  </SheetDescription>
                </SheetHeader>
                <div className="px-4 pb-6 space-y-4">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <ScoreBadge label="vec" value={detailResult.vectorScore} />
                    <ScoreBadge label="bm25" value={detailResult.bm25Score} />
                    <ScoreBadge label="fused" value={detailResult.fusedScore} />
                    <ScoreBadge
                      label="rerank"
                      value={detailResult.rerankerScore}
                    />
                    <ScoreBadge
                      label="final"
                      value={detailResult.finalScore}
                      prominent
                    />
                  </div>
                  <div>
                    <div className="text-[11px] font-medium text-muted-foreground mb-1">
                      Chunk text
                    </div>
                    <ScrollArea className="h-72 w-full rounded-md border">
                      <pre className="text-xs font-mono whitespace-pre-wrap break-words p-3 leading-relaxed">
                        {detailResult.text}
                      </pre>
                    </ScrollArea>
                  </div>
                  <div>
                    <div className="text-[11px] font-medium text-muted-foreground mb-1">
                      Parent context
                    </div>
                    <div className="rounded-md border border-dashed bg-muted/20 p-2.5">
                      <div className="text-[11px] font-mono text-muted-foreground truncate">
                        {detailResult.parentSourceFile}
                      </div>
                      <p className="text-xs text-muted-foreground/80 mt-1">
                        {detailResult.parentTextPreview}
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <MetaRow
                      label="chunkMethod"
                      value={detailResult.chunkMethod}
                    />
                    <MetaRow
                      label="embeddingMethod"
                      value={detailResult.embeddingMethod}
                    />
                    <MetaRow
                      label="tokenCount"
                      value={String(detailResult.tokenCount)}
                    />
                    {detailResult.section && (
                      <MetaRow label="section" value={detailResult.section} />
                    )}
                    <MetaRow
                      label="chunkingTimeMs"
                      value={fmtMs(detailResult.chunkingTimeMs)}
                    />
                    <MetaRow
                      label="embeddingTimeMs"
                      value={fmtMs(detailResult.embeddingTimeMs)}
                    />
                    <MetaRow
                      label="alphaUsed"
                      value={detailResult.alphaUsed.toFixed(4)}
                    />
                    <MetaRow
                      label="betaUsed"
                      value={detailResult.betaUsed.toFixed(4)}
                    />
                    <MetaRow
                      label="experimentId"
                      value={detailResult.experimentId}
                    />
                    <MetaRow
                      label="parentId"
                      value={detailResult.parentId}
                    />
                  </div>
                </div>
              </>
            )}
          </SheetContent>
        </Sheet>

        {/* ── Add to Memory Cart dialog ──────────────────────────────────── */}
        <Dialog open={cartDialogOpen} onOpenChange={setCartDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add to Memory Cart</DialogTitle>
              <DialogDescription>
                {selectedChunkIds.size} selected result
                {selectedChunkIds.size === 1 ? "" : "s"}. Choose a target cart —
                memories are matched by chunk ID.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant={cartMode === "new" ? "default" : "outline"}
                  onClick={() => setCartMode("new")}
                  className="flex-1"
                >
                  <Plus className="h-3.5 w-3.5" /> New cart
                </Button>
                <Button
                  size="sm"
                  variant={cartMode === "existing" ? "default" : "outline"}
                  onClick={() => setCartMode("existing")}
                  className="flex-1"
                >
                  Existing cart
                </Button>
              </div>

              {cartMode === "new" ? (
                <div className="space-y-1.5">
                  <Label htmlFor="cart-name" className="text-xs">
                    Cart name
                  </Label>
                  <Input
                    id="cart-name"
                    placeholder="e.g. RAG eval set Q1"
                    value={newCartName}
                    onChange={(e) => setNewCartName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleAddToCart();
                    }}
                  />
                </div>
              ) : (
                <div className="space-y-1.5">
                  <Label htmlFor="cart-pick" className="text-xs">
                    Choose cart
                  </Label>
                  <Select
                    value={existingCartId ?? "__none__"}
                    onValueChange={(v) =>
                      setExistingCartId(v === "__none__" ? null : v)
                    }
                  >
                    <SelectTrigger id="cart-pick" className="w-full">
                      <SelectValue placeholder="Select a cart" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">— Select a cart —</SelectItem>
                      {(cartsQuery.data?.items ?? []).map((c: any) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.name} ({c.memoryCount})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {cartsQuery.isError && (
                    <p className="text-[11px] text-destructive">
                      Failed to load carts
                    </p>
                  )}
                </div>
              )}

              <p className="text-[11px] text-muted-foreground">
                Memories were created automatically when the search completed.
                We&apos;ll match them by chunk ID against your selection.
              </p>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setCartDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleAddToCart}
                disabled={addCartMutation.isPending}
              >
                {addCartMutation.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                Add {selectedChunkIds.size} to cart
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </ViewBody>
    </>
  );
}
