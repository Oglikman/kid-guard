# KidGuard face-match prototype (PRD milestone 1)

Webcam -> detect face -> match against enrolled family members -> adult / child / unknown / none -> normal or strict profile.
OpenCV YuNet (detect) + SFace (recognise). Everything runs on this PC; frames are never saved or uploaded.
Rebuilt from scratch against `../PRD.md` (the earlier version is in `../_archive/prototype_v0`).

## Run (use `py`, not `python`, on this machine)
```
py -m pip install -r requirements.txt
py fetch_models.py                 # downloads + hash-checks the two ONNX models
py -m pytest -q                    # unit tests, no camera needed
py enroll.py Oran adult            # consent prompt, then 8 samples (q cancels)
py enroll.py Sam child
py run.py                          # live window; q quits
py delete_templates.py             # erase all enrolled faces (F12)
```

## Measuring accuracy (milestone 1 acceptance)
```
py evaluate.py collect --kind genuine  --who Oran --note "daylight"    # you in front of the camera
py evaluate.py collect --kind genuine  --who Oran --note "lamp only"   # vary lighting/angle
py evaluate.py collect --kind impostor                                 # someone NOT enrolled in front
py evaluate.py report                                                  # FAR / FRR / child-as-adult, suggested threshold
py evaluate.py report --apply                                          # save the suggested threshold
py evaluate.py latency                                                 # ms per frame (PRD target < 100 ms)
```
Only scores are saved (`eval_scores.json`), never images or embeddings. Collect genuine data in a separate session from enrollment, otherwise scores look better than reality.

## Policy engine (PRD milestone 3)
```
py check_url.py http://adult-sample.test --label child     # BLOCK (strict profile)
py check_url.py http://adult-sample.test --label adult     # ALLOW (normal profile)
py check_url.py https://example.org --label unknown --time 23:30
```
- Inputs: face label (-> profile via the fail-safe rule), URL, time of day, parent overrides (`policy.json`), blocklists (`blocklists/<category>.txt`).
- Precedence: browser-internal pages allowed -> unparseable/non-web URL (blocked for strict) -> parent always-block -> strict curfew -> parent always-allow -> category rule -> allow.
- Default policy: strict blocks adult, gambling, drugs; normal allows everything. Unknown profile names are treated as strict.
- **The shipped blocklists contain placeholder `.test` domains only; they block no real site.** Add a vetted, licence-compatible list before real use (PRD open question 6).
- Not covered by the engine itself: IP-address URLs, DNS-over-HTTPS and other-browser bypasses (PRD section 7).

## Browser extension (PRD milestone 4)
See `../extension/README.md` for install steps. `run.py` publishes the current label to `state.json` (1 s heartbeat; "none" on exit);
`native_host.py` is what the browser launches; `fake_state.py child|adult` simulates the camera for testing.
Stale (>5 s), missing or corrupt state is always treated as "nobody present" (strict).
`py run.py --seconds 600` runs the camera loop without a window for 10 minutes and then releases the camera (use this for browser tests;
a camera window left open makes other scripts get black frames). `host.log` records what the extension asked and the host answered (no URLs).

## Liveness (PRD milestone 2, F13)
Two MiniFASNet anti-spoofing models (downloaded by `fetch_models.py`) check that an adult's face is a real person. An adult who is not judged
live counts as **unknown** (strict). `run.py` requires this by default; `--no-liveness` is for development only.
```
py evaluate.py lcollect --kind live  --note "me, normal light"            # your real face
py evaluate.py lcollect --kind spoof --note "phone photo of me"           # a photo of an enrolled adult on a phone screen
py evaluate.py lcollect --kind spoof --note "video of me on phone"        # replay attack
py evaluate.py lreport                                                    # live/spoof score separation, suggested threshold
py evaluate.py lreport --apply                                            # save it (liveness_threshold in settings.json)
```
Limits: effectiveness on this webcam is unmeasured until you collect data; video replay and 3D masks are not covered by this kind of model;
the weights' licence is unconfirmed (see PRD section 7).

## Head-turn challenge (PRD F14)
The MiniFASNet liveness score proved unreliable against phone photos on this webcam (76% of photo frames accepted at 0.5; see PRD section 6), so an
adult must also turn their head to a random side ("Turn your head to YOUR LEFT") before the normal profile unlocks. Yaw comes from YuNet's landmarks
(`kidguard/challenge.py`). Failure keeps strict; 3 failures in 60 s lock the challenge for 60 s; the pass drops when the adult is out of view for 3 s,
when a child/stranger is in view, and after 30 minutes. `run.py` shows the prompt in its window; `--no-challenge` is for development only.
```
py evaluate.py ccollect --kind live  --attempts 20 --who Oran --note "normal light"   # real turns (--who also records face-match during the turn)
py evaluate.py ccollect --kind photo --attempts 50 --note "phone photo, bright, tilted"
py evaluate.py ccollect --kind video --attempts 20 --note "video of me turning"
py evaluate.py creport                                                                # pass rates vs the PRD targets
```
Status: built and unit-tested; thresholds (`YAW_NEUTRAL`, `YAW_TURN`, ...) in `config.py` are untuned guesses and the camera behaviour is unmeasured.
If `left`/`right` come out mirrored, set `YAW_SIGN_USER_LEFT = -1.0` in `config.py`. Headless runs (`--seconds`) cannot unlock unless `--no-challenge` is given.

## Behaviour
- Fail-safe: no face, unknown face, camera error -> **strict**. Child with an adult -> strict.
- Unlock needs 5 consecutive adult frames; locking is immediate.
- Templates: embeddings only, DPAPI-encrypted for this Windows user in `templates.bin`.
- Threshold: `settings.json` if present, else SFace's documented 0.363 (unverified until you run `report`).

## PRD coverage
F1 enroll with consent, F2 classify, F3 fail-safe mapping, F4 child+adult, F5 lock fast/unlock slow, F8 camera indicator, F12 delete templates, plus the decision logic behind F6 (URL blocking by profile and category; the browser extension itself is not built).
Also built since: F6 extension, F7 native messaging, F13 liveness, F14 head-turn challenge. Not here yet: F9 PIN, F10 logs, F11 alerts.

## Honest limits
- No liveness: a photo or video of an enrolled adult can fool it.
- Accuracy depends on lighting, angle and distance; lookalikes (siblings, parent/child) may need a higher threshold.
- Prototype only: not a security product; no legal/privacy review done.
