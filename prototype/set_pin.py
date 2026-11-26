"""Sets or changes the parent PIN used after a failed head-turn challenge (PRD F15); close run.py before using it."""
from __future__ import annotations

import getpass
import sys

from kidguard import config
from kidguard.pin import PinGate, valid_new_pin


def main(gate: PinGate | None = None, ask=getpass.getpass) -> int:
    """Asks for the old PIN if there is one, then the new PIN twice with hidden typing, and saves it."""
    gate = PinGate() if gate is None else gate
    if gate.status() == "error":
        print(f"The PIN file cannot be read, so nothing was changed: {gate.path}")
        return 1
    old = None
    if gate.record is not None:
        if gate.lock_left() > 0:
            print(f"PIN entry is locked for {int(gate.lock_left()) + 1} more seconds.")
            return 1
        old = ask(f"Current {config.PIN_DIGITS}-digit PIN: ")
    new = ask(f"Type a new {config.PIN_DIGITS}-digit PIN (nothing shows as you type): ")
    if not valid_new_pin(new):
        print(f"Not saved: the PIN must be exactly {config.PIN_DIGITS} digits.")
        return 1
    if ask(f"Type the {config.PIN_DIGITS}-digit PIN again: ") != new:
        print("Not saved: the two entries did not match.")
        return 1
    result = gate.set_pin(new, old)
    print({"ok": "PIN saved.", "wrong": "Not saved: the current PIN was wrong.",
           "locked": "Not saved: too many wrong PINs, so PIN entry is now locked."}.get(result, "Not saved: the PIN file could not be written."))
    return 0 if result == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
