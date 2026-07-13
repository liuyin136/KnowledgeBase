"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MemorySavePanel } from "@/components/rag/MemorySavePanel";
import { loadMemorySearchSession, type MemorySearchSession } from "@/lib/api/memorySession";

export default function RagMemoryPage() {
  const [session, setSession] = useState<MemorySearchSession | null>(null);

  useEffect(() => {
    setSession(loadMemorySearchSession());
  }, []);

  if (!session || session.hits.length === 0) {
    return (
      <main className="rag-page">
        <h1>Graph memory</h1>
        <p>
          No search session found. Run a search on{" "}
          <Link href="/rag/search" className="cp-link">
            /rag/search
          </Link>{" "}
          first, then return here to select hits and save manually.
        </p>
      </main>
    );
  }

  return (
    <main className="rag-page">
      <h1>Graph memory</h1>
      <MemorySavePanel session={session} />
    </main>
  );
}
