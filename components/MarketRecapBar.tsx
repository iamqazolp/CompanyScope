"use client";

import { ArrowDownRight, ArrowUpRight, Newspaper } from "lucide-react";
import type { MarketRecapResponse } from "@/lib/types";

interface Props {
  data: MarketRecapResponse | null;
  loading: boolean;
  briefActive?: boolean;
  onOpenBrief: () => void;
}

const SHORT_LABELS: Record<string, string> = {
  "S&P 500": "S&P 500",
  "Nasdaq 100": "NDX",
  "Dow 30": "DOW",
  "US 10Y Yield": "10Y",
  "VIX Volatility": "VIX",
  Bitcoin: "BTC",
};

export function MarketRecapBar({
  data,
  loading,
  briefActive = false,
  onOpenBrief,
}: Props) {
  const benchmarks = data?.benchmarks || [];

  return (
    <div className="border-b border-slate-800/75 bg-[#070b13]">
      <div className="mx-auto max-w-[1520px] px-4 sm:px-6 h-9 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3.5 overflow-x-auto no-scrollbar text-[11px] font-mono">
          <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-400 shrink-0">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Markets
          </span>

          {loading && benchmarks.length === 0 ? (
            <span className="text-[11px] text-slate-600">Loading tape...</span>
          ) : (
            benchmarks.map((b) => {
              const up = (b.change_pct ?? 0) >= 0;
              const lbl = SHORT_LABELS[b.label] || b.label;
              return (
                <div
                  key={b.symbol}
                  className="inline-flex items-center gap-1.5 shrink-0"
                >
                  <span className="text-slate-500">{lbl}</span>
                  <span className="text-slate-200 font-medium tabular-nums">
                    {typeof b.price === "number"
                      ? b.symbol === "^TNX"
                        ? `${b.price.toFixed(2)}%`
                        : b.price.toLocaleString("en-US", {
                            maximumFractionDigits: b.price >= 1000 ? 0 : 2,
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
                        <ArrowUpRight className="h-2.5 w-2.5" />
                      ) : (
                        <ArrowDownRight className="h-2.5 w-2.5" />
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

        <button
          type="button"
          onClick={onOpenBrief}
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium shrink-0 transition cursor-pointer ${
            briefActive
              ? "border-blue-500/50 bg-blue-500/15 text-blue-200"
              : "border-slate-800 bg-[#0d1422] text-slate-300 hover:border-slate-700 hover:text-white"
          }`}
        >
          <Newspaper className="h-3 w-3 text-blue-400" />
          <span>Market Brief</span>
        </button>
      </div>
    </div>
  );
}
