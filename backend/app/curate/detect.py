"""Format detection: extension first, content sniff as fallback.

Recognizes the dataset dialects (jsonl/json/csv/tsv) plus the document formats
(yaml/txt/pdf/docx). The historical fallback for unknown text stays "jsonl" so the
existing https-URL refine flow is never re-routed.
"""
from pathlib import Path


def detect(source: str, head: bytes = b"") -> str:
    ext = Path(source.split("?")[0]).suffix.lower()
    if ext in (".jsonl", ".ndjson"):
        return "jsonl"
    if ext == ".json":
        return "json"
    if ext == ".csv":
        return "csv"
    if ext == ".tsv":
        return "tsv"
    if ext in (".yaml", ".yml"):
        return "yaml"
    if ext in (".txt", ".text"):
        return "txt"
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"

    # --- content sniff (no/unknown extension) ---
    if head[:4] == b"%PDF":                       # PDF magic
        return "pdf"
    if head[:4] == b"PK\x03\x04":                 # zip container -> the only OOXML we parse is .docx
        return "docx"
    s = head.lstrip()
    if s[:3] == b"---" or s[:5] == b"%YAML":       # YAML document marker / directive
        return "yaml"
    first = s[:1]
    if first in (b"[",):
        return "json"
    if first in (b"{",):
        # one object per line -> jsonl; a single big object -> json. Sniff a newline+brace.
        return "jsonl" if head.count(b"\n{") or head.count(b"}\n{") else "json"
    return "jsonl"
