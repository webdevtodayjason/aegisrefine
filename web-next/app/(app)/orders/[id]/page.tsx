"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ApiError,
  getJob,
  getCert,
  verifyJob,
  downloadUrl,
  packageUrl,
  type Cert,
} from "@/lib/api";

// ---- types ------------------------------------------------------------------
type Job = Awaited<ReturnType<typeof getJob>>;
type VerifyResult = Awaited<ReturnType<typeof verifyJob>>;

// synthesis provenance lives untyped under guarantees.synthesis — model the
// customer-safe subset (cost fields by_model_usd / spent_usd stay OUT of view).
interface SynthProvenance {
  method?: string;
  mode?: string;
  candidates_generated?: number;
  kept_synthetic?: number;
  yield_pct?: number;
  models?: Record<string, string>;
  real_rows?: number;
  synthetic_rows?: number;
  labeled_synthetic?: boolean;
}

// ---- formatting helpers -----------------------------------------------------
const money = (n: number | null | undefined) => "$" + (Number(n) || 0).toFixed(2);
const num = (n: number | null | undefined) => (Number(n) || 0).toLocaleString("en-US");
// show sub-cent honestly (up to 6dp), else 2dp
const usd = (n: number | null | undefined) => {
  const v = Number(n) || 0;
  return v > 0 && v < 0.01 ? "$" + v.toFixed(6).replace(/0+$/, "").replace(/\.$/, "") : "$" + v.toFixed(2);
};
const shortSig = (s: string | undefined) => {
  const v = String(s || "");
  return v.length > 22 ? v.slice(0, 12) + "…" + v.slice(-6) : v || "—";
};
const longDate = (iso: string | null) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
};
const shortDate = (iso: string | null) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return "—";
  }
};

// ---- tiny presentational primitives ----------------------------------------
type Tone = "teal" | "green" | "amber" | "red" | "muted";

const PILL_TONE: Record<Tone, string> = {
  teal: "border-teal-line bg-teal-dim text-teal",
  green: "border-green/40 bg-green/10 text-green",
  amber: "border-amber/40 bg-amber/[0.09] text-amber",
  red: "border-red/40 bg-red/10 text-red",
  muted: "border-line-2 bg-white/[0.03] text-muted-2",
};

function Pill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 font-mono text-[10.5px] tracking-[0.08em] ${PILL_TONE[tone]}`}>
      {children}
    </span>
  );
}

function Label({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`font-mono text-[11px] uppercase tracking-[0.14em] text-muted-2 ${className}`}>{children}</div>;
}

function KVList({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-col gap-px overflow-hidden rounded-lg border border-line bg-line">{children}</div>;
}

function KV({ k, value, vClass = "" }: { k: string; value: React.ReactNode; vClass?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 bg-panel px-3.5 py-2.5 text-[13px]">
      <span className="text-muted">{k}</span>
      <span className={`max-w-[62%] break-words text-right font-mono ${vClass}`}>{value}</span>
    </div>
  );
}

function Spinner({ className = "" }: { className?: string }) {
  return <span className={`inline-block animate-spin rounded-full border-2 border-teal/20 border-t-teal ${className}`} />;
}

// ---- stepper ----------------------------------------------------------------
type StepState = "done" | "active" | "pending";

const STEP_SKIN: Record<StepState, { bar: string; knob: string; name: string; ic: string }> = {
  done: { bar: "bg-green", knob: "text-green bg-green/15 border-green/50", name: "text-muted", ic: "✓" },
  active: { bar: "bg-amber", knob: "text-amber bg-amber/[0.09] border-amber/50", name: "text-amber", ic: "●" },
  pending: { bar: "bg-[#2A2A30]", knob: "text-muted-3 bg-transparent border-line-2", name: "text-muted-3", ic: "" },
};

function Stepper({ steps }: { steps: { label: string; st: StepState }[] }) {
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${steps.length},1fr)` }}>
      {steps.map((s) => {
        const k = STEP_SKIN[s.st];
        return (
          <div key={s.label} className="flex flex-col gap-2">
            <div className={`h-[3px] rounded-[3px] ${k.bar}`} />
            <div className="flex items-center gap-1.5">
              <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[9px] ${k.knob}`}>{k.ic}</span>
              <span className={`font-mono text-[10px] tracking-[0.04em] ${k.name}`}>{s.label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =============================================================================
export default function OrderDetailPage() {
  const params = useParams();
  const raw = Array.isArray(params.id) ? params.id[0] : params.id;
  const id = Number(raw);
  const validId = Number.isFinite(id) && id > 0;

  const [job, setJob] = useState<Job | null>(null);
  const [jobState, setJobState] = useState<"loading" | "ready" | "error">("loading");
  const [jobError, setJobError] = useState<string>("");

  const [cert, setCert] = useState<Cert | null>(null);
  const [certState, setCertState] = useState<"idle" | "loading" | "ready" | "none" | "error">("idle");
  const [certError, setCertError] = useState<string>("");

  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string>("");

  // load the job
  useEffect(() => {
    if (!validId) {
      setJobState("error");
      setJobError("No job selected");
      return;
    }
    let alive = true;
    setJobState("loading");
    getJob(id)
      .then((j) => {
        if (!alive) return;
        setJob(j);
        setJobState("ready");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setJobState("error");
        setJobError(e instanceof Error ? e.message : "Job not found");
      });
    return () => {
      alive = false;
    };
  }, [id, validId]);

  // once we have a completed job, pull the signed certificate
  useEffect(() => {
    if (!validId || !job) return;
    if (job.status !== "completed") {
      setCertState("idle");
      return;
    }
    let alive = true;
    setCertState("loading");
    getCert(id)
      .then((c) => {
        if (!alive) return;
        setCert(c);
        setCertState("ready");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) {
          setCertState("none"); // signed cert not minted yet
        } else {
          setCertState("error");
          setCertError(e instanceof Error ? e.message : "Failed to load certificate");
        }
      });
    return () => {
      alive = false;
    };
  }, [id, validId, job]);

  const runVerify = useCallback(async () => {
    setVerifying(true);
    setVerifyError("");
    setVerify(null);
    try {
      const v = await verifyJob(id);
      setVerify(v);
    } catch (e: unknown) {
      setVerifyError(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setVerifying(false);
    }
  }, [id]);

  // ---- frame -----------------------------------------------------------------
  const back = (
    <Link href="/dashboard" className="mb-6 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-2 hover:text-text">
      ← Dashboard
    </Link>
  );

  if (jobState === "loading") {
    return (
      <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
        {back}
        <div className="card flex items-center gap-3 p-6 font-mono text-[13px] text-muted-2">
          <Spinner className="h-[18px] w-[18px]" /> Loading job…
        </div>
      </main>
    );
  }

  if (jobState === "error" || !job) {
    const noSelection = jobError === "No job selected";
    return (
      <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
        {back}
        <h1 className="mb-2 text-2xl font-medium tracking-[-0.015em]">{noSelection ? "No job selected" : "Job not found"}</h1>
        {noSelection ? (
          <p className="text-[13px] text-muted">
            Open a job from the <Link href="/dashboard" className="text-teal hover:underline">dashboard</Link> or{" "}
            <Link href="/new-order" className="text-teal hover:underline">start a new order</Link>.
          </p>
        ) : (
          <p className="text-[13px] text-red">✗ {jobError}</p>
        )}
      </main>
    );
  }

  // ---- derived state ---------------------------------------------------------
  const synth = job.service === "synthesis";
  const completed = job.status === "completed";
  const failed = job.status === "failed";
  const processing = job.status === "processing";
  const hasCert = !!job.certificate;
  const targetKept = (job as Job & { synth_target_kept?: number | null }).synth_target_kept ?? null;

  // header badge
  let badge: { txt: string; tone: Tone } = { txt: "PAID · READY", tone: "teal" };
  if (completed) badge = { txt: "COMPLETE", tone: "green" };
  else if (failed) badge = { txt: "FAILED", tone: "red" };
  else if (processing) badge = { txt: "PROCESSING", tone: "teal" };

  // stepper (driven only from status + cert presence — the data the client exposes)
  const processed = processing || completed;
  const steps: { label: string; st: StepState }[] = synth
    ? [
        { label: "PAID", st: "done" },
        { label: "GENERATE", st: completed ? "done" : processing ? "active" : "pending" },
        { label: "FILTER", st: completed ? "done" : "pending" },
        { label: "CERTIFY", st: hasCert ? "done" : "pending" },
      ]
    : [
        { label: "PAID", st: "done" },
        { label: "TRIAGE", st: processed ? "done" : "pending" },
        { label: "SCORED", st: processed ? "done" : "pending" },
        { label: "REFINED", st: completed ? "done" : "pending" },
        { label: "CERTIFIED", st: hasCert ? "done" : "pending" },
      ];

  // conductor pipeline current node
  let loop: { txt: string; tone: Tone };
  if (completed) loop = { txt: "AAR · certified", tone: "green" };
  else if (failed) loop = { txt: synth ? "Generation failed" : "Refinement failed", tone: "red" };
  else if (processing) loop = { txt: synth ? "Generating · filtering" : "Triage + scoring", tone: "teal" };
  else loop = { txt: synth ? "Paid · queued to generate" : "Paid · ready to triage", tone: "teal" };

  const LOOP_DOT: Record<Tone, string> = {
    teal: "#00E5CC",
    green: "#22C55E",
    amber: "#F59E0B",
    red: "#ef4444",
    muted: "#71717A",
  };

  return (
    <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
      {back}

      {/* title row */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="eyebrow mb-2.5">// {synth ? "GENERATION JOB" : "REFINEMENT JOB"}</div>
          <h1 className="mb-1.5 text-[26px] font-medium tracking-[-0.015em]">
            {synth ? "Generation job #" : "Refinement job #"}
            {job.id}
          </h1>
          <div className="font-mono text-[12px] text-muted-2">
            JOB-{String(job.id).padStart(5, "0")} · created {longDate(job.created_at)} · {synth ? "synthetic JSONL" : "ChatML JSONL"}
          </div>
        </div>
        <div className="self-start">
          <Pill tone={badge.tone}>{badge.txt}</Pill>
        </div>
      </div>

      {/* stepper */}
      <div className="mb-6">
        <Stepper steps={steps} />
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[1.55fr_1fr]">
        {/* LEFT column */}
        <div className="flex flex-col gap-5">
          {/* primary card — service aware */}
          {synth ? (
            <div className="card p-6">
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <span className="text-teal">◎</span>
                  <span className="text-base font-semibold">Synthetic generation</span>
                </div>
                <Pill tone="teal">DGX SPARK · LIVE</Pill>
              </div>
              <p className="mb-4 text-[13px] text-muted">
                Aegis governs the run and picks the cheapest capable models (shown in the certificate&apos;s provenance) to
                generate candidates, keeps only the strong-solves, and signs the result — no source dataset required.
              </p>

              <div className="mb-4">
                <KVList>
                  <KV k="Topic" value={job.synth_topic || "—"} vClass="text-teal" />
                  <KV k="Target rows" value={targetKept != null ? num(targetKept) : "—"} />
                </KVList>
              </div>

              <Label className="mb-2.5">Pipeline</Label>
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <Pill tone="teal">Generate</Pill>
                <span className="text-muted-2">→</span>
                <Pill tone="teal">Filter</Pill>
                <span className="text-muted-2">→</span>
                <Pill tone="teal">Certify</Pill>
              </div>

              {completed ? (
                <div className="flex items-center gap-2.5 rounded-[10px] border border-green/[0.28] bg-green/[0.08] p-3.5 font-mono text-[12.5px] text-green">
                  <span>✓</span> Dataset generated — download &amp; signed certificate are ready below.
                </div>
              ) : failed ? (
                <div className="rounded-[10px] border border-red/40 bg-red/10 p-3.5 text-[13px] text-red">
                  ✗ Generation failed. Reach support@aegisrefine.com — you are not charged for a failed run.
                </div>
              ) : (
                <div className="flex items-center gap-2.5 rounded-[10px] border border-teal-line bg-teal-dim p-3.5 font-mono text-[12.5px] text-teal">
                  <Spinner className="h-[18px] w-[18px]" /> {"Generating your dataset — ~5 min; we'll email you when it's ready."}
                </div>
              )}
            </div>
          ) : (
            <div className="card p-6">
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <span className="text-teal">◎</span>
                  <span className="text-base font-semibold">Aegis-14B refinement</span>
                </div>
                <Pill tone="teal">DGX SPARK · LIVE</Pill>
              </div>
              <p className="mb-4 text-[13px] text-muted">
                Aegis-14B triages and scores your data, refines it on DGX Spark under the human spend gate, and ships a
                signed certificate you can re-verify.
              </p>

              {completed ? (
                <div className="flex items-center gap-2.5 rounded-[10px] border border-green/[0.28] bg-green/[0.08] p-3.5 font-mono text-[12.5px] text-green">
                  <span>✓</span> Refinement complete — download &amp; signed certificate are ready below.
                </div>
              ) : failed ? (
                <div className="rounded-[10px] border border-red/40 bg-red/10 p-3.5 text-[13px] text-red">
                  ✗ Refinement failed. Reach support@aegisrefine.com — you are not charged for a failed run.
                </div>
              ) : processing ? (
                <div className="flex items-center gap-2.5 rounded-[10px] border border-teal-line bg-teal-dim p-3.5 font-mono text-[12.5px] text-teal">
                  <Spinner className="h-[18px] w-[18px]" /> Refining your dataset on DGX Spark…
                </div>
              ) : (
                <div className="flex items-center gap-2.5 rounded-[10px] border border-teal-line bg-teal-dim p-3.5 font-mono text-[12.5px] text-teal">
                  <span className="text-teal">⛉</span> Paid — queued to refine.
                </div>
              )}
            </div>
          )}

          {/* DELIVERABLES */}
          <div className="card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold">Deliverables</h2>
              <span className={`font-mono text-[11px] ${completed ? "text-green" : "text-muted-2"}`}>
                {completed ? "READY" : "LOCKED UNTIL COMPLETE"}
              </span>
            </div>
            <div className="flex flex-col gap-2.5">
              <Deliverable
                icon="▤"
                label={synth ? "Synthetic dataset" : "Refined dataset"}
                meta={completed ? (synth ? "synthesized · JSONL" : "refined · JSONL") : "awaiting completion"}
                href={completed ? downloadUrl(id) : null}
                chip="↓ DOWNLOAD"
              />
              <Deliverable
                icon="⛉"
                label="Dataset package (.zip)"
                meta={completed ? "dataset + signed certificate + verify steps" : "awaiting completion"}
                href={completed ? packageUrl(id) : null}
                chip="↓ DOWNLOAD"
              />
            </div>
          </div>

          {/* SIGNED AAR CERTIFICATE */}
          {completed && (
            <CertSection
              state={certState}
              cert={cert}
              error={certError}
              jobId={id}
              verify={verify}
              verifying={verifying}
              verifyError={verifyError}
              onVerify={runVerify}
            />
          )}
        </div>

        {/* RIGHT column */}
        <div className="flex flex-col gap-4 lg:sticky lg:top-6">
          <div className="card p-6">
            <Label className="mb-3.5">Job details</Label>
            <div className="flex flex-col gap-3 text-[13px]">
              <Row k={synth ? "Topic" : "Source data"} v={synth ? job.synth_topic || "—" : job.input || "—"} break />
              <Row k="Status" v={job.status || "pending"} />
              <Row k="Created" v={shortDate(job.created_at)} />
              <Row k="Inference" v={synth ? "cheapest-good-enough (see provenance)" : "DGX Spark"} vClass="text-green" />
            </div>
          </div>

          <div className="card p-6">
            <Label className="mb-3.5">Your order</Label>
            <Ledger job={job} cert={certState === "ready" ? cert : null} />
          </div>

          <div className="card border-teal-line p-6 shadow-[0_0_40px_rgba(0,229,204,0.06)]">
            <Label className="mb-3.5 text-teal">Conductor pipeline</Label>
            <div className="flex items-center gap-2.5">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: LOOP_DOT[loop.tone], boxShadow: `0 0 8px ${LOOP_DOT[loop.tone]}` }}
              />
              <div>
                <div className="font-mono text-[10px] tracking-[0.12em] text-muted-2">CURRENT NODE</div>
                <div className="text-[13.5px] font-medium" style={{ color: LOOP_DOT[loop.tone] }}>
                  {loop.txt}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

// ---- deliverable row --------------------------------------------------------
function Deliverable({
  icon,
  label,
  meta,
  href,
  chip,
}: {
  icon: string;
  label: string;
  meta: string;
  href: string | null;
  chip: string;
}) {
  const inner = (
    <>
      <span className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-lg border border-teal-line bg-teal/[0.08] text-teal">
        {icon}
      </span>
      <div className="flex-1">
        <div className="text-sm font-medium">{label}</div>
        <div className="font-mono text-[11px] text-muted-2">{meta}</div>
      </div>
      <span
        className={`shrink-0 rounded-md border px-3 py-1.5 font-mono text-[11px] ${
          href ? "border-teal-line text-teal" : "border-line-2 text-muted-3"
        }`}
      >
        {href ? chip : "⛒ LOCKED"}
      </span>
    </>
  );
  const cls = "flex items-center gap-3.5 rounded-[10px] border border-line bg-panel-3 p-3.5 transition-opacity";
  if (!href) return <div className={`${cls} opacity-45`}>{inner}</div>;
  return (
    <a href={href} download className={cls}>
      {inner}
    </a>
  );
}

// ---- right-column simple row -----------------------------------------------
function Row({ k, v, vClass = "", break: brk = false }: { k: string; v: React.ReactNode; vClass?: string; break?: boolean }) {
  return (
    <div className="flex justify-between gap-2.5">
      <span className="text-muted">{k}</span>
      <span className={`font-mono ${brk ? "max-w-[62%] break-all text-right" : ""} ${vClass}`}>{v}</span>
    </div>
  );
}

// ---- order ledger (price paid + re-checkable guarantees, NEVER spend/margin)
function Ledger({ job, cert }: { job: Job; cert: Cert | null }) {
  const quoted = job.quote_amount != null ? money(job.quote_amount) : "—";
  const ec = cert?.economics ?? null;
  const g = cert?.guarantees ?? null;
  const capOk = ec ? ec.cap_respected !== false : null;
  return (
    <div className="flex flex-col">
      <div className="flex justify-between border-b border-line py-2 text-[13.5px]">
        <span className="text-muted">Price paid</span>
        <span className="font-mono font-semibold text-green">{quoted}</span>
      </div>
      {capOk !== null && (
        <div className="flex justify-between border-b border-line py-2 text-[13px]">
          <span className="text-muted">Budget cap</span>
          <span className={`font-mono ${capOk ? "text-green" : "text-amber"}`}>{capOk ? "✓ respected" : "✗ exceeded"}</span>
        </div>
      )}
      {g ? (
        <>
          <div className="flex justify-between border-b border-line py-2 text-[13px]">
            <span className="text-muted">Rows</span>
            <span className="font-mono">{num(g.rows)}</span>
          </div>
          <div className="flex justify-between border-b border-line py-2 text-[13px]">
            <span className="text-muted">PII residual</span>
            <span className={`font-mono ${g.pii_residual === 0 ? "text-green" : "text-amber"}`}>{num(g.pii_residual)}</span>
          </div>
          <div className="flex justify-between border-b border-line py-2 text-[13px]">
            <span className="text-muted">Dupes residual</span>
            <span className={`font-mono ${g.dupes_residual === 0 ? "text-green" : "text-amber"}`}>{num(g.dupes_residual)}</span>
          </div>
          <div className="flex justify-between py-2 pb-0 text-[13px]">
            <span className="text-muted">Schema valid</span>
            <span className={`font-mono ${g.schema_valid ? "text-green" : "text-amber"}`}>{g.schema_valid ? "✓ valid" : "✗ invalid"}</span>
          </div>
        </>
      ) : (
        <div className="pt-2.5 font-mono text-[11px] text-muted-2">
          Re-checkable guarantees appear here once the job completes &amp; is signed.
        </div>
      )}
    </div>
  );
}

// ---- signed AAR certificate section ----------------------------------------
function CertSection({
  state,
  cert,
  error,
  verify,
  verifying,
  verifyError,
  onVerify,
}: {
  state: "idle" | "loading" | "ready" | "none" | "error";
  cert: Cert | null;
  error: string;
  jobId: number;
  verify: VerifyResult | null;
  verifying: boolean;
  verifyError: string;
  onVerify: () => void;
}) {
  if (state === "loading" || state === "idle") {
    return (
      <div className="card flex items-center gap-2.5 p-6 font-mono text-[12.5px] text-muted-2">
        <Spinner className="h-[18px] w-[18px]" /> Loading signed certificate…
      </div>
    );
  }
  if (state === "none") {
    return (
      <div className="card p-6">
        <div className="mb-1.5 flex items-center gap-2.5">
          <span className="text-muted-2">⛉</span>
          <h2 className="text-base font-semibold">Signed AAR certificate</h2>
        </div>
        <p className="text-[13px] text-muted">No certificate yet — it is being signed. Refresh in a moment.</p>
      </div>
    );
  }
  if (state === "error" || !cert) {
    return (
      <div className="card p-6 text-[13px] text-red">✗ {error || "Failed to load certificate"}</div>
    );
  }

  const ec = cert.economics;
  const g = cert.guarantees;
  const syn = (g?.synthesis as SynthProvenance | undefined) ?? null;
  const sig = cert.sig;
  const capOk = ec ? ec.cap_respected !== false : true;

  return (
    <div className="card p-6">
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="text-teal">⛉</span>
          <h2 className="text-base font-semibold">Signed AAR certificate</h2>
        </div>
        <Pill tone="green">SIGNED</Pill>
      </div>
      <p className="mb-4 text-[13px] text-muted">
        The agent&apos;s audited price + re-checkable data guarantees, Ed25519-signed.
        {syn ? " This job synthesized data — provenance below." : ""}
      </p>

      {/* ECONOMICS — quoted price + cap only (never spent / margin / COGS) */}
      <Label className="mb-2.5">Economics</Label>
      <KVList>
        <KV k="Price paid (capped)" value={usd(ec?.quoted_usd)} vClass="text-green" />
        <KV k="Cap respected" value={capOk ? "✓ yes" : "✗ no"} vClass={capOk ? "text-green" : "text-amber"} />
      </KVList>

      {/* GUARANTEES */}
      <Label className="mb-2.5 mt-[18px]">Guarantees</Label>
      <KVList>
        <KV k="Rows" value={num(g?.rows)} />
        <KV k="PII residual" value={num(g?.pii_residual)} vClass={g?.pii_residual === 0 ? "text-green" : "text-amber"} />
        <KV k="Dupes residual" value={num(g?.dupes_residual)} vClass={g?.dupes_residual === 0 ? "text-green" : "text-amber"} />
        <KV k="Schema valid" value={g?.schema_valid ? "✓ valid" : "✗ invalid"} vClass={g?.schema_valid ? "text-green" : "text-amber"} />
      </KVList>

      {/* SYNTHETIC PROVENANCE — counts only (no by_model cost, no spent) */}
      {syn && (
        <div className="mt-[18px]">
          <Label className="mb-2.5">Synthetic provenance</Label>
          <KVList>
            <KV k="Method" value={syn.method || "—"} />
            {syn.mode && <KV k="Mode" value={syn.mode} vClass="text-teal" />}
            <KV k="Candidates generated" value={num(syn.candidates_generated)} />
            <KV k="Kept synthetic" value={num(syn.kept_synthetic)} vClass="text-green" />
            <KV k="Yield" value={syn.yield_pct != null ? `${syn.yield_pct}%` : "—"} vClass="text-teal" />
            <KV k="Real vs synthetic rows" value={`${num(syn.real_rows)} real · ${num(syn.synthetic_rows)} synthetic`} />
          </KVList>
          {syn.models && (
            <div className="mt-2.5">
              <Label className="mb-2">Models</Label>
              <KVList>
                {(["challenger", "weak", "strong", "judge"] as const)
                  .filter((m) => syn.models?.[m])
                  .map((m) => (
                    <KV key={m} k={m[0].toUpperCase() + m.slice(1)} value={syn.models?.[m]} />
                  ))}
              </KVList>
            </div>
          )}
          {syn.labeled_synthetic && (
            <div className="mt-3 font-mono text-[11px] text-muted-2">
              <span className="text-green">✓</span> Every row labeled synthetic · provenance signed
            </div>
          )}
        </div>
      )}

      {/* SIGNATURE */}
      <div className="mt-[18px] flex items-center justify-between gap-3 rounded-lg border border-line bg-panel-3 px-3.5 py-3">
        <span className="font-mono text-[11px] text-muted-2">SIGNATURE</span>
        <span className="font-mono text-[11px] text-teal" title={sig?.value || ""}>
          {(sig?.alg || "—") + " · " + shortSig(sig?.value)}
        </span>
      </div>

      {/* RE-VERIFY */}
      <button onClick={onVerify} disabled={verifying} className="btn-teal mt-4 w-full px-5 py-3 text-[15px] disabled:opacity-60">
        ⛉ &nbsp;Re-verify →
      </button>

      {verifying && (
        <div className="mt-3.5 flex items-center gap-2.5 font-mono text-[12.5px] text-teal">
          <Spinner className="h-[18px] w-[18px]" /> Re-running signature + data guarantees…
        </div>
      )}
      {verifyError && !verifying && <div className="mt-3.5 text-[13px] text-red">✗ {verifyError}</div>}
      {verify && !verifying && <VerifyResultCard v={verify} />}
    </div>
  );
}

function VerifyResultCard({ v }: { v: VerifyResult }) {
  const rc = v.guarantees_recheck;
  const sigOk = v.ok && v.level !== "FAIL";
  const ok = sigOk;
  return (
    <div className="mt-3.5">
      <div className="mb-3.5 flex items-center gap-3">
        <span
          className={`flex h-10 w-10 items-center justify-center rounded-full border text-xl ${
            ok ? "border-green/40 bg-green/[0.12] text-green" : "border-red/40 bg-red/[0.12] text-red"
          }`}
        >
          {ok ? "✓" : "✗"}
        </span>
        <div>
          <div className="text-[15px] font-semibold">{ok ? "Re-verified against reality" : "Verification failed"}</div>
          <Pill tone={sigOk ? "green" : "red"}>CONFORMANCE {v.level || "FAIL"}</Pill>
        </div>
      </div>
      <KVList>
        <KV k="Signature ok" value={sigOk ? "✓ yes" : "✗ no"} vClass={sigOk ? "text-green" : "text-amber"} />
        <KV k="Rows" value={rc?.rows != null ? num(rc.rows) : "—"} />
        <KV
          k="PII residual"
          value={rc?.pii_residual != null ? num(rc.pii_residual) : "—"}
          vClass={rc?.pii_residual === 0 ? "text-green" : "text-amber"}
        />
      </KVList>
    </div>
  );
}
