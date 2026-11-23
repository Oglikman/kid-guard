"""Webcam access."""
from __future__ import annotations

import cv2


def open_camera(index: int = 0) -> cv2.VideoCapture:
    """Opens the webcam (DirectShow first, then default backend) and raises a clear error if neither works."""
    for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            return cap
        cap.release()
    raise RuntimeError("Could not open the webcam (in use by another app, or blocked in Windows camera privacy settings).")


def draw_camera_indicator(frame) -> None:
    """Draws the always-visible 'CAMERA ON' indicator onto a frame (PRD F8)."""
    cv2.circle(frame, (18, 20), 7, (0, 0, 255), -1)
    cv2.putText(frame, "CAMERA ON", (32, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
