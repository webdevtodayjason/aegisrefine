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


def test_synth_runner_grounds_augment_on_reference_file(db, user, tmp_path, monkeypatch):
    import os
    from app.curate.canonical import record
    from app.models.job import Job
    from app.synth import runner

    captured = {}

    def fake_synthesize(**kwargs):
        captured["reference"] = kwargs["reference"]
        return {
            "kept": [record([
                {"role": "user", "content": "harder double-digit addition"},
                {"role": "assistant", "content": "42"},
            ], source="synthetic")],
            "candidates_generated": 1,
            "kept_count": 1,
            "yield_pct": 100.0,
            "spent_usd": 0.0,
            "by_model_usd": {},
            "models": {"challenger": "fake", "weak": "fake", "strong": "fake", "judge": "fake"},
        }

    monkeypatch.setattr(runner, "synthesize", fake_synthesize)
    ref = tmp_path / "grounding.jsonl"
    ref.write_text('{"question":"What is 12+30?","answer":"42"}\n')
    job = Job(user_id=user.id, status="processing", input_file_path="none", quote_amount=55.0,
              approved_cap=55.0, revenue_collected=55.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)

    cert = runner.run_synth_job(db, job, topic="harder arithmetic", target_kept=1, reference=str(ref))

    assert "What is 12+30?" in captured["reference"]
    assert os.path.exists(job.output_file_path)
    assert cert["guarantees"]["synthesis"]["real_rows"] == 1


def test_synth_runner_fails_instead_of_signing_empty_output(db, user, monkeypatch):
    import pytest
    from app.models.job import Job
    from app.synth import runner

    def fake_empty(**kwargs):
        return {
            "kept": [],
            "candidates_generated": 0,
            "kept_count": 0,
            "yield_pct": 0.0,
            "spent_usd": 0.0,
            "by_model_usd": {},
            "models": {"challenger": "fake", "weak": "fake", "strong": "fake", "judge": "fake"},
        }

    monkeypatch.setattr(runner, "synthesize", fake_empty)
    job = Job(user_id=user.id, status="processing", input_file_path="none", quote_amount=55.0,
              approved_cap=55.0, revenue_collected=55.0, target_margin_pct=0.65)
    db.add(job); db.commit(); db.refresh(job)

    with pytest.raises(RuntimeError, match="zero kept rows"):
        runner.run_synth_job(db, job, topic="geo", target_kept=1)

    assert job.status == "failed"
    assert not job.output_file_path


def test_synth_quote_accepts_upload_handle_for_augment():
    from starlette.testclient import TestClient
    from app.main import app

    c = TestClient(app, follow_redirects=False)
    r = c.post("/auth/signup", json={"email": "synth-upload@test.com", "password": "hunter2pass"})
    assert r.status_code == 200, r.text
    upload = c.post("/jobs/upload", files={
        "file": ("grounding.jsonl", b'{"question":"q","answer":"a"}\n', "application/x-ndjson")
    })
    assert upload.status_code == 200, upload.text
    r = c.post("/jobs/synth-quote", json={
        "topic": "harder variants",
        "target_kept": 5,
        "upload_handle": upload.json()["handle"],
    })

    assert r.status_code == 200, r.text
    out = r.json()
    assert out["service"] == "synthesis"
    assert out["mode"] == "augment"
    assert out["token"]


def test_quote_synth_caps_with_margin():
    from app.services.quote_service import quote_synth
    q = quote_synth(100)        # 100 × $0.05 = $5 COGS -> floor $49
    assert q["estimated_cost_usd"] == 5.0 and q["quote_usd"] == 49.0 and q["service"] == "synthesis"
    q2 = quote_synth(2000)      # 2000 × $0.05 = $100 COGS -> $100/(1-0.65) cap
    assert q2["quote_usd"] == round(100 / (1 - 0.65), 2) > q2["estimated_cost_usd"]
    assert q2["target_margin_pct"] == 65.0
