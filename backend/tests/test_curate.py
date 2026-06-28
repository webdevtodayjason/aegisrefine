import json
from app.curate import engine


def test_curation_cleans_dedups_masks(tmp_path, write_jsonl):
    src = write_jsonl(tmp_path, [
        {"conversations": [{"from": "human", "value": "Email john@x.com"}, {"from": "gpt", "value": "call 555-123-4567"}]},
        {"instruction": "2+2?", "input": "", "output": "4"},
        {"prompt": "hi", "completion": "hello"},
        {"conversations": [{"from": "human", "value": "Email john@x.com"}, {"from": "gpt", "value": "call 555-123-4567"}]},  # dup
        {"question": "SSN?", "answer": "123-45-6789"},
        {"foo": "bar"},  # unknown -> skipped, never guessed
    ])
    res = engine.run(src, out_dir=str(tmp_path))
    st = res["stats"]
    assert st["rows_in"] == 5            # 6 lines, 1 unknown skipped
    assert st["dupes_removed"] >= 1
    assert st["pii_masked"] >= 3          # email + phone + ssn
    assert st["rows_out"] == st["rows_in"] - st["dupes_removed"] - st["dropped_invalid"]
    v = engine.verify_output(res["output_path"])
    assert v["ok"] and v["pii_residual"] == 0 and v["dupes_residual"] == 0 and v["schema_valid"]


def test_output_is_valid_sharegpt(tmp_path, write_jsonl):
    src = write_jsonl(tmp_path, [{"prompt": "hi", "completion": "hello"}])
    res = engine.run(src, out_dir=str(tmp_path))
    line = json.loads(open(res["output_path"]).readline())
    assert line["conversations"][0]["from"] == "human"
    assert line["conversations"][1]["from"] == "gpt"


def test_empty_and_garbage_inputs(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    res = engine.run(str(empty), out_dir=str(tmp_path))
    assert res["stats"]["rows_in"] == 0 and res["stats"]["rows_out"] == 0
