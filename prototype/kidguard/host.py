"""Native-messaging host logic: length-prefixed JSON framing plus request handling for the browser extension (PRD F6, F7)."""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import config
from .blocklist import Blocklist, load_blocklist
from .decision import Policy, decide_for_label, load_policy
from .policy import profile_for
from .state import read_state

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1_000_000


@dataclass
class HostContext:
    """Everything the handler needs: the blocklist, file locations and a clock (injectable for tests)."""

    blocklist: Blocklist = field(default_factory=Blocklist)
    policy_path: Path = config.POLICY_PATH
    state_path: Path = config.STATE_PATH
    blocklist_dir: Path = config.BLOCKLIST_DIR
    now_fn: Callable[[], datetime] = datetime.now
    state_time_fn: Callable[[], float] | None = None
    log_path: Path | None = None   # if set, one line per request is appended here (never contains URLs)


def read_message(stream):
    """Reads one 4-byte-length-prefixed JSON message from a binary stream, returning None at end of input."""
    header = stream.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("=I", header)
    if length > MAX_MESSAGE_BYTES:
        raise ValueError(f"message too large ({length} bytes)")
    body = stream.read(length)
    if len(body) < length:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(stream, obj: dict) -> None:
    """Writes one length-prefixed JSON message to a binary stream and flushes it."""
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    stream.write(struct.pack("=I", len(body)) + body)
    stream.flush()


def _policy(ctx: HostContext) -> Policy:
    """Loads the parent policy, falling back to the default (strict-blocking) policy if the file is unreadable."""
    try:
        return load_policy(ctx.policy_path)
    except (OSError, ValueError, KeyError, TypeError):
        return Policy()


def _reading(ctx: HostContext):
    """Reads the shared who-is-present state using the context's file path and clock."""
    now = ctx.state_time_fn() if ctx.state_time_fn else None
    return read_state(ctx.state_path, now=now)


def handle(msg: dict, ctx: HostContext) -> dict:
    """Answers one request (check, status, reload, ping); any internal error becomes a blocking, fail-safe reply."""
    mid = msg.get("id") if isinstance(msg, dict) else None
    try:
        kind = msg.get("type")
        if kind == "ping":
            return {"type": "pong", "id": mid, "version": PROTOCOL_VERSION}
        if kind == "reload":
            ctx.blocklist = load_blocklist(ctx.blocklist_dir)
            return {"type": "ok", "id": mid, "domains": ctx.blocklist.size()}
        if kind == "status":
            r = _reading(ctx)
            return {"type": "status", "id": mid, "label": r.label, "profile": profile_for(r.label),
                    "state": r.reason, "age": r.age, "version": PROTOCOL_VERSION}
        if kind == "check":
            url = msg.get("url")
            if not isinstance(url, str):
                return {"type": "error", "id": mid, "error": "url must be a string"}
            r = _reading(ctx)
            d = decide_for_label(url, r.label, ctx.now_fn(), _policy(ctx), ctx.blocklist)
            return {"type": "decision", "id": mid, "action": d.action, "reason": d.reason, "profile": d.profile,
                    "category": d.category, "host": d.host, "label": r.label, "state": r.reason}
        return {"type": "error", "id": mid, "error": f"unknown type '{kind}'"}
    except Exception as e:  # fail-safe: never answer 'allow' because of a bug
        return {"type": "decision", "id": mid, "action": "block", "profile": "strict", "label": "none",
                "reason": f"internal error, blocking for safety ({type(e).__name__})", "category": None, "host": None,
                "state": "error"}


LOG_MAX_BYTES = 200_000


def log_event(ctx: HostContext, msg: dict, reply: dict) -> None:
    """Appends one line (time, request type, label, state, action, reason, profile; never the URL) to the debug log, trimming it when large and never raising."""
    if ctx.log_path is None:
        return
    try:
        p = Path(ctx.log_path)
        if p.exists() and p.stat().st_size > LOG_MAX_BYTES:
            p.write_text("".join(p.read_text(encoding="utf-8").splitlines(keepends=True)[-500:]), encoding="utf-8")
        line = "{} {} id={} label={} state={} age={} action={} profile={} reason={}\n".format(
            datetime.now().strftime("%H:%M:%S"), reply.get("type"), reply.get("id"), reply.get("label"), reply.get("state"),
            None if reply.get("age") is None else round(reply["age"], 1), reply.get("action"), reply.get("profile"),
            (reply.get("reason") or "").split(" (")[0][:80])
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass   # logging must never break the host


def serve(stdin, stdout, ctx: HostContext) -> None:
    """Reads requests until the browser closes the pipe, answering each one in order and logging it."""
    while True:
        msg = read_message(stdin)
        if msg is None:
            return
        reply = handle(msg, ctx)
        write_message(stdout, reply)
        log_event(ctx, msg, reply)
