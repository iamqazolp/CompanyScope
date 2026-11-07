"use client";

import { useState } from "react";
import { BarChart3, TrendingUp } from "lucide-react";
import type { FinancialRow } from "@/lib/types";
import { formatCompactUSD } from "@/lib/format";

type MetricKey =
  | "Revenue"
  | "Operating Income"
  | "Net Income"
  | "Free Cash Flow";

const METRICS: MetricKey[] = [
  "Revenue",
  "Operating Income",
  "Net Income",
  "Free Cash Flow",
];

interface Props {
  ticker: string;
  rows: FinancialRow[];
  loading: boolean;
}

export function FinancialChart({ ticker, rows, loading }: Props) {
  const [activeMetric, setActiveMetric] = useState<MetricKey>("Revenue");

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800/80 bg-[#0d1422] p-4 animate-pulse">
        <div className="h-4 w-48 rounded bg-slate-800 mb-4" />
        <div className="grid grid-cols-4 gap-3 mb-4">
          {[0, 1, 2, 3].map((k) => (
            <div key={k} className="h-14 rounded-lg bg-slate-800/60" />
          ))}
        </div>
        <div className="h-28 rounded-lg bg-slate-800/40" />
      </div>
    );
  }

  if (!rows.length) {
    return null;
  }

  const sorted = [...rows].sort((a, b) => a.year - b.year);
  const latest = sorted[sorted.length - 1];
  const prev = sorted.length > 1 ? sorted[sorted.length - 2] : undefined;

  const values = sorted.map((r) => Number(r[activeMetric] ?? 0));
  const maxAbs = Math.max(...values.map((v) => Math.abs(v)), 1);

  const calcYoY = (key: MetricKey): string | null => {
    if (!latest || !prev) return null;
    const cur = latest[key];
    const old = prev[key];
    if (
      typeof cur !== "number" ||
      typeof old !== "number" ||
      Math.abs(old) === 0
    ) {
      return null;
    }
    const pct = ((cur - old) / Math.abs(old)) * 100;
    return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
  };

  return (
    <section className="rounded-xl border border-slate-800/80 bg-[#0d1422]/90 p-4 shadow-lg shadow-black/20">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3.5">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/10 border border-blue-500/25 text-blue-400">
            <BarChart3 className="h-3.5 w-3.5" />
          </span>
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              {ticker} · Audited SEC EDGAR 10-K XBRL Fundamentals
            </h2>
            <p className="text-[11px] text-slate-500">
              FY{sorted[0].year}–FY{latest.year} structured statement facts (click metric to chart)
            </p>
          </div>
        </div>

        <div className="inline-flex rounded-lg border border-slate-800 bg-[#090e19] p-0.5">
          {METRICS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setActiveMetric(m)}
              className={`px-2.5 py-1 text-[11px] font-medium rounded-md transition ${
                activeMetric === m
                  ? "bg-blue-600/25 text-blue-300 border border-blue-500/40"
                  : "text-slate-400 hover:text-slate-200 border border-transparent"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* Latest Fiscal Year KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4">
        {METRICS.map((m) => {
          const yoy = calcYoY(m);
          const isPositive = yoy ? !yoy.startsWith("-") : true;
          const isSelected = activeMetric === m;
          return (
            <button
              key={m}
              type="button"
              onClick={() => setActiveMetric(m)}
              className={`text-left rounded-lg border p-2.5 transition ${
                isSelected
                  ? "border-blue-500/40 bg-blue-950/20"
                  : "border-slate-800/70 bg-[#0a101c] hover:border-slate-700"
              }`}
            >
              <div className="flex items-center justify-between text-[11px] text-slate-400">
                <span>{m}</span>
                <span className="font-mono text-[10px] text-slate-500">
                  FY{latest.year}
                </span>
              </div>
              <div className="mt-1 flex items-baseline justify-between gap-2">
                <span className="font-mono text-sm font-semibold tabular-nums text-slate-100">
                  {formatCompactUSD(latest[m])}
                </span>
                {yoy && (
                  <span
                    className={`inline-flex items-center gap-0.5 font-mono text-[10px] tabular-nums ${
                      isPositive ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    <TrendingUp className="h-2.5 w-2.5" />
                    {yoy}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Multi-Year Bar Visualization */}
      <div className="grid grid-cols-5 gap-3 items-end pt-3 px-2 h-32 rounded-lg bg-[#090e19] border border-slate-800/60 pb-2.5">
        {sorted.map((row, idx) => {
          const rawVal = row[activeMetric];
          const numVal = typeof rawVal === "number" ? rawVal : 0;
          const heightPct = Math.max(8, Math.round((Math.abs(numVal) / maxAbs) * 74));
          const prevVal = idx > 0 ? sorted[idx - 1][activeMetric] : null;
          const delta =
            typeof rawVal === "number" &&
            typeof prevVal === "number" &&
            Math.abs(prevVal) > 0
              ? ((rawVal - prevVal) / Math.abs(prevVal)) * 100
              : null;

          return (
            <div
              key={row.year}
              className="flex flex-col items-center justify-end h-full group"
            >
              <div className="font-mono text-[10px] tabular-nums text-slate-300 mb-1">
                {formatCompactUSD(rawVal)}
              </div>
              <div className="w-full max-w-[54px] flex items-end justify-center h-[74px]">
                <div
                  style={{ height: `${heightPct}%` }}
                  className="w-full rounded-t-md bg-gradient-to-t from-blue-600/70 to-cyan-400/80 border border-blue-400/30 transition-all duration-300 group-hover:from-blue-500 group-hover:to-emerald-400"
                />
              </div>
              <div className="mt-1.5 flex items-center gap-1 font-mono text-[11px] text-slate-400">
                <span>FY{String(row.year).slice(-2)}</span>
                {delta !== null && (
                  <span
                    className={`text-[9px] ${
                      delta >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {delta >= 0 ? "+" : ""}
                    {delta.toFixed(0)}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
