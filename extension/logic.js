// Pure helper functions for the KidGuard extension (no browser APIs, so they can be unit-tested with Node).

// When the companion app cannot be reached: true = block everything (PRD fail-safe), false = allow (development only).
export const FAIL_CLOSED = true;

/** Returns true for browser-internal and extension pages, which KidGuard never checks so the browser stays usable. */
export function isInternalUrl(url) {
  return /^(chrome|edge|about|devtools|chrome-[a-z-]+|edge-[a-z-]+):/i.test(url || "");
}

/** Returns true if a URL should be sent to the companion app for a decision. */
export function shouldCheck(url) {
  return typeof url === "string" && url.length > 0 && !isInternalUrl(url);
}

/** Builds the decision used when the companion app is unreachable, blocking by default for safety. */
export function failClosedDecision(why, failClosed = FAIL_CLOSED) {
  return failClosed
    ? { type: "decision", action: "block", profile: "strict", label: "none", state: "offline", category: null, host: null,
        reason: `KidGuard could not reach its companion app (${why}), so it is blocking for safety` }
    : { type: "decision", action: "allow", profile: "strict", label: "none", state: "offline", category: null, host: null,
        reason: `companion app unreachable (${why}); fail-open is enabled (development only)` };
}

/** Builds the extension's blocked-page URL carrying only the host, reason, label and the original URL for "try again". */
export function blockedPageUrl(base, decision, originalUrl) {
  const q = new URLSearchParams({
    host: decision.host || "",
    reason: decision.reason || "",
    label: decision.label || "",
    state: decision.state || "",
    u: originalUrl || "",
  });
  return `${base}?${q.toString()}`;
}

/** Returns true when the profile just became strict, so already-open tabs must be re-checked (PRD F7). */
export function needsRecheck(previousProfile, newProfile) {
  return newProfile === "strict" && previousProfile !== "strict";
}

/** Returns the original URL only if it is a plain http(s) address, otherwise null (prevents javascript: injection via the query string). */
export function safeRetryUrl(u) {
  try {
    const parsed = new URL(u);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/** Returns the URL a blocked page may automatically go back to: only when the companion app now says allow and the URL is plain http(s), otherwise null. */
export function autoRetryTarget(decision, originalUrl) {
  return decision && decision.action === "allow" ? safeRetryUrl(originalUrl) : null;
}

/** Maps a profile (or null when offline) to the toolbar badge text and colour. */
export function badgeFor(profile) {
  if (profile === "normal") return { text: "OK", color: "#2e7d32" };
  if (profile === "strict") return { text: "S", color: "#c62828" };
  return { text: "!", color: "#616161" };
}
