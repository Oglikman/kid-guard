// Unit tests for the extension's pure helper functions; run with: node --test extension/tests
import test from "node:test";
import assert from "node:assert/strict";
import { isInternalUrl, shouldCheck, failClosedDecision, blockedPageUrl, needsRecheck, safeRetryUrl, autoRetryTarget, badgeFor, FAIL_CLOSED } from "../logic.js";

test("internal and extension pages are not checked", () => {
  for (const u of ["chrome://settings", "edge://flags", "about:blank", "chrome-extension://abc/blocked.html", "devtools://devtools/x", "chrome-search://x"]) {
    assert.equal(shouldCheck(u), false, u);
  }
});

test("web, file, data and javascript URLs are sent to the companion app", () => {
  for (const u of ["https://example.org", "http://a.test/x", "file:///c:/a.html", "data:text/html,hi", "javascript:alert(1)", "view-source:http://a.test"]) {
    assert.equal(shouldCheck(u), true, u);
  }
});

test("empty or non-string input is not checked", () => {
  assert.equal(shouldCheck(""), false);
  assert.equal(shouldCheck(undefined), false);
  assert.equal(isInternalUrl(null), false);
});

test("fail-closed is on by default and blocks", () => {
  assert.equal(FAIL_CLOSED, true);
  const d = failClosedDecision("timeout");
  assert.equal(d.action, "block");
  assert.equal(d.profile, "strict");
  assert.match(d.reason, /timeout/);
});

test("fail-open variant allows but is clearly labelled", () => {
  const d = failClosedDecision("x", false);
  assert.equal(d.action, "allow");
  assert.match(d.reason, /development only/);
});

test("blocked page URL carries host, reason, label, state and original URL, safely encoded", () => {
  const url = blockedPageUrl("chrome-extension://id/blocked.html", { host: "a.test", reason: "r & s", label: "child", state: "ok" }, "http://a.test/?x=1&y=2");
  const q = new URL(url).searchParams;
  assert.equal(q.get("host"), "a.test");
  assert.equal(q.get("reason"), "r & s");
  assert.equal(q.get("u"), "http://a.test/?x=1&y=2");
});

test("recheck triggers only when the profile newly becomes strict", () => {
  assert.equal(needsRecheck("normal", "strict"), true);
  assert.equal(needsRecheck(null, "strict"), true);
  assert.equal(needsRecheck("strict", "strict"), false);
  assert.equal(needsRecheck("strict", "normal"), false);
  assert.equal(needsRecheck("normal", "normal"), false);
});

test("retry URL accepts only http(s)", () => {
  assert.equal(safeRetryUrl("https://example.org/a"), "https://example.org/a");
  assert.equal(safeRetryUrl("javascript:alert(1)"), null);
  assert.equal(safeRetryUrl("data:text/html,x"), null);
  assert.equal(safeRetryUrl("not a url"), null);
  assert.equal(safeRetryUrl(null), null);
});

test("auto-retry happens only on allow and only to http(s) URLs", () => {
  assert.equal(autoRetryTarget({ action: "allow" }, "https://example.net/a"), "https://example.net/a");
  assert.equal(autoRetryTarget({ action: "block" }, "https://example.net/a"), null);
  assert.equal(autoRetryTarget({ action: "warn" }, "https://example.net/a"), null);
  assert.equal(autoRetryTarget(failClosedDecision("timeout"), "https://example.net/a"), null);
  assert.equal(autoRetryTarget({ action: "allow" }, "javascript:alert(1)"), null);
  assert.equal(autoRetryTarget(undefined, "https://example.net/a"), null);
  assert.equal(autoRetryTarget(null, null), null);
});

test("badge reflects profile and offline state", () => {
  assert.equal(badgeFor("normal").text, "OK");
  assert.equal(badgeFor("strict").text, "S");
  assert.equal(badgeFor(null).text, "!");
});
