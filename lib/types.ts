export type CitationType =
  | "numeric"
  | "market"
  | "narrative"
  | "earnings"
  | "sentiment"
  | "insider";

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
  as_of?: string;
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
  model?: string;
  tier?: "tier1" | "tier2";
  escalated?: boolean;
  escalation_reason?: string;
}

export interface TierBreakdown {
  supervisor_model: string;
  tier1_model: string;
  tier2_model: string;
  tier1_agents: string[];
  tier2_agents: string[];
  escalated_agents: string[];
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
  tier?: "tier1" | "tier2";
  escalated?: boolean;
  escalation_reason?: string;
  tier_breakdown?: TierBreakdown;
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
  period?: string;
  period_end?: string;
  Revenue?: number | null;
  "Gross Profit"?: number | null;
  "R&D Expense"?: number | null;
  "SG&A Expense"?: number | null;
  "Operating Income"?: number | null;
  "Net Income"?: number | null;
  "Diluted EPS"?: number | null;
  "Cash & Equivalents"?: number | null;
  "Total Assets"?: number | null;
  "Long-Term Debt"?: number | null;
  "Total Liabilities"?: number | null;
  "Stockholders Equity"?: number | null;
  "Net Cash"?: number | null;
  "Operating Cash Flow"?: number | null;
  CapEx?: number | null;
  "Free Cash Flow"?: number | null;
  "Share Repurchases"?: number | null;
  "Dividends Paid"?: number | null;
  "Gross Margin %"?: number | null;
  "Operating Margin %"?: number | null;
  "Net Margin %"?: number | null;
  "FCF Margin %"?: number | null;
  "ROE %"?: number | null;
  "Debt / Equity"?: number | null;
}

export interface TickerSearchResult {
  ticker: string;
  company_name: string;
  exchange?: string;
  tradingview_symbol?: string;
  price?: number | null;
  change_pct?: number | null;
  market_cap?: number | null;
  sector?: string;
}

export interface LiveQuote {
  ticker: string;
  company_name?: string;
  exchange?: string;
  sector?: string;
  suggested_peers?: string[];
  tradingview_symbol?: string;
  currency?: string;
  as_of?: string;
  price?: number | null;
  previous_close?: number | null;
  change?: number | null;
  change_pct?: number | null;
  volume?: number | null;
  fifty_two_week_high?: number | null;
  fifty_two_week_low?: number | null;
  market_cap?: number | null;
  enterprise_value?: number | null;
  trailing_pe?: number | null;
  forward_pe?: number | null;
  ev_to_ebitda?: number | null;
  price_to_book?: number | null;
  dividend_yield?: number | null;
  beta?: number | null;
  analyst_target_mean?: number | null;
  analyst_target_high?: number | null;
  analyst_target_low?: number | null;
  recommendation?: string;
  analyst_count?: number | null;
}

export interface OhlcvCandle {
  time: number | string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LiveChartResponse {
  ticker: string;
  timeframe: string;
  is_intraday: boolean;
  tradingview_symbol: string;
  period_change_pct?: number | null;
  candles: OhlcvCandle[];
  quote: LiveQuote;
  error?: string;
}

export interface MarketBenchmark {
  symbol: string;
  label: string;
  tradingview_symbol: string;
  price: number | null;
  change_pct: number | null;
}

export interface MarketHeadline {
  title: string;
  publisher: string;
  age: string;
  url: string;
}

export interface MarketRecapResponse {
  as_of: string;
  model: string;
  benchmarks: MarketBenchmark[];
  recap_markdown: string;
  citations: Citation[];
  headlines: MarketHeadline[];
  error?: string;
}

export interface StreamStep {
  id: string;
  timestamp: number;
  type:
    | "plan"
    | "specialist_start"
    | "tier_escalation"
    | "tool_call"
    | "specialist_done"
    | "synthesizing"
    | "guard_check";
  label: string;
  detail?: string;
  role?: string;
  ticker?: string;
  model?: string;
  escalated?: boolean;
}
