# KidGuard browser extension (PRD milestone 4: F6, F7)

Chrome/Edge (Manifest V3) extension. For every top-level navigation it asks the local companion app
(native messaging host `com.kidguard.host`, Python) for allow/block and redirects blocked pages to `blocked.html`.

```
camera loop (run.py) --writes--> state.json --read by--> native_host.py <--native messaging--> extension
                                                              |
                                              policy engine + blocklists + policy.json
```

## Install (Windows, current user only)
1. `cd C:\Users\oran\cluade\projects\kid-guard\prototype`
2. `py install_host.py --dry-run` to see exactly what will change, then `py install_host.py`.
   It writes two registry keys under HKCU (Chrome and Edge) and two files in `prototype\native_host_files\`.
   Undo with `py install_host.py --uninstall`.
3. Restart the browser. Open `chrome://extensions` (or `edge://extensions`), turn on **Developer mode**,
   **Load unpacked**, choose `kid-guard\extension`. The ID must be `cndbaefonacneegmndgbjaablgjjdmkj`
   (it is fixed by the `key` in manifest.json; if it differs, run `py install_host.py --extension-id <ID>`).
4. Open the extension's **Details** and turn on **Allow in Incognito**, otherwise incognito windows bypass KidGuard.

## Try it without the camera
```
py fake_state.py child      # terminal 1: pretend a child is present (Ctrl+C to stop)
```
Then browse to `http://adult-sample.test` (placeholder blocklist) -> blocked page.
Stop it and run `py fake_state.py adult` -> the same site loads (it will not resolve, but it is not blocked).
Stop publishing entirely -> after 5 s the state is stale -> strict applies again.
With the camera: `py run.py` publishes the real label.

## Behaviour
- Fail-closed: if the companion app is unreachable (not installed, crashed, timeout > 1.5 s), all web pages are blocked
  with an explanation. Toggle `FAIL_CLOSED` in `logic.js` for development only.
- Profile switch (F7): the service worker polls every 2 s; when the profile newly becomes strict, all open tabs are re-checked.
  Expected delay: camera heartbeat (1 s) + poll (2 s), so about 3-4 s. Observed once by hand (simulated label): about 3 s.
- Blocked pages re-check their original address every 2 s and go back to it automatically as soon as the companion app says allow
  (observed with the real camera: 2-3 s after the person was recognised again). They never move on while the answer is block.
- Debug log: the host appends one line per request to `prototype/host.log` (label, state, decision; never the URL).
- Toolbar badge: green OK = normal profile, red S = strict, grey ! = companion app offline.

## Limits (be honest with yourself)
- **Tested by hand in Chrome, first with a simulated label and then with the real camera.** Logic and page wiring are unit-tested (Node, 14 tests), the host is
  tested as a real subprocess (Python), and the owner confirmed blocking, unlocking and a live profile switch in the browser.
  Not yet checked: Edge, incognito, long-term use.
- `blocklists/gambling.txt` contains a test entry `example.net` (a harmless IANA example site) so live blocking can be tried; remove it before real use.
- Redirect happens at navigation start; a blocked page may flash briefly before the redirect. Only top-level
  navigations are checked, not iframes or background requests.
- Only works in Chrome/Edge with the extension enabled. Other browsers, incognito (if not allowed), VPN/DoH,
  removing the extension, and covering the camera are separate PRD items (tamper protection, DNS enforcement, liveness).
- `warn` decisions are treated as allow in this version (no warning page yet); the default policy has none.
- No icons yet; Chrome shows a default one.
- The shipped blocklists are placeholders and block no real site.
