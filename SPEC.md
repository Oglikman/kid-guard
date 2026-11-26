# KidGuard (working name) — v1 Spec

Webcam-aware child-protection app: detects WHO is at the computer and applies the matching browsing rules.

## Decisions (from planning Q&A)
| # | Question | Decision |
|---|----------|----------|
| 1 | Platform | Windows desktop + Chrome/Edge |
| 2 | Customer | Families / parents |
| 3 | Who is at the screen | Enrolled faces (on-device, encrypted templates) |
| 4 | Harm scope | Adult, gambling, drugs, violence/gore/self-harm, chat/grooming (phased, see below) |
| 5 | Business model | Not decided yet |

## Differentiator
Existing filters lock a device or profile. KidGuard switches rules based on the person actually present, so a child on a parent's unlocked laptop is still protected.

## Pipeline
1. **Presence** — webcam frame, processed locally, never uploaded.
2. **Identify** — match against enrolled family faces: adult / child / unknown / no face.
3. **Policy engine** — inputs: person class, time, URL category, parent overrides. Output: allow / warn / block.
4. **Enforcement** — browser extension (Chrome/Edge) + OS-level DNS filter to cover other browsers.
5. **Alert & log** — parent notification and a log of blocks with reasons.

## Fail-safe rules
- Unknown person, no face, camera covered, or camera error -> strict (child) profile.
- Liveness check so a photo cannot pass as an adult: an anti-spoofing score plus an active head-turn challenge (PRD F13, F14). Built 2026-11-26, only first camera checks (PRD section 6): 3 random turns, a wrong-way turn fails, and after any failure the parent PIN plus 3 new turns (PRD F15).
- Tamper protection: parent PIN to disable, alert if the app or extension is removed.

## Harm categories by phase
- **v1:** adult, gambling, drugs (blocklists + category feeds).
- **v2:** violence/gore/self-harm (on-device page-content classification; self-harm needs a careful parent-alert design, not just a block).
- **v3:** chat/grooming risk (conversation analysis; highest privacy and accuracy risk).

## v1 scope
- Windows companion app (camera + policy engine) and Chrome/Edge extension.
- Face enrollment with adult/child roles.
- Blocklist + category-based blocking.
- Parent dashboard: logs, alerts, PIN.
- Out of v1: mobile, age estimation of unknown faces, image classification, pricing.

## Privacy and legal (must resolve before launch)
- Faces are biometric data: GDPR / Israeli privacy law, BIPA, COPPA, app-store rules.
- On-device processing only; no image upload; encrypted templates; delete on request.
- Explicit parental consent; visible camera-active indicator.
- Get a privacy-law review before any release.

## Known bypasses to design against
Another browser, incognito, VPN, DoH, covering the camera, photo spoofing, uninstalling the extension.

## Open items
- Pricing model.
- Product name.
- Competitor and legal scan (my search found no existing product combining webcam identification with browser filtering; not proof, verify).
- Face-recognition library choice and Windows camera-permission behavior (first prototype).

## Suggested build order
1. Prototype: webcam presence + enrolled-face match, locally, in a small Windows app.
2. Policy engine with a hard-coded blocklist.
3. Chrome/Edge extension talking to the companion app (native messaging).
4. Parent dashboard and logs.
5. Tamper protection and DNS-level enforcement.
