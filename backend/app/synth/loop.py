"""The Agentic Self-Instruct loop (AutoData Tier-A). Pure-ish: model calls go through `_call`,
which is injectable so tests run with no real spend. Budget is tracked + capped here; the caller
records the aggregate spend on the ledger and signs the cert."""
import json

from app.services import escalation
from app.curate.clean.pii import mask_text
from app.curate.canonical import record

# Default roles — verified-working paid arsenal models; all overridable per job.
# weak must be genuinely weaker than strong for Delta to mean something.
ROLES = {"challenger": "glm-4.6", "weak": "MiniMax-M2", "strong": "glm-4.6", "judge": "MiniMax-M2"}

MAX_ROUNDS = 20


def _ask(messages, model, max_tokens=400, _call=None):
    """One model call -> (text, cost_usd). Returns ('', 0.0) if no provider key."""
    if _call is not None:
        return _call(messages, model)
    r = escalation.escalate(messages, model=model, max_tokens=max_tokens)
    return (r["text"], r["cost_usd"]) if r else ("", 0.0)


def _correct(task, answer, judge_model, _call=None):
    """Judge: is `answer` correct+complete for `task`? -> (1|0, cost)."""
    msg = [{"role": "user", "content":
            f"Task:\n{task}\n\nProposed answer:\n{answer}\n\n"
            "Is the answer correct AND complete for the task? Reply exactly YES or NO."}]
    text, cost = _ask(msg, judge_model, max_tokens=5, _call=_call)
    return (1 if text and text.strip().upper().startswith("Y") else 0), cost


def synthesize(*, topic, target_kept=10, reference="", roles=None, batch=4,
               cap_usd=1.0, _call=None) -> dict:
    """Run the Challenger->solve->judge->Delta loop until target_kept high-value examples are
    collected or the budget cap is hit. Returns kept (labeled-synthetic canonical records) + the
    provenance stats (candidates, kept, yield, spend, per-model cost)."""
    roles = {**ROLES, **(roles or {})}
    kept, candidates, rounds = [], 0, 0
    spent = 0.0
    by_model = {}

    def afford(est=0.02):
        return spent + est <= cap_usd

    def meter(model, cost):
        nonlocal spent
        spent += cost
        by_model[model] = round(by_model.get(model, 0.0) + cost, 6)

    while len(kept) < target_kept and rounds < MAX_ROUNDS and afford():
        rounds += 1
        ch_msg = [{"role": "user", "content":
                   f"Generate {batch} diverse, challenging training questions about: {topic}."
                   + (f"\nGround them strictly in:\n{reference[:1500]}" if reference else "")
                   + "\nReturn ONLY a JSON array of question strings."}]
        ch_text, c = _ask(ch_msg, roles["challenger"], max_tokens=600, _call=_call)
        meter(roles["challenger"], c)
        try:
            tasks = [t for t in json.loads(ch_text) if isinstance(t, str)][:batch]
        except Exception:
            tasks = [ln.strip("-*0123456789. ").strip() for ln in (ch_text or "").splitlines() if ln.strip()][:batch]

        for task in tasks:
            if not afford():
                break
            candidates += 1
            w, cw = _ask([{"role": "user", "content": task}], roles["weak"], _call=_call); meter(roles["weak"], cw)
            s, cs = _ask([{"role": "user", "content": task}], roles["strong"], _call=_call); meter(roles["strong"], cs)
            iw, cjw = _correct(task, w, roles["judge"], _call=_call); meter(roles["judge"], cjw)
            is_, cjs = _correct(task, s, roles["judge"], _call=_call); meter(roles["judge"], cjs)
            if is_ - iw == 1:  # strong solved, weak failed -> Zone of Proximal Development
                t_clean, _ = mask_text(task)
                a_clean, _ = mask_text(s or "")
                kept.append(record([{"role": "user", "content": t_clean},
                                     {"role": "assistant", "content": a_clean}], source="synthetic"))

    return {
        "kept": kept,
        "candidates_generated": candidates,
        "kept_count": len(kept),
        "yield_pct": round(100 * len(kept) / candidates, 1) if candidates else 0.0,
        "spent_usd": round(spent, 6),
        "by_model_usd": by_model,
        "models": roles,
        "rounds": rounds,
        "cap_hit": not afford(),
    }
