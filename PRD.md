# KidGuard (working name) — Product Requirements Document

Version 0.1 · 2026-11-02 · Owner: Oran · Status: Draft, prototype in progress
Related: `SPEC.md` (decisions), `prompt.md` (build prompt), `prototype/` (step 1 code).

## 1. Problem and goal
**Problem.** Parental-control tools lock a device or a profile, not a person. If a child uses a parent's unlocked computer, the filter does not change, and the child can reach 18+ or otherwise harmful sites. A review of existing products (Net Nanny, NetParental, SafeNest, Lion Browser) found age-based profiles chosen by the parent and no product combining webcam identification with browser filtering. That is a quick scan, not proof; it must be verified (see section 8).

**Goal.** Protect underage children from 18+ sites and other harmful content by detecting who is actually at the computer and applying the matching browsing rules automatically.

**Product statement.** A Windows app that identifies the person at the webcam on-device and switches Chrome/Edge filtering between normal (adult present) and strict (child, unknown or nobody).

## 2. Users and use cases
- **Primary user: parent/guardian** — installs, enrolls family faces, sets the PIN, reviews logs and alerts.
- **Protected user: child** — browses on a shared or unlocked family computer; should not need to do anything.
- **Secondary: other adults/guests** — treated as unknown, so they get the strict profile.

Key scenarios:
1. Parent browses normally; the app recognizes them and applies the normal profile.
2. Child sits down at a computer the parent left unlocked; strict profile applies immediately and 18+ sites are blocked.
3. A guest or unrecognized person sits down; strict profile applies.
4. Child covers the camera or leaves the frame; strict profile applies (fail-safe).
5. Parent reviews what was blocked and when.

## 3. Scope
**In scope for v1**
- Windows desktop companion app + Chrome/Edge extension.
- Enrolled-face identification (adult / child roles), on-device only.
- Blocking of adult, gambling and drug sites (blocklists + category feeds).
- Parent PIN, logs, basic dashboard and alerts, tamper protection.

**Out of scope for v1**
- Mobile, Mac, Chromebook.
- Age estimation of unknown faces.
- Page-content/image classification.
- Payments and pricing (undecided).
- School/multi-tenant management.

**Later phases**
- v2: violence/gore/self-harm detection (on-device content classification; self-harm needs a careful parent-alert design, not just a block).
- v3: chat/grooming risk detection (highest privacy and accuracy risk).

## 4. Functional requirements
| ID | Requirement | Acceptance test |
|---|---|---|
| F1 | Parent can enroll a family member with a name and role (adult/child) after an explicit consent screen. | Enrollment is refused unless consent is given; template saved with role. |
| F2 | The app captures webcam frames locally and classifies the person as adult, child, unknown or none. | Each class is produced in a live test with enrolled/unenrolled people and a covered camera. |
| F3 | Any non-adult label (child, unknown, none, camera error) maps to the strict profile; only a confirmed adult maps to normal. | Unit test over all labels; live test. |
| F4 | A child present together with an adult yields the strict profile. | Unit + live test. |
| F5 | Switching to a stricter profile is immediate; switching to normal requires several consecutive adult frames. | Smoother unit tests; measured unlock delay. |
| F6 | The browser extension blocks URLs according to the active profile and blocklist/categories. | Known adult/gambling/drug test URLs blocked in strict, allowed in normal where policy permits. |
| F7 | The extension gets the active profile from the companion app (native messaging). | Profile change in the app is reflected in the extension within a defined latency. |
| F8 | A visible indicator shows whenever the camera is active. | Indicator present in every state. |
| F9 | A parent PIN is required to disable protection, change roles, delete templates or uninstall. | Attempts without PIN fail. |
| F10 | The app logs timestamp, person class, domain, action and reason; parents can review it. | Log entries match test activity. |
| F11 | Parents are alerted when protection is disabled, the extension is removed, or repeated block attempts occur. | Alert triggered in each case. |
| F12 | Parents can delete all stored face templates at any time. | Template file removed; app returns to "nobody enrolled". |
| F13 | Liveness check: a photo or screen of an enrolled adult must not unlock the normal profile. The anti-spoofing score is a first gate only; the adult must also pass an active head-turn challenge (F14). | Photo/replay test rejected at the agreed rate (see section 6). |
| F14 | Active head-turn challenge: before an enrolled adult unlocks the normal profile, they must turn their head to a randomly chosen side (left or right) within a time limit, measured from face landmarks, with the same identity throughout. A timeout or failure keeps the strict profile; repeated failures trigger a cooldown and lockout; the pass is dropped when the adult leaves view or after the re-verification interval. Design: `DESIGN-liveness-challenge.md`. | Unit tests with synthetic landmark sequences; live test: real adult passes, phone photo does not (targets in section 6). |

## 5. Non-functional requirements
- **Privacy:** all face processing on-device; no camera frames or biometric data leave the machine; no photos stored; only encrypted templates (Windows DPAPI, current Windows user).
- **Security:** tamper protection (PIN, removal alert); fail-safe on any error.
- **Performance:** classification fast enough to react within about a second. The rebuilt prototype measured about 25 ms per frame (detect + embed) on this laptop's CPU, and the camera limited the loop to about 15-17 fps.
- **Reliability:** works in typical home lighting; degrades to strict, never to normal.
- **Platform:** Windows 11, Chrome and Edge. Python 3.14 used for the prototype; production stack undecided.
- **Usability:** parent setup under 10 minutes; no daily action required from the child.
- **Compliance:** see section 7.

## 6. Success metrics
Targets below are **proposed, not yet validated**, and must be agreed and measured.

| Metric | Proposed target | How measured |
|---|---|---|
| False accept: stranger/child classified as enrolled adult | As close to 0 as achievable; target set from test data | Different-person trials at the chosen threshold |
| False reject: enrolled adult classified as unknown | Low enough that parents are not constantly locked out (target TBD) | Same-person trials in varied lighting/angles |
| Photo/replay spoof accepted | 0 in test set | Liveness test with printed photo and screen replay |
| Head-turn challenge, live adult | Passes in at least 95% of attempts (at least 20 per condition: normal, dim, angled). Proposed | `evaluate.py ccollect` / `creport` |
| Head-turn challenge, phone photo | 0 passes in 50 attempts per setup (bright, dim, still, tilted, moved). Note: 0 in 50 only supports a pass rate below about 6% at 95% confidence. Proposed | Same |
| Head-turn challenge, video replay | Measured and reported; no target (may pass) | Same |
| Added unlock delay from the challenge | Under 4 s. Proposed | Timed live test |
| Time to strict profile when child sits down | Under 1 second | Timed live test |
| Per-frame processing | Under 100 ms on typical laptop CPU | `evaluate.py latency` |
| Blocking effectiveness on test URL set | Target TBD | Test list per category |

**Measured so far (prototype, honest status).** Detection and embedding work on the real webcam: a face was found in 40/40 frames at about 25 ms per frame (prototype rebuilt from scratch against this PRD on 2026-11-02; 31 unit tests pass; accuracy is measured with `evaluate.py collect` and `evaluate.py report`). With nobody enrolled, every face correctly fell back to "unknown" and therefore strict.

**Recognition accuracy, first measurement (2026-11-02; one enrolled adult, one unenrolled person; real webcam).** 152 genuine frames over three runs scored 0.586-0.844 (median 0.784; 5th percentile 0.606). 60 impostor frames scored 0.135-0.279 (95th percentile 0.248). At the default threshold of 0.363 there were 0 false accepts and 0 false rejects among frames where a face was detected, with a gap of about 0.3 between the highest impostor score and the lowest genuine score.

**Limits of this result.** Only one impostor person was tested, and frames from one session are highly correlated, so this is effectively one stranger. No lookalike, sibling or child was tested, and no child was enrolled, so the child-classified-as-adult check has no data. The false-reject figure excludes frames with no detected face: in a deliberate 90-degree head-turn run, 28 of 60 frames had no detected face, which means the strict profile would apply. Observed once: while `run.py` held the camera, a second program received only black frames, so in production only the companion app should open the camera.

**Threshold.** The prototype's working threshold is set to 0.45: about 0.17 above the highest impostor score seen and about 0.14 below the lowest genuine score. The tool's own suggestion (0.299, just above the highest impostor) was not used because it rests on a single impostor. This is a working value, not a validated one.

**Liveness (MiniFASNet), first measurement (2026-11-23; owner's face, real webcam, phone screen).** 364 scored frames: 173 live (normal, dim and angled light) and 191 phone-photo frames over several runs. Live frames scored a median of 0.89-0.998 (lowest single frame 0.167). Phone-photo runs were inconsistent: some scored near 0 (median 0.00-0.01), but a photo in good lighting scored a median of 0.96-0.99 on two separate runs, and the same photo with the screen dimmed scored a median of 0.76 (maximum 0.98). At the default threshold of 0.5, **76% of phone-photo frames were accepted** and 3.5% of live frames rejected. The best single threshold the report found (0.99) still accepted about 9% of photo frames and rejected about 42% of live frames, so a threshold cannot separate live from photo on this webcam. A first guess that screen brightness explained the difference was not supported by the repeat run. One run (a dimmed-screen photo) was discarded because the owner reported their face was not properly in frame; the data was kept in a backup file. Video replay was **not tested**. One person, one phone, one webcam, one day.

**Conclusion.** The passive anti-spoofing model does not reliably stop a phone photo on this setup, so it is kept only as a cheap first gate and an active head-turn challenge (F14) is added. The challenge is **built and unit-tested (140 Python tests pass) but not yet measured on the real camera**; its thresholds are untuned guesses.

**Still not measured:** the head-turn challenge, video replay, more people and lookalikes, children, and false rejects across lighting and angles beyond the conditions tried.

## 7. Assumptions, dependencies and risks
**Assumptions:** a webcam is present and permitted; the household has few enrolled people; a parent controls the Windows admin account.

**Dependencies:** OpenCV (YuNet + SFace ONNX models, hash-pinned in `fetch_models.py`); Chrome/Edge extension APIs; blocklist/category data source (not yet chosen).

**Risks**
- **Legal/privacy (highest):** face templates are biometric data. Relevant regimes include GDPR / Israeli privacy law, BIPA, COPPA and app-store rules. Needs a privacy-law review and explicit parental consent before any release. This PRD makes no compliance claim.
- **Accuracy:** lookalikes (siblings, parent/child) may need a higher threshold; lighting and angle affect results.
- **Spoofing:** the trained anti-spoofing model (milestone 2) was measured on 2026-11-23 and accepted 76% of phone-photo frames at its default threshold (section 6), so it is not a reliable defence alone. An active head-turn challenge (F14, design in `DESIGN-liveness-challenge.md`) is being added. Remaining known gaps: a video of the enrolled adult turning left and right could pass the challenge (randomised direction and a time limit make this harder, not impossible; not yet measured), and 3D masks, deepfakes and live face-swap software are not addressed. Some adults may be unable to perform a head turn; in v1 they stay in the strict profile (the safe failure), and a parent PIN path (F9) is a possible later alternative. Yaw from 5 landmarks is coarse, and glasses, hair or head shape may shift thresholds; false-reject rates are unknown until measured.
- **Bypasses:** another browser, incognito, VPN, encrypted DNS (DoH), covering the camera, uninstalling the extension. v1 mitigations: fail-safe on covered camera, OS-level DNS enforcement, PIN/removal alerts. Residual risk will remain and must be disclosed.
- **Model licensing:** OpenCV Zoo models were used for the prototype; the licence must be confirmed before any commercial use. InsightFace pretrained models are non-commercial, so they are not a drop-in commercial alternative. The liveness models (MiniFASNetV2 and MiniFASNetV1SE ONNX exports) come from a third-party GitHub repository (yakhyo/face-anti-spoofing) whose code is Apache-2.0; that repository does not state a licence for the weights, and their training data is not documented there. Downstream projects describe them as Apache-2.0, which is secondhand. Confirm the licence of the weights (and the upstream Minivision Silent-Face-Anti-Spoofing project) before any commercial use. The file hashes in `fetch_models.py` were pinned from the first download, so they detect later changes but cannot prove the original file was genuine.
- **Product risk:** no parental-control tool is 100% effective (Better Internet for Kids); marketing must not over-promise.

## 8. Open questions
1. Product name and pricing model (undecided).
2. Competitor and legal scan to confirm the gap and the privacy position.
3. Acceptable false-accept / false-reject targets and the chosen threshold.
4. Liveness method. On 2026-11-02 a trained anti-spoofing model (MiniFASNet) was chosen over a head-turn challenge. **Revised 2026-11-23:** measured data showed the model accepts most phone-photo frames (section 6), so an active head-turn challenge (F14) was approved on top of it, using the 5 landmarks YuNet already provides (no new ML model). Decisions taken: prompt shown in the camera window first; re-verify every 30 minutes while the adult stays in view; no fallback for adults who cannot turn their head in v1; blink challenge not included (it would need a facial-landmark model with eyelid points, which is an ML library choice to be decided with the owner). Still open: video-replay effectiveness, how the prompt is shown in the browser, and the weights' licence (section 7).
5. Production tech stack for the companion app (prototype is Python).
6. Blocklist/category data source and update mechanism.
7. How enrolled children's templates are updated as they grow.

## 9. Milestones and acceptance criteria
1. **Face-match prototype** (built; live accuracy pending) — accepted when same-person vs different-person scores are measured, a threshold is chosen from data, and fail-safe cases are demonstrated live.
2. **Liveness check** — accepted when photo and replay attempts are rejected at the agreed rate. **Status (2026-11-02): built, not yet measured.** Two MiniFASNet models (`prototype/kidguard/liveness.py`) score each adult face; an adult who is not judged live counts as unknown (strict), averaged over a few frames, and must re-prove liveness after leaving view. `run.py` requires it by default (`--no-liveness` is development-only). Measurement tools: `evaluate.py lcollect --kind live|spoof --note ...` and `evaluate.py lreport`. 113 Python unit tests pass, including the rule that an adult who fails liveness is never labelled adult. Acceptance still needs a test set (live face in several conditions; photo on a phone screen; printed photo if available; video replay) and a threshold chosen from the data. **Update 2026-11-23: measured, and the passive model does not meet the goal** (76% of phone-photo frames accepted at 0.5; no threshold separates live from photo; section 6). An active head-turn challenge (F14) was approved to close the gap; it is built (`prototype/kidguard/challenge.py`, wired into `run.py`, `--no-challenge` for development; measurement tools `evaluate.py ccollect` / `creport`) and unit-tested, but not yet measured on the real camera. Known consequence: `run.py --seconds N` (headless) shows no prompt, so it cannot unlock the normal profile unless `--no-challenge` is used.
3. **Policy engine** with blocklist and unit tests — accepted when F3–F5 pass. **Status (2026-11-02): built** (`prototype/kidguard/decision.py`, `blocklist.py`; 62 unit tests pass across the prototype). The shipped blocklists are placeholders; a real, licence-compatible list is still needed (open question 6).
4. **Chrome/Edge extension + native messaging** — accepted when F6–F7 pass. **Status (2026-11-02): built and verified manually in a real browser** (`extension/`, `prototype/kidguard/host.py`; 89 Python + 9 Node unit tests pass, and the native host was tested as a real subprocess). Manual checks by the owner, using a simulated camera label (`fake_state.py`), not the real camera: the extension connected to the host; with a child label a listed site showed the blocked page and an unlisted site loaded; with an adult label a listed test site loaded; switching adult to child turned an already-open tab into the blocked page in about 3 s (owner's estimate, single run, not a controlled measurement). Found and fixed during testing: a Windows file-replace race in the state file. Later the owner also reported, with the real camera and Chrome (informal, no numbers recorded): the extension works, and an unenrolled person shown to the camera was labelled unknown. Later, with the real camera in Chrome, a blocked tab went back to the site by itself once the owner was recognised again; the host debug log shows an allow decision 2-3 s after the last block in two separate cycles. Found and fixed during that test: the blocked page's script was not loaded as a module, so its details, Try again button and auto-return never ran (now covered by page-wiring tests; 14 Node and 91 Python unit tests pass). Not yet verified: Edge, incognito, and long-term use.
5. **Parent dashboard, logs, PIN, alerts** — accepted when F9–F12 pass.
6. **Tamper protection + DNS-level enforcement** — accepted when listed bypasses are tested and residual gaps documented.
7. **Privacy-law review** — required before any release.
