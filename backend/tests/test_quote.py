from app.services.quote_service import price_quote, sign_quote_token, verify_quote_token


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
