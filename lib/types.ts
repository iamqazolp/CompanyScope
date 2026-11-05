export type CitationType = "numeric" | "narrative" | "earnings" | "sentiment";

export interface Citation {
  type: CitationType;
  ticker?: string;
  year?: number | string;
  concept?: string;
  section?: string;
  chunk_id?: string;
  quote?: string;
  source_context?: string;
  source_url?: string;
  verified_value?: number;
  unit?: string;
  filing_date?: string;
  form?: string;
}

export interface SubAgentReport {
  agent: string;
  role: string;
  ticker: string;
  answer: string;
  citations_count: number;
  self_corrections: number;
  cost_usd?: number;
}

export interface ToolTraceItem {
  agent?: string;
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

export interface QuotaStatus {
  limit: number;
  used: number;
  remaining: number;
  reset_at: string;
}

export interface QueryResult {
  answer: string;
  citations: Citation[];
  needs_clarification?: string;
  used_tools?: string[];
  tool_trace?: ToolTraceItem[];
  sub_agent_reports?: SubAgentReport[];
  self_corrections?: number;
  cost_usd?: number;
  model?: string;
  latency_ms?: number;
  trace_url?: string;
  report_slug?: string;
  quota?: QuotaStatus;
  error?: string;
}

export interface ShowcaseSummary {
  slug: string;
  title: string;
  category: string;
  question: string;
  tickers: string[];
  mode: string;
  citations_count: number;
  latency_ms: number;
}

export interface SavedReport {
  slug: string;
  title?: string;
  category?: string;
  question: string;
  tickers: string[];
  mode: string;
  result: QueryResult;
  is_showcase?: boolean;
  created_at: string;
}

export interface FinancialRow {
  year: number;
  Revenue?: number | null;
  "Net Income"?: number | null;
  "Operating Income"?: number | null;
  "Total Assets"?: number | null;
  "Total Liabilities"?: number | null;
  "Operating Cash Flow"?: number | null;
  "Free Cash Flow"?: number | null;
}

export interface StreamStep {
  id: string;
  timestamp: number;
  type:
    | "plan"
    | "specialist_start"
    | "tool_call"
    | "specialist_done"
    | "synthesizing"
    | "guard_check";
  label: string;
  detail?: string;
  role?: string;
  ticker?: string;
}
