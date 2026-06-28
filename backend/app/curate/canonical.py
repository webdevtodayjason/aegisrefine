"""The one schema everything lands in before cleaning: {messages:[{role,content}], meta:{}}."""
import hashlib

ROLE_MAP = {
    "human": "user", "user": "user", "prompt": "user", "question": "user",
    "instruction": "user", "q": "user",
    "gpt": "assistant", "assistant": "assistant", "completion": "assistant",
    "answer": "assistant", "response": "assistant", "output": "assistant", "a": "assistant",
    "system": "system",
}


def norm_role(r) -> str:
    return ROLE_MAP.get(str(r).strip().lower(), "user")


def record(messages, source="", extra=None) -> dict:
    msgs = []
    for m in messages or []:
        content = (m.get("content") or "").strip()
        if content:
            msgs.append({"role": norm_role(m.get("role")), "content": content})
    meta = {"source": source}
    if extra:
        meta.update(extra)
    return {"messages": msgs, "meta": meta}


def content_key(rec: dict) -> str:
    """sha256 over normalized message contents — exact-dedupe key."""
    blob = "\n".join(f"{m['role']}:{m['content']}" for m in rec["messages"])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
