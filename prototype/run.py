"""Live loop: classifies who is at the webcam and shows the resulting filter profile (PRD F2, F3, F4, F5, F8)."""
from __future__ import annotations

import argparse
import sys
import time

import cv2

from kidguard import config
from kidguard.camera import draw_camera_indicator, open_camera
from kidguard.challenge import ChallengeBank, prompt_text, yaw_ratio
from kidguard.engine import FaceEngine, best_match
from kidguard.liveness import LivenessModel, SmootherBank
from kidguard.policy import StableLabel, classify, profile_for
from kidguard.state import write_state
from kidguard.store import load_templates


def label_frame(engine: FaceEngine, frame, templates: dict, threshold: float, liveness=None, bank=None, challenge=None, now=None):
    """Returns (raw_label, per-face (name, role, score, live_score) results); an adult who has not passed the liveness check and the head-turn challenge counts as unknown (PRD F13, F14)."""
    results, adults_seen, identity_roles = [], [], []
    faces = engine.detect(frame)
    for f in faces:
        name, role, score = best_match(engine.embed(frame, f), templates, threshold)
        identity_roles.append(role)
        live_score = None
        if role == "adult":
            adults_seen.append(name)
            proven = True
            if liveness is not None:
                live_score = liveness.score(frame, f)["fused"]
                proven = bank.update(name, live_score)
            if challenge is not None:
                passed = challenge.update(name, yaw_ratio(f[4:14]), now)   # always updated, so progress is not skipped when liveness is not yet proven
                proven = proven and passed
            if not proven:
                role = None   # identity says adult, but liveness or the challenge is not proven: strict
        results.append((name, role, score, live_score))
    if bank is not None:
        bank.keep_only(adults_seen)   # an adult who left view must pass liveness again
    if challenge is not None:
        if len(faces) > 1 and any(r != "adult" for r in identity_roles):
            challenge.release_all()   # a child or stranger is in view with the adult: passes are dropped
        else:
            challenge.keep_only(adults_seen, now)   # an adult unseen for longer than the grace period must pass again
    return classify([r[1] for r in results]), results


def main() -> int:
    """Runs the live classification loop, in a window by default or for a fixed frame count with --headless."""
    ap = argparse.ArgumentParser(description="Live who-is-at-the-screen demo")
    ap.add_argument("--threshold", type=float, default=None, help="override the saved/default match threshold")
    ap.add_argument("--headless", type=int, default=0, help="run N frames without a window and print a summary")
    ap.add_argument("--seconds", type=float, default=0, help="run without a window for this many seconds, then stop and release the camera")
    ap.add_argument("--live-threshold", type=float, default=None, help="override the saved/default liveness threshold")
    ap.add_argument("--no-liveness", action="store_true", help="DEVELOPMENT ONLY: skip the anti-spoofing check (a photo of an adult can then unlock)")
    ap.add_argument("--no-challenge", action="store_true", help="DEVELOPMENT ONLY: skip the head-turn challenge (F14)")
    args = ap.parse_args()
    headless = bool(args.headless or args.seconds)
    threshold = args.threshold if args.threshold is not None else config.load_threshold()

    templates = load_templates()
    if not templates:
        print("Nobody is enrolled yet, so every face will be 'unknown' (strict). Run enroll.py first.")
    print(f"Match threshold: {threshold}")
    liveness = bank = None
    if args.no_liveness:
        print("WARNING: liveness check is OFF (development only): a photo of an adult can unlock the normal profile.")
    else:
        live_thr = args.live_threshold if args.live_threshold is not None else config.load_liveness_threshold()
        try:
            liveness, bank = LivenessModel(), SmootherBank(live_thr)
        except FileNotFoundError as e:
            print(f"{e}\nThe liveness models are required (PRD F13). Use --no-liveness only for development.")
            write_state("none")
            return 2
        print(f"Liveness threshold: {live_thr}")
    challenge = None
    if args.no_challenge:
        print("WARNING: head-turn challenge is OFF (development only): a still photo that passes liveness can unlock the normal profile.")
    else:
        challenge = ChallengeBank()
        print("Head-turn challenge is ON: an enrolled adult must turn their head when asked before the normal profile unlocks.")
        if headless:
            print("NOTE: the prompt is only shown in the camera window, so a headless run (--seconds / --headless) cannot be unlocked; use --no-challenge for headless development.")
    engine, stable = FaceEngine(), StableLabel(config.UNLOCK_FRAMES)
    try:
        cap = open_camera()
    except RuntimeError as e:
        print(f"Camera error -> STRICT profile. {e}")
        write_state("none")
        return 2

    counts, n, t0 = {}, 0, time.time()
    last_written, last_label = 0.0, None
    try:
        while True:
            ok, frame = cap.read()
            results = []
            if ok:
                raw, results = label_frame(engine, frame, templates, threshold, liveness, bank, challenge)
            else:
                raw = "none"  # camera read failure is treated like nobody present (fail-safe)
            label = stable.update(raw)
            if label != last_label or time.time() - last_written >= 1.0:   # publish for the browser: on change, and as a 1 s heartbeat
                write_state(label)
                last_written, last_label = time.time(), label
            n += 1
            counts[label] = counts.get(label, 0) + 1
            if headless:
                if (args.headless and n >= args.headless) or (args.seconds and time.time() - t0 >= args.seconds):
                    break
                continue
            if not ok:
                continue
            profile = profile_for(label)
            color = (0, 200, 0) if profile == "normal" else (0, 0, 255)
            draw_camera_indicator(frame)
            cv2.putText(frame, f"{label.upper()} -> {profile.upper()} profile", (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            for i, (name, role, score, live) in enumerate(results):
                text = f"{name or 'unknown'}  {score:.2f}" + ("" if live is None else f"  live {live:.2f}")
                if name is not None and role is None:
                    text += "  NOT LIVE"
                cv2.putText(frame, text, (10, 86 + 22 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            if challenge is not None:
                for j, p in enumerate(p for p in challenge.prompts().values() if prompt_text(p)):
                    cv2.putText(frame, prompt_text(p), (10, 140 + 30 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.imshow("KidGuard", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        write_state("none")   # when the camera loop ends, the browser must fall back to strict
    dt = time.time() - t0
    print(f"{n} frames in {dt:.1f}s ({n / dt:.1f} fps). Smoothed labels: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
