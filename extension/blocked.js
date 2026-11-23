// Fills in the blocked page from its query string using textContent only (never innerHTML), so nothing in the URL can inject markup.
import { safeRetryUrl, autoRetryTarget } from "./logic.js";

/** Returns a plain-language explanation of who the system thinks is at the computer. */
function whyText(label, state) {
  if (state === "offline") return "KidGuard's companion app isn't running, so browsing is blocked for safety.";
  if (label === "child") return "A child profile is active, so this kind of site is blocked.";
  if (label === "adult") return "This site is blocked by a rule set by a parent.";
  return "KidGuard couldn't confirm that an adult is at the computer, so strict rules apply.";
}

/** Reads the query parameters and renders the page, wiring up the retry button when a safe URL is available. */
function render() {
  const q = new URLSearchParams(location.search);
  document.getElementById("why").textContent = whyText(q.get("label"), q.get("state"));
  document.getElementById("host").textContent = q.get("host") || "(unknown)";
  document.getElementById("reason").textContent = q.get("reason") || "";
  const retry = safeRetryUrl(q.get("u"));
  if (retry) {
    const btn = document.getElementById("retry");
    btn.hidden = false;
    btn.addEventListener("click", () => { location.href = retry; }); // re-checked on load, so this cannot bypass the block
    watchForAllow(retry);
  }
}

/** Every 2 seconds asks the service worker whether the original URL is allowed now, and goes back to it as soon as the answer is allow. */
function watchForAllow(url) {
  const note = document.getElementById("auto");
  note.hidden = false;
  setInterval(async () => {
    try {
      const decision = await chrome.runtime.sendMessage({ type: "recheckUrl", url });
      const target = autoRetryTarget(decision, url);
      if (target) location.replace(target);   // the load is checked again by the normal navigation guard
    } catch (e) {
      // service worker not ready: try again at the next tick
    }
  }, 2000);
}

render();
