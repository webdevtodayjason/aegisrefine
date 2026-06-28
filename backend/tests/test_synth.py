from app.synth.loop import synthesize, ROLES


def _mock(separation=True, judge_all_yes=False):
    """Returns a _call that fakes the four roles. strong gives a 'GOOD' answer; weak a 'bad' one.
    Judge says YES iff the answer contains GOOD (unless judge_all_yes)."""
    def call(messages, model):
        c = messages[0]["content"]
        if c.startswith("Generate"):
            return ('["What is 2+2?", "Explain quicksort."]', 0.001)
        if "Is the answer correct" in c:
            return ("YES" if (judge_all_yes or "GOOD" in c) else "NO", 0.0001)
        # a solver call
        good = (model == ROLES["strong"]) if separation else True
        return ("GOOD answer" if good else "bad", 0.0002)
    return call


def test_keeps_strong_solves_weak_fails():
    r = synthesize(topic="geo", target_kept=2, cap_usd=1.0, batch=2, _call=_mock())
    assert r["kept_count"] == 2 and r["candidates_generated"] == 2 and r["yield_pct"] == 100.0
    assert r["spent_usd"] > 0 and r["by_model_usd"]
    assert all(k["meta"]["source"] == "synthetic" for k in r["kept"])
    assert r["kept"][0]["messages"][1]["content"] == "GOOD answer"   # task -> the strong (correct) answer


def test_discards_when_no_separation():
    # both solvers "correct" -> Delta = 0 -> nothing kept
    r = synthesize(topic="x", target_kept=5, cap_usd=0.05, batch=2, _call=_mock(judge_all_yes=True))
    assert r["kept_count"] == 0


def test_budget_cap_halts_the_loop():
    def pricey(messages, model):
        c = messages[0]["content"]
        if c.startswith("Generate"):
            return ('["q1","q2","q3","q4"]', 0.01)
        if "Is the answer correct" in c:
            return ("YES" if "GOOD" in c else "NO", 0.005)
        return ("GOOD" if model == ROLES["strong"] else "bad", 0.01)
    r = synthesize(topic="x", target_kept=100, cap_usd=0.05, batch=4, _call=pricey)
    # cap is enforced at BATCH granularity (an in-flight concurrent batch completes), so it can
    # overshoot by up to one batch — bounded, never runaway. The caller passes a buffered cap_usd
    # (below the job's hard cap) so the cert's cap_respected stays true.
    assert r["cap_hit"] and r["kept_count"] < 100 and r["spent_usd"] < 0.25


def test_synth_runner_signs_provenance_cert(db, user):
    import os
    from app.models.job import Job
    from app.synth.runner import run_synth_job
    job = Job(user_id=user.id, status="processing", input_file_path="none", quote_amount=55.0,
              approved_cap=20.0, revenue_collected=55.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)
    cert = run_synth_job(db, job, topic="geo", target_kept=2, _call=_mock())
    assert os.path.exists(job.output_file_path)                       # labeled-synthetic JSONL written
    g = cert["guarantees"]["synthesis"]
    assert g["kept_synthetic"] == 2 and g["labeled_synthetic"] is True and g["spent_usd"] > 0
    assert cert["guarantees"]["pii_residual"] == 0                    # synth output is PII-checked too
    assert cert["economics"]["spent_usd"] > 0 and cert["economics"]["cap_respected"] is True
    assert cert["sig"]["alg"] == "Ed25519"
