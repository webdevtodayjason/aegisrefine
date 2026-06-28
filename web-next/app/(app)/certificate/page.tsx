"use client";

// Customer-facing signed-AAR certificate, ported from the static backend/web/certificate.html.
// Resolves a job id from ?job=N (or an inline input), fetches the signed Agent Attestation
// Record via getCert(), and renders three views: the certificate artifact, the raw signed JSON,
// and an independent re-verify. Only customer-safe economics are shown — QUOTED price paid +
// budget-cap discipline. COGS / spent / margin / by-model costs stay in the signed JSON for
// verifiers, never surfaced in the artifact. Built with the design tokens for the dark-teal look.
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getCert, getJob, verifyJob, ApiError } from "@/lib/api";

// --- the real AAR shape (richer than lib/api's minimal Cert) — see backend aar_service.py ---
interface AarCheck {
  source?: string;
  query?: string;
  observed_at?: string;
  response_sha256?: string;
  excerpt?: string;
}
interface AarSynthesis {
  method?: string;
  mode?: string;
  candidates_generated?: number | null;
  kept_synthetic?: number | null;
  yield_pct?: number | null;
  models?: Record<string, string> | string[] | string | null;
  real_rows?: number | null;
  synthetic_rows?: number | null;
}
interface AarGuarantees {
  rows?: number | null;
  pii_residual?: number | null;
  dupes_residual?: number | null;
  schema_valid?: boolean | null;
  output_format?: string | null;
  synthesis?: AarSynthesis | null;
}
interface AarEconomics {
  quoted_usd?: number | null;
  cap_respected?: boolean;
  // spent_usd / margin_usd / providers intentionally not read — verifier-only fields.
}
interface Aar {
  aar?: string;
  subject?: string;
  principal?: string;
  task?: { id?: string; claim?: string };
  verdict?: string;
  ground_truth?: string;
  reason?: string;
  checks?: AarCheck[];
  verifier?: { id?: string; model?: string; independence?: string };
  issued?: string;
  economics?: AarEconomics | null;
  guarantees?: AarGuarantees | null;
  sig?: { alg?: string; value?: string; by?: string };
}

// best-effort enrichment from /jobs/{id} for the governed-decisions ledger + cert id
type SpendTicket = {
  id: number;
  amount: number | null;
  description: string | null;
  status: string;
  approved_by: string | null;
};
type JobDetail = {
  spend_tickets?: SpendTicket[];
  certificate?: { id?: number; aar?: string } | null;
};

type VerifyResult = {
  ok: boolean;
  level: string;
  output?: string;
  guarantees_recheck?: {
    rows?: number | null;
    pii_residual?: number | null;
    dupes_residual?: number | null;
    schema_valid?: boolean | null;
    ok?: boolean;
  };
};

type Tab = "cert" | "json" | "verify";
type Phase = "init" | "nojob" | "loading" | "ready" | "error";

// --- formatting helpers (mirrors the static page) ---
const money = (v: number | null | undefined) =>
  v == null ? "—" : "$" + Number(v).toFixed(2);

const short = (s: string, n = 14) => {
  const str = String(s || "");
  return str.length > n * 2 ? str.slice(0, n) + "…" + str.slice(-n) : str;
};

const fmtDate = (iso?: string) => {
  try {
    return (
      new Date(iso as string)
        .toISOString()
        .replace("T", " ")
        .replace(/\.\d+Z$/, "")
        .replace("Z", "") + " UTC"
    );
  } catch {
    return iso || "—";
  }
};

const modelsLabel = (m: AarSynthesis["models"]): string => {
  if (Array.isArray(m)) return m.join(", ");
  if (m && typeof m === "object") return Object.values(m).join(", ");
  return m || "—";
};

// --- small presentational pieces ---
function Dot() {
  return (
    <span className="mr-2 inline-block h-[7px] w-[7px] rounded-full bg-teal shadow-[0_0_8px_#00E5CC] motion-safe:animate-pulse" />
  );
}

function StatCell({ h, v, color }: { h: string; v: string; color?: string }) {
  return (
    <div className="bg-[#121519] px-3 py-[15px] text-center">
      <div className="font-mono text-[9px] tracking-[0.1em] text-muted-2">{h}</div>
      <div className="mt-1.5 font-mono text-[16px]" style={color ? { color } : undefined}>
        {v}
      </div>
    </div>
  );
}

function AttRow({
  label,
  value,
  valueClass = "",
  valueStyle,
  title,
}: {
  label: string;
  value: React.ReactNode;
  valueClass?: string;
  valueStyle?: React.CSSProperties;
  title?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 bg-panel-3 px-4 py-3 text-[13px]">
      <span className="flex-shrink-0 text-muted-2">{label}</span>
      <span
        className={`break-all text-right font-mono ${valueClass}`}
        style={valueStyle}
        title={title}
      >
        {value}
      </span>
    </div>
  );
}

function DecRow({ color, children, tag }: { color: string; children: React.ReactNode; tag: string }) {
  return (
    <div className="flex items-center gap-3 bg-[#121519] px-4 py-3">
      <span className="h-2 w-2 flex-shrink-0 rounded-full" style={{ background: color }} />
      <span className="flex-1 text-[13px]">{children}</span>
      <span className="font-mono text-[11px] text-muted-2">{tag}</span>
    </div>
  );
}

// --- the certificate artifact (CERTIFICATE tab) ---
function CertArtifact({ aar, job, jobId }: { aar: Aar; job: JobDetail | null; jobId: string }) {
  const e = aar.economics;
  const g = aar.guarantees;
  const sha = aar.checks?.[0]?.response_sha256 || "—";
  const verifierId = aar.verifier?.id || "—";
  const verifierShort = verifierId.split(":").pop() || "conductor";
  const sigAlg = aar.sig?.alg || "—";
  const sigVal = aar.sig?.value || "";
  const certId = job?.certificate?.id
    ? `cert_${job.certificate.id}`
    : aar.task?.id || `job-${jobId}`;
  const claimMid = aar.task?.claim ? `— ${aar.task.claim} —` : "";

  // governed-decisions ledger (best-effort, from /jobs/{id})
  const tickets = job?.spend_tickets ?? [];
  const colorFor = (st: string) =>
    st === "approved" || st === "executed" ? "#22C55E" : st === "rejected" ? "#ef4444" : "#F59E0B";

  return (
    <div
      className="relative mx-auto w-full max-w-[700px] rounded-[16px] border border-teal-line p-[clamp(26px,4vw,46px)]"
      style={{
        background: "linear-gradient(180deg,#121519,#0D0D0F)",
        boxShadow: "0 0 70px rgba(0,229,204,0.08)",
      }}
    >
      {/* corner ticks */}
      <span className="absolute left-[14px] top-[14px] h-[22px] w-[22px] border-l-2 border-t-2 border-[rgba(0,229,204,0.6)]" />
      <span className="absolute right-[14px] top-[14px] h-[22px] w-[22px] border-r-2 border-t-2 border-[rgba(0,229,204,0.6)]" />
      <span className="absolute bottom-[14px] left-[14px] h-[22px] w-[22px] border-b-2 border-l-2 border-[rgba(0,229,204,0.6)]" />
      <span className="absolute bottom-[14px] right-[14px] h-[22px] w-[22px] border-b-2 border-r-2 border-[rgba(0,229,204,0.6)]" />

      {/* header */}
      <div className="mb-[22px] text-center">
        <div className="mb-3.5 text-[40px] leading-none text-teal drop-shadow-[0_0_12px_rgba(0,229,204,0.5)]">
          ⛉
        </div>
        <div className="text-[clamp(23px,3.2vw,32px)] font-semibold tracking-[-0.01em]">
          Audit <span className="text-teal">Certificate</span>
        </div>
        <div className="mt-2 font-mono text-[10px] tracking-[0.2em] text-muted-2">
          AEGIS-14B-GOVERNED · CRYPTOGRAPHICALLY SIGNED
        </div>
      </div>

      {/* verdict badge */}
      <div className="mb-6 flex justify-center">
        <div
          className="inline-flex items-center gap-2.5 rounded-full px-[18px] py-[9px]"
          style={{ background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.4)" }}
        >
          <span
            className="flex h-[22px] w-[22px] items-center justify-center rounded-full text-[12px]"
            style={{ background: "#22C55E", color: "#04130A" }}
          >
            ✓
          </span>
          <span className="font-mono text-[12px] tracking-[0.1em] text-green">
            {String(aar.verdict ?? "verified").toUpperCase()} · GROUND TRUTH{" "}
            {String(aar.ground_truth ?? "confirmed").toUpperCase()}
          </span>
        </div>
      </div>

      {/* attestation sentence */}
      <p className="mx-auto mb-[26px] max-w-[480px] text-center text-[13.5px] leading-[1.6] text-muted">
        This attests that{" "}
        <span className="font-mono text-text">{aar.task?.id || `job-${jobId}`}</span>{" "}
        {claimMid ? `${claimMid} ` : ""}
        was governed by a Aegis-14B agent, every external spend held behind an explicit human gate,
        and the result hash committed as evidence for an independent verifier.
      </p>

      {/* economics — QUOTED price + cap discipline only */}
      {e ? (
        <div className="mb-[22px] grid grid-cols-2 gap-px overflow-hidden rounded-[10px] border border-line bg-[rgba(255,255,255,0.07)]">
          <StatCell h="QUOTED PRICE" v={money(e.quoted_usd)} color="#22C55E" />
          <StatCell
            h="BUDGET CAP"
            v={e.cap_respected !== false ? "RESPECTED" : "EXCEEDED"}
            color={e.cap_respected !== false ? "#00E5CC" : "#ef4444"}
          />
        </div>
      ) : (
        <div className="mb-[22px] grid grid-cols-1 gap-px overflow-hidden rounded-[10px] border border-line bg-[rgba(255,255,255,0.07)]">
          <StatCell h="PRICE" v="NOT RECORDED FOR THIS JOB" color="#71717A" />
        </div>
      )}

      {/* re-checkable guarantees */}
      {g && (
        <>
          <div className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-2">
            RE-CHECKABLE GUARANTEES
          </div>
          <div className="mb-[26px] flex flex-col gap-px overflow-hidden rounded-[10px] border border-line bg-[rgba(255,255,255,0.07)]">
            <AttRow label="Clean rows" value={g.rows ?? "—"} valueClass="text-teal" />
            <AttRow
              label="PII residual"
              value={`${g.pii_residual ?? "—"} ${Number(g.pii_residual) === 0 ? "✓" : "✗"}`}
              valueClass={Number(g.pii_residual) === 0 ? "text-green" : "text-red"}
            />
            <AttRow
              label="Duplicate residual"
              value={`${g.dupes_residual ?? "—"} ${Number(g.dupes_residual) === 0 ? "✓" : "✗"}`}
              valueClass={Number(g.dupes_residual) === 0 ? "text-green" : "text-red"}
            />
            <AttRow
              label="Schema valid"
              value={g.schema_valid ? "✓ valid" : "✗ invalid"}
              valueClass={g.schema_valid ? "text-green" : "text-red"}
            />
            {g.output_format && <AttRow label="Output format" value={g.output_format} />}
          </div>

          {/* synthetic provenance (counts only — costs stay in the signed JSON) */}
          {g.synthesis && (
            <>
              <div className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-2">
                SYNTHETIC PROVENANCE
              </div>
              <div className="mb-[26px] flex flex-col gap-px overflow-hidden rounded-[10px] border border-line bg-[rgba(255,255,255,0.07)]">
                <AttRow label="Method" value={g.synthesis.method || "—"} valueClass="break-words" />
                <AttRow
                  label="Candidates generated"
                  value={g.synthesis.candidates_generated ?? "—"}
                />
                <AttRow
                  label="Kept (synthetic)"
                  value={g.synthesis.kept_synthetic ?? "—"}
                  valueClass="text-teal"
                />
                <AttRow label="Yield" value={`${g.synthesis.yield_pct ?? "—"}%`} />
                <AttRow
                  label="Real / synthetic rows"
                  value={`${g.synthesis.real_rows ?? 0} real · ${
                    g.synthesis.synthetic_rows ?? g.synthesis.kept_synthetic ?? 0
                  } synthetic`}
                />
                <AttRow
                  label="Models"
                  value={modelsLabel(g.synthesis.models)}
                  valueClass="break-words"
                />
              </div>
            </>
          )}
        </>
      )}

      {/* governed decisions */}
      <div className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-2">
        GOVERNED DECISIONS
      </div>
      <div className="mb-[26px] flex flex-col gap-px overflow-hidden rounded-[10px] border border-line bg-[rgba(255,255,255,0.07)]">
        {tickets.length === 0 && (
          <DecRow color="#22C55E" tag="no gated spend">
            Refinement governed end-to-end by Aegis-14B
          </DecRow>
        )}
        {tickets.map((tk) => {
          const amt = tk.amount != null ? `$${Number(tk.amount).toFixed(2)}` : "";
          return (
            <div key={tk.id} className="contents">
              <DecRow color={colorFor(tk.status)} tag="Aegis-14B">
                Agent proposed {amt} — {tk.description || "external spend"}
              </DecRow>
              {tk.approved_by && (
                <DecRow color="#22C55E" tag={tk.approved_by}>
                  Human {tk.status === "rejected" ? "rejected" : "approved"} the spend
                </DecRow>
              )}
              {tk.status === "executed" && (
                <DecRow color="#F59E0B" tag="stub">
                  Spend authorized <span className="text-amber">(test)</span> — no live funds moved
                </DecRow>
              )}
            </div>
          );
        })}
        <DecRow color="#00E5CC" tag={verifierShort}>
          Dataset refined &amp; certificate signed
        </DecRow>
      </div>

      {/* attestation record */}
      <div className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-2">
        ATTESTATION RECORD
      </div>
      <div className="mb-[26px] flex flex-col gap-px overflow-hidden rounded-[10px] border border-line bg-[rgba(255,255,255,0.07)]">
        <AttRow label="Subject" value={aar.subject} valueClass="text-teal" />
        <AttRow label="Principal" value={aar.principal} />
        <AttRow label="Claim" value={aar.task?.claim || "—"} />
        <AttRow label="Verdict" value={aar.verdict} valueClass="text-green" />
        <AttRow label="Ground truth" value={aar.ground_truth} valueClass="text-green" />
        <AttRow
          label="Evidence (response_sha256)"
          value={short(sha, 12)}
          valueClass="text-teal"
          title={sha}
        />
        <AttRow label="Verifier" value={verifierId} />
        <AttRow label="Issued" value={fmtDate(aar.issued)} />
      </div>

      {/* signature footer */}
      <div className="flex flex-wrap items-end justify-between gap-5 border-t border-white/[0.08] pt-[22px]">
        <div>
          <div className="mb-1 font-mono text-[18px] tracking-[0.05em] text-teal">⌁ {verifierShort}</div>
          <div className="my-1.5 h-px w-[130px] bg-white/20" />
          <div className="font-mono text-[10px] text-muted-2">
            {sigAlg} · sig <span title={sigVal}>{short(sigVal, 10)}</span>
          </div>
        </div>
        <div className="flex flex-col items-center gap-1.5">
          <div
            className="h-[62px] w-[62px] rounded-[8px] border border-teal-line"
            style={{
              backgroundColor: "#0D0D0F",
              backgroundImage:
                "repeating-linear-gradient(45deg,rgba(0,229,204,.5) 0 3px,transparent 3px 6px),repeating-linear-gradient(-45deg,rgba(0,229,204,.3) 0 3px,transparent 3px 6px)",
            }}
          />
          <div className="font-mono text-[9px] text-muted-2">SCAN TO VERIFY</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[9.5px] text-muted-2">CERT ID</div>
          <div className="mb-2 font-mono text-[11px] text-muted">{certId}</div>
          <div className="font-mono text-[9.5px] text-muted-2">SIGNING AUTHORITY</div>
          <div className="font-mono text-[11px] text-muted">{aar.sig?.by || aar.principal}</div>
        </div>
      </div>
    </div>
  );
}

// --- raw signed JSON (SIGNED JSON tab) ---
function SignedJson({ aar, jobId }: { aar: Aar; jobId: string }) {
  const signed = !!aar.sig?.value;
  return (
    <>
      <div className="mx-auto w-full max-w-[700px] overflow-hidden rounded-[14px] border border-line bg-[#0D0D0F]">
        <div className="flex items-center justify-between border-b border-line bg-panel px-[18px] py-[13px]">
          <span className="font-mono text-[12.5px]">job-{jobId}.aar.json</span>
          <span className={`font-mono text-[11px] ${signed ? "text-green" : "text-amber"}`}>
            {signed ? "✓ ED25519 SIGNATURE PRESENT" : "⚠ UNSIGNED"}
          </span>
        </div>
        <pre className="m-0 max-h-[70vh] overflow-auto border-0 bg-[#0D0D0F] p-5 text-[12px] leading-[1.7] text-[#9fd6d0]">
          {JSON.stringify(aar, null, 2)}
        </pre>
      </div>
      <p className="mx-auto mt-3.5 text-center font-mono text-[10.5px] text-muted-2">
        This is the exact bytes served at <span className="text-teal">/jobs/{jobId}/aar</span> — verify
        it yourself with the public key at /.well-known/did.json
      </p>
    </>
  );
}

// --- independent verification (VERIFY tab) ---
function VerifyPanel({ jobId }: { jobId: string }) {
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function runVerify() {
    setVerifying(true);
    setErr(null);
    setResult(null);
    try {
      const v = (await verifyJob(Number(jobId))) as unknown as VerifyResult;
      setResult(v);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setVerifying(false);
    }
  }

  const ok = result ? result.ok && result.level !== "FAIL" : false;
  const rc = result?.guarantees_recheck;

  return (
    <div className="mx-auto max-w-[620px] rounded-[14px] border border-line bg-panel p-[22px]">
      <div className="mb-1.5 flex items-center gap-2.5">
        <span className="text-teal">⛉</span>
        <span className="text-[15px] font-semibold">Independent verification</span>
      </div>
      <p className="mb-[18px] text-[13px] leading-[1.6] text-muted">
        Runs the public zero-dependency verifier (<span className="font-mono">tools/aar.mjs</span>)
        against this certificate and the published DID document. No Aegis trust required — the math
        checks out or it doesn&apos;t.
      </p>
      <button
        type="button"
        onClick={runVerify}
        disabled={verifying}
        className="btn-teal rounded-[9px] px-[18px] py-[13px] text-[14.5px] disabled:cursor-not-allowed disabled:opacity-40"
      >
        {verifying ? "verifying…" : "Run public verifier →"}
      </button>

      <div className="mt-5">
        {verifying && (
          <span className="font-mono text-[12.5px] text-muted">
            <Dot />
            verifying signature + conformance…
          </span>
        )}

        {err && <div className="mt-2 whitespace-pre-wrap text-[12.5px] text-red">✗ {err}</div>}

        {result && (
          <>
            <div className="mb-4 flex items-center gap-3">
              <span
                className="flex h-[46px] w-[46px] items-center justify-center rounded-full text-[22px]"
                style={{
                  background: ok ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
                  border: `1px solid ${ok ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)"}`,
                  color: ok ? "#22C55E" : "#ef4444",
                }}
              >
                {ok ? "✓" : "✗"}
              </span>
              <div>
                <div className="mb-1.5 text-[16px] font-semibold">
                  {ok ? "Signature verified" : "Verification failed"}
                </div>
                <span
                  className="inline-block rounded-[5px] px-[9px] py-1 font-mono text-[10.5px] tracking-[0.04em]"
                  style={
                    ok
                      ? { color: "#22C55E", border: "1px solid rgba(34,197,94,0.3)", background: "rgba(34,197,94,0.06)" }
                      : { color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.06)" }
                  }
                >
                  CONFORMANCE: {result.level || "FAIL"}
                </span>
                {ok && (
                  <span
                    className="ml-1.5 inline-block rounded-[5px] px-[9px] py-1 font-mono text-[10.5px] tracking-[0.04em] text-teal"
                    style={{ border: "1px solid rgba(0,229,204,0.3)", background: "rgba(0,229,204,0.1)" }}
                  >
                    UNMODIFIED SINCE ISSUE
                  </span>
                )}
              </div>
            </div>

            {rc && (
              <>
                <div className="mb-2 mt-[18px] font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-2">
                  GUARANTEES RE-CHECK{" "}
                  <span className={rc.ok !== false ? "text-green" : "text-red"}>
                    {rc.ok !== false ? "✓ re-runs clean" : "✗ mismatch"}
                  </span>
                </div>
                <div className="mb-1 flex flex-col gap-px overflow-hidden rounded-[10px] border border-line bg-[rgba(255,255,255,0.07)]">
                  <AttRow label="Clean rows" value={rc.rows ?? "—"} valueClass="text-teal" />
                  <AttRow
                    label="PII residual"
                    value={`${rc.pii_residual ?? "—"} ${Number(rc.pii_residual) === 0 ? "✓" : "✗"}`}
                    valueClass={Number(rc.pii_residual) === 0 ? "text-green" : "text-red"}
                  />
                  <AttRow
                    label="Duplicate residual"
                    value={`${rc.dupes_residual ?? "—"} ${Number(rc.dupes_residual) === 0 ? "✓" : "✗"}`}
                    valueClass={Number(rc.dupes_residual) === 0 ? "text-green" : "text-red"}
                  />
                  <AttRow
                    label="Schema valid"
                    value={rc.schema_valid ? "✓ valid" : "✗ invalid"}
                    valueClass={rc.schema_valid ? "text-green" : "text-red"}
                  />
                </div>
              </>
            )}

            <div className="mb-2 mt-4 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-2">
              RAW VERIFIER OUTPUT
            </div>
            <pre className="m-0 max-h-[300px] overflow-auto rounded-[8px] border border-line bg-[#03090b] p-2.5 text-[11px] text-[#9fd6d0]">
              {result.output || "(no output)"}
            </pre>
          </>
        )}
      </div>
    </div>
  );
}

export default function CertificatePage() {
  const router = useRouter();
  const [jobId, setJobId] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("init");
  const [aar, setAar] = useState<Aar | null>(null);
  const [job, setJob] = useState<JobDetail | null>(null);
  const [errMsg, setErrMsg] = useState("");
  const [is404, setIs404] = useState(false);
  const [tab, setTab] = useState<Tab>("cert");
  const [inputVal, setInputVal] = useState("");

  // resolve ?job=N from the URL on mount (matches the dashboard's read-from-search idiom)
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("job");
    if (p) setJobId(p);
    else setPhase("nojob");
  }, []);

  // load the signed AAR whenever the resolved job id changes
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    setPhase("loading");
    setAar(null);
    setJob(null);
    setTab("cert");
    getCert(Number(jobId))
      .then(async (c) => {
        if (!alive) return;
        setAar(c as unknown as Aar);
        // best-effort enrichment for the governed-decisions ledger + cert id
        try {
          const j = (await getJob(Number(jobId))) as unknown as JobDetail;
          if (alive) setJob(j);
        } catch {
          /* enrichment is optional — the cert renders fine without it */
        }
        if (alive) setPhase("ready");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        const msg = e instanceof Error ? e.message : String(e);
        const status = e instanceof ApiError ? e.status : 0;
        setIs404(status === 404 || /no certificate|404|not found/i.test(msg));
        setErrMsg(msg);
        setPhase("error");
      });
    return () => {
      alive = false;
    };
  }, [jobId]);

  function openJob(v: string) {
    const id = v.trim();
    if (!id) return;
    router.replace(`/certificate?job=${encodeURIComponent(id)}`);
    setJobId(id);
  }

  function downloadJson() {
    if (!aar) return;
    const blob = new Blob([JSON.stringify(aar, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `job-${jobId}.aar.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto max-w-[900px]">
      {/* header / thesis */}
      <div className="mb-[22px] flex flex-wrap items-end justify-between gap-5">
        <div>
          <div className="eyebrow mb-2.5">// SIGNED AAR CERTIFICATE</div>
          <h1 className="m-0 mb-1.5 text-[26px] font-medium tracking-[-0.015em]">
            Proof of refinement
          </h1>
          <p className="m-0 max-w-[560px] text-sm text-muted">
            Every Aegis job ships an Agent Attestation Record — Ed25519-signed, governed by
            Aegis-14B, and{" "}
            <span className="text-teal">checkable by anyone, owned by no vendor</span>.
          </p>
        </div>
        {phase === "ready" && (
          <div className="flex gap-2.5 print:hidden">
            <button
              type="button"
              onClick={downloadJson}
              className="inline-flex items-center justify-center gap-2 rounded-[9px] border border-teal-line px-3.5 py-2 font-mono text-[12px] text-teal transition-colors hover:bg-teal-dim"
            >
              ↓ JSON
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex items-center justify-center gap-2 rounded-[9px] border border-teal-line px-3.5 py-2 font-mono text-[12px] text-teal transition-colors hover:bg-teal-dim"
            >
              ↓ PDF
            </button>
          </div>
        )}
      </div>

      {/* tabs (only meaningful once a cert is loaded) */}
      {phase === "ready" && (
        <div className="mb-[22px] print:hidden">
          <div className="inline-flex gap-1 rounded-[9px] border border-line bg-panel p-1">
            {(
              [
                ["cert", "CERTIFICATE"],
                ["json", "SIGNED JSON"],
                ["verify", "VERIFY"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={[
                  "rounded-[6px] px-[18px] py-[9px] font-mono text-[12px] tracking-[0.04em] transition-all",
                  tab === key ? "bg-teal-dim text-teal" : "text-muted hover:text-text",
                ].join(" ")}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* live region */}
      {(phase === "init" || phase === "loading") && (
        <div className="mx-auto max-w-[700px] rounded-[14px] border border-line bg-panel p-[22px] text-center">
          <Dot />
          <span className="font-mono text-[13px] text-muted">Loading certificate…</span>
        </div>
      )}

      {phase === "nojob" && (
        <div className="mx-auto max-w-[560px] rounded-[14px] border border-line bg-panel p-[22px] text-center">
          <h2 className="m-0 mb-2 text-lg font-semibold">No certificate selected</h2>
          <p className="m-0 mb-[18px] text-[13.5px] leading-[1.6] text-muted">
            Open a certificate by job id — every completed Aegis job has a signed AAR.
          </p>
          <div className="mx-auto flex max-w-[320px] gap-2">
            <input
              value={inputVal}
              onChange={(ev) => setInputVal(ev.target.value)}
              onKeyDown={(ev) => {
                if (ev.key === "Enter") openJob(inputVal);
              }}
              placeholder="job id, e.g. 1"
              inputMode="numeric"
              className="flex-1 rounded-[11px] border border-line-2 bg-panel px-3.5 py-3 text-center text-sm text-text outline-none transition-colors focus:border-teal/60"
            />
            <button
              type="button"
              onClick={() => openJob(inputVal)}
              className="btn-teal whitespace-nowrap rounded-[9px] px-[18px] py-[13px] text-[14.5px]"
            >
              Open →
            </button>
          </div>
          <div className="mt-3.5 font-mono text-[10.5px] text-muted-2">
            <Link href="/dashboard" className="text-teal">
              ← back to dashboard
            </Link>
          </div>
        </div>
      )}

      {phase === "error" && (
        <div className="mx-auto max-w-[560px] rounded-[14px] border border-line bg-panel p-[22px] text-center">
          <div
            className="mx-auto mb-3.5 flex h-[46px] w-[46px] items-center justify-center rounded-full text-[22px]"
            style={{
              background: "rgba(245,158,11,0.1)",
              border: "1px solid rgba(245,158,11,0.4)",
              color: "#F59E0B",
            }}
          >
            !
          </div>
          <h2 className="m-0 mb-2 text-lg font-semibold">
            {is404 ? "No certificate for this job yet" : "Could not load certificate"}
          </h2>
          <p className="m-0 mb-[18px] text-[13.5px] leading-[1.6] text-muted">
            {is404 ? (
              <>
                Job <span className="font-mono">{jobId}</span> hasn&apos;t been completed and signed.
                The certificate is issued when the job finishes.
              </>
            ) : (
              <span className="whitespace-pre-wrap text-red">{errMsg}</span>
            )}
          </p>
          <div className="font-mono text-[11px] text-muted-2">
            <Link href={`/orders/${jobId}`} className="text-teal">
              → view job {jobId}
            </Link>{" "}
            ·{" "}
            <Link href="/dashboard" className="text-teal">
              dashboard
            </Link>
          </div>
        </div>
      )}

      {phase === "ready" && aar && (
        <>
          {tab === "cert" && <CertArtifact aar={aar} job={job} jobId={jobId as string} />}
          {tab === "json" && <SignedJson aar={aar} jobId={jobId as string} />}
          {tab === "verify" && <VerifyPanel jobId={jobId as string} />}
        </>
      )}
    </div>
  );
}
