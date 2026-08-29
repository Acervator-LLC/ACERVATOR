"""The desktop shell's boundary: the stdio protocol and the History surface.

Two properties carry this file. The protocol must survive a bad request
and must not be corrupted by anything else the backend writes to stdout,
and the payload the surface produces must satisfy the key list the
renderer itself enforces. The second is read out of
``src/gui/web/history_panel.js`` rather than restated here, so the two
halves cannot drift apart without this failing.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from src.core import desktop_bridge as db
from src.exchange import history_read_contract as hrc
from src.exchange import history_surface

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_JS = REPO_ROOT / "src" / "gui" / "web" / "history_panel.js"

NOW = 1780000000.0

LINE_SEPARATOR = " "
PARAGRAPH_SEPARATOR = " "


@pytest.fixture()
def registry():
    return db.build_registry()


def renderer_required_keys() -> list:
    """The keys ``history_panel.js`` refuses to render without."""
    source = PANEL_JS.read_text(encoding="utf-8")
    block = re.search(r"var REQUIRED_KEYS = \[(.*?)\]", source, re.S)
    assert block, "history_panel.js no longer declares REQUIRED_KEYS"
    return re.findall(r'"([a-z_]+)"', block.group(1))


def unparseable_lines(payload: bytes) -> int:
    """How many non-blank lines of ``payload`` are not JSON."""
    count = 0
    for line in payload.splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
        except ValueError:
            count += 1
    return count


def noisy_handler(_params):
    """A handler that writes to stdout, which is the hazard the redirect
    in ``main`` exists to contain."""
    print("CONTAMINATION")
    return {"ok": 1}


def test_the_renderer_still_declares_its_required_keys():
    assert renderer_required_keys() == [
        "columns",
        "page",
        "summary",
        "filters",
        "filter_options",
        "loaded",
    ]


def test_ping_answers_with_the_protocol_version(registry):
    reply = db.handle_line(json.dumps({"id": 7, "method": "bridge.ping"}), registry)
    assert reply == {"id": 7, "ok": True, "result": {"protocol": db.PROTOCOL_VERSION}}


def test_unknown_method_is_an_error_frame_not_an_exception(registry):
    reply = db.handle_line(json.dumps({"id": 1, "method": "nope"}), registry)
    assert reply["ok"] is False
    assert reply["id"] == 1
    assert reply["error"]["type"] == "UnknownMethod"


def test_malformed_json_is_an_error_frame(registry):
    reply = db.handle_line("{not json", registry)
    assert reply["ok"] is False
    assert reply["id"] is None


def test_a_json_scalar_is_not_a_request(registry):
    reply = db.handle_line("42", registry)
    assert reply["ok"] is False
    assert reply["error"]["type"] == "TypeError"


def test_a_failing_handler_reports_its_own_exception():
    def boom(_params):
        raise ValueError("handler said no")

    reply = db.handle_line(json.dumps({"id": 3, "method": "x"}), {"x": boom})
    assert reply["ok"] is False
    assert reply["error"]["type"] == "ValueError"
    assert reply["error"]["message"] == "handler said no"


def test_a_frame_is_one_line_with_no_carriage_return():
    raw = db.encode_frame({"id": 1, "ok": True, "result": {"t": "a b"}})
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    assert b"\r" not in raw


def test_a_frame_escapes_the_javascript_line_terminators():
    payload = "a" + LINE_SEPARATOR + "b" + PARAGRAPH_SEPARATOR + "c"
    raw = db.encode_frame({"id": 1, "ok": True, "result": {"t": payload}})
    assert raw.count(b"\n") == 1
    assert LINE_SEPARATOR.encode("utf-8") not in raw
    assert PARAGRAPH_SEPARATOR.encode("utf-8") not in raw
    assert json.loads(raw)["result"]["t"] == payload


def test_serve_answers_every_request_in_order(registry):
    requests = b"".join(
        json.dumps({"id": i, "method": "bridge.ping"}).encode() + b"\n"
        for i in range(3)
    )
    out = io.BytesIO()
    answered = db.serve(io.BytesIO(requests), out, registry)
    assert answered == 3
    ids = [json.loads(line)["id"] for line in out.getvalue().splitlines()]
    assert ids == [0, 1, 2]


def test_serve_skips_blank_lines(registry):
    ping = json.dumps({"id": 1, "method": "bridge.ping"}).encode()
    stream = io.BytesIO(b"\n\n" + ping + b"\n")
    out = io.BytesIO()
    assert db.serve(stream, out, registry) == 1


def test_payload_carries_every_key_the_renderer_requires(registry):
    request = json.dumps(
        {"id": 1, "method": history_surface.METHOD, "params": {"now_ts": NOW}}
    )
    reply = db.handle_line(request, registry)
    assert reply["ok"] is True
    for key in renderer_required_keys():
        assert key in reply["result"], "renderer requires " + key


def test_payload_serves_all_thirteen_columns_with_cell_fields():
    trade = {
        "timestamp": NOW,
        "symbol": "BTC-USD",
        "side": "BUY",
        "amount": 0.5,
        "price": 100.0,
        "cost": 50.0,
        "fee": 0.25,
        "id": "t-1",
        "bot_id": "bot-1",
        "exchange": "coinbase",
    }
    model = history_surface.view_model({"trades": [trade], "now_ts": NOW})
    assert len(model["columns"]) == len(hrc.COLUMNS) == 13
    rows = model["page"]["rows"]
    assert len(rows) == 1
    cells = rows[0]["cells"]
    assert len(cells) == 13
    for cell in cells:
        assert set(cell) >= {"key", "value", "text", "color", "tooltip"}
    by_key = {c["key"]: c for c in cells}
    assert by_key["side"]["text"] == "BUY"
    assert by_key["side"]["color"] == "#00ff88"
    assert by_key["symbol"]["text"] == "BTC-USD"


def test_a_row_delivered_as_json_still_renders_its_timestamp():
    """JSON carries no datetime object, so the surface derives one. A row
    without it renders the contract's empty marker instead of a date."""
    plain = {"timestamp": NOW, "symbol": "BTC-USD", "side": "BUY"}
    model = history_surface.view_model({"trades": [plain], "now_ts": NOW})
    stamp = {c["key"]: c for c in model["page"]["rows"][0]["cells"]}["timestamp"]
    assert stamp["text"] != "—"
    assert stamp["text"].startswith("2026-")


def test_the_whole_payload_is_json_serialisable():
    model = history_surface.view_model({"trades": [], "now_ts": NOW})
    assert json.loads(json.dumps(model, ensure_ascii=True))["loaded"] == 0


def test_supplied_filters_override_the_defaults_and_unknown_keys_are_ignored():
    model = history_surface.view_model(
        {"trades": [], "now_ts": NOW, "filters": {"side": "BUY", "bogus": "x"}}
    )
    assert model["filters"]["side"] == "BUY"
    assert "bogus" not in model["filters"]


def test_an_inactive_date_bound_reads_as_any():
    assert history_surface.date_text(0) == "(any)"
    assert history_surface.date_text(int(NOW)).startswith("2026-")


def test_the_backend_answers_over_its_own_stdio():
    """The whole boundary as the shell uses it: a child process, two
    requests written to its stdin, two frames read off its stdout."""
    lines = "".join(
        json.dumps({"id": i, "method": "bridge.ping"}) + "\n" for i in (1, 2)
    )
    done = subprocess.run(
        [sys.executable, "-m", "src.core.desktop_bridge"],
        input=lines.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    frames = [json.loads(x) for x in done.stdout.splitlines() if x.strip()]
    assert [f["id"] for f in frames] == [1, 2]
    assert all(f["ok"] for f in frames)


def test_the_backend_answers_while_its_stdin_stays_open():
    """The shell holds stdin open for the life of the window, so a frame
    has to come back on the newline rather than when the pipe closes. A
    reader that filled a buffer first would hang here instead."""
    child = subprocess.Popen(
        [sys.executable, "-m", "src.core.desktop_bridge"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )
    frames = []

    def collect():
        for line in child.stdout:
            frames.append(json.loads(line))
            if len(frames) >= 2:
                return

    worker = threading.Thread(target=collect, daemon=True)
    worker.start()
    try:
        for request in (
            {"id": 1, "method": "bridge.ping"},
            {"id": 2, "method": history_surface.METHOD, "params": {"now_ts": NOW}},
        ):
            child.stdin.write(json.dumps(request).encode() + b"\n")
            child.stdin.flush()
            worker.join(timeout=60)
        assert [f["id"] for f in frames] == [1, 2], "the backend did not answer"
        assert all(f["ok"] for f in frames)
        assert "columns" in frames[1]["result"]
    finally:
        child.stdin.close()
        child.wait(timeout=60)
    assert child.returncode == 0


def noisy_request() -> bytes:
    return json.dumps({"id": 1, "method": "noisy"}).encode() + b"\n"


def test_a_handler_that_prints_cannot_corrupt_the_frame_stream(monkeypatch):
    """``main`` rebinds ``sys.stdout`` away from the protocol channel, so
    a print anywhere in the backend cannot put a non-frame line between
    two frames."""
    channel = io.BytesIO()
    noise = io.StringIO()
    monkeypatch.setattr(sys, "stdout", noise)
    db.serve(io.BytesIO(noisy_request()), channel, {"noisy": noisy_handler})
    assert unparseable_lines(channel.getvalue()) == 0
    frames = [json.loads(x) for x in channel.getvalue().splitlines() if x.strip()]
    assert frames == [{"id": 1, "ok": True, "result": {"ok": 1}}]
    assert "CONTAMINATION" in noise.getvalue()


def test_control_a_backend_sharing_stdout_does_corrupt_the_stream(monkeypatch):
    """The blinded twin of the test above. When the protocol channel and
    stdout are the same stream, the same request puts a line that is not
    a frame into it. This is what makes the test above evidence rather
    than an assumption."""
    shared = io.BytesIO()
    monkeypatch.setattr(
        sys, "stdout", io.TextIOWrapper(shared, encoding="utf-8", write_through=True)
    )
    db.serve(io.BytesIO(noisy_request()), shared, {"noisy": noisy_handler})
    assert unparseable_lines(shared.getvalue()) == 1
