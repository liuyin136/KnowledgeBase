"use client";

import { useUIStore, type ViewKey } from "@/store/use-ui-store";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Upload,
  Search,
  ShoppingCart,
  FlaskConical,
  Moon,
  Sun,
  Database,
  Settings,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useEffect } from "react";

const NAV: { key: ViewKey; label: string; icon: React.ComponentType<{ className?: string }>; desc: string }[] = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard, desc: "System health & quick stats" },
  { key: "ingest", label: "Ingest", icon: Upload, desc: "Upload & embed documents" },
  { key: "search", label: "Hybrid Search", icon: Search, desc: "Tunable retrieval" },
  { key: "memory", label: "Memory Cart", icon: ShoppingCart, desc: "Curate retrieval results" },
  { key: "experiments", label: "Experiments", icon: FlaskConical, desc: "History & comparison" },
  { key: "settings", label: "Settings", icon: Settings, desc: "Active models & how to switch" },
];

export function Sidebar() {
  const { view, setView, theme, toggleTheme } = useUIStore();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-5 py-5 border-b">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Database className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold">RAG Lab</div>
          <div className="text-[11px] text-muted-foreground">v1 · Local-First</div>
        </div>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map((item) => {
          const active = view === item.key;
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              onClick={() => setView(item.key)}
              className={cn(
                "w-full flex items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "hover:bg-sidebar-accent/60 text-sidebar-foreground/80",
              )}
            >
              <Icon className={cn("h-4.5 w-4.5 mt-0.5 shrink-0", active && "text-primary")} />
              <div className="min-w-0">
                <div className={cn("text-sm font-medium", active && "text-primary")}>{item.label}</div>
                <div className="text-[11px] text-muted-foreground truncate">{item.desc}</div>
              </div>
            </button>
          );
        })}
      </nav>
      <div className="border-t px-3 py-3 space-y-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleTheme}
          className="w-full justify-start gap-2 text-sidebar-foreground/70"
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </Button>
        <div className="px-3 py-1.5 text-[10px] text-muted-foreground/70 leading-relaxed">
          v1.3 · Jina v5 default + BGE-M3 toggle · Standard paths only. No Late/Agentic chunking, no Structured Chat, no GraphRAG.
        </div>
      </div>
    </aside>
  );
}

export function MobileNav() {
  const { view, setView } = useUIStore();
  return (
    <div className="md:hidden sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="flex items-center gap-1 overflow-x-auto px-2 py-2 thin-scroll">
        {NAV.map((item) => {
          const active = view === item.key;
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              onClick={() => setView(item.key)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors",
                active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
