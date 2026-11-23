"""Enrols a family member after explicit consent, storing only an encrypted face template (PRD F1)."""
from __future__ import annotations

import argparse
import sys
import time

import cv2

from kidguard import config
from kidguard.camera import draw_camera_indicator, open_camera
from kidguard.engine import FaceEngine
from kidguard.store import load_templates, save_templates

CONSENT_TEXT = """
KidGuard face enrollment
------------------------
This turns on the webcam and saves a numeric template of the face being enrolled.
 - No photos or video are saved. Only a list of numbers, encrypted for this Windows account.
 - Nothing is uploaded; everything stays on this computer.
 - A parent/guardian must consent for any child being enrolled.
 - Delete everything at any time with: py delete_templates.py
"""


def ask_consent() -> bool:
    """Prints the consent text and returns True only if the parent/guardian types 'yes'."""
    print(CONSENT_TEXT)
    return input("Does the parent/guardian consent? Type 'yes' to continue: ").strip().lower() == "yes"


def capture_embeddings(engine: FaceEngine, samples: int) -> list:
    """Collects embeddings from frames with exactly one reasonably large face, spaced half a second apart."""
    cap = open_camera()
    got, last = [], 0.0
    try:
        while len(got) < samples:
            ok, frame = cap.read()
            if not ok:
                print("Camera read failed.", file=sys.stderr)
                break
            faces = engine.detect(frame)
            now = time.time()
            if len(faces) == 1 and faces[0][2] >= config.MIN_FACE_PX and now - last > 0.5:
                got.append(engine.embed(frame, faces[0]))
                last = now
            draw_camera_indicator(frame)
            cv2.putText(frame, f"samples {len(got)}/{samples}: look at the camera, turn your head slightly (q = cancel)",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            cv2.imshow("KidGuard enroll", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return got


def main() -> int:
    """Parses arguments, obtains consent, captures samples and saves the person's encrypted template."""
    ap = argparse.ArgumentParser(description="Enrol a family member")
    ap.add_argument("name")
    ap.add_argument("role", choices=["adult", "child"])
    ap.add_argument("--samples", type=int, default=config.ENROLL_SAMPLES)
    args = ap.parse_args()
    if not ask_consent():
        print("No consent given. Nothing was captured.")
        return 1
    embeddings = capture_embeddings(FaceEngine(), args.samples)
    if len(embeddings) < args.samples:
        print(f"Only {len(embeddings)} of {args.samples} samples captured; nothing saved.")
        return 1
    templates = load_templates()
    templates[args.name] = {"role": args.role, "embeddings": [e.tolist() for e in embeddings]}
    save_templates(templates)
    print(f"Saved {args.name} as {args.role} ({len(embeddings)} samples).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
