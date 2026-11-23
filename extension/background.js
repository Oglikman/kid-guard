// KidGuard service worker: asks the companion app (native messaging) about every top-level navigation and redirects blocked ones.
import { shouldCheck, failClosedDecision, blockedPageUrl, needsRecheck, badgeFor } from "./logic.js";

const HOST = "com.kidguard.host";
const REQUEST_TIMEOUT_MS = 1500;
const POLL_MS = 2000;

let port = null;
let nextId = 1;
const pending = new Map();
let lastError = null;
let lastStatus = null;
let lastProfile = null;

/** Opens (or returns) the native-messaging connection to the companion app, recording any error. */
function connect() {
  if (port) return port;
  try {
    const p = chrome.runtime.connectNative(HOST);
    p.onMessage.addListener(onHostMessage);
    p.onDisconnect.addListener(() => {
      lastError = (chrome.runtime.lastError && chrome.runtime.lastError.message) || "companion app disconnected";
      port = null;
      lastStatus = null;
      for (const waiter of pending.values()) waiter.reject(new Error(lastError));
      pending.clear();
      poll();
    });
    port = p;
  } catch (e) {
    lastError = String(e);
    port = null;
  }
  return port;
}

/** Delivers a reply from the companion app to the request that is waiting for it. */
function onHostMessage(msg) {
  const waiter = pending.get(msg && msg.id);
  if (waiter) {
    pending.delete(msg.id);
    waiter.resolve(msg);
  }
}

/** Sends one request to the companion app and resolves with its reply, rejecting on timeout or disconnect. */
function request(msg, timeoutMs = REQUEST_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const p = connect();
    if (!p) return reject(new Error(lastError || "cannot connect"));
    const id = nextId++;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error("timeout"));
    }, timeoutMs);
    pending.set(id, {
      resolve: (v) => { clearTimeout(timer); resolve(v); },
      reject: (e) => { clearTimeout(timer); reject(e); },
    });
    try {
      p.postMessage({ ...msg, id });
    } catch (e) {
      pending.delete(id);
      clearTimeout(timer);
      reject(e);
    }
  });
}

/** Asks the companion app to judge a URL, falling back to the fail-closed decision on any error or malformed reply. */
async function checkUrl(url) {
  try {
    const reply = await request({ type: "check", url });
    return reply && reply.type === "decision" ? reply : failClosedDecision("unexpected reply");
  } catch (e) {
    return failClosedDecision(e.message);
  }
}

/** Sends a tab to the blocked page, ignoring errors if the tab has already closed. */
function redirectToBlocked(tabId, decision, url) {
  const target = blockedPageUrl(chrome.runtime.getURL("blocked.html"), decision, url);
  chrome.tabs.update(tabId, { url: target }).catch(() => {});
}

/** Checks a top-level navigation and redirects it to the blocked page if the decision is block. */
async function guardNavigation(details) {
  if (details.frameId !== 0 || !shouldCheck(details.url)) return;
  const decision = await checkUrl(details.url);
  if (decision.action === "block") redirectToBlocked(details.tabId, decision, details.url);
}

/** Re-checks every open tab so a switch to the strict profile takes effect on pages that are already loaded. */
async function recheckAllTabs() {
  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) {
    if (!tab.url || !shouldCheck(tab.url)) continue;
    const decision = await checkUrl(tab.url);
    if (decision.action === "block") redirectToBlocked(tab.id, decision, tab.url);
  }
}

/** Updates the toolbar badge for the given profile (null means the companion app is offline). */
function updateBadge(profile) {
  const b = badgeFor(profile);
  chrome.action.setBadgeText({ text: b.text });
  chrome.action.setBadgeBackgroundColor({ color: b.color });
}

/** Fetches the current profile from the companion app, updates the badge, and re-checks open tabs when it just became strict. */
async function poll() {
  let profile = "strict"; // offline counts as strict (fail-safe)
  try {
    const status = await request({ type: "status" });
    if (status && status.type === "status") {
      lastStatus = status;
      profile = status.profile;
    }
  } catch (e) {
    lastError = e.message;
    lastStatus = null;
  }
  updateBadge(lastStatus ? profile : null);
  const recheck = needsRecheck(lastProfile, profile);
  lastProfile = profile;
  if (recheck) await recheckAllTabs();
}

chrome.webNavigation.onBeforeNavigate.addListener(guardNavigation);
chrome.webNavigation.onHistoryStateUpdated.addListener(guardNavigation);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || !msg) return false;
  if (msg.type === "getStatus") {
    sendResponse({ connected: !!port && !!lastStatus, lastError, status: lastStatus, profile: lastProfile });
    return false;
  }
  if (msg.type === "recheckUrl" && shouldCheck(msg.url)) {   // the blocked page asks whether its original URL is allowed now
    checkUrl(msg.url).then(sendResponse);
    return true;   // keep the channel open for the async reply
  }
  return false;
});

chrome.alarms.create("kidguard-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => poll());
chrome.runtime.onStartup.addListener(() => poll());
chrome.runtime.onInstalled.addListener(() => poll());
setInterval(poll, POLL_MS);
poll();
