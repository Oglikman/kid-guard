# KidGuard — Build Prompt

You are building **KidGuard (working name)**, a Windows child-protection app that uses the webcam to detect who is at the computer and applies matching browsing rules in Chrome/Edge. Read `SPEC.md` in this folder first; it is the source of truth for decisions.

## Goal
Protect underage children from 18+ sites and other harmful content, even when they use a parent's unlocked computer, by switching filter rules based on the person actually present.

## Fixed decisions
- Platform: Windows desktop app + Chrome/Edge extension.
- Customer: families/parents.
- Detection: enrolled faces only (no age estimation in v1). Roles: adult or child.
- Harm scope: v1 = adult, gambling, drugs. Violence/self-harm = v2. Chat/grooming = v3. Do not build v2/v3 now.
- Business model: undecided. Do not add payment or pricing code.

## Hard requirements
1. **On-device only.** Never upload camera frames or face data. No network calls with biometric data.
2. **Encrypted storage** of face templates (Windows DPAPI or equivalent). Store templates, not photos.
3. **Fail safe.** Unknown person, no face, covered camera, or camera error -> strict child profile.
4. **Liveness check** so a photo or screen cannot pass as an adult: anti-spoofing score plus an active head-turn challenge (PRD F13, F14; design in `DESIGN-liveness-challenge.md`). 3 random turns; a wrong-way turn fails; after any failure require the parent PIN and 3 new turns, with a growing lockout for wrong PINs (PRD F15).
5. **Visible indicator** whenever the camera is active.
6. **Parent PIN** required to disable protection, change roles, or uninstall; alert/log if the extension is removed.
7. **Explicit parental consent** screen before any face enrollment.

## Architecture
- **Companion app** (suggest Python or Tauri/Electron; justify your choice): camera capture, face match, policy engine, local log store.
- **Browser extension** (Manifest V3, Chrome/Edge): blocks URLs per policy; talks to the companion app via native messaging.
- **Policy engine**: inputs = person class (adult/child/unknown/none), URL category, time of day, parent overrides. Output = allow / warn / block, with a reason string.
- **Blocklist/category data**: start with a small local list in a documented file format; make the source swappable.
- **Log**: timestamp, person class, URL (domain only by default), action, reason.

## Build order (stop and show me after each step)
1. Prototype: webcam presence + enrolled-face match in a small Windows app, running locally. Report accuracy and latency honestly.
2. Policy engine with a hard-coded blocklist and unit tests.
3. Chrome/Edge extension + native messaging to the companion app.
4. Parent dashboard (logs, alerts, PIN).
5. Tamper protection and DNS-level enforcement for other browsers.

## Known bypasses to design against
Other browsers, incognito, VPN, encrypted DNS (DoH), covering the camera, photo spoofing, uninstalling the extension. For each, state what v1 covers and what it does not.

## Working rules
- Keep answers short and direct; cite sources for any external facts (library accuracy, laws).
- Ask before choosing a face-recognition library or making any legal/privacy trade-off.
- Be honest about limits: if something is only partly protected, say so.
- Do not claim legal compliance. Flag items needing a privacy-law review.
- Every new function must include a one-sentence description of what it does (docstring or comment).
- Write tests for the policy engine; verify the prototype actually runs before reporting it works.

## Open items to raise with me
Product name, pricing, face-recognition library, Windows camera-permission behavior, competitor/legal scan.
