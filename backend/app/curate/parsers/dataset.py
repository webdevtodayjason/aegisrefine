"""Parse existing dataset dialects -> canonical. (Scenario #6: highest local-reliability.)

Handles ShareGPT (conversations/from-value), ChatML (messages), Alpaca (instruction/input/output),
prompt/completion, and question/answer. Unknown shapes are skipped, never guessed.
"""
import json
from app.curate.canonical import record


def from_obj(obj, source=""):
    if not isinstance(obj, dict):
        return None
    if "conversations" in obj and isinstance(obj["conversations"], list):
        return record([{"role": c.get("from"), "content": c.get("value")} for c in obj["conversations"]], source)
    if "messages" in obj and isinstance(obj["messages"], list):
        return record(obj["messages"], source)
    if "instruction" in obj and "output" in obj:
        instr = obj["instruction"] + (("\n\n" + obj["input"]) if obj.get("input") else "")
        return record([{"role": "user", "content": instr}, {"role": "assistant", "content": obj["output"]}], source)
    if "prompt" in obj and "completion" in obj:
        return record([{"role": "user", "content": obj["prompt"]}, {"role": "assistant", "content": obj["completion"]}], source)
    if "question" in obj and "answer" in obj:
        return record([{"role": "user", "content": obj["question"]}, {"role": "assistant", "content": obj["answer"]}], source)
    return None


def parse_jsonl(text, source=""):
    recs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        r = from_obj(obj, source)
        if r and r["messages"]:
            recs.append(r)
    return recs


def parse_json(text, source=""):
    try:
        data = json.loads(text)
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("data") or data.get("conversations") or data.get("rows") or [data]
    recs = []
    for obj in data if isinstance(data, list) else []:
        r = from_obj(obj, source)
        if r and r["messages"]:
            recs.append(r)
    return recs
