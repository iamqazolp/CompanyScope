"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { ResearchTerminal } from "@/components/ResearchTerminal";
import type { SavedReport } from "@/lib/types";

export default function SharedReportPage() {
  const params = useParams<{ slug: string }>();
  const slug = params?.slug;
  const [report, setReport] = useState<SavedReport | null>(null);
  const [notFound, setNotFound] = useState<boolean>(false);

  useEffect(() => {
    if (!slug) return;
    fetch(`/api/reports/${encodeURIComponent(slug)}`)
      .then((r) => {
        if (!r.ok) {
          setNotFound(true);
          return null;
        }
        return r.json();
      })
      .then((data) => {
        if (data) setReport(data);
      })
      .catch(() => setNotFound(true));
  }, [slug]);

  if (notFound) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#080c14] text-center px-4">
        <h1 className="text-lg font-semibold text-slate-100">
          Research Report Not Found
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          This permalink may have expired or does not exist.
        </p>
        <a
          href="/"
          className="mt-4 rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-emerald-400 transition"
        >
          Open CompanyScope Terminal
        </a>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#080c14] text-slate-400 gap-2 text-xs font-mono">
        <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
        <span>Loading verified report...</span>
      </div>
    );
  }

  return <ResearchTerminal initialReport={report} />;
}
