"""Deletes all stored face templates after confirmation (PRD F12)."""
import sys

from kidguard.store import delete_all


def main() -> int:
    """Asks for confirmation, then deletes the templates file and reports what happened."""
    if input("Delete ALL enrolled face templates? Type 'yes' to confirm: ").strip().lower() != "yes":
        print("Cancelled. Nothing deleted.")
        return 1
    print("Templates deleted." if delete_all() else "No templates were stored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
