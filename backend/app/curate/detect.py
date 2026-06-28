"""Format detection: extension first, content sniff as fallback."""
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
    s = head.lstrip()[:1]
    if s in (b"[",):
        return "json"
    if s in (b"{",):
        # one object per line -> jsonl; a single big object -> json. Sniff a newline+brace.
        return "jsonl" if head.count(b"\n{") or head.count(b"}\n{") else "json"
    return "jsonl"
