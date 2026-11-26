"""PIN step-up (PRD F15): after a failed head-turn challenge, a new attempt needs the parent PIN, with a growing lockout for wrong PINs.

The salted PIN hash, the "PIN required" flag and the lockout live in ONE encrypted file, so deleting it leaves "no PIN set" (strict) rather than
quietly clearing a lockout. Anything unreadable or unwritable is treated as strict. Limits: a user of the same Windows account can delete the file
or restore an older copy, and a short PIN can be brute-forced by anyone who can decrypt it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from . import config
from .store import dpapi_decrypt, dpapi_encrypt

SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def valid_new_pin(pin: str) -> bool:
    """Returns True if a new PIN is exactly the required number of ASCII digits."""
    return len(pin) == config.PIN_DIGITS and all(c in "0123456789" for c in pin)


def hash_pin(pin: str, salt: bytes) -> str:
    """Returns the scrypt hash of a PIN with the given salt, as hex."""
    return hashlib.scrypt(pin.encode("utf-8"), salt=salt, dklen=32, **SCRYPT).hex()


def lock_seconds(level: int) -> float:
    """Returns how long the lockout of a given level (1 = first) lasts, staying at the longest step after the last one."""
    return config.PIN_LOCKOUTS_S[min(level, len(config.PIN_LOCKOUTS_S)) - 1]


class PinGate:
    """Decides whether a new challenge attempt may start, and keeps that decision across restarts."""

    def __init__(self, path: Path = config.SECURITY_PATH, encrypt=dpapi_encrypt, decrypt=dpapi_decrypt,
                 clock=time.monotonic, wall=time.time) -> None:
        """Loads the saved record; the cipher and clocks are replaceable so tests need neither Windows encryption nor waiting."""
        self.path, self.encrypt, self.decrypt, self.clock, self.wall = Path(path), encrypt, decrypt, clock, wall
        self.record = None              # None until a PIN is set
        self.broken = False             # True if the file cannot be trusted or written: everything stays strict
        self.failed = False             # an attempt failed and has not yet been cleared by PIN + pass
        self.active: set = set()        # attempts in progress (in memory)
        self.granted_until = None       # a correct PIN allows one new attempt until this time (never saved)
        self.locked_until = 0.0         # on the monotonic clock, so changing the computer clock cannot shorten it while running
        self._load()

    def _load(self) -> None:
        """Reads the saved record; a missing file means no PIN, and any other problem marks the gate as broken."""
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return
        except OSError:
            self.broken = True
            return
        try:
            data = json.loads(self.decrypt(raw).decode("utf-8"))
            record = {"salt": str(data["salt"]), "hash": str(data["hash"]), "required": data["required"],
                      "wrong": int(data["wrong"]), "level": int(data["level"]), "locked_until": float(data["locked_until"])}
            bytes.fromhex(record["salt"])
            if not isinstance(record["required"], bool) or record["wrong"] < 0 or record["level"] < 0:
                raise ValueError("bad values")
        except Exception:               # any damage at all must fail safe
            self.broken = True
            return
        self.record, self.failed = record, record["required"]
        if record["level"] > 0:         # resume a lockout, never longer than its own step even if the computer clock moved back
            left = min(max(0.0, record["locked_until"] - self.wall()), lock_seconds(record["level"]))
            self.locked_until = self.clock() + left

    def _save(self) -> bool:
        """Writes the record atomically, and marks the gate broken (strict) if it cannot."""
        if self.broken or self.record is None:
            return False
        self.record["required"] = bool(self.failed or self.active)   # an attempt in progress counts if the app is killed
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_bytes(self.encrypt(json.dumps(self.record).encode("utf-8")))
            for tries in range(10):
                try:
                    os.replace(tmp, self.path)
                    return True
                except PermissionError:
                    if tries == 9:
                        raise
                    time.sleep(0.02)
        except OSError:
            self.broken = True
        return False

    def lock_left(self) -> float:
        """Returns the seconds of PIN lockout remaining (0 if not locked)."""
        return max(0.0, self.locked_until - self.clock())

    def status(self) -> str:
        """Returns 'ok' (an attempt may start), 'pin', 'locked', 'no_pin' or 'error'."""
        if self.broken:
            return "error"
        if self.record is None:
            return "no_pin"
        if not self.failed or (self.granted_until is not None and self.clock() < self.granted_until):
            return "ok"
        return "locked" if self.lock_left() > 0 else "pin"

    def begin(self, token) -> bool:
        """Saves that an attempt is now showing its first turn, using up any PIN grant; returns False (do not show it) if that cannot be saved."""
        if self.status() != "ok":
            return False
        self.granted_until = None
        self.active.add(token)
        return self._save()

    def succeed(self, token, authorized: bool) -> bool:
        """Records a passed attempt, clearing 'PIN required' only if the PIN authorized it; returns False if that cannot be saved."""
        self.active.discard(token)
        if authorized:
            self.failed = False
        return self._save()

    def fail(self, token) -> None:
        """Records a failed attempt, so the PIN is needed before the next one."""
        self.active.discard(token)
        self.failed, self.granted_until = True, None
        self._save()

    def needs_pin_for_next(self) -> bool:
        """Returns True if the next attempt to start is one that only a correct PIN has allowed."""
        return self.failed

    def try_pin(self, pin: str) -> str:
        """Checks a typed PIN and returns 'ok', 'wrong', 'locked', 'no_pin' or 'error', counting wrong tries toward the growing lockout."""
        if self.broken:
            return "error"
        if self.record is None:
            return "no_pin"
        if self.lock_left() > 0:
            return "locked"
        self.record["wrong"] += 1       # counted and saved BEFORE checking, so killing the app cannot give a free guess
        if not self._save():
            return "error"
        if hmac.compare_digest(hash_pin(pin, bytes.fromhex(self.record["salt"])), self.record["hash"]):
            self.record.update(wrong=0, level=0, locked_until=0.0)
            self.locked_until = 0.0
            if not self._save():
                return "error"
            self.granted_until = self.clock() + config.PIN_GRANT_S
            return "ok"
        if self.record["wrong"] >= config.PIN_TRIES_PER_LOCK:
            self.record["wrong"] = 0
            self.record["level"] += 1
            duration = lock_seconds(self.record["level"])
            self.record["locked_until"] = self.wall() + duration
            self.locked_until = self.clock() + duration
            return "locked" if self._save() else "error"
        return "wrong"

    def set_pin(self, new_pin: str, old_pin: str | None = None) -> str:
        """Sets the first PIN, or changes it after checking the old one; returns 'ok', 'invalid', 'wrong', 'locked' or 'error'."""
        if self.broken:
            return "error"
        if not valid_new_pin(new_pin):
            return "invalid"
        if self.record is not None:
            result = self.try_pin(old_pin or "")
            self.granted_until = None   # changing the PIN does not itself allow an attempt
            if result != "ok":
                return result
        salt = secrets.token_bytes(16)
        base = self.record or {"required": False, "wrong": 0, "level": 0, "locked_until": 0.0}
        self.record = dict(base, salt=salt.hex(), hash=hash_pin(new_pin, salt))
        return "ok" if self._save() else "error"


class PinEntry:
    """Collects digits typed into the camera window and submits them to the gate, never showing or logging them."""

    def __init__(self, gate: PinGate) -> None:
        """Starts with an empty entry for the given gate."""
        self.gate, self.digits, self.message = gate, "", ""

    def key(self, code: int) -> None:
        """Handles one key code from cv2.waitKey: digits add, Backspace removes, Enter submits; ignored unless a PIN is wanted."""
        if self.gate.status() != "pin":
            self.digits = ""
            return
        if ord("0") <= code <= ord("9") and len(self.digits) < config.PIN_DIGITS:
            self.digits += chr(code)
        elif code == 8:
            self.digits = self.digits[:-1]
        elif code in (10, 13) and self.digits and len(self.digits) < config.PIN_DIGITS:
            self.message = "Too short"   # not sent to the gate, so it does not count as a wrong PIN
        elif code in (10, 13) and self.digits:
            result = self.gate.try_pin(self.digits)
            self.digits = ""
            self.message = {"ok": "", "wrong": "Wrong PIN", "locked": "Too many wrong PINs"}.get(result, "PIN check failed")

    def text(self) -> str:
        """Returns the line to show in the window: the PIN request with hidden digits, the lockout, or a setup problem."""
        status = self.gate.status()
        if status == "pin":
            lead = f"{self.message}. " if self.message else ""
            return f"{lead}Type {config.PIN_DIGITS}-digit PIN + Enter: {'*' * len(self.digits)}"
        if status == "locked":
            return f"PIN locked for {int(self.gate.lock_left()) + 1}s"
        if status == "no_pin":
            return "No PIN set: run set_pin.py (staying strict)"
        if status == "error":
            return "PIN file problem: staying strict"
        return ""
