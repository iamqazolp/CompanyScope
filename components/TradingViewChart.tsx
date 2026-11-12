"use client";

import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CandlestickChart,
  Loader2,
  Tv,
} from "lucide-react";
import type { FinancialRow, LiveChartResponse, OhlcvCandle } from "@/lib/types";
import { formatCompactUSD } from "@/lib/format";
import { FinancialChart } from "./FinancialChart";

const TIMEFRAMES = ["1D", "5D", "1M", "6M", "1Y", "5Y"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

interface Props {
  ticker: string;
  xbrlRows: FinancialRow[];
  xbrlLoading?: boolean;
}

export function TradingViewChart({
  ticker,
  xbrlRows,
  xbrlLoading = false,
}: Props) {
  const [viewMode, setViewMode] = useState<
    "candles" | "tradingview_pro" | "xbrl"
  >("candles");
  const [timeframe, setTimeframe] = useState<Timeframe>("6M");
  const [chartData, setChartData] = useState<LiveChartResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [hoveredBar, setHoveredBar] = useState<OhlcvCandle | null>(null);

  const candleContainerRef = useRef<HTMLDivElement | null>(null);
  const tvWidgetContainerRef = useRef<HTMLDivElement | null>(null);

  const cleanTicker = ticker.trim().toUpperCase() || "AAPL";

  // Fetch OHLCV candles + live quote & valuation snapshot
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
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cleanTicker, timeframe]);

  // Render TradingView lightweight-charts candlestick + volume series
  useEffect(() => {
    if (viewMode !== "candles") return;
    const container = candleContainerRef.current;
    const candles = chartData?.candles || [];
    if (!container || candles.length === 0) return;

    const chart: IChartApi = createChart(container, {
      width: container.clientWidth,
      height: 310,
      layout: {
        background: { type: ColorType.Solid, color: "#090e19" },
        textColor: "#94a3b8",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(30, 41, 59, 0.45)" },
        horzLines: { color: "rgba(30, 41, 59, 0.45)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: "rgba(51, 65, 85, 0.6)",
      },
      timeScale: {
        borderColor: "rgba(51, 65, 85, 0.6)",
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
      scaleMargins: { top: 0.78, bottom: 0 },
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
            ? "rgba(16, 185, 129, 0.28)"
            : "rgba(244, 63, 94, 0.28)",
      }))
    );

    chart.timeScale().fitContent();

    const byTime = new Map<string, OhlcvCandle>();
    for (const c of candles) {
      byTime.set(String(c.time), c);
    }

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        setHoveredBar(null);
        return;
      }
      const match = byTime.get(String(param.time));
      if (match) setHoveredBar(match);
    });

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.floor(entry.contentRect.width);
        if (w > 0) {
          chart.applyOptions({ width: w });
        }
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [viewMode, chartData]);

  // Mount Official TradingView Advanced Technical Chart widget when in "tradingview_pro" mode
  const tvSymbol =
    chartData?.tradingview_symbol || `NASDAQ:${cleanTicker}`;

  useEffect(() => {
    if (viewMode !== "tradingview_pro") return;
    const holder = tvWidgetContainerRef.current;
    if (!holder) return;
    holder.innerHTML = "";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    widgetDiv.style.height = "360px";
    widgetDiv.style.width = "100%";
    holder.appendChild(widgetDiv);

    const script = document.createElement("script");
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval: "D",
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "en",
      backgroundColor: "rgba(9, 14, 25, 1)",
      gridColor: "rgba(30, 41, 59, 0.45)",
      hide_side_toolbar: false,
      allow_symbol_change: true,
      save_image: false,
      studies: ["STD;RSI"],
      support_host: "https://www.tradingview.com",
    });
    holder.appendChild(script);

    return () => {
      holder.innerHTML = "";
    };
  }, [viewMode, tvSymbol]);

  const quote = chartData?.quote;
  const isUp = (quote?.change_pct ?? 0) >= 0;
  const activeBar =
    hoveredBar ||
    (chartData?.candles?.length
      ? chartData.candles[chartData.candles.length - 1]
      : null);

  return (
    <div className="rounded-xl border border-slate-800/90 bg-[#0d1422] overflow-hidden shadow-xl shadow-black/20">
      {/* Live Valuation & Spot Quote Strip */}
      <div className="px-4 py-3 border-b border-slate-800/80 bg-[#0a101d] flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-2.5">
          <div className="flex items-center gap-1.5">
            <Activity className="h-4 w-4 text-emerald-400 self-center" />
            <span className="font-mono text-sm font-bold text-white">
              {cleanTicker}
            </span>
            {quote?.company_name && quote.company_name !== cleanTicker && (
              <span className="text-xs text-slate-400 truncate max-w-[180px]">
                {quote.company_name}
              </span>
            )}
          </div>

          {typeof quote?.price === "number" && (
            <div className="flex items-baseline gap-1.5 font-mono">
              <span className="text-base font-bold text-slate-100 tabular-nums">
                ${quote.price.toFixed(2)}
              </span>
              {typeof quote.change_pct === "number" && (
                <span
                  className={`inline-flex items-center text-xs font-semibold tabular-nums ${
                    isUp ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {isUp ? (
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  ) : (
                    <ArrowDownRight className="h-3.5 w-3.5" />
                  )}
                  {isUp ? "+" : ""}
                  {quote.change_pct.toFixed(2)}%
                </span>
              )}
            </div>
          )}
        </div>

        {/* 3-Way Chart Engine Switcher */}
        <div className="inline-flex rounded-lg border border-slate-800 bg-[#080d18] p-0.5">
          <button
            type="button"
            onClick={() => setViewMode("candles")}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition cursor-pointer ${
              viewMode === "candles"
                ? "bg-emerald-500/20 text-emerald-200 border border-emerald-500/40"
                : "text-slate-400 hover:text-slate-200 border border-transparent"
            }`}
          >
            <CandlestickChart className="h-3.5 w-3.5" />
            <span>Live OHLCV</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode("tradingview_pro")}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition cursor-pointer ${
              viewMode === "tradingview_pro"
                ? "bg-blue-500/20 text-blue-200 border border-blue-500/40"
                : "text-slate-400 hover:text-slate-200 border border-transparent"
            }`}
          >
            <Tv className="h-3.5 w-3.5" />
            <span>TradingView Studio</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode("xbrl")}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition cursor-pointer ${
              viewMode === "xbrl"
                ? "bg-violet-500/20 text-violet-200 border border-violet-500/40"
                : "text-slate-400 hover:text-slate-200 border border-transparent"
            }`}
          >
            <BarChart3 className="h-3.5 w-3.5" />
            <span>SEC XBRL</span>
          </button>
        </div>
      </div>

      {/* Key Live Multiples Strip */}
      {quote && (
        <div className="px-4 py-2 border-b border-slate-800/70 bg-[#090e1a] grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 text-[11px] font-mono">
          <div>
            <span className="text-slate-500 block text-[10px]">Mkt Cap</span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {formatCompactUSD(quote.market_cap)}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">
              Trailing P/E
            </span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {quote.trailing_pe ? `${quote.trailing_pe.toFixed(1)}x` : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">
              Forward P/E
            </span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {quote.forward_pe ? `${quote.forward_pe.toFixed(1)}x` : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">EV/EBITDA</span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {quote.ev_to_ebitda ? `${quote.ev_to_ebitda.toFixed(1)}x` : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">52W Range</span>
            <span className="text-slate-200 font-semibold tabular-nums">
              {quote.fifty_two_week_low && quote.fifty_two_week_high
                ? `$${quote.fifty_two_week_low.toFixed(0)}–$${quote.fifty_two_week_high.toFixed(0)}`
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">
              Street Target
            </span>
            <span className="text-cyan-300 font-semibold tabular-nums">
              {quote.analyst_target_mean
                ? `$${quote.analyst_target_mean.toFixed(0)}${
                    quote.recommendation
                      ? ` (${quote.recommendation.replace("_", " ")})`
                      : ""
                  }`
                : "—"}
            </span>
          </div>
        </div>
      )}

      {/* Body per Selected Chart Engine */}
      {viewMode === "candles" && (
        <div className="p-3.5 space-y-2.5 bg-[#090e19]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            {/* Timeframe Selector */}
            <div className="inline-flex items-center gap-1">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                  className={`px-2 py-0.5 rounded font-mono text-[11px] transition cursor-pointer ${
                    timeframe === tf
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "text-slate-500 hover:text-slate-200 border border-transparent"
                  }`}
                >
                  {tf}
                </button>
              ))}
              {typeof chartData?.period_change_pct === "number" && (
                <span
                  className={`ml-2 font-mono text-[11px] tabular-nums ${
                    chartData.period_change_pct >= 0
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }`}
                >
                  ({chartData.period_change_pct >= 0 ? "+" : ""}
                  {chartData.period_change_pct.toFixed(2)}% in {timeframe})
                </span>
              )}
            </div>

            {/* Crosshair OHLCV Legend */}
            {activeBar && (
              <div className="flex flex-wrap items-center gap-2.5 font-mono text-[10.5px] text-slate-400 tabular-nums">
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
                  C{" "}
                  <strong className="text-slate-200">{activeBar.close}</strong>
                </span>
                <span>
                  Vol{" "}
                  <strong className="text-slate-200">
                    {(activeBar.volume / 1e6).toFixed(1)}M
                  </strong>
                </span>
              </div>
            )}
          </div>

          <div className="relative min-h-[310px] w-full rounded-lg overflow-hidden border border-slate-800/60">
            {loading && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#090e19]/80 text-xs font-mono text-slate-400 gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                <span>Loading TradingView Lightweight Candles...</span>
              </div>
            )}
            <div ref={candleContainerRef} className="w-full h-[310px]" />
          </div>

          <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
            <span>
              Powered by TradingView Lightweight Charts™ · {tvSymbol}
            </span>
            <span>Scroll to zoom · Drag to pan</span>
          </div>
        </div>
      )}

      {viewMode === "tradingview_pro" && (
        <div className="p-2 bg-[#090e19]">
          <div
            ref={tvWidgetContainerRef}
            className="tradingview-widget-container w-full h-[360px] rounded-lg overflow-hidden"
          />
        </div>
      )}

      {viewMode === "xbrl" && (
        <div className="p-1 bg-[#0d1422]">
          <FinancialChart
            ticker={cleanTicker}
            rows={xbrlRows}
            loading={xbrlLoading}
          />
        </div>
      )}
    </div>
  );
}
