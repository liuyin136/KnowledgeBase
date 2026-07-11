import { RagNav } from "./RagNav";

export function RagShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="rag-layout">
      <aside className="rag-sidebar">
        <h1 className="rag-title">RAG Console</h1>
        <RagNav />
      </aside>
      <main className="rag-main">{children}</main>
    </div>
  );
}
