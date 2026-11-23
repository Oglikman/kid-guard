"""Unit tests for native-messaging framing and the host's request handling."""
import io
import json
import struct
from datetime import datetime

import pytest

from kidguard.blocklist import Blocklist
from kidguard.decision import Policy, save_policy
from kidguard.host import HostContext, handle, read_message, serve, write_message
from kidguard.state import write_state
from install_host import build_host_manifest, extension_id_from_key

NOON = datetime(2026, 11, 2, 12, 0)


def make_ctx(tmp_path, label="child", ts=1000.0, now=1001.0, **kw):
    """Builds a HostContext with a temp state file holding the label, a fixed clock and a small blocklist."""
    sp = tmp_path / "state.json"
    if label is not None:
        write_state(label, sp, now=ts)
    return HostContext(blocklist=Blocklist({"adult": ["adult.test"]}), policy_path=tmp_path / "policy.json",
                       state_path=sp, now_fn=lambda: NOON, state_time_fn=lambda: now, **kw)


def frame(obj):
    """Encodes a dict as one length-prefixed native-messaging frame."""
    b = json.dumps(obj).encode()
    return struct.pack("=I", len(b)) + b


def test_framing_round_trip():
    """A message written with write_message is read back identically, and EOF returns None."""
    buf = io.BytesIO()
    write_message(buf, {"a": 1, "b": "ü"})
    buf.seek(0)
    assert read_message(buf) == {"a": 1, "b": "ü"} and read_message(buf) is None


def test_read_truncated_body_is_eof():
    """A frame whose body is shorter than its header says is treated as end of input."""
    assert read_message(io.BytesIO(struct.pack("=I", 50) + b"{}")) is None


def test_read_rejects_oversized_message():
    """A frame announcing more than the size limit raises ValueError."""
    with pytest.raises(ValueError):
        read_message(io.BytesIO(struct.pack("=I", 5_000_000)))


def test_check_child_blocks_adult_site(tmp_path):
    """With a child present, an adult-category URL is blocked and the id is echoed."""
    r = handle({"type": "check", "id": 7, "url": "http://adult.test/x"}, make_ctx(tmp_path, "child"))
    assert (r["type"], r["action"], r["id"], r["label"], r["profile"]) == ("decision", "block", 7, "child", "strict")


def test_check_adult_allows(tmp_path):
    """With a fresh adult label, the same URL is allowed (normal profile)."""
    r = handle({"type": "check", "id": 1, "url": "http://adult.test"}, make_ctx(tmp_path, "adult"))
    assert r["action"] == "allow" and r["profile"] == "normal" and r["state"] == "ok"


def test_check_stale_adult_falls_back_to_strict(tmp_path):
    """If the camera app stopped updating, a once-adult label expires and the site is blocked."""
    r = handle({"type": "check", "id": 1, "url": "http://adult.test"}, make_ctx(tmp_path, "adult", ts=1000.0, now=1100.0))
    assert r["action"] == "block" and r["state"] == "stale" and r["label"] == "none"


def test_check_no_state_file_blocks(tmp_path):
    """With no state file at all (camera app never started), adult sites are blocked."""
    r = handle({"type": "check", "id": 1, "url": "http://adult.test"}, make_ctx(tmp_path, None))
    assert r["action"] == "block" and r["state"] == "missing"


def test_check_bad_url_type_is_error(tmp_path):
    """A non-string url returns an error reply instead of crashing."""
    assert handle({"type": "check", "id": 2, "url": 5}, make_ctx(tmp_path))["type"] == "error"


def test_unknown_type_is_error(tmp_path):
    """An unknown message type returns an error reply that echoes the id."""
    r = handle({"type": "nope", "id": 3}, make_ctx(tmp_path))
    assert r["type"] == "error" and r["id"] == 3


def test_status_and_ping(tmp_path):
    """Status reports label, profile and freshness; ping reports the protocol version."""
    ctx = make_ctx(tmp_path, "adult")
    s = handle({"type": "status", "id": 1}, ctx)
    assert (s["label"], s["profile"], s["state"]) == ("adult", "normal", "ok")
    assert handle({"type": "ping", "id": 2}, ctx)["type"] == "pong"


def test_broken_policy_file_falls_back_to_default(tmp_path):
    """A corrupt policy.json does not crash the host and the default strict rules still apply."""
    ctx = make_ctx(tmp_path, "child")
    (tmp_path / "policy.json").write_text("{broken")
    assert handle({"type": "check", "id": 1, "url": "http://adult.test"}, ctx)["action"] == "block"


def test_parent_policy_is_applied(tmp_path):
    """An always-block domain from policy.json is blocked even for an adult."""
    ctx = make_ctx(tmp_path, "adult")
    save_policy(Policy(always_block={"timewaster.test"}), tmp_path / "policy.json")
    assert handle({"type": "check", "id": 1, "url": "http://timewaster.test"}, ctx)["action"] == "block"


def test_internal_error_blocks(tmp_path):
    """If the engine raises unexpectedly, the reply is a block, never an allow."""
    ctx = make_ctx(tmp_path, "adult")
    ctx.blocklist = None  # forces an AttributeError inside the engine
    r = handle({"type": "check", "id": 9, "url": "http://example.org"}, ctx)
    assert r["action"] == "block" and "internal error" in r["reason"] and r["id"] == 9


def test_serve_handles_multiple_messages_in_order(tmp_path):
    """serve answers each request in order and stops cleanly at end of input."""
    ins = io.BytesIO(frame({"type": "ping", "id": 1}) + frame({"type": "check", "id": 2, "url": "http://adult.test"}))
    out = io.BytesIO()
    serve(ins, out, make_ctx(tmp_path, "child"))
    out.seek(0)
    first, second = read_message(out), read_message(out)
    assert first["type"] == "pong" and second["action"] == "block" and read_message(out) is None


def test_log_has_no_urls_and_records_decisions(tmp_path):
    """serve writes one log line per request containing label and action but never the URL."""
    log = tmp_path / "host.log"
    ctx = make_ctx(tmp_path, "child", log_path=log)
    ins = io.BytesIO(frame({"type": "status", "id": 1}) + frame({"type": "check", "id": 2, "url": "http://adult.test/private?q=1"}))
    serve(ins, io.BytesIO(), ctx)
    text = log.read_text()
    assert "adult.test" not in text and "private" not in text
    assert "label=child" in text and "action=block" in text and text.count("\n") == 2


def test_log_failure_does_not_break_serving(tmp_path):
    """If the log cannot be written (path is a directory), requests are still answered."""
    out = io.BytesIO()
    serve(io.BytesIO(frame({"type": "ping", "id": 1})), out, make_ctx(tmp_path, "child", log_path=tmp_path))
    out.seek(0)
    assert read_message(out)["type"] == "pong"


def test_extension_id_is_32_chars_a_to_p():
    """The computed extension ID is 32 letters in a-p, as Chrome requires."""
    import base64
    eid = extension_id_from_key(base64.b64encode(b"some public key bytes").decode())
    assert len(eid) == 32 and set(eid) <= set("abcdefghijklmnop")


def test_host_manifest_restricts_origin(tmp_path):
    """The host manifest allows exactly one extension origin and points at the launcher."""
    m = build_host_manifest(tmp_path / "x.bat", "abcdefghijklmnopabcdefghijklmnop")
    assert m["allowed_origins"] == ["chrome-extension://abcdefghijklmnopabcdefghijklmnop/"] and m["type"] == "stdio"
