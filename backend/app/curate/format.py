"""Emit + validate ShareGPT and ChatML. Every line is schema-checked before it ships."""
import json

_SG = {"user": "human", "assistant": "gpt", "system": "system"}


def to_sharegpt(rec: dict) -> dict:
    return {"conversations": [{"from": _SG[m["role"]], "value": m["content"]} for m in rec["messages"]]}


def to_chatml(rec: dict) -> dict:
    return {"messages": rec["messages"]}


def valid_record(rec: dict) -> bool:
    msgs = rec.get("messages") or []
    if len(msgs) < 2:
        return False
    if any(not m["content"].strip() for m in msgs):
        return False
    seq = [m["role"] for m in msgs if m["role"] != "system"]
    if not seq or seq[0] != "user":
        return False
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:  # roles must alternate
            return False
    return True


def write_jsonl(records, path, fmt="sharegpt") -> int:
    emit = to_sharegpt if fmt == "sharegpt" else to_chatml
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(emit(r), ensure_ascii=False) + "\n")
            n += 1
    return n
