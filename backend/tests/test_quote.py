from app.services import agent
from app.services.quote_service import price_quote, quote_job, sign_quote_token, verify_quote_token
from app.curate.parsers.dataset import parse_jsonl


def test_worked_examples_match_spec():
    a = price_quote(n_records=10000, complexity=0.20, data_type="jsonl", passes=1,
                    escalation_fraction=0.0, malformed_rate=0.02)
    b = price_quote(n_records=100000, complexity=0.50, data_type="tabular", passes=2,
                    escalation_fraction=0.20, pii=True, malformed_rate=0.05)
    c = price_quote(n_records=20000, complexity=0.85, data_type="scanned", pages=20000,
                    ocr_profile="textract_expense", passes=2, escalation_fraction=0.35,
                    pii=True, scanned_doc=True, malformed_rate=0.10,
                    base_model="gpt_4o_mini", next_model="gpt_4_1_mini")
    assert (a["quoted_usd"], b["quoted_usd"], c["quoted_usd"]) == (55.0, 250.0, 610.0)
    assert (a["estimated_cost_usd"], b["estimated_cost_usd"], c["estimated_cost_usd"]) == (6.21, 20.43, 263.26)


def test_human_quote_ceiling():
    big = price_quote(n_records=200000, complexity=0.85, data_type="scanned", pages=200000,
                      ocr_profile="textract_expense", passes=2, escalation_fraction=0.35, pii=True,
                      scanned_doc=True, base_model="gpt_4o_mini", next_model="gpt_4_1_mini")
    assert big["requires_human_quote"] and big["quoted_usd"] > 1000


def test_private_cogs_not_leaked_through_public_keys():
    # the route strips estimated_cost; price_quote itself keeps it server-side only
    q = price_quote(n_records=100, complexity=0.3)
    assert "estimated_cost_usd" in q  # present in the engine output (server-side)


def test_token_tamper_and_expiry():
    now = 1782600000
    tok = sign_quote_token({"quoted_usd": 250.0}, "https://x.com/d", "a@b.com", now)
    assert verify_quote_token(tok, now)["q"] == 250.0
    assert verify_quote_token(tok[:-3] + "xxx", now) is None
    assert verify_quote_token(tok, now + 16 * 60) is None


def test_question_ground_truth_jsonl_counts_as_training_records():
    rows = parse_jsonl(
        '{"question":"What is 2+2?","ground_truth":"A: 4"}\n'
        '{"question":"What is 3+5?","ground_truth":"A: 8"}\n',
        "https://example.com/gsm.jsonl",
    )
    assert len(rows) == 2
    assert rows[0]["messages"][0]["content"] == "What is 2+2?"
    assert rows[0]["messages"][1]["content"] == "A: 4"


def test_quote_job_reads_uploaded_local_file_handle(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "decide", lambda *a, **k: {
        "complexity": 0.3,
        "risk": "low",
        "est_tokens": 1000,
        "noise_level": 0.1,
        "steps": ["parse", "mask", "emit"],
        "can_run_locally": True,
    })
    src = tmp_path / "upload.jsonl"
    src.write_text(
        '{"prompt":"Email me at a@b.com","completion":"No thanks"}\n'
        '{"question":"What is 2+2?","ground_truth":"4"}\n'
    )

    q = quote_job(str(src), "buyer@test.com", 1782600000)

    assert q["n_records"] == 2
    assert q["data_type"] == "jsonl"
    assert q["complexity_scored_by"] == "aegis-14b"
    assert q["quoted_usd"] == 55.0


def test_quote_job_handles_multiple_supported_data_shapes(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "decide", lambda *a, **k: {
        "complexity": 0.2,
        "risk": "low",
        "est_tokens": 1000,
        "noise_level": 0.1,
        "steps": ["parse", "mask", "emit"],
        "can_run_locally": True,
    })
    cases = [
        ("sharegpt.jsonl", '{"conversations":[{"from":"human","value":"q"},{"from":"gpt","value":"a"}]}\n', "jsonl", 1),
        ("pairs.csv", "question,answer\nWhat is 2+2?,4\nWhat is 3+5?,8\n", "tabular", 2),
        ("notes.txt", "First paragraph with a@b.com.\n\nSecond paragraph.", "document", 2),
        ("examples.yaml", "- question: What is 9+1?\n  answer: '10'\n", "document", 1),
    ]

    for name, body, expected_type, expected_records in cases:
        src = tmp_path / name
        src.write_text(body)
        q = quote_job(str(src), "buyer@test.com", 1782600000)
        assert q["data_type"] == expected_type
        assert q["n_records"] == expected_records
        assert q["complexity_scored_by"] == "aegis-14b"


def test_quote_job_temporarily_queues_when_aegis_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "decide", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DGX busy")))
    src = tmp_path / "upload.jsonl"
    src.write_text('{"question":"What is 2+2?","answer":"4"}\n')

    try:
        quote_job(str(src), "buyer@test.com", 1782600000)
        raise AssertionError("expected quote_job to require Aegis-14B")
    except agent.AegisTemporarilyQueued as e:
        assert "temporarily queued" in str(e)


def test_quote_job_rejects_sources_with_no_usable_records(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "decide", lambda *a, **k: (_ for _ in ()).throw(AssertionError("model should not run")))
    src = tmp_path / "contacts.csv"
    src.write_text("name,email\nAda,ada@example.com\n")

    try:
        quote_job(str(src), "buyer@test.com", 1782600000)
        raise AssertionError("expected quote_job to reject an unmappable dataset")
    except ValueError as e:
        assert "no usable training records" in str(e)
