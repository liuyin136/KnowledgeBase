"use client";

import { useUIStore } from "@/store/use-ui-store";
import { Sidebar, MobileNav } from "@/components/rag/sidebar";
import { DashboardView } from "@/components/rag/views/dashboard-view";
import { IngestView } from "@/components/rag/views/ingest-view";
import { SearchView } from "@/components/rag/views/search-view";
import { MemoryView } from "@/components/rag/views/memory-view";
import { ExperimentsView } from "@/components/rag/views/experiments-view";
import { SettingsView } from "@/components/rag/views/settings-view";
import { Suspense } from "react";

export default function Home() {
  const view = useUIStore((s) => s.view);

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <MobileNav />
          <main className="flex-1 overflow-y-auto thin-scroll">
            <Suspense fallback={<div className="p-8 text-muted-foreground">Loading…</div>}>
              {view === "dashboard" && <DashboardView />}
              {view === "ingest" && <IngestView />}
              {view === "search" && <SearchView />}
              {view === "memory" && <MemoryView />}
              {view === "experiments" && <ExperimentsView />}
              {view === "settings" && <SettingsView />}
            </Suspense>
          </main>
        </div>
      </div>
      <footer className="border-t bg-background px-4 py-2.5 text-[11px] text-muted-foreground flex items-center justify-between gap-4 mt-auto">
        <span>
          RAG Lab v1.3 · Local-First · Embedding: <span className="font-mono">Jina v5 small</span> (default) · BGE-M3 toggle · Jina task-conditioned + Matryoshka 1024
        </span>
        <span className="hidden sm:inline">Standard paths only · 6-slice roadmap · Observability-first</span>
      </footer>
    </div>
  );
}
