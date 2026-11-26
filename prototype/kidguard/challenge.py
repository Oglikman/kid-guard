"""Active head-turn challenge (PRD F14): an enrolled adult must turn their head to a random side before the normal profile unlocks.

Head yaw is estimated from YuNet's landmarks. On a real head the nose sits in front of the eye plane, so the nose moves sideways relative to
the eyes when the head turns; on a flat photo or screen it does not (except for perspective effects). Design: DESIGN-liveness-challenge.md.
Everything here is pure logic with an injectable clock and random choice, so it is testable without a camera.
"""
from __future__ import annotations

import math
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
    """One person's challenge: idle -> prompting (neutral phase, then turn phase) -> passed, with cooldown and lockout after failures."""

    def __init__(self, choose=None) -> None:
        """Creates an idle challenge; `choose` picks the direction (default: cryptographically random left/right)."""
        self.choose = choose or (lambda: secrets.choice(DIRECTIONS))
        self.state = "idle"             # idle | prompting | passed | cooldown | locked
        self.direction = None
        self.phase = "neutral"          # neutral | turn (only meaningful while prompting)
        self.count = 0
        self.started = 0.0
        self.until = 0.0                # end of cooldown / lockout
        self.passed_at = 0.0
        self.last_seen = 0.0
        self.fails: list = []           # times of recent failed attempts (kept when the adult leaves view, so leaving cannot reset a lockout)

    def _fail(self, now: float) -> None:
        """Records a failed attempt and moves to cooldown, or to lockout after too many recent failures."""
        self.fails = [t for t in self.fails if now - t < config.CHALLENGE_FAIL_WINDOW_S] + [now]
        if len(self.fails) >= config.CHALLENGE_MAX_FAILS:
            self.state, self.until, self.fails = "locked", now + config.CHALLENGE_LOCKOUT_S, []
        else:
            self.state, self.until = "cooldown", now + config.CHALLENGE_COOLDOWN_S
        self.direction, self.count = None, 0

    def update(self, yaw, now: float | None = None) -> bool:
        """Feeds one frame's yaw ratio (None if unusable) for this identified adult and returns True once the challenge has been passed."""
        now = time.monotonic() if now is None else now
        self.last_seen = now
        if self.state == "passed":
            if now - self.passed_at < config.CHALLENGE_REVERIFY_S:
                return True
            self.state = "idle"         # the pass expired: the adult must prove themselves again
        if self.state in ("cooldown", "locked"):
            if now < self.until:
                return False
            self.state = "idle"
        if self.state == "idle":
            self.state, self.direction, self.phase, self.count, self.started = "prompting", self.choose(), "neutral", 0, now
        if now - self.started > config.CHALLENGE_TIMEOUT_S:
            self._fail(now)
            return False
        if yaw is None:
            return False
        if self.phase == "neutral":
            self.count = self.count + 1 if abs(yaw) < config.YAW_NEUTRAL else 0
            if self.count >= config.CHALLENGE_NEUTRAL_FRAMES:
                self.phase, self.count = "turn", 0
        else:
            self.count = self.count + 1 if turn_progress(yaw, self.direction) >= config.YAW_TURN else 0
            if self.count >= config.CHALLENGE_FRAMES:
                self.state, self.passed_at = "passed", now
                return True
        return False

    def release(self) -> None:
        """Drops a pass or in-progress attempt (the adult left view), but keeps cooldown, lockout and failure history."""
        if self.state in ("prompting", "passed"):
            self.state, self.direction, self.count = "idle", None, 0

    def prompt(self, now: float | None = None) -> dict:
        """Returns what the screen should show: state, requested direction, phase and seconds left (or None)."""
        now = time.monotonic() if now is None else now
        left = None
        if self.state == "prompting":
            left = max(0.0, config.CHALLENGE_TIMEOUT_S - (now - self.started))
        elif self.state in ("cooldown", "locked"):
            left = max(0.0, self.until - now)
        return {"state": self.state, "direction": self.direction, "phase": self.phase, "seconds_left": left}


class ChallengeBank:
    """Keeps one HeadTurnChallenge per enrolled adult and drops a person's progress after they have been out of view for a grace period."""

    def __init__(self, choose=None) -> None:
        """Creates an empty bank; `choose` is passed on to each challenge (tests use it to fix the direction)."""
        self.choose = choose
        self._by_name: dict = {}

    def update(self, name: str, yaw, now: float | None = None) -> bool:
        """Feeds one frame's yaw for a person and returns whether they currently count as having passed the challenge."""
        ch = self._by_name.setdefault(name, HeadTurnChallenge(self.choose))
        return ch.update(yaw, now)

    def keep_only(self, names, now: float | None = None) -> None:
        """Releases anyone not in `names` who has been unseen for longer than the grace period, so they must pass again."""
        now = time.monotonic() if now is None else now
        for n, ch in self._by_name.items():
            if n not in set(names) and now - ch.last_seen > config.CHALLENGE_GRACE_S:
                ch.release()

    def release_all(self) -> None:
        """Releases everyone's pass or progress at once (used when more than one face is in view)."""
        for ch in self._by_name.values():
            ch.release()

    def prompts(self, now: float | None = None) -> dict:
        """Returns {name: prompt dict} for everyone with a challenge, for display."""
        return {n: ch.prompt(now) for n, ch in self._by_name.items()}


def prompt_text(p: dict) -> str:
    """Turns a prompt dict into the one-line instruction (or status) shown to the user."""
    if p["state"] == "prompting":
        if p["phase"] == "neutral":
            return f"Look at the camera ({p['seconds_left']:.0f}s)"
        return f"Turn your head to YOUR {p['direction'].upper()} ({p['seconds_left']:.0f}s)"
    if p["state"] == "cooldown":
        return f"Challenge failed. Try again in {math.ceil(p['seconds_left'])}s"
    if p["state"] == "locked":
        return f"Too many failures. Locked for {math.ceil(p['seconds_left'])}s"
    if p["state"] == "passed":
        return "Challenge passed"
    return ""
