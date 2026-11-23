"""Webcam access helper."""
from __future__ import annotations

import cv2


def open_camera(index: int = 0) -> cv2.VideoCapture:
    """Opens the webcam, trying the DirectShow backend first and falling back to the default, and raises if neither works."""
    for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            return cap
        cap.release()
    raise RuntimeError("Could not open the webcam (is another app using it, or is camera access blocked in Windows privacy settings?)")
