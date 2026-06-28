"""Parse 'document' formats -> canonical records: YAML, plain TXT, PDF text, Word .docx.

Q&A-shaped inputs (YAML lists of instruction/output, question/answer, conversations, messages,
prompt/completion, ...) reuse the multi-dialect dataset converter — no new guessing. Free text
(TXT / PDF text / DOCX paragraphs) is split into reasonable chunks; each chunk becomes ONE
verbatim-reproduction record so the real document content flows through the same
normalize -> PII-mask -> dedupe -> schema-validate pipeline. No facts are invented.

A SCANNED / image-only PDF (no extractable text) is NOT OCR'd here — we return zero records and
flag needs_ocr=True so the separate, gated OCR phase can pick it up.
"""
import io
import re

from app.curate.canonical import record
from app.curate.parsers.dataset import from_obj

# A free-text chunk becomes a verbatim-reproduction sample: the user turn carries the instruction
# plus the real passage, the assistant turn returns it. This is honest (the assistant answer IS the
# source text — nothing fabricated) and forms a valid 2-turn ShareGPT/ChatML row.
_DOC_INSTRUCTION = "Reproduce the following reference passage verbatim."

_PARA = re.compile(r"\n[ \t]*\n")


def _text_record(chunk: str, source: str = "", extra: dict | None = None):
    chunk = (chunk or "").strip()
    if not chunk:
        return None
    return record(
        [{"role": "user", "content": f"{_DOC_INSTRUCTION}\n\n{chunk}"},
         {"role": "assistant", "content": chunk}],
        source, extra,
    )


def chunk_text(text: str, max_lines: int = 12) -> list[str]:
    """Split free text into reasonable chunks: paragraphs (blank-line separated). If the text has
    no paragraph structure, fall back to N-line windows so long flat text still yields records."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [p.strip() for p in _PARA.split(text) if p.strip()]
    if len(parts) > 1:
        return parts
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return []
    if len(lines) <= max_lines:
        joined = "\n".join(lines).strip()
        return [joined] if joined else []
    return [w for w in ("\n".join(lines[i:i + max_lines]).strip()
                        for i in range(0, len(lines), max_lines)) if w]


def parse_txt(text: str, source: str = "") -> list:
    recs = []
    for i, ch in enumerate(chunk_text(text)):
        r = _text_record(ch, source, {"kind": "document", "format": "txt", "chunk": i})
        if r and r["messages"]:
            recs.append(r)
    return recs


def _yaml_items(data):
    """Normalize a safe_load result into a list of candidate items (handles list / dict / nested)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "rows", "examples", "items", "conversations", "samples"):
            v = data.get(key)
            if isinstance(v, list):
                return v
        return [data]  # a single record-shaped mapping
    return []


def parse_yaml(text: str, source: str = "") -> list:
    import yaml
    try:
        data = yaml.safe_load(text)
    except Exception:
        return []
    recs = []
    for i, item in enumerate(_yaml_items(data)):
        r = None
        if isinstance(item, dict):
            r = from_obj(item, source)  # instruction/output, question/answer, messages, ...
        elif isinstance(item, str):
            r = _text_record(item, source, {"kind": "document", "format": "yaml", "chunk": i})
        if r and r["messages"]:
            recs.append(r)
    return recs


def parse_pdf(data: bytes, source: str = ""):
    """`data` is raw PDF bytes. Returns (records, stats). A scanned / no-text PDF -> needs_ocr."""
    import pdfplumber
    pages_text = []
    n_pages = 0
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            n_pages = len(pdf.pages)
            for page in pdf.pages:
                pages_text.append(page.extract_text() or "")
    except Exception as e:
        return [], {"needs_ocr": False, "parse_error": str(e)[:200], "pages": n_pages}
    full = "\n\n".join(t for t in pages_text if t.strip())
    if not full.strip():
        return [], {"needs_ocr": True, "pages": n_pages}  # image-only / scanned PDF
    recs = []
    for i, ch in enumerate(chunk_text(full)):
        r = _text_record(ch, source, {"kind": "document", "format": "pdf", "chunk": i})
        if r and r["messages"]:
            recs.append(r)
    return recs, {"needs_ocr": False, "pages": n_pages}


def parse_docx(data: bytes, source: str = "") -> list:
    """`data` is raw .docx bytes. Each non-empty paragraph -> one record."""
    import docx
    doc = docx.Document(io.BytesIO(data))
    recs = []
    i = 0
    for para in doc.paragraphs:
        r = _text_record(para.text, source, {"kind": "document", "format": "docx", "chunk": i})
        if r and r["messages"]:
            recs.append(r)
            i += 1
    return recs
