"""Dev helper: publishes a fixed label every second so the browser extension can be tested without the camera (Ctrl+C to stop)."""
import argparse
import sys
import time

from kidguard.state import VALID_LABELS, write_state


def main() -> int:
    """Writes the chosen label once a second until interrupted, then writes 'none' so the browser falls back to strict."""
    ap = argparse.ArgumentParser(description="Pretend the camera sees this label")
    ap.add_argument("label", choices=VALID_LABELS)
    ap.add_argument("--seconds", type=float, default=0, help="stop by itself after this many seconds (default: run until Ctrl+C)")
    args = ap.parse_args()
    label, end = args.label, (time.time() + args.seconds if args.seconds else None)
    print(f"Publishing '{label}' every second. Press Ctrl+C to stop (this is a TEST tool: it bypasses the camera).")
    try:
        while end is None or time.time() < end:
            write_state(label)
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        write_state("none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
