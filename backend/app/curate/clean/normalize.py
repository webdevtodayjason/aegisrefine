"""Deterministic text normalization: unicode, whitespace, strip baked-in chat markers."""
import re
import unicodedata

# ponytail: stdlib regex covers the common markers; ftfy/full mojibake repair is a v2 upgrade.
_MARKERS = re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>|\[/?INST\]|<<SYS>>|<</SYS>>", re.I)
_HEADING = re.compile(r"^#{1,6}[ \t]+", re.M)
_WS = re.compile(r"[ \t]+")
_NL = re.compile(r"\n{3,}")


def normalize_text(t: str) -> str:
    if not t:
        return ""
    t = unicodedata.normalize("NFC", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = _MARKERS.sub("", t)
    t = _HEADING.sub("", t)
    t = _WS.sub(" ", t)
    t = _NL.sub("\n\n", t)
    return t.strip()


def normalize_record(rec: dict) -> dict:
    msgs = [{"role": m["role"], "content": normalize_text(m["content"])} for m in rec["messages"]]
    rec["messages"] = [m for m in msgs if m["content"]]
    return rec
