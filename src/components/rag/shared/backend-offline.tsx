"use client";

/**
 * Shared "Backend offline" empty-state used across all views when an API call
 * returns BACKEND_UNAVAILABLE / BACKEND_UNREACHABLE (HTTP 503).
 *
 * v1.2 pivot: the real backend is FastAPI + Neo4j (Docker stack). In this
 * sandbox the stack is typically down, so we show a friendly, actionable
 * banner instead of a generic "Failed to load" message.
 */

import * as React from "react";
import { ServerOff, RefreshCw, ExternalLink, Terminal } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export interface BackendOfflineProps {
  /** Optional title override. Defaults to "Backend offline". */
  title?: string;
  /** Optional message override. Defaults to the docker-compose guidance. */
  message?: string;
  /** Retry callback. If omitted, the Retry button is hidden. */
  onRetry?: () => void;
  /** Show the inline docker-compose hint block (default: true). */
  showHint?: boolean;
  /** Compact variant: less vertical padding (default: false). */
  compact?: boolean;
}

const DEFAULT_MESSAGE =
  "The FastAPI backend is not reachable. Start the Docker stack (`docker compose up -d`) and ensure Neo4j + Redis + the backend service are healthy.";

export function BackendOffline({
  title = "Backend offline",
  message = DEFAULT_MESSAGE,
  onRetry,
  showHint = true,
  compact = false,
}: BackendOfflineProps) {
  return (
    <Alert
      variant="default"
      className={
        "border-amber-500/40 bg-amber-500/5 text-amber-900 dark:text-amber-200 " +
        (compact ? "py-3" : "py-6")
      }
      role="alert"
    >
      <ServerOff className="h-4 w-4 text-amber-600 dark:text-amber-400" />
      <AlertTitle className="flex items-center gap-2 text-amber-900 dark:text-amber-100">
        {title}
        <span className="text-[10px] font-mono uppercase tracking-wide text-amber-700/70 dark:text-amber-300/70">
          HTTP 503
        </span>
      </AlertTitle>
      <AlertDescription className="text-amber-900/80 dark:text-amber-200/80">
        <p className="leading-relaxed">{message}</p>
        {showHint && (
          <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-amber-700/80 dark:text-amber-300/80 mb-1">
              <Terminal className="h-3 w-3" />
              Quick start
            </div>
            <code className="text-xs font-mono text-amber-900 dark:text-amber-100 break-all">
              docker compose up -d
            </code>
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {onRetry && (
            <Button
              size="sm"
              variant="outline"
              onClick={onRetry}
              className="gap-1.5 border-amber-500/40 text-amber-900 hover:bg-amber-500/10 dark:text-amber-100"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry
            </Button>
          )}
          <a
            href="/api/v1/neo4j/health"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/40 px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-500/10 dark:text-amber-100"
          >
            <ExternalLink className="h-3 w-3" />
            Check Neo4j health
          </a>
        </div>
      </AlertDescription>
    </Alert>
  );
}

/**
 * Convenience wrapper for query-failure states. Picks between BackendOffline
 * (when the error is a 503 backend-offline) and a generic error message.
 */
export function QueryErrorBanner({
  error,
  onRetry,
  title,
  message,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  message?: string;
}) {
  // Lazily import the helper to avoid a circular dep at module load.
  const isOffline =
    typeof window !== "undefined" &&
    // Lightweight duck-type without importing the helper (keeps this file
    // dependency-free of api-client).
    error !== null &&
    typeof error === "object" &&
    ((error as { code?: string }).code === "BACKEND_UNAVAILABLE" ||
      (error as { code?: string }).code === "BACKEND_UNREACHABLE");

  if (isOffline) {
    return <BackendOffline title={title} message={message} onRetry={onRetry} />;
  }

  const msg =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "Unknown error";

  return (
    <Alert variant="destructive">
      <AlertTitle>Something went wrong</AlertTitle>
      <AlertDescription className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-xs font-mono break-all">{msg}</span>
        {onRetry && (
          <Button size="sm" variant="outline" onClick={onRetry}>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
