"use client";

import { useEffect, useRef, useState } from "react";
import type { IChartApi, Time } from "lightweight-charts";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CandlestickChart,
  Loader2,
  Tv,
} from "lucide-react";
import type {
  FinancialRow,
  LiveChartResponse,
  LiveQuote,
  OhlcvCandle,
} from "@/lib/types";
import { formatCompactUSD } from "@/lib/format";
import { FinancialChart } from "./FinancialChart";

const TIMEFRAMES = ["1D", "5D", "1M", "6M", "1Y", "5Y"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

interface Props {
  ticker: string;
  xbrlRows: FinancialRow[];
  quarterlyRows?: FinancialRow[];
  xbrlLoading?: boolean;
  onQuoteLoaded?: (quote: LiveQuote) => void;
  onAuditMetric?: (prompt: string) => void;
}

export function TradingViewChart({
  ticker,
  xbrlRows,
  quarterlyRows = [],
  xbrlLoading = false,
  onQuoteLoaded,
  onAuditMetric,
}: Props) {
  const [viewMode, setViewMode] = useState<
    "candles" | "tradingview_pro" | "xbrl"
  >("candles");
  const [timeframe, setTimeframe] = useState<Timeframe>("6M");
  const [chartData, setChartData] = useState<LiveChartResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [hoveredBar, setHoveredBar] = useState<OhlcvCandle | null>(null);

  const candleContainerRef = useRef<HTMLDivElement | null>(null);
  const cleanTicker = ticker.trim().toUpperCase() || "NVDA";

  useEffect(() => {
    if (cleanTicker.length > 6) return;
    let cancelled = false;
    setLoading(true);
    fetch(
      `/api/market/chart/${encodeURIComponent(
        cleanTicker
      )}?timeframe=${timeframe}`
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((data: LiveChartResponse | null) => {
        if (!cancelled && data && !data.error) {
          setChartData(data);
          setHoveredBar(null);
          if (data.quote && onQuoteLoaded) {
            onQuoteLoaded(data.quote);
          }
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cleanTicker, timeframe, onQuoteLoaded]);

  useEffect(() => {
    if (viewMode !== "candles") return;
    const container = candleContainerRef.current;
    const candles = chartData?.candles || [];
    if (!container || candles.length === 0) return;

    let disposed = false;
    let chart: IChartApi | null = null;
    let ro: ResizeObserver | null = null;

    import("lightweight-charts").then(
      ({ ColorType, CrosshairMode, createChart }) => {
        if (disposed || !candleContainerRef.current) return;
        container.innerHTML = "";

        chart = createChart(container, {
          width: container.clientWidth || 640,
          height: 275,
          layout: {
            background: { type: ColorType.Solid, color: "#080c16" },
            textColor: "#94a3b8",
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Monaco, monospace",
            fontSize: 10.5,
          },
          grid: {
            vertLines: { color: "rgba(30, 41, 59, 0.35)" },
            horzLines: { color: "rgba(30, 41, 59, 0.35)" },
          },
          crosshair: {
            mode: CrosshairMode.Normal,
          },
          rightPriceScale: {
            borderColor: "rgba(51, 65, 85, 0.5)",
          },
          timeScale: {
            borderColor: "rgba(51, 65, 85, 0.5)",
            timeVisible: Boolean(chartData?.is_intraday),
            secondsVisible: false,
          },
        });

        const candleSeries = chart.addCandlestickSeries({
          upColor: "#10b981",
          downColor: "#f43f5e",
          borderUpColor: "#10b981",
          borderDownColor: "#f43f5e",
          wickUpColor: "#10b981",
          wickDownColor: "#f43f5e",
        });

        const volumeSeries = chart.addHistogramSeries({
          priceFormat: { type: "volume" },
          priceScaleId: "",
        });
        volumeSeries.priceScale().applyOptions({
          scaleMargins: { top: 0.8, bottom: 0 },
        });

        candleSeries.setData(
          candles.map((c) => ({
            time: c.time as Time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          }))
        );

        volumeSeries.setData(
          candles.map((c) => ({
            time: c.time as Time,
            value: c.volume,
            color:
              c.close >= c.open
                ? "rgba(16, 185, 129, 0.24)"
                : "rgba(244, 63, 94, 0.24)",
          }))
        );

        chart.timeScale().fitContent();

        const byTime = new Map<string, OhlcvCandle>();
        for (const c of candles) {
          byTime.set(String(c.time), c);
        }

        chart.subscribeCrosshairMove((param) => {
          if (disposed) return;
          if (!param.time) {
            setHoveredBar(null);
            return;
          }
          const match = byTime.get(String(param.time));
          if (match) setHoveredBar(match);
        });

        ro = new ResizeObserver((entries) => {
          if (disposed || !chart) return;
          for (const entry of entries) {
            const w = Math.floor(entry.contentRect.width);
            if (w > 0) {
              chart.applyOptions({ width: w });
            }
          }
        });
        ro.observe(container);
      }
    );

    return () => {
      disposed = true;
      ro?.disconnect();
      chart?.remove();
    };
  }, [viewMode, chartData]);

  const tvSymbol = chartData?.tradingview_symbol || `NASDAQ:${cleanTicker}`;
  const tvIframeUrl = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(
    tvSymbol
  )}&interval=D&theme=dark&style=1&timezone=Etc%2FUTC&studies=%5B%22RSI%40tv-basicstudies%22%5D&hide_side_toolbar=0&allow_symbol_change=1&saveimage=0&locale=en`;

  const quote = chartData?.quote;
  const isUp = (quote?.change_pct ?? 0) >= 0;
  const activeBar =
    hoveredBar ||
    (chartData?.candles?.length
      ? chartData.candles[chartData.candles.length - 1]
      : null);

  return (
    <div className="rounded-xl border border-slate-800/90 bg-[#0b111d] overflow-hidden">
      {/* Compact Header: Quote + Inline Timeframes + View Switcher */}
      <div className="px-3.5 py-2.5 border-b border-slate-800/80 bg-[#090e19] flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex flex-wrap items-baseline gap-2.5">
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono text-sm font-bold text-white">
              {cleanTicker}
            </span>
            {quote?.company_name && quote.company_name !== cleanTicker && (
              <span className="text-xs text-slate-400 truncate max-w-[175px]">
                {quote.company_name}
              </span>
            )}
            {quote?.sector && (
              <span className="hidden sm:inline-block rounded border border-slate-800 bg-[#070b14] px-1.5 py-0.5 text-[10px] font-mono text-slate-500">
                {quote.sector}
              </span>
            )}
          </div>

          {typeof quote?.price === "number" && (
            <div className="flex items-baseline gap-1.5 font-mono">
              <span className="text-sm font-bold text-slate-100 tabular-nums">
                ${quote.price.toFixed(2)}
              </span>
              {typeof quote.change_pct === "number" && (
                <span
                  className={`inline-flex items-center text-xs font-semibold tabular-nums ${
                    isUp ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {isUp ? (
                    <ArrowUpRight className="h-3 w-3" />
                  ) : (
                    <ArrowDownRight className="h-3 w-3" />
                  )}
                  {isUp ? "+" : ""}
                  {quote.change_pct.toFixed(2)}%
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {viewMode === "candles" && (
            <div className="inline-flex items-center rounded-md border border-slate-800/90 bg-[#070b14] p-0.5">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                  className={`px-1.5 py-0.5 rounded font-mono text-[10.5px] transition cursor-pointer ${
                    timeframe === tf
                      ? "bg-emerald-500/20 text-emerald-300"
                      : "text-slate-500 hover:text-slate-200"
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          )}

          <div className="inline-flex rounded-md border border-slate-800 bg-[#070b14] p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("candles")}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition cursor-pointer ${
                viewMode === "candles"
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <CandlestickChart className="h-3 w-3 text-emerald-400" />
              <span>Chart</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("tradingview_pro")}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition cursor-pointer ${
                viewMode === "tradingview_pro"
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Tv className="h-3 w-3 text-blue-400" />
              <span>Studio</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("xbrl")}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition cursor-pointer ${
                viewMode === "xbrl"
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <BarChart3 className="h-3 w-3 text-violet-400" />
              <span>Financials</span>
            </button>
          </div>
        </div>
      </div>

      {/* Valuation Strip */}
      {quote && (
        <div className="px-3.5 py-1.5 border-b border-slate-800/70 bg-[#080d17] grid grid-cols-3 sm:grid-cols-6 gap-2 text-[10.5px] font-mono">
          <div>
            <span className="text-slate-500 mr-1.5">Cap</span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {formatCompactUSD(quote.market_cap)}
            </span>
          </div>
          <div>
            <span className="text-slate-500 mr-1.5">P/E</span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {quote.trailing_pe ? `${quote.trailing_pe.toFixed(1)}x` : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 mr-1.5">Fwd</span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {quote.forward_pe ? `${quote.forward_pe.toFixed(1)}x` : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 mr-1.5">EV/EBITDA</span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {quote.ev_to_ebitda ? `${quote.ev_to_ebitda.toFixed(1)}x` : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 mr-1.5">52W</span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {quote.fifty_two_week_low && quote.fifty_two_week_high
                ? `${quote.fifty_two_week_low.toFixed(0)}–${quote.fifty_two_week_high.toFixed(0)}`
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 mr-1.5">Target</span>
            <span className="text-cyan-300 font-semibold tabular-nums">
              {quote.analyst_target_mean
                ? `$${quote.analyst_target_mean.toFixed(0)}`
                : "—"}
            </span>
          </div>
        </div>
      )}

      {/* Active Chart Canvas */}
      {viewMode === "candles" && (
        <div className="relative bg-[#080c16]">
          {/* Floating TradingView-style OHLCV HUD */}
          {activeBar && (
            <div className="absolute top-2 left-3 z-10 pointer-events-none flex flex-wrap items-center gap-2 rounded bg-[#080c16]/85 px-2 py-0.5 font-mono text-[10px] text-slate-400 tabular-nums">
              <span>
                O <strong className="text-slate-200">{activeBar.open}</strong>
              </span>
              <span>
                H <strong className="text-slate-200">{activeBar.high}</strong>
              </span>
              <span>
                L <strong className="text-slate-200">{activeBar.low}</strong>
              </span>
              <span>
                C <strong className="text-slate-200">{activeBar.close}</strong>
              </span>
              {activeBar.volume > 0 && (
                <span>
                  V{" "}
                  <strong className="text-slate-200">
                    {(activeBar.volume / 1e6).toFixed(1)}M
                  </strong>
                </span>
              )}
              {typeof chartData?.period_change_pct === "number" && (
                <span
                  className={
                    chartData.period_change_pct >= 0
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }
                >
                  {timeframe}: {chartData.period_change_pct >= 0 ? "+" : ""}
                  {chartData.period_change_pct.toFixed(2)}%
                </span>
              )}
            </div>
          )}

          {loading && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-[#080c16]/75">
              <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
            </div>
          )}
          <div ref={candleContainerRef} className="w-full h-[275px]" />
        </div>
      )}

      {viewMode === "tradingview_pro" && (
        <div className="bg-[#080c16]">
          <iframe
            key={tvSymbol}
            title={`TradingView ${tvSymbol}`}
            src={tvIframeUrl}
            className="w-full h-[320px] border-0 bg-[#080c16]"
            allowFullScreen
          />
        </div>
      )}

      {viewMode === "xbrl" && (
        <FinancialChart
          ticker={cleanTicker}
          rows={xbrlRows}
          quarterlyRows={quarterlyRows}
          loading={xbrlLoading}
          onAuditMetric={onAuditMetric}
        />
      )}
    </div>
  );
}
