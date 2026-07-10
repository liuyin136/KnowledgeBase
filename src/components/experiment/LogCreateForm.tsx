"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  CATEGORY_LABELS,
  type Category,
  createLog,
} from "@/lib/api/files";

const FIELD_CONFIG: Record<
  Category,
  { key: keyof import("@/lib/api/files").CreateLogRequest; label: string }[]
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

  const updateField = (key: string, value: string) => {
    setFields((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!category) {
      setError("Select a log type first.");
      return;
    }
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const body = {
        category,
        title: title.trim(),
        ...fields,
      };
      const res = await createLog(body);
      router.push(
        `/experiment/edit/${res.path.split("/").map(encodeURIComponent).join("/")}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create log");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <p className="cp-label">Step 1 — Select log type</p>
      <div className="cp-type-grid">
        {(Object.keys(CATEGORY_LABELS) as Category[]).map((cat) => (
          <button
            key={cat}
            type="button"
            className={`cp-type-btn${category === cat ? " active" : ""}`}
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
          <p className="cp-label">Step 2 — Fill in details</p>
          <div className="cp-field">
            <label className="cp-label" htmlFor="log-title">
              Title *
            </label>
            <input
              id="log-title"
              className="cp-input"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          {FIELD_CONFIG[category].map(({ key, label }) => (
            <div key={key} className="cp-field">
              <label className="cp-label" htmlFor={key}>
                {label}
              </label>
              <textarea
                id={key}
                className="cp-textarea"
                value={fields[key] ?? ""}
                onChange={(e) => updateField(key, e.target.value)}
              />
            </div>
          ))}
        </>
      )}

      {error && <div className="cp-error">{error}</div>}

      <div className="cp-actions">
        <button
          type="submit"
          className="cp-btn cp-btn-primary"
          disabled={!category || submitting}
        >
          {submitting ? "Creating..." : "Create Log"}
        </button>
      </div>
    </form>
  );
}
