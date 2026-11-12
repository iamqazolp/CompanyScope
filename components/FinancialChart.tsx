"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import type { FinancialRow } from "@/lib/types";
import { formatCompactUSD } from "@/lib/format";

type StatementTab = "income" | "balance" | "cashflow" | "ratios";
type Cadence = "annual" | "quarterly";
type FormatKind = "usd" | "eps" | "pct" | "mult";

interface LineSpec {
  key: keyof FinancialRow;
  label: string;
  format: FormatKind;
  highlight?: boolean;
}

const STATEMENT_LINES: Record<StatementTab, LineSpec[]> = {
  income: [
    { key: "Revenue", label: "Revenue", format: "usd", highlight: true },
    { key: "Gross Profit", label: "Gross Profit", format: "usd" },
    { key: "R&D Expense", label: "R&D Expense", format: "usd" },
    { key: "SG&A Expense", label: "SG&A Expense", format: "usd" },
    {
      key: "Operating Income",
      label: "Operating Income",
      format: "usd",
      highlight: true,
    },
    { key: "Net Income", label: "Net Income", format: "usd", highlight: true },
    { key: "Diluted EPS", label: "Diluted EPS", format: "eps" },
  ],
  balance: [
    { key: "Cash & Equivalents", label: "Cash & Short-Term Inv.", format: "usd" },
    {
      key: "Total Assets",
      label: "Total Assets",
      format: "usd",
      highlight: true,
    },
    { key: "Long-Term Debt", label: "Long-Term Debt", format: "usd" },
    { key: "Total Liabilities", label: "Total Liabilities", format: "usd" },
    {
      key: "Stockholders Equity",
      label: "Stockholders' Equity",
      format: "usd",
      highlight: true,
    },
    { key: "Net Cash", label: "Net Cash / (Debt)", format: "usd" },
  ],
  cashflow: [
    {
      key: "Operating Cash Flow",
      label: "Operating Cash Flow",
      format: "usd",
      highlight: true,
    },
    { key: "CapEx", label: "Capital Expenditures", format: "usd" },
    {
      key: "Free Cash Flow",
      label: "Free Cash Flow",
      format: "usd",
      highlight: true,
    },
    { key: "Share Repurchases", label: "Share Repurchases", format: "usd" },
    { key: "Dividends Paid", label: "Dividends Paid", format: "usd" },
  ],
  ratios: [
    {
      key: "Gross Margin %",
      label: "Gross Margin",
      format: "pct",
      highlight: true,
    },
    {
      key: "Operating Margin %",
      label: "Operating Margin",
      format: "pct",
      highlight: true,
    },
    { key: "Net Margin %", label: "Net Margin", format: "pct", highlight: true },
    { key: "FCF Margin %", label: "FCF Margin", format: "pct" },
    { key: "ROE %", label: "Return on Equity (ROE)", format: "pct" },
    { key: "Debt / Equity", label: "Long-Term Debt / Equity", format: "mult" },
  ],
};

function formatCell(val: unknown, fmt: FormatKind): string {
  if (typeof val !== "number" || Number.isNaN(val)) return "—";
  if (fmt === "usd") return formatCompactUSD(val);
  if (fmt === "eps") return `${val < 0 ? "-" : ""}$${Math.abs(val).toFixed(2)}`;
  if (fmt === "pct") return `${val.toFixed(1)}%`;
  return `${val.toFixed(2)}x`;
}

function periodLabel(r: FinancialRow): string {
  if (r.period) return r.period;
  return `FY${String(r.year).slice(-2)}`;
}

interface Props {
  ticker: string;
  rows: FinancialRow[];
  quarterlyRows?: FinancialRow[];
  loading: boolean;
  onAuditMetric?: (prompt: string) => void;
}

export function FinancialChart({
  ticker,
  rows,
  quarterlyRows = [],
  loading,
  onAuditMetric,
}: Props) {
  const [statement, setStatement] = useState<StatementTab>("income");
  const [cadence, setCadence] = useState<Cadence>("annual");
  const [activeKey, setActiveKey] = useState<keyof FinancialRow>("Revenue");

  // Keep active chart metric aligned with active statement tab
  useEffect(() => {
    const lines = STATEMENT_LINES[statement];
    if (!lines.some((l) => l.key === activeKey) && lines[0]) {
      setActiveKey(lines[0].key);
    }
  }, [statement, activeKey]);

  if (loading) {
    return (
      <div className="p-4 animate-pulse space-y-3 bg-[#090e19]">
        <div className="h-7 w-72 rounded bg-slate-800/50" />
        <div className="h-32 rounded-lg bg-slate-800/35" />
        <div className="h-44 rounded-lg bg-slate-800/30" />
      </div>
    );
  }

  const activeSeries =
    cadence === "quarterly" && quarterlyRows.length > 0 ? quarterlyRows : rows;

  if (!activeSeries.length) {
    return (
      <div className="p-6 text-center font-mono text-xs text-slate-500 bg-[#090e19]">
        No SEC XBRL statement data cached for {ticker}.
      </div>
    );
  }

  const sorted =
    cadence === "annual"
      ? [...activeSeries].sort((a, b) => a.year - b.year)
      : [...activeSeries];

  const visibleLines = STATEMENT_LINES[statement].filter((spec) =>
    sorted.some((r) => typeof r[spec.key] === "number")
  );
  const currentSpec =
    visibleLines.find((l) => l.key === activeKey) ||
    visibleLines[0] ||
    STATEMENT_LINES.income[0];

  const chartVals = sorted.map((r) => {
    const v = r[currentSpec.key];
    return typeof v === "number" ? v : 0;
  });
  const maxAbs = Math.max(...chartVals.map((v) => Math.abs(v)), 1);

  // Auto-computed XBRL diagnostic signals from Annual series
  const annualSorted = [...rows].sort((a, b) => a.year - b.year);
  const latestA = annualSorted[annualSorted.length - 1];
  const firstA = annualSorted[0];
  const spanYrs =
    latestA && firstA ? Math.max(1, latestA.year - firstA.year) : 1;
  const revCagr =
    latestA?.Revenue &&
    firstA?.Revenue &&
    firstA.Revenue > 0 &&
    latestA.Revenue > 0 &&
    annualSorted.length >= 2
      ? (Math.pow(latestA.Revenue / firstA.Revenue, 1 / spanYrs) - 1) * 100
      : null;
  const fcfConv =
    latestA?.["Free Cash Flow"] &&
    latestA?.["Operating Cash Flow"] &&
    latestA["Operating Cash Flow"] > 0
      ? (latestA["Free Cash Flow"] / latestA["Operating Cash Flow"]) * 100
      : null;

  return (
    <div className="p-3.5 space-y-3 bg-[#090e19]">
      {/* Statement Tabs + Annual/Quarterly Toggle + XBRL Health Diagnostics */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex rounded-md border border-slate-800 bg-[#070b14] p-0.5">
          {(
            [
              ["income", "Income"],
              ["balance", "Balance Sheet"],
              ["cashflow", "Cash Flow"],
              ["ratios", "Margins & ROE"],
            ] as const
          ).map(([id, lbl]) => (
            <button
              key={id}
              type="button"
              onClick={() => setStatement(id)}
              className={`px-2.5 py-1 rounded text-[11px] font-medium transition cursor-pointer ${
                statement === id
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {lbl}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Auto-computed XBRL Signals */}
          <div className="hidden xl:flex items-center gap-1.5 font-mono text-[10px]">
            {revCagr !== null && (
              <span className="rounded border border-slate-800 bg-[#070b14] px-2 py-0.5 text-slate-300">
                {spanYrs}Y Rev CAGR{" "}
                <strong
                  className={
                    revCagr >= 0 ? "text-emerald-400" : "text-rose-400"
                  }
                >
                  {revCagr >= 0 ? "+" : ""}
                  {revCagr.toFixed(1)}%
                </strong>
              </span>
            )}
            {typeof latestA?.["Operating Margin %"] === "number" && (
              <span className="rounded border border-slate-800 bg-[#070b14] px-2 py-0.5 text-slate-300">
                Op Margin{" "}
                <strong className="text-cyan-300">
                  {latestA["Operating Margin %"].toFixed(1)}%
                </strong>
              </span>
            )}
            {fcfConv !== null && (
              <span className="rounded border border-slate-800 bg-[#070b14] px-2 py-0.5 text-slate-300">
                FCF/OCF{" "}
                <strong className="text-emerald-300">
                  {fcfConv.toFixed(0)}%
                </strong>
              </span>
            )}
          </div>

          <div className="inline-flex rounded-md border border-slate-800 bg-[#070b14] p-0.5 font-mono text-[10.5px]">
            <button
              type="button"
              onClick={() => setCadence("annual")}
              className={`px-2 py-0.5 rounded transition cursor-pointer ${
                cadence === "annual"
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "text-slate-500 hover:text-slate-200"
              }`}
            >
              Annual (10-K)
            </button>
            <button
              type="button"
              disabled={quarterlyRows.length === 0}
              onClick={() => setCadence("quarterly")}
              className={`px-2 py-0.5 rounded transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
                cadence === "quarterly"
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "text-slate-500 hover:text-slate-200"
              }`}
            >
              Quarterly (10-Q)
            </button>
          </div>
        </div>
      </div>

      {/* Interactive Selected-Line Bar Chart */}
      <div className="rounded-lg bg-[#070b14] border border-slate-800/70 px-3 pt-2.5 pb-2">
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2 font-mono text-[11px]">
            <span className="font-semibold text-slate-200">
              {currentSpec.label}
            </span>
            <span className="text-[10px] text-slate-500">
              ({cadence === "annual" ? "SEC 10-K Annual" : "SEC 10-Q Quarterly"})
            </span>
          </div>

          {onAuditMetric && sorted.length > 0 && (
            <button
              type="button"
              onClick={() => {
                const firstP = periodLabel(sorted[0]);
                const lastP = periodLabel(sorted[sorted.length - 1]);
                const lastV = formatCell(
                  sorted[sorted.length - 1][currentSpec.key],
                  currentSpec.format
                );
                onAuditMetric(
                  `Audit ${ticker}'s ${currentSpec.label} trajectory from ${firstP} to ${lastP} (latest ${lastV}) using SEC 10-K/10-Q MD&A disclosures and 8-K commentary to explain the underlying business drivers and risks.`
                );
              }}
              className="inline-flex items-center gap-1 rounded border border-emerald-500/35 bg-emerald-500/10 hover:bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] text-emerald-300 transition cursor-pointer"
            >
              <Sparkles className="h-2.5 w-2.5" />
              <span>AI Audit {currentSpec.label}</span>
            </button>
          )}
        </div>

        <div
          style={{
            gridTemplateColumns: `repeat(${sorted.length}, minmax(0, 1fr))`,
          }}
          className="grid gap-2.5 items-end h-32 pt-2"
        >
          {sorted.map((row, idx) => {
            const rawVal = row[currentSpec.key];
            const numVal = typeof rawVal === "number" ? rawVal : 0;
            const isNeg = numVal < 0;
            const heightPct =
              typeof rawVal === "number"
                ? Math.max(8, Math.round((Math.abs(numVal) / maxAbs) * 78))
                : 4;
            const prevVal = idx > 0 ? sorted[idx - 1][currentSpec.key] : null;
            const delta =
              typeof rawVal === "number" &&
              typeof prevVal === "number" &&
              Math.abs(prevVal) > 0
                ? currentSpec.format === "pct"
                  ? rawVal - prevVal
                  : ((rawVal - prevVal) / Math.abs(prevVal)) * 100
                : null;

            return (
              <div
                key={`${periodLabel(row)}-${idx}`}
                className="flex flex-col items-center justify-end h-full"
              >
                <div className="font-mono text-[10px] tabular-nums text-slate-300 mb-1">
                  {formatCell(rawVal, currentSpec.format)}
                </div>
                <div className="w-full max-w-[46px] flex items-end justify-center h-[72px]">
                  <div
                    style={{ height: `${heightPct}%` }}
                    className={`w-full rounded-t border transition-all duration-200 ${
                      isNeg
                        ? "bg-gradient-to-t from-rose-700/75 to-rose-400/80 border-rose-400/35"
                        : "bg-gradient-to-t from-blue-600/75 to-cyan-400/85 border-blue-400/35"
                    }`}
                  />
                </div>
                <div className="mt-1 flex flex-wrap items-center justify-center gap-1 font-mono text-[10px] text-slate-400">
                  <span>{periodLabel(row)}</span>
                  {delta !== null && (
                    <span
                      className={`text-[9px] tabular-nums ${
                        delta >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {delta >= 0 ? "+" : ""}
                      {currentSpec.format === "pct"
                        ? `${delta.toFixed(1)}pp`
                        : `${delta.toFixed(0)}%`}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Multi-Period Statement Matrix Table (Click any row to plot or AI-audit) */}
      <div className="rounded-lg border border-slate-800/80 bg-[#070b14] overflow-x-auto">
        <table className="w-full text-left border-collapse font-mono text-[11px]">
          <thead>
            <tr className="border-b border-slate-800/80 text-[10px] text-slate-500 uppercase">
              <th className="py-2 pl-3 pr-2 font-medium">
                XBRL Line Item (Click to Plot)
              </th>
              {sorted.map((r, i) => (
                <th
                  key={i}
                  className="py-2 px-2 text-right font-medium tabular-nums"
                >
                  {periodLabel(r)}
                </th>
              ))}
              <th className="py-2 px-2 text-right font-medium">Δ</th>
              {onAuditMetric && (
                <th className="py-2 pl-1 pr-2.5 text-right font-medium w-14">
                  AI
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {visibleLines.map((spec) => {
              const selected = currentSpec.key === spec.key;
              const lastVal = sorted[sorted.length - 1]?.[spec.key];
              const prevVal =
                sorted.length >= 2
                  ? sorted[sorted.length - 2]?.[spec.key]
                  : null;
              const chg =
                typeof lastVal === "number" &&
                typeof prevVal === "number" &&
                Math.abs(prevVal) > 0
                  ? spec.format === "pct"
                    ? lastVal - prevVal
                    : ((lastVal - prevVal) / Math.abs(prevVal)) * 100
                  : null;

              return (
                <tr
                  key={String(spec.key)}
                  onClick={() => setActiveKey(spec.key)}
                  className={`transition cursor-pointer ${
                    selected
                      ? "bg-blue-950/25 text-white"
                      : "hover:bg-slate-800/35 text-slate-300"
                  }`}
                >
                  <td
                    className={`py-1.5 pl-3 pr-2 whitespace-nowrap ${
                      spec.highlight ? "font-semibold text-slate-100" : ""
                    }`}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          selected ? "bg-cyan-400" : "bg-transparent"
                        }`}
                      />
                      {spec.label}
                    </span>
                  </td>

                  {sorted.map((r, idx) => {
                    const v = r[spec.key];
                    const neg = typeof v === "number" && v < 0;
                    return (
                      <td
                        key={idx}
                        className={`py-1.5 px-2 text-right tabular-nums whitespace-nowrap ${
                          neg
                            ? "text-rose-300"
                            : spec.highlight
                            ? "text-slate-100 font-semibold"
                            : "text-slate-300"
                        }`}
                      >
                        {formatCell(v, spec.format)}
                      </td>
                    );
                  })}

                  <td className="py-1.5 px-2 text-right tabular-nums whitespace-nowrap text-[10px]">
                    {chg === null ? (
                      <span className="text-slate-600">—</span>
                    ) : (
                      <span
                        className={
                          chg >= 0 ? "text-emerald-400" : "text-rose-400"
                        }
                      >
                        {chg >= 0 ? "+" : ""}
                        {spec.format === "pct"
                          ? `${chg.toFixed(1)}pp`
                          : `${chg.toFixed(1)}%`}
                      </span>
                    )}
                  </td>

                  {onAuditMetric && (
                    <td
                      className="py-1.5 pl-1 pr-2.5 text-right"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        title={`Dispatch AI agents to audit ${ticker} ${spec.label}`}
                        onClick={() => {
                          const firstP = periodLabel(sorted[0]);
                          const lastP = periodLabel(sorted[sorted.length - 1]);
                          const lastFmt = formatCell(lastVal, spec.format);
                          onAuditMetric(
                            `Audit ${ticker}'s ${spec.label} from ${firstP} to ${lastP} (latest ${lastFmt}) using SEC 10-K/10-Q MD&A and 8-K filings to explain what drove this change.`
                          );
                        }}
                        className="inline-flex items-center gap-0.5 rounded border border-slate-800 hover:border-emerald-500/50 bg-[#0b111e] hover:bg-emerald-500/15 px-1.5 py-0.5 text-[9.5px] text-slate-400 hover:text-emerald-300 transition cursor-pointer"
                      >
                        <Sparkles className="h-2.5 w-2.5" />
                        <span>Ask</span>
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
