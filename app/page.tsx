"use client";

import { useEffect, useState } from "react";
import { ShieldCheck, Send, Zap } from "lucide-react";
import type { QueryResult, QuotaStatus, ShowcaseSummary } from "@/lib/types";
import { citationBadgeLabel } from "@/lib/format";

export default function HomePage() {
  const [ticker, setTicker] = useState("AAPL");
  const [question, setQuestion] = useState("");
  const [quota, setQuota] = useState<QuotaStatus>({
    limit: 5,
    used: 0,
    remaining: 5,
    reset_at: "",
  });
  const [showcases, setShowcases] = useState<ShowcaseSummary[]>([]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    Promise.all([fetch("/api/quota"), fetch("/api/showcase")])
      .then(async ([qRes, sRes]) => {
        if (qRes.ok) setQuota(await qRes.json());
        if (sRes.ok) {
          const data = await sRes.json();
          setShowcases(data.reports || []);
        }
      })
      .catch(() => {});
  }, []);

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    try {
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          ticker,
          mode: "multi_agent",
        }),
      });
      const body = await resp.json();
      if (body.quota) setQuota(body.quota);
      setResult(body);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-100 p-6 max-w-6xl mx-auto space-y-6">
      <header className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-emerald-400" />
          <h1 className="text-base font-semibold">CompanyScope Research Terminal</h1>
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/30 bg-blue-950/30 px-3 py-1 text-xs font-mono">
          <Zap className="h-3.5 w-3.5 text-amber-400" />
          <span>{quota.remaining}/{quota.limit} Daily Queries</span>
        </div>
      </header>

      {showcases.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {showcases.map((sc) => (
            <button
              key={sc.slug}
              type="button"
              onClick={async () => {
                const r = await fetch(`/api/reports/${sc.slug}`);
                if (r.ok) {
                  const saved = await r.json();
                  setResult(saved.result);
                }
              }}
              className="rounded-lg border border-slate-800 bg-[#0d1422] px-3 py-1.5 text-xs text-slate-300 hover:border-emerald-500/40"
            >
              {sc.title}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleAsk} className="flex gap-2">
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          className="w-24 rounded-lg border border-slate-800 bg-[#0d1422] px-3 py-2 font-mono text-xs uppercase"
        />
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask any SEC filing, XBRL, or market sentiment question..."
          className="flex-1 rounded-lg border border-slate-800 bg-[#0d1422] px-3.5 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950"
        >
          <Send className="h-3.5 w-3.5" />
          <span>{loading ? "Running..." : "Analyze"}</span>
        </button>
      </form>

      {result && (
        <section className="rounded-xl border border-slate-800 bg-[#0d1422] p-5 space-y-4">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
            {result.answer}
          </p>
          <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-800">
            {(result.citations || []).map((c, idx) => (
              <span
                key={idx}
                className="rounded border border-emerald-500/30 bg-emerald-950/20 px-2.5 py-1 font-mono text-xs text-emerald-300"
              >
                [{idx + 1}] {citationBadgeLabel(c)}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
