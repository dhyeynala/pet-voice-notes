// Unit tests for the HTML escaping used by the frontend (node --test tests/js/).
import { test } from "node:test";
import assert from "node:assert/strict";
import { escapeHtml } from "../../public/js/dom.js";
import { parseMarkdown } from "../../public/js/markdown.js";

test("escapeHtml escapes the five HTML-significant characters", () => {
  assert.equal(escapeHtml(`<a href="x" title='y'>&</a>`), "&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;");
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(undefined), "");
  assert.equal(escapeHtml(42), "42");
});

test("parseMarkdown never emits tags or attributes from the input", () => {
  const payloads = [
    "<img src=x onerror=alert(1)>",
    "<script>alert(1)</script>",
    '**<svg onload="alert(1)">**',
    "> <iframe src=javascript:alert(1)>",
    "- <a href=\"javascript:alert(1)\">x</a>",
    "`<b onmouseover=alert(1)>`",
  ];
  for (const p of payloads) {
    const html = parseMarkdown(p);
    assert.doesNotMatch(html, /<(img|script|svg|iframe|a|b)\b/i, `raw tag leaked for ${p}: ${html}`);
    assert.doesNotMatch(html, /<[^>]*\son\w+\s*=/i, `event handler attribute leaked for ${p}: ${html}`);
  }
  assert.match(parseMarkdown("<img src=x onerror=alert(1)>"), /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(parseMarkdown("<script>alert(1)</script>"), /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
});

test("parseMarkdown output only contains whitelisted tags", () => {
  const html = parseMarkdown("# T\n## S\n### s\n**b** *i* `c`\n> q\n- one\n1. two\n\npara <div>x</div>");
  const tags = new Set([...html.matchAll(/<\/?([a-z0-9]+)/gi)].map((m) => m[1].toLowerCase()));
  const allowed = new Set(["h1", "h2", "h3", "strong", "em", "code", "blockquote", "li", "ul", "p", "br"]);
  for (const t of tags) assert.ok(allowed.has(t), `unexpected tag <${t}> in ${html}`);
});

test("parseMarkdown still formats", () => {
  assert.match(parseMarkdown("**bold**"), /<strong[^>]*>bold<\/strong>/);
  assert.match(parseMarkdown("*it*"), /<em[^>]*>it<\/em>/);
  assert.match(parseMarkdown("`x < y`"), /<code[^>]*>x &lt; y<\/code>/);
  assert.match(parseMarkdown("# Title"), /<h1[^>]*>Title<\/h1>/);
  assert.match(parseMarkdown("> quoted"), /<blockquote[^>]*>quoted<\/blockquote>/);
  assert.match(parseMarkdown("- a\n- b"), /<ul[^>]*><li[^>]*>a<\/li>/);
  assert.equal(parseMarkdown(""), "");
});
