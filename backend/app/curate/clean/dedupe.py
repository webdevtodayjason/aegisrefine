"""Exact dedupe on the canonical content hash. (MinHash/LSH near-dup is a v2 upgrade.)"""
from app.curate.canonical import content_key


def dedupe(records):
    seen = set()
    out = []
    removed = 0
    for r in records:
        k = content_key(r)
        if k in seen:
            removed += 1
            continue
        seen.add(k)
        out.append(r)
    return out, removed
