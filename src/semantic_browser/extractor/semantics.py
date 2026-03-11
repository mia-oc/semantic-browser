"""Deterministic DOM semantics extraction."""

from __future__ import annotations

from typing import Any


EXTRACT_JS = """
() => {
  const isVisible = (el) => {
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const roleOrTag = (el) => el.getAttribute('role') || el.tagName.toLowerCase();
  const nameFor = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const labels = labelledBy.split(/\\s+/).map(id => document.getElementById(id)).filter(Boolean);
      const txt = labels.map(l => l.textContent?.trim() || '').join(' ').trim();
      if (txt) return txt;
    }
    if (el.labels && el.labels.length) {
      const txt = Array.from(el.labels).map(l => l.textContent?.trim() || '').join(' ').trim();
      if (txt) return txt;
    }
    const ph = el.getAttribute('placeholder');
    if (ph) return ph.trim();
    const txt = el.innerText || el.textContent || '';
    return txt.trim().slice(0, 120);
  };

  const all = Array.from(document.querySelectorAll('a[href],button,input,select,textarea,[role=\"button\"],[role=\"link\"],[role=\"checkbox\"],[role=\"textbox\"],main,nav,header,footer,aside,section,article,form,dialog,table,ul,ol,h1,h2,h3,[role=\"heading\"]'));
  const visible = all.filter(isVisible);
  const nodes = visible.slice(0, 2000).map((el, idx) => {
    const tag = el.tagName.toLowerCase();
    const role = roleOrTag(el);
    const name = nameFor(el);
    const type = el.getAttribute('type') || '';
    const id = el.id || '';
    const href = el.getAttribute('href') || '';
    const disabled = el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true';
    const checked = el.getAttribute('aria-checked') === 'true' || (tag === 'input' && el.checked === true);
    const expanded = el.getAttribute('aria-expanded');
    const rect = el.getBoundingClientRect();
    const inViewport = rect.bottom >= 0 && rect.right >= 0 && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
    return {
      dom_index: idx,
      tag,
      role,
      name,
      type,
      id,
      href,
      disabled,
      checked,
      expanded,
      in_viewport: inViewport,
      rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
      text: (el.innerText || '').trim().slice(0, 300),
    };
  });

  return {
    title: document.title,
    node_count: nodes.length,
    nodes,
  };
}
"""


async def extract_semantics(page: Any) -> dict[str, Any]:
    return await page.evaluate(EXTRACT_JS)
