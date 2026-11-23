// Toolbar popup: shows companion-app status, who is detected, the active profile, and warns about bypass settings.

/** Adds a warning line to the popup. */
function warn(text) {
  const el = document.getElementById("warn");
  el.hidden = false;
  el.append(Object.assign(document.createElement("div"), { textContent: text }));
}

/** Asks the service worker for its latest status and renders it. */
async function render() {
  let s = null;
  try {
    s = await chrome.runtime.sendMessage({ type: "getStatus" });
  } catch (e) {
    s = null;
  }
  const connected = !!(s && s.connected);
  document.getElementById("conn").textContent = connected ? "connected" : "NOT connected";
  const status = s && s.status;
  document.getElementById("label").textContent = status ? status.label : "-";
  const profileEl = document.getElementById("profile");
  const profile = status ? status.profile : "strict (offline)";
  profileEl.textContent = profile;
  profileEl.className = status && status.profile === "normal" ? "normal" : "strict";
  if (!connected) warn("Companion app unreachable: browsing is blocked for safety. " + ((s && s.lastError) || ""));
  else if (status && status.state !== "ok") warn(`Camera state: ${status.state}. Treated as nobody present (strict).`);
  chrome.extension.isAllowedIncognitoAccess((allowed) => {
    if (!allowed) warn("Not enabled in Incognito: children can bypass KidGuard there. Enable it on chrome://extensions.");
  });
}

render();
