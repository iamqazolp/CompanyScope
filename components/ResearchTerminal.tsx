"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  ExternalLink,
  FileCheck2,
  Layers,
  Loader2,
  Search,
  Send,
  Share2,
  X,
  Zap,
} from "lucide-react";
import type {
  Citation,
  FinancialRow,
  LiveQuote,
  MarketRecapResponse,
  QueryResult,
  QuotaStatus,
  SavedReport,
  ShowcaseSummary,
  StreamStep,
  TickerSearchResult,
} from "@/lib/types";
import { citationBadgeLabel, formatResetCountdown } from "@/lib/format";
import { MarketRecapBar } from "./MarketRecapBar";
import { MarkdownView } from "./MarkdownView";
import { SourceInspector } from "./SourceInspector";
import { TradingViewChart } from "./TradingViewChart";

const DEFAULT_FALLBACK_MOVERS: TickerSearchResult[] = [
  { ticker: "NVDA", company_name: "NVIDIA Corp." },
  { ticker: "MSFT", company_name: "Microsoft Corp." },
  { ticker: "JPM", company_name: "JPMorgan Chase" },
  { ticker: "LLY", company_name: "Eli Lilly & Co." },
  { ticker: "AMZN", company_name: "Amazon.com Inc." },
  { ticker: "PLTR", company_name: "Palantir Tech." },
  { ticker: "COST", company_name: "Costco Wholesale" },
];

interface Props {
  initialReport?: SavedReport | null;
}

export function ResearchTerminal({ initialReport = null }: Props) {
  const initialTicker = initialReport?.tickers?.[0] || "NVDA";
  const [ticker, setTicker] = useState<string>(initialTicker);
  const [activeQuote, setActiveQuote] = useState<LiveQuote | null>(null);

  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchOpen, setSearchOpen] = useState<boolean>(false);
  const [searchLoading, setSearchLoading] = useState<boolean>(false);
  const [searchResults, setSearchResults] = useState<TickerSearchResult[]>([]);
  const [highlightIdx, setHighlightIdx] = useState<number>(0);
  const searchBoxRef = useRef<HTMLDivElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const [movers, setMovers] = useState<TickerSearchResult[]>(
    DEFAULT_FALLBACK_MOVERS
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
  }>({
    tier1Model: "gpt-6.1-terra",
    tier2Model: "gpt-6-luna",
  });

  const [recap, setRecap] = useState<MarketRecapResponse | null>(null);
  const [recapLoading, setRecapLoading] = useState<boolean>(true);
  const [recapRefreshing, setRecapRefreshing] = useState<boolean>(false);

  const [showcases, setShowcases] = useState<ShowcaseSummary[]>([]);
  const [samplesMenuOpen, setSamplesMenuOpen] = useState<boolean>(false);
  const samplesRef = useRef<HTMLDivElement | null>(null);

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
  const [rightTab, setRightTab] = useState<"sources" | "brief">(
    initialReport?.result?.citations?.length ? "sources" : "brief"
  );

  const [financials, setFinancials] = useState<FinancialRow[]>([]);
  const [quarterlyFinancials, setQuarterlyFinancials] = useState<
    FinancialRow[]
  >([]);
  const [finLoading, setFinLoading] = useState<boolean>(false);

  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [steps, setSteps] = useState<StreamStep[]>([]);
  const [traceExpanded, setTraceExpanded] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState<boolean>(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState<boolean>(false);
  const [inspectorOverride, setInspectorOverride] = useState<
    Citation[] | null
  >(null);

  const selectTicker = useCallback(
    (sym: string, preservePeers = false) => {
      const clean = sym.trim().toUpperCase().replace(".", "-");
      if (!clean || clean.length > 6) return;
      setTicker(clean);
      setSearchQuery("");
      setSearchOpen(false);
      if (!preservePeers) {
        setPeerInput("");
      }
      if (typeof window !== "undefined") {
        try {
          window.sessionStorage.setItem("cs_active_ticker", clean);
        } catch {
          // Ignore private-mode storage errors
        }
      }
    },
    []
  );

  const fetchRecap = useCallback(async (force = false) => {
    if (force) setRecapRefreshing(true);
    try {
      const url = force ? "/api/market/recap?force=true" : "/api/market/recap";
      const r = await fetch(url);
      if (r.ok) {
        const data: MarketRecapResponse = await r.json();
        if (!data.error) setRecap(data);
      }
    } catch {
      // Ignore transient offline errors
    } finally {
      setRecapLoading(false);
      setRecapRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchRecap(false);

    let savedTicker: string | null = null;
    if (!initialReport && typeof window !== "undefined") {
      try {
        savedTicker = window.sessionStorage.getItem("cs_active_ticker");
        if (savedTicker) {
          setTicker(savedTicker.toUpperCase());
        }
      } catch {
        // Ignore storage errors
      }
    }

    async function init() {
      try {
        const [hRes, qRes, sRes, mRes] = await Promise.all([
          fetch("/api/health"),
          fetch("/api/quota"),
          fetch("/api/showcase"),
          fetch("/api/market/movers?limit=7"),
        ]);
        if (!cancelled && hRes.ok) {
          const h = await hRes.json();
          setEngineInfo({
            tier1Model: h.tier1_model || h.model || "gpt-6.1-terra",
            tier2Model: h.tier2_model || "gpt-6-luna",
          });
        }
        if (!cancelled && qRes.ok) {
          const q = await qRes.json();
          if (typeof q.remaining === "number") setQuota(q);
        }
        if (!cancelled && sRes.ok) {
          const s = await sRes.json();
          setShowcases(s.reports || []);
        }
        if (!cancelled && mRes.ok) {
          const m = await mRes.json();
          if (Array.isArray(m.movers) && m.movers.length > 0) {
            setMovers(m.movers);
            if (!initialReport && !savedTicker && m.movers[0]?.ticker) {
              setTicker(m.movers[0].ticker);
            }
          }
        }
      } catch {
        // Ignore boot network errors
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, [fetchRecap, initialReport]);

  // Global Cmd+K / Ctrl+K shortcut + outside click handlers
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
        searchInputRef.current?.focus();
      }
    }
    function onDocMouseDown(e: MouseEvent) {
      const target = e.target as Node;
      if (searchBoxRef.current && !searchBoxRef.current.contains(target)) {
        setSearchOpen(false);
      }
      if (samplesRef.current && !samplesRef.current.contains(target)) {
        setSamplesMenuOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onDocMouseDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onDocMouseDown);
    };
  }, []);

  // Debounced live autocomplete across 6,000+ US equities
  useEffect(() => {
    if (!searchOpen) return;
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults(movers);
      setHighlightIdx(0);
      setSearchLoading(false);
      return;
    }

    let cancelled = false;
    setSearchLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const r = await fetch(
          `/api/market/search?q=${encodeURIComponent(q)}&limit=8`
        );
        if (!cancelled && r.ok) {
          const data = await r.json();
          if (Array.isArray(data.results)) {
            setSearchResults(data.results);
            setHighlightIdx(0);
          }
        }
      } catch {
        // Ignore transient search errors
      } finally {
        if (!cancelled) setSearchLoading(false);
      }
    }, 150);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [searchQuery, searchOpen, movers]);

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
          setQuarterlyFinancials(
            Array.isArray(data.quarterly) ? data.quarterly : []
          );
        } else if (!cancelled) {
          setFinancials([]);
          setQuarterlyFinancials([]);
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

  const loadShowcase = useCallback(
    async (slug: string) => {
      setErrorBanner(null);
      setSamplesMenuOpen(false);
      try {
        const r = await fetch(`/api/reports/${encodeURIComponent(slug)}`);
        if (!r.ok) return;
        const rep: SavedReport = await r.json();
        if (rep.tickers?.[0]) selectTicker(rep.tickers[0], true);
        setPeerInput(
          rep.tickers?.length > 1 ? rep.tickers.slice(1).join(", ") : ""
        );
        setActiveSlug(rep.slug);
        setActiveQuestion(rep.question);
        setResult(rep.result);
        setInspectorOverride(null);
        setSteps([]);
        setActiveTab("synthesis");
        setSelectedCitIdx(rep.result.citations?.length ? 0 : null);
        if (rep.result.citations?.length) setRightTab("sources");
      } catch {
        setErrorBanner("Failed to load report.");
      }
    },
    [selectTicker]
  );

  const runLiveQuery = useCallback(
    async (override?: {
      q: string;
      tkr: string;
      peers: string;
      m: "multi_agent" | "auto" | "single";
    }) => {
      const qText = (override ? override.q : question).trim();
      const primaryTkr =
        (override ? override.tkr : ticker).trim().toUpperCase() || "NVDA";
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
      setTraceExpanded(true);
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
          label: `${activeMode === "single" ? "Single" : "Supervisor"} → ${allTickers.join(", ")}`,
        },
      ]);

      try {
        const resp = await fetch("/api/ask/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: qText,
            ticker: primaryTkr,
            tickers: peerList.length > 0 ? allTickers : undefined,
            mode: activeMode,
          }),
        });

        if (resp.status === 429) {
          const errJson = await resp.json().catch(() => ({}));
          if (errJson.quota) setQuota(errJson.quota);
          setErrorBanner(
            errJson.error || "Daily 5-query limit reached. Resets at 00:00 UTC."
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
                if (
                  Array.isArray(ev.tickers) &&
                  ev.tickers[0] &&
                  ev.tickers[0] !== primaryTkr
                ) {
                  selectTicker(ev.tickers[0], ev.tickers.length > 1);
                  if (ev.tickers.length > 1) {
                    setPeerInput(ev.tickers.slice(1).join(", "));
                  }
                }
                const planLabel =
                  ev.mode === "single"
                    ? `${ev.model || engineInfo.tier2Model}${
                        ev.escalated ? " ⚡" : ""
                      } → ${(ev.tickers || []).join(", ")}`
                    : `${ev.supervisor_model || engineInfo.tier1Model} → [${(
                        ev.tickers || []
                      ).join(", ")}] · ${(ev.specialists || [])
                        .join(", ")
                        .toUpperCase()}`;
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
                    label: `${ev.agent} (${ev.model || engineInfo.tier2Model}${
                      ev.escalated ? " ⚡" : ""
                    })`,
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
                    label: `⚡ ${ev.agent}: ${ev.from_model} → ${ev.to_model}`,
                  },
                ]);
              } else if (ev.type === "tool_call") {
                const argPreview = ev.args
                  ? Object.entries(ev.args)
                      .map(([k, v]) => `${k}=${String(v).slice(0, 22)}`)
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
                    label: `${ev.agent || ev.ticker} · ${ev.tool}(${argPreview})`,
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
                    label: `${ev.agent} ✓ (${ev.citations_count} citations)`,
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
                    label: `Synthesizing (${ev.model || engineInfo.tier1Model})...`,
                  },
                ]);
              } else if (ev.type === "guard_check") {
                setSteps((prev) => [
                  ...prev,
                  {
                    id: `guard-${Date.now()}`,
                    timestamp: Date.now(),
                    type: "guard_check",
                    label: `Guard: ${ev.valid_count} valid / ${ev.invalid_count} rejected`,
                  },
                ]);
              } else if (ev.type === "result") {
                const payload: QueryResult = ev.data;
                if (ev.quota) setQuota(ev.quota);
                if (payload.error) {
                  setErrorBanner(payload.error);
                } else {
                  setResult(payload);
                  setTraceExpanded(false);
                  setActiveSlug(ev.report_slug || payload.report_slug || null);
                  setSelectedCitIdx(payload.citations?.length ? 0 : null);
                  if (payload.citations?.length) setRightTab("sources");
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
          err instanceof Error ? err.message : "Connection failed."
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [question, ticker, peerInput, mode, isStreaming, engineInfo, selectTicker]
  );

  const handleCopyPermalink = useCallback(() => {
    if (!activeSlug || typeof window === "undefined") return;
    const url = `${window.location.origin}/report/${activeSlug}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    });
  }, [activeSlug]);

  const suggestedPeers =
    activeQuote?.ticker === ticker && activeQuote?.suggested_peers?.length
      ? activeQuote.suggested_peers
      : ["NVDA", "MSFT", "JPM"].filter((s) => s !== ticker);
  const topPeer = suggestedPeers[0] || "MSFT";

  const quickActions = [
    {
      label: "Valuation & Insiders",
      peers: "",
      mode: "multi_agent" as const,
      query: `Compare ${ticker}'s live Market Cap, Forward P/E, and recent SEC Form 4 insider trades against its latest XBRL Free Cash Flow and Item 1A risks.`,
    },
    {
      label: `vs ${topPeer}`,
      peers: topPeer,
      mode: "multi_agent" as const,
      query: `Compare latest annual Revenue, profitability, live valuation multiples, and primary 10-K risk disclosures between ${ticker} and ${topPeer}.`,
    },
    {
      label: "Multi-Year Growth",
      peers: "",
      mode: "multi_agent" as const,
      query: `Calculate ${ticker}'s multi-year revenue growth, analyze margin expansion, and reconcile management commentary against 10-K risk factors.`,
    },
    {
      label: "8-K & Live News",
      peers: "",
      mode: "multi_agent" as const,
      query: `Summarize ${ticker}'s latest Form 8-K events alongside fresh 7-day news headlines and Reddit investor sentiment.`,
    },
  ];

  const reportCitations = result?.citations || [];
  const inspectorCitations = inspectorOverride || reportCitations;
  const activeCitation =
    selectedCitIdx !== null && inspectorCitations[selectedCitIdx]
      ? inspectorCitations[selectedCitIdx]
      : inspectorCitations[0] || null;

  return (
    <div className="min-h-screen flex flex-col bg-[#060911]">
      {/* Slim Functional Header: Universal Ticker/Company Search + Live Market Movers */}
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-[#070b14]/95 backdrop-blur-md">
        <div className="mx-auto max-w-[1520px] px-4 sm:px-6 h-12 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <a href="/" className="flex items-center gap-2 shrink-0">
              <div className="h-7 w-7 rounded-md bg-emerald-500/15 border border-emerald-400/40 flex items-center justify-center text-emerald-300 font-mono font-bold text-xs">
                CS
              </div>
              <span className="font-semibold tracking-tight text-slate-100 text-sm hidden sm:inline">
                CompanyScope
              </span>
            </a>

            <div className="h-4 w-px bg-slate-800 hidden sm:block shrink-0" />

            {/* All-Market Company & Ticker Search Combobox */}
            <div ref={searchBoxRef} className="relative shrink-0">
              <div className="relative flex items-center">
                <Search className="h-3.5 w-3.5 text-slate-500 absolute left-2.5 pointer-events-none" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchOpen ? searchQuery : ""}
                  onFocus={() => {
                    setSearchOpen(true);
                    setSearchQuery("");
                  }}
                  onChange={(e) => {
                    setSearchOpen(true);
                    setSearchQuery(e.target.value);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setHighlightIdx((i) =>
                        Math.min(i + 1, Math.max(0, searchResults.length - 1))
                      );
                    } else if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setHighlightIdx((i) => Math.max(0, i - 1));
                    } else if (e.key === "Enter") {
                      e.preventDefault();
                      const picked = searchResults[highlightIdx];
                      if (picked?.ticker) {
                        selectTicker(picked.ticker);
                        searchInputRef.current?.blur();
                      } else if (searchQuery.trim()) {
                        selectTicker(searchQuery.trim());
                        searchInputRef.current?.blur();
                      }
                    } else if (e.key === "Escape") {
                      setSearchOpen(false);
                      searchInputRef.current?.blur();
                    }
                  }}
                  placeholder={`${ticker} · Search any US stock`}
                  aria-label="Search any US ticker or company name"
                  className="w-44 sm:w-56 rounded-md border border-slate-800 bg-[#0b111e] pl-8 pr-11 py-1 text-xs text-slate-100 placeholder:text-slate-300 placeholder:font-mono focus:placeholder:text-slate-500 focus:border-emerald-500/60 focus:outline-none transition"
                />
                {searchLoading ? (
                  <Loader2 className="h-3 w-3 animate-spin text-slate-500 absolute right-2.5" />
                ) : (
                  <kbd className="hidden sm:inline-block absolute right-2 rounded border border-slate-800 bg-[#070b14] px-1 py-0.2 font-mono text-[9.5px] text-slate-500 pointer-events-none">
                    ⌘K
                  </kbd>
                )}
              </div>

              {/* Autocomplete Results Popover */}
              {searchOpen && (
                <div className="absolute left-0 mt-1.5 w-80 sm:w-96 rounded-lg border border-slate-700/90 bg-[#0b111e] shadow-2xl overflow-hidden z-50">
                  <div className="px-3 py-1.5 border-b border-slate-800/80 flex items-center justify-between text-[10px] font-mono text-slate-500">
                    <span>
                      {searchQuery.trim()
                        ? "NASDAQ · NYSE · AMEX MATCHES"
                        : "TODAY'S MOST ACTIVE US EQUITIES"}
                    </span>
                    <span>ESC</span>
                  </div>

                  {searchResults.length === 0 && !searchLoading ? (
                    <div className="px-3 py-4 text-xs text-slate-500 text-center">
                      Press Enter to jump directly to{" "}
                      <strong className="font-mono text-slate-200">
                        {searchQuery.trim().toUpperCase()}
                      </strong>
                    </div>
                  ) : (
                    <div className="max-h-72 overflow-y-auto divide-y divide-slate-800/50">
                      {searchResults.map((item, idx) => {
                        const up = (item.change_pct ?? 0) >= 0;
                        const active = idx === highlightIdx;
                        return (
                          <button
                            key={item.ticker}
                            type="button"
                            onMouseEnter={() => setHighlightIdx(idx)}
                            onClick={() => selectTicker(item.ticker)}
                            className={`w-full px-3 py-2 flex items-center justify-between gap-3 text-left transition cursor-pointer ${
                              active ? "bg-slate-800/80" : "hover:bg-slate-800/40"
                            }`}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-xs font-bold text-white">
                                  {item.ticker}
                                </span>
                                {item.exchange && (
                                  <span className="rounded bg-slate-900 px-1 py-0.2 font-mono text-[9.5px] text-slate-500">
                                    {item.exchange}
                                  </span>
                                )}
                                {item.sector && (
                                  <span className="text-[10px] text-slate-500 truncate">
                                    {item.sector}
                                  </span>
                                )}
                              </div>
                              <p className="text-[11px] text-slate-400 truncate">
                                {item.company_name}
                              </p>
                            </div>

                            {typeof item.price === "number" && (
                              <div className="text-right font-mono shrink-0 tabular-nums">
                                <div className="text-xs font-semibold text-slate-200">
                                  ${item.price.toFixed(2)}
                                </div>
                                {typeof item.change_pct === "number" && (
                                  <div
                                    className={`text-[10px] ${
                                      up ? "text-emerald-400" : "text-rose-400"
                                    }`}
                                  >
                                    {up ? "+" : ""}
                                    {item.change_pct.toFixed(2)}%
                                  </div>
                                )}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Live Market Movers Strip (Dynamic, All-Sector) */}
            <div className="hidden lg:flex items-center gap-1 overflow-x-auto no-scrollbar min-w-0">
              {movers.map((mv) => {
                const isSelected = ticker === mv.ticker;
                const up = (mv.change_pct ?? 0) >= 0;
                return (
                  <button
                    key={mv.ticker}
                    type="button"
                    onClick={() => selectTicker(mv.ticker)}
                    title={mv.company_name}
                    className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-[11px] shrink-0 transition cursor-pointer ${
                      isSelected
                        ? "bg-emerald-500/20 text-emerald-200 border border-emerald-500/40"
                        : "text-slate-400 hover:text-slate-100 border border-transparent hover:border-slate-800"
                    }`}
                  >
                    <span className="font-semibold">{mv.ticker}</span>
                    {typeof mv.change_pct === "number" && (
                      <span
                        className={`text-[10px] tabular-nums ${
                          up ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {up ? "+" : ""}
                        {mv.change_pct.toFixed(1)}%
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Status & Quota */}
          <div className="flex items-center gap-2 shrink-0">
            <span
              title={`Tier 1: ${engineInfo.tier1Model} · Tier 2: ${engineInfo.tier2Model}`}
              className="hidden xl:inline-flex items-center gap-1 rounded-md border border-slate-800/90 bg-[#0b111e] px-2 py-1 font-mono text-[10.5px] text-slate-400"
            >
              <Cpu className="h-3 w-3 text-emerald-400" />
              <span>
                {engineInfo.tier1Model} + {engineInfo.tier2Model}
              </span>
            </span>

            <div
              title={formatResetCountdown(quota.reset_at)}
              className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-[11px] font-mono tabular-nums ${
                quota.remaining > 1
                  ? "border-slate-800 bg-[#0b111e] text-slate-200"
                  : quota.remaining === 1
                  ? "border-amber-500/40 bg-amber-950/30 text-amber-200"
                  : "border-rose-500/40 bg-rose-950/30 text-rose-200"
              }`}
            >
              <Zap className="h-3 w-3 text-amber-400" />
              <span>
                {quota.remaining}/{quota.limit}
              </span>
            </div>

            <a
              href="https://github.com/iamqazolp/CompanyScope"
              target="_blank"
              rel="noreferrer"
              title="GitHub Repository"
              className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-[#0b111e] px-2 py-1 text-xs text-slate-400 hover:border-slate-700 hover:text-white transition"
            >
              <span className="hidden sm:inline">GitHub</span>
              <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </header>

      {/* Slim Cross-Asset Benchmark Strip */}
      <MarketRecapBar
        data={recap}
        loading={recapLoading}
        briefActive={rightTab === "brief"}
        onOpenBrief={() => {
          setRightTab("brief");
          setMobileDrawerOpen(true);
        }}
      />

      {/* Main 12-Col Workspace */}
      <main className="flex-1 mx-auto w-full max-w-[1520px] px-4 sm:px-6 py-4">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* Left 8 Cols: Live Chart Deck -> Command Bar -> Research Output */}
          <div className="lg:col-span-7 xl:col-span-8 space-y-3.5">
            {/* 1. Live TradingView Chart + Multiples + XBRL Deck */}
            <TradingViewChart
              ticker={ticker}
              xbrlRows={financials}
              quarterlyRows={quarterlyFinancials}
              xbrlLoading={finLoading}
              onQuoteLoaded={setActiveQuote}
              onAuditMetric={(promptText) => {
                setQuestion(promptText);
                runLiveQuery({
                  q: promptText,
                  tkr: ticker,
                  peers: "",
                  m: "multi_agent",
                });
              }}
            />

            {/* 2. Unified All-Market Analyst Command Composer */}
            <div className="rounded-xl border border-slate-800/90 bg-[#0b111d] p-3 space-y-2.5">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  runLiveQuery();
                }}
                className="rounded-lg border border-slate-800 bg-[#070b14] focus-within:border-emerald-500/50 transition"
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
                  placeholder={`Ask about ${ticker} or any US public company (e.g., "Compare ${ticker} vs ${topPeer} margins & P/E", "Audit Palantir's 10-K risks")...`}
                  className="w-full resize-none bg-transparent px-3 pt-2.5 pb-1.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
                />

                <div className="flex flex-wrap items-center justify-between gap-2 px-2.5 pb-2 pt-1 border-t border-slate-800/60">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <div className="inline-flex items-center gap-1.5 rounded border border-slate-800 bg-[#0b111e] px-2 py-0.5">
                      <span className="text-[10.5px] font-mono text-slate-500">
                        +Peers
                      </span>
                      <input
                        type="text"
                        value={peerInput}
                        onChange={(e) =>
                          setPeerInput(e.target.value.toUpperCase())
                        }
                        placeholder={suggestedPeers.slice(0, 2).join(", ")}
                        className="w-24 bg-transparent font-mono text-[11px] uppercase text-slate-200 placeholder:text-slate-600 focus:outline-none"
                      />
                    </div>

                    {/* One-click dynamic sector peer suggestions */}
                    <div className="hidden sm:flex items-center gap-1">
                      {suggestedPeers.slice(0, 2).map((p) => {
                        const added = peerInput
                          .split(",")
                          .map((x) => x.trim())
                          .includes(p);
                        return (
                          <button
                            key={p}
                            type="button"
                            onClick={() => {
                              const cur = peerInput
                                .split(",")
                                .map((x) => x.trim())
                                .filter(Boolean);
                              const next = added
                                ? cur.filter((x) => x !== p)
                                : [...cur, p].slice(0, 3);
                              setPeerInput(next.join(", "));
                            }}
                            className={`rounded px-1.5 py-0.5 font-mono text-[10px] border transition cursor-pointer ${
                              added
                                ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                                : "border-slate-800/80 bg-[#080d17] text-slate-500 hover:text-slate-300"
                            }`}
                          >
                            +{p}
                          </button>
                        );
                      })}
                    </div>

                    <div className="inline-flex rounded border border-slate-800 bg-[#0b111e] p-0.5">
                      {(
                        [
                          ["multi_agent", "Multi"],
                          ["auto", "Auto"],
                          ["single", "Single"],
                        ] as const
                      ).map(([val, lbl]) => (
                        <button
                          key={val}
                          type="button"
                          onClick={() => setMode(val)}
                          className={`px-2 py-0.5 text-[10.5px] font-mono rounded transition cursor-pointer ${
                            mode === val
                              ? "bg-slate-800 text-emerald-300"
                              : "text-slate-500 hover:text-slate-300"
                          }`}
                        >
                          {lbl}
                        </button>
                      ))}
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={
                      isStreaming || !question.trim() || quota.remaining <= 0
                    }
                    className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-800 disabled:text-slate-500 px-3 py-1 text-xs font-semibold text-slate-950 transition cursor-pointer disabled:cursor-not-allowed"
                  >
                    {isStreaming ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Running</span>
                      </>
                    ) : (
                      <>
                        <Send className="h-3 w-3" />
                        <span>Run</span>
                      </>
                    )}
                  </button>
                </div>
              </form>

              {/* Dynamic Quick Actions + Compact Multi-Sector Samples Dropdown */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  {quickActions.map((act) => (
                    <button
                      key={act.label}
                      type="button"
                      disabled={isStreaming || quota.remaining <= 0}
                      onClick={() => {
                        setPeerInput(act.peers);
                        setMode(act.mode);
                        setQuestion(act.query);
                        runLiveQuery({
                          q: act.query,
                          tkr: ticker,
                          peers: act.peers,
                          m: act.mode,
                        });
                      }}
                      className="rounded-md border border-slate-800/90 bg-[#080d17] hover:border-slate-700 px-2.5 py-1 text-[11px] text-slate-300 hover:text-white transition disabled:opacity-40 cursor-pointer"
                    >
                      {act.label}
                    </button>
                  ))}
                </div>

                {showcases.length > 0 && (
                  <div ref={samplesRef} className="relative">
                    <button
                      type="button"
                      onClick={() => setSamplesMenuOpen((v) => !v)}
                      className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-[#080d17] hover:border-slate-700 px-2.5 py-1 text-[11px] font-mono text-emerald-400 hover:text-emerald-300 transition cursor-pointer"
                    >
                      <FileCheck2 className="h-3 w-3" />
                      <span>Instant Audits</span>
                      <ChevronDown className="h-3 w-3 opacity-70" />
                    </button>

                    {samplesMenuOpen && (
                      <div className="absolute right-0 mt-1.5 w-72 rounded-lg border border-slate-700/90 bg-[#0b111e] shadow-2xl overflow-hidden z-40">
                        <div className="px-3 py-1.5 border-b border-slate-800/80 text-[10px] font-mono text-slate-500">
                          ZERO-QUOTA VERIFIED REPORTS
                        </div>
                        <div className="divide-y divide-slate-800/60">
                          {showcases.map((sc) => (
                            <button
                              key={sc.slug}
                              type="button"
                              onClick={() => loadShowcase(sc.slug)}
                              className={`w-full px-3 py-2 text-left hover:bg-slate-800/60 transition cursor-pointer ${
                                activeSlug === sc.slug ? "bg-emerald-500/10" : ""
                              }`}
                            >
                              <div className="flex items-center justify-between gap-2 font-mono text-[11px]">
                                <span className="font-bold text-emerald-300">
                                  {sc.tickers.join(" vs ")}
                                </span>
                                <span className="text-[10px] text-slate-500">
                                  {sc.category}
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-300 line-clamp-1 mt-0.5">
                                {sc.title}
                              </p>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Error Alert */}
            {errorBanner && (
              <div className="rounded-lg border border-rose-500/40 bg-rose-950/25 px-3.5 py-2.5 text-xs text-rose-200 flex items-center justify-between gap-3">
                <span>{errorBanner}</span>
                <button
                  type="button"
                  onClick={() => setErrorBanner(null)}
                  className="text-rose-400 hover:text-rose-200 cursor-pointer"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}

            {/* Collapsible Execution Trace */}
            {(isStreaming || steps.length > 0) && (
              <div className="rounded-xl border border-slate-800/80 bg-[#090e19] px-3.5 py-2">
                <button
                  type="button"
                  onClick={() => setTraceExpanded((v) => !v)}
                  className="w-full flex items-center justify-between text-xs font-mono text-slate-300 cursor-pointer"
                >
                  <span className="inline-flex items-center gap-2">
                    {isStreaming ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" />
                    ) : (
                      <Activity className="h-3.5 w-3.5 text-emerald-400" />
                    )}
                    <span>
                      {isStreaming
                        ? steps[steps.length - 1]?.label || "Running agents..."
                        : `Trace · ${steps.length} steps`}
                    </span>
                  </span>
                  <span className="inline-flex items-center gap-1 text-[10.5px] text-slate-500">
                    {traceExpanded ? (
                      <ChevronUp className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5" />
                    )}
                  </span>
                </button>

                {(isStreaming || traceExpanded) && (
                  <div className="mt-2 pt-2 border-t border-slate-800/70 space-y-1 max-h-32 overflow-y-auto pr-1">
                    {steps.map((st) => (
                      <div
                        key={st.id}
                        className={`flex items-center gap-2 font-mono text-[10.5px] ${
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
                )}
              </div>
            )}

            {/* 3. Research Synthesis Output Card */}
            {result && (
              <article className="rounded-xl border border-slate-800/90 bg-[#0b111d] overflow-hidden">
                <div className="px-4 py-2.5 border-b border-slate-800/80 bg-[#090e19] flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    {activeQuestion && (
                      <h1 className="text-xs sm:text-sm font-semibold text-slate-100 truncate">
                        {activeQuestion}
                      </h1>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {result.sub_agent_reports &&
                      result.sub_agent_reports.length > 0 && (
                        <div className="inline-flex rounded-md border border-slate-800 bg-[#070b14] p-0.5">
                          <button
                            type="button"
                            onClick={() => setActiveTab("synthesis")}
                            className={`px-2 py-0.5 rounded text-[11px] font-medium transition cursor-pointer ${
                              activeTab === "synthesis"
                                ? "bg-slate-800 text-white"
                                : "text-slate-400 hover:text-slate-200"
                            }`}
                          >
                            Synthesis
                          </button>
                          <button
                            type="button"
                            onClick={() => setActiveTab("specialists")}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition cursor-pointer ${
                              activeTab === "specialists"
                                ? "bg-slate-800 text-white"
                                : "text-slate-400 hover:text-slate-200"
                            }`}
                          >
                            <Layers className="h-3 w-3 text-blue-400" />
                            <span>Agents ({result.sub_agent_reports.length})</span>
                          </button>
                        </div>
                      )}

                    {activeSlug && (
                      <button
                        type="button"
                        onClick={handleCopyPermalink}
                        title="Copy shareable report link"
                        className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-[#070b14] hover:border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition cursor-pointer"
                      >
                        {copiedLink ? (
                          <Check className="h-3 w-3 text-emerald-400" />
                        ) : (
                          <Share2 className="h-3 w-3 text-slate-400" />
                        )}
                        <span className="hidden sm:inline">
                          {copiedLink ? "Copied" : "Share"}
                        </span>
                      </button>
                    )}

                    {reportCitations.length > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          setInspectorOverride(null);
                          setRightTab("sources");
                          setMobileDrawerOpen(true);
                        }}
                        className="lg:hidden inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[11px] font-mono text-emerald-300"
                      >
                        <span>Sources ({reportCitations.length})</span>
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => {
                        setResult(null);
                        setActiveSlug(null);
                        setSteps([]);
                      }}
                      title="Close report"
                      className="rounded-md p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200 transition cursor-pointer"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="p-4 space-y-4">
                  {activeTab === "synthesis" ? (
                    <MarkdownView content={result.answer} />
                  ) : (
                    <div className="space-y-2.5">
                      {(result.sub_agent_reports || []).map((sub) => (
                        <div
                          key={sub.agent}
                          className="rounded-lg border border-slate-800 bg-[#080c16] p-3 space-y-2"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
                            <div className="flex items-center gap-2">
                              <span className="inline-flex items-center gap-1 font-semibold text-blue-300">
                                <Bot className="h-3.5 w-3.5" />
                                {sub.agent}
                              </span>
                              {sub.model && (
                                <span
                                  className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                    sub.escalated
                                      ? "border-amber-500/40 bg-amber-500/15 text-amber-200"
                                      : "border-slate-800 bg-slate-900 text-slate-400"
                                  }`}
                                >
                                  {sub.model}
                                  {sub.escalated ? " ⚡" : ""}
                                </span>
                              )}
                            </div>
                            <span className="text-slate-500">
                              {sub.citations_count} cits
                            </span>
                          </div>
                          <MarkdownView content={sub.answer} />
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Compact Citation Chips */}
                  {reportCitations.length > 0 && (
                    <div className="pt-3 border-t border-slate-800/70 flex flex-wrap items-center gap-1.5">
                      {reportCitations.map((cit, idx) => {
                        const selected =
                          rightTab === "sources" &&
                          inspectorOverride === null &&
                          (selectedCitIdx ?? 0) === idx;
                        const style =
                          cit.type === "numeric" || cit.type === "market"
                            ? selected
                              ? "border-blue-400 bg-blue-500/20 text-blue-100"
                              : "border-blue-500/25 bg-blue-950/20 text-blue-300 hover:border-blue-400/50"
                            : cit.type === "sentiment" || cit.type === "insider"
                            ? selected
                              ? "border-amber-400 bg-amber-500/20 text-amber-100"
                              : "border-amber-500/25 bg-amber-950/20 text-amber-300 hover:border-amber-400/50"
                            : selected
                            ? "border-emerald-400 bg-emerald-500/20 text-emerald-100"
                            : "border-emerald-500/25 bg-emerald-950/20 text-emerald-300 hover:border-amber-400/50";

                        return (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => {
                              setInspectorOverride(null);
                              setSelectedCitIdx(idx);
                              setRightTab("sources");
                              setMobileDrawerOpen(true);
                            }}
                            className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[10.5px] transition cursor-pointer ${style}`}
                          >
                            <span className="opacity-70">[{idx + 1}]</span>
                            <span>{citationBadgeLabel(cit)}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Minimal Telemetry Footer */}
                  <div className="pt-2.5 border-t border-slate-800/50 flex flex-wrap items-center justify-between gap-2 text-[10.5px] font-mono text-slate-500">
                    <div className="flex flex-wrap items-center gap-2.5">
                      {result.model && (
                        <span className="text-slate-300">
                          {result.model}
                          {result.escalated ? " ⚡" : ""}
                        </span>
                      )}
                      {result.tier_breakdown &&
                        result.tier_breakdown.tier2_agents.length > 0 && (
                          <span>
                            + {result.tier_breakdown.tier2_agents.length}×{" "}
                            {result.tier_breakdown.tier2_model}
                          </span>
                        )}
                      {typeof result.latency_ms === "number" && (
                        <span className="inline-flex items-center gap-1 tabular-nums">
                          <Clock className="h-3 w-3" />
                          {(result.latency_ms / 1000).toFixed(1)}s
                        </span>
                      )}
                      {typeof result.cost_usd === "number" && (
                        <span className="tabular-nums">
                          ${result.cost_usd.toFixed(4)}
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
                        <span>Trace</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>
              </article>
            )}
          </div>

          {/* Right 4 Cols: Dual-Mode Source Inspector & Live Market Brief */}
          <div className="hidden lg:block lg:col-span-5 xl:col-span-4 sticky top-16 h-[calc(100vh-5rem)]">
            <SourceInspector
              panelTab={rightTab}
              onChangeTab={setRightTab}
              citation={activeCitation}
              allCitations={inspectorCitations}
              selectedIndex={
                selectedCitIdx ?? (inspectorCitations.length ? 0 : null)
              }
              onSelectIndex={(i) => setSelectedCitIdx(i)}
              recap={recap}
              recapRefreshing={recapRefreshing}
              onRefreshRecap={() => fetchRecap(true)}
              onInspectRecapCitation={(cits, idx) => {
                setInspectorOverride(cits);
                setSelectedCitIdx(idx);
                setRightTab("sources");
              }}
            />
          </div>
        </div>
      </main>

      {/* Mobile Drawer */}
      {mobileDrawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden bg-black/75 backdrop-blur-sm p-3 flex flex-col">
          <div className="flex-1 overflow-hidden">
            <SourceInspector
              panelTab={rightTab}
              onChangeTab={setRightTab}
              citation={activeCitation}
              allCitations={inspectorCitations}
              selectedIndex={
                selectedCitIdx ?? (inspectorCitations.length ? 0 : null)
              }
              onSelectIndex={(i) => setSelectedCitIdx(i)}
              recap={recap}
              recapRefreshing={recapRefreshing}
              onRefreshRecap={() => fetchRecap(true)}
              onInspectRecapCitation={(cits, idx) => {
                setInspectorOverride(cits);
                setSelectedCitIdx(idx);
                setRightTab("sources");
              }}
              onCloseMobile={() => setMobileDrawerOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
