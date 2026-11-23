"""Enrols a family member: shows a consent prompt, captures face embeddings (no photos saved) and stores them encrypted."""
from __future__ import annotations

import argparse
import sys
import time

import cv2

from camera import open_camera
from face_engine import FaceEngine
from store import load_templates, save_templates

CONSENT_TEXT = """
KidGuard face enrollment
------------------------
This will turn on the webcam and save a numeric template of the face you enroll.
 - No photos or video are saved. Only a list of numbers, encrypted for this Windows account.
 - Nothing is uploaded; everything stays on this computer.
 - A parent/guardian must consent for any child being enrolled.
 - You can delete the stored templates at any time (delete templates.bin).
"""


def ask_consent() -> bool:
    """Prints the consent text and returns True only if the user types 'yes'."""
    print(CONSENT_TEXT)
    return input("Do you (the parent/guardian) consent? Type 'yes' to continue: ").strip().lower() == "yes"


def capture_embeddings(engine: FaceEngine, samples: int) -> list:
    """Captures embeddings from frames that contain exactly one face, spaced out, until enough are collected."""
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
            if len(faces) == 1 and now - last > 0.5:
                got.append(engine.embed(frame, faces[0]))
                last = now
            cv2.putText(frame, "CAMERA ON", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.putText(frame, f"samples {len(got)}/{samples}  (look at camera, turn head slightly; q=cancel)",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imshow("KidGuard enroll", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return got


def main() -> int:
    """Parses arguments, gets consent, captures samples and saves the person's encrypted template."""
    ap = argparse.ArgumentParser(description="Enrol a family member")
    ap.add_argument("name")
    ap.add_argument("role", choices=["adult", "child"])
    ap.add_argument("--samples", type=int, default=8)
    args = ap.parse_args()
    if not ask_consent():
        print("No consent given. Nothing was captured.")
        return 1
    embeddings = capture_embeddings(FaceEngine(), args.samples)
    if len(embeddings) < args.samples:
        print(f"Only {len(embeddings)} samples captured; not saved.")
        return 1
    templates = load_templates()
    templates[args.name] = {"role": args.role, "embeddings": [e.tolist() for e in embeddings]}
    save_templates(templates)
    print(f"Saved {args.name} as {args.role} ({len(embeddings)} samples).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
