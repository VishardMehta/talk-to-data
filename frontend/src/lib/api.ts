/** API client for the Talk-To-Data FastAPI backend. */

import type { ThinkingStep, QueryResult } from "@/types";

const ENV_API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();

// In local dev the Vite proxy forwards /api/* to http://127.0.0.1:8000.
// A relative "/api" base means the browser stays on the same origin and
// never needs CORS headers — the proxy handles it transparently.
// Direct addresses are kept as fallbacks for production or non-proxied setups.
const DEFAULT_API_BASE = "/api";
const API_BASE_CANDIDATES = Array.from(
  new Set(
    [
      ENV_API_BASE,
      DEFAULT_API_BASE,           // relative — goes through Vite proxy in dev
      "http://127.0.0.1:8000/api",// direct backend for production / no-proxy
      "http://localhost:8000/api",
    ].filter(Boolean)
  )
) as string[];

let resolvedApiBase: string | null = null;

function buildUploadFormData(files: File[], sessionId: string): FormData {
  const form = new FormData();
  for (const f of files) {
    form.append("files", f);
  }
  form.append("session_id", sessionId);
  return form;
}

function estimateUploadTimeoutMs(files: File[]): number {
  const totalBytes = files.reduce((sum, f) => sum + (f.size || 0), 0);
  const totalMB = totalBytes / (1024 * 1024);
  const baseMs = 5 * 60 * 1000;
  const perMbMs = 12 * 1000;
  const timeout = Math.round(baseMs + totalMB * perMbMs);
  return Math.max(5 * 60 * 1000, Math.min(timeout, 20 * 60 * 1000));
}

function isRetryableUploadError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const name = (err.name || "").toLowerCase();
  const msg = (err.message || "").toLowerCase();
  if (name.includes("abort") || name.includes("timeout")) return true;
  return (
    msg.includes("bodystreambuffer was aborted")
    || msg.includes("networkerror")
    || msg.includes("failed to fetch")
    || msg.includes("connection")
    || msg.includes("timed out")
    || msg.includes("stream ended without final result")
  );
}

async function probeApiBase(base: string): Promise<boolean> {
  try {
    const res = await fetch(`${base}/health`, {
      signal: AbortSignal.timeout(1500),
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function resolveApiBase(): Promise<string> {
  if (resolvedApiBase) return resolvedApiBase;

  for (const base of API_BASE_CANDIDATES) {
    if (await probeApiBase(base)) {
      resolvedApiBase = base;
      return base;
    }
  }

  resolvedApiBase = ENV_API_BASE || DEFAULT_API_BASE;
  return resolvedApiBase;
}

function resetResolvedApiBase() {
  resolvedApiBase = null;
}

export async function checkBackendHealth(): Promise<boolean> {
  for (const base of API_BASE_CANDIDATES) {
    if (await probeApiBase(base)) {
      resolvedApiBase = base;
      return true;
    }
  }
  return false;
}

export interface UploadedTableInfo {
  name: string;
  filename: string;
  rows: number;
  columns: number;
  /** True when the backend served this table from its in-session cache (unchanged content) */
  reused?: boolean;
}

export interface UploadResult {
  success: boolean;
  message: string;
  /** All tables loaded (multi-file) */
  tables?: UploadedTableInfo[];
  /** How many tables were freshly ingested vs reused from session cache */
  loaded_count?: number;
  reused_count?: number;
  /** Legacy single-file compat */
  filename?: string;
  rows?: number;
  columns?: number;
  suggested_questions?: string[];
  suggestions_deferred?: boolean;
  fast_mode?: boolean;
  errors?: string[];
}

export interface UploadProgressEvent {
  percent: number;
  stage: string;
  message: string;
  filename?: string;
  table_name?: string;
}

/**
 * Upload one or more files to the backend.
 * Files are loaded into in-memory DuckDB tables and never persisted to disk.
 */
export async function uploadFiles(
  files: File[],
  sessionId: string
): Promise<UploadResult> {
  const apiBase = await resolveApiBase();
  const timeoutMs = Math.max(180_000, estimateUploadTimeoutMs(files));
  const form = buildUploadFormData(files, sessionId);

  try {
    const res = await fetch(`${apiBase}/upload`, {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(timeoutMs),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      return { success: false, message: err.detail ?? "Upload failed" };
    }

    return res.json();
  } catch (err) {
    if (err instanceof Error && err.name === "TimeoutError") {
      return { success: false, message: "Upload timed out — file may be too large or backend is slow." };
    }
    if (err instanceof TypeError) {
      resetResolvedApiBase();
      return {
        success: false,
        message: "Cannot reach backend API. Ensure backend is running and CORS allows this frontend port.",
      };
    }
    return {
      success: false,
      message: err instanceof Error ? err.message : "Upload failed",
    };
  }
}

/**
 * Upload files and receive true backend stage progress via SSE.
 */
export async function uploadFilesWithProgress(
  files: File[],
  sessionId: string,
  onProgress: (event: UploadProgressEvent) => void
): Promise<UploadResult> {
  const apiBase = await resolveApiBase();
  const timeoutMs = Math.max(300_000, estimateUploadTimeoutMs(files));
  let lastError: unknown = null;

  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      if (attempt > 1) {
        onProgress({
          percent: 1,
          stage: "dataset_uploaded",
          message: "Upload stream interrupted. Retrying once...",
        });
      }

      const res = await fetch(`${apiBase}/upload/stream`, {
        method: "POST",
        body: buildUploadFormData(files, sessionId),
        signal: AbortSignal.timeout(timeoutMs),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        return { success: false, message: err.detail ?? "Upload failed" };
      }

      if (!res.body) {
        return { success: false, message: "Upload stream unavailable" };
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalResult: UploadResult | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!value) continue;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw || raw === "[DONE]") continue;

          let event: Record<string, unknown>;
          try {
            event = JSON.parse(raw);
          } catch {
            continue;
          }

          if (event.type === "upload_progress") {
            onProgress({
              percent: Number(event.percent ?? 0),
              stage: String(event.stage ?? "processing"),
              message: String(event.message ?? "Processing..."),
              filename: event.filename ? String(event.filename) : undefined,
              table_name: event.table_name ? String(event.table_name) : undefined,
            });
          } else if (event.type === "upload_result") {
            finalResult = event.data as UploadResult;
          } else if (event.type === "error") {
            return {
              success: false,
              message: String(event.message ?? "Upload failed"),
            };
          }
        }
      }

      if (finalResult) return finalResult;

      throw new Error("Upload stream ended without final result");
    } catch (err) {
      lastError = err;
      if (attempt < 2 && isRetryableUploadError(err)) {
        continue;
      }
      break;
    }
  }

  const fallback = await uploadFiles(files, sessionId);
  if (fallback.success) return fallback;

  if (lastError instanceof TypeError) {
    resetResolvedApiBase();
    return {
      success: false,
      message: "Cannot reach backend API. Ensure backend is running and CORS allows this frontend port.",
    };
  }

  if (lastError instanceof Error && isRetryableUploadError(lastError)) {
    return {
      success: false,
      message: `${lastError.message}. ${fallback.message || "Upload failed after one automatic retry."}`,
    };
  }

  return {
    success: false,
    message: fallback.message || (lastError instanceof Error ? lastError.message : "Upload failed"),
  };
}

/** Convenience wrapper for a single file (backward compat) */
export async function uploadFile(
  file: File,
  sessionId: string
): Promise<UploadResult> {
  return uploadFiles([file], sessionId);
}

// ── Streaming query ────────────────────────────────────────────────────────

export interface StreamCallbacks {
  onThinkingStep: (step: ThinkingStep) => void;
  onThinkingUpdate: (id: string, patch: Partial<ThinkingStep>) => void;
  onResult: (result: QueryResult) => void;
  onError: (message: string) => void;
}

/**
 * Stream a query via Server-Sent Events.
 * Returns a function to abort the stream.
 */
export function streamQuery(
  question: string,
  sessionId: string,
  dataSource: string,
  callbacks: StreamCallbacks
): () => void {
  const controller = new AbortController();

  const run = async () => {
    const apiBase = await resolveApiBase();
    try {
      const res = await fetch(`${apiBase}/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          session_id: sessionId,
          data_source: dataSource,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Query failed" }));
        callbacks.onError(err.detail ?? "Query failed");
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw || raw === "[DONE]") continue;

          try {
            const event = JSON.parse(raw);
            handleStreamEvent(event, callbacks);
          } catch {
            // ignore parse errors on malformed lines
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") {
        callbacks.onError(err.message ?? "Connection lost");
      }
    }
  };

  run();
  return () => controller.abort();
}

function handleStreamEvent(
  event: Record<string, unknown>,
  callbacks: StreamCallbacks
) {
  if (event.type === "thinking_step") {
    callbacks.onThinkingStep({
      id: String(event.id),
      type: event.step_type as ThinkingStep["type"],
      message: String(event.message),
      detail: event.detail ? String(event.detail) : undefined,
      status: "active",
      timestamp: Date.now(),
    });
  } else if (event.type === "thinking_done") {
    callbacks.onThinkingUpdate(String(event.id), { status: "done" });
  } else if (event.type === "result") {
    callbacks.onResult(event.data as QueryResult);
  } else if (event.type === "error") {
    callbacks.onError(String(event.message));
  }
}

/** Non-streaming fallback query */
export async function queryDirect(
  question: string,
  sessionId: string,
  dataSource: string
): Promise<QueryResult | null> {
  try {
    const apiBase = await resolveApiBase();
    const res = await fetch(`${apiBase}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        session_id: sessionId,
        data_source: dataSource,
      }),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function clearSession(sessionId: string): Promise<void> {
  try {
    const apiBase = await resolveApiBase();
    await fetch(`${apiBase}/session/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch {
    // best effort
  }
}

export interface RemoveTableResult {
  ok: boolean;
  removed: boolean;
  remaining_tables: number;
}

export async function removeUploadedTable(
  sessionId: string,
  tableName: string
): Promise<RemoveTableResult> {
  try {
    const apiBase = await resolveApiBase();
    const res = await fetch(`${apiBase}/session/remove-table`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        table_name: tableName,
      }),
    });

    if (!res.ok) {
      return { ok: false, removed: false, remaining_tables: -1 };
    }

    const data = await res.json();
    return {
      ok: Boolean(data.ok),
      removed: Boolean(data.removed),
      remaining_tables: Number(data.remaining_tables ?? 0),
    };
  } catch {
    return { ok: false, removed: false, remaining_tables: -1 };
  }
}
