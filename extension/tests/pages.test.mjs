// Guards against page-wiring mistakes that unit tests of pure logic cannot see; run with: node --test extension/tests/pages.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (f) => fs.readFileSync(path.join(dir, f), "utf8");

/** Returns every <script> tag in an HTML string as {src, isModule}. */
function scripts(html) {
  return [...html.matchAll(/<script\b([^>]*)>/gi)].map((m) => ({
    src: (m[1].match(/\bsrc="([^"]+)"/) || [])[1],
    isModule: /\btype="module"/.test(m[1]),
  }));
}

test("any page script that uses import/export is loaded with type=module", () => {
  for (const page of fs.readdirSync(dir).filter((f) => f.endsWith(".html"))) {
    for (const s of scripts(read(page))) {
      if (!s.src) continue;
      const usesModules = /^\s*(import|export)\s/m.test(read(s.src));
      assert.ok(!usesModules || s.isModule, `${page}: ${s.src} uses import/export but is not type="module"`);
    }
  }
});

test("pages load no remote scripts and no inline scripts (extension CSP)", () => {
  for (const page of fs.readdirSync(dir).filter((f) => f.endsWith(".html"))) {
    const html = read(page);
    assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>\s*\S/i.test(html), `${page} has an inline script`);
    for (const s of scripts(html)) assert.ok(s.src && !/^https?:/.test(s.src), `${page} loads a remote script`);
  }
});

test("every script file referenced by the manifest or a page exists", () => {
  const manifest = JSON.parse(read("manifest.json"));
  assert.ok(fs.existsSync(path.join(dir, manifest.background.service_worker)));
  assert.equal(manifest.background.type, "module"); // background.js imports ./logic.js
  for (const page of fs.readdirSync(dir).filter((f) => f.endsWith(".html"))) {
    for (const s of scripts(read(page))) assert.ok(fs.existsSync(path.join(dir, s.src)), `${page}: missing ${s.src}`);
  }
});

test("elements that blocked.js writes to exist in blocked.html", () => {
  const html = read("blocked.html");
  for (const id of ["why", "host", "reason", "retry", "auto"]) assert.ok(html.includes(`id="${id}"`), `blocked.html lacks #${id}`);
});
