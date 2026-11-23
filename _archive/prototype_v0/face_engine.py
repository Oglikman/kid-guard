"""Face detection, embedding and matching (OpenCV YuNet + SFace), plus the fail-safe classifier."""
from __future__ import annotations

from pathlib import Path

import numpy as np

MODELS_DIR = Path(__file__).parent / "models"
DETECTOR_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# SFace's documented cosine-similarity threshold; tune from benchmark results.
DEFAULT_THRESHOLD = 0.363


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Returns the cosine similarity between two embedding vectors."""
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def best_match(embedding: np.ndarray, templates: dict, threshold: float = DEFAULT_THRESHOLD):
    """Returns (name, role, score) of the best enrolled match, or (None, None, best_score) if below threshold."""
    best_name, best_role, best_score = None, None, -1.0
    for name, entry in templates.items():
        for tmpl in entry["embeddings"]:
            score = cosine_similarity(embedding, tmpl)
            if score > best_score:
                best_name, best_role, best_score = name, entry["role"], score
    if best_score < threshold:
        return None, None, best_score
    return best_name, best_role, best_score


def classify(face_roles: list) -> str:
    """Maps per-face roles (adult/child/None for unknown) to adult, child, unknown or none, strictest first."""
    if not face_roles:
        return "none"
    if any(r is None for r in face_roles):
        return "unknown"
    if any(r == "child" for r in face_roles):
        return "child"
    return "adult"


def profile_for(label: str) -> str:
    """Returns 'normal' only when the label is adult; every other label (fail-safe) gets 'strict'."""
    return "normal" if label == "adult" else "strict"


class StableLabel:
    """Smooths per-frame labels: locks to a stricter label immediately but needs several consecutive 'adult' frames to unlock."""

    def __init__(self, unlock_frames: int = 5) -> None:
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


class FaceEngine:
    """Wraps the YuNet detector and SFace recognizer behind a small interface."""

    def __init__(self, score_threshold: float = 0.9) -> None:
        """Loads both ONNX models and raises a clear error if they have not been downloaded."""
        import cv2

        for m in (DETECTOR_MODEL, RECOGNIZER_MODEL):
            if not m.exists():
                raise FileNotFoundError(f"{m.name} missing; run: py fetch_models.py")
        self._cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(str(DETECTOR_MODEL), "", (320, 320), score_threshold, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(RECOGNIZER_MODEL), "")

    def detect(self, frame: np.ndarray) -> list:
        """Returns the detected face rows (box, landmarks, score) for a BGR frame, or an empty list."""
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        return [] if faces is None else list(faces)

    def embed(self, frame: np.ndarray, face_row: np.ndarray) -> np.ndarray:
        """Returns the aligned, L2-normalised embedding for one detected face."""
        aligned = self.recognizer.alignCrop(frame, face_row)
        feat = np.asarray(self.recognizer.feature(aligned), dtype=np.float32).ravel()
        norm = np.linalg.norm(feat)
        return feat / norm if norm else feat
