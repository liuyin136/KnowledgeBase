"use client";

/**
 * MemoryView — Memory Cart Page (v1.2 redesign).
 *
 * Layout (desktop):
 *   ┌──────────────┬─────────────────┬────────────────────────────────────┐
 *   │ carts sidebar │ memory list     │ inspection area (dominant)         │
 *   │ ~260px        │ ~260px          │ 1fr                                │
 *   │ - create cart │ - keyboard nav  │ - query blockquote (top)           │
 *   │ - carts list  │ - up/down arrows│ - resizable: chunk text / scores   │
 *   │               │ - click to      │ - manage-selection table (collaps) │
 *   │               │   inspect       │                                    │
 *   └──────────────┴─────────────────┴────────────────────────────────────┘
 *
 * Mobile: carts collapse to a top Sheet trigger; memory list becomes a
 * horizontal scroll strip; inspection stacks below.
 *
 * Keyboard: when the memory list has focus, ArrowUp/ArrowDown (and Home/End)
 * move the active memory; the inspection pane updates immediately.
 *
 * v1.2: graceful backend-offline state — when api.memoryCarts.get throws
 * BACKEND_UNAVAILABLE / BACKEND_UNREACHABLE, the inspection area shows the
 * shared <BackendOffline/> component instead of crashing.
 */

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { api, isBackendOffline } from "@/lib/api-client";
import type { Memory, MemoryCart } from "@/lib/rag/types";
import { ViewHeader, ViewBody } from "@/components/rag/shared/view-header";
import { BackendOffline } from "@/components/rag/shared/backend-offline";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable";
import {
  ShoppingCart,
  Plus,
  Pencil,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Clock,
  AlertCircle,
  Inbox,
  ListPlus,
  Search as SearchIcon,
  PanelTop,
  PanelBottom,
  ArrowUp,
  ArrowDown,
  Eye,
  Quote,
  Menu,
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
  compact,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
  compact?: boolean;
}) {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["carts"],
    queryFn: () => api.memoryCarts.list(),
  });

  const carts = data?.items ?? [];

  if (compact) {
    // Used inside the mobile Sheet.
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {carts.length} cart{carts.length === 1 ? "" : "s"}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => refetch()}
            aria-label="Refresh carts"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          </Button>
        </div>
        {isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-14 w-full rounded-md" />
            ))}
          </div>
        ) : isError ? (
          isBackendOffline(error) ? (
            <BackendOffline compact onRetry={() => refetch()} />
          ) : (
            <div className="flex items-center gap-2 text-xs text-destructive">
              <AlertCircle className="h-4 w-4" /> Failed to load carts.
            </div>
          )
        ) : carts.length === 0 ? (
          <div className="rounded-md border border-dashed p-4 text-center">
            <p className="text-xs text-muted-foreground">No carts yet.</p>
          </div>
        ) : (
          carts.map((c: MemoryCart) => (
            <button
              key={c.id}
              onClick={() => onSelect(c.id)}
              className={cn(
                "w-full text-left rounded-md border p-2.5 transition-all hover:shadow-sm hover:border-primary/40 hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                selectedId === c.id && "ring-2 ring-primary border-primary bg-accent/40"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-sm truncate">{c.name}</span>
                <Badge variant="secondary" className="shrink-0 font-mono text-[10px]">
                  {c.memoryCount}
                </Badge>
              </div>
              <div className="text-[10px] text-muted-foreground mt-1">
                Updated {relativeTime(c.updatedAt)}
              </div>
            </button>
          ))
        )}
      </div>
    );
  }

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
          isBackendOffline(error) ? (
            <BackendOffline compact onRetry={() => refetch()} />
          ) : (
            <div className="flex items-center gap-2 text-xs text-destructive">
              <AlertCircle className="h-4 w-4" /> Failed to load carts.
            </div>
          )
        ) : carts.length === 0 ? (
          <div className="rounded-md border border-dashed p-6 text-center">
            <Inbox className="mx-auto h-6 w-6 text-muted-foreground mb-2" />
            <p className="text-xs text-muted-foreground">
              No carts yet. Create one to start curating retrieval results.
            </p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-y-auto thin-scroll pr-1">
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
  const { data, isLoading, isError, error } = useQuery({
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
              isBackendOffline(error) ? (
                <div className="p-3">
                  <BackendOffline compact />
                </div>
              ) : (
                <div className="p-4 text-xs text-destructive flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" /> Failed to load memories.
                </div>
              )
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

// ─── Memory navigation list (keyboard-navigable) ────────────────────────────
/**
 * Compact vertical list of memories in the active cart. ArrowUp/ArrowDown +
 * Home/End move the active memory; the parent's `onSelect` updates the
 * inspection pane. The list container has `role="listbox"` and each item
 * `role="option"`, with `aria-activedescendant` on the listbox pointing to
 * the active item for screen readers.
 */
function MemoryNavList({
  memories,
  activeId,
  onSelect,
  className,
}: {
  memories: CartMemory[];
  activeId: string | null;
  onSelect: (id: string) => void;
  className?: string;
}) {
  const listRef = React.useRef<HTMLDivElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (memories.length === 0) return;
    const idx = memories.findIndex((m) => m.id === activeId);
    let next = idx;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      next = Math.min(memories.length - 1, idx + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      next = Math.max(0, idx - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      next = 0;
    } else if (e.key === "End") {
      e.preventDefault();
      next = memories.length - 1;
    } else {
      return;
    }
    if (next !== idx && memories[next]) {
      onSelect(memories[next].id);
      // Scroll the newly-active item into view.
      const listEl = listRef.current;
      if (listEl) {
        const item = listEl.querySelector<HTMLElement>(`[data-memory-id="${memories[next].id}"]`);
        item?.scrollIntoView({ block: "nearest" });
      }
    }
  };

  if (memories.length === 0) {
    return (
      <div className={cn("rounded-md border border-dashed p-6 text-center", className)}>
        <Inbox className="mx-auto h-6 w-6 text-muted-foreground mb-2" />
        <p className="text-xs text-muted-foreground">No memories in this cart.</p>
        <p className="text-[10px] text-muted-foreground mt-1">
          Use <span className="font-medium">Add memories</span> to curate.
        </p>
      </div>
    );
  }

  return (
    <div
      className={className}
      ref={listRef}
      role="listbox"
      aria-label="Memories in cart"
      aria-activedescendant={activeId ?? undefined}
      tabIndex={0}
      onKeyDown={handleKeyDown}
    >
      <div className="flex items-center justify-between px-1 mb-2">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          Memories
        </span>
        <span className="text-[10px] text-muted-foreground flex items-center gap-1">
          <ArrowUp className="h-2.5 w-2.5" />
          <ArrowDown className="h-2.5 w-2.5" />
          to navigate
        </span>
      </div>
      <div className="space-y-1.5 max-h-[70vh] overflow-y-auto thin-scroll pr-0.5">
        {memories.map((m, i) => {
          const active = m.id === activeId;
          return (
            <button
              key={m.id}
              id={`mem-${m.id}`}
              data-memory-id={m.id}
              role="option"
              aria-selected={active}
              onClick={() => onSelect(m.id)}
              className={cn(
                "w-full text-left rounded-md border p-2.5 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "ring-2 ring-primary border-primary bg-accent/40 shadow-sm"
                  : "hover:border-primary/40 hover:bg-accent/50"
              )}
            >
              <div className="flex items-center justify-between gap-2 mb-0.5">
                <span
                  className={cn(
                    "font-mono text-[10px] tabular-nums shrink-0",
                    active ? "text-primary" : "text-muted-foreground"
                  )}
                >
                  #{i + 1}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                  score {fmtScore(m.score)}
                </span>
              </div>
              <div className={cn("text-xs line-clamp-2 leading-snug", active && "text-foreground")}>
                {m.queryText}
              </div>
              {m.chunkText && (
                <div className="text-[10px] text-muted-foreground line-clamp-1 mt-1">
                  {m.chunkText}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Memory Inspection Pane (resizable chunk-text / scores split) ───────────
/**
 * The dominant inspection area for the active memory. Shows:
 *   - Query as a prominent blockquote at the top.
 *   - ResizablePanelGroup (vertical): top = chunk text in a big ScrollArea,
 *     bottom = scores + metadata table.
 *
 * The resizable group is given an explicit height (rather than relying on
 * `h-full` chain) so the panels always have a bounded container to fill.
 */
function MemoryInspectionPane({ memory }: { memory: CartMemory }) {
  return (
    <div className="flex flex-col gap-3">
      {/* Query blockquote (always visible, prominent) */}
      <div className="shrink-0 rounded-md border bg-primary/5 border-primary/30 p-3">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-primary mb-1.5">
          <Quote className="h-3 w-3" />
          Query that produced this memory
        </div>
        <blockquote className="text-sm leading-relaxed text-foreground/90 italic border-l-2 border-primary/40 pl-3">
          {memory.queryText}
        </blockquote>
        <div className="text-[10px] text-muted-foreground mt-2 flex items-center gap-2 flex-wrap">
          <span className="font-mono">{memory.id}</span>
          <span aria-hidden>·</span>
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {relativeTime(memory.createdAt)}
          </span>
          {memory.userQueryId && (
            <>
              <span aria-hidden>·</span>
              <span className="font-mono">userQuery: {memory.userQueryId.slice(0, 8)}…</span>
            </>
          )}
        </div>
      </div>

      {/* Resizable split: chunk text (top, large) | scores table (bottom) */}
      <div className="rounded-md border overflow-hidden bg-background h-[55vh] min-h-[400px]">
        <ResizablePanelGroup direction="vertical" className="h-full">
          <ResizablePanel defaultSize={62} minSize={30}>
            <div className="h-full flex flex-col">
              <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b bg-muted/30">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                  <PanelTop className="h-3 w-3" />
                  Chunk text
                </div>
                <span className="text-[10px] font-mono text-muted-foreground">
                  {(memory.chunkText ?? "").length.toLocaleString()} chars
                </span>
              </div>
              <ScrollArea className="flex-1 min-h-0 thin-scroll" type="auto">
                <div className="p-4 text-base leading-relaxed whitespace-pre-wrap break-words">
                  {memory.chunkText ?? (
                    <span className="text-sm italic text-muted-foreground">
                      No chunk text recorded for this memory.
                    </span>
                  )}
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          <ResizablePanel defaultSize={38} minSize={15}>
            <div className="h-full flex flex-col">
              <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b bg-muted/30">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                  <PanelBottom className="h-3 w-3" />
                  Scores & metadata
                </div>
              </div>
              <ScrollArea className="flex-1 min-h-0 thin-scroll" type="auto">
                <div className="p-3">
                  <MemoryScoresTable memory={memory} />
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
}

function ScoreCell({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="rounded-md border p-2.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={cn("font-mono text-sm mt-0.5", highlight && "text-primary font-semibold")}>{value}</div>
    </div>
  );
}

function MemoryScoresTable({ memory }: { memory: CartMemory }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <ScoreCell label="Final score" value={fmtScore(memory.score)} highlight />
        <ScoreCell label="Vector" value={fmtScore(memory.vectorScore)} />
        <ScoreCell label="BM25" value={fmtScore(memory.bm25Score)} />
        <ScoreCell label="Fused" value={fmtScore(memory.fusedScore)} />
        <ScoreCell label="Reranker" value={fmtScore(memory.rerankerScore)} />
        <ScoreCell label="Success" value={fmtScore(memory.successScore)} />
      </div>
      <Separator />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        <MetaRow label="Memory ID" value={memory.id} mono />
        <MetaRow label="User query ID" value={memory.userQueryId} mono />
        <MetaRow label="Chunk ID" value={memory.chunkId ?? "—"} mono />
        <MetaRow
          label="Experiment ID"
          value={memory.experimentId ?? "—"}
          mono
        />
        <MetaRow label="Selected in cart" value={memory.selected ? "yes" : "no"} />
        <MetaRow label="Created" value={relativeTime(memory.createdAt)} />
      </div>
      {memory.notes && (
        <>
          <Separator />
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Notes</div>
            <div className="rounded-md bg-muted/50 p-2.5 text-xs">{memory.notes}</div>
          </div>
        </>
      )}
    </div>
  );
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground shrink-0 w-32">
        {label}
      </span>
      <span className={cn("truncate", mono && "font-mono text-[11px]")}>{value}</span>
    </div>
  );
}

// ─── Manage Selection (collapsible checkbox table) ─────────────────────────
/**
 * The memory selection table (checkboxes to keep/remove from cart). Lives
 * BELOW the inspection area so it doesn't compete for space. Collapsible
 * so the user can focus on inspection.
 */
function ManageSelectionTable({
  cartId,
  memories,
  activeId,
  onSelect,
}: {
  cartId: string;
  memories: CartMemory[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);

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

  if (memories.length === 0) return null;

  return (
    <Card>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <ListPlus className="h-4 w-4 text-primary" />
            Manage selection
            <Badge variant="secondary" className="text-[10px]">{memories.length}</Badge>
          </CardTitle>
          <CardDescription className="text-xs">
            Toggle which memories stay in this cart. Unchecking removes them.
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
          <CardContent>
            <div className="rounded-md border max-h-[40vh] overflow-y-auto thin-scroll">
              <Table>
                <TableHeader className="sticky top-0 bg-background z-10">
                  <TableRow>
                    <TableHead className="w-[40px]">Keep</TableHead>
                    <TableHead className="min-w-[160px]">Query</TableHead>
                    <TableHead className="min-w-[200px]">Chunk text</TableHead>
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
                      data-state={m.id === activeId ? "selected" : undefined}
                      className={cn(
                        "group cursor-pointer",
                        m.id === activeId && "bg-accent/40"
                      )}
                      onClick={() => onSelect(m.id)}
                    >
                      <TableCell onClick={(ev) => ev.stopPropagation()}>
                        <Checkbox
                          checked={true}
                          onCheckedChange={(v) => handleToggle(m.id, Boolean(v))}
                          aria-label={`Keep memory ${m.id} in cart`}
                        />
                      </TableCell>
                      <TableCell className="max-w-[200px]">
                        <span className="text-sm line-clamp-2">{m.queryText}</span>
                      </TableCell>
                      <TableCell className="max-w-[260px]">
                        <span className="text-xs text-muted-foreground line-clamp-2">
                          {m.chunkText ?? "—"}
                        </span>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">{fmtScore(m.score)}</TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">{fmtScore(m.vectorScore)}</TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">{fmtScore(m.bm25Score)}</TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">{fmtScore(m.rerankerScore)}</TableCell>
                      <TableCell className="text-[10px] text-muted-foreground whitespace-nowrap">
                        {relativeTime(m.createdAt)}
                      </TableCell>
                      <TableCell>
                        <Eye className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

// ─── Cart Detail (the dominant right-side inspection area) ─────────────────
function CartDetail({ cartId }: { cartId: string }) {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["cart", cartId],
    queryFn: () => api.memoryCarts.get(cartId),
  });

  const memories = ((data?.memories ?? []) as CartMemory[]);
  const existingIds = React.useMemo(() => new Set(memories.map((m) => m.id)), [memories]);

  // Active memory for the inspection pane. Defaults to the first memory.
  const [activeMemoryId, setActiveMemoryId] = React.useState<string | null>(null);

  // Keep the active memory valid as the cart data changes (e.g. refetch,
  // selection toggle). Falls back to the first memory.
  React.useEffect(() => {
    if (memories.length === 0) {
      if (activeMemoryId !== null) setActiveMemoryId(null);
      return;
    }
    if (!memories.find((m) => m.id === activeMemoryId)) {
      setActiveMemoryId(memories[0].id);
    }
  }, [memories, activeMemoryId]);

  const activeMemory = memories.find((m) => m.id === activeMemoryId) ?? null;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-3 w-1/4 mt-2" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardContent className="pt-6 space-y-3">
          {isBackendOffline(error) ? (
            <BackendOffline
              onRetry={() => refetch()}
              message="The FastAPI backend is not reachable, so this cart's memories cannot be loaded. Start the Docker stack (`docker compose up -d`) and retry."
            />
          ) : (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" /> Failed to load cart detail.
            </div>
          )}
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Cart header */}
      <Card className="shrink-0">
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
      </Card>

      {/* Inspection area — dominant. Grid: memory list | inspection pane */}
      <div className="grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
        {/* Memory navigation list */}
        <div>
          <MemoryNavList
            memories={memories}
            activeId={activeMemoryId}
            onSelect={setActiveMemoryId}
            className="rounded-md border bg-card p-2.5"
          />
        </div>

        {/* Inspection pane (resizable chunk text / scores) */}
        <div>
          {activeMemory ? (
            <MemoryInspectionPane memory={activeMemory} />
          ) : (
            <div className="h-[55vh] min-h-[400px] rounded-md border border-dashed flex flex-col items-center justify-center text-center p-8">
              <ShoppingCart className="h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-sm font-medium">No memory selected</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                {memories.length === 0
                  ? "This cart is empty. Use Add memories to curate retrieval results."
                  : "Select a memory from the list to inspect its chunk text and scores."}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Manage-selection table (below, collapsible) */}
      <ManageSelectionTable
        cartId={cartId}
        memories={memories}
        activeId={activeMemoryId}
        onSelect={setActiveMemoryId}
      />
    </div>
  );
}

// ─── All Memories Browser (collapsible) ─────────────────────────────────────
function AllMemoriesSection() {
  const [open, setOpen] = React.useState(false);
  const [expFilter, setExpFilter] = React.useState<string>("all");

  // Search documents for the filter dropdown (repurposed from experiments).
  const { data: docData } = useQuery({
    queryKey: ["documents", "list", { kind: "search" }],
    queryFn: () => api.documents.list({ page: 1, pageSize: 50 }),
  });
  const searchDocs = docData?.items ?? [];

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["memories", "all", 1, 50],
    queryFn: () =>
      api.memories.list({
        page: 1,
        pageSize: 50,
      }),
    enabled: open,
  });

  const memories = (data?.items ?? []) as Memory[];
  const [detail, setDetail] = React.useState<CartMemory | null>(null);

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
              <Label htmlFor="exp-filter" className="text-xs text-muted-foreground">Filter by document</Label>
              <Select value={expFilter} onValueChange={setExpFilter}>
                <SelectTrigger id="exp-filter" className="h-8 w-[260px] text-xs">
                  <SelectValue placeholder="All documents" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All documents</SelectItem>
                  {searchDocs.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      {d.filename?.slice(0, 60) ?? d.id}
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
                isBackendOffline(error) ? (
                  <div className="p-3">
                    <BackendOffline compact />
                  </div>
                ) : (
                  <div className="p-4 text-xs text-destructive flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" /> Failed to load memories.
                  </div>
                )
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
                      <TableRow
                        key={m.id}
                        className="group cursor-pointer"
                        onClick={() => setDetail(m)}
                      >
                        <TableCell className="max-w-[200px]">
                          <span className="text-sm line-clamp-2">{m.queryText}</span>
                        </TableCell>
                        <TableCell className="max-w-[280px]">
                          <span className="text-xs text-muted-foreground line-clamp-2">
                            {m.chunkText ?? "—"}
                          </span>
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

      {detail && (
        <Sheet open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
          <SheetContent side="right" className="sm:max-w-lg overflow-y-auto thin-scroll">
            <SheetHeader>
              <SheetTitle className="text-base">Memory detail</SheetTitle>
              <SheetDescription className="text-xs">
                id: <span className="font-mono">{detail.id}</span>
              </SheetDescription>
            </SheetHeader>
            <div className="px-4 pb-6">
              <MemoryInspectionPane memory={detail} />
            </div>
          </SheetContent>
        </Sheet>
      )}
    </Card>
  );
}

// ─── Cart Detail Placeholder ────────────────────────────────────────────────
function CartDetailPlaceholder() {
  return (
    <Card className="border-dashed">
      <CardContent className="pt-10 pb-10 flex flex-col items-center justify-center text-center min-h-[400px]">
        <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center mb-3">
          <ShoppingCart className="h-5 w-5 text-primary" />
        </div>
        <p className="text-sm font-medium">Select a cart to inspect its memories</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-xs">
          Pick a cart from the sidebar — the inspection pane will show its
          memories with a large, readable chunk-text view and a resizable
          scores panel.
        </p>
      </CardContent>
    </Card>
  );
}

// ─── Mobile Carts Sheet ────────────────────────────────────────────────────
function MobileCartsSheet({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5 lg:hidden">
          <Menu className="h-4 w-4" />
          Carts
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[280px] sm:max-w-[280px] overflow-y-auto thin-scroll">
        <SheetHeader>
          <SheetTitle className="text-base">Memory Carts</SheetTitle>
          <SheetDescription className="text-xs">Pick a cart to inspect.</SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6 mt-2">
          <CreateCartCard onCreated={(id) => { onSelect(id); setOpen(false); }} />
          <div className="mt-3">
            <CartsList
              selectedId={selectedId}
              onSelect={(id) => { onSelect(id); setOpen(false); }}
              compact
            />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ─── Main View ──────────────────────────────────────────────────────────────
export function MemoryView() {
  const [selectedCartId, setSelectedCartId] = React.useState<string | null>(null);

  return (
    <>
      <ViewHeader
        title="Memory Cart"
        description="Inspect retrieval memories with a large, comfortable reading pane"
        icon={ShoppingCart}
      />
      <ViewBody className="space-y-4">
        {/* Mobile: carts in a Sheet (button bar above the detail) */}
        <div className="lg:hidden">
          <MobileCartsSheet selectedId={selectedCartId} onSelect={setSelectedCartId} />
        </div>

        {/* Desktop: carts sidebar | cart detail (dominant inspection area) */}
        <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
          {/* Left column — desktop only (mobile uses the Sheet) */}
          <div className="hidden lg:flex lg:flex-col gap-4">
            <CreateCartCard onCreated={setSelectedCartId} />
            <CartsList selectedId={selectedCartId} onSelect={setSelectedCartId} />
          </div>

          {/* Right column — cart detail (dominant) */}
          <div className="min-h-0">
            {selectedCartId ? (
              <CartDetail cartId={selectedCartId} />
            ) : (
              <CartDetailPlaceholder />
            )}
          </div>
        </div>

        {/* All-memories browser (collapsible, below) */}
        <AllMemoriesSection />
      </ViewBody>
    </>
  );
}
