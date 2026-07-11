import type { Metadata } from "next";
import { RagShell } from "@/components/rag/RagShell";
import "../../styles/cyberpunk-tokens.css";
import "./rag.css";

export const metadata: Metadata = {
  title: "RAG Console",
};

export default function RagLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="rag-root">
      <RagShell>{children}</RagShell>
    </div>
  );
}
