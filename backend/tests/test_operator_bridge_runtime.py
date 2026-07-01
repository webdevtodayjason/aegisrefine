import importlib.util
from pathlib import Path


BRIDGE_PATH = Path(__file__).resolve().parents[2] / "hermes" / "operator_bridge.py"
RUNTIME_ENV_KEYS = (
    "HERMES_BIN",
    "HERMES_OPERATOR_RUNTIME",
    "HERMES_OPERATOR_MODE",
    "HERMES_OPERATOR_PROVIDER",
    "NEMOCLAW_BIN",
    "NEMOCLAW_SANDBOX",
    "NEMOCLAW_HERMES_BIN",
    "OPENSHELL_BIN",
)


def load_bridge(monkeypatch, **env):
    for key in RUNTIME_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("operator_bridge_under_test", BRIDGE_PATH)
    bridge = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(bridge)
    return bridge


def test_operator_command_defaults_to_local_hermes(monkeypatch):
    bridge = load_bridge(
        monkeypatch,
        HERMES_BIN="/opt/hermes/bin/hermes",
        HERMES_OPERATOR_PROVIDER="nous",
    )

    cmd = bridge._operator_cmd({"job_id": 17, "phase": "paid_job_created"}, "nvidia/nemotron-3-nano-30b-a3b")

    assert cmd[0] == "/opt/hermes/bin/hermes"
    assert "nemohermes" not in cmd
    assert cmd[1:5] == ["--provider", "nous", "-m", "nvidia/nemotron-3-nano-30b-a3b"]
    assert "--skills" in cmd
    assert "aegis-refine" in cmd


def test_operator_command_can_run_inside_nemoclaw(monkeypatch):
    bridge = load_bridge(
        monkeypatch,
        HERMES_BIN="/opt/hermes/bin/hermes",
        HERMES_OPERATOR_RUNTIME="nemoclaw",
        NEMOCLAW_BIN="/usr/local/bin/nemohermes",
        NEMOCLAW_SANDBOX="aegis-sandbox",
        NEMOCLAW_HERMES_BIN="hermes",
    )

    cmd = bridge._operator_cmd({"job_id": 17, "phase": "completed"}, None)

    assert cmd[:5] == [
        "/usr/local/bin/nemohermes",
        "aegis-sandbox",
        "exec",
        "--",
        "hermes",
    ]
    assert bridge._runtime_metadata("completed") == {
        "mode": "nemoclaw",
        "runtime": "NemoClaw / nemohermes",
        "status": "completed",
        "sandbox": "aegis-sandbox",
    }


def test_operator_command_can_use_openshell_wrapper(monkeypatch):
    bridge = load_bridge(
        monkeypatch,
        HERMES_BIN="/opt/hermes/bin/hermes",
        HERMES_OPERATOR_RUNTIME="openshell",
        OPENSHELL_BIN="/usr/local/bin/openshell",
        NEMOCLAW_SANDBOX="aegis-sandbox",
        NEMOCLAW_HERMES_BIN="hermes",
    )

    cmd = bridge._operator_cmd({"job_id": 17, "phase": "completed"}, None)

    assert cmd[:7] == [
        "/usr/local/bin/openshell",
        "sandbox",
        "exec",
        "-n",
        "aegis-sandbox",
        "--",
        "hermes",
    ]


def test_normalized_receipt_records_operator_runtime(monkeypatch):
    bridge = load_bridge(
        monkeypatch,
        HERMES_OPERATOR_RUNTIME="nemoclaw",
        NEMOCLAW_SANDBOX="aegis-sandbox",
    )

    out = bridge._normalize_result(
        {"job_id": 17, "service": "refine", "phase": "completed"},
        {"route": "run_local"},
    )

    assert out["operator_runtime"]["runtime"] == "NemoClaw / nemohermes"
    assert out["operator_runtime"]["sandbox"] == "aegis-sandbox"
    assert out["operator_runtime"]["status"] == "completed"


def test_queued_receipt_records_runtime_when_sandbox_fails(monkeypatch):
    bridge = load_bridge(
        monkeypatch,
        HERMES_OPERATOR_RUNTIME="nemoclaw",
        NEMOCLAW_SANDBOX="aegis-sandbox",
    )

    out = bridge._queued_result({"job_id": 17, "service": "refine"}, RuntimeError("missing nemohermes"))

    assert out["route"] == "temporarily_queue"
    assert out["spend"]["executed"] is None
    assert out["operator_runtime"]["runtime"] == "NemoClaw / nemohermes"
    assert out["operator_runtime"]["status"] == "queued"
