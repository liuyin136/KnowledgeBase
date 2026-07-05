"use client";

/**
 * IngestView — multi .md file upload + IngestConfig + live per-chunk progress + chunk inspector.
 *
 * Upload redesigned (v1.3+): drag/drop or browse multiple .md only. Uses multipart
 * FormData + api.documents.upload (fixes JSON/multipart binding error).
 * JSON create retained for edit-save flows.
 *
 * Layout: 3-column grid on lg, stacks on mobile.
 * Server state: TanStack Query ("documents", "ingest-status").
 * Local state: selectedDocumentId, job/experiment, inspector + upload staging.
 */

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Upload,
  FileText,
  Trash2,
  Play,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ArrowRight,
  FileUp,
  Layers,
  Database,
  Activity,
  Eye,
  Clock,
  Hash,
} from "lucide-react";

import { api, APIError, isBackendOffline } from "@/lib/api-client";
import { useUIStore } from "@/store/use-ui-store";
import { ViewHeader, ViewBody } from "@/components/rag/shared/view-header";
import { BackendOffline } from "@/components/rag/shared/backend-offline";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import type { IngestConfig, IngestProgressEvent, ChunkMetadata, JobStatusResponse } from "@/lib/rag/types";

// ─── Types for documents (loose API shape) ──────────────────────────────────

interface DocumentItem {
  id: string;
  filename: string;
  contentType: string;
  size: number;       // legacy alias
  sizeBytes?: number; // server returns this
  createdAt: string;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

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
  return new Date(iso).toLocaleDateString();
}

function truncate(text: string, n: number): string {
  if (!text) return "";
  return text.length > n ? text.slice(0, n) + "…" : text;
}

// Color-coded stage badge
function stageTone(stage: IngestProgressEvent["stage"]): string {
  switch (stage) {
    case "chunking":
      return "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300";
    case "embedding":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "persisting":
      return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "done":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "error":
      return "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300";
    default:
      return "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300";
  }
}

function statusTone(status: string): string {
  switch (status) {
    case "completed":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "failed":
      return "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300";
    case "running":
      return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "queued":
    default:
      return "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300";
  }
}

const CHUNK_METHODS = ["Recursive", "Semantic", "Structure-Aware"] as const;

// ─── Main component ─────────────────────────────────────────────────────────

export function IngestView() {
  const qc = useQueryClient();

  // Local state
  const [selectedDocumentId, setSelectedDocumentId] = React.useState<string | null>(null);
  const [embeddingApproach, setEmbeddingApproach] = React.useState<"LongText" | "ChildChunk">("ChildChunk");
  const [chunkMethod, setChunkMethod] = React.useState<(typeof CHUNK_METHODS)[number]>("Recursive");
  const [experimentDescription, setExperimentDescription] = React.useState("");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [experimentId, setExperimentId] = React.useState<string | null>(null);
  const [inspectorChunk, setInspectorChunk] = React.useState<ChunkMetadata | null>(null);
  const [inspectorOpen, setInspectorOpen] = React.useState(false);

  // Start ingest mutation
  const startMutation = useMutation({
    mutationFn: (vars: { documentId: string; config: IngestConfig; experimentDescription?: string }) =>
      api.ingest.start(vars),
    onSuccess: (res) => {
      setJobId(res.jobId);
      setExperimentId(res.experimentId);
      toast.success("Ingestion started");
    },
    onError: (err) => {
      const msg = err instanceof APIError ? err.message : "Failed to start ingestion";
      toast.error(msg);
    },
  });

  // Poll job status while running / queued
  const statusQuery = useQuery<JobStatusResponse>({
    queryKey: ["ingest-status", jobId],
    queryFn: () => api.ingest.status(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const d = query.state.data;
      if (!d) return 1000;
      return d.status === "running" || d.status === "queued" ? 1000 : false;
    },
    refetchOnWindowFocus: false,
  });
  // observation (browser): active ingestion progress (pre-neo4j events; on done will be in experiment neo4j records)
  React.useEffect(() => { if (statusQuery.data && typeof window !== "undefined") console.debug("[obs:ingest-active]", { status: statusQuery.data.status, progress: statusQuery.data.progress, chunks: statusQuery.data.events?.length }); }, [statusQuery.data]);

  // On completion / failure, invalidate downstream queries once
  const lastHandledStatus = React.useRef<string | null>(null);
  React.useEffect(() => {
    const st = statusQuery.data?.status;
    if (!st || st === lastHandledStatus.current) return;
    if (st === "completed" || st === "failed") {
      lastHandledStatus.current = st;
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["experiments"] }); // keep for backend if used
      if (st === "completed") {
        // Also refresh documents count indirectly (chunks come from a new experiment)
        qc.invalidateQueries({ queryKey: ["documents"] });
      }
    }
  }, [statusQuery.data?.status, qc]);

  // ─── Handlers ────────────────────────────────────────────────────────────

  const handleStart = () => {
    if (!selectedDocumentId) {
      toast.error("Please select a document to ingest first.");
      return;
    }
    const config: IngestConfig = {
      embeddingApproach,
      chunkMethod,
      advOption: "None",
    };
    startMutation.mutate({
      documentId: selectedDocumentId,
      config,
      experimentDescription: experimentDescription.trim() || undefined,
    });
  };

  const openInspector = (chunk: ChunkMetadata) => {
    setInspectorChunk(chunk);
    setInspectorOpen(true);
  };

  // Reset progress when user navigates away implicitly via re-mount; we keep
  // jobId local so a refresh clears it. Provide a manual "reset" affordance.
  const resetJob = () => {
    setJobId(null);
    setExperimentId(null);
    lastHandledStatus.current = null;
    qc.removeQueries({ queryKey: ["ingest-status"] });
  };

  const status = statusQuery.data;
  const events = status?.events ?? [];
  const lastEvent = events.length > 0 ? events[events.length - 1] : null;
  const chunkEvents = events.filter((e) => e.chunk) as { chunk: ChunkMetadata; index: number; total: number; progress: number; stage: IngestProgressEvent["stage"]; message?: string }[];

  return (
    <>
      <ViewHeader
        title="Ingest"
        description="Upload multiple .md files, configure chunking + embedding, and watch per-chunk metadata stream in."
        icon={Upload}
      />
      <ViewBody>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ─── Left: Documents ──────────────────────────────────────────── */}
          <div className="space-y-6">
            <UploadDocumentCard onCreated={() => qc.invalidateQueries({ queryKey: ["documents"] })} />
            <DocumentsListCard
              selectedId={selectedDocumentId}
              onSelect={setSelectedDocumentId}
              onDeleted={(id) => {
                if (selectedDocumentId === id) setSelectedDocumentId(null);
                qc.invalidateQueries({ queryKey: ["documents"] });
              }}
            />
          </div>

          {/* ─── Middle: Config + action ──────────────────────────────────── */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Layers className="h-4 w-4 text-primary" />
                  Ingest Configuration
                </CardTitle>
                <CardDescription>
                  Pick an embedding approach and chunking method. This drives the experiment observability.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {/* embeddingApproach */}
                <div className="space-y-2">
                  <Label>Embedding Approach</Label>
                  <RadioGroup
                    value={embeddingApproach}
                    onValueChange={(v) => setEmbeddingApproach(v as "LongText" | "ChildChunk")}
                    className="gap-2"
                  >
                    <label
                      htmlFor="approach-longtext"
                      className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                        embeddingApproach === "LongText"
                          ? "border-primary bg-primary/5"
                          : "hover:bg-accent/50"
                      }`}
                    >
                      <RadioGroupItem value="LongText" id="approach-longtext" className="mt-1" />
                      <div className="min-w-0">
                        <div className="text-sm font-medium">LongText</div>
                        <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
                          Embed the entire document as a single vector. Sliding-window chunking only — chunkMethod is ignored.
                        </p>
                      </div>
                    </label>
                    <label
                      htmlFor="approach-childchunk"
                      className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                        embeddingApproach === "ChildChunk"
                          ? "border-primary bg-primary/5"
                          : "hover:bg-accent/50"
                      }`}
                    >
                      <RadioGroupItem value="ChildChunk" id="approach-childchunk" className="mt-1" />
                      <div className="min-w-0">
                        <div className="text-sm font-medium">ChildChunk</div>
                        <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
                          Chunk the document, then embed each chunk separately. Enables per-chunk observability.
                        </p>
                      </div>
                    </label>
                  </RadioGroup>
                </div>

                {/* chunkMethod */}
                <div className="space-y-2">
                  <Label htmlFor="chunk-method">Chunk Method</Label>
                  <Select
                    value={embeddingApproach === "LongText" ? undefined : chunkMethod}
                    onValueChange={(v) => setChunkMethod(v as (typeof CHUNK_METHODS)[number])}
                    disabled={embeddingApproach === "LongText"}
                  >
                    <SelectTrigger id="chunk-method" className="w-full">
                      <SelectValue
                        placeholder={
                          embeddingApproach === "LongText"
                            ? "LongText uses its own sliding-window chunking"
                            : "Select a chunking method"
                        }
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {CHUNK_METHODS.map((m) => (
                        <SelectItem key={m} value={m}>
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {embeddingApproach === "LongText" && (
                    <p className="text-[11px] text-muted-foreground italic">
                      LongText uses its own sliding-window chunking — chunkMethod is ignored.
                    </p>
                  )}
                </div>

                {/* advOption */}
                <div className="space-y-2">
                  <Label>Advanced Option</Label>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="opacity-60 cursor-not-allowed">
                      None (v1)
                    </Badge>
                    <span className="text-[11px] text-muted-foreground">
                      Late / Agentic chunking deferred to v2.
                    </span>
                  </div>
                </div>

                {/* experimentDescription */}
                <div className="space-y-2">
                  <Label htmlFor="exp-desc">Experiment Description (optional)</Label>
                  <Input
                    id="exp-desc"
                    placeholder="e.g. Recursive vs Structure-Aware on rag-overview.md"
                    value={experimentDescription}
                    onChange={(e) => setExperimentDescription(e.target.value)}
                    maxLength={200}
                  />
                </div>

                {/* Start button */}
                <Button
                  className="w-full"
                  size="lg"
                  onClick={handleStart}
                  disabled={startMutation.isPending || !selectedDocumentId || !!jobId}
                >
                  <Play className="h-4 w-4" />
                  {startMutation.isPending ? "Starting…" : jobId ? "Job running…" : "Start Ingestion"}
                </Button>
                {!selectedDocumentId && (
                  <p className="text-[11px] text-muted-foreground text-center">
                    Select a document from the left to enable ingestion.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* ─── Right: Live progress (only when job active) ──────────────── */}
          <div className="space-y-6">
            {!jobId ? (
              <Card className="border-dashed">
                <CardContent className="py-12 flex flex-col items-center text-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <Activity className="h-6 w-6" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-sm font-semibold">No active ingestion</h3>
                    <p className="text-xs text-muted-foreground max-w-xs">
                      Select a document, configure your ingest options, and press <span className="font-medium">Start Ingestion</span> to see live per-chunk progress here.
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <IngestProgressPanel
                status={status}
                isLoading={statusQuery.isLoading && !status}
                isError={statusQuery.isError}
                experimentId={experimentId}
                lastEvent={lastEvent}
                chunkEvents={chunkEvents}
                onOpenInspector={openInspector}
                onReset={resetJob}
              />
            )}
          </div>
        </div>

        {/* ─── Chunk Inspector Sheet ──────────────────────────────────────── */}
        <Sheet open={inspectorOpen} onOpenChange={(o) => setInspectorOpen(o)}>
          <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto thin-scroll">
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <Eye className="h-4 w-4 text-primary" />
                Chunk Inspector
              </SheetTitle>
              <SheetDescription>
                Full per-chunk metadata. Use this to compare chunking quality across documents.
              </SheetDescription>
            </SheetHeader>
            {inspectorChunk && <ChunkInspector chunk={inspectorChunk} />}
          </SheetContent>
        </Sheet>
      </ViewBody>
    </>
  );
}

// ─── Sub-components ─────────────────────────────────────────────────────────

// ─── Redesigned multi-.md file upload (replaces old paste form) ─────────────

function UploadDocumentCard({ onCreated }: { onCreated: () => void }) {
  const [staged, setStaged] = React.useState<File[]>([]);
  const [isUploading, setIsUploading] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = React.useState(false);

  const isMdFile = (f: File): boolean => {
    const n = (f.name || "").toLowerCase();
    return n.endsWith(".md") || n.endsWith(".markdown");
  };

  const addFiles = (newFiles: File[]) => {
    const valid = newFiles.filter(isMdFile);
    const rejected = newFiles.length - valid.length;
    if (rejected > 0) {
      toast.error(`Only .md files are accepted. Skipped ${rejected}.`);
    }
    if (valid.length === 0) return;

    // Avoid exact dups by name+size (simple)
    setStaged((prev) => {
      const existingKeys = new Set(prev.map((p) => `${p.name}:${p.size}`));
      const toAdd = valid.filter((v) => !existingKeys.has(`${v.name}:${v.size}`));
      return [...prev, ...toAdd];
    });
  };

  const removeStaged = (idx: number) => {
    setStaged((prev) => prev.filter((_, i) => i !== idx));
  };

  const clearStaged = () => setStaged([]);

  // Drag & drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const dropped = Array.from(e.dataTransfer.files || []);
    if (dropped.length) addFiles(dropped);
  };

  // Browse
  const openFileDialog = () => fileInputRef.current?.click();
  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files || []);
    if (selected.length) addFiles(selected);
    // reset input so same file can be picked again later
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // Batch upload via FormData (multipart) to /api/v1/documents.
  // The proxy (backend-client.ts) now correctly forwards multipart without
  // consuming the body via text() first.
  const uploadStaged = async () => {
    if (staged.length === 0) return;
    setIsUploading(true);
    const fd = new FormData();
    // Use "files" (plural) to reliably bind to backend's List[UploadFile] param.
    // Backend also accepts singular "file" for legacy single-file cases.
    staged.forEach((f) => fd.append("files", f));

    try {
      const res = await api.documents.upload(fd);
      const count = res?.ids?.length ?? staged.length;
      toast.success(`Uploaded ${count} document${count === 1 ? "" : "s"}`);
      // Auto-select the last one uploaded for convenience (if present)
      const lastId = res?.ids?.[res.ids.length - 1];
      if (lastId) {
        // Parent will receive via onCreated + we can bubble if needed; here we just clear
      }
      clearStaged();
      onCreated();
    } catch (err) {
      const msg = err instanceof APIError ? err.message : "Failed to upload files";
      toast.error(msg);
    } finally {
      setIsUploading(false);
    }
  };

  const totalBytes = staged.reduce((sum, f) => sum + (f.size || 0), 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileUp className="h-4 w-4 text-primary" />
          Upload Markdown Files
        </CardTitle>
        <CardDescription>
          Drop or select one or more <span className="font-mono">.md</span> files. Only Markdown accepted.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Drop zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={openFileDialog}
          className={`group flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center cursor-pointer transition-colors ${
            isDragOver ? "border-primary bg-primary/5" : "border-muted-foreground/30 hover:border-primary/60 hover:bg-accent/30"
          }`}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              openFileDialog();
            }
          }}
          aria-label="Drop markdown files here or click to browse"
        >
          <Upload className="h-8 w-8 text-muted-foreground mb-2 group-hover:text-primary transition-colors" />
          <div className="text-sm font-medium">Drop .md files here</div>
          <div className="text-[11px] text-muted-foreground">or click to browse (multiple supported)</div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".md,.markdown,text/markdown"
            className="hidden"
            onChange={handleFileInputChange}
          />
        </div>

        {/* Staged files */}
        {staged.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>{staged.length} file{staged.length > 1 ? "s" : ""} ready · {formatBytes(totalBytes)}</span>
              <button className="underline hover:text-foreground" onClick={clearStaged} disabled={isUploading}>
                Clear all
              </button>
            </div>
            <ul className="space-y-1 max-h-40 overflow-y-auto thin-scroll rounded border p-1">
              {staged.map((f, idx) => (
                <li key={`${f.name}-${idx}`} className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent/50">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1 truncate font-mono text-xs">{f.name}</div>
                  <div className="text-[10px] text-muted-foreground tabular-nums">{formatBytes(f.size)}</div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-muted-foreground hover:text-red-600"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeStaged(idx);
                    }}
                    disabled={isUploading}
                    aria-label={`Remove ${f.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Action */}
        <Button
          className="w-full"
          onClick={uploadStaged}
          disabled={isUploading || staged.length === 0}
        >
          <Upload className="h-4 w-4" />
          {isUploading
            ? `Uploading ${staged.length}…`
            : staged.length > 0
              ? `Upload ${staged.length} Markdown File${staged.length > 1 ? "s" : ""}`
              : "Select files to upload"}
        </Button>

        <p className="text-[11px] text-muted-foreground text-center">
          Files are stored as upload placeholders (ready for ingest). Markdown enables Structure-Aware chunking.
        </p>
      </CardContent>
    </Card>
  );
}

function DocumentsListCard({
  selectedId,
  onSelect,
  onDeleted,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDeleted: (id: string) => void;
}) {
  const { data, isLoading, isError, error, refetch } = useQuery<{ items: DocumentItem[]; total: number }>({
    queryKey: ["documents", { page: 1, pageSize: 50 }],
    queryFn: () => api.documents.list({ page: 1, pageSize: 50 }),
  });
  // observation (browser): neo4j Knowledge records shown in ingest documents list
  React.useEffect(() => { if (data && typeof window !== "undefined") console.debug("[obs:ingest-documents]", { total: data.total, sample: data.items?.slice(0,2) }); }, [data]);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.documents.delete(id),
    onSuccess: (_res, id) => {
      toast.success("Document deleted");
      onDeleted(id);
    },
    onError: (err) => {
      const msg = err instanceof APIError ? err.message : "Failed to delete document";
      toast.error(msg);
    },
  });

  const items = data?.items ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4 text-primary" />
          Documents
          {data?.total !== undefined && (
            <Badge variant="secondary" className="ml-1">
              {data.total}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>Select a document to ingest. Upload more .md files above. Click a row to select.</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : isError ? (
          isBackendOffline(error) ? (
            <div className="py-4">
              <BackendOffline
                compact
                onRetry={() => refetch()}
                message="Backend offline — document list unavailable."
              />
            </div>
          ) : (
            <div className="text-sm text-red-600 dark:text-red-400 py-4 text-center">
              Failed to load documents.{" "}
              <button className="underline" onClick={() => refetch()}>
                Retry
              </button>
            </div>
          )
        ) : items.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            No documents yet. Drop .md files above to upload.
          </div>
        ) : (
          <ul className="space-y-1 max-h-80 overflow-y-auto thin-scroll">
            {items.map((doc) => {
              const active = selectedId === doc.id;
              return (
                <li
                  key={doc.id}
                  className={`flex items-center gap-2 rounded-md border px-3 py-2 cursor-pointer transition-colors ${
                    active ? "border-primary bg-primary/5" : "hover:bg-accent/50 border-transparent"
                  }`}
                  onClick={() => onSelect(doc.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(doc.id);
                    }
                  }}
                  aria-pressed={active}
                >
                  <FileText className={`h-4 w-4 shrink-0 ${active ? "text-primary" : "text-muted-foreground"}`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{doc.filename}</div>
                    <div className="text-[11px] text-muted-foreground flex items-center gap-2">
                      <span className="font-mono">{formatBytes(doc.sizeBytes ?? doc.size ?? 0)}</span>
                      <span>·</span>
                      <span className="truncate">{doc.contentType}</span>
                      <span>·</span>
                      <span>{timeAgo(doc.createdAt)}</span>
                      {(doc as any).representativeEmbeddingMethod && (
                        <Badge variant="outline" className="text-[9px] ml-1">{(doc as any).representativeEmbeddingMethod}</Badge>
                      )}
                      {(doc as any).kinds && (doc as any).kinds.length > 1 && (
                        <span className="text-[9px] text-primary/70">+{(doc as any).kinds.length - 1} kinds</span>
                      )}
                      {/* Highlight if longtext knowledge present (from Knowledge nodes) */}
                      {(doc as any).representativeEmbeddingMethod === 'LongText' && (
                        <Badge className="text-[9px] ml-1 bg-blue-500/20 text-blue-600">LongText :knowledge</Badge>
                      )}
                    </div>
                  </div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-red-600 hover:bg-red-500/10"
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`Delete ${doc.filename}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete document?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This permanently removes <span className="font-mono">{doc.filename}</span> and all related data. This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          className="bg-red-600 hover:bg-red-700 text-white"
                          onClick={() => deleteMutation.mutate(doc.id)}
                        >
                          Delete
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

interface ChunkEventRow {
  chunk: ChunkMetadata;
  index: number;
  total: number;
  progress: number;
  stage: IngestProgressEvent["stage"];
  message?: string;
}

function IngestProgressPanel({
  status,
  isLoading,
  isError,
  experimentId,
  lastEvent,
  chunkEvents,
  onOpenInspector,
  onReset,
}: {
  status: JobStatusResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  experimentId: string | null;
  lastEvent: IngestProgressEvent | null;
  chunkEvents: ChunkEventRow[];
  onOpenInspector: (chunk: ChunkMetadata) => void;
  onReset: () => void;
}) {
  const setActiveDocument = useUIStore((s) => s.setActiveDocument);
  const setView = useUIStore((s) => s.setView);

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-12 space-y-3">
          <Skeleton className="h-6 w-1/2" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card className="border-red-500/30">
        <CardContent className="py-8 text-center text-sm text-red-600 dark:text-red-400">
          Failed to load job status.
          <div className="mt-3">
            <Button variant="outline" size="sm" onClick={onReset}>
              Dismiss
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!status) return null;

  const completed = status.status === "completed";
  const failed = status.status === "failed";

  return (
    <Card className="py-0">
      {/* Sticky progress header */}
      <div className="sticky top-0 z-10 bg-card rounded-t-xl border-b px-5 py-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <Database className="h-4 w-4 text-primary shrink-0" />
            <span className="text-sm font-semibold truncate">Live Ingestion</span>
          </div>
          <Badge variant="outline" className={statusTone(status.status)}>
            {status.status === "completed" && <CheckCircle2 className="h-3 w-3" />}
            {status.status === "failed" && <XCircle className="h-3 w-3" />}
            {status.status}
          </Badge>
        </div>

        <Progress value={status.progress} className="h-2" />

        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span className="font-mono">
            {status.current}/{status.total || "?"} chunks
          </span>
          <span className="font-mono">{Math.round(status.progress)}%</span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {lastEvent && (
            <Badge variant="outline" className={stageTone(lastEvent.stage)}>
              {lastEvent.stage}
            </Badge>
          )}
          {lastEvent?.message && (
            <span className="text-[11px] text-muted-foreground truncate">{lastEvent.message}</span>
          )}
        </div>
      </div>

      {/* Banners */}
      {completed && (
        <div className="px-5 pt-4">
          <Alert className="border-emerald-500/30 bg-emerald-500/5">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            <AlertTitle>Ingestion completed</AlertTitle>
            <AlertDescription className="text-sm">
              {chunkEvents.length} chunks embedded with full metadata. View the document to see records.
              <div className="mt-2 flex gap-2 flex-wrap">
                <Button
                  size="sm"
                  onClick={() => {
                    if (experimentId) {
                      setActiveDocument(experimentId);
                      setView("documents");
                    }
                  }}
                  disabled={!experimentId}
                >
                  View Document <ArrowRight className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="outline" onClick={onReset}>
                  New Ingestion
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        </div>
      )}

      {failed && (
        <div className="px-5 pt-4">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Ingestion failed</AlertTitle>
            <AlertDescription className="text-sm">
              <div className="font-mono text-xs">{status.errorCode || "UNKNOWN"}</div>
              <div className="mt-1">{status.errorMessage || "An unknown error occurred."}</div>
              <div className="mt-2">
                <Button size="sm" variant="outline" onClick={onReset}>
                  Dismiss
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        </div>
      )}

      {/* Per-chunk metadata table — visual centerpiece */}
      <div className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium flex items-center gap-2">
            <Hash className="h-3.5 w-3.5 text-muted-foreground" />
            Per-chunk metadata
          </h3>
          <span className="text-[11px] text-muted-foreground font-mono">{chunkEvents.length} rows</span>
        </div>
        {chunkEvents.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            {completed ? "LongText windows stored as :Knowledge (full text visible in Documents). No per-child events." : "Waiting for first chunk…"}
          </div>
        ) : (
          <div className="rounded-md border max-h-96 overflow-y-auto thin-scroll">
            <Table>
              <TableHeader className="sticky top-0 bg-card z-[1]">
                <TableRow>
                  <TableHead className="w-10 text-right">#</TableHead>
                  <TableHead>Method</TableHead>
                  <TableHead>Embedding</TableHead>
                  <TableHead className="text-right">Tokens</TableHead>
                  <TableHead className="text-right">Chunk ms</TableHead>
                  <TableHead className="text-right">Embed ms</TableHead>
                  <TableHead>Section</TableHead>
                  <TableHead>Preview</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {chunkEvents.map((row) => {
                  const c = row.chunk;
                  return (
                    <TableRow
                      key={c.chunkId}
                      className="cursor-pointer hover:bg-accent/50"
                      onClick={() => onOpenInspector(c)}
                    >
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">{c.chunkIndex}</TableCell>
                      <TableCell className="font-mono text-xs">{c.chunkMethod}</TableCell>
                      <TableCell className="font-mono text-xs">{c.embeddingMethod}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{c.tokenCount}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{Math.round(c.chunkingTimeMs)}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{Math.round(c.embeddingTimeMs)}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground max-w-32 truncate" title={c.section ?? ""}>
                        {c.section || "—"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-48 truncate" title={c.textPreview}>
                        {truncate(c.textPreview, 60)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
        <p className="text-[11px] text-muted-foreground mt-2">
          Click any row to open the chunk inspector.
        </p>
      </div>
    </Card>
  );
}

function ChunkInspector({ chunk }: { chunk: ChunkMetadata }) {
  const rows: { label: string; value: React.ReactNode; mono?: boolean }[] = [
    { label: "Chunk ID", value: chunk.chunkId, mono: true },
    { label: "Parent Doc ID", value: chunk.parentDocId, mono: true },
    { label: "Run ID", value: chunk.experimentId, mono: true },
    { label: "Chunk Index", value: chunk.chunkIndex, mono: true },
    { label: "Chunk Method", value: chunk.chunkMethod, mono: true },
    { label: "Embedding Method", value: chunk.embeddingMethod, mono: true },
    { label: "Token Count", value: chunk.tokenCount, mono: true },
    { label: "Chunking Time", value: `${Math.round(chunk.chunkingTimeMs)} ms`, mono: true },
    { label: "Embedding Time", value: `${Math.round(chunk.embeddingTimeMs)} ms`, mono: true },
    { label: "Char Range", value: chunk.charStart !== undefined && chunk.charEnd !== undefined ? `${chunk.charStart} – ${chunk.charEnd}` : "—", mono: true },
    { label: "Section Path", value: chunk.section || "—" },
  ];

  return (
    <div className="px-4 pb-6 space-y-5">
      <div>
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2 flex items-center gap-2">
          <Clock className="h-3 w-3" /> Metadata
        </h4>
        <dl className="rounded-md border divide-y">
          {rows.map((r) => (
            <div key={r.label} className="grid grid-cols-[120px_1fr] gap-2 px-3 py-2">
              <dt className="text-xs text-muted-foreground">{r.label}</dt>
              <dd className={`text-xs ${r.mono ? "font-mono" : ""} break-all`}>{r.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div>
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
          Text Preview
        </h4>
        <pre className="rounded-md border bg-muted/30 p-3 text-xs whitespace-pre-wrap break-words font-mono leading-relaxed max-h-80 overflow-y-auto thin-scroll">
          {chunk.textPreview}
        </pre>
      </div>
    </div>
  );
}
