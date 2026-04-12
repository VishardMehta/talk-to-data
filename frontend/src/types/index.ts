export type ChartType = "bar" | "line" | "pie" | "histogram" | "stat_card" | "table";

export interface QueryResult {
  question: string;
  interpreted_as?: string;
  answer: string;
  sql?: string;
  table_name?: string;
  chart_type?: ChartType;
  data?: Record<string, unknown>[];
  x_key?: string;
  y_key?: string;
  name_key?: string;
  value_key?: string;
  columns?: string[];
  rows?: unknown[][];
  follow_ups?: string[];
  confidence?: number;
  cached?: boolean;
  time_ms?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  queryResult?: QueryResult;
  thinkingSteps?: ThinkingStep[];
}

export interface ThinkingStep {
  id: string;
  type: "routing" | "sql" | "executing" | "answering" | "complete" | "error";
  message: string;
  detail?: string;
  status: "pending" | "active" | "done" | "error";
  timestamp: number;
}

export interface MetricCard {
  label: string;
  value: string;
  change?: string;
  trend?: "up" | "down" | "neutral";
}
