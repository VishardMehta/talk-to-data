/** API client for the upload-only FastAPI backend. */

import type { ThinkingStep, QueryResult } from "@/types";

const API_BASE = "http://localhost:8000/api";

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function uploadFile(
  file: File,
  sessionId: string
): Promise<{ success: boolean; message: string; filename?: string; rows?: number; columns?: number; suggested_questions?: string[] }> {
  const form = new FormData();
  form.append("file", file);
  form.append("session_id", sessionId);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    return { success: false, message: err.detail ?? "Upload failed" };
  }

  return res.json();
}

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
    try {
      const res = await fetch(`${API_BASE}/query/stream`, {
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
            // ignore parse errors
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

function handleStreamEvent(event: Record<string, unknown>, callbacks: StreamCallbacks) {
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
    const res = await fetch(`${API_BASE}/query`, {
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
    await fetch(`${API_BASE}/session/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch {
    // best effort
  }
}
