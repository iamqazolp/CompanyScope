import type { Citation } from "./types";

export function formatCompactUSD(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e12) {
    return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  }
  if (abs >= 1e9) {
    return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  }
  if (abs >= 1e6) {
    return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  }
  if (abs >= 1e3) {
    return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  }
  return `${sign}$${abs.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

export function formatExactUSD(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatMarketMetric(
  value: number | null | undefined,
  unit?: string
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (unit === "x") {
    return `${value.toFixed(2)}x`;
  }
  if (unit === "%") {
    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  }
  if (Math.abs(value) >= 1e6) {
    return formatCompactUSD(value);
  }
  return `$${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function citationBadgeLabel(c: Citation): string {
  const tkr = c.ticker ? `${c.ticker} ` : "";
  const yr = c.year ? `${c.year}` : "";
  if (c.type === "market") {
    const valPart =
      typeof c.verified_value === "number"
        ? ` · ${formatMarketMetric(c.verified_value, c.unit)}`
        : "";
    return `${tkr}LIVE · ${c.concept || "Quote"}${valPart}`.trim();
  }
  if (c.type === "numeric") {
    const valPart =
      typeof c.verified_value === "number"
        ? ` · ${formatCompactUSD(c.verified_value)}`
        : "";
    return `${tkr}XBRL ${yr} · ${c.concept || "Metric"}${valPart}`.trim();
  }
  if (c.type === "insider") {
    return `${tkr}${c.section || "SEC Form 4"}`.trim();
  }
  if (c.type === "earnings") {
    return `${tkr}8-K ${yr} · ${c.section || "Earnings"}`.trim();
  }
  if (c.type === "sentiment") {
    return `${tkr}${c.section || "Market News"}`.trim();
  }
  return `${tkr}10-K ${yr} · ${c.section || "Filing"}`.trim();
}

export function formatResetCountdown(resetIso: string | undefined): string {
  if (!resetIso) return "Resets at 00:00 UTC";
  const target = new Date(resetIso).getTime();
  const diffMs = target - Date.now();
  if (Number.isNaN(target) || diffMs <= 0) return "Resets at 00:00 UTC";
  const hrs = Math.floor(diffMs / 3600000);
  const mins = Math.floor((diffMs % 3600000) / 60000);
  return `Resets in ${hrs}h ${mins}m (00:00 UTC)`;
}
