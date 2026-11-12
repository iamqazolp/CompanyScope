"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Bot,
  Check,
  Clock,
  Cpu,
  ExternalLink,
  Layers,
  Loader2,
  Send,
  Share2,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import type {
  Citation,
  FinancialRow,
  QueryResult,
  QuotaStatus,
  SavedReport,
  ShowcaseSummary,
  StreamStep,
} from "@/lib/types";
import { citationBadgeLabel, formatResetCountdown } from "@/lib/format";
import { MarketRecapBar } from "./MarketRecapBar";
import { MarkdownView } from "./MarkdownView";
import { SourceInspector } from "./SourceInspector";
import { TradingViewChart } from "./TradingViewChart";

const POPULAR_TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"];

const QUICK_PROMPTS = [
  {
    label: "📈 Live Valuation vs. FCF & Insiders",
    ticker: "AAPL",
    peers: "",
    mode: "multi_agent",
    q: "Compare Apple's live Market Cap, Forward P/E, and recent SEC Form 4 insider trades against its FY2025 XBRL Free Cash Flow and Item 1A risks.",
  },
  {
    label: "AAPL vs. MSFT Peer Compare",
    ticker: "AAPL",
    peers: "MSFT",
    mode: "multi_agent",
    q: "Compare revenue scale, profitability, and primary AI and cloud risk disclosures between Apple and Microsoft.",
  },
  {
    label: "⚡ Multi-Year CAGR & Forensic Escalation",
    ticker: "AAPL",
    peers: "",
    mode: "multi_agent",
    q: "Calculate Apple's 3-year revenue CAGR from 2022 to 2025, analyze gross margin expansion, and reconcile any contradictions between 8-K commentary and 10-K antitrust/tariff risks.",
  },
  {
    label: "8-K Earnings & Street Pulse",
    ticker: "AAPL",
    peers: "",
    mode: "multi_agent",
    q: "Summarize Apple's 2025 8-K earnings release highlights alongside current Reddit investor sentiment and Yahoo Finance news headlines.",
  },
];

interface Props {
  initialReport?: SavedReport | null;
}

export function ResearchTerminal({ initialReport = null }: Props) {
  const [ticker, setTicker] = useState<string>(
    initialReport?.tickers?.[0] || "AAPL"
  );
  const [peerInput, setPeerInput] = useState<string>(
    initialReport?.tickers && initialReport.tickers.length > 1
      ? initialReport.tickers.slice(1).join(", ")
      : ""
  );
  const [mode, setMode] = useState<"multi_agent" | "auto" | "single">(
    (initialReport?.mode as "multi_agent" | "auto" | "single") || "multi_agent"
  );
  const [question, setQuestion] = useState<string>(
    initialReport?.question || ""
  );

  const [quota, setQuota] = useState<QuotaStatus>({
    limit: 5,
    used: 0,
    remaining: 5,
    reset_at: "",
  });
  const [engineInfo, setEngineInfo] = useState<{
    tier1Model: string;
    tier2Model: string;
    embedding: string;
    backend: string;
  }>({
    tier1Model: "gpt-6.1-terra",
    tier2Model: "gpt-6-luna",
    embedding: "gemini-embedding-2",
    backend: "pgvector",
  });

  const [showcases, setShowcases] = useState<ShowcaseSummary[]>([]);
  const [activeSlug, setActiveSlug] = useState<string | null>(
    initialReport?.slug || null
  );
  const [activeQuestion, setActiveQuestion] = useState<string>(
    initialReport?.question || ""
  );
  const [result, setResult] = useState<QueryResult | null>(
    initialReport?.result || null
  );
  const [selectedCitIdx, setSelectedCitIdx] = useState<number | null>(
    initialReport?.result?.citations?.length ? 0 : null
  );
  const [activeTab, setActiveTab] = useState<"synthesis" | "specialists">(
    "synthesis"
  );

  const [financials, setFinancials] = useState<FinancialRow[]>([]);
  const [finLoading, setFinLoading] = useState<boolean>(false);

  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [steps, setSteps] = useState<StreamStep[]>([]);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState<boolean>(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState<boolean>(false);
  const [inspectorOverride, setInspectorOverride] = useState<
    Citation[] | null
  >(null);

  // Initial bootstrap: health, quota, showcase list, and default showcase if empty
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const [hRes, qRes, sRes] = await Promise.all([
          fetch("/api/health"),
          fetch("/api/quota"),
          fetch("/api/showcase"),
        ]);
        if (!cancelled && hRes.ok) {
          const h = await hRes.json();
          setEngineInfo({
            tier1Model: h.tier1_model || h.model || "gpt-6.1-terra",
            tier2Model: h.tier2_model || "gpt-6-luna",
            embedding: h.embedding_model || "gemini-embedding-2",
            backend: h.vector_backend || "pgvector",
          });
        }
        if (!cancelled && qRes.ok) {
          const q = await qRes.json();
          if (typeof q.remaining === "number") setQuota(q);
        }
        if (!cancelled && sRes.ok) {
          const s = await sRes.json();
          const list: ShowcaseSummary[] = s.reports || [];
          setShowcases(list);
          // Auto-load first verified showcase on fresh visit so terminal feels alive immediately
          if (!initialReport && list.length > 0) {
            const firstRes = await fetch(`/api/reports/${list[0].slug}`);
            if (!cancelled && firstRes.ok) {
              const rep: SavedReport = await firstRes.json();
              setActiveSlug(rep.slug);
              setActiveQuestion(rep.question);
              setResult(rep.result);
              setSelectedCitIdx(rep.result.citations?.length ? 0 : null);
            }
          }
        }
      } catch {
        // Ignore transient offline errors during local boot
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, [initialReport]);

  // Fetch multi-year XBRL financials when primary ticker changes
  useEffect(() => {
    const clean = ticker.trim().toUpperCase();
    if (!clean || clean.length > 6) return;
    let cancelled = false;
    setFinLoading(true);
    fetch(`/api/financials/${encodeURIComponent(clean)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.financials)) {
          setFinancials(data.financials);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setFinLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const loadShowcase = useCallback(async (slug: string) => {
    setErrorBanner(null);
    try {
      const r = await fetch(`/api/reports/${encodeURIComponent(slug)}`);
      if (!r.ok) return;
      const rep: SavedReport = await r.json();
      if (rep.tickers?.[0]) setTicker(rep.tickers[0]);
      setPeerInput(rep.tickers?.length > 1 ? rep.tickers.slice(1).join(", ") : "");
      setActiveSlug(rep.slug);
      setActiveQuestion(rep.question);
      setResult(rep.result);
      setInspectorOverride(null);
      setSteps([]);
      setActiveTab("synthesis");
      setSelectedCitIdx(rep.result.citations?.length ? 0 : null);
    } catch {
      setErrorBanner("Failed to load showcase report.");
    }
  }, []);

  const runLiveQuery = useCallback(
    async (override?: {
      q: string;
      tkr: string;
      peers: string;
      m: "multi_agent" | "auto" | "single";
    }) => {
      const qText = (override ? override.q : question).trim();
      const primaryTkr = (override ? override.tkr : ticker)
        .trim()
        .toUpperCase() || "AAPL";
      const peersRaw = override ? override.peers : peerInput;
      const activeMode = override ? override.m : mode;

      if (!qText || isStreaming) return;

      const peerList = peersRaw
        .split(",")
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      const allTickers = Array.from(new Set([primaryTkr, ...peerList])).slice(
        0,
        4
      );

      setErrorBanner(null);
      setIsStreaming(true);
      setActiveQuestion(qText);
      setActiveSlug(null);
      setResult(null);
      setInspectorOverride(null);
      setSelectedCitIdx(null);
      setActiveTab("synthesis");
      setSteps([
        {
          id: "dispatch",
          timestamp: Date.now(),
          type: "plan",
          label: `Dispatching ${activeMode === "single" ? "Single-Agent" : "Multi-Agent Supervisor"} across ${allTickers.join(", ")}`,
        },
      ]);

      try {
        const resp = await fetch("/api/ask/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: qText,
            ticker: primaryTkr,
            tickers: allTickers.length > 1 ? allTickers : undefined,
            mode: activeMode,
          }),
        });

        if (resp.status === 429) {
          const errJson = await resp.json().catch(() => ({}));
          if (errJson.quota) setQuota(errJson.quota);
          setErrorBanner(
            errJson.error ||
              "Daily 5-query guest limit reached. Explore Showcase Reports above or return after 00:00 UTC."
          );
          setIsStreaming(false);
          return;
        }

        if (!resp.ok || !resp.body) {
          throw new Error(`Request failed (${resp.status})`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const frames = buffer.split("\n\n");
          buffer = frames.pop() || "";

          for (const frame of frames) {
            const line = frame
              .split("\n")
              .find((l) => l.startsWith("data: "));
            if (!line) continue;
            const rawData = line.slice(6).trim();
            if (rawData === "[DONE]") continue;

            try {
              const ev = JSON.parse(rawData);
              if (ev.type === "quota" && ev.quota) {
                setQuota(ev.quota);
              } else if (ev.type === "plan") {
                const planLabel =
                  ev.mode === "single"
                    ? `Single-Agent routed to ${ev.model || engineInfo.tier2Model}${
                        ev.escalated ? " (⚡ Demanding Task Escalation)" : ""
                      } for ${(ev.tickers || []).join(", ")}`
                    : `Tier-1 Supervisor (${
                        ev.supervisor_model || engineInfo.tier1Model
                      }) dispatched [${(ev.specialists || [])
                        .join(", ")
                        .toUpperCase()}] across ${(ev.tickers || []).join(", ")}`;
                setSteps((prev) => [
                  ...prev,
                  {
                    id: `plan-${Date.now()}`,
                    timestamp: Date.now(),
                    type: "plan",
                    model: ev.supervisor_model || ev.model,
                    escalated: Boolean(ev.escalated),
                    label: planLabel,
                  },
                ]);
              } else if (ev.type === "specialist_start") {
                const tierTag = ev.escalated
                  ? `⚡ Tier-1 Escalated (${ev.model})`
                  : `${ev.tier === "tier1" ? "Tier-1" : "Tier-2"} (${
                      ev.model || engineInfo.tier2Model
                    })`;
                setSteps((prev) => [
                  ...prev,
                  {
                    id: `start-${ev.agent}-${Date.now()}`,
                    timestamp: Date.now(),
                    type: "specialist_start",
                    role: ev.role,
                    ticker: ev.ticker,
                    model: ev.model,
                    escalated: Boolean(ev.escalated),
                    label: `${ev.agent} specialist started on ${tierTag}`,
                  },
                ]);
              } else if (ev.type === "tier_escalation") {
                setSteps((prev) => [
                  ...prev,
                  {
                    id: `esc-${ev.agent}-${Date.now()}`,
                    timestamp: Date.now(),
                    type: "tier_escalation",
                    role: ev.role,
                    ticker: ev.ticker,
                    model: ev.to_model,
                    escalated: true,
                    label: `⚡ ${ev.agent} escalated ${ev.from_model} → ${ev.to_model} (${String(
                      ev.reason || "demanding_retry"
                    ).replace(/_/g, " ")})`,
                  },
                ]);
              } else if (ev.type === "tool_call") {
                const argPreview = ev.args
                  ? Object.entries(ev.args)
                      .map(([k, v]) => `${k}=${String(v).slice(0, 28)}`)
                      .join(", ")
                  : "";
                setSteps((prev) => [
                  ...prev,
                  {
                    id: `tool-${Date.now()}-${Math.random()}`,
                    timestamp: Date.now(),
                    type: "tool_call",
                    role: ev.role,
                    ticker: ev.ticker,
                    label: `${ev.agent || ev.ticker} → ${ev.tool}(${argPreview})`,
                  },
                ]);
              } else if (ev.type === "specialist_done") {
                setSteps((prev) => [
                  ...prev,
                  {
                    id: `done-${ev.agent}-${Date.now()}`,
                    timestamp: Date.now(),
                    type: "specialist_done",
                    role: ev.role,
                    ticker: ev.ticker,
                    label: `${ev.agent} verified ${ev.citations_count} citation(s)`,
                  },
                ]);
              } else if (ev.type === "synthesizing") {
                setSteps((prev) => [
                  ...prev,
                  {
                    id: `synth-${Date.now()}`,
                    timestamp: Date.now(),
                    type: "synthesizing",
                    model: ev.model,
                    label: `Tier-1 Lead Synthesizer (${
                      ev.model || engineInfo.tier1Model
                    }) merging ${ev.reports_count} verified specialist reports...`,
                  },
                ]);
              } else if (ev.type === "guard_check") {
                setSteps((prev) => [
                  ...prev,
                  {
                    id: `guard-${Date.now()}`,
                    timestamp: Date.now(),
                    type: "guard_check",
                    label: `Citation Guard checked ${ev.valid_count} valid / ${ev.invalid_count} invalid claims`,
                  },
                ]);
              } else if (ev.type === "result") {
                const payload: QueryResult = ev.data;
                if (ev.quota) setQuota(ev.quota);
                if (payload.error) {
                  setErrorBanner(payload.error);
                } else {
                  setResult(payload);
                  setActiveSlug(ev.report_slug || payload.report_slug || null);
                  setSelectedCitIdx(payload.citations?.length ? 0 : null);
                }
              } else if (ev.type === "error") {
                setErrorBanner(ev.error || "Execution error");
              }
            } catch {
              // Skip malformed SSE lines
            }
          }
        }
      } catch (err) {
        setErrorBanner(
          err instanceof Error
            ? err.message
            : "Failed to connect to CompanyScope API."
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [question, ticker, peerInput, mode, isStreaming]
  );

  const handleCopyPermalink = useCallback(() => {
    if (!activeSlug || typeof window === "undefined") return;
    const url = `${window.location.origin}/report/${activeSlug}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2200);
    });
  }, [activeSlug]);

  const reportCitations = result?.citations || [];
  const inspectorCitations = inspectorOverride || reportCitations;
  const activeCitation =
    selectedCitIdx !== null && inspectorCitations[selectedCitIdx]
      ? inspectorCitations[selectedCitIdx]
      : inspectorCitations[0] || null;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Institutional Navigation Bar */}
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-[#080c14]/90 backdrop-blur-md">
        <div className="mx-auto max-w-[1520px] px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <a href="/" className="flex items-center gap-2.5 group">
              <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-emerald-500/25 to-blue-600/25 border border-emerald-400/40 flex items-center justify-center text-emerald-300 font-mono font-bold text-sm">
                CS
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold tracking-tight text-slate-100 text-sm">
                    CompanyScope
                  </span>
                  <span className="hidden sm:inline-flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                    <ShieldCheck className="h-3 w-3" />
                    Zero-Hallucination SEC Analyst
                  </span>
                </div>
                <p className="hidden md:block text-[10.5px] text-slate-500 font-mono">
                  Tier 1: {engineInfo.tier1Model} · Sub-Agents:{" "}
                  {engineInfo.tier2Model} · {engineInfo.embedding} ·{" "}
                  {engineInfo.backend}
                </p>
              </div>
            </a>
          </div>

          {/* Right Status & 5/Day No-Login Quota Pill */}
          <div className="flex items-center gap-2.5">
            <div
              title={formatResetCountdown(quota.reset_at)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-mono tabular-nums ${
                quota.remaining > 1
                  ? "border-blue-500/30 bg-blue-950/30 text-blue-200"
                  : quota.remaining === 1
                  ? "border-amber-500/40 bg-amber-950/30 text-amber-200"
                  : "border-rose-500/40 bg-rose-950/30 text-rose-200"
              }`}
            >
              <Zap className="h-3.5 w-3.5 text-amber-400" />
              <span>
                {quota.remaining}/{quota.limit} Free Queries Today
              </span>
              <span className="hidden sm:inline text-[10px] text-slate-400">
                · No Login
              </span>
            </div>

            <a
              href="https://github.com/iamqazolp/CompanyScope"
              target="_blank"
              rel="noreferrer"
              className="hidden sm:inline-flex items-center gap-1 rounded-lg border border-slate-800 bg-[#0d1422] px-2.5 py-1.5 text-xs text-slate-300 hover:border-slate-700 hover:text-white transition"
            >
              <span>GitHub</span>
              <ArrowUpRight className="h-3.5 w-3.5 text-slate-500" />
            </a>
          </div>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="flex-1 mx-auto w-full max-w-[1520px] px-4 sm:px-6 py-5">
        {/* Live Cross-Asset Market Tape & 0-Quota AI Market News Recap */}
        <MarketRecapBar
          onInspectRecapCitation={(recapCits, idx) => {
            setInspectorOverride(recapCits);
            setSelectedCitIdx(idx);
            setMobileDrawerOpen(true);
          }}
        />

        {/* Instant Showcase Banner (Zero Quota Cost) */}
        {showcases.length > 0 && (
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-emerald-400 mr-1">
              <Sparkles className="h-3.5 w-3.5" />
              Instant Verified Reports (0 Quota):
            </span>
            {showcases.map((sc) => {
              const isCurrent = activeSlug === sc.slug;
              return (
                <button
                  key={sc.slug}
                  type="button"
                  onClick={() => loadShowcase(sc.slug)}
                  className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition ${
                    isCurrent
                      ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-100"
                      : "border-slate-800 bg-[#0d1422] text-slate-300 hover:border-slate-700 hover:text-white"
                  }`}
                >
                  <span className="font-mono font-semibold text-emerald-400">
                    {sc.tickers.join("+")}
                  </span>
                  <span className="truncate max-w-[260px] sm:max-w-none">
                    {sc.title}
                  </span>
                  <span className="hidden md:inline rounded bg-slate-800/90 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                    {sc.citations_count} cits
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {/* Two-Column Analyst Terminal Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          {/* Left / Center Research Column (7 cols on lg) */}
          <div className="lg:col-span-7 xl:col-span-8 space-y-4">
            {/* Query Composer & Ticker Controls Card */}
            <div className="rounded-xl border border-slate-800/90 bg-[#0d1422] p-4 shadow-xl shadow-black/25 space-y-3.5">
              {/* Ticker & Orchestration Controls */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex items-center gap-1.5">
                    <label className="text-[11px] font-medium text-slate-400">
                      Ticker
                    </label>
                    <input
                      type="text"
                      value={ticker}
                      onChange={(e) => setTicker(e.target.value.toUpperCase())}
                      maxLength={6}
                      className="w-20 rounded-lg border border-slate-700/80 bg-[#080d18] px-2.5 py-1 font-mono text-xs font-semibold uppercase text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>

                  <div className="hidden sm:flex items-center gap-1">
                    {POPULAR_TICKERS.map((sym) => (
                      <button
                        key={sym}
                        type="button"
                        onClick={() => setTicker(sym)}
                        className={`rounded px-1.5 py-0.5 font-mono text-[10.5px] transition ${
                          ticker === sym
                            ? "bg-blue-500/25 text-blue-200 border border-blue-500/40"
                            : "text-slate-500 hover:text-slate-300"
                        }`}
                      >
                        {sym}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-1.5 ml-1">
                    <label className="text-[11px] font-medium text-slate-400">
                      vs. Peers
                    </label>
                    <input
                      type="text"
                      value={peerInput}
                      onChange={(e) =>
                        setPeerInput(e.target.value.toUpperCase())
                      }
                      placeholder="e.g. MSFT, NVDA"
                      className="w-28 sm:w-32 rounded-lg border border-slate-800 bg-[#080d18] px-2.5 py-1 font-mono text-xs uppercase text-slate-200 placeholder:text-slate-600 focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                </div>

                {/* Mode Selector */}
                <div className="inline-flex rounded-lg border border-slate-800 bg-[#080d18] p-0.5">
                  {(
                    [
                      ["multi_agent", "Multi-Agent"],
                      ["auto", "Auto"],
                      ["single", "Single"],
                    ] as const
                  ).map(([val, label]) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => setMode(val)}
                      className={`px-2.5 py-1 text-[11px] font-medium rounded-md transition ${
                        mode === val
                          ? "bg-emerald-500/20 text-emerald-200 border border-emerald-500/40"
                          : "text-slate-400 hover:text-slate-200 border border-transparent"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Prompt Input */}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  runLiveQuery();
                }}
                className="relative"
              >
                <textarea
                  rows={2}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      runLiveQuery();
                    }
                  }}
                  placeholder="Ask any SEC 10-K/10-Q/8-K, XBRL financial ratio, earnings call, or market sentiment question..."
                  className="w-full resize-none rounded-xl border border-slate-700/80 bg-[#080d18] pl-3.5 pr-28 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-emerald-500/60 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={isStreaming || !question.trim() || quota.remaining <= 0}
                  className="absolute right-2.5 bottom-2.5 inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-800 disabled:text-slate-500 px-3.5 py-1.5 text-xs font-semibold text-slate-950 transition cursor-pointer disabled:cursor-not-allowed"
                >
                  {isStreaming ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Running</span>
                    </>
                  ) : (
                    <>
                      <Send className="h-3.5 w-3.5" />
                      <span>Analyze</span>
                    </>
                  )}
                </button>
              </form>

              {/* Preset Analytical Prompt Chips */}
              <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                <span className="text-[10.5px] text-slate-500 mr-1">
                  Live Queries (uses 1 quota):
                </span>
                {QUICK_PROMPTS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    disabled={isStreaming || quota.remaining <= 0}
                    onClick={() => {
                      setTicker(preset.ticker);
                      setPeerInput(preset.peers);
                      setMode(preset.mode as "multi_agent");
                      setQuestion(preset.q);
                      runLiveQuery({
                        q: preset.q,
                        tkr: preset.ticker,
                        peers: preset.peers,
                        m: preset.mode as "multi_agent",
                      });
                    }}
                    className="rounded-md border border-slate-800 bg-[#090f1c] hover:border-slate-700 px-2.5 py-1 text-[11px] text-slate-300 hover:text-white transition disabled:opacity-40"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Error or Quota Exhausted Alert */}
            {errorBanner && (
              <div className="rounded-xl border border-rose-500/40 bg-rose-950/25 px-4 py-3 text-xs text-rose-200 flex items-center justify-between gap-3">
                <span>{errorBanner}</span>
                <button
                  type="button"
                  onClick={() => setErrorBanner(null)}
                  className="text-rose-400 hover:text-rose-200 font-mono"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Live SSE Execution Timeline */}
            {(isStreaming || steps.length > 0) && (
              <div className="rounded-xl border border-slate-800/80 bg-[#0b111e] p-3.5">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                    {isStreaming ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" />
                    ) : (
                      <Activity className="h-3.5 w-3.5 text-emerald-400" />
                    )}
                    <span>
                      {isStreaming
                        ? "Live Multi-Agent & Citation Guard Execution..."
                        : "Execution Trace Completed"}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-slate-500">
                    {steps.length} events
                  </span>
                </div>
                <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                  {steps.map((st) => (
                    <div
                      key={st.id}
                      className={`flex items-center gap-2 font-mono text-[11px] ${
                        st.escalated || st.type === "tier_escalation"
                          ? "text-amber-300"
                          : "text-slate-400"
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                          st.escalated || st.type === "tier_escalation"
                            ? "bg-amber-400"
                            : "bg-emerald-400/80"
                        }`}
                      />
                      <span className="truncate">{st.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Verified Research Answer & Sub-Agent Reports */}
            {result && (
              <article className="rounded-xl border border-slate-800/90 bg-[#0d1422] overflow-hidden shadow-xl shadow-black/25">
                {/* Report Header Bar */}
                <div className="px-5 py-3.5 border-b border-slate-800/80 bg-[#0a101d] flex flex-wrap items-center justify-between gap-3">
                  <div className="space-y-0.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-[11px] text-emerald-400 font-medium">
                      <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
                      <span>100% Citation-Verified Research Synthesis</span>
                    </div>
                    {activeQuestion && (
                      <h1 className="text-sm font-semibold text-slate-100 truncate">
                        {activeQuestion}
                      </h1>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {activeSlug && (
                      <button
                        type="button"
                        onClick={handleCopyPermalink}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700/80 bg-[#0d1526] hover:border-emerald-500/50 px-2.5 py-1.5 text-xs text-slate-200 transition"
                      >
                        {copiedLink ? (
                          <>
                            <Check className="h-3.5 w-3.5 text-emerald-400" />
                            <span className="text-emerald-300">Copied URL</span>
                          </>
                        ) : (
                          <>
                            <Share2 className="h-3.5 w-3.5 text-slate-400" />
                            <span>Share Report</span>
                          </>
                        )}
                      </button>
                    )}

                    {reportCitations.length > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          setInspectorOverride(null);
                          setMobileDrawerOpen(true);
                        }}
                        className="lg:hidden inline-flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-300"
                      >
                        <span>Sources ({reportCitations.length})</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Synthesis vs Specialist Sub-Agents Tabs */}
                {result.sub_agent_reports &&
                  result.sub_agent_reports.length > 0 && (
                    <div className="px-5 pt-2.5 border-b border-slate-800/70 bg-[#090f1b] flex items-center gap-4">
                      <button
                        type="button"
                        onClick={() => setActiveTab("synthesis")}
                        className={`pb-2 text-xs font-medium border-b-2 transition ${
                          activeTab === "synthesis"
                            ? "border-emerald-400 text-emerald-300"
                            : "border-transparent text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        Executive Synthesis
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTab("specialists")}
                        className={`pb-2 text-xs font-medium border-b-2 transition inline-flex items-center gap-1.5 ${
                          activeTab === "specialists"
                            ? "border-blue-400 text-blue-300"
                            : "border-transparent text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        <Layers className="h-3.5 w-3.5" />
                        <span>
                          Specialist Sub-Agents (
                          {result.sub_agent_reports.length})
                        </span>
                      </button>
                    </div>
                  )}

                {/* Main Body */}
                <div className="p-5 space-y-5">
                  {activeTab === "synthesis" ? (
                    <MarkdownView content={result.answer} />
                  ) : (
                    <div className="space-y-3">
                      {(result.sub_agent_reports || []).map((sub) => (
                        <div
                          key={sub.agent}
                          className="rounded-lg border border-slate-800 bg-[#090e19] p-3.5 space-y-2"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold text-blue-300">
                                <Bot className="h-3.5 w-3.5" />
                                {sub.agent}
                              </span>
                              {sub.model && (
                                <span
                                  title={
                                    sub.escalation_reason
                                      ? sub.escalation_reason.replace(/_/g, " ")
                                      : undefined
                                  }
                                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10px] ${
                                    sub.escalated
                                      ? "border-amber-500/40 bg-amber-500/15 text-amber-200"
                                      : sub.tier === "tier1"
                                      ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-200"
                                      : "border-slate-700 bg-slate-800/70 text-slate-300"
                                  }`}
                                >
                                  {sub.escalated
                                    ? `⚡ Tier 1 Escalated · ${sub.model}`
                                    : `${
                                        sub.tier === "tier1"
                                          ? "Tier 1"
                                          : "Tier 2"
                                      } · ${sub.model}`}
                                </span>
                              )}
                            </div>
                            <span className="font-mono text-[10.5px] text-slate-500">
                              {sub.citations_count} verified citations ·{" "}
                              {sub.self_corrections} retries
                            </span>
                          </div>
                          <MarkdownView content={sub.answer} />
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Interactive Citation Evidence Pills */}
                  {reportCitations.length > 0 && (
                    <div className="pt-4 border-t border-slate-800/80">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2.5">
                        Verified Source Citations (Click to Inspect Primary Filing / Live Quote / XBRL)
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {reportCitations.map((cit, idx) => {
                          const selected =
                            inspectorOverride === null &&
                            (selectedCitIdx ?? 0) === idx;
                          const style =
                            cit.type === "numeric" || cit.type === "market"
                              ? selected
                                ? "border-blue-400 bg-blue-500/20 text-blue-100"
                                : "border-blue-500/25 bg-blue-950/20 text-blue-300 hover:border-blue-400/50"
                              : cit.type === "sentiment" ||
                                cit.type === "insider"
                              ? selected
                                ? "border-amber-400 bg-amber-500/20 text-amber-100"
                                : "border-amber-500/25 bg-amber-950/20 text-amber-300 hover:border-amber-400/50"
                              : selected
                              ? "border-emerald-400 bg-emerald-500/20 text-emerald-100"
                              : "border-emerald-500/25 bg-emerald-950/20 text-emerald-300 hover:border-emerald-400/50";

                          return (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => {
                                setInspectorOverride(null);
                                setSelectedCitIdx(idx);
                                setMobileDrawerOpen(true);
                              }}
                              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-mono text-[11px] transition cursor-pointer ${style}`}
                            >
                              <span className="opacity-70">[{idx + 1}]</span>
                              <span>{citationBadgeLabel(cit)}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Telemetry Footer */}
                  <div className="pt-3 border-t border-slate-800/60 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-slate-500">
                    <div className="flex flex-wrap items-center gap-3">
                      {result.model && (
                        <span className="inline-flex items-center gap-1 text-emerald-300/90">
                          <Cpu className="h-3 w-3 text-emerald-400" />
                          <span>
                            {result.tier === "tier2" ? "Tier 2:" : "Tier 1:"}{" "}
                            {result.model}
                            {result.escalated ? " ⚡" : ""}
                          </span>
                        </span>
                      )}
                      {result.tier_breakdown &&
                        result.tier_breakdown.tier2_agents.length > 0 && (
                          <span className="text-slate-400">
                            Sub-Agents: {result.tier_breakdown.tier2_agents.length}×{" "}
                            {result.tier_breakdown.tier2_model}
                            {result.tier_breakdown.escalated_agents.length > 0
                              ? ` · ${result.tier_breakdown.escalated_agents.length}× ${result.tier_breakdown.tier1_model} ⚡`
                              : ""}
                          </span>
                        )}
                      {typeof result.latency_ms === "number" && (
                        <span className="inline-flex items-center gap-1 tabular-nums">
                          <Clock className="h-3 w-3 text-slate-400" />
                          {(result.latency_ms / 1000).toFixed(2)}s
                        </span>
                      )}
                      {typeof result.cost_usd === "number" && (
                        <span className="tabular-nums">
                          ${result.cost_usd.toFixed(5)}
                        </span>
                      )}
                      {result.used_tools && result.used_tools.length > 0 && (
                        <span className="text-slate-400">
                          Tools: {result.used_tools.join(" · ")}
                        </span>
                      )}
                    </div>

                    {result.trace_url && (
                      <a
                        href={result.trace_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300"
                      >
                        <span>Langfuse OTel Trace</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>
              </article>
            )}

            {/* TradingView Live OHLCV + TradingView Studio + SEC XBRL Chart Deck */}
            <TradingViewChart
              ticker={ticker}
              xbrlRows={financials}
              xbrlLoading={finLoading}
            />
          </div>

          {/* Right Sticky Primary Source Inspector (5 cols on lg) */}
          <div className="hidden lg:block lg:col-span-5 xl:col-span-4 sticky top-20 h-[calc(100vh-6.5rem)]">
            <SourceInspector
              citation={activeCitation}
              allCitations={inspectorCitations}
              selectedIndex={
                selectedCitIdx ?? (inspectorCitations.length ? 0 : null)
              }
              onSelectIndex={(i) => setSelectedCitIdx(i)}
            />
          </div>
        </div>
      </main>

      {/* Mobile Source Inspector Modal */}
      {mobileDrawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden bg-black/75 backdrop-blur-sm p-3 flex flex-col">
          <div className="flex-1 overflow-hidden">
            <SourceInspector
              citation={activeCitation}
              allCitations={inspectorCitations}
              selectedIndex={
                selectedCitIdx ?? (inspectorCitations.length ? 0 : null)
              }
              onSelectIndex={(i) => setSelectedCitIdx(i)}
              onCloseMobile={() => setMobileDrawerOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
