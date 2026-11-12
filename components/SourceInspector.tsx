"use client";

import { useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Database,
  ExternalLink,
  FileText,
  Newspaper,
  Radio,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import type { Citation, MarketRecapResponse } from "@/lib/types";
import {
  citationBadgeLabel,
  formatCompactUSD,
  formatExactUSD,
  formatMarketMetric,
} from "@/lib/format";
import { MarkdownView } from "./MarkdownView";

interface Props {
  panelTab: "sources" | "brief";
  onChangeTab: (tab: "sources" | "brief") => void;
  citation: Citation | null;
  allCitations: Citation[];
  selectedIndex: number | null;
  onSelectIndex: (idx: number) => void;
  recap?: MarketRecapResponse | null;
  recapRefreshing?: boolean;
  onRefreshRecap?: () => void;
  onInspectRecapCitation?: (citations: Citation[], index: number) => void;
  onCloseMobile?: () => void;
}

type FilterCat = "all" | "data" | "sec" | "pulse";

function matchesFilter(c: Citation, f: FilterCat): boolean {
  if (f === "all") return true;
  if (f === "data") return c.type === "numeric" || c.type === "market";
  if (f === "sec") return c.type === "narrative" || c.type === "earnings";
  return c.type === "sentiment" || c.type === "insider";
}

function renderHighlightedContext(context: string, quote: string | undefined) {
  if (!quote || !quote.trim()) {
    return <span>{context}</span>;
  }
  const cleanContext = context;
  const idx = cleanContext.toLowerCase().indexOf(quote.trim().toLowerCase());
  if (idx === -1) {
    const prefix = quote.trim().slice(0, 42).toLowerCase();
    const approxIdx =
      prefix.length > 12 ? cleanContext.toLowerCase().indexOf(prefix) : -1;
    if (approxIdx === -1) {
      return <span>{cleanContext}</span>;
    }
    const endIdx = Math.min(
      cleanContext.length,
      approxIdx + quote.trim().length
    );
    return (
      <>
        <span>{cleanContext.slice(0, approxIdx)}</span>
        <mark className="bg-emerald-500/25 text-emerald-200 border-b border-emerald-400/70 px-1 rounded">
          {cleanContext.slice(approxIdx, endIdx)}
        </mark>
        <span>{cleanContext.slice(endIdx)}</span>
      </>
    );
  }
  const endIdx = idx + quote.trim().length;
  return (
    <>
      <span>{cleanContext.slice(0, idx)}</span>
      <mark className="bg-emerald-500/25 text-emerald-100 border-b border-emerald-400 px-1 rounded">
        {cleanContext.slice(idx, endIdx)}
      </mark>
      <span>{cleanContext.slice(endIdx)}</span>
    </>
  );
}

export function SourceInspector({
  panelTab,
  onChangeTab,
  citation,
  allCitations,
  selectedIndex,
  onSelectIndex,
  recap = null,
  recapRefreshing = false,
  onRefreshRecap,
  onInspectRecapCitation,
  onCloseMobile,
}: Props) {
  const [filter, setFilter] = useState<FilterCat>("all");

  const filteredEntries = useMemo(
    () =>
      allCitations
        .map((c, idx) => ({ c, idx }))
        .filter(({ c }) => matchesFilter(c, filter)),
    [allCitations, filter]
  );

  const curPos = filteredEntries.findIndex((e) => e.idx === selectedIndex);
  const canStep = panelTab === "sources" && filteredEntries.length > 1;

  const stepPrev = () => {
    if (!filteredEntries.length) return;
    const nextPos =
      curPos <= 0 ? filteredEntries.length - 1 : curPos - 1;
    onSelectIndex(filteredEntries[nextPos].idx);
  };

  const stepNext = () => {
    if (!filteredEntries.length) return;
    const nextPos =
      curPos < 0 || curPos >= filteredEntries.length - 1 ? 0 : curPos + 1;
    onSelectIndex(filteredEntries[nextPos].idx);
  };

  const edgarSearchUrl = "https://www.sec.gov/edgar/searchedgar/companysearch";
  const recapCitations = recap?.citations || [];
  const headlines = recap?.headlines || [];

  return (
    <aside className="flex flex-col h-full rounded-xl border border-slate-800/90 bg-[#0b111d] overflow-hidden">
      {/* Top Tab Bar + Prev/Next Controls */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800/80 bg-[#090e19]">
        <div className="inline-flex items-center gap-1 rounded-md border border-slate-800 bg-[#070b14] p-0.5">
          <button
            type="button"
            onClick={() => onChangeTab("sources")}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition cursor-pointer ${
              panelTab === "sources"
                ? "bg-slate-800 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <ShieldCheck className="h-3 w-3 text-emerald-400" />
            <span>Sources</span>
            {allCitations.length > 0 && (
              <span className="font-mono text-[10px] text-slate-400">
                {allCitations.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => onChangeTab("brief")}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium transition cursor-pointer ${
              panelTab === "brief"
                ? "bg-slate-800 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Newspaper className="h-3 w-3 text-blue-400" />
            <span>Market Brief</span>
          </button>
        </div>

        <div className="flex items-center gap-1">
          {canStep && (
            <div className="inline-flex items-center rounded border border-slate-800 bg-[#070b14]">
              <button
                type="button"
                onClick={stepPrev}
                title="Previous source"
                className="p-1 text-slate-400 hover:text-white cursor-pointer"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={stepNext}
                title="Next source"
                className="p-1 text-slate-400 hover:text-white border-l border-slate-800 cursor-pointer"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {panelTab === "brief" && onRefreshRecap && (
            <button
              type="button"
              disabled={recapRefreshing}
              onClick={onRefreshRecap}
              title="Refresh market brief"
              className="rounded border border-slate-800 bg-[#070b14] p-1 text-slate-400 hover:text-white disabled:opacity-40 cursor-pointer"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${
                  recapRefreshing ? "animate-spin" : ""
                }`}
              />
            </button>
          )}

          {onCloseMobile && (
            <button
              type="button"
              onClick={onCloseMobile}
              className="lg:hidden rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* TAB 1: SOURCES INSPECTOR */}
      {panelTab === "sources" ? (
        <>
          {!allCitations.length ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
              <ShieldCheck className="h-5 w-5 text-slate-600 mb-2" />
              <p className="text-xs text-slate-400">No active citations</p>
              <button
                type="button"
                onClick={() => onChangeTab("brief")}
                className="mt-2.5 text-[11px] font-mono text-blue-400 hover:text-blue-300 cursor-pointer"
              >
                View Market Brief →
              </button>
            </div>
          ) : (
            <>
              {/* Filter + Citation Selector Strip */}
              <div className="border-b border-slate-800/70 bg-[#080c16] px-3 py-2 space-y-2">
                {allCitations.length >= 3 && (
                  <div className="flex items-center gap-1">
                    {(
                      [
                        ["all", "All"],
                        ["data", "Data"],
                        ["sec", "SEC"],
                        ["pulse", "Pulse"],
                      ] as const
                    ).map(([key, lbl]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setFilter(key)}
                        className={`px-2 py-0.5 rounded font-mono text-[10px] transition cursor-pointer ${
                          filter === key
                            ? "bg-slate-800 text-slate-100"
                            : "text-slate-500 hover:text-slate-300"
                        }`}
                      >
                        {lbl}
                      </button>
                    ))}
                  </div>
                )}

                <div className="flex gap-1.5 overflow-x-auto no-scrollbar pb-0.5">
                  {filteredEntries.map(({ c, idx }) => {
                    const active = selectedIndex === idx;
                    const tone =
                      c.type === "numeric" || c.type === "market"
                        ? active
                          ? "border-blue-400/60 bg-blue-500/20 text-blue-200"
                          : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-200"
                        : c.type === "sentiment" || c.type === "insider"
                        ? active
                          ? "border-amber-400/60 bg-amber-500/20 text-amber-200"
                          : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-200"
                        : active
                        ? "border-emerald-400/60 bg-emerald-500/20 text-emerald-200"
                        : "border-slate-800 bg-slate-900/70 text-slate-400 hover:text-slate-200";
                    return (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => onSelectIndex(idx)}
                        className={`shrink-0 rounded border px-2 py-0.5 font-mono text-[10px] transition cursor-pointer ${tone}`}
                      >
                        [{idx + 1}] {c.ticker || ""}{" "}
                        {c.type === "numeric" || c.type === "market"
                          ? c.concept
                          : c.section || c.type}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Active Citation Detail */}
              {citation && (
                <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
                  {citation.type === "market" ? (
                    <div className="space-y-2.5">
                      <div className="rounded-lg border border-cyan-500/25 bg-[#08111e] p-3 space-y-2">
                        <div className="flex items-center justify-between text-xs">
                          <span className="inline-flex items-center gap-1.5 text-cyan-400 font-mono font-semibold">
                            <TrendingUp className="h-3.5 w-3.5" />
                            {citation.ticker || "MARKET"} · Live Snapshot
                          </span>
                          <span className="font-mono text-[10px] text-emerald-400">
                            VERIFIED
                          </span>
                        </div>
                        <div className="font-mono text-xs text-slate-300">
                          {citation.concept}
                        </div>
                        {typeof citation.verified_value === "number" && (
                          <div className="pt-2 border-t border-slate-800/80 font-mono text-lg font-bold text-cyan-300 tabular-nums">
                            {formatMarketMetric(
                              citation.verified_value,
                              citation.unit
                            )}
                          </div>
                        )}
                        {citation.as_of && (
                          <div className="font-mono text-[10px] text-slate-500">
                            {new Date(citation.as_of)
                              .toISOString()
                              .slice(0, 19)
                              .replace("T", " ")}{" "}
                            UTC
                          </div>
                        )}
                      </div>
                      {citation.ticker && (
                        <a
                          href={`https://www.tradingview.com/symbols/${encodeURIComponent(
                            citation.ticker
                          )}/`}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] font-mono text-cyan-400 hover:text-cyan-300"
                        >
                          <span>TradingView ({citation.ticker})</span>
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  ) : citation.type === "numeric" ? (
                    <div className="space-y-2.5">
                      <div className="rounded-lg border border-blue-500/25 bg-[#080f1d] p-3 space-y-2">
                        <div className="flex items-center justify-between text-xs">
                          <span className="inline-flex items-center gap-1.5 text-blue-400 font-mono font-semibold">
                            <Database className="h-3.5 w-3.5" />
                            {citation.ticker || "SEC"} · FY{citation.year}{" "}
                            {citation.form || "10-K"}
                          </span>
                          <span className="font-mono text-[10px] text-emerald-400">
                            XBRL
                          </span>
                        </div>

                        <div className="font-mono text-xs text-slate-200 break-all">
                          {citation.concept}
                        </div>

                        {typeof citation.verified_value === "number" && (
                          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/80">
                            <div>
                              <div className="text-[9.5px] uppercase text-slate-500">
                                Scale
                              </div>
                              <div className="font-mono text-base font-bold text-blue-300 tabular-nums">
                                {formatCompactUSD(citation.verified_value)}
                              </div>
                            </div>
                            <div>
                              <div className="text-[9.5px] uppercase text-slate-500">
                                Exact ({citation.unit || "USD"})
                              </div>
                              <div className="font-mono text-[11px] text-slate-200 tabular-nums mt-1">
                                {formatExactUSD(citation.verified_value)}
                              </div>
                            </div>
                          </div>
                        )}

                        {citation.filing_date && (
                          <div className="font-mono text-[10px] text-slate-500">
                            Filed {citation.filing_date}
                          </div>
                        )}
                      </div>

                      <a
                        href={edgarSearchUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] font-mono text-blue-400 hover:text-blue-300"
                      >
                        <span>SEC EDGAR ({citation.ticker})</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  ) : (
                    <div className="space-y-2.5">
                      <div className="flex flex-wrap items-center justify-between gap-1.5 text-[11px]">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="inline-flex items-center gap-1 rounded bg-slate-800/90 px-2 py-0.5 font-mono text-slate-200">
                            {citation.type === "sentiment" ? (
                              <Radio className="h-3 w-3 text-amber-400" />
                            ) : (
                              <FileText className="h-3 w-3 text-emerald-400" />
                            )}
                            {citation.ticker} · {citation.year}
                          </span>
                          {citation.section && (
                            <span className="rounded bg-slate-800/60 px-2 py-0.5 text-slate-300 font-mono text-[10.5px]">
                              {citation.section}
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-[10px] text-emerald-400">
                          VERIFIED
                        </span>
                      </div>

                      {/* Primary Excerpt with Highlighted Verbatim Quote */}
                      <div className="rounded-lg border border-slate-800 bg-[#080c16] p-3 text-xs leading-relaxed text-slate-300 whitespace-pre-wrap max-h-80 overflow-y-auto">
                        {citation.source_context
                          ? renderHighlightedContext(
                              citation.source_context,
                              citation.quote
                            )
                          : citation.quote || ""}
                      </div>

                      <div className="flex items-center justify-between pt-0.5">
                        {citation.chunk_id ? (
                          <span className="font-mono text-[9.5px] text-slate-600 truncate max-w-[180px]">
                            {citation.chunk_id}
                          </span>
                        ) : (
                          <span />
                        )}
                        {citation.source_url ? (
                          <a
                            href={citation.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] font-mono text-amber-400 hover:text-amber-300"
                          >
                            <span>Source</span>
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        ) : (
                          <a
                            href={edgarSearchUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] font-mono text-emerald-400 hover:text-emerald-300"
                          >
                            <span>SEC EDGAR</span>
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </>
      ) : (
        /* TAB 2: LIVE MARKET BRIEF & WIRE */
        <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
          {recap ? (
            <>
              <div className="rounded-lg border border-slate-800/90 bg-[#080c16] p-3 space-y-2.5">
                <div className="flex items-center justify-between text-[10.5px] font-mono text-slate-500">
                  <span className="text-emerald-400 font-semibold">
                    Daily Pulse
                  </span>
                  {recap.as_of && (
                    <span>
                      {new Date(recap.as_of).toISOString().slice(11, 16)} UTC
                    </span>
                  )}
                </div>

                <MarkdownView content={recap.recap_markdown} />

                {recapCitations.length > 0 && (
                  <div className="pt-2 border-t border-slate-800/70 flex flex-wrap gap-1">
                    {recapCitations.map((cit, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() =>
                          onInspectRecapCitation?.(recapCitations, idx)
                        }
                        className="inline-flex items-center gap-1 rounded border border-amber-500/30 bg-amber-950/20 hover:border-amber-400/60 px-1.5 py-0.5 font-mono text-[10px] text-amber-200 transition cursor-pointer"
                      >
                        <span className="opacity-70">[{idx + 1}]</span>
                        <span>{citationBadgeLabel(cit)}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {headlines.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[10.5px] font-mono uppercase tracking-wider text-slate-500">
                    Wire
                  </div>
                  {headlines.map((hl, i) => (
                    <a
                      key={i}
                      href={hl.url || "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="block rounded-lg border border-slate-800/80 bg-[#080c16] hover:border-slate-700 px-3 py-2 transition group"
                    >
                      <div className="flex items-center justify-between gap-2 text-[10px] font-mono text-slate-500 mb-0.5">
                        <span className="text-blue-300">{hl.publisher}</span>
                        <span className="inline-flex items-center gap-1 group-hover:text-slate-300">
                          {hl.age}
                          <ExternalLink className="h-2.5 w-2.5" />
                        </span>
                      </div>
                      <p className="text-xs text-slate-200 group-hover:text-white line-clamp-2 leading-snug">
                        {hl.title}
                      </p>
                    </a>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="p-6 text-center font-mono text-xs text-slate-500">
              Loading market brief...
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
