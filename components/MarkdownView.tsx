"use client";

import React from "react";

function formatInline(text: string): React.ReactNode[] {
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g);
  return tokens.map((tok, i) => {
    if (tok.startsWith("**") && tok.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-slate-100">
          {tok.slice(2, -2)}
        </strong>
      );
    }
    if (tok.startsWith("`") && tok.endsWith("`")) {
      return (
        <code
          key={i}
          className="rounded bg-slate-800/90 border border-slate-700/60 px-1.5 py-0.5 font-mono text-[11.5px] text-emerald-300"
        >
          {tok.slice(1, -1)}
        </code>
      );
    }
    if (tok.startsWith("*") && tok.endsWith("*") && tok.length > 2) {
      return (
        <em key={i} className="italic text-slate-300">
          {tok.slice(1, -1)}
        </em>
      );
    }
    return <React.Fragment key={i}>{tok}</React.Fragment>;
  });
}

export function MarkdownView({ content }: { content: string }) {
  const lines = (content || "").split("\n");
  const blocks: React.ReactNode[] = [];

  lines.forEach((rawLine, idx) => {
    const trimmed = rawLine.trim();
    if (!trimmed) {
      blocks.push(<div key={`sp-${idx}`} className="h-2" />);
      return;
    }

    if (trimmed.startsWith("### ")) {
      blocks.push(
        <h4
          key={idx}
          className="text-sm font-semibold text-slate-100 pt-2 pb-0.5"
        >
          {formatInline(trimmed.slice(4))}
        </h4>
      );
      return;
    }

    if (trimmed.startsWith("## ") || trimmed.startsWith("# ")) {
      const clean = trimmed.replace(/^#+\s*/, "");
      blocks.push(
        <h3
          key={idx}
          className="text-base font-semibold text-white pt-2.5 pb-1 border-b border-slate-800/70"
        >
          {formatInline(clean)}
        </h3>
      );
      return;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const indent = rawLine.search(/\S|$/);
      blocks.push(
        <div
          key={idx}
          style={{ marginLeft: indent >= 2 ? "1rem" : "0rem" }}
          className="flex items-start gap-2 text-[13.5px] leading-relaxed text-slate-200 py-0.5"
        >
          <span className="mt-2 h-1.5 w-1.5 rounded-full bg-emerald-400/80 shrink-0" />
          <div>{formatInline(trimmed.replace(/^[-*]\s+/, ""))}</div>
        </div>
      );
      return;
    }

    const numMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (numMatch) {
      blocks.push(
        <div
          key={idx}
          className="flex items-start gap-2 text-[13.5px] leading-relaxed text-slate-200 py-0.5"
        >
          <span className="font-mono text-xs font-semibold text-blue-400 mt-0.5 shrink-0">
            {numMatch[1]}.
          </span>
          <div>{formatInline(numMatch[2])}</div>
        </div>
      );
      return;
    }

    blocks.push(
      <p key={idx} className="text-[13.5px] leading-relaxed text-slate-200">
        {formatInline(trimmed)}
      </p>
    );
  });

  return <div className="space-y-1">{blocks}</div>;
}
