"""End-to-end test: launches native_host.py as a real subprocess and talks to it over binary pipes exactly as the browser does."""
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

from kidguard.state import write_state

HOST = Path(__file__).resolve().parent.parent / "native_host.py"


def ask(proc, obj):
    """Sends one framed request to the host process and returns its framed reply."""
    body = json.dumps(obj).encode()
    proc.stdin.write(struct.pack("=I", len(body)) + body)
    proc.stdin.flush()
    (n,) = struct.unpack("=I", proc.stdout.read(4))
    return json.loads(proc.stdout.read(n))


def start(state_file):
    """Starts the host process pointed at a temporary state file."""
    env = dict(os.environ, KIDGUARD_STATE=str(state_file))
    return subprocess.Popen([sys.executable, str(HOST)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, cwd=str(HOST.parent))


def test_host_process_round_trip_and_profile_switch(tmp_path):
    """Real host process: ping works, a child gets adult-site blocks, then an adult label (updated live) unlocks, then stale falls back to strict."""
    state = tmp_path / "state.json"
    write_state("child", state)
    p = start(state)
    try:
        assert ask(p, {"type": "ping", "id": 1})["type"] == "pong"
        r = ask(p, {"type": "check", "id": 2, "url": "http://adult-sample.test/x"})
        assert r["action"] == "block" and r["label"] == "child" and r["id"] == 2
        write_state("adult", state)   # the camera app flips the label while the host keeps running
        r = ask(p, {"type": "check", "id": 3, "url": "http://adult-sample.test/x"})
        assert r["action"] == "allow" and r["profile"] == "normal"
        write_state("adult", state, now=time.time() - 60)   # camera app stopped updating a minute ago
        r = ask(p, {"type": "check", "id": 4, "url": "http://adult-sample.test/x"})
        assert r["action"] == "block" and r["state"] == "stale"
    finally:
        p.stdin.close()
        try:
            code = p.wait(timeout=30)   # generous: the machine may be busy; a real hang would still fail
        except subprocess.TimeoutExpired:
            p.kill()
            raise
        assert code == 0   # exits cleanly when the browser closes the pipe
        p.stdout.close()
        p.stderr.close()
