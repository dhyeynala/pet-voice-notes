// public/js/markdown.js: minimal markdown renderer for assistant messages.
// Security (review H1): the input is HTML-escaped FIRST, then a small set of formatting rules is
// applied to the escaped text. The output therefore contains only the tags produced below.
import { escapeHtml } from "./dom.js";

export function parseMarkdown(text) {
  if (!text) return "";
  return (
    escapeHtml(text)
      // Headers
      .replace(/^### (.*$)/gim, '<h3 style="margin: 8px 0 4px 0; color: #2c3e50; font-size: 1.1em; font-weight: 600;">$1</h3>')
      .replace(/^## (.*$)/gim, '<h2 style="margin: 12px 0 6px 0; color: #2c3e50; font-size: 1.3em; font-weight: 700;">$1</h2>')
      .replace(/^# (.*$)/gim, '<h1 style="margin: 15px 0 8px 0; color: #2c3e50; font-size: 1.5em; font-weight: 800;">$1</h1>')
      // Bold, italic, inline code
      .replace(/\*\*(.*?)\*\*/g, '<strong style="font-weight: 600; color: #2c3e50;">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em style="font-style: italic; color: #2c3e50;">$1</em>')
      .replace(/`(.*?)`/g, '<code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #667eea; font-size: 0.9em;">$1</code>')
      // Blockquotes ("> " was escaped to "&gt; ")
      .replace(/^&gt; (.*$)/gim, '<blockquote style="margin: 6px 0; padding: 8px 12px; border-left: 4px solid #667eea; background: #f8fafc; color: #4a5568; font-style: italic;">$1</blockquote>')
      // Bullets and numbered lists
      .replace(/^[•-] (.*$)/gim, '<li style="margin: 2px 0; padding-left: 8px;">$1</li>')
      .replace(/^(\d+)\. (.*$)/gim, '<li style="margin: 2px 0; padding-left: 8px;">$2</li>')
      // Paragraphs and line breaks
      .replace(/\n\n/g, '</p><p style="margin: 4px 0; line-height: 1.5;">')
      .replace(/\n/g, "<br>")
      .replace(/^(.+)$/gm, '<p style="margin: 4px 0; line-height: 1.5;">$1</p>')
      // Lists
      .replace(/(<li.*?<\/li>)/g, '<ul style="margin: 6px 0; padding-left: 16px;">$1</ul>')
      .replace(/<\/ul>\s*<ul>/g, "")
      .replace(/<ul[^>]*>\s*<\/ul>/g, "")
      // Empty paragraphs
      .replace(/<p[^>]*>\s*<\/p>/g, "")
      .replace(/<p[^>]*>\s*<br>\s*<\/p>/g, "")
  );
}
