"use client";

import { useMemo, useState } from "react";
import type { SearchHit } from "@/lib/api/search";
import { extractMemoryAndWait, type MemoryGraphJobResult } from "@/lib/api/memory";
import type { MemorySearchSession } from "@/lib/api/memorySession";

export function MemorySavePanel({ session }: { session: MemorySearchSession }) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MemoryGraphJobResult | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const selectedCount = selected.size;

  const hitsById = useMemo(() => {
    const map = new Map<string, SearchHit>();
    for (const hit of session.hits) {
      map.set(hit.chunk_id, hit);
    }
    return map;
  }, [session.hits]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onSave() {
    const grandchild_ids = Array.from(selected);
    if (grandchild_ids.length < 1) {
      setError("Select at least one search hit");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const jobResult = await extractMemoryAndWait({
        query_text: session.query,
        grandchild_ids,
        session_id: session.session_id,
        user_query_id: session.session_id,
      });
      setResult(jobResult);
      setConfirmOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rag-memory-panel">
      <header>
        <h2>Save to graph memory</h2>
        <p className="rag-memory-query">
          Query: <code>{session.query}</code>
        </p>
        <p className="rag-memory-meta">
          Session: <code>{session.session_id}</code>
          {session.span_id && (
            <>
              {" "}
              · span: <code>{session.span_id}</code>
            </>
          )}
        </p>
      </header>

      <ul className="rag-memory-hit-list">
        {session.hits.map((hit) => (
          <li key={hit.chunk_id} className="rag-memory-hit-row">
            <label>
              <input
                type="checkbox"
                checked={selected.has(hit.chunk_id)}
                onChange={() => toggle(hit.chunk_id)}
                disabled={busy}
              />
              <span className="rag-memory-hit-preview">{hit.content_preview}</span>
              <span className="rag-memory-hit-path">{hit.relative_path || hit.parent_path}</span>
            </label>
          </li>
        ))}
      </ul>

      <div className="rag-memory-actions">
        <button
          type="button"
          className="cp-link"
          disabled={busy || selectedCount === 0}
          onClick={() => setConfirmOpen(true)}
        >
          Save {selectedCount} hit{selectedCount === 1 ? "" : "s"} to memory
        </button>
      </div>

      {confirmOpen && (
        <div className="rag-memory-confirm" role="dialog" aria-modal="true">
          <p>
            Save <strong>{selectedCount}</strong> grandchild chunk
            {selectedCount === 1 ? "" : "s"} to the knowledge graph?
          </p>
          <div className="rag-memory-confirm-actions">
            <button type="button" className="cp-link" disabled={busy} onClick={() => setConfirmOpen(false)}>
              Cancel
            </button>
            <button type="button" className="cp-link" disabled={busy} onClick={onSave}>
              {busy ? "Extracting…" : "Confirm save"}
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="rag-error" role="alert">
          {error}
          {session.span_id && (
            <>
              {" "}
              (span: <code>{session.span_id}</code>)
            </>
          )}
        </p>
      )}

      {result && (
        <div className="rag-memory-result" aria-live="polite">
          <h3>Memory saved</h3>
          <ul>
            <li>
              memory_key: <code>{result.memory_key}</code>
            </li>
            <li>version: {result.version ?? 1}</li>
            <li>entities: {result.entities_created ?? 0}</li>
            <li>relations: {result.relations_created ?? 0}</li>
            <li>claims: {result.claims_created ?? 0}</li>
            <li>communities: {result.communities_created ?? 0}</li>
            <li>summaries: {result.summaries_created ?? 0}</li>
          </ul>
          <p>
            <a
              href="http://localhost:7474/browser/"
              target="_blank"
              rel="noopener noreferrer"
              className="cp-link"
            >
              Open Neo4j Browser
            </a>
          </p>
        </div>
      )}

      {selectedCount > 0 && (
        <details className="rag-memory-preview">
          <summary>Preview selected chunks</summary>
          <ul>
            {Array.from(selected).map((id) => {
              const hit = hitsById.get(id);
              return (
                <li key={id}>
                  <code>{id}</code> — {hit?.content_preview?.slice(0, 120)}
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </section>
  );
}
