# KidGuard: project instructions for Claude Code

Owner: Oran. Keep answers short and direct. Cite sources for any external facts. Be honest about what is verified and what is not.

## Standing rules (from the owner)
- **Every new function gets a one-sentence description** of what it does (docstring or comment), in every language.
- **PRD guardrail:** every new project or model needs a proper PRD before any code is written. `PRD.md` is the source of truth.
  Whenever it changes, regenerate `PRD.docx` from it (generator: `~/.claude/skills/new-project-kickstart/md_to_docx.js`, or `claude-config/` in the transfer bundle).
  Keep `SPEC.md` and `prompt.md` consistent with the PRD.
- Ask before choosing a face-recognition or other ML library, or making a privacy/legal trade-off. Do not claim legal compliance.
- Verify that things actually run before saying they work. Report failures and unmeasured claims plainly.

## What this is
KidGuard identifies who is at the computer (webcam, on-device) and applies strict browsing rules in Chrome/Edge unless a live, enrolled adult is present.
Read `PRD.md` first (requirements, status, risks), then `SPEC.md`, `prompt.md`, `prototype/README.md`, `extension/README.md`.

## Layout
- `prototype/`: Python app (face match, liveness, policy engine, native-messaging host, evaluation tools, tests).
- `extension/`: Chrome/Edge Manifest V3 extension (+ Node tests).
- `_archive/prototype_v0/`: first prototype, superseded.

## Practical notes (Windows)
- Use `py`, not `python`, if `python` is the Microsoft Store stub.
- Only one program can use the camera at a time; a second one gets black frames. Close `run.py` windows before running `evaluate.py`.
- Use `py run.py --seconds 600 --no-challenge` for browser tests (no window, releases the camera by itself). Without `--no-challenge` a headless run can never unlock, because the head-turn prompt (F14) and PIN entry (F15) only work in the camera window.
- The parent PIN is set by the owner with `py set_pin.py`. Never ask for it in chat, type it, or read or delete `security.bin`.
- Word locks `PRD.docx` while it is open; close it before regenerating.
- Face templates (`templates.bin`) are encrypted for one Windows user and are not portable; re-enroll on each machine.
- Thresholds in `settings.json` are camera-specific; re-measure with `evaluate.py` on each machine.
- Run tests: `cd prototype; py -m pytest -q`, and `node --test extension/tests/logic.test.mjs extension/tests/pages.test.mjs`.
