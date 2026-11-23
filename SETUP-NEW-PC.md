# Setting up KidGuard on another PC

Written 2026-11-02. Everything below assumes Windows 10/11 and PowerShell.

## 1. Install Claude Code
In PowerShell (no administrator needed):
```
irm https://claude.ai/install.ps1 | iex
```
Open a **new** terminal, then check: `claude --version`. Log in by running `claude` and following the browser prompt (needs a Pro, Max, Team,
Enterprise or Console account). Git for Windows is optional but recommended (https://git-scm.com/downloads/win). Source: https://code.claude.com/docs/en/setup

## 2. Install the tools the project needs
- **Python 3.14** (this is what the project was built and tested on; other versions are untested). Make sure the `py` launcher works: `py --version`.
- **Node.js** (only for the extension's unit tests; tested with v26).
- **Google Chrome** (the extension was verified in Chrome; Edge is untested).

## 3. Unpack the project
Unzip the bundle so the project is at, for example, `C:\Users\<you>\projects\kid-guard`. Any path works.

## 4. Install and verify
```
cd <path>\kid-guard\prototype
py -m pip install -r requirements.txt
py fetch_models.py          # downloads about 40 MB, checks SHA-256 hashes; all lines must say "hash OK"
py -m pytest -q             # expect 113 passed
cd ..
node --test extension/tests/logic.test.mjs extension/tests/pages.test.mjs    # expect 14 pass
```

## 5. Claude settings (optional but recommended)
From the `claude-config` folder in the bundle:
- Copy `skills\new-project-kickstart` into `%USERPROFILE%\.claude\skills\` (the PRD / function-description rules and the Word generator).
- Copy `statusline.ps1` to `%USERPROFILE%\.claude\`, then add this to `%USERPROFILE%\.claude\settings.json` (change `<you>`; keep any existing settings):
  ```
  "statusLine": { "type": "command", "command": "powershell -NoProfile -ExecutionPolicy Bypass -File C:/Users/<you>/.claude/statusline.ps1" }
  ```
The project's own `CLAUDE.md` already carries the standing rules, so it works even without this step.

## 6. What does NOT transfer (and why)
| Not copied | Why | What to do |
|---|---|---|
| `templates.bin` (enrolled faces) | Encrypted for one Windows user (DPAPI); also biometric data | Re-enroll: `py enroll.py <name> adult` |
| `settings.json` (thresholds) | Tuned to the old camera | Re-measure with `evaluate.py`; defaults apply meanwhile (match 0.363, liveness 0.5) |
| `eval_scores.json`, `liveness_scores.json` | Measurements from the old camera | Collect again |
| `models/*.onnx` | Large; re-downloaded and hash-checked instead | `py fetch_models.py` |
| `native_host_files/`, registry entries | Contain this PC's paths | `py install_host.py` on the new PC |
| `state.json`, `host.log` | Runtime files | Created automatically |

## 7. Run it
```
cd <path>\kid-guard\prototype
py enroll.py Oran adult                  # consent prompt, then 8 samples
py evaluate.py collect --kind genuine --who Oran --note "normal light"
py evaluate.py collect --kind impostor   # someone NOT enrolled in front of the camera
py evaluate.py report                    # then: py evaluate.py report --apply  (after reading it)
py install_host.py --dry-run             # see what changes, then:  py install_host.py
```
Then in Chrome: `chrome://extensions` -> Developer mode -> Load unpacked -> the `extension` folder. Its ID should be `cndbaefonacneegmndgbjaablgjjdmkj`.
Turn on **Allow in Incognito**. Start the camera side with `py run.py --seconds 600` and open a new tab.

## 8. Continue the work with Claude Code
```
cd <path>\kid-guard
claude
```
`CLAUDE.md` loads automatically. A good first message: "Read PRD.md and continue where we left off."

## Where things stand (end of 2026-11-02)
- Face matching works on the old PC's webcam (one enrolled adult, one stranger): see PRD section 6. Not yet tested: lookalikes, children, a second camera.
- Policy engine and Chrome extension verified by hand in Chrome, including live profile switching and automatic recovery of blocked pages.
- Liveness (anti-photo) check is built but **not yet measured**. Next step: `evaluate.py lcollect` (live, phone photo, video replay) then `lreport`.
- Not started: parent dashboard / PIN / logs / alerts, tamper protection, DNS enforcement, a real blocklist, legal and privacy review.
