"""Orchestrate a real curation run: read -> detect -> parse -> normalize -> mask -> dedupe ->
validate -> emit ShareGPT+ChatML, with real stats. The only entry point refinery.py calls.
"""
import os
import json
import hashlib
import tempfile
import urllib.request

from app.curate import detect as _detect
from app.curate.parsers import dataset as _ds, tabular as _tab, documents as _docs
from app.curate.clean.normalize import normalize_record
from app.curate.clean.pii import mask_record, residual_count
from app.curate.clean.dedupe import dedupe
from app.curate.format import valid_record, write_jsonl
from app.curate.stats import Stats
from app.services import storage


def _read_bytes(source: str) -> bytes:
    """Read the raw source bytes. A source is ONE of: an R2 key (starts with 'users/', read via
    storage when R2 is configured), an https URL, or a local filesystem path."""
    if source.startswith("users/") and storage.enabled():
        return storage.get_bytes(source)
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as r:
            return r.read()
    with open(source, "rb") as f:
        return f.read()


def run(source: str, out_dir: str | None = None) -> dict:
    raw = _read_bytes(source)
    fmt = _detect.detect(source, raw[:512])
    extra: dict = {}
    if fmt == "pdf":                                   # binary -> keep raw bytes
        recs, extra = _docs.parse_pdf(raw, source)
    elif fmt == "docx":                                # binary -> keep raw bytes
        recs = _docs.parse_docx(raw, source)
    else:                                              # text formats -> decode utf-8
        text = raw.decode("utf-8", "replace")
        if fmt == "json":
            recs = _ds.parse_json(text, source)
        elif fmt in ("csv", "tsv"):
            recs = _tab.parse_csv(text, source, "\t" if fmt == "tsv" else ",")
        elif fmt == "yaml":
            recs = _docs.parse_yaml(text, source)
        elif fmt == "txt":
            recs = _docs.parse_txt(text, source)
        else:
            recs = _ds.parse_jsonl(text, source)

    st = Stats(rows_in=len(recs))
    recs = [normalize_record(r) for r in recs]
    for r in recs:
        _, c = mask_record(r)
        st.pii_masked += c
    recs, st.dupes_removed = dedupe(recs)
    good = [r for r in recs if valid_record(r)]
    st.dropped_invalid = len(recs) - len(good)
    st.rows_out = len(good)

    out_dir = out_dir or tempfile.mkdtemp(prefix="aegis-curate-")
    os.makedirs(out_dir, exist_ok=True)
    sg_path = os.path.join(out_dir, "dataset.sharegpt.jsonl")
    cm_path = os.path.join(out_dir, "dataset.chatml.jsonl")
    write_jsonl(good, sg_path, "sharegpt")
    write_jsonl(good, cm_path, "chatml")

    stats = st.as_dict()
    if extra:                       # e.g. {"needs_ocr": True, "pages": N} from a scanned PDF
        stats.update(extra)
    return {
        "format_in": fmt,
        "output_path": sg_path,
        "chatml_path": cm_path,
        "output_sha256": _sha256_file(sg_path),
        "stats": stats,
        "records": good,
        "needs_ocr": bool(extra.get("needs_ocr")),
    }


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --- re-checkable guarantees (the verifier re-runs these on the delivered file) ---

def verify_output(path: str) -> dict:
    """Re-run the property checks on a produced file. This is what turns the cert into a
    guarantee: anyone can re-run it and get the same answers."""
    lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if ln.strip()]
    text = "\n".join(lines)
    pii = residual_count(text)
    schema_ok = True
    seen = set()
    dupes = 0
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            schema_ok = False
            continue
        convs = obj.get("conversations") or obj.get("messages")
        if not convs or len(convs) < 2:
            schema_ok = False
        key = hashlib.sha256(ln.encode("utf-8")).hexdigest()
        if key in seen:
            dupes += 1
        seen.add(key)
    return {
        "rows": len(lines),
        "pii_residual": pii,
        "dupes_residual": dupes,
        "schema_valid": schema_ok,
        "ok": pii == 0 and dupes == 0 and schema_ok and len(lines) > 0,
    }
