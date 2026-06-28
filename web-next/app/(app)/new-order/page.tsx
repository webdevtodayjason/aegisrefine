"use client";

import { useRef, useState } from "react";
import {
  ApiError,
  createJob,
  quoteRefine,
  quoteSynth,
  signup,
  uploadFile,
  type Quote,
} from "@/lib/api";

// --- constants (ported 1:1 from the static wizard) ---------------------------
const ACCEPT = ".json,.jsonl,.csv,.tsv,.yaml,.yml,.txt,.pdf,.docx";
const MAX_UPLOAD = 50 * 1024 * 1024; // 50 MB client-side guard — bigger files: host + paste a URL
const SERVICE_LABEL: Record<Start, string> = {
  refine: "Clean my data",
  augment: "Expand my data",
  synth: "Generate a dataset",
};

// shared classNames mirroring the static design system (app.css)
const INPUT =
  "w-full rounded-[11px] border border-line-2 bg-panel px-3.5 py-3 text-[14px] text-text outline-none transition-colors focus:border-[rgba(0,229,204,0.6)]";
const LABEL = "font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-2";
const CTA =
  "btn-teal w-full rounded-[9px] px-[18px] py-[13px] text-[14.5px] font-semibold shadow-[0_0_24px_rgba(0,229,204,0.35)]";
const GHOST =
  "mt-2.5 w-full inline-flex items-center justify-center rounded-[9px] border border-teal-line bg-transparent px-[18px] py-[13px] text-[14.5px] font-semibold text-teal transition-colors hover:bg-teal-dim";

// --- local quote shapes (extend the typed Quote with backend-only fields) ----
type Start = "refine" | "augment" | "synth";
type Upload = { handle: string; name: string; size: number };
interface RefineQuoteData extends Quote {
  quoted_usd?: number;
  n_records?: number;
  data_type?: string;
  complexity_scored_by?: string;
}
interface SynthQuoteData extends Quote {
  quote_usd?: number;
  target_kept?: number;
  mode?: string;
}
type QuoteBox =
  | { kind: "idle" }
  | { kind: "loading"; msg: string }
  | { kind: "refine"; q: RefineQuoteData }
  | { kind: "synth"; q: SynthQuoteData }
  | { kind: "human"; q: RefineQuoteData };

function fmtSize(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

// Best-effort detail extraction: the typed client carries the raw response body
// (often `{"detail":"…"}`) on ApiError.message.
function apiErr(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    try {
      const j = JSON.parse(e.message) as { detail?: unknown };
      if (typeof j.detail === "string") return j.detail;
    } catch {
      /* not JSON — fall through */
    }
    return e.message || fallback;
  }
  return e instanceof Error ? e.message : fallback;
}

export default function NewOrderPage() {
  const [purpose, setPurpose] = useState<"ft" | null>(null);
  const [start, setStart] = useState<Start | null>(null);

  // inputs (controlled, mirroring the static fields)
  const [datasetUrl, setDatasetUrl] = useState("");
  const [email, setEmail] = useState("judge@aegisrefine.com");
  const [synthTopic, setSynthTopic] = useState("");
  const [synthRows, setSynthRows] = useState("100");

  // upload
  const [upload, setUpload] = useState<Upload | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // quote / output
  const [quoteBox, setQuoteBox] = useState<QuoteBox>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [redirecting, setRedirecting] = useState(false);

  // in-flow account creation
  const [showAuth, setShowAuth] = useState(false);
  const [suEmail, setSuEmail] = useState("");
  const [suPass, setSuPass] = useState("");
  const [suErr, setSuErr] = useState<string | null>(null);
  const pendingRetry = useRef<null | (() => void)>(null);

  // --- helpers ---------------------------------------------------------------
  function resetQuote() {
    setQuoteBox({ kind: "idle" });
    setError(null);
    setRedirecting(false);
  }

  // reveal the mini-signup; resume the exact action that hit the 401 afterwards
  function needAuth(retry: () => void) {
    pendingRetry.current = retry;
    setSuEmail(email.trim());
    setShowAuth(true);
  }

  function pickPurpose(p: "ft") {
    if (p !== "ft") return; // RAG is coming-soon / not selectable
    setPurpose(p);
  }

  function pickStart(s: Start) {
    setStart(s);
    // switching starting point re-renders fresh fields and clears any pending upload
    setDatasetUrl("");
    setEmail("judge@aegisrefine.com");
    setSynthTopic("");
    setSynthRows("100");
    setUpload(null);
    setUploading(false);
    setUploadErr(null);
    setShowAuth(false);
    resetQuote();
  }

  // validate, then POST the file to /jobs/upload; store the returned {handle}
  async function onFilePick(files: FileList | null) {
    const f = files && files[0];
    if (!f) return;
    const name = f.name.toLowerCase();
    if (!ACCEPT.split(",").some((ext) => name.endsWith(ext))) {
      setUploadErr("Unsupported file type. Use JSON, JSONL, CSV, TSV, YAML, TXT, PDF, or DOCX.");
      return;
    }
    if (f.size > MAX_UPLOAD) {
      setUploadErr("File is over 50 MB — host it and paste an https URL instead.");
      return;
    }
    setUploadErr(null);
    setUploading(true);
    try {
      const d = await uploadFile(f);
      setUpload({ handle: d.handle, name: f.name, size: f.size });
      setUploading(false);
      resetQuote();
    } catch (e) {
      setUploading(false);
      setUpload(null);
      if (e instanceof ApiError && e.status === 401) {
        needAuth(() => onFilePick(files));
        return;
      }
      setUploadErr(apiErr(e, "upload failed — try again"));
    }
  }

  function removeUpload() {
    setUpload(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setUploadErr(null);
    resetQuote();
  }

  // route the shared "Get my quote" button by the chosen starting point
  function onQuote() {
    if (!start) {
      setError("Pick where you're starting (step 2) first.");
      return;
    }
    if (start === "refine") void getQuote();
    else void getSynthQuote();
  }

  // --- card ① CLEAN MY DATA (refine) -----------------------------------------
  async function getQuote() {
    setError(null);
    setShowAuth(false);
    const url = datasetUrl.trim();
    if (!upload && !url) {
      setError("Upload a file or paste an https URL first.");
      return;
    }
    setQuoteBox({ kind: "loading", msg: "Aegis-14B is reading your dataset…" });
    try {
      // uploaded file → carry its handle as the source; otherwise the https URL
      const body = upload
        ? { upload_handle: upload.handle, email: email.trim() }
        : { dataset_url: url, email: email.trim() };
      const q = (await quoteRefine(body)) as RefineQuoteData;
      if (q.requires_human_quote) {
        setQuoteBox({ kind: "human", q });
        return;
      }
      setQuoteBox({ kind: "refine", q });
    } catch (e) {
      setQuoteBox({ kind: "idle" });
      if (e instanceof ApiError && e.status === 401) {
        needAuth(getQuote);
        return;
      }
      setError(apiErr(e, "could not quote that dataset"));
    }
  }

  // --- cards ② EXPAND / ③ GENERATE (synthesis) -------------------------------
  async function getSynthQuote() {
    setError(null);
    setShowAuth(false);
    const topic = synthTopic.trim();
    const rows = parseInt(synthRows, 10);
    // ② augment grounds on the dataset (upload OR URL); ③ generate-from-seed sends no reference
    const reference = start === "augment" ? datasetUrl.trim() : "";
    if (start === "augment" && !upload && !reference) {
      setError("Upload a file or paste the https URL to ground on.");
      return;
    }
    if (!topic) {
      setError(
        start === "augment"
          ? "Describe what the new examples should cover."
          : "Enter a topic / domain to generate.",
      );
      return;
    }
    if (!rows || rows < 1) {
      setError(`Enter how many rows to ${start === "augment" ? "add" : "keep"} (1 or more).`);
      return;
    }
    setQuoteBox({ kind: "loading", msg: "Aegis is pricing your job…" });
    try {
      // augment with an uploaded file carries the handle; otherwise the URL reference
      // (synth sends neither). The backend's synth-quote accepts upload_handle for
      // augment grounding, which the typed client's body shape doesn't yet name.
      const body: { topic: string; target_kept: number; reference?: string; upload_handle?: string } = {
        topic,
        target_kept: rows,
        reference,
      };
      if (start === "augment" && upload) {
        body.upload_handle = upload.handle;
        body.reference = "";
      }
      const q = (await quoteSynth(body as Parameters<typeof quoteSynth>[0])) as SynthQuoteData;
      setQuoteBox({ kind: "synth", q });
    } catch (e) {
      setQuoteBox({ kind: "idle" });
      if (e instanceof ApiError && e.status === 401) {
        needAuth(getSynthQuote);
        return;
      }
      setError(apiErr(e, "could not quote that job"));
    }
  }

  // --- shared accept → Stripe Checkout (all paying paths carry a .token) ------
  async function accept() {
    const q = quoteBox.kind === "refine" || quoteBox.kind === "synth" ? quoteBox.q : null;
    if (!q || !q.token) return;
    setError(null);
    setRedirecting(true);
    try {
      const { checkout_url } = await createJob(q.token);
      window.location.href = checkout_url;
    } catch (e) {
      setRedirecting(false);
      if (e instanceof ApiError && e.status === 401) {
        needAuth(accept);
        return;
      }
      setError(apiErr(e, "could not start checkout"));
    }
  }

  async function doSignup() {
    const em = suEmail.trim();
    const pw = suPass;
    if (!em) {
      setSuErr("Enter your email.");
      return;
    }
    if (!pw) {
      setSuErr("Choose a password.");
      return;
    }
    setSuErr(null);
    try {
      await signup(em, pw);
      setShowAuth(false);
      const retry = pendingRetry.current;
      pendingRetry.current = null;
      retry?.(); // resume the original action, inputs intact
    } catch (e) {
      setSuErr(apiErr(e, "could not create your account"));
    }
  }

  // --- small presentational helpers ------------------------------------------
  const QuoteRow = ({
    k,
    v,
    vClass = "",
    top = false,
  }: {
    k: string;
    v: React.ReactNode;
    vClass?: string;
    top?: boolean;
  }) => (
    <div className={`flex justify-between py-2 text-[13px] ${top ? "border-t border-white/[0.06]" : ""}`}>
      <span className="text-muted">{k}</span>
      <span className={`font-mono ${vClass}`}>{v}</span>
    </div>
  );

  const SyntheticCard = (
    <div className="card rounded-[14px] p-[22px]">
      <div className="mb-1.5 flex items-center gap-[9px]">
        <span className="text-teal">✦</span>
        <span className="text-[15px] font-semibold">Synthetic · labeled · signed</span>
      </div>
      <p className="m-0 text-[13px] text-muted">
        Every generated row is labeled <span className="text-teal">synthetic</span> and ships in the same
        Ed25519-signed certificate, with full provenance — models, candidates, yield, real spend.
      </p>
    </div>
  );

  // drop-zone / chosen-file / uploading states
  const uploadZone = uploading ? (
    <div className="flex cursor-progress flex-col items-center justify-center gap-[7px] rounded-[13px] border border-solid border-teal-line bg-panel-2 px-[18px] py-[26px] text-center">
      <div className="text-[22px] leading-none text-teal">⟳</div>
      <div className="text-[14px] font-semibold text-text">Uploading…</div>
      <div className="font-mono text-[11px] tracking-[0.02em] text-muted-2">securing your file</div>
    </div>
  ) : upload ? (
    <div className="flex items-center justify-between gap-3 rounded-[13px] border border-teal-line bg-teal-dim px-[15px] py-[13px]">
      <div className="flex min-w-0 items-center gap-[11px]">
        <span className="shrink-0 text-[18px] leading-none text-teal">⛁</span>
        <div className="min-w-0">
          <div className="truncate text-[13.5px] font-semibold text-text">{upload.name}</div>
          <div className="mt-0.5 font-mono text-[11px] text-muted-2">{fmtSize(upload.size)} · uploaded</div>
        </div>
      </div>
      <button
        type="button"
        title="Remove file"
        onClick={removeUpload}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-line-2 bg-transparent text-base leading-none text-muted transition-colors hover:border-red hover:text-red"
      >
        ×
      </button>
    </div>
  ) : (
    <div
      onClick={() => fileInputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        void onFilePick(e.dataTransfer.files);
      }}
      className={`flex cursor-pointer flex-col items-center justify-center gap-[7px] rounded-[13px] border-[1.5px] border-dashed bg-panel-2 px-[18px] py-[26px] text-center transition-colors ${
        dragOver
          ? "border-teal bg-teal-dim shadow-[0_0_0_3px_rgba(0,229,204,0.1)]"
          : "border-line-2 hover:border-teal-line hover:bg-teal-dim"
      }`}
    >
      <div className="text-[22px] leading-none text-teal">⤓</div>
      <div className="text-[14px] font-semibold text-text">Drop your file here, or click to choose</div>
      <div className="font-mono text-[11px] tracking-[0.02em] text-muted-2">
        JSON · JSONL · CSV · TSV · YAML · TXT · PDF · DOCX
      </div>
    </div>
  );

  // shared upload block (refine ① / augment ②): drop zone + hidden picker + URL fallback
  const uploadBlock = (label: string, hint: string) => (
    <div>
      <div className={`${LABEL} mb-2.5`}>{label}</div>
      {uploadZone}
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => onFilePick(e.target.files)}
      />
      {uploadErr && <div className="mt-2 whitespace-pre-wrap text-[12.5px] text-red">✗ {uploadErr}</div>}
      <details className="mt-2.5">
        <summary className="inline-flex cursor-pointer select-none items-center gap-1.5 font-mono text-[11px] tracking-[0.04em] text-muted-2 transition-colors hover:text-teal [&::-webkit-details-marker]:hidden">
          or paste an https URL
        </summary>
        <input
          className={`${INPUT} mt-2.5`}
          placeholder="https://…/your-dataset.jsonl"
          value={datasetUrl}
          onChange={(e) => setDatasetUrl(e.target.value)}
        />
      </details>
      {hint && <div className="mt-2 font-mono text-[11px] text-muted-2">{hint}</div>}
    </div>
  );

  // --- render ----------------------------------------------------------------
  return (
    <main className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[1.5fr_1fr]">
      {/* LEFT: intent-first wizard */}
      <div className="flex flex-col gap-[22px]">
        <div>
          <div className="eyebrow mb-2.5 text-teal">// NEW DATASET JOB</div>
          <h1 className="m-0 mb-1.5 text-[26px] font-medium tracking-[-0.015em]">Let&apos;s build your dataset</h1>
          <p className="m-0 text-[14px] text-muted">
            A couple of quick questions — Aegis returns one flat, capped price before anything runs.
          </p>
        </div>

        {/* STEP 1 — what's it for */}
        <div>
          <div className={`${LABEL} mb-3`}>Step 1 · What are you making it for?</div>
          <div className="flex flex-col gap-2.5">
            <button
              type="button"
              onClick={() => pickPurpose("ft")}
              className={`flex w-full cursor-pointer items-center justify-between gap-[14px] rounded-[13px] border px-[18px] py-4 text-left text-text transition-colors ${
                purpose === "ft" ? "border-teal-line bg-teal-dim" : "border-line bg-panel hover:border-line-2"
              }`}
            >
              <div>
                <div className="text-[15px] font-semibold">Fine-tuning a model</div>
                <div className="mt-[3px] text-[13px] text-muted">
                  Instruction → response pairs · ShareGPT / ChatML
                </div>
              </div>
              <span className="inline-block rounded-[5px] border border-[rgba(34,197,94,0.3)] bg-[rgba(34,197,94,0.06)] px-[9px] py-1 font-mono text-[10.5px] tracking-[0.04em] text-green">
                LIVE
              </span>
            </button>
            <div
              aria-disabled="true"
              className="flex w-full cursor-not-allowed items-center justify-between gap-[14px] rounded-[13px] border border-line bg-panel px-[18px] py-4 text-left text-text opacity-[0.55]"
            >
              <div>
                <div className="text-[15px] font-semibold">RAG / retrieval (knowledge chunks)</div>
                <div className="mt-[3px] text-[13px] text-muted">Chunked, embeddable knowledge for retrieval</div>
              </div>
              <span className="inline-block rounded-[5px] border border-line-2 bg-transparent px-[9px] py-1 font-mono text-[10.5px] tracking-[0.04em] text-muted-2">
                COMING SOON
              </span>
            </div>
          </div>
        </div>

        {/* STEP 2 — where you're starting (revealed after step 1) */}
        {purpose === "ft" && (
          <div className="flex flex-col gap-[14px]">
            <div className={LABEL}>Step 2 · Where are you starting?</div>
            <div className="flex flex-col gap-2.5">
              {(
                [
                  ["refine", "①", "Clean my data", "I have data — make it training-ready."],
                  ["augment", "②", "Expand my data", "I have data — generate more high-value examples grounded in it."],
                  ["synth", "③", "Generate a dataset", "I don't have data — generate from a topic."],
                ] as [Start, string, string, string][]
              ).map(([key, ix, title, sub]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => pickStart(key)}
                  className={`flex w-full cursor-pointer items-center justify-between gap-[14px] rounded-[13px] border px-[18px] py-4 text-left text-text transition-colors ${
                    start === key ? "border-teal-line bg-teal-dim" : "border-line bg-panel hover:border-line-2"
                  }`}
                >
                  <div>
                    <div className="text-[15px] font-semibold">
                      <span className="mr-1 font-mono text-teal">{ix}</span> {title}
                    </div>
                    <div className="mt-[3px] text-[13px] text-muted">{sub}</div>
                  </div>
                  <span className="font-mono text-[11px] text-muted-2">{key === "synth" ? "synthesize" : key}</span>
                </button>
              ))}
            </div>

            {/* fields for the chosen starting point */}
            {start && (
              <div className="mt-1.5 flex flex-col gap-[18px]">
                {start === "refine" && (
                  <>
                    {uploadBlock(
                      "Source data",
                      "Discord logs · PDFs · scraped HTML · raw JSON — upload a file or paste a URL",
                    )}
                    <div>
                      <div className={`${LABEL} mb-2.5`}>Customer email</div>
                      <input className={INPUT} value={email} onChange={(e) => setEmail(e.target.value)} />
                    </div>
                  </>
                )}

                {start === "augment" && (
                  <>
                    {uploadBlock(
                      "Source data to ground on",
                      "New examples are generated grounded in this dataset",
                    )}
                    <div>
                      <div className={`${LABEL} mb-2.5`}>What should the new examples cover?</div>
                      <input
                        className={INPUT}
                        placeholder="e.g. harder multi-step variants, edge cases"
                        value={synthTopic}
                        onChange={(e) => setSynthTopic(e.target.value)}
                      />
                    </div>
                    <div>
                      <div className={`${LABEL} mb-2.5`}>Target rows to add</div>
                      <input
                        className={INPUT}
                        type="number"
                        min={1}
                        step={1}
                        value={synthRows}
                        onChange={(e) => setSynthRows(e.target.value)}
                      />
                      <div className="mt-2 font-mono text-[11px] text-muted-2">
                        Aegis over-generates, then keeps only rows that pass the Δ-filter
                      </div>
                    </div>
                    {SyntheticCard}
                  </>
                )}

                {start === "synth" && (
                  <>
                    <div>
                      <div className={`${LABEL} mb-2.5`}>Topic / domain</div>
                      <input
                        className={INPUT}
                        placeholder="e.g. multi-step algebra word problems"
                        value={synthTopic}
                        onChange={(e) => setSynthTopic(e.target.value)}
                      />
                      <div className="mt-2 font-mono text-[11px] text-muted-2">
                        What kind of high-value examples Aegis should generate
                      </div>
                    </div>
                    <div>
                      <div className={`${LABEL} mb-2.5`}>Target rows to keep</div>
                      <input
                        className={INPUT}
                        type="number"
                        min={1}
                        step={1}
                        value={synthRows}
                        onChange={(e) => setSynthRows(e.target.value)}
                      />
                      <div className="mt-2 font-mono text-[11px] text-muted-2">
                        Aegis over-generates, then keeps only rows that pass the Δ-filter (strong-solves ∧ weak-fails)
                      </div>
                    </div>
                    {SyntheticCard}
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* RIGHT: summary (sticky) */}
      <div className="flex flex-col gap-[18px] self-start lg:sticky lg:top-[90px]">
        <div className="card rounded-[14px] p-[22px]">
          <h2 className="m-0 mb-1.5 text-[16px] font-semibold">Your quote</h2>
          <p className="m-0 mb-4 text-[12.5px] text-muted">
            Aegis-14B returns ONE flat, capped price before anything runs. No surprise bills.
          </p>

          {/* quoteBox */}
          {quoteBox.kind === "idle" && (
            <>
              <button className={CTA} onClick={onQuote}>
                Get my quote →
              </button>
              <div className="mt-3 flex items-center justify-center gap-[7px] font-mono text-[10px] text-muted-2">
                <span className="text-teal">⛉</span> No charge to quote · 15-min hold · Secured by Stripe
              </div>
            </>
          )}

          {quoteBox.kind === "loading" && <p className="m-0 text-[12.5px] text-muted">{quoteBox.msg}</p>}

          {quoteBox.kind === "human" && (
            <div className="px-0 py-2 text-center">
              <div className="font-mono text-[28px] font-bold text-amber">
                ${(quoteBox.q.quoted_usd ?? 0).toLocaleString()}
              </div>
              <p className="m-0 mt-2 text-[12.5px] text-muted">
                Large job — a human confirms the price before anything runs.
              </p>
            </div>
          )}

          {quoteBox.kind === "refine" && (
            <>
              <div className="px-0 pb-3 pt-1 text-center">
                <div className="font-mono text-[42px] font-bold tracking-[-0.02em] text-teal">
                  ${(quoteBox.q.quoted_usd ?? 0).toFixed(2)}
                </div>
                <div className="mt-0.5 font-mono text-[10px] text-muted-2">FLAT · CAPPED · NO SURPRISES</div>
              </div>
              <QuoteRow k="Service" v="Clean my data" vClass="text-teal" top />
              <QuoteRow k="Records detected" v={(quoteBox.q.n_records ?? 0).toLocaleString()} />
              <QuoteRow k="Format in" v={quoteBox.q.data_type ?? ""} />
              <QuoteRow k="Priced by" v={quoteBox.q.complexity_scored_by ?? ""} vClass="text-green" />
              <p className="my-2.5 mb-4 text-[12px] text-muted">
                The most you&apos;ll ever pay. We run on our own GPUs first and eat any overage — you won&apos;t.
              </p>
              <button className={CTA} onClick={accept}>
                Accept &amp; pay ${(quoteBox.q.quoted_usd ?? 0).toFixed(2)} →
              </button>
              <button className={GHOST} onClick={onQuote}>
                Re-quote
              </button>
            </>
          )}

          {quoteBox.kind === "synth" && (
            <>
              <div className="px-0 pb-3 pt-1 text-center">
                <div className="font-mono text-[42px] font-bold tracking-[-0.02em] text-teal">
                  ${(Number(quoteBox.q.quote_usd) || 0).toFixed(2)}
                </div>
                <div className="mt-0.5 font-mono text-[10px] text-muted-2">FLAT · CAPPED · NO SURPRISES</div>
              </div>
              <QuoteRow
                k="Service"
                v={start ? SERVICE_LABEL[start] : "Synthesis"}
                vClass="text-teal"
                top
              />
              <QuoteRow k="Target rows" v={(Number(quoteBox.q.target_kept) || 0).toLocaleString()} />
              <QuoteRow
                k="Mode"
                v={quoteBox.q.mode ?? (start === "augment" ? "augment" : "from-seed")}
                vClass="text-green"
              />
              <p className="my-2.5 mb-3.5 text-[12px] text-muted">
                Every row labeled <span className="text-teal">synthetic</span> · signed provenance. The most
                you&apos;ll ever pay — we eat any overage.
              </p>
              <div className="mb-4 flex items-start gap-[9px] rounded-[10px] border border-teal-line bg-teal-dim px-[13px] py-[11px]">
                <span className="text-[13px] leading-[1.3] text-teal">⏳</span>
                <span className="text-[12px] leading-[1.45] text-muted">
                  Synthesis runs <span className="text-teal">~25–30&nbsp;min</span> as a background job — close
                  this and we&apos;ll email you when it&apos;s ready.
                </span>
              </div>
              <button className={CTA} onClick={accept}>
                Accept &amp; pay ${(Number(quoteBox.q.quote_usd) || 0).toFixed(2)} →
              </button>
              <button className={GHOST} onClick={onQuote}>
                Re-quote
              </button>
            </>
          )}

          {/* out: errors, redirect notice, and in-flow account creation */}
          {error && <div className="mt-3 whitespace-pre-wrap text-[12.5px] text-red">✗ {error}</div>}
          {redirecting && (
            <p className="mt-3.5 text-[12.5px] text-muted">
              Redirecting to Stripe (test card 4242 4242 4242 4242)…
            </p>
          )}
          {showAuth && (
            <div className="card mt-3.5 rounded-[14px] border-teal-line bg-gradient-to-b from-[rgba(0,229,204,0.05)] to-panel p-[22px]">
              <div className={`${LABEL} mb-2`}>Create your account to continue</div>
              <p className="m-0 mb-3.5 text-[12.5px] text-muted">
                You&apos;re not signed in yet — create an account and we&apos;ll pick up right where you left off.
                Your inputs are saved.
              </p>
              <div className="flex flex-col gap-2.5">
                <input
                  className={INPUT}
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  value={suEmail}
                  onChange={(e) => setSuEmail(e.target.value)}
                />
                <input
                  className={INPUT}
                  type="password"
                  placeholder="Choose a password"
                  autoComplete="new-password"
                  value={suPass}
                  onChange={(e) => setSuPass(e.target.value)}
                />
              </div>
              <button className={`${CTA} mt-3`} onClick={doSignup}>
                Create account &amp; continue →
              </button>
              {suErr && <div className="mt-2 whitespace-pre-wrap text-[12.5px] text-red">✗ {suErr}</div>}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
