"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  CATEGORY_LABELS,
  type Category,
  type CreateLogRequest,
  createLog,
} from "@/lib/api/files";
import { pollJobUntilDone } from "@/lib/api/jobs";

const FIELD_CONFIG: Record<
  Category,
  { key: keyof CreateLogRequest; label: string }[]
> = {
  RND: [
    { key: "environment", label: "Environment" },
    { key: "execution_step", label: "Execution Step" },
    { key: "results", label: "Results / Observation" },
    { key: "next_steps", label: "Next Steps" },
  ],
  case: [
    { key: "symptom", label: "Symptom" },
    { key: "error_log", label: "Error Log" },
    { key: "investigation", label: "Investigation" },
    { key: "solution", label: "Solution" },
    { key: "note", label: "Note" },
  ],
  Daily: [
    { key: "done", label: "Done" },
    { key: "todo", label: "TODO" },
    { key: "blocker", label: "Blocker" },
  ],
};

export function LogCreateForm() {
  const router = useRouter();
  const [category, setCategory] = useState<Category | null>(null);
  const [title, setTitle] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!category || !title.trim()) {
      setError("Category and title are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setToast(null);
    try {
      const res = await createLog({ category, title: title.trim(), ...fields });
      if (res.ingest_job_id) {
        const job = await pollJobUntilDone(res.ingest_job_id, { timeoutMs: 300_000 });
        if (job.status === "failed") {
          throw new Error(job.error || "Ingest job failed");
        }
      }
      setToast("Document created and indexed.");
      router.push("/rag/library");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create document");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rag-panel">
      <p>Select document type</p>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
        {(Object.keys(CATEGORY_LABELS) as Category[]).map((cat) => (
          <button
            key={cat}
            type="button"
            className="rag-button"
            onClick={() => {
              setCategory(cat);
              setFields({});
            }}
          >
            {CATEGORY_LABELS[cat]}
          </button>
        ))}
      </div>
      {category && (
        <>
          <label htmlFor="rag-title">Title</label>
          <input
            id="rag-title"
            className="rag-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
          {FIELD_CONFIG[category].map(({ key, label }) => (
            <div key={key} style={{ marginTop: "0.75rem" }}>
              <label htmlFor={key}>{label}</label>
              <textarea
                id={key}
                className="rag-input"
                rows={4}
                value={fields[key] ?? ""}
                onChange={(e) => setFields((p) => ({ ...p, [key]: e.target.value }))}
              />
            </div>
          ))}
        </>
      )}
      {error && <div className="rag-error">{error}</div>}
      {toast && <div className="rag-toast">{toast}</div>}
      <button type="submit" className="rag-button" disabled={!category || submitting} style={{ marginTop: "1rem" }}>
        {submitting ? "Creating..." : "Create & Ingest"}
      </button>
    </form>
  );
}
