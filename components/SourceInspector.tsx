"use client";

import {
  CheckCircle2,
  Database,
  ExternalLink,
  FileText,
  MessageSquareQuote,
  Radio,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import type { Citation } from "@/lib/types";
import {
  formatCompactUSD,
  formatExactUSD,
  formatMarketMetric,
} from "@/lib/format";

interface Props {
  citation: Citation | null;
  allCitations: Citation[];
  selectedIndex: number | null;
  onSelectIndex: (idx: number) => void;
  onCloseMobile?: () => void;
}

function renderHighlightedContext(context: string, quote: string | undefined) {
  if (!quote || !quote.trim()) {
    return <span>{context}</span>;
  }
  const cleanContext = context;
  const idx = cleanContext.toLowerCase().indexOf(quote.trim().toLowerCase());
  if (idx === -1) {
    // Try matching first 40 chars if minor punctuation differs
    const prefix = quote.trim().slice(0, 42).toLowerCase();
    const approxIdx = prefix.length > 12 ? cleanContext.toLowerCase().indexOf(prefix) : -1;
    if (approxIdx === -1) {
      return <span>{cleanContext}</span>;
    }
    const endIdx = Math.min(cleanContext.length, approxIdx + quote.trim().length);
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
  citation,
  allCitations,
  selectedIndex,
  onSelectIndex,
  onCloseMobile,
}: Props) {
  const edgarSearchUrl = citation?.ticker
    ? `https://www.sec.gov/edgar/searchedgar/companysearch`
    : "https://www.sec.gov/edgar/searchedgar/companysearch";

  return (
    <aside className="flex flex-col h-full rounded-xl border border-slate-800/80 bg-[#0d1422] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/80 bg-[#0a101d]">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
              Primary Source Inspector
            </h3>
            <p className="text-[11px] text-slate-500">
              {allCitations.length} Citation-Guard verified evidence items
            </p>
          </div>
        </div>
        {onCloseMobile && (
          <button
            type="button"
            onClick={onCloseMobile}
            className="lg:hidden rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Empty State */}
      {!allCitations.length && (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
          <div className="h-10 w-10 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 mb-3">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <p className="text-xs font-medium text-slate-300">
            100% Grounded Citation Guard
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-500 max-w-xs">
            Select a Showcase Report or run any equity research query to inspect verified XBRL figures and highlighted SEC filing paragraphs here.
          </p>
        </div>
      )}

      {/* Citation Selector Strip */}
      {allCitations.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto px-3.5 py-2.5 border-b border-slate-800/70 bg-[#090e19]">
          {allCitations.map((c, idx) => {
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
                className={`shrink-0 rounded-md border px-2 py-1 font-mono text-[10px] transition ${tone}`}
              >
                [{idx + 1}] {c.ticker || ""}{" "}
                {c.type === "numeric" || c.type === "market"
                  ? c.concept
                  : c.section || c.type}
              </button>
            );
          })}
        </div>
      )}

      {/* Active Citation Detail */}
      {citation && (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Verification Status Banner */}
          <div className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-950/20 px-3 py-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
              <span className="text-xs font-medium text-emerald-200">
                {citation.type === "numeric"
                  ? "Verified Authoritative XBRL Fact"
                  : citation.type === "market"
                  ? "Verified Live Market Snapshot"
                  : citation.type === "insider"
                  ? "Verified SEC Form 4 / Live Event"
                  : citation.type === "earnings"
                  ? "Verified Earnings / 8-K Ex. 99.1 Quote"
                  : citation.type === "sentiment"
                  ? "Verified Live News / Investor Pulse"
                  : "RapidFuzz Verified SEC Filing Quote"}
              </span>
            </div>
            <span className="font-mono text-[10px] uppercase text-emerald-400/90">
              PASS
            </span>
          </div>

          {citation.type === "market" ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-cyan-500/30 bg-[#091220] p-3.5 space-y-2.5">
                <div className="flex items-center gap-2 text-cyan-400 text-xs font-semibold">
                  <TrendingUp className="h-3.5 w-3.5" />
                  <span>
                    {citation.ticker || "MARKET"} · Live Market & Valuation Feed
                  </span>
                </div>
                <div className="pt-1">
                  <div className="text-[11px] text-slate-500">
                    Verified Market Metric
                  </div>
                  <div className="font-mono text-sm text-slate-100 font-semibold">
                    {citation.concept}
                  </div>
                </div>
                {typeof citation.verified_value === "number" && (
                  <div className="pt-2 border-t border-slate-800/80">
                    <div className="text-[10px] uppercase text-slate-500">
                      Snapshot Value ({citation.unit || "USD"})
                    </div>
                    <div className="font-mono text-lg font-bold text-cyan-300 tabular-nums">
                      {formatMarketMetric(citation.verified_value, citation.unit)}
                    </div>
                  </div>
                )}
                {citation.as_of && (
                  <div className="text-[11px] text-slate-400 pt-1">
                    Snapshot UTC:{" "}
                    <span className="font-mono text-slate-300">
                      {new Date(citation.as_of).toISOString().slice(0, 19).replace("T", " ")}
                    </span>
                  </div>
                )}
              </div>
              {citation.ticker && (
                <a
                  href={`https://finance.yahoo.com/quote/${encodeURIComponent(
                    citation.ticker
                  )}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 transition"
                >
                  <span>Verify Live Quote on Yahoo Finance ({citation.ticker})</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          ) : citation.type === "numeric" ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-blue-500/25 bg-[#090f1d] p-3.5 space-y-2.5">
                <div className="flex items-center gap-2 text-blue-400 text-xs font-semibold">
                  <Database className="h-3.5 w-3.5" />
                  <span>
                    {citation.ticker || "SEC"} · FY{citation.year} {citation.form || "10-K"} XBRL Statement
                  </span>
                </div>

                <div className="pt-1">
                  <div className="text-[11px] text-slate-500">XBRL Concept / Line Item</div>
                  <div className="font-mono text-sm text-slate-100 font-semibold break-all">
                    {citation.concept}
                  </div>
                </div>

                {typeof citation.verified_value === "number" && (
                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/80">
                    <div>
                      <div className="text-[10px] uppercase text-slate-500">
                        Compact Scale
                      </div>
                      <div className="font-mono text-base font-bold text-blue-300 tabular-nums">
                        {formatCompactUSD(citation.verified_value)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase text-slate-500">
                        Exact Reported ({citation.unit || "USD"})
                      </div>
                      <div className="font-mono text-xs text-slate-200 tabular-nums mt-1">
                        {formatExactUSD(citation.verified_value)}
                      </div>
                    </div>
                  </div>
                )}

                {citation.filing_date && (
                  <div className="text-[11px] text-slate-400 pt-1">
                    SEC Filing Date:{" "}
                    <span className="font-mono text-slate-300">
                      {citation.filing_date}
                    </span>
                  </div>
                )}
              </div>

              <a
                href={edgarSearchUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition"
              >
                <span>Verify on SEC EDGAR ({citation.ticker})</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Metadata Header */}
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                <span className="inline-flex items-center gap-1 rounded bg-slate-800/90 px-2 py-0.5 font-mono text-slate-200">
                  {citation.type === "sentiment" ? (
                    <Radio className="h-3 w-3 text-amber-400" />
                  ) : (
                    <FileText className="h-3 w-3 text-emerald-400" />
                  )}
                  {citation.ticker} · {citation.year}
                </span>
                {citation.section && (
                  <span className="rounded bg-slate-800/60 px-2 py-0.5 text-slate-300">
                    {citation.section}
                  </span>
                )}
                {citation.chunk_id && (
                  <span className="font-mono text-[10px] text-slate-500 break-all">
                    ID: {citation.chunk_id}
                  </span>
                )}
              </div>

              {/* Exact Verbatim Quote */}
              {citation.quote && (
                <div className="rounded-lg border-l-2 border-emerald-400 bg-emerald-950/15 p-3">
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-400 mb-1">
                    <MessageSquareQuote className="h-3 w-3" />
                    <span>Exact Verified Quote</span>
                  </div>
                  <p className="text-xs leading-relaxed text-slate-200 italic">
                    &ldquo;{citation.quote}&rdquo;
                  </p>
                </div>
              )}

              {/* Surrounding Primary Chunk Context */}
              {citation.source_context && (
                <div className="rounded-lg border border-slate-800 bg-[#080d18] p-3.5">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
                    Retrieved Primary Source Chunk (Highlighted Match)
                  </div>
                  <p className="text-xs leading-relaxed text-slate-300 whitespace-pre-wrap">
                    {renderHighlightedContext(
                      citation.source_context,
                      citation.quote
                    )}
                  </p>
                </div>
              )}

              <a
                href={citation.source_url || edgarSearchUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition"
              >
                <span>
                  {citation.source_url
                    ? "Open Original External Post / Article"
                    : `Open SEC EDGAR Filings (${citation.ticker})`}
                </span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
