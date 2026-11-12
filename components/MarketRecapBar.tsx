"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Newspaper,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import type { Citation, MarketRecapResponse } from "@/lib/types";
import { citationBadgeLabel } from "@/lib/format";
import { MarkdownView } from "./MarkdownView";

interface Props {
  onInspectRecapCitation?: (citations: Citation[], index: number) => void;
}

export function MarketRecapBar({ onInspectRecapCitation }: Props) {
  const [data, setData] = useState<MarketRecapResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [expanded, setExpanded] = useState<boolean>(false);

  const fetchRecap = useCallback(async (force = false) => {
    if (force) setRefreshing(true);
    try {
      const url = force ? "/api/market/recap?force=true" : "/api/market/recap";
      const res = await fetch(url);
      if (res.ok) {
        const json: MarketRecapResponse = await res.json();
        if (!json.error) {
          setData(json);
        }
      }
    } catch {
      // Ignore transient network errors
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchRecap(false);
  }, [fetchRecap]);

  const benchmarks = data?.benchmarks || [];
  const citations = data?.citations || [];
  const headlines = data?.headlines || [];

  return (
    <section className="mb-4 rounded-xl border border-slate-800/90 bg-[#0b111e] overflow-hidden shadow-lg shadow-black/20">
      {/* Top Live Benchmark Tape + Daily Recap Toggle */}
      <div className="px-3.5 py-2 flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-0.5">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-emerald-300 shrink-0">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Live Tape
          </span>

          {loading && benchmarks.length === 0 ? (
            <span className="text-[11px] font-mono text-slate-500">
              Loading live S&amp;P 500, Nasdaq 100, 10Y Yield, VIX...
            </span>
          ) : (
            benchmarks.map((b) => {
              const up = (b.change_pct ?? 0) >= 0;
              return (
                <div
                  key={b.symbol}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800/80 bg-[#080d18] px-2.5 py-1 text-[11px] font-mono shrink-0"
                >
                  <span className="text-slate-400 font-medium">{b.label}</span>
                  <span className="text-slate-100 font-semibold tabular-nums">
                    {typeof b.price === "number"
                      ? b.symbol === "^TNX"
                        ? `${b.price.toFixed(2)}%`
                        : b.price.toLocaleString("en-US", {
                            maximumFractionDigits: 2,
                          })
                      : "—"}
                  </span>
                  {typeof b.change_pct === "number" && (
                    <span
                      className={`inline-flex items-center tabular-nums ${
                        up ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {up ? (
                        <ArrowUpRight className="h-3 w-3" />
                      ) : (
                        <ArrowDownRight className="h-3 w-3" />
                      )}
                      {up ? "+" : ""}
                      {b.change_pct.toFixed(2)}%
                    </span>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition cursor-pointer ${
              expanded
                ? "border-blue-400/50 bg-blue-500/15 text-blue-200"
                : "border-slate-700/80 bg-[#0d1526] text-slate-200 hover:border-blue-500/40 hover:text-white"
            }`}
          >
            <Newspaper className="h-3.5 w-3.5 text-blue-400" />
            <span>Market News Recap</span>
            <span className="hidden sm:inline font-mono text-[10px] text-emerald-400">
              (0 Quota)
            </span>
            {expanded ? (
              <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
            )}
          </button>

          {expanded && (
            <button
              type="button"
              title="Refresh live market recap"
              disabled={refreshing}
              onClick={() => fetchRecap(true)}
              className="rounded-lg border border-slate-800 bg-[#080d18] p-1.5 text-slate-400 hover:text-slate-200 disabled:opacity-40 cursor-pointer"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
              />
            </button>
          )}
        </div>
      </div>

      {/* Collapsible Verified AI Market News Recap & Breaking Headlines */}
      {expanded && data && (
        <div className="border-t border-slate-800/80 bg-[#090e1a] p-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-7 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-300">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                <span>AI Daily Market &amp; Macro Recap</span>
                <span className="font-mono text-[10px] text-slate-500 font-normal">
                  · {data.model} · Cached 30m (0 Quota)
                </span>
              </div>
              {data.as_of && (
                <span className="font-mono text-[10px] text-slate-500">
                  Updated{" "}
                  {new Date(data.as_of)
                    .toISOString()
                    .slice(11, 16)}{" "}
                  UTC
                </span>
              )}
            </div>

            <div className="rounded-lg border border-slate-800/80 bg-[#0d1422] p-3.5">
              <MarkdownView content={data.recap_markdown} />

              {citations.length > 0 && (
                <div className="mt-3 pt-2.5 border-t border-slate-800/70 flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] font-mono uppercase text-slate-500 mr-1">
                    Verified Recap Sources:
                  </span>
                  {citations.map((cit, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => onInspectRecapCitation?.(citations, idx)}
                      className="inline-flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-950/20 hover:border-amber-400/60 px-2 py-0.5 font-mono text-[10.5px] text-amber-200 transition cursor-pointer"
                    >
                      <span className="opacity-70">[{idx + 1}]</span>
                      <span>{citationBadgeLabel(cit)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="lg:col-span-5 space-y-2">
            <div className="text-xs font-semibold text-slate-300">
              Breaking 24h–48h Market Wire
            </div>
            <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
              {headlines.map((hl, i) => (
                <a
                  key={i}
                  href={hl.url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-lg border border-slate-800/80 bg-[#0d1422] hover:border-slate-700 px-3 py-2 transition group"
                >
                  <div className="flex items-center justify-between gap-2 text-[10px] font-mono text-slate-400 mb-0.5">
                    <span className="text-blue-300 font-semibold">
                      {hl.publisher}
                    </span>
                    <span className="inline-flex items-center gap-1 text-slate-500 group-hover:text-slate-300">
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
          </div>
        </div>
      )}
    </section>
  );
}
