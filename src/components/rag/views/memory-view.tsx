"use client";

/**
 * MemoryView — Memory Cart Page (Frontend_Workflow_Mapping v1.1 §3).
 * Two-column layout:
 *   • Left (~340px): create-cart form + carts list.
 *   • Right: cart detail with checkbox selection table + add-memories dialog
 *           + collapsible global memory browser.
 *
 * All server state via TanStack Query. Mutations invalidate the relevant keys.
 */

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { api } from "@/lib/api-client";
import type { Memory, MemoryCart } from "@/lib/rag/types";
import { ViewHeader, ViewBody } from "@/components/rag/shared/view-header";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
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
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import {
  ShoppingCart,
  Plus,
  Pencil,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Clock,
  AlertCircle,
  Eye,
  Inbox,
  ListPlus,
  Search as SearchIcon,
} from "lucide-react";

// ─── helpers ─────────────────────────────────────────────────────────────────
function relativeTime(d: string | Date | null | undefined): string {
  if (!d) return "—";
  try {
    return formatDistanceToNow(new Date(d), { addSuffix: true });
  } catch {
    return "—";
  }
}

function fmtScore(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(3);
}

function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

// Extended memory type returned by the cart detail endpoint (full memory rows).
type CartMemory = Memory;

// ─── Create Cart ─────────────────────────────────────────────────────────────
function CreateCartCard({ onCreated }: { onCreated: (id: string) => void }) {
  const qc = useQueryClient();
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");

  const createMut = useMutation({
    mutationFn: () =>
      api.memoryCarts.create({
        name: name.trim(),
        description: description.trim() || undefined,
      }),
    onSuccess: (data) => {
      toast.success("Cart created", { description: `"${name.trim()}"` });
      qc.invalidateQueries({ queryKey: ["carts"] });
      setName("");
      setDescription("");
      onCreated(data.id);
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : "Failed to create cart";
      toast.error("Create failed", { description: msg });
    },
  });

  const canSubmit = name.trim().length > 0 && !createMut.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Plus className="h-4 w-4 text-primary" />
          Create Cart
        </CardTitle>
        <CardDescription className="text-xs">
          A cart groups curated memories for export or sharing.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="cart-name" className="text-xs">Name</Label>
          <Input
            id="cart-name"
            placeholder="e.g. Best hybrid-search hits"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSubmit) createMut.mutate();
            }}
            disabled={createMut.isPending}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cart-desc" className="text-xs">
            Description <span className="text-muted-foreground">(optional)</span>
          </Label>
          <Textarea
            id="cart-desc"
            placeholder="What this cart is for…"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            disabled={createMut.isPending}
            className="resize-none"
          />
        </div>
        <Button
          className="w-full"
          size="sm"
          disabled={!canSubmit}
          onClick={() => createMut.mutate()}
        >
          {createMut.isPending ? "Creating…" : "Create Cart"}
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── Carts List ──────────────────────────────────────────────────────────────
function CartsList({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["carts"],
    queryFn: () => api.memoryCarts.list(),
  });

  const carts = data?.items ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Memory Carts</CardTitle>
        <CardDescription className="text-xs">
          {carts.length} cart{carts.length === 1 ? "" : "s"}
        </CardDescription>
        <CardAction>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => refetch()}
            aria-label="Refresh carts"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-16 w-full rounded-md" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4" /> Failed to load carts.
          </div>
        ) : carts.length === 0 ? (
          <div className="rounded-md border border-dashed p-6 text-center">
            <Inbox className="mx-auto h-6 w-6 text-muted-foreground mb-2" />
            <p className="text-xs text-muted-foreground">
              No carts yet. Create one to start curating retrieval results.
            </p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[55vh] overflow-y-auto thin-scroll pr-1">
            {carts.map((c: MemoryCart) => (
              <button
                key={c.id}
                onClick={() => onSelect(c.id)}
                aria-current={selectedId === c.id}
                className={cn(
                  "w-full text-left rounded-md border p-3 transition-all hover:shadow-sm hover:border-primary/40 hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  selectedId === c.id && "ring-2 ring-primary border-primary bg-accent/40 shadow-sm"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-medium text-sm truncate">{c.name}</div>
                  <Badge variant="secondary" className="shrink-0 font-mono text-[10px]">
                    {c.memoryCount}
                  </Badge>
                </div>
                {c.description && (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{c.description}</p>
                )}
                <div className="text-[10px] text-muted-foreground mt-1.5 flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Updated {relativeTime(c.updatedAt)}
                </div>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Memory Detail Sheet ────────────────────────────────────────────────────
function MemoryDetailSheet({
  memory,
  open,
  onOpenChange,
}: {
  memory: CartMemory | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  if (!memory) return null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-lg overflow-y-auto thin-scroll">
        <SheetHeader>
          <SheetTitle className="text-base">Memory detail</SheetTitle>
          <SheetDescription className="text-xs">
            id: <span className="font-mono">{memory.id}</span>
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6 space-y-4 text-sm">
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Query</div>
            <div className="rounded-md bg-muted/50 p-2.5 text-sm leading-relaxed">{memory.queryText}</div>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Chunk text</div>
            <div className="rounded-md bg-muted/50 p-2.5 text-sm leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto thin-scroll">
              {memory.chunkText ?? "—"}
            </div>
          </div>
          <Separator />
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            <ScoreCell label="Final score" value={fmtScore(memory.score)} highlight />
            <ScoreCell label="Vector" value={fmtScore(memory.vectorScore)} />
            <ScoreCell label="BM25" value={fmtScore(memory.bm25Score)} />
            <ScoreCell label="Fused" value={fmtScore(memory.fusedScore)} />
            <ScoreCell label="Reranker" value={fmtScore(memory.rerankerScore)} />
            <ScoreCell label="Success" value={fmtScore(memory.successScore)} />
          </div>
          {memory.notes && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Notes</div>
              <div className="rounded-md bg-muted/50 p-2.5 text-sm">{memory.notes}</div>
            </div>
          )}
          <div className="text-[10px] text-muted-foreground flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Created {relativeTime(memory.createdAt)}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ScoreCell({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="rounded-md border p-2">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={cn("font-mono text-sm mt-0.5", highlight && "text-primary font-semibold")}>{value}</div>
    </div>
  );
}

// ─── Add Memories Dialog ────────────────────────────────────────────────────
function AddMemoriesDialog({
  cartId,
  existingIds,
}: {
  cartId: string;
  existingIds: Set<string>;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [search, setSearch] = React.useState("");

  // Load all recent memories when the dialog opens.
  const { data, isLoading, isError } = useQuery({
    queryKey: ["memories", "all", 1, 100],
    queryFn: () => api.memories.list({ page: 1, pageSize: 100 }),
    enabled: open,
  });

  React.useEffect(() => {
    if (!open) {
      setSelected(new Set());
      setSearch("");
    }
  }, [open]);

  const addMut = useMutation({
    mutationFn: (ids: string[]) => api.memoryCarts.patch(cartId, { addMemoryIds: ids }),
    onSuccess: (_data, ids) => {
      toast.success(`Added ${ids.length} memor${ids.length === 1 ? "y" : "ies"} to cart`);
      qc.invalidateQueries({ queryKey: ["cart", cartId] });
      qc.invalidateQueries({ queryKey: ["carts"] });
      setOpen(false);
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : "Failed to add memories";
      toast.error("Add failed", { description: msg });
    },
  });

  const memories = (data?.items ?? []) as Memory[];
  const candidates = memories.filter(
    (m) => !existingIds.has(m.id) && (!search || m.queryText.toLowerCase().includes(search.toLowerCase()))
  );

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <ListPlus className="h-3.5 w-3.5" /> Add memories
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add memories to cart</DialogTitle>
          <DialogDescription>
            Select recent memories to add. Memories already in this cart are hidden.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <div className="relative">
            <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Filter by query text…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-8 text-sm"
            />
          </div>
          <div className="rounded-md border max-h-[50vh] overflow-y-auto thin-scroll">
            {isLoading ? (
              <div className="p-3 space-y-2">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : isError ? (
              <div className="p-4 text-xs text-destructive flex items-center gap-2">
                <AlertCircle className="h-4 w-4" /> Failed to load memories.
              </div>
            ) : candidates.length === 0 ? (
              <div className="p-6 text-center text-xs text-muted-foreground">
                No memories available to add.
              </div>
            ) : (
              <ul className="divide-y">
                {candidates.map((m) => {
                  const checked = selected.has(m.id);
                  return (
                    <li key={m.id}>
                      <label
                        className={cn(
                          "flex items-start gap-2.5 p-2.5 cursor-pointer hover:bg-accent/50 transition-colors",
                          checked && "bg-accent/40"
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => toggle(m.id)}
                          className="mt-0.5"
                          aria-label={`Select memory ${m.id}`}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm truncate">{m.queryText}</div>
                          {m.chunkText && (
                            <div className="text-xs text-muted-foreground line-clamp-1 mt-0.5">{m.chunkText}</div>
                          )}
                          <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-2">
                            <span className="font-mono">score {fmtScore(m.score)}</span>
                            <span>{relativeTime(m.createdAt)}</span>
                          </div>
                        </div>
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          {selected.size > 0 && (
            <div className="text-xs text-muted-foreground">
              {selected.size} selected
            </div>
          )}
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" size="sm">Cancel</Button>
          </DialogClose>
          <Button
            size="sm"
            disabled={selected.size === 0 || addMut.isPending}
            onClick={() => addMut.mutate(Array.from(selected))}
          >
            {addMut.isPending
              ? "Adding…"
              : `Add ${selected.size > 0 ? selected.size : ""} selected`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Edit Cart Dialog ────────────────────────────────────────────────────────
function EditCartDialog({
  cartId,
  name,
  description,
}: {
  cartId: string;
  name: string;
  description: string | null;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [n, setN] = React.useState(name);
  const [d, setD] = React.useState(description ?? "");

  React.useEffect(() => {
    if (open) {
      setN(name);
      setD(description ?? "");
    }
  }, [open, name, description]);

  const saveMut = useMutation({
    mutationFn: () =>
      api.memoryCarts.patch(cartId, {
        name: n.trim(),
        description: d.trim() || undefined,
      }),
    onSuccess: () => {
      toast.success("Cart updated");
      qc.invalidateQueries({ queryKey: ["cart", cartId] });
      qc.invalidateQueries({ queryKey: ["carts"] });
      setOpen(false);
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : "Failed to update cart";
      toast.error("Update failed", { description: msg });
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Edit cart">
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit cart</DialogTitle>
          <DialogDescription>Rename or update the description.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="edit-name" className="text-xs">Name</Label>
            <Input id="edit-name" value={n} onChange={(e) => setN(e.target.value)} disabled={saveMut.isPending} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-desc" className="text-xs">Description</Label>
            <Textarea
              id="edit-desc"
              value={d}
              onChange={(e) => setD(e.target.value)}
              rows={3}
              disabled={saveMut.isPending}
              className="resize-none"
            />
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" size="sm">Cancel</Button>
          </DialogClose>
          <Button
            size="sm"
            disabled={!n.trim() || saveMut.isPending}
            onClick={() => saveMut.mutate()}
          >
            {saveMut.isPending ? "Saving…" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Memory Selection Table (cart detail) ───────────────────────────────────
function MemorySelectionTable({ cartId, memories }: { cartId: string; memories: CartMemory[] }) {
  const qc = useQueryClient();
  const [detail, setDetail] = React.useState<CartMemory | null>(null);
  const [detailOpen, setDetailOpen] = React.useState(false);

  // Optimistic toggle: replace the selection with the remaining checked ids.
  const toggleMut = useMutation({
    mutationFn: (memoryIds: string[]) => api.memoryCarts.patch(cartId, { memoryIds }),
    onMutate: async (memoryIds: string[]) => {
      await qc.cancelQueries({ queryKey: ["cart", cartId] });
      const prev = qc.getQueryData<{ memories: CartMemory[] }>(["cart", cartId]);
      if (prev) {
        const set = new Set(memoryIds);
        qc.setQueryData(["cart", cartId], {
          ...prev,
          memories: prev.memories.filter((m) => set.has(m.id)),
        });
      }
      return { prev };
    },
    onSuccess: (_data, memoryIds) => {
      toast.success(`Updated selection (${memoryIds.length} memor${memoryIds.length === 1 ? "y" : "ies"})`);
      qc.invalidateQueries({ queryKey: ["cart", cartId] });
      qc.invalidateQueries({ queryKey: ["carts"] });
    },
    onError: (e: unknown, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["cart", cartId], ctx.prev);
      const msg = e instanceof Error ? e.message : "Failed to update selection";
      toast.error("Update failed", { description: msg });
    },
  });

  const handleToggle = (id: string, checked: boolean) => {
    const next = memories.filter((m) => (m.id === id ? checked : true)).map((m) => m.id);
    toggleMut.mutate(next);
  };

  const openDetail = (m: CartMemory) => {
    setDetail(m);
    setDetailOpen(true);
  };

  if (memories.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-8 text-center">
        <Inbox className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">
          No memories in this cart yet.
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          Use <span className="font-medium">Add memories</span> to curate retrieval results.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="rounded-md border max-h-[60vh] overflow-y-auto thin-scroll">
        <Table>
          <TableHeader className="sticky top-0 bg-background z-10">
            <TableRow>
              <TableHead className="w-[40px]"></TableHead>
              <TableHead className="min-w-[160px]">Query</TableHead>
              <TableHead className="min-w-[220px]">Chunk text</TableHead>
              <TableHead className="w-[70px] text-right">Score</TableHead>
              <TableHead className="w-[70px] text-right">Vector</TableHead>
              <TableHead className="w-[70px] text-right">BM25</TableHead>
              <TableHead className="w-[70px] text-right">Rerank</TableHead>
              <TableHead className="w-[110px]">Created</TableHead>
              <TableHead className="w-[40px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {memories.map((m) => (
              <TableRow
                key={m.id}
                data-state={m.selected ? "selected" : undefined}
                className="group"
              >
                <TableCell>
                  <Checkbox
                    checked={true}
                    onCheckedChange={(v) => handleToggle(m.id, Boolean(v))}
                    aria-label={`Keep memory ${m.id} in cart`}
                  />
                </TableCell>
                <TableCell className="max-w-[200px]">
                  <button
                    className="text-left text-sm hover:text-primary hover:underline line-clamp-2"
                    onClick={() => openDetail(m)}
                  >
                    {m.queryText}
                  </button>
                </TableCell>
                <TableCell className="max-w-[260px]">
                  <button
                    className="text-left text-xs text-muted-foreground hover:text-primary line-clamp-2 text-left"
                    onClick={() => openDetail(m)}
                  >
                    {m.chunkText ?? "—"}
                  </button>
                </TableCell>
                <TableCell className="text-right font-mono text-xs">{fmtScore(m.score)}</TableCell>
                <TableCell className="text-right font-mono text-xs text-muted-foreground">{fmtScore(m.vectorScore)}</TableCell>
                <TableCell className="text-right font-mono text-xs text-muted-foreground">{fmtScore(m.bm25Score)}</TableCell>
                <TableCell className="text-right font-mono text-xs text-muted-foreground">{fmtScore(m.rerankerScore)}</TableCell>
                <TableCell className="text-[10px] text-muted-foreground whitespace-nowrap">
                  {relativeTime(m.createdAt)}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => openDetail(m)}
                    aria-label="View memory detail"
                  >
                    <Eye className="h-3 w-3" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <MemoryDetailSheet memory={detail} open={detailOpen} onOpenChange={setDetailOpen} />
    </>
  );
}

// ─── Cart Detail ────────────────────────────────────────────────────────────
function CartDetail({ cartId }: { cartId: string }) {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["cart", cartId],
    queryFn: () => api.memoryCarts.get(cartId),
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-3 w-1/4 mt-2" />
        </CardHeader>
        <CardContent className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> Failed to load cart detail.
          </div>
          <Button variant="outline" size="sm" className="mt-3" onClick={() => refetch()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  const memories = (data.memories ?? []) as CartMemory[];
  const existingIds = new Set(memories.map((m) => m.id));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2 min-w-0">
          <div className="min-w-0">
            <CardTitle className="flex items-center gap-2 text-base truncate">
              <ShoppingCart className="h-4 w-4 text-primary shrink-0" />
              <span className="truncate">{data.name}</span>
            </CardTitle>
            <CardDescription className="text-xs mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
              <span>{memories.length} memor{memories.length === 1 ? "y" : "ies"}</span>
              <span aria-hidden>·</span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Created {relativeTime(data.createdAt)}
              </span>
              <span aria-hidden>·</span>
              <span>Updated {relativeTime(data.updatedAt)}</span>
            </CardDescription>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => refetch()}
              aria-label="Refresh cart"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            </Button>
            <EditCartDialog
              cartId={cartId}
              name={data.name}
              description={data.description}
            />
          </div>
        </div>
        {data.description && (
          <p className="text-xs text-muted-foreground mt-1">{data.description}</p>
        )}
        <CardAction>
          <AddMemoriesDialog cartId={cartId} existingIds={existingIds} />
        </CardAction>
      </CardHeader>
      <CardContent>
        <MemorySelectionTable cartId={cartId} memories={memories} />
      </CardContent>
    </Card>
  );
}

// ─── All Memories Browser (collapsible) ─────────────────────────────────────
function AllMemoriesSection() {
  const [open, setOpen] = React.useState(false);
  const [expFilter, setExpFilter] = React.useState<string>("all");

  // Search-experiments for the filter dropdown.
  const { data: expData } = useQuery({
    queryKey: ["experiments", "list", { kind: "search" }],
    queryFn: () => api.experiments.list({ page: 1, pageSize: 50, kind: "search" }),
  });
  const searchExps = expData?.items ?? [];

  const { data, isLoading, isError } = useQuery({
    queryKey: ["memories", "all", 1, 50, expFilter],
    queryFn: () =>
      api.memories.list({
        page: 1,
        pageSize: 50,
        experimentId: expFilter === "all" ? undefined : expFilter,
      }),
    enabled: open,
  });

  const memories = (data?.items ?? []) as Memory[];

  // Mutation to toggle a memory in/out of the most recent cart via set selection.
  // For the global browser we use addMemoryIds when not selected; for removal we
  // would need to know which cart contains it. v1 keeps the browser as
  // read-only + "add to cart" via per-row dropdown. Simplest: show selected
  // badge and a quick "add to cart" picker.
  const [detail, setDetail] = React.useState<Memory | null>(null);
  const [detailOpen, setDetailOpen] = React.useState(false);

  return (
    <Card>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CardHeader>
          <CardTitle className="text-base">All Memories</CardTitle>
          <CardDescription className="text-xs">
            Browse all retrieval memories across experiments.
          </CardDescription>
          <CardAction>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="h-7 gap-1">
                {open ? "Hide" : "Show"}
                {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              </Button>
            </CollapsibleTrigger>
          </CardAction>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <Label htmlFor="exp-filter" className="text-xs text-muted-foreground">Filter by experiment</Label>
              <Select value={expFilter} onValueChange={setExpFilter}>
                <SelectTrigger id="exp-filter" className="h-8 w-[260px] text-xs">
                  <SelectValue placeholder="All experiments" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All experiments</SelectItem>
                  {searchExps.map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.description?.slice(0, 60) ?? e.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-[10px] text-muted-foreground">
                {memories.length} shown
              </span>
            </div>
            <div className="rounded-md border max-h-96 overflow-y-auto thin-scroll">
              {isLoading ? (
                <div className="p-3 space-y-2">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : isError ? (
                <div className="p-4 text-xs text-destructive flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" /> Failed to load memories.
                </div>
              ) : memories.length === 0 ? (
                <div className="p-6 text-center text-xs text-muted-foreground">
                  No memories found. Run a search to populate.
                </div>
              ) : (
                <Table>
                  <TableHeader className="sticky top-0 bg-background z-10">
                    <TableRow>
                      <TableHead className="min-w-[180px]">Query</TableHead>
                      <TableHead className="min-w-[240px]">Chunk text</TableHead>
                      <TableHead className="w-[70px] text-right">Score</TableHead>
                      <TableHead className="w-[100px]">In cart</TableHead>
                      <TableHead className="w-[110px]">Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {memories.map((m) => (
                      <TableRow key={m.id} className="group">
                        <TableCell className="max-w-[200px]">
                          <button
                            className="text-left text-sm hover:text-primary hover:underline line-clamp-2"
                            onClick={() => {
                              setDetail(m);
                              setDetailOpen(true);
                            }}
                          >
                            {m.queryText}
                          </button>
                        </TableCell>
                        <TableCell className="max-w-[280px]">
                          <button
                            className="text-left text-xs text-muted-foreground hover:text-primary line-clamp-2 text-left"
                            onClick={() => {
                              setDetail(m);
                              setDetailOpen(true);
                            }}
                          >
                            {m.chunkText ?? "—"}
                          </button>
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">{fmtScore(m.score)}</TableCell>
                        <TableCell>
                          {m.selected ? (
                            <Badge variant="default" className="text-[10px]">in cart</Badge>
                          ) : (
                            <Badge variant="outline" className="text-[10px] text-muted-foreground">—</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-[10px] text-muted-foreground whitespace-nowrap">
                          {relativeTime(m.createdAt)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>

      <MemoryDetailSheet
        memory={detail as CartMemory | null}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />
    </Card>
  );
}

// ─── Cart Detail Placeholder ────────────────────────────────────────────────
function CartDetailPlaceholder() {
  return (
    <Card className="border-dashed">
      <CardContent className="pt-10 pb-10 flex flex-col items-center justify-center text-center">
        <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center mb-3">
          <ShoppingCart className="h-5 w-5 text-primary" />
        </div>
        <p className="text-sm font-medium">Select a cart to view its memories</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-xs">
          Pick a cart from the list to inspect and curate its retrieval results.
        </p>
      </CardContent>
    </Card>
  );
}

// ─── Main View ──────────────────────────────────────────────────────────────
export function MemoryView() {
  const [selectedCartId, setSelectedCartId] = React.useState<string | null>(null);

  return (
    <>
      <ViewHeader
        title="Memory Cart"
        description="Curate retrieval memories into shareable carts"
        icon={ShoppingCart}
      />
      <ViewBody>
        <div className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
          {/* Left column */}
          <div className="space-y-4">
            <CreateCartCard onCreated={(id) => setSelectedCartId(id)} />
            <CartsList selectedId={selectedCartId} onSelect={setSelectedCartId} />
          </div>
          {/* Right column */}
          <div className="space-y-4">
            {selectedCartId ? (
              <CartDetail cartId={selectedCartId} />
            ) : (
              <CartDetailPlaceholder />
            )}
            <AllMemoriesSection />
          </div>
        </div>
      </ViewBody>
    </>
  );
}
