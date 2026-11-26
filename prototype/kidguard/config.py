"""Paths and tunable settings for the prototype."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DETECTOR_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"
TEMPLATES_PATH = ROOT / "templates.bin"
SETTINGS_PATH = ROOT / "settings.json"
EVAL_LOG_PATH = ROOT / "eval_scores.json"
BLOCKLIST_DIR = ROOT / "blocklists"
POLICY_PATH = ROOT / "policy.json"
STATE_PATH = Path(os.environ.get("KIDGUARD_STATE") or ROOT / "state.json")   # written by run.py, read by the native host (env override is for tests)
STATE_MAX_AGE_S = 5.0                 # state older than this is treated as 'nobody present' (fail-safe)
HOST_NAME = "com.kidguard.host"
HOST_LOG_PATH = ROOT / "host.log"     # debug log of what the extension asked and what the host answered (no URLs)

# SFace's documented cosine threshold; unverified for this setup until evaluate.py report is run (PRD section 6).
DEFAULT_THRESHOLD = 0.363
UNLOCK_FRAMES = 5          # consecutive adult frames needed before the normal profile unlocks (PRD F5)
DETECT_SCORE = 0.9         # minimum detector confidence for a face
MIN_FACE_PX = 80           # enrollment ignores faces narrower than this many pixels
ENROLL_SAMPLES = 8
LIVENESS_EVAL_PATH = ROOT / "liveness_scores.json"
DEFAULT_LIVENESS_THRESHOLD = 0.5   # mean 'real' probability of the two MiniFASNet models; unverified until lreport is run
LIVENESS_WINDOW = 5                # frames averaged before deciding live / not live
LIVENESS_MIN_FRAMES = 3            # frames needed before an adult can count as live

# Active head-turn challenge (PRD F14; design in DESIGN-liveness-challenge.md). All values are untuned starting guesses.
CHALLENGE_EVAL_PATH = ROOT / "challenge_scores.json"
YAW_NEUTRAL = 0.10                 # |yaw ratio| below this counts as facing the camera
YAW_TURN = 0.25                    # yaw ratio beyond this, in the requested direction, counts as turned
CHALLENGE_NEUTRAL_FRAMES = 1       # frames facing the camera needed before a turn counts (was 3; a quick pass through the centre could be missed)
CHALLENGE_FRAMES = 3               # consecutive turned frames needed to pass
CHALLENGE_TIMEOUT_S = 6.0          # time allowed from the prompt to a completed turn
CHALLENGE_COOLDOWN_S = 5.0         # wait after a failed attempt before the next one
CHALLENGE_MAX_FAILS = 3            # failed attempts within CHALLENGE_FAIL_WINDOW_S that trigger a lockout
CHALLENGE_FAIL_WINDOW_S = 60.0
CHALLENGE_LOCKOUT_S = 60.0
CHALLENGE_GRACE_S = 3.0            # an adult unseen for longer than this loses their challenge progress / pass
CHALLENGE_REVERIFY_S = 1800.0      # a pass expires after this long even if the adult stays in view (30 min)
YAW_SIGN_USER_LEFT = 1.0           # +1: turning to the user's own left moves the nose toward the right of the (unmirrored) image; set -1 if the camera is mirrored


def load_threshold(path: Path = SETTINGS_PATH) -> float:
    """Returns the saved match threshold, or the default if none has been saved."""
    try:
        return float(json.loads(Path(path).read_text())["threshold"])
    except (OSError, ValueError, KeyError):
        return DEFAULT_THRESHOLD


def _read_settings(path: Path) -> dict:
    """Returns the settings file as a dict, or an empty dict if it is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_threshold(value: float, path: Path = SETTINGS_PATH) -> None:
    """Saves the chosen match threshold to the settings file, keeping any other saved settings."""
    data = _read_settings(path)
    data["threshold"] = round(float(value), 4)
    Path(path).write_text(json.dumps(data))


def load_liveness_threshold(path: Path = SETTINGS_PATH) -> float:
    """Returns the saved liveness threshold, or the default if none has been saved."""
    try:
        return float(_read_settings(path)["liveness_threshold"])
    except (KeyError, ValueError, TypeError):
        return DEFAULT_LIVENESS_THRESHOLD


def save_liveness_threshold(value: float, path: Path = SETTINGS_PATH) -> None:
    """Saves the chosen liveness threshold to the settings file, keeping any other saved settings."""
    data = _read_settings(path)
    data["liveness_threshold"] = round(float(value), 4)
    Path(path).write_text(json.dumps(data))
