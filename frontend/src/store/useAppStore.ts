import { create } from "zustand";
import type { ThinkingStep, QueryResult } from "@/types";

export type DataSource = "csv" | "database" | "sample" | "json" | null;

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  queryResult?: QueryResult;
  thinkingSteps?: ThinkingStep[];
}

// Re-export for backward compat
export type { ThinkingStep, QueryResult };
export type { MetricCard } from "@/types";
export type { ChartType } from "@/types";

// Legacy ChartData type for any remaining usages
export interface ChartData {
  type: "line" | "bar" | "pie";
  title: string;
  data: Record<string, unknown>[];
  xKey?: string;
  yKey?: string;
  nameKey?: string;
  valueKey?: string;
}

interface AppState {
  dataSource: DataSource;
  uploadedFile: File | null;
  uploadedFileName: string | null;
  sessionId: string;
  messages: Message[];
  isLoading: boolean;
  thinkingSteps: ThinkingStep[];
  sidebarCollapsed: boolean;
  backendAvailable: boolean;

  setDataSource: (source: DataSource) => void;
  setUploadedFile: (file: File | null) => void;
  addMessage: (msg: Message) => void;
  updateMessage: (id: string, patch: Partial<Message>) => void;
  setLoading: (v: boolean) => void;
  setThinkingSteps: (steps: ThinkingStep[]) => void;
  addThinkingStep: (step: ThinkingStep) => void;
  updateThinkingStep: (id: string, patch: Partial<ThinkingStep>) => void;
  clearThinkingSteps: () => void;
  toggleSidebar: () => void;
  clearChat: () => void;
  setBackendAvailable: (v: boolean) => void;
}

function generateSessionId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export const useAppStore = create<AppState>((set) => ({
  dataSource: null,
  uploadedFile: null,
  uploadedFileName: null,
  sessionId: generateSessionId(),
  messages: [],
  isLoading: false,
  thinkingSteps: [],
  sidebarCollapsed: false,
  backendAvailable: false,

  setDataSource: (source) => set({ dataSource: source }),
  setUploadedFile: (file) =>
    set({ uploadedFile: file, uploadedFileName: file?.name ?? null }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    })),
  setLoading: (v) => set({ isLoading: v }),
  setThinkingSteps: (steps) => set({ thinkingSteps: steps }),
  addThinkingStep: (step) =>
    set((s) => ({ thinkingSteps: [...s.thinkingSteps, step] })),
  updateThinkingStep: (id, patch) =>
    set((s) => ({
      thinkingSteps: s.thinkingSteps.map((step) =>
        step.id === id ? { ...step, ...patch } : step
      ),
    })),
  clearThinkingSteps: () => set({ thinkingSteps: [] }),
  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  clearChat: () => set({ messages: [], thinkingSteps: [] }),
  setBackendAvailable: (v) => set({ backendAvailable: v }),
}));
