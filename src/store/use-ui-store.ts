/**
 * Client UI state (Zustand). Per Frontend_Workflow_Mapping v1.1 §5:
 *   • Server state → TanStack Query (experiments, documents, search results, carts)
 *   • Client state → Zustand (current view, selected chunks for cart, filters)
 */
import { create } from "zustand";

export type ViewKey = "dashboard" | "ingest" | "search" | "memory" | "experiments";

interface UIState {
  view: ViewKey;
  setView: (v: ViewKey) => void;
  // Search → cart selection (memory ids pending add to a cart)
  pendingMemoryIds: string[];
  togglePending: (id: string) => void;
  clearPending: () => void;
  // Active experiment (for search context)
  activeExperimentId: string | null;
  setActiveExperiment: (id: string | null) => void;
  // Theme
  theme: "light" | "dark";
  toggleTheme: () => void;
  setTheme: (t: "light" | "dark") => void;
}

export const useUIStore = create<UIState>((set) => ({
  view: "dashboard",
  setView: (v) => set({ view: v }),
  pendingMemoryIds: [],
  togglePending: (id) =>
    set((s) => ({
      pendingMemoryIds: s.pendingMemoryIds.includes(id)
        ? s.pendingMemoryIds.filter((x) => x !== id)
        : [...s.pendingMemoryIds, id],
    })),
  clearPending: () => set({ pendingMemoryIds: [] }),
  activeExperimentId: null,
  setActiveExperiment: (id) => set({ activeExperimentId: id }),
  theme: "light",
  toggleTheme: () => set((s) => ({ theme: s.theme === "light" ? "dark" : "light" })),
  setTheme: (t) => set({ theme: t }),
}));
