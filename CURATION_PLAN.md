# Aegis Curation Engine — Product + Build Plan (Honest Edition)

> Closes the one real gap: today the signed certificate covers **client-supplied** bytes
> (`complete_job(output)` in `routers/refinery.py`). This plan builds the real curation
> engine so the certificate covers bytes **Aegis actually produced** — and can be
> **re-verified**, not just trusted.

---

## 0. North Star — what actually makes us different

We are **not** "another data cleaner." Dedup + PII-strip + format is commodity (a script or a
GPT prompt does it). Our defensible value is the **trust layer**, and it only counts if it's
*real*:

1. **Re-checkable guarantees, not a signed PDF.** A signature alone proves only *who* made the
   file and that it's *unchanged* — not that the work was done right. It becomes a **guarantee**
   only when its claims are **independently re-runnable against the delivered file**, and the
   public verifier **re-executes them**:
   - `PII = 0` → re-scan the output, find zero emails/phones/SSNs/cards/secrets.
   - `deduped` → re-run dedup, nothing collapses.
   - `schema-valid` → re-run the ShareGPT/ChatML validator, it passes.
   - `derived from YOUR input` → input-hash → output-hash lineage.
   - `every paid step human-approved` → the gated audit trail.
   "Trust us" → **"verify it yourself in 30 seconds."** The signature just makes the report
   tamper-evident. **The guarantee is the re-runnable checks.** (See §6.)

2. **PII-safety is the killer feature, not the cleaning.** The buyer who pays is the one who
   *can't* dump raw data into a fine-tune or a RAG because it would leak salaries / customer PII /
   secrets. "Provably safe to put in production" is the product.

3. **Fine-tune OR RAG.** Same engine, two output modes: ShareGPT/ChatML JSONL (fine-tune) **and**
   clean, PII-masked, metadata-tagged chunks (RAG/vector-DB). The DB→RAG job is a first-class
   customer, not an afterthought.

**One-liner:** *Aegis turns your messy data into clean, PII-safe ShareGPT/ChatML or RAG-ready
datasets on private hardware — and hands you a certificate you can re-verify proving exactly
what's in it and what isn't.*

Honest status: items 2–3 need building (§3–§4); item 1's re-verification is the §6 upgrade. The
signature without these = theater. With them = a real, defensible difference.

---

## 1. The promise, made honest

**"Give us your data, no matter what — we'll take care of it"** is true when "take care of it"
is one of three honest outcomes, and every input is **tagged before any claim is made**:

1. **`local-reliable`** — deterministic Python cleans it (parse, normalize, dedupe, PII-mask,
   format) free + locally; Aegis-14B judges the result in JSON. The default for most uploads.
2. **`needs-gated-tool`** — meaning is locked in a binary the local stack can't read (scanned
   PDF, voice note, JS/anti-bot-walled page). The pipeline **detects** it, Aegis's `spend` job
   proposes a costed `SpendTicket`, and a **human approves before any money or API call moves**.
   Nothing faked, nothing silently dropped.
3. **`out-of-scope`** — instruction **synthesis from question-less prose** is *generation*, which
   Aegis was trained NOT to do. We template from data that already contains the Q, gate it to a
   separate generation model, or honestly decline. **Aegis never writes training text.**

The promise holds because the system **never returns invented data**: every output row is a
deterministic render of a real source row, masked + validated; every hard input is gated (with
the human's OK) or quarantined with a reason. The signed AAR records exactly how many rows went
in, came out, were masked, dropped, gated — so "we took care of it" is a **provable number.**

**Honesty tripwires (must hold in code):**
- Aegis-14B is **judge/governor only** (strict JSON: triage/quality/spend/audit). Output bytes
  come from `curate/format.py`, **never** the model. Never pipe model text into `complete_job`.
- Local OCR (Tesseract) on skewed/handwritten scans **poisons** datasets → bad scans go to the
  **gate**, not to Tesseract-and-hope.
- Keep the system prompt literal `"Aegis-7B"` (deployed weights were trained on it).

---

## 2. What you can bring (intake matrix)

| Data type | How you collect it | Formats | What we do | Output | Honesty |
|---|---|---|---|---|---|
| **Existing datasets** (HF dumps, mixed-schema JSONL, prior SFT) | `datasets.to_json` / `snapshot_download` / copy `*.jsonl` | `.jsonl/.json/.parquet/.csv/.tsv/.gz` | schema-map dialects → normalize → dedupe + eval-decontam → PII/secret mask → re-serialize | ShareGPT + ChatML | **local-reliable** |
| **Tabular / DB** (CSV, JSON, xlsx, **DB dumps**) | `pg_dump`/`mysqldump`/`\copy`, Sheets, xlsx + data dictionary | `.csv/.tsv/.json/.xlsx`, SQL dump, parquet | sniff+parse → type/null normalize → dedupe → PII-mask → deterministic Jinja column→role templating | ShareGPT/ChatML **or RAG chunks** | **local-reliable** |
| **Q&A / KB / docs** | Zendesk/Intercom API, Notion export, `git clone` docs | article JSON, `.md/.mdx`, forum JSON, HTML | HTML/MD→text → segment (Q→accepted-answer) → dedupe → PII-mask → template | ShareGPT/ChatML **or RAG chunks** | **local-reliable** (image-only → gated) |
| **Chat / support exports** | DiscordChatExporter, Slack ZIP, WhatsApp `.txt`, Zendesk API | Slack/Discord JSON, WhatsApp `.txt`, support JSON, mbox | parse→event log → strip noise → segment → role-map → dedupe → PII-mask → format | conversational ShareGPT/ChatML | **local-reliable** (voice/image → gated) |
| **Web / forums / articles** | Discourse/SE/Reddit/GitHub APIs first; else sitemap + trafilatura | HTML, WARC, forum JSON, RSS, MD | main-content extract → normalize → lang filter → dedupe → PII/secret mask → quality filter → pair-build | ShareGPT/ChatML + license meta | **local-reliable** (JS/anti-bot → gated) |
| **Documents** (PDF/Word/PPT; **scanned**) | SharePoint/Drive/NAS pull, scan room | born-digital PDF, `.docx/.pptx/.xlsx`, **scanned PDF/.tif/.jpg** | fingerprint → text-layer probe → born-digital parse/clean/format; **scanned → OCR gate** | ShareGPT/ChatML or RAG chunks | **needs-gated-tool** (scanned set) |

---

## 3. The curation engine architecture

### New package: `backend/app/curate/`
```
curate/
  engine.py          # orchestrates a run; the only thing refinery.py calls
  detect.py          # MIME/format detection (extension + python-magic + content sniff)
  canonical.py       # unified record {messages:[{role,content}], meta:{source,license,sha}}
  parsers/
    dataset.py       #  jsonl/json/parquet + dialect map (vicuna/chatml/alpaca/prompt-completion)
    tabular.py       #  csv/tsv/xlsx/sql-dump -> rows -> Jinja templating
    qa_docs.py       #  html/md/notion/forum-json -> Q/A pairs            (v2)
    chat.py          #  slack/discord/whatsapp/support -> segments        (v2)
    web.py           #  trafilatura + forum walkers                       (v2)
    documents.py     #  pymupdf/docx/pptx + text-layer probe              (v2)
  clean/
    normalize.py     # ftfy, NFC, whitespace, un-template (<|im_start|>/[INST]/###), de-boilerplate
    dedupe.py        # exact sha256 + near-dup MinHash/LSH + n-gram eval-decontam
    pii.py           # regex (email/phone/card/SSN/IP/keys) + Presidio NER + detect-secrets -> typed placeholders
  format.py          # ShareGPT + ChatML + RAG-chunk emitters; schema-validate every line
  stats.py           # REAL counts: rows_in/out, dropped_by_reason{}, pii_masked, dupes_removed, noise_reduced_pct
  gated/
    base.py          # SpendTicket-gated adapter contract: never called until status=='approved'
    ocr.py / asr.py / unblock.py   # Textract / Whisper / Bright Data    (v2)
```

### Data flow
```
detect -> parsers/<type> -> canonical records
   -> clean/normalize -> clean/dedupe -> clean/pii      (DETERMINISTIC, free, local)
   -> agent.decide("triage"/"quality")                  (AEGIS-14B: JSON keep/drop/route/format)
   -> format (ShareGPT/ChatML/RAG, schema-validated)
   -> stats (real in/out numbers)
```

### Aegis-14B plug-in points (unchanged client, `services/agent.py`)
- **triage** per shard → `{complexity,risk,noise_level,can_run_locally}`; `can_run_locally=false` **fires the gate**.
- **quality** per candidate → `{quality_score,issues,recommended_format,...}`; deterministic code executes keep/drop, Aegis only decides + picks ShareGPT-vs-ChatML.
- **spend** when local can't → `{tool,reason,est_cost_usd,...}` → existing `spend_service.create_spend_ticket`.
- **audit** roll-up → folded into the AAR claim.

### Wire-in (two surgical edits, no new endpoints for MVP)
1. `refinery.process_job`: after triage/quality, `result = engine.run(job.input_file_path, sample)` → write **real** JSONL → `job.output_file_path`, `summary["stats"]=result.stats`.
2. `refinery.complete_job`: read the engine's **real output bytes** (not client-supplied); `CompleteRequest.output` becomes ignored. `aar_service` already hashes the real output into `response_sha256`, so the cert + "noise reduced" number become **true automatically.**

---

## 4. Phased build plan

### MVP — demo-ready before EOD Tue 2026-06-30 (a few hours)
Make the promise TRUE end-to-end on the highest-reliability path: **existing messy datasets (#6)**
+ **tabular/DB (#4)** sharing the formatter. Build only: `detect.py`, `parsers/dataset.py`,
`parsers/tabular.py`, `clean/{normalize,dedupe,pii}.py` (regex+detect-secrets; Presidio if time),
`format.py` (ShareGPT+ChatML+validate), `stats.py`, `engine.run()` + the two `refinery.py` edits.
Gated path **wired but stubbed** (the `hard_doc` branch already proposes a real `SpendTicket`).

**Demo spine:** upload a real zoo of mixed-schema JSONL → `process` → live Aegis JSON triage/quality
on screen → engine emits clean ShareGPT+ChatML with a real `rows_in→rows_out, % noise removed` →
`complete` → signed L2 AAR over the **actual** output → public verifier passes (and re-checks PII=0,
§6). Then a scanned-PDF upload → triage `can_run_locally=false` → Aegis `spend` proposes a costed
ticket → **human approves on camera** (gate real even though the OCR vendor is stubbed for the cut).

### v2 / later (each a few hours unless noted)
qa_docs (#2) · chat parsers (#1, Slack/support first; full multi-party segmentation bigger) ·
web (#5) · documents born-digital (#3) + scanned text-layer probe · real gated vendors
(ocr/asr/unblock behind the approved ticket; needs API keys) · MinHash near-dup + eval-decontam
+ Presidio everywhere · RAG-chunk output mode polish.
**Out-of-scope (explicit):** prose→instruction *synthesis* = generation → a separate model behind
its own gate, **never** Aegis-14B.

---

## 5. Buyer questions, answered true

- **What can I bring?** Anything in the matrix — datasets, tables/DB dumps, KB/docs, chat/support
  exports, web/forum, documents. Hard binaries (scans, voice, walled pages) accepted too: we detect
  them and quote a small, human-approved tool cost first. We never invent data; we tell you up front
  which files are free-local, gated, or out-of-scope.
- **Does format matter?** No. Detection routes each file to a parser; everything lands in one
  canonical schema before cleaning. Mixed schemas inside one file is the normal case.
- **How do you curate it?** Deterministic local code does the mechanical work for free on our GPU
  box; Aegis-14B (our fine-tuned governor) **judges** each batch in JSON and **decides** when a paid
  tool is genuinely needed; it never rewrites your text. A human approves any spend.
- **What do I get back?** Clean ShareGPT/ChatML (or RAG chunks) your trainer accepts first run —
  deduped, PII-masked, schema-valid, with source/license provenance — **plus a re-verifiable signed
  certificate** stating exactly how many rows went in, out, masked, dropped, gated.
- **Is it easy?** Pay once, drop a folder or hand us a URL/token; we run it and return the clean
  corpus + the certificate. The only mid-job touch is a one-click approval **if** a paid tool is
  needed — with the exact dollar amount shown first.

---

## 6. Make the proof a real guarantee (the verifier upgrade)

The single thing that lifts the cert from "signed paper" to "guarantee": the public verifier must
**re-run the property checks on the delivered output**, not just check the signature.

- `aar_service` already commits `response_sha256` (output hash) + an evidence block. **Add** a
  committed `checks[]` of machine-re-runnable assertions: `pii_residual=0` (re-scan), `dupes=0`
  (re-run dedup), `schema=valid` (re-run validator), `input_sha256` (lineage).
- Extend the verifier (`aar.mjs verify` / the `/jobs/{id}/verify` badge) to **re-execute** those
  checks against the output file and pass only if they still hold. Then the L2 badge means
  "independently re-verified," not "we attested."
- **This is the moat made literal.** Budget: a few hours on top of the MVP; do it right after the
  engine produces real bytes (otherwise there's nothing true to re-check).

---

*Honesty risks (load-bearing): (1) `complete_job` MUST switch to engine bytes or the cert is
meaningless — the one MVP edit that matters. (2) Never route Aegis output text into the formatter.
(3) Bad scans go to the gate, not Tesseract. (4) Keep the `"Aegis-7B"` system prompt literal.
(5) Prose→instruction synthesis stays out-of-scope (generation), not bolted onto Aegis.*
