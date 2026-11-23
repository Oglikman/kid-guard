"""Fail-safe policy: who is present -> label -> filter profile (PRD F3, F4, F5)."""
from __future__ import annotations


def classify(face_roles: list) -> str:
    """Maps per-face roles (adult/child, or None for unknown) to adult, child, unknown or none, strictest first."""
    if not face_roles:
        return "none"
    if any(r is None for r in face_roles):
        return "unknown"
    if any(r == "child" for r in face_roles):
        return "child"
    return "adult"


def profile_for(label: str) -> str:
    """Returns 'normal' only for the label 'adult'; every other label, including errors, gets 'strict'."""
    return "normal" if label == "adult" else "strict"


class StableLabel:
    """Smooths per-frame labels: locks to a stricter label immediately, unlocks to adult only after several consecutive adult frames."""

    def __init__(self, unlock_frames: int) -> None:
        """Starts in the strictest state ('none') so nothing is unlocked until proven."""
        self.unlock_frames = unlock_frames
        self.current = "none"
        self._adult_run = 0

    def update(self, label: str) -> str:
        """Feeds one frame's label and returns the smoothed label."""
        if label == "adult":
            self._adult_run += 1
            if self._adult_run >= self.unlock_frames:
                self.current = "adult"
        else:
            self._adult_run = 0
            self.current = label
        return self.current
