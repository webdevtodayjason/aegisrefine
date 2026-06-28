"""Document-format parsers: a tiny YAML (Q&A-shaped) + plain TXT parse to valid records that
survive the same schema check the rest of the pipeline enforces."""
from app.curate.parsers import documents as docs
from app.curate.format import valid_record


def test_yaml_and_txt_parse_to_records():
    # YAML: a list of mixed Q&A dialects -> reuse the multi-dialect converter.
    yaml_text = (
        "- question: What is 2+2?\n"
        "  answer: \"4\"\n"
        "- instruction: Capital of France?\n"
        "  input: \"\"\n"
        "  output: Paris\n"
    )
    y = docs.parse_yaml(yaml_text, "u.yaml")
    assert len(y) == 2
    assert [m["role"] for m in y[0]["messages"]] == ["user", "assistant"]
    assert y[0]["messages"][0]["content"] == "What is 2+2?"
    assert y[0]["messages"][1]["content"] == "4"
    assert all(valid_record(r) for r in y)

    # TXT: blank-line paragraphs -> one verbatim-reproduction record each.
    txt = "First paragraph about cats.\n\nSecond paragraph about dogs.\n\nThird about birds."
    t = docs.parse_txt(txt, "u.txt")
    assert len(t) == 3
    for r in t:
        assert [m["role"] for m in r["messages"]] == ["user", "assistant"]
        assert r["messages"][1]["content"]  # assistant turn carries the real passage
        assert valid_record(r)
