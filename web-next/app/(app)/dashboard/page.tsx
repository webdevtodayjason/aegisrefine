"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listJobs, type JobBrief } from "@/lib/api";

// --- formatting helpers ---
const money = (n: number) =>
  "$" + (Number(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });


// Customer-facing price only — never COGS/margin. quote_amount is the quoted cap;
// fall back to revenue_collected (what was actually billed) if no quote is recorded.
const jobPrice = (j: JobBrief): string => {
  const p = j.quote_amount ?? j.revenue_collected;
  return p == null ? "—" : money(p);
};

// status -> [label, color, borderRGBA, bgRGBA]; unknown statuses fall back gracefully
const STATUS: Record<string, [string, string, string, string]> = {
  pending: ["QUEUED", "#3A7BFF", "rgba(58,123,255,0.4)", "rgba(58,123,255,0.08)"],
  paid: ["PAID", "#3A7BFF", "rgba(58,123,255,0.4)", "rgba(58,123,255,0.08)"],
  queued: ["QUEUED", "#3A7BFF", "rgba(58,123,255,0.4)", "rgba(58,123,255,0.08)"],
  triage: ["TRIAGE", "#3A7BFF", "rgba(58,123,255,0.4)", "rgba(58,123,255,0.08)"],
  triaged: ["TRIAGED", "#3A7BFF", "rgba(58,123,255,0.4)", "rgba(58,123,255,0.08)"],
  processing: ["PROCESSING", "#00E5CC", "rgba(0,229,204,0.4)", "rgba(0,229,204,0.08)"],
  refining: ["REFINING", "#00E5CC", "rgba(0,229,204,0.4)", "rgba(0,229,204,0.08)"],
  awaiting_approval: ["AWAITING GATE", "#F59E0B", "rgba(245,158,11,0.4)", "rgba(245,158,11,0.08)"],
  awaiting_gate: ["AWAITING GATE", "#F59E0B", "rgba(245,158,11,0.4)", "rgba(245,158,11,0.08)"],
  gated: ["AWAITING GATE", "#F59E0B", "rgba(245,158,11,0.4)", "rgba(245,158,11,0.08)"],
  complete: ["COMPLETE", "#22C55E", "rgba(34,197,94,0.4)", "rgba(34,197,94,0.08)"],
  completed: ["COMPLETE", "#22C55E", "rgba(34,197,94,0.4)", "rgba(34,197,94,0.08)"],
  rejected: ["HALTED", "#ef4444", "rgba(239,68,68,0.4)", "rgba(239,68,68,0.08)"],
  halted: ["HALTED", "#ef4444", "rgba(239,68,68,0.4)", "rgba(239,68,68,0.08)"],
  failed: ["FAILED", "#ef4444", "rgba(239,68,68,0.4)", "rgba(239,68,68,0.08)"],
};
const theme = (s: string): [string, string, string, string] =>
  STATUS[String(s || "").toLowerCase()] ?? [
    String(s || "UNKNOWN").toUpperCase(),
    "#A1A1AA",
    "rgba(255,255,255,0.15)",
    "rgba(255,255,255,0.04)",
  ];

// newest first: created_at desc, fall back to id desc when timestamps are missing/equal
const byNewest = (a: JobBrief, b: JobBrief) => {
  const ta = a.created_at ? new Date(a.created_at).getTime() : NaN;
  const tb = b.created_at ? new Date(b.created_at).getTime() : NaN;
  if (!isNaN(ta) && !isNaN(tb) && ta !== tb) return tb - ta;
  return b.id - a.id;
};

function StatusBadge({ status }: { status: string }) {
  const [label, color, border, bg] = theme(status);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded font-mono text-[10.5px] tracking-[0.04em]"
      style={{ color, border: `1px solid ${border}`, background: bg, padding: "4px 9px" }}
    >
      <i className="h-[5px] w-[5px] rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

export default function DashboardPage() {
  const [jobs, setJobs] = useState<JobBrief[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paid, setPaid] = useState(false);

  useEffect(() => {
    setPaid(new URLSearchParams(window.location.search).get("paid") === "1");
    let alive = true;
    listJobs()
      .then((data) => {
        if (alive) setJobs([...(data ?? [])].sort(byNewest));
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  const newest = jobs && jobs.length ? jobs[0] : null;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-5 py-10 sm:px-12">
      {/* page header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow mb-2.5">// WELCOME BACK</div>
          <h1 className="mb-1.5 text-[28px] font-medium tracking-[-0.015em]">Your refinery</h1>
          <p className="m-0 max-w-[560px] text-sm text-muted">
            Aegis-14B triages every job on DGX Spark · external spend pauses at one human gate · each finish ships a
            signed AAR.
          </p>
        </div>
        <Link href="/new-order" className="btn-teal px-5 py-3 text-[15px]">
          ＋ New order
        </Link>
      </div>

      {/* payment confirmation (?paid=1) */}
      {paid && (
        <Link
          href={newest ? `/orders/${newest.id}` : "/dashboard"}
          className="flex items-center gap-4 rounded-xl px-5 py-4 transition-colors"
          style={{
            border: "1px solid rgba(34,197,94,0.35)",
            background: "linear-gradient(90deg,rgba(34,197,94,0.08),rgba(34,197,94,0.02))",
          }}
        >
          <span
            className="flex h-10 w-10 flex-none items-center justify-center rounded-[9px] text-lg text-green"
            style={{ background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.4)" }}
          >
            ✓
          </span>
          <div className="flex-1">
            <div className="text-[15px] font-semibold">Payment received — your job is queued</div>
            <div className="text-[13px] text-muted">
              {newest ? (
                <>
                  Job <span className="font-mono text-green">#{newest.id}</span> is in the refinery — open it to track
                  progress.
                </>
              ) : (
                "Your job is in the refinery — it will appear here shortly."
              )}
            </div>
          </div>
          <span className="font-mono text-xs text-green">View job →</span>
        </Link>
      )}

      {/* jobs panel */}
      <div className="overflow-hidden rounded-2xl border border-line bg-panel">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="m-0 text-base font-semibold">Jobs &amp; orders</h2>
          {jobs && jobs.length > 0 && (
            <span className="font-mono text-[11px] text-muted-2">{jobs.length} total</span>
          )}
        </div>

        {/* column headers */}
        <div className="hidden grid-cols-[1.7fr_0.9fr_0.9fr_0.8fr_70px] gap-3 border-b border-line px-5 py-3 font-mono text-[10px] tracking-[0.12em] text-muted-2 sm:grid">
          <div>JOB</div>
          <div>SERVICE</div>
          <div>STATUS</div>
          <div>PRICE</div>
          <div />
        </div>

        {/* loading */}
        {jobs === null && error === null && (
          <div className="px-5 py-6 font-mono text-xs text-muted">Loading jobs…</div>
        )}

        {/* error */}
        {error !== null && (
          <div className="px-5 py-6 font-mono text-xs text-red">✗ Could not load jobs: {error}</div>
        )}

        {/* empty */}
        {jobs !== null && error === null && jobs.length === 0 && (
          <div className="px-5 py-[30px] text-center">
            <div className="mb-3.5 text-sm text-muted">Place your first order — start your first refinement.</div>
            <Link href="/new-order" className="btn-ghost px-5 py-3 text-sm">
              ＋ New order
            </Link>
          </div>
        )}

        {/* rows */}
        {jobs !== null &&
          error === null &&
          jobs.map((j) => {
            const isSynth = String(j.service || "").toLowerCase() === "synthesis";
            const name = isSynth ? j.synth_topic || "Synthetic dataset" : j.input || "Refinement job";
            return (
              <Link
                key={j.id}
                href={`/orders/${j.id}`}
                className="grid grid-cols-[1fr_70px] items-center gap-3 border-b border-white/[0.05] px-5 py-4 transition-colors last:border-b-0 hover:bg-white/[0.02] sm:grid-cols-[1.7fr_0.9fr_0.9fr_0.8fr_70px]"
              >
                <div className="min-w-0">
                  <div className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-medium">{name}</div>
                  <div className="font-mono text-[10.5px] text-muted-2">
                    JOB-{j.id}
                    {/* service shown inline on mobile where the dedicated column is hidden */}
                    <span className="sm:hidden"> · {j.service}</span>
                  </div>
                </div>
                <div className="hidden font-mono text-[12.5px] text-muted sm:block">{j.service}</div>
                <div className="hidden sm:block">
                  <StatusBadge status={j.status} />
                </div>
                <div className="hidden font-mono text-[12.5px] text-muted sm:block">{jobPrice(j)}</div>
                <div className="text-right font-mono text-[11.5px] text-teal">View →</div>
              </Link>
            );
          })}
      </div>
    </div>
  );
}
