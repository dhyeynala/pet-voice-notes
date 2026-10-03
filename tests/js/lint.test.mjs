// Static checks on public/: no HTML built from interpolated strings, no inline event handlers,
// no third-party URLs (the demo must work offline and send nothing off-machine).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "public");
const jsFiles = readdirSync(join(PUBLIC, "js")).filter((f) => f.endsWith(".js"));
const htmlFiles = readdirSync(PUBLIC).filter((f) => f.endsWith(".html"));
const read = (...p) => readFileSync(join(PUBLIC, ...p), "utf8");

test("no innerHTML/outerHTML/insertAdjacentHTML built from ${} interpolation", () => {
  const problems = [];
  for (const f of jsFiles) {
    const src = read("js", f);
    // From each sink to the end of its statement (`;` or a blank line).
    const sink = /(\.(?:innerHTML|outerHTML)\s*\+?=|\.insertAdjacentHTML\s*\(|document\.write(?:ln)?\s*\()([\s\S]*?)(;|\n\s*\n)/g;
    for (const m of src.matchAll(sink)) {
      const rhs = m[2];
      if (rhs.includes("${") || /["'`]\s*\+|\+\s*["'`]/.test(rhs)) {
        const line = src.slice(0, m.index).split("\n").length;
        problems.push(`${f}:${line}: ${m[0].trim().slice(0, 120)}`);
      }
    }
  }
  assert.deepEqual(problems, [], "build these nodes with el()/textContent or escapeHtml() instead");
});

test("every innerHTML sink is static or goes through parseMarkdown/escapeHtml", () => {
  const problems = [];
  for (const f of jsFiles) {
    const src = read("js", f);
    for (const m of src.matchAll(/\.innerHTML\s*=\s*([^;\n]+)/g)) {
      const rhs = m[1].trim();
      const ok = /^(parseMarkdown|escapeHtml)\(/.test(rhs) || /^(["'])[^"']*\1$/.test(rhs) || /^`[^`$]*`$/.test(rhs);
      if (!ok) problems.push(`${f}: innerHTML = ${rhs.slice(0, 100)}`);
    }
  }
  assert.deepEqual(problems, []);
});

test("HTML pages have no inline event handlers or inline scripts", () => {
  for (const f of htmlFiles) {
    const html = read(f);
    assert.doesNotMatch(html, /<[a-z][^>]*\son[a-z]+\s*=/i, `${f} has an inline on*= handler`);
    for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
      assert.match(m[1], /\ssrc=/, `${f} has an inline <script>`);
      assert.equal(m[2].trim(), "", `${f} has an inline <script> body`);
    }
  }
});

test("pages and modules load nothing from third-party hosts", () => {
  for (const f of htmlFiles) {
    assert.doesNotMatch(read(f), /(src|href)\s*=\s*["'](https?:)?\/\//i, `${f} references an external URL`);
  }
  for (const f of jsFiles) {
    assert.doesNotMatch(read("js", f), /fetch\(\s*["'`]https?:/, `${f} fetches an absolute URL`);
    assert.doesNotMatch(read("js", f), /\bimport\b[^;]*["']https?:/, `${f} imports a remote module`);
  }
});

test("no module calls a removed legacy route", () => {
  const removed = /["'`/](visualizations|knowledge_search|assistant_summary|health_insights|daily_routine|textinput|preload|upload_pdf|user-pets)["'`/]|cache\/(clear|status)|analytics\/summary/;
  for (const f of jsFiles) {
    assert.doesNotMatch(read("js", f), removed, `${f} still calls a removed route`);
  }
});
