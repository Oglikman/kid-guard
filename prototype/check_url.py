"""Command-line test for the policy engine: shows what would happen to a URL for a given person label (no camera needed)."""
import argparse
import sys
from datetime import datetime

from kidguard.blocklist import load_blocklist
from kidguard.decision import decide_for_label, load_policy


def main() -> int:
    """Parses a URL and label, runs the policy engine and prints the decision."""
    ap = argparse.ArgumentParser(description="Test the KidGuard policy engine")
    ap.add_argument("url")
    ap.add_argument("--label", choices=["adult", "child", "unknown", "none"], default="unknown")
    ap.add_argument("--time", help="HH:MM to simulate (default: now)")
    args = ap.parse_args()
    now = datetime.now()
    if args.time:
        h, m = args.time.split(":")
        now = now.replace(hour=int(h), minute=int(m))
    bl = load_blocklist()
    d = decide_for_label(args.url, args.label, now, load_policy(), bl)
    print(f"{d.action.upper()}  |  {d.reason}  |  profile={d.profile}  host={d.host}  (blocklist: {bl.size()} domains)")
    return 0 if d.action != "block" else 3


if __name__ == "__main__":
    sys.exit(main())
