"""Shared 'who is at the screen' state: written by the camera loop, read by the native host (PRD F7)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from . import config

VALID_LABELS = ("adult", "child", "unknown", "none")


@dataclass
class StateReading:
    """The label the browser side should use, why, and how old the underlying state is."""

    label: str
    reason: str            # ok | missing | corrupt | invalid | stale
    age: float | None = None


def write_state(label: str, path: Path = config.STATE_PATH, now: float | None = None) -> bool:
    """Writes the label and timestamp (atomic replace, retried because Windows denies it while a reader has the file open), returning False instead of raising if it cannot."""
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    payload = json.dumps({"label": label, "ts": time.time() if now is None else now})
    try:
        tmp.write_text(payload)
    except OSError:
        return False
    for _ in range(10):
        try:
            os.replace(tmp, p)
            return True
        except PermissionError:
            time.sleep(0.02)
    try:                      # last resort: non-atomic write; readers treat a torn read as corrupt (strict)
        p.write_text(payload)
        return True
    except OSError:
        return False          # an unwritable state simply goes stale, which the browser treats as strict


def read_state(path: Path = config.STATE_PATH, now: float | None = None,
               max_age: float = config.STATE_MAX_AGE_S) -> StateReading:
    """Returns the stored label, or 'none' (strict) if the file is missing, corrupt, invalid or older than max_age seconds."""
    now = time.time() if now is None else now
    for attempt in range(2):      # one retry: a read that races a writer can be torn or briefly denied
        try:
            data = json.loads(Path(path).read_text())
            label, ts = data["label"], float(data["ts"])
            break
        except FileNotFoundError:
            return StateReading("none", "missing")
        except (OSError, ValueError, KeyError, TypeError):
            if attempt == 1:
                return StateReading("none", "corrupt")
            time.sleep(0.03)
    if label not in VALID_LABELS:
        return StateReading("none", "invalid")
    age = now - ts
    if age > max_age or age < -2.0:   # too old, or timestamp from the future (clock problem)
        return StateReading("none", "stale", age)
    return StateReading(label, "ok", age)
