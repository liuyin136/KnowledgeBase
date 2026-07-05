"use client";

/**
 * DocumentsView (repurposed from ExperimentsView per redesign plan).
 * The "document" functionality is purely to display all uploaded, ingested, chunked files.
 * Uses the working :Knowledge source_file grouping (Ingest documents list logic).
 * Three local modes: "list" | "detail" | "compare".
 *
 *   • list    — documents by source_file from :Knowledge (the only working Cypher path).
 *   • detail  — show associated :Knowledge and :KnowledgeChunk for the document.
 *   • compare — side-by-side for two documents.
 *
 * Note: "experiment" concept removed as unnecessary; experiment_id kept internally for linking runs if needed.
 * Active "document" uses the former activeExperimentId (repurposed).
 */

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { DocumentTextResponse } from "@/lib/rag/types";
import { formatDistanceToNow } from "date-fns";
import { api, isBackendOffline } from "@/lib/api-client";
import type { ChunkMetadata } from "@/lib/rag/types";
import { ViewHeader, ViewBody } from "@/components/rag/shared/view-header";
import { BackendOffline } from "@/components/rag/shared/backend-offline";
import { MarkdownEditor, MarkdownRender } from "@/components/rag/shared/markdown-editor";
import { useUIStore } from "@/store/use-ui-store";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { toast } from "sonner";
import {
  ArrowLeft,
  FlaskConical,
  RefreshCw,
  Clock,
  AlertCircle,
  Eye,
  Boxes,
  Layers,
  Gauge,
  FileText,
  Hash,
  Timer,
  Settings2,
  GitCompareArrows,
  Inbox,
  CheckCircle2,
  XCircle,
  Loader2,
  CircleDashed,
  Save,
  FileCode2,
  Info,
  Play,
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────────────
// Old Experiment interface removed (concept and node deleted per redesign).
// Now using document/source_file based data from :Knowledge.

// Chunks endpoint returns text + parentSourceFile in addition to ChunkMetadata.
interface ChunkRow extends ChunkMetadata {
  text: string;
  parentSourceFile: string;
}

type Mode = "list" | "detail" | "compare";

// ─── Helpers ─────────────────────────────────────────────────────────────────
function relativeTime(d: string | Date | null | undefined): string {
  if (!d) return "—";
  try {
    return formatDistanceToNow(new Date(d), { addSuffix: true });
  } catch {
    return "—";
  }
}

function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function isSearchExp(e: Experiment): boolean {
  return e.embeddingApproach === "Query";
}

function statusBadge(status: ExperimentStatus) {
  const map: Record<ExperimentStatus, { cls: string; icon: React.ReactNode; label: string }> = {
    completed: {
      cls: "border-transparent bg-primary/15 text-primary",
      icon: <CheckCircle2 className="h-3 w-3" />,
      label: "completed",
    },
    failed: {
      cls: "border-transparent bg-destructive/15 text-destructive",
      icon: <XCircle className="h-3 w-3" />,
      label: "failed",
    },
    running: {
      cls: "border-transparent bg-amber-500/15 text-amber-600 dark:text-amber-400",
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
      label: "running",
    },
    pending: {
      cls: "border-transparent bg-slate-500/15 text-slate-600 dark:text-slate-300",
      icon: <CircleDashed className="h-3 w-3" />,
      label: "pending",
    },
  };
  const s = map[status] ?? map.pending;
  return (
    <Badge variant="outline" className={cn("gap-1 text-[10px] font-medium", s.cls)}>
      {s.icon}
      {s.label}
    </Badge>
  );
}

function approachBadge(approach: string) {
  if (approach === "Query") {
    return <Badge variant="secondary" className="text-[10px]">Query</Badge>;
  }
  if (approach === "LongText") {
    return <Badge variant="default" className="text-[10px]">LongText</Badge>;
  }
  if (approach === "ChildChunk") {
    return <Badge className="text-[10px] bg-primary/85">ChildChunk</Badge>;
  }
  return <Badge variant="outline" className="text-[10px]">{approach}</Badge>;
}

function chunkMethodBadge(method: string) {
  if (method === "N/A" || !method) return <span className="text-xs text-muted-foreground">N/A</span>;
  return <Badge variant="outline" className="text-[10px]">{method}</Badge>;
}

// ─── Stat card (observability) ──────────────────────────────────────────────
function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  mono,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: React.ReactNode;
  hint?: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-card p-3 flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className={cn("text-sm font-medium", mono && "font-mono text-xs")}>{value}</div>
      {hint && <div className="text-[10px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

// ─── Observability Panel ────────────────────────────────────────────────────
function ObservabilityPanel({ exp, chunks }: { exp: Experiment; chunks?: ChunkRow[] }) {
  const totalChunkingMs = chunks?.reduce((s, c) => s + (c.chunkingTimeMs || 0), 0);
  const totalEmbeddingMs = chunks?.reduce((s, c) => s + (c.embeddingTimeMs || 0), 0);
  const search = isSearchExp(exp);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
      <StatCard icon={Boxes} label="Total chunks" value={fmtNum(exp.totalChunks)} mono />
      <StatCard
        icon={Hash}
        label="Avg tokens / chunk"
        value={fmtNum(exp.avgTokensPerChunk, 1)}
        mono
      />
      <StatCard icon={Timer} label="Total time" value={fmtMs(exp.totalTimeMs)} mono />
      <StatCard icon={Gauge} label="Status" value={statusBadge(exp.status)} />
      <StatCard icon={Layers} label="Embedding" value={approachBadge(exp.embeddingApproach)} />
      <StatCard icon={Layers} label="Chunk method" value={chunkMethodBadge(exp.chunkMethod)} />
      <StatCard icon={Settings2} label="Adv option" value={exp.advOption || "None"} mono />
      <StatCard
        icon={FileText}
        label="Source file"
        value={
          <span className="truncate block max-w-full" title={exp.sourceFile ?? ""}>
            {exp.sourceFile ?? "—"}
          </span>
        }
      />
      {chunks && (
        <>
          <StatCard icon={Timer} label="Σ Chunking ms" value={fmtMs(totalChunkingMs)} mono />
          <StatCard icon={Timer} label="Σ Embedding ms" value={fmtMs(totalEmbeddingMs)} mono />
        </>
      )}
      {search && (
        <>
          <StatCard
            icon={Settings2}
            label="Hybrid α"
            value={exp.hybridAlpha != null ? exp.hybridAlpha.toFixed(2) : "—"}
            mono
            hint={exp.autoTuneWeights ? "auto-tuned" : "manual"}
          />
          <StatCard
            icon={Settings2}
            label="BM25"
            value={exp.useBm25 ? "on" : "off"}
          />
          <StatCard
            icon={Settings2}
            label="Reranker"
            value={exp.useReranker ? "on" : "off"}
          />
          <StatCard icon={Hash} label="topK vector" value={fmtNum(exp.topKVector)} mono />
          <StatCard icon={Hash} label="topN rerank" value={fmtNum(exp.topNRerank)} mono />
          <StatCard
            icon={Settings2}
            label="Parent context"
            value={fmtNum(exp.parentContextLevels)}
            mono
          />
          {exp.autoTuneWeights && (
            <StatCard
              icon={Gauge}
              label="Best α (sweep)"
              value={exp.bestAlpha != null ? exp.bestAlpha.toFixed(2) : "—"}
              mono
            />
          )}
          {exp.rawQuery && (
            <StatCard
              icon={FileText}
              label="Raw query"
              value={
                <span className="text-xs line-clamp-2" title={exp.rawQuery}>
                  {exp.rawQuery}
                </span>
              }
            />
          )}
        </>
      )}
    </div>
  );
}

// ─── Chunk Inspector Sheet ──────────────────────────────────────────────────
function ChunkInspectorSheet({
  chunk,
  open,
  onOpenChange,
}: {
  chunk: ChunkRow | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  if (!chunk) return null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-lg overflow-y-auto thin-scroll">
        <SheetHeader>
          <SheetTitle className="text-base">Chunk inspector</SheetTitle>
          <SheetDescription className="text-xs">
            chunkId: <span className="font-mono">{chunk.chunkId}</span>
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6 space-y-4 text-sm">
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {(chunk as any).nodeType === 'knowledge' || (chunk as any).node_type === 'knowledge' ? 'Full :Knowledge text (document)' : ' :KnowledgeChunk text'}
            </div>
            <div className="rounded-md bg-muted/50 p-2.5 text-sm leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto thin-scroll">
              {chunk.text || chunk.textPreview || "(no text available for this row)"}
            </div>
          </div>
          <Separator />
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            <MetaCell label="Chunk index" value={fmtNum(chunk.chunkIndex)} mono />
            <MetaCell label="Method" value={chunk.chunkMethod} />
            <MetaCell label="Embedding" value={chunk.embeddingMethod} />
            <MetaCell label="Tokens" value={fmtNum(chunk.tokenCount)} mono />
            <MetaCell label="Chunking ms" value={fmtMs(chunk.chunkingTimeMs)} mono />
            <MetaCell label="Embedding ms" value={fmtMs(chunk.embeddingTimeMs)} mono />
            <MetaCell
              label="Char range"
              value={
                chunk.charStart != null && chunk.charEnd != null
                  ? `${chunk.charStart}–${chunk.charEnd}`
                  : "—"
              }
              mono
            />
            <MetaCell label="Section" value={chunk.section ?? "—"} />
          </div>
          <div className="rounded-md border p-2 text-xs">
            <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">
              Parent source file
            </div>
            <div className="font-mono break-all">{chunk.parentSourceFile || (chunk as any).parentDocId || "—"}</div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function MetaCell({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-md border p-2">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={cn("text-sm mt-0.5", mono && "font-mono text-xs")}>{value}</div>
    </div>
  );
}

// ─── Chunk Browser (detail mode) ────────────────────────────────────────────
function ChunkBrowser({ experimentId }: { experimentId: string }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["experiment", experimentId, "chunks"],
    queryFn: () => api.documents.chunks(experimentId), // now by source_file for Documents page (redesign)
  });
  const [active, setActive] = React.useState<ChunkRow | null>(null);
  const [open, setOpen] = React.useState(false);

  const chunks = ((data?.items ?? []) as ChunkRow[]);
  React.useEffect(() => { if (data && typeof window !== "undefined") console.debug("[obs:experiment-chunks]", { exp: experimentId, total: data.total, nodeTypes: (data.items ?? []).slice(0,3).map((c: any) => c.nodeType || c.node_type) }); }, [data]);

  const openRow = (c: ChunkRow) => {
    setActive(c);
    setOpen(true);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Boxes className="h-4 w-4 text-primary" />
          Chunk Browser
        </CardTitle>
        <CardDescription className="text-xs">
          {chunks.length} chunk{chunks.length === 1 ? "" : "s"} · click a row to inspect
          {chunks.some((c: any) => (c.nodeType || c.node_type) === 'knowledge') && (
            <span className="ml-2 text-primary"> (includes full ingested parent :Knowledge — first row is usually the complete document; click to view)</span>
          )}
        </CardDescription>
        <CardAction>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => refetch()} aria-label="Refresh chunks">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4" /> Failed to load chunks.
          </div>
        ) : chunks.length === 0 ? (
          <div className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground">
            No chunks recorded for this document.
          </div>
        ) : (
          <div className="rounded-md border max-h-96 overflow-y-auto thin-scroll">
            <Table>
              <TableHeader className="sticky top-0 bg-background z-10">
                <TableRow>
                  <TableHead className="w-[50px]">#</TableHead>
                  <TableHead className="w-[110px]">Method</TableHead>
                  <TableHead className="w-[110px]">Embedding</TableHead>
                  <TableHead className="w-[70px] text-right">Tokens</TableHead>
                  <TableHead className="w-[80px] text-right">Chunk ms</TableHead>
                  <TableHead className="w-[80px] text-right">Embed ms</TableHead>
                  <TableHead className="w-[110px]">Section</TableHead>
                  <TableHead className="min-w-[260px]">Preview</TableHead>
                  <TableHead className="w-[40px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {chunks.map((c, idx) => {
                  const isFullDoc = idx === 0 && ((c as any).nodeType || (c as any).node_type || "").includes("knowledge");
                  return (
                  <TableRow
                    key={c.chunkId}
                    className={`group cursor-pointer ${isFullDoc ? "bg-primary/5 font-medium" : ""}`}
                    onClick={() => openRow(c)}
                  >
                    <TableCell className="font-mono text-xs">{c.chunkIndex}</TableCell>
                    <TableCell>{chunkMethodBadge(c.chunkMethod)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px]">{c.embeddingMethod}</Badge>
                      { (c as any).nodeType && (
                        <Badge variant="secondary" className="ml-1 text-[9px]">{(c as any).nodeType}</Badge>
                      )}
                      {isFullDoc && <Badge className="ml-1 text-[9px] bg-primary">FULL DOC</Badge>}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{fmtNum(c.tokenCount)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{fmtMs(c.chunkingTimeMs)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{fmtMs(c.embeddingTimeMs)}</TableCell>
                    <TableCell className="text-[10px] text-muted-foreground truncate max-w-[110px]" title={c.section ?? ""}>
                      {c.section ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground line-clamp-2 max-w-[280px]" title={c.text || c.textPreview}>
                      {(c as any).nodeType === 'knowledge' || (c as any).node_type === 'knowledge' 
                        ? (c.text || c.textPreview || '').slice(0, 200) 
                        : c.textPreview}
                    </TableCell>
                    <TableCell>
                      <Eye className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                    </TableCell>
                  </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
      <ChunkInspectorSheet chunk={active} open={open} onOpenChange={setOpen} />
    </Card>
  );
}

// ─── Source Document (reconstructed from chunks, with MD editor) ────────────
/**
 * SourceDocumentSection — v1.2 requirement #6.
 *
 * The Experiment node only has the `sourceFile` filename, not the full text.
 * We reconstruct the document by concatenating chunk texts (sorted by
 * chunkIndex) and present it in a Tabs view:
 *   - "Rendered": react-markdown preview (read-only).
 *   - "Raw":      MDXEditor with toolbar (editable). A "Save as new document"
 *                 button POSTs the edited text as a new Knowledge document
 *                 (non-destructive — the original run's chunks are
 *                 untouched). The researcher can then re-run ingest on the
 *                 edited source from the Ingest view.
 *
 * Backend-offline (HTTP 503) → shared <BackendOffline/> component.
 */
function SourceDocumentSection({
  experimentId,
  sourceFile,
  documentData,
}: {
  experimentId: string;
  sourceFile?: string | null;
  documentData?: any;
}) {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["experiment", experimentId, "chunks"],
    queryFn: () => api.documents.chunks(experimentId), // now by source_file for Documents page (redesign)
  });

  const chunks = ((data?.items ?? []) as ChunkRow[]).slice().sort(
    (a, b) => (a.chunkIndex ?? 0) - (b.chunkIndex ?? 0),
  );

  // Reconstruct the document for this document.
  // Strongly prefer full text from the backend document ( :Knowledge ) if provided, or from chunks.
  const reconstructed = React.useMemo(() => {
    // Prefer full from documentData (backend retrieved :knowledge)
    const docIngested = documentData?.ingested?.text;
    if (docIngested && docIngested.length > 30) {
      return docIngested;
    }
    if (!chunks.length) return "";

    // 1. Any row that came from a :Knowledge ...
    const knowledgeRows = chunks.filter((c: any) =>
      (c.nodeType || c.node_type || "").includes("knowledge") ||
      (c.embeddingMethod || "").includes("LongText")
    );
    const bestKnowledge = knowledgeRows
      .map((c) => c.text || c.textPreview || "")
      .filter((t: string) => t.length > 30)
      .sort((a: string, b: string) => b.length - a.length)[0];

    if (bestKnowledge) {
      return bestKnowledge;
    }

    // 2. Longest ...
    const longest = [...chunks]
      .map((c) => c.text || c.textPreview || "")
      .filter((t: string) => t.length > 30)
      .sort((a: string, b: string) => b.length - a.length)[0];

    if (longest) return longest;

    // 3. Classic ...
    return chunks
      .map((c) => c.text ?? c.textPreview ?? "")
      .filter((t: string) => t.length > 0)
      .join("\n\n");
  }, [chunks, documentData]);

  const [mode, setMode] = React.useState<"rendered" | "raw">("rendered");
  const [edited, setEdited] = React.useState<string>("");
  const [hasEdits, setHasEdits] = React.useState(false);

  // Seed the editor with the reconstructed text whenever it changes
  // (e.g. first load, or refetch). Only when the user hasn't started editing.
  React.useEffect(() => {
    if (!hasEdits) setEdited(reconstructed);
  }, [reconstructed, hasEdits]);

  const saveMut = useMutation({
    mutationFn: (text: string) =>
      api.documents.create({
        filename: `${sourceFile ?? "document"} (edited-${Date.now().toString(36)})`,
        text,
        contentType: "text/markdown",
      }),
    onSuccess: (res) => {
      toast.success("Saved as new document", {
        description: `Created "${sourceFile ?? "document"} (edited)" — re-run ingest from the Ingest view to test the modified source.`,
      });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      setHasEdits(false);
      void res;
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : "Failed to save document";
      toast.error("Save failed", { description: msg });
    },
  });

  const handleEditorChange = (v: string) => {
    setEdited(v);
    setHasEdits(v !== reconstructed);
  };

  const charCount = edited.length;
  const chunkCount = chunks.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileCode2 className="h-4 w-4 text-primary" />
          Source Document
        </CardTitle>
        <CardDescription className="text-xs flex flex-wrap items-center gap-x-2 gap-y-1">
          <span>
            Document content for this document (pulled from :Knowledge rows with matching source_file via /chunks or document).
            Reconstructed / full text from <span className="font-mono">{chunkCount}</span> row{chunkCount === 1 ? "" : "s"}.
          </span>
          <span aria-hidden>·</span>
          <span className="font-mono">{charCount.toLocaleString()} chars</span>
          {sourceFile && (
            <>
              <span aria-hidden>·</span>
              <span className="text-muted-foreground truncate max-w-[260px]" title={sourceFile}>
                original: {sourceFile}
              </span>
            </>
          )}
        </CardDescription>
        <CardAction>
          <Tabs value={mode} onValueChange={(v) => setMode(v as "rendered" | "raw")}>
            <TabsList className="h-7">
              <TabsTrigger value="rendered" className="text-xs h-5 px-2.5">Rendered</TabsTrigger>
              <TabsTrigger value="raw" className="text-xs h-5 px-2.5">Raw</TabsTrigger>
            </TabsList>
          </Tabs>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Loading */}
        {isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        )}

        {/* Backend offline */}
        {!isLoading && isError && isBackendOffline(error) && (
          <BackendOffline
            onRetry={() => refetch()}
            message="The FastAPI backend is not reachable, so the document's chunks cannot be loaded. Start the Docker stack (`docker compose up -d`) and retry."
          />
        )}

        {/* Generic error */}
        {!isLoading && isError && !isBackendOffline(error) && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Failed to load chunks</AlertTitle>
            <AlertDescription className="flex items-center justify-between gap-3">
              <span className="text-xs">
                {error instanceof Error ? error.message : "Unknown error"}
              </span>
              <Button size="sm" variant="outline" onClick={() => refetch()}>
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* Empty */}
        {!isLoading && !isError && chunkCount === 0 && (
          <div className="rounded-md border border-dashed p-8 text-center">
            <Inbox className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              No chunks recorded for this document.
            </p>
          </div>
        )}

        {/* Rendered view */}
        {!isLoading && !isError && chunkCount > 0 && mode === "rendered" && (
          <div className="rounded-md border bg-background p-4 max-h-[55vh] overflow-y-auto thin-scroll">
            <MarkdownRender value={reconstructed} />
          </div>
        )}

        {/* Raw / editable view */}
        {!isLoading && !isError && chunkCount > 0 && mode === "raw" && (
          <>
            <Alert className="border-primary/30 bg-primary/5">
              <Info className="h-4 w-4 text-primary" />
              <AlertDescription className="text-xs text-foreground/80">
                Editing creates a <strong>new</strong> document record only.
                Historical :Knowledge / :KnowledgeChunk for this document (and their run id if any) are never mutated.
                Re-ingest will produce fresh nodes. Original run data stays intact.
              </AlertDescription>
            </Alert>
            <MarkdownEditor
              value={edited}
              onChange={handleEditorChange}
              placeholder="Edit the reconstructed markdown source…"
              ariaLabel="Reconstructed source markdown editor"
              className="min-h-[280px]"
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-muted-foreground">
                {hasEdits ? (
                  <span className="text-primary">● Unsaved changes</span>
                ) : (
                  <span>No changes</span>
                )}
                <span className="mx-2" aria-hidden>·</span>
                <span className="font-mono">{charCount.toLocaleString()} chars</span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!hasEdits || saveMut.isPending}
                  onClick={() => {
                    setEdited(reconstructed);
                    setHasEdits(false);
                  }}
                >
                  Reset
                </Button>
                <Button
                  size="sm"
                  disabled={!hasEdits || saveMut.isPending}
                  onClick={() => saveMut.mutate(edited)}
                  className="gap-1.5"
                >
                  {saveMut.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5" />
                  )}
                  Save as new document
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Original / Raw Uploaded :Knowledge (new for visibility of pre-ingest) ─
function OriginalDocumentSection({ sourceFile, experimentId, documentData }: { sourceFile?: string | null; experimentId?: string; documentData?: any }) {
  // If documentData pre-fetched in parent (DetailMode), use it (avoids double fetch).
  // Otherwise, fetch here.
  let doc = documentData;
  let isLoading = false;
  let isError = false;
  let refetch = () => {};

  if (!documentData && experimentId) {
    const docQ = useQuery({
      queryKey: ["experiment", experimentId, "document"],
      queryFn: () => api.documents.getText(experimentId, "any"), // source_file based for document display
      enabled: !!experimentId,
    });
    doc = docQ.data;
    isLoading = docQ.isLoading;
    isError = docQ.isError;
    refetch = () => docQ.refetch();
  }

  if (!experimentId) return null;

  // Prefer the ingested full :Knowledge text (tied to source_file), fallback to raw upload :Knowledge
  const ingestedText = doc?.ingested?.text;
  const originalText = doc?.original?.text;
  const primaryText = ingestedText || originalText || "";
  const isIngested = !!ingestedText;

  const [mode, setMode] = React.useState<"rendered" | "raw">("rendered");

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8">
          <Skeleton className="h-40 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !primaryText) {
    return (
      <Card>
        <CardContent className="py-4">
          <div className="text-xs text-destructive">
            Failed to load document document from backend (/experiments/{experimentId}/document).
            <button onClick={() => refetch()} className="underline ml-1">Retry</button>
          </div>
          <div className="text-xs text-muted-foreground mt-2">
            Ensure backend retrieves :Knowledge records (original Upload or source_file-linked parent) with full text.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4 text-primary" />
          Source Document for this document
        </CardTitle>
        <CardDescription className="text-xs">
          {isIngested
            ? "Ingested full :Knowledge (parent document text for this document_id, via backend)"
            : "Raw uploaded :Knowledge (pre-ingest Upload node)"}
          {doc?.ingested?.embeddingMethod && <span className="ml-2 font-mono">({doc.ingested.embeddingMethod})</span>}
          {doc?.original?.embeddingMethod && !isIngested && <span className="ml-2 font-mono">({doc.original.embeddingMethod})</span>}
        </CardDescription>
        <CardAction>
          <Tabs value={mode} onValueChange={(v) => setMode(v as "rendered" | "raw")}>
            <TabsList className="h-7">
              <TabsTrigger value="rendered" className="text-xs h-5 px-2.5">Rendered</TabsTrigger>
              <TabsTrigger value="raw" className="text-xs h-5 px-2.5">Raw</TabsTrigger>
            </TabsList>
          </Tabs>
        </CardAction>
      </CardHeader>
      <CardContent>
        {mode === "rendered" ? (
          <div className="rounded-md border bg-background p-4 max-h-[40vh] overflow-y-auto thin-scroll">
            <MarkdownRender value={primaryText} />
          </div>
        ) : (
          <pre className="rounded-md border bg-muted/30 p-3 text-xs whitespace-pre-wrap break-words font-mono max-h-[40vh] overflow-y-auto thin-scroll">{primaryText}</pre>
        )}
        <div className="mt-2 text-[10px] text-muted-foreground">
          {primaryText.length.toLocaleString()} chars · source: <span className="font-mono">{sourceFile}</span>
          {doc?.ingested && <span className="ml-2">(from :Knowledge tied to document)</span>}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Detail Mode ────────────────────────────────────────────────────────────
function DetailMode({
  experimentId,
  onBack,
  onCompareWith,
}: {
  experimentId: string;
  onBack: () => void;
  onCompareWith: (otherId: string) => void;
}) {
  const { data: exp, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => api.documents.getText(experimentId, "any"), // fallback to text for document info
  });
  // observation (browser): neo4j Experiment + linked Knowledge records shown in Experiments view
  React.useEffect(() => { if (exp && typeof window !== "undefined") console.debug("[obs:experiments-exp]", { id: exp.id, status: exp.status, chunks_via_doc: (exp as any).document }); }, [exp]);

  // Fetch the document ( :knowledge records ) once here for the detail, so child components
  // can receive pre-fetched data. Prioritizes frontend seeing the full :knowledge text.
  const docQ = useQuery({
    queryKey: ["experiment", experimentId, "document"],
    queryFn: () => api.documents.getText(experimentId, "any"), // source_file based for document display
    enabled: !!experimentId,
  });
  const experimentDocument = docQ.data;

  const [pickerOpen, setPickerOpen] = React.useState(false);
  const [otherId, setOtherId] = React.useState<string>("");

  const { data: listData } = useQuery({
    queryKey: ["documents", "list", { page: 1, pageSize: 100 }],
    queryFn: () => api.documents.list({ page: 1, pageSize: 100 }),
    enabled: pickerOpen,
  });
  const candidates = (listData?.items ?? []).filter(
    (e: any) => e.id !== experimentId
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-32" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !exp) {
    return (
      <Card>
        <CardContent className="pt-6 space-y-3">
          {isBackendOffline(error) ? (
            <BackendOffline
              title="Backend offline"
              message="The FastAPI backend is not reachable, so this document's metadata cannot be loaded. Start the Docker stack (`docker compose up -d`) and retry."
              onRetry={() => refetch()}
            />
          ) : (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" /> Failed to load document.
            </div>
          )}
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onBack}>← Back</Button>
            <Button variant="outline" size="sm" onClick={() => refetch()}>Retry</Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-1">
          <ArrowLeft className="h-4 w-4" /> Back to list
        </Button>
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              // Re-ingest action: navigate to Ingest + pre-select source (config user can match from exp metadata)
              const sf = (exp as Experiment).sourceFile;
              if (sf) {
                // We can't deeply prefill without extra store; select doc + instruct
                // For strong UX we set active + switch view; user sees the doc in list
                // A minimal enhancement: we can also store a pendingSource hint
                useUIStore.getState().setView("ingest");
                // After switch the user can pick the matching filename from Documents list
                toast.info(`Switched to Ingest. Select "${sf}" to re-run with similar settings.`);
              }
            }}
            className="gap-1.5"
          >
            <Play className="h-3.5 w-3.5" /> Re-ingest this source
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              const sf = (exp as Experiment).sourceFile;
              useUIStore.getState().setView("ingest");
              toast.info(`In Ingest view: pick "${sf}", set Embedding Approach = ChildChunk to run child-chunk variant. New nodes will be created (original run data untouched).`);
            }}
            className="gap-1.5"
          >
            <Layers className="h-3.5 w-3.5" /> Re-ingest as ChildChunk
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPickerOpen(true)} className="gap-1.5">
            <GitCompareArrows className="h-3.5 w-3.5" /> Compare with…
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FlaskConical className="h-4 w-4 text-primary" />
            <span className="truncate">{exp.description}</span>
          </CardTitle>
          <CardDescription className="text-xs flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-mono">{exp.id}</span>
            <span aria-hidden>·</span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" /> Created {relativeTime(exp.createdAt)}
            </span>
            <span aria-hidden>·</span>
            <span>Updated {relativeTime(exp.updatedAt)}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {exp.status === "failed" && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>
                Document run failed
                {exp.errorCode && <span className="font-mono ml-1">({exp.errorCode})</span>}
              </AlertTitle>
              <AlertDescription>{exp.errorMessage ?? "No error message provided."}</AlertDescription>
            </Alert>
          )}
          <div>
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
              Document Info (source_file based)
            </h3>
            <p className="text-sm">Chunks and knowledge records for this document. (Observability panel for run metadata hidden in document mode.)</p>
          </div>
        </CardContent>
      </Card>

      <ChunkBrowser experimentId={experimentId} />

      {/* Document source info simplified for :Knowledge based display */}
      <p className="text-xs text-muted-foreground">Full document text and source reconstruction available via document detail or Ingest. Chunks shown above from :Knowledge/:KnowledgeChunk by source_file.</p>

      {/* Compare-with picker */}
      <ComparePickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        candidates={candidates}
        otherId={otherId}
        setOtherId={setOtherId}
        onConfirm={() => {
          if (otherId) {
            setPickerOpen(false);
            onCompareWith(otherId);
          }
        }}
      />
    </div>
  );
}

function ComparePickerDialog({
  open,
  onOpenChange,
  candidates,
  otherId,
  setOtherId,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  candidates: any[];
  otherId: string;
  setOtherId: (v: string) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Compare with…</DialogTitle>
          <DialogDescription>Pick another document to compare side-by-side.</DialogDescription>
        </DialogHeader>
        <Select value={otherId} onValueChange={setOtherId}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select a document" />
          </SelectTrigger>
          <SelectContent>
            {candidates.length === 0 ? (
              <SelectItem value="__none" disabled>No other documents</SelectItem>
            ) : (
              candidates.map((e) => (
                <SelectItem key={e.id} value={e.id}>
                  {e.filename || (e.description ? e.description.slice(0, 60) : '') || e.id}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" size="sm">Cancel</Button>
          </DialogClose>
          <Button size="sm" disabled={!otherId || otherId === "__none"} onClick={onConfirm}>
            Compare
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Compare Mode ───────────────────────────────────────────────────────────
function CompareMode({
  ids,
  onBack,
}: {
  ids: [string, string];
  onBack: () => void;
}) {
  const q1 = useQuery({
    queryKey: ["experiment", ids[0]],
    queryFn: () => api.documents.getText(ids[0], "any"),
  });
  const q2 = useQuery({
    queryKey: ["experiment", ids[1]],
    queryFn: () => api.documents.getText(ids[1], "any"),
  });
  const c1 = useQuery({
    queryKey: ["experiment", ids[0], "chunks"],
    queryFn: () => api.documents.chunks(ids[0]),
  });
  const c2 = useQuery({
    queryKey: ["experiment", ids[1], "chunks"],
    queryFn: () => api.documents.chunks(ids[1]),
  });

  const a = q1.data as Experiment | undefined;
  const b = q2.data as Experiment | undefined;
  const chunksA = (c1.data?.items ?? []) as ChunkRow[];
  const chunksB = (c2.data?.items ?? []) as ChunkRow[];

  const loading = q1.isLoading || q2.isLoading;
  const error = q1.isError || q2.isError;

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-32" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !a || !b) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> Failed to load one or both documents.
          </div>
          <Button variant="outline" size="sm" className="mt-3" onClick={onBack}>← Back</Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <Button variant="ghost" size="sm" onClick={onBack} className="gap-1">
          <ArrowLeft className="h-4 w-4" /> Back to list
        </Button>
        <Badge variant="secondary" className="gap-1 text-xs">
          <GitCompareArrows className="h-3 w-3" /> Comparing 2 documents
        </Badge>
      </div>

      {/* Side-by-side stat panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CompareExperimentColumn exp={a} label="A" chunks={chunksA} />
        <CompareExperimentColumn exp={b} label="B" chunks={chunksB} />
      </div>

      {/* Comparison table */}
      <ComparisonTable a={a} b={b} chunksA={chunksA} chunksB={chunksB} />

      {/* Bar comparison */}
      <BarComparison a={a} b={b} chunksA={chunksA} chunksB={chunksB} />

      <p className="text-xs text-muted-foreground italic">
        Comparison helps you see how changing one factor (embedding approach OR chunk method) affects retrieval metadata.
      </p>
    </div>
  );
}

function CompareExperimentColumn({
  exp,
  label,
  chunks,
}: {
  exp: Experiment;
  label: string;
  chunks: ChunkRow[];
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Badge variant="default" className="text-[10px]">{label}</Badge>
          <CardTitle className="text-base truncate">{exp.description}</CardTitle>
        </div>
        <CardDescription className="text-xs font-mono">{exp.id}</CardDescription>
      </CardHeader>
      <CardContent>
        <ObservabilityPanel exp={exp} chunks={chunks} />
      </CardContent>
    </Card>
  );
}

// ─── Comparison Table ───────────────────────────────────────────────────────
function ComparisonTable({
  a,
  b,
  chunksA,
  chunksB,
}: {
  a: Experiment;
  b: Experiment;
  chunksA: ChunkRow[];
  chunksB: ChunkRow[];
}) {
  const totalChunkingA = chunksA.reduce((s, c) => s + (c.chunkingTimeMs || 0), 0);
  const totalChunkingB = chunksB.reduce((s, c) => s + (c.chunkingTimeMs || 0), 0);
  const totalEmbedA = chunksA.reduce((s, c) => s + (c.embeddingTimeMs || 0), 0);
  const totalEmbedB = chunksB.reduce((s, c) => s + (c.embeddingTimeMs || 0), 0);

  type Row = {
    metric: string;
    a: React.ReactNode;
    b: React.ReactNode;
    delta?: { value: string; positive: boolean } | null;
  };

  const numDelta = (av: number | null | undefined, bv: number | null | undefined, fmt: (n: number) => string) => {
    if (av == null || bv == null) return null;
    const d = bv - av;
    const sign = d > 0 ? "+" : "";
    return { value: `${sign}${fmt(d)}`, positive: d >= 0 };
  };

  const rows: Row[] = [
    {
      metric: "Embedding approach",
      a: approachBadge(a.embeddingApproach),
      b: approachBadge(b.embeddingApproach),
    },
    {
      metric: "Chunk method",
      a: chunkMethodBadge(a.chunkMethod),
      b: chunkMethodBadge(b.chunkMethod),
    },
    {
      metric: "Total chunks",
      a: fmtNum(a.totalChunks),
      b: fmtNum(b.totalChunks),
      delta: numDelta(a.totalChunks, b.totalChunks, (n) => fmtNum(n)),
    },
    {
      metric: "Avg tokens / chunk",
      a: fmtNum(a.avgTokensPerChunk, 1),
      b: fmtNum(b.avgTokensPerChunk, 1),
      delta: numDelta(a.avgTokensPerChunk, b.avgTokensPerChunk, (n) => n.toFixed(1)),
    },
    {
      metric: "Total time (ms)",
      a: fmtMs(a.totalTimeMs),
      b: fmtMs(b.totalTimeMs),
      delta: numDelta(a.totalTimeMs, b.totalTimeMs, (n) => `${Math.round(n)}ms`),
    },
    {
      metric: "Σ Chunking time (ms)",
      a: chunksA.length ? fmtMs(totalChunkingA) : "—",
      b: chunksB.length ? fmtMs(totalChunkingB) : "—",
      delta: chunksA.length && chunksB.length ? numDelta(totalChunkingA, totalChunkingB, (n) => `${Math.round(n)}ms`) : null,
    },
    {
      metric: "Σ Embedding time (ms)",
      a: chunksA.length ? fmtMs(totalEmbedA) : "—",
      b: chunksB.length ? fmtMs(totalEmbedB) : "—",
      delta: chunksA.length && chunksB.length ? numDelta(totalEmbedA, totalEmbedB, (n) => `${Math.round(n)}ms`) : null,
    },
    {
      metric: "Status",
      a: statusBadge(a.status),
      b: statusBadge(b.status),
    },
    {
      metric: "Source file",
      a: <span className="text-xs truncate block max-w-[180px]" title={a.sourceFile ?? ""}>{a.sourceFile ?? "—"}</span>,
      b: <span className="text-xs truncate block max-w-[180px]" title={b.sourceFile ?? ""}>{b.sourceFile ?? "—"}</span>,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Metric Comparison</CardTitle>
        <CardDescription className="text-xs">
          Δ = B − A. <span className="text-primary">teal</span> for positive, muted for negative.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[180px]">Metric</TableHead>
                <TableHead className="w-[20%]">Document A</TableHead>
                <TableHead className="w-[20%]">Document B</TableHead>
                <TableHead className="w-[80px] text-right">Δ</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.metric}>
                  <TableCell className="text-xs font-medium text-muted-foreground">{r.metric}</TableCell>
                  <TableCell>{r.a}</TableCell>
                  <TableCell>{r.b}</TableCell>
                  <TableCell className="text-right">
                    {r.delta ? (
                      <span
                        className={cn(
                          "font-mono text-xs",
                          r.delta.positive ? "text-primary" : "text-muted-foreground"
                        )}
                      >
                        {r.delta.value}
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Bar Comparison ─────────────────────────────────────────────────────────
function BarComparison({
  a,
  b,
  chunksA,
  chunksB,
}: {
  a: Experiment;
  b: Experiment;
  chunksA: ChunkRow[];
  chunksB: ChunkRow[];
}) {
  if (chunksA.length === 0 && chunksB.length === 0) return null;

  const maxChunks = Math.max(chunksA.length, chunksB.length, 1);
  const maxTokens = Math.max(a.avgTokensPerChunk, b.avgTokensPerChunk, 1);

  const Bar = ({
    label,
    valueA,
    valueB,
    fmtVal,
  }: {
    label: string;
    valueA: number;
    valueB: number;
    fmtVal: (n: number) => string;
  }) => {
    const max = Math.max(valueA, valueB, 1);
    return (
      <div className="space-y-1.5">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="space-y-1">
          <BarRow label="A" value={valueA} max={max} fmtVal={fmtVal} />
          <BarRow label="B" value={valueB} max={max} fmtVal={fmtVal} />
        </div>
      </div>
    );
  };

  const BarRow = ({
    label,
    value,
    max,
    fmtVal,
  }: {
    label: string;
    value: number;
    max: number;
    fmtVal: (n: number) => string;
  }) => (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-mono w-3 text-muted-foreground">{label}</span>
      <div className="flex-1 h-3 rounded bg-muted overflow-hidden">
        <div
          className={cn(
            "h-full rounded transition-all",
            label === "A" ? "bg-primary/70" : "bg-primary"
          )}
          style={{ width: `${Math.max(2, (value / max) * 100)}%` }}
        />
      </div>
      <span className="text-[10px] font-mono w-14 text-right">{fmtVal(value)}</span>
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Distribution</CardTitle>
        <CardDescription className="text-xs">
          Quick visual comparison of chunk count and average tokens.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Bar
          label="Chunk count"
          valueA={chunksA.length}
          valueB={chunksB.length}
          fmtVal={(n) => fmtNum(n)}
        />
        <Bar
          label="Avg tokens / chunk"
          valueA={a.avgTokensPerChunk}
          valueB={b.avgTokensPerChunk}
          fmtVal={(n) => fmtNum(n, 1)}
        />
        <div className="text-[10px] text-muted-foreground">
          Max chunks (A: {chunksA.length}, B: {chunksB.length}) · Max avg tokens: {fmtNum(maxTokens, 1)}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── List Mode ──────────────────────────────────────────────────────────────
function ExperimentTable({
  kind,
  onOpen,
  compareIds,
  setCompareIds,
}: {
  kind: "all" | "ingest" | "search";
  onOpen: (id: string) => void;
  compareIds: string[];
  setCompareIds: (ids: string[]) => void;
}) {
  const [page, setPage] = React.useState(1);
  const pageSize = 15;
  React.useEffect(() => {
    setPage(1);
  }, [kind]);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["documents", "list", { page, pageSize }],
    queryFn: () =>
      api.documents.list({
        page,
        pageSize,
      }),
  });
  // observation (browser): documents list from neo4j :Knowledge (the working path)
  React.useEffect(() => { if (data && typeof window !== "undefined") console.debug("[obs:experiments-list]", { total: data.total, kind, sampleIds: (data.items ?? []).slice(0,2).map((e: any) => e.id) }); }, [data]);

  const items = (data?.items ?? []) as any[]; // now documents from working :Knowledge list
  const total = data?.total ?? 0;
  const hasMore = data?.hasMore ?? false;

  const toggleCompare = (id: string, checked: boolean) => {
    if (checked) {
      const next = [...compareIds, id].slice(-2);
      setCompareIds(next);
    } else {
      setCompareIds(compareIds.filter((x) => x !== id));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Documents</CardTitle>
        <CardDescription className="text-xs">
          {total} document{total === 1 ? "" : "s"} (source_file from :Knowledge) · page {page}
        </CardDescription>
        <CardAction>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => refetch()}
            aria-label="Refresh experiments"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded-md border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[40px]">
                  <span className="sr-only">Select for comparison</span>
                </TableHead>
                <TableHead className="min-w-[200px]">Filename (source_file)</TableHead>
                <TableHead className="w-[100px]">Embedding</TableHead>
                <TableHead className="w-[120px]">Kinds</TableHead>
                <TableHead className="w-[70px] text-right">Chunks</TableHead>
                <TableHead className="w-[80px] text-right">Size</TableHead>
                <TableHead className="w-[80px] text-right">Time</TableHead>
                <TableHead className="w-[90px]"> </TableHead>
                <TableHead className="w-[140px]"> </TableHead>
                <TableHead className="w-[110px]">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={10}>
                      <Skeleton className="h-9 w-full" />
                    </TableCell>
                  </TableRow>
                ))
              ) : isError ? (
                <TableRow>
                  <TableCell colSpan={10}>
                    {isBackendOffline(error) ? (
                      <div className="py-2">
                        <BackendOffline
                          compact
                          onRetry={() => refetch()}
                          message="The FastAPI backend is not reachable, so experiments cannot be loaded."
                        />
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 py-2 text-xs text-destructive">
                        <AlertCircle className="h-4 w-4" /> Failed to load documents.
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={10}>
                    <div className="py-10 text-center">
                      <Inbox className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                      <p className="text-sm text-muted-foreground">
                        No documents yet. Upload in Ingest view to create :Knowledge records.
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                items.map((e) => {
                  const checked = compareIds.includes(e.id);
                  const compareDisabled = !checked && compareIds.length >= 2;
                  return (
                    <TableRow
                      key={e.id}
                      className="group cursor-pointer hover:bg-muted/50"
                      onClick={() => onOpen(e.id)}
                    >
                      <TableCell onClick={(ev) => ev.stopPropagation()}>
                        <Checkbox
                          checked={checked}
                          disabled={compareDisabled}
                          onCheckedChange={(v) => toggleCompare(e.id, Boolean(v))}
                          aria-label={`Select ${e.id} for comparison`}
                        />
                      </TableCell>
                      <TableCell className="max-w-[280px]">
                        <div className="text-sm line-clamp-1">{e.filename || e.description}</div>
                        <div className="text-[10px] font-mono text-muted-foreground">{e.id}</div>
                      </TableCell>
                      <TableCell>{e.representativeEmbeddingMethod || approachBadge(e.embeddingApproach)}</TableCell>
                      <TableCell>{chunkMethodBadge(e.chunkMethod)}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{fmtNum(e.totalChunks || e.chunk_count)}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{fmtNum(e.avgTokensPerChunk, 1)}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{fmtMs(e.totalTimeMs)}</TableCell>
                      <TableCell>{statusBadge(e.status)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground truncate max-w-[140px]" title={e.filename || e.sourceFile || ""}>
                        {e.filename || e.sourceFile || "—"}
                      </TableCell>
                      <TableCell className="text-[10px] text-muted-foreground whitespace-nowrap">
                        {relativeTime(e.createdAt)}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        {total > pageSize && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
            </span>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Prev
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!hasMore}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Main View ──────────────────────────────────────────────────────────────
export function DocumentsView() {
  const { activeDocumentId, setActiveDocument } = useUIStore(); // document focus (ex-activeExperimentId)
  const [mode, setMode] = React.useState<Mode>("list");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [compareIds, setCompareIds] = React.useState<string[]>([]);
  const [comparePair, setComparePair] = React.useState<[string, string] | null>(null);
  const [kind, setKind] = React.useState<"all" | "ingest" | "search">("all");

  // Auto-open detail if activeDocumentId is set when the view mounts.
  React.useEffect(() => {
    if (activeDocumentId) {
      setSelectedId(activeDocumentId);
      setMode("detail");
    }
  }, [activeDocumentId]);

  const openDetail = (id: string) => {
    setSelectedId(id);
    setMode("detail");
  };

  const backToList = () => {
    setSelectedId(null);
    setMode("list");
    // Clear active so re-entering the view starts at the list.
    if (activeDocumentId) setActiveDocument(null);
  };

  const startCompare = (ids: [string, string]) => {
    setComparePair(ids);
    setMode("compare");
  };

  const backFromCompare = () => {
    setComparePair(null);
    setMode("list");
    setCompareIds([]);
    if (activeDocumentId) setActiveDocument(null);
  };

  return (
    <>
      <ViewHeader
        title="Documents"
        description="All uploaded, ingested & chunked files (display of :Knowledge records)"
        icon={FileText}
        actions={
          mode === "list" && (
            <ToggleGroup
              type="single"
              value={kind}
              onValueChange={(v) => v && setKind(v as "all" | "ingest" | "search")}
              className="rounded-md border bg-background"
              size="sm"
            >
              <ToggleGroupItem value="all" className="text-xs h-7 px-3">All</ToggleGroupItem>
              <ToggleGroupItem value="ingest" className="text-xs h-7 px-3">Ingest</ToggleGroupItem>
              <ToggleGroupItem value="search" className="text-xs h-7 px-3">Search</ToggleGroupItem>
            </ToggleGroup>
          )
        }
      />
      <ViewBody>
        {mode === "list" && (
          <div className="space-y-3">
            <ExperimentTable
              kind={kind}
              onOpen={openDetail}
              compareIds={compareIds}
              setCompareIds={setCompareIds}
            />
            {compareIds.length === 2 && (
              <div className="sticky bottom-4 z-20">
                <Button
                  className="w-full shadow-lg gap-2"
                  onClick={() => startCompare([compareIds[0], compareIds[1]])}
                >
                  <GitCompareArrows className="h-4 w-4" />
                  Compare selected ({compareIds.length} documents) →
                </Button>
              </div>
            )}
          </div>
        )}

        {mode === "detail" && selectedId && (
          <DetailMode
            experimentId={selectedId}
            onBack={backToList}
            onCompareWith={(otherId) => startCompare([selectedId, otherId])}
          />
        )}

        {mode === "compare" && comparePair && (
          <CompareMode ids={comparePair} onBack={backFromCompare} />
        )}
      </ViewBody>
    </>
  );
}
