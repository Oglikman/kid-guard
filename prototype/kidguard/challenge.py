"""Active head-turn challenge (PRD F14): an enrolled adult must make several turns to random sides before the normal profile unlocks.

Head yaw is estimated from YuNet's landmarks. On a real head the nose sits in front of the eye plane, so the nose moves sideways relative to
the eyes when the head turns; on a flat photo or screen it does not (except for perspective effects). Design: DESIGN-liveness-challenge.md.
Everything here is pure logic with an injectable clock and random choice, so it is testable without a camera.
"""
from __future__ import annotations

import secrets
import time

import numpy as np

from . import config

DIRECTIONS = ("left", "right")


def yaw_ratio(landmarks):
    """Returns the nose offset from the eye midpoint divided by the eye distance (about 0 facing the camera), or None if the landmarks are unusable.

    `landmarks` is YuNet's x, y pairs for right eye, left eye, nose tip, ... (at least the first three points).
    """
    try:
        pts = np.asarray(landmarks, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if pts.size < 6 or not np.isfinite(pts[:6]).all():
        return None
    right_eye_x, left_eye_x, nose_x = pts[0], pts[2], pts[4]
    eye_dist = left_eye_x - right_eye_x
    if eye_dist <= 1e-6:          # eyes in the wrong order or on top of each other: not a usable face pose
        return None
    return float((nose_x - (right_eye_x + left_eye_x) / 2.0) / eye_dist)


def turn_progress(yaw: float, direction: str, sign: float = config.YAW_SIGN_USER_LEFT) -> float:
    """Returns how far the head is turned toward `direction` (positive = toward it, negative = the other way)."""
    signed = yaw * sign
    return signed if direction == "left" else -signed


class HeadTurnChallenge:
    """One person's attempt: several random turns in a row, each facing the camera first; a wrong-side turn, timeout or abandonment fails it."""

    def __init__(self, choose=None, gate=None) -> None:
        """Creates an idle challenge; `choose` picks each side (default: cryptographically random), `gate` is the PinGate (None only for measurement and tests)."""
        self.choose = choose or (lambda: secrets.choice(DIRECTIONS))
        self.gate = gate
        self.state = "idle"             # idle | prompting | passed | failed | pin | locked | no_pin | error
        self.direction = None
        self.phase = "neutral"          # neutral | turn (only meaningful while prompting)
        self.step = 0                   # turns completed in this attempt
        self.count = 0
        self.wrong_count = 0
        self.revealed = False           # True once the first turn has been shown: from then on, abandoning is a failure
        self.authorized = False         # True if a correct PIN is what allowed this attempt
        self.fail_reason = None         # wrong_way | timeout | abandoned | other_face
        self.started = 0.0
        self.passed_at = 0.0
        self.last_seen = 0.0

    def _start(self, now: float) -> None:
        """Begins a new attempt at its first step."""
        self.state, self.step, self.revealed, self.fail_reason = "prompting", 0, False, None
        self.authorized = bool(self.gate is not None and self.gate.needs_pin_for_next())
        self._next_step(now)

    def _next_step(self, now: float) -> None:
        """Picks the next random side and restarts the step timer, waiting for the person to face the camera first."""
        self.direction, self.phase, self.count, self.wrong_count, self.started = self.choose(), "neutral", 0, 0, now

    def fail(self, reason: str) -> None:
        """Ends the attempt as failed and tells the gate, so the PIN is needed before another one."""
        self.state, self.fail_reason, self.direction, self.count, self.revealed = "failed", reason, None, 0, False
        if self.gate is not None:
            self.gate.fail(self)

    def update(self, yaw, now: float | None = None) -> bool:
        """Feeds one frame's yaw ratio (None if unusable) for this identified adult and returns True once all turns have been passed."""
        now = time.monotonic() if now is None else now
        self.last_seen = now
        if self.state == "passed":
            if now - self.passed_at < config.CHALLENGE_REVERIFY_S:
                return True
            self.state = "idle"         # the pass expired: the adult must prove themselves again
        if self.state != "prompting":
            status = "ok" if self.gate is None else self.gate.status()
            if status != "ok":
                self.state = status     # pin | locked | no_pin | error: stay strict
                return False
            self._start(now)
        if now - self.started > config.CHALLENGE_TIMEOUT_S:
            self.fail("timeout")
            return False
        if yaw is None:
            return False
        if self.phase == "neutral":
            self.count = self.count + 1 if abs(yaw) < config.YAW_NEUTRAL else 0
            if self.count >= config.CHALLENGE_NEUTRAL_FRAMES:
                if not self.revealed and self.gate is not None and not self.gate.begin(self):
                    self.state = self.gate.status()   # could not record the attempt (or the PIN grant ran out): do not show a turn
                    return False
                self.revealed, self.phase, self.count = True, "turn", 0
            return False
        progress = turn_progress(yaw, self.direction)
        self.count = self.count + 1 if progress >= config.YAW_TURN else 0
        self.wrong_count = self.wrong_count + 1 if progress <= -config.YAW_TURN else 0
        if self.wrong_count >= config.CHALLENGE_FRAMES:
            self.fail("wrong_way")
        elif self.count >= config.CHALLENGE_FRAMES:
            self.step += 1
            if self.step < config.CHALLENGE_STEPS:
                self._next_step(now)
            elif self.gate is not None and not self.gate.succeed(self, self.authorized):
                self.state = self.gate.status()
            else:
                self.state, self.passed_at, self.revealed = "passed", now, False
                return True
        return False

    def release(self, reason: str = "abandoned") -> None:
        """Drops a pass (no penalty) or an unfinished attempt, which counts as a failure once its first turn has been shown."""
        if self.state == "prompting" and self.revealed:
            self.fail(reason)
        elif self.state in ("prompting", "passed"):
            self.state, self.direction, self.count = "idle", None, 0

    def prompt(self, now: float | None = None) -> dict:
        """Returns what the screen should show: state, requested side, phase, step number, seconds left and why it last failed."""
        now = time.monotonic() if now is None else now
        left = None
        if self.state == "prompting":
            left = max(0.0, config.CHALLENGE_TIMEOUT_S - (now - self.started))
        return {"state": self.state, "direction": self.direction, "phase": self.phase, "step": self.step + 1,
                "seconds_left": left, "fail_reason": self.fail_reason}


class ChallengeBank:
    """Keeps one HeadTurnChallenge per enrolled adult and releases a person who leaves view or is replaced by another face."""

    def __init__(self, choose=None, gate=None) -> None:
        """Creates an empty bank; `choose` and `gate` are passed on to each challenge."""
        self.choose, self.gate = choose, gate
        self._by_name: dict = {}
        self._other_face: dict = {}     # consecutive frames showing only other faces, per person

    def update(self, name: str, yaw, now: float | None = None) -> bool:
        """Feeds one frame's yaw for a person and returns whether they currently count as having passed the challenge."""
        ch = self._by_name.setdefault(name, HeadTurnChallenge(self.choose, self.gate))
        return ch.update(yaw, now)

    def keep_only(self, names, now: float | None = None, face_in_view: bool = False) -> None:
        """Releases anyone missing longer than the grace period, or replaced by another face for several frames in a row."""
        now = time.monotonic() if now is None else now
        present = set(names)
        for n, ch in self._by_name.items():
            if n in present:
                self._other_face[n] = 0
                continue
            self._other_face[n] = self._other_face.get(n, 0) + 1 if face_in_view else 0
            if ch.state == "prompting" and ch.revealed and self._other_face[n] >= config.CHALLENGE_FRAMES:
                ch.release("other_face")
            elif now - ch.last_seen > config.CHALLENGE_GRACE_S:
                ch.release()

    def release_all(self, reason: str = "abandoned") -> None:
        """Releases everyone's pass or progress at once (used when a child or stranger joins, or the app closes)."""
        for ch in self._by_name.values():
            ch.release(reason)

    def prompts(self, now: float | None = None) -> dict:
        """Returns {name: prompt dict} for everyone with a challenge, for display."""
        return {n: ch.prompt(now) for n, ch in self._by_name.items()}


class LockedChallenge(ChallengeBank):
    """Used when no window can show prompts: nobody can pass, and no attempt is started that could count as a failure."""

    def update(self, name: str, yaw, now: float | None = None) -> bool:
        """Always returns False without starting an attempt."""
        return False


def prompt_text(p: dict) -> str:
    """Turns a prompt dict into the one-line instruction (or status) shown to the user."""
    if p["state"] == "prompting":
        if p["phase"] == "neutral":
            return f"{p['step']}/{config.CHALLENGE_STEPS}: look at the camera ({p['seconds_left']:.0f}s)"
        return f"{p['step']}/{config.CHALLENGE_STEPS}: turn to YOUR {p['direction'].upper()} ({p['seconds_left']:.0f}s)"
    if p["state"] == "failed":
        return "Challenge failed"
    if p["state"] == "passed":
        return "Challenge passed"
    return ""
