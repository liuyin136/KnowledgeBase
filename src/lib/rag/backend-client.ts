/**
 * Backend client — proxies all /api/v1/* requests to the FastAPI backend
 * (the real RAG engine: Neo4j + BGE-M3 + Redis). In Docker, BACKEND_URL points
 * to http://backend:8000. In the sandbox (no backend), requests fail with a
 * clear 503 "BACKEND_UNAVAILABLE" error so the frontend can show offline state.
 *
 * Per infrastructure-environment-spec_v1.1.md: the FastAPI backend owns all
 * RAG logic; the Next.js app is the frontend + thin proxy layer.
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || ""; // e.g. "http://backend:8000"

export function isBackendConfigured(): boolean {
  return Boolean(BACKEND_URL);
}

/**
 * Proxy a request to the FastAPI backend, forwarding method/body/query.
 * Returns the backend's JSON response + status. If the backend is unreachable
 * or unconfigured, returns a standardized 503 error body.
 */
export async function proxyToBackend(
  req: NextRequest,
  path: string,
  opts?: { method?: string; body?: unknown; forwardQuery?: boolean },
): Promise<NextResponse> {
  if (!BACKEND_URL) {
    return NextResponse.json(
      {
        error: {
          code: "BACKEND_UNAVAILABLE",
          message:
            "FastAPI backend is not configured. Set BACKEND_URL (e.g. http://backend:8000) and start the Docker stack (neo4j + redis + backend). The Next.js frontend is a thin proxy; all RAG logic lives in the FastAPI backend.",
          details: { hint: "Run: docker compose up -d  (see /docker/docker-compose.yml)" },
        },
      },
      { status: 503 },
    );
  }
  const url = new URL(req.url);
  const qs = opts?.forwardQuery === false ? "" : url.search;
  const target = `${BACKEND_URL}${path}${qs}`;
  try {
    const init: RequestInit = {
      method: opts?.method || req.method,
      headers: { "Content-Type": "application/json" },
    };
    if (opts?.body !== undefined) {
      init.body = JSON.stringify(opts.body);
    } else if (req.method !== "GET" && req.method !== "DELETE") {
      // Forward the incoming body for POST/PATCH/PUT
      const text = await req.text();
      if (text) init.body = text;
    }
    // Forward multipart untouched
    if (req.method === "POST") {
      const ct = req.headers.get("content-type") || "";
      if (ct.includes("multipart/form-data")) {
        const form = await req.formData();
        init.headers = {}; // let fetch set the multipart boundary
        init.body = form;
      }
    }
    const upstream = await fetch(target, init);
    const text = await upstream.text();
    const data = text ? JSON.parse(text) : null;
    return NextResponse.json(data, { status: upstream.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Network error";
    return NextResponse.json(
      {
        error: {
          code: "BACKEND_UNREACHABLE",
          message: `Cannot reach FastAPI backend at ${BACKEND_URL}: ${message}`,
          details: { backendUrl: BACKEND_URL, target },
        },
      },
      { status: 503 },
    );
  }
}

/** Backend health check (for Dashboard system card). */
export async function backendHealth(): Promise<{
  status: "online" | "offline";
  detail?: unknown;
}> {
  if (!BACKEND_URL) return { status: "offline" };
  try {
    const res = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return { status: "offline" };
    const data = await res.json().catch(() => ({}));
    return { status: "online", detail: data };
  } catch {
    return { status: "offline" };
  }
}
