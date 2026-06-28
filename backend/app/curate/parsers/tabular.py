"""Parse CSV/TSV/DB-export rows -> canonical. (Scenario #4.)

MVP maps only when a question-ish and answer-ish column are present — we don't guess wild
column->role mappings (a confirmed column map is the v2 upgrade). Honest over clever.
"""
import csv
import io
from app.curate.canonical import record

_Q = {"question", "prompt", "instruction", "input", "query", "title", "issue"}
_A = {"answer", "response", "output", "completion", "reply", "body", "resolution", "solution"}


def parse_csv(text, source="", delimiter=","):
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []
    headers = rows[0].keys()
    q_col = next((h for h in headers if h and h.lower() in _Q), None)
    a_col = next((h for h in headers if h and h.lower() in _A), None)
    if not (q_col and a_col):
        return []  # no defensible mapping -> nothing, rather than garbage
    recs = []
    for row in rows:
        recs.append(record([{"role": "user", "content": row.get(q_col, "")},
                            {"role": "assistant", "content": row.get(a_col, "")}], source))
    return recs
