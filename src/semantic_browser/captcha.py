"""CAPTCHA assist: turn a visual challenge into something a vision model can answer, then act on the answer.

Pipeline (all driven through the `captcha` verb):
  detect   -> provider (recaptcha / hcaptcha / turnstile / cloudflare / generic) + kind (checkbox / grid / canvas / text / wait)
  annotate -> numbered badges injected into the challenge frame, a tight screenshot (PNG) and optionally a PDF
  answer   -> `captcha select 1 5 9`, `captcha text abc`, `captcha open`, `captcha submit`, `captcha refresh`,
              `captcha drag X,Y X,Y` / `captcha click X,Y ...` (canvas puzzles; X,Y are pixels of the image, a ruler is drawn on it)

This module never tries to *solve* a challenge itself; it only makes the challenge legible to a (vision) model that the
caller already trusts, and performs the clicks that model asks for.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------------------------------------------
# provider knowledge
# --------------------------------------------------------------------------------------------------------------

_PROVIDER_FRAMES: list[tuple[str, str, str]] = [
    # (provider, url regex, kind)
    ("recaptcha", r"recaptcha/(?:api2|enterprise)/anchor", "checkbox"),
    ("recaptcha", r"recaptcha/(?:api2|enterprise)/bframe", "grid"),
    ("hcaptcha", r"hcaptcha\.com/.*frame=checkbox|newassets\.hcaptcha\.com/.*checkbox", "checkbox"),
    ("hcaptcha", r"hcaptcha\.com/.*frame=challenge", "grid"),
    ("turnstile", r"challenges\.cloudflare\.com/cdn-cgi/challenge-platform|challenges\.cloudflare\.com/turnstile", "checkbox"),
]

_GRID_SELECTORS = {
    "recaptcha": ["td.rc-imageselect-tile", ".rc-imageselect-tile"],
    "hcaptcha": [".task-grid .task-image .image", ".task-image .image", ".task-image"],
    "generic": [".tile", "[data-tile]", ".captcha-tile"],
}
_PROMPT_SELECTORS = {
    "recaptcha": [".rc-imageselect-desc-no-canonical", ".rc-imageselect-desc", ".rc-imageselect-instructions"],
    "hcaptcha": [".prompt-text", ".challenge-prompt"],
    "canvas": [".prompt-text", ".challenge-prompt", ".captcha-prompt", "[class*=prompt-text i]"],
}
_CHECKBOX_SELECTORS = {
    "recaptcha": ["#recaptcha-anchor", ".recaptcha-checkbox"],
    "hcaptcha": ["#checkbox", "[role=checkbox]"],
    "turnstile": ["input[type=checkbox]", "[role=checkbox]", "label"],
}
_RELOAD_SELECTORS = ["#recaptcha-reload-button", ".refresh-button", ".refresh", "[aria-label*='reload' i]", "[aria-label*='refresh' i]", "[title*='refresh' i]"]
_SUBMIT_RE = re.compile(r"^\s*(verify|validate|submit|next|confirm|done|continue|check|skip|send|proceed|ok|go|sign in|log in|login)\b", re.I)

_FIND_TILES_JS = r"""(opts) => {
  const old = document.getElementById('__sb_cap_marks'); if (old) old.remove();
  document.querySelectorAll('[data-sb-tile]').forEach(e => e.removeAttribute('data-sb-tile'));
  const vis = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width < 36 || r.height < 36 || r.width > 520 || r.height > 520) return false;
    const s = getComputedStyle(e);
    if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0) return false;
    return r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  let cands = [];
  for (const sel of opts.selectors) {
    try { cands = [...document.querySelectorAll(sel)].filter(vis); } catch (e) { cands = []; }
    if (cands.length >= 4) break;
  }
  if (cands.length < 4) {
    const all = [...document.querySelectorAll(
      'td,img,svg,canvas,[role=button],[role=checkbox],[role=gridcell],[class*=tile i],[class*=cell i],[data-tile],[class*=grid] > *'
    )].filter(vis);
    const groups = new Map();
    for (const e of all) {
      const r = e.getBoundingClientRect();
      const k = Math.round(r.width / 8) + 'x' + Math.round(r.height / 8);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(e);
    }
    let best = [];
    for (const g of groups.values()) {
      const flat = g.filter(e => !g.some(o => o !== e && o.contains(e)));
      if (flat.length >= 4 && flat.length <= 36 && flat.length > best.length) best = flat;
    }
    cands = best;
  }
  cands = cands.filter(e => !cands.some(o => o !== e && o.contains(e)));
  if (cands.length < 4) return { tiles: [], rows: 0, cols: 0, prompt: '', clip: null };
  cands.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  const rows = [];
  for (const e of cands) {
    const r = e.getBoundingClientRect();
    const row = rows.find(rw => Math.abs(rw.top - r.top) < r.height / 2);
    if (row) row.items.push(e); else rows.push({ top: r.top, items: [e] });
  }
  rows.forEach(rw => rw.items.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left));
  const ordered = rows.flatMap(rw => rw.items);
  const cols = Math.max(...rows.map(rw => rw.items.length));
  // prompt: provider selector, else nearest ancestor with readable text
  let prompt = '';
  for (const sel of opts.promptSelectors) {
    const p = document.querySelector(sel);
    if (p && p.innerText.trim()) { prompt = p.innerText.trim().replace(/\s+/g, ' '); break; }
  }
  let anc = ordered[0].parentElement;
  while (anc && !ordered.every(t => anc.contains(t))) anc = anc.parentElement;
  let box = anc;
  for (let up = 0; anc && up < 3 && !prompt; up++, anc = anc.parentElement) {
    const lines = (anc.innerText || '').split('\n').map(s => s.trim()).filter(s => s && !/^\d+$/.test(s) && !/^(verify|submit|next|skip|confirm|done|continue|reload|refresh)$/i.test(s));
    if (lines.length) { prompt = lines.slice(0, 3).join(' / ').slice(0, 220); box = anc; }
  }
  // badges + data attributes
  const layer = document.createElement('div');
  layer.id = '__sb_cap_marks';
  layer.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none';
  let x0 = 1e9, y0 = 1e9, x1 = 0, y1 = 0;
  const out = [];
  ordered.forEach((e, i) => {
    e.setAttribute('data-sb-tile', String(i + 1));
    const r = e.getBoundingClientRect();
    x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top); x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom);
    const b = document.createElement('div');
    b.textContent = String(i + 1);
    b.style.cssText = 'position:fixed;left:' + (r.left + 3) + 'px;top:' + (r.top + 3) + 'px;min-width:22px;height:22px;line-height:22px;' +
      'text-align:center;font:bold 14px/22px Arial,sans-serif;color:#fff;background:#d00;border:2px solid #fff;border-radius:11px;' +
      'box-shadow:0 0 3px #000;padding:0 3px;box-sizing:border-box';
    layer.appendChild(b);
    out.push({ i: i + 1, x: r.left, y: r.top, w: r.width, h: r.height });
  });
  document.documentElement.appendChild(layer);
  if (box) { const r = box.getBoundingClientRect(); x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top); x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); }
  const pad = 8;
  const clip = { x: Math.max(0, x0 - pad), y: Math.max(0, y0 - pad), w: Math.min(innerWidth, x1 + pad) - Math.max(0, x0 - pad), h: Math.min(innerHeight, y1 + pad) - Math.max(0, y0 - pad) };
  return { tiles: out, rows: rows.length, cols, prompt, clip };
}"""


_FIND_CANVAS_JS = r"""(opts) => {
  const old = document.getElementById('__sb_cap_marks'); if (old) old.remove();
  const vis = (e) => {
    const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width >= 120 && r.height >= 80 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  const cvs = [...document.querySelectorAll('canvas')].filter(vis).sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height - a.getBoundingClientRect().width * a.getBoundingClientRect().height);
  if (!cvs.length) return null;
  const c = cvs[0], cr = c.getBoundingClientRect();
  const inFrame = window.top !== window;
  if (!inFrame && !opts.force) {   // in the main page a canvas only counts when it is named like a challenge
    let n = c, hit = false;
    for (let i = 0; n && i < 4; i++, n = n.parentElement) if (/captcha|puzzle|slider|challenge|verify/i.test((n.id || '') + ' ' + (n.className && n.className.toString ? n.className.toString() : '') + ' ' + (n.getAttribute('aria-label') || ''))) hit = true;
    if (!hit) return null;
  }
  let prompt = '', pel = null;
  for (const sel of opts.promptSelectors) { const p = document.querySelector(sel); if (p && p.innerText.trim()) { pel = p; prompt = p.innerText.trim().replace(/\s+/g, ' '); break; } }
  if (!prompt) {
    for (const p of document.querySelectorAll('[class*=prompt i],[class*=instruction i],[id*=prompt i],[id*=instruction i],h1,h2,h3,[role=heading]')) {
      const t = (p.innerText || '').trim().replace(/\s+/g, ' ');
      const r = p.getBoundingClientRect();
      if (t && t.length <= 220 && r.width > 0 && r.height > 0 && !p.contains(c)) { pel = p; prompt = t; break; }
    }
  }
  let x = 0, y = 0, w = innerWidth, h = innerHeight;
  if (!inFrame) {
    let box = c, up = c.parentElement;
    for (let i = 0; up && i < 3 && up !== document.body; i++, up = up.parentElement) {
      const r = up.getBoundingClientRect();
      if (r.width > 700 || r.height > 800) break;
      box = up; if (pel && up.contains(pel)) break;
    }
    const r = box.getBoundingClientRect();
    const pad = 6;
    x = Math.max(0, r.left - pad); y = Math.max(0, r.top - pad);
    w = Math.min(innerWidth, r.right + pad) - x; h = Math.min(innerHeight, r.bottom + pad) - y;
  }
  // coordinate ruler: faint lines every 50px, numbered every 100px, measured from the top-left of the captured image
  const layer = document.createElement('div');
  layer.id = '__sb_cap_marks';
  layer.style.cssText = 'position:fixed;left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px;z-index:2147483647;pointer-events:none;overflow:hidden';
  const add = (css, text) => { const d = document.createElement('div'); d.style.cssText = 'position:absolute;' + css; if (text) d.textContent = text; layer.appendChild(d); };
  for (let gx = 0; gx <= w; gx += 50) add('left:' + gx + 'px;top:0;width:1px;height:100%;background:rgba(255,0,255,' + (gx % 100 ? 0.25 : 0.55) + ')');
  for (let gy = 0; gy <= h; gy += 50) add('top:' + gy + 'px;left:0;height:1px;width:100%;background:rgba(255,0,255,' + (gy % 100 ? 0.25 : 0.55) + ')');
  const lab = 'font:bold 10px/10px Arial,sans-serif;color:#fff;background:rgba(160,0,160,.85);padding:1px 2px;';
  for (let gx = 0; gx <= w; gx += 100) for (let gy = 0; gy <= h; gy += 100) add('left:' + (gx + 2) + 'px;top:' + (gy + 2) + 'px;' + lab, gx + ',' + gy);
  document.documentElement.appendChild(layer);
  return { prompt, clip: { x, y, w, h }, canvas: { x: cr.left, y: cr.top, w: cr.width, h: cr.height } };
}"""

_ERROR_JS = r"""() => {
  const re = /(please )?try again|incorrect|wrong (answer|selection)|verification failed|invalid (answer|response|captcha)|did not match|didn't match/i;
  for (const e of document.querySelectorAll('div,span,p,label,[role=alert],[aria-live]')) {
    if (e.children.length > 2) continue;
    const t = (e.innerText || '').trim().replace(/\s+/g, ' ');
    if (!t || t.length > 80 || !re.test(t)) continue;
    const r = e.getBoundingClientRect();
    let shown = r.width > 2 && r.height > 2 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight;
    try { shown = shown && e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }); } catch (err) { /* older engines */ }
    for (let n = e; shown && n && n.nodeType === 1; n = n.parentElement) { const st = getComputedStyle(n); if (+st.opacity < 0.2 || st.transform.startsWith('matrix(0,')) shown = false; }
    if (shown) return t;
  }
  return '';
}"""

_CLEAR_MARKS_JS = """() => { const m = document.getElementById('__sb_cap_marks'); if (m) m.remove();
  document.querySelectorAll('[data-sb-tile]').forEach(e => e.removeAttribute('data-sb-tile')); }"""

_GENERIC_JS = r"""() => {
  const txt = (document.body ? document.body.innerText : '').slice(0, 4000);
  const title = document.title || '';
  const interstitial = /just a moment|attention required|checking your browser|verify you are human|are you a robot|unusual traffic|press (&|and) hold/i.test(title + ' ' + txt.slice(0, 1500));
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 10 && r.height > 10 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const img = [...document.querySelectorAll('img')].find(e => vis(e) && /captcha/i.test((e.alt || '') + (e.src || '') + (e.id || '') + (e.className || '')));
  // only text-like fields: a submit button whose id merely says "recaptcha-demo-submit" is not an answer box
  const inp = [...document.querySelectorAll('input')].find(e => vis(e) && /^(text|search|tel|number|)$/i.test(e.getAttribute('type') || '') &&
    /captcha/i.test((e.name || '') + (e.id || '') + (e.placeholder || '') + (e.getAttribute('aria-label') || '')));
  const cv = [...document.querySelectorAll('canvas')].some(e => { const r = e.getBoundingClientRect(); return r.width >= 120 && r.height >= 80 && /captcha|puzzle|slider|challenge/i.test((e.id||'')+' '+(e.className||'')+' '+((e.parentElement&&(e.parentElement.id+' '+e.parentElement.className))||'')); });
  return { interstitial, title, hasImage: !!img, hasInput: !!inp, hasCanvas: cv };
}"""


# --------------------------------------------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------------------------------------------


@dataclass
class Challenge:
    provider: str
    kind: str  # checkbox | grid | text | interstitial | none
    frame: Any = None
    frame_element: Any = None
    prompt: str = ""
    rows: int = 0
    cols: int = 0
    tiles: int = 0
    image_path: str | None = None
    pdf_path: str | None = None
    notes: list[str] = field(default_factory=list)
    origin: tuple[float, float] | None = None  # page position (CSS px) of the image's top-left corner: kind=canvas only
    size: tuple[float, float] | None = None  # image size in px
    error: str = ""  # the widget's own failure text ("Please try again.") when it is showing one

    def describe(self) -> str:
        if self.kind == "none":
            return "No CAPTCHA detected on this page."
        head = f"CAPTCHA: provider={self.provider} kind={self.kind}"
        if self.kind == "grid":
            head += f" grid={self.rows}x{self.cols} tiles={self.tiles}"
        lines = [head]
        if self.prompt:
            lines.append(f'Prompt: "{self.prompt}"')
        if self.error:
            lines.append(f'Widget message: "{self.error}"')
        if self.image_path:
            lines.append(f"Image: {self.image_path}")
        if self.pdf_path:
            lines.append(f"PDF: {self.pdf_path}")
        lines.extend(self.notes)
        lines.append(_next_step(self))
        return "\n".join(lines)


def _next_step(ch: Challenge) -> str:
    if ch.kind == "grid":
        return "Next: look at the image (tiles numbered left->right, top->bottom), then `captcha select N N N`, then `captcha submit`."
    if ch.kind == "canvas":
        return (
            "Next: look at the image; the magenta ruler gives pixel positions (X,Y from its top-left). Drag puzzle: `captcha drag X,Y X,Y` "
            "(from, to). Click puzzle: `captcha click X,Y [X,Y ...]`. Then `captcha submit` if the widget has a Verify button."
        )
    if ch.kind == "checkbox":
        return "Next: `captcha open` to tick the checkbox, then run `captcha` again to see whether an image challenge appeared."
    if ch.kind == "text":
        return "Next: read the characters in the image, then `captcha text <answer>` and `captcha submit`."
    if ch.kind == "interstitial":
        return "Next: this is a browser-check page. `wait 4000` then `view`; if it persists, run `shot` and decide whether human help is needed."
    return ""


# --------------------------------------------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------------------------------------------


async def _frame_visible(frame: Any) -> tuple[Any | None, bool]:
    try:
        el = await frame.frame_element()
        return el, bool(await el.is_visible())
    except Exception:
        return None, False


async def detect(page: Any) -> list[Challenge]:
    """All challenges currently on the page, most actionable first (grid > text > checkbox > interstitial)."""
    found: list[Challenge] = []
    for frame in list(page.frames):
        url = frame.url or ""
        for provider, pattern, kind in _PROVIDER_FRAMES:
            if re.search(pattern, url):
                el, visible = await _frame_visible(frame)
                if not visible:
                    continue
                box = None
                try:
                    box = await el.bounding_box() if el else None
                except Exception:
                    box = None
                if box and box["width"] < 20:
                    continue
                found.append(Challenge(provider=provider, kind=kind, frame=frame, frame_element=el))
                break
    try:
        g = await page.main_frame.evaluate(_GENERIC_JS)
    except Exception:
        g = {}
    # a lone weak signal (image *or* input) must not outrank a recognised provider widget
    if (g.get("hasImage") and g.get("hasInput")) or ((g.get("hasImage") or g.get("hasInput")) and not found):
        found.append(Challenge(provider="generic", kind="text", frame=page.main_frame))
    if not any(c.kind == "grid" for c in found):
        # generic grids (and hand-rolled challenges) live in a frame we already know, or the main frame
        for frame in [c.frame for c in found if c.provider != "generic"] + [page.main_frame]:
            probe = await _probe_tiles(frame, "generic")
            if probe["tiles"]:
                prov = next((c.provider for c in found if c.frame is frame), "generic")
                found.append(Challenge(provider=prov, kind="grid", frame=frame))
                break
    if g.get("hasCanvas") and not any(c.kind in {"grid", "canvas"} for c in found):
        found.append(Challenge(provider="generic", kind="canvas", frame=page.main_frame))
    if g.get("interstitial") and not found:
        found.append(Challenge(provider="cloudflare" if "moment" in (g.get("title") or "").lower() else "generic", kind="interstitial", frame=page.main_frame))
    order = {"grid": 0, "canvas": 0, "text": 1, "checkbox": 2, "interstitial": 3}
    found.sort(key=lambda c: order.get(c.kind, 9))
    # a visible grid supersedes the checkbox of the same provider
    if any(c.kind == "grid" for c in found):
        found = [c for c in found if c.kind != "checkbox" or not any(o.kind == "grid" and o.provider == c.provider for o in found)]
    return found


async def _probe_canvas(frame: Any, provider: str, *, force: bool = False) -> dict[str, Any] | None:
    try:
        res = await frame.evaluate(_FIND_CANVAS_JS, {"promptSelectors": _PROMPT_SELECTORS.get(provider, []) + _PROMPT_SELECTORS["canvas"], "force": force})
    except Exception:
        return None
    return res if isinstance(res, dict) else None


async def _probe_tiles(frame: Any, provider: str) -> dict[str, Any]:
    opts = {
        "selectors": _GRID_SELECTORS.get(provider, []) + _GRID_SELECTORS["generic"],
        "promptSelectors": _PROMPT_SELECTORS.get(provider, []),
    }
    try:
        return await frame.evaluate(_FIND_TILES_JS, opts)
    except Exception:
        return {"tiles": [], "rows": 0, "cols": 0, "prompt": "", "clip": None}


# --------------------------------------------------------------------------------------------------------------
# annotate
# --------------------------------------------------------------------------------------------------------------


def _out_dir() -> Path:
    from semantic_browser.daemon import paths

    return paths.private_dir(paths.home() / "captcha")


async def annotate(page: Any, ch: Challenge, *, pdf: bool = False, out_dir: Path | None = None) -> Challenge:
    """Fill in prompt/tiles and write `image_path` (and `pdf_path`) for the challenge."""
    out = out_dir or _out_dir()
    stamp = time.strftime("%H%M%S")
    clip_abs: dict[str, float] | None = None
    offset = {"x": 0.0, "y": 0.0}
    if ch.frame_element is not None:
        try:
            await ch.frame_element.scroll_into_view_if_needed(timeout=1500)
            fb = await ch.frame_element.bounding_box()
            if fb:
                offset = {"x": fb["x"], "y": fb["y"]}
                clip_abs = {"x": fb["x"], "y": fb["y"], "width": fb["width"], "height": fb["height"]}
        except Exception:
            pass
    if ch.kind == "grid":
        probe = await _probe_tiles(ch.frame, ch.provider)
        ch.tiles, ch.rows, ch.cols = len(probe["tiles"]), probe["rows"], probe["cols"]
        ch.prompt = probe.get("prompt") or ch.prompt
        c = probe.get("clip")
        if c:
            clip_abs = {"x": offset["x"] + c["x"], "y": offset["y"] + c["y"], "width": c["w"], "height": c["h"]}
        elif not ch.tiles:  # a "grid" frame without tiles (hCaptcha drag / click puzzles) draws on a <canvas>
            ch.kind = "canvas"
    if ch.kind == "canvas":
        cprobe = await _probe_canvas(ch.frame, ch.provider, force=ch.provider != "generic")
        if cprobe is None:
            ch.notes.append("(no canvas found in the challenge; the whole frame is shown without a ruler)")
        else:
            ch.prompt = cprobe.get("prompt") or ch.prompt
            c = cprobe["clip"]
            clip_abs = {"x": offset["x"] + c["x"], "y": offset["y"] + c["y"], "width": c["w"], "height": c["h"]}
    elif ch.kind == "text":
        clip_abs = await _text_captcha_clip(page, ch) or clip_abs
    shot_kwargs: dict[str, Any] = {"type": "png", "scale": "css"}  # one image pixel per CSS pixel: the ruler's numbers are the click coordinates
    if clip_abs and clip_abs["width"] > 10 and clip_abs["height"] > 10:
        vp = page.viewport_size or {"width": 1280, "height": 800}
        x = max(0.0, clip_abs["x"])
        y = max(0.0, clip_abs["y"])
        shot_kwargs["clip"] = {
            "x": x, "y": y,
            "width": max(10.0, min(clip_abs["width"], vp["width"] - x)),
            "height": max(10.0, min(clip_abs["height"], vp["height"] - y)),
        }
    if ch.kind in {"grid", "canvas", "text"}:
        try:
            ch.error = str(await ch.frame.evaluate(_ERROR_JS) or "")[:80]
        except Exception:
            ch.error = ""
    path = out / f"captcha-{stamp}-{ch.provider}-{ch.kind}.png"
    try:
        png = await page.screenshot(**shot_kwargs)
    except Exception:
        shot_kwargs.pop("clip", None)
        png = await page.screenshot(**shot_kwargs)
        ch.notes.append("(could not crop to the challenge; image is the whole viewport)")
    path.write_bytes(png)
    ch.image_path = str(path)
    if ch.kind == "canvas":
        sc = shot_kwargs.get("clip") or {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
        ch.origin, ch.size = (float(sc["x"]), float(sc["y"])), (float(sc["width"]), float(sc["height"]))
    if pdf:
        jpg = await page.screenshot(**{**shot_kwargs, "type": "jpeg", "quality": 85})
        w, h = _jpeg_size(jpg)
        pdf_path = path.with_suffix(".pdf")
        pdf_path.write_bytes(jpeg_to_pdf(jpg, w, h, caption=ch.prompt or f"{ch.provider} {ch.kind}"))
        ch.pdf_path = str(pdf_path)
    # remove badges / ruler so the live page is left untouched
    if ch.kind in {"grid", "canvas"}:
        try:
            await ch.frame.evaluate("() => { const m = document.getElementById('__sb_cap_marks'); if (m) m.remove(); }")
        except Exception:
            pass
    return ch


async def _text_captcha_clip(page: Any, ch: Challenge) -> dict[str, float] | None:
    try:
        return await ch.frame.evaluate(
            r"""() => {
              const vis = e => { const r = e.getBoundingClientRect(); return r.width > 10 && r.height > 10; };
              const img = [...document.querySelectorAll('img')].find(e => vis(e) && /captcha/i.test((e.alt||'')+(e.src||'')+(e.id||'')+(e.className||'')));
              const inp = [...document.querySelectorAll('input')].find(e => vis(e) && /captcha/i.test((e.name||'')+(e.id||'')+(e.placeholder||'')));
              const t = img || inp; if (!t) return null;
              const r = t.getBoundingClientRect(); return { x: Math.max(0, r.left - 10), y: Math.max(0, r.top - 10), width: r.width + 20, height: r.height + 20 };
            }"""
        )
    except Exception:
        return None


# --------------------------------------------------------------------------------------------------------------
# act
# --------------------------------------------------------------------------------------------------------------


async def open_checkbox(page: Any, ch: Challenge) -> str:
    sels = _CHECKBOX_SELECTORS.get(ch.provider, ["[role=checkbox]", "input[type=checkbox]"])
    for sel in sels:
        try:
            loc = ch.frame.locator(sel).first
            if await loc.count():
                await loc.click(timeout=2500)
                return f"clicked the {ch.provider} checkbox"
        except Exception:
            continue
    if ch.frame_element is not None:  # closed shadow roots (Turnstile): click where the box is drawn
        box = await ch.frame_element.bounding_box()
        if box:
            await page.mouse.click(box["x"] + min(30, box["width"] / 4), box["y"] + box["height"] / 2)
            return f"clicked the {ch.provider} widget at its checkbox position"
    raise RuntimeError("could not find a checkbox to click")


async def select_tiles(ch: Challenge, numbers: list[int]) -> str:
    if ch.kind != "grid":
        raise RuntimeError("no image grid is active; run `captcha` first")
    clicked: list[int] = []
    missing: list[int] = []
    for n in numbers:
        loc = ch.frame.locator(f'[data-sb-tile="{n}"]').first
        try:
            if not await loc.count():
                missing.append(n)
                continue
            await loc.click(timeout=2500)
            clicked.append(n)
        except Exception:
            missing.append(n)
    msg = f"clicked tile(s) {clicked}" if clicked else "clicked nothing"
    if missing:
        msg += f"; could not click {missing} (tile numbers are re-assigned each time you run `captcha`)"
    return msg


_POINT_RE = re.compile(r"^\d+(?:\.\d+)?$")


def parse_points(words: list[str]) -> list[tuple[float, float]]:
    """`50,90`, `(50,90)`, `x=50,y=90`, `50 90`, `50,90;60,70` -> [(50.0, 90.0), ...]; anything else is an error, never a guess."""
    text = re.sub(r"[xyXY]\s*=", "", " ".join(words)).replace(";", " ").replace("(", " ").replace(")", " ")
    toks = [t for t in re.split(r"[\s,]+", text) if t]
    if len(toks) < 2 or len(toks) % 2 or not all(_POINT_RE.match(t) for t in toks):
        raise ValueError("expected pixel positions from the image's ruler, like `120,80` (several allowed: `120,80 200,40`)")
    nums = [float(t) for t in toks]
    return list(zip(nums[0::2], nums[1::2], strict=True))


def to_page(ch: Challenge, pt: tuple[float, float]) -> tuple[float, float]:
    """Image pixel -> page CSS pixel for a canvas challenge, refusing positions outside the captured image."""
    if ch.kind != "canvas" or ch.origin is None or ch.size is None:
        raise RuntimeError("no coordinate challenge is active; run `captcha` on a page that shows a drag or click puzzle first")
    x, y = pt
    w, h = ch.size
    if x < 0 or y < 0 or x > w or y > h:
        raise ValueError(f"({x:g},{y:g}) is outside the challenge image ({w:g}x{h:g}); use the numbers on the image's ruler")
    return ch.origin[0] + x, ch.origin[1] + y


async def drag_points(page: Any, ch: Challenge, start: tuple[float, float], end: tuple[float, float]) -> str:
    (x1, y1), (x2, y2) = to_page(ch, start), to_page(ch, end)
    await page.mouse.move(x1, y1)
    await page.mouse.down()
    steps = 24
    for i in range(1, steps + 1):  # a plain straight path in small steps: puzzle widgets need intermediate mouse moves
        await page.mouse.move(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
        await page.wait_for_timeout(12)
    await page.mouse.up()
    return f"dragged from ({start[0]:g},{start[1]:g}) to ({end[0]:g},{end[1]:g})"


async def click_points(page: Any, ch: Challenge, points: list[tuple[float, float]]) -> str:
    for pt in points:  # validate every point before touching the page
        to_page(ch, pt)
    for pt in points:
        x, y = to_page(ch, pt)
        await page.mouse.click(x, y)
        await page.wait_for_timeout(180)
    return "clicked " + " ".join(f"({x:g},{y:g})" for x, y in points)


async def type_text(page: Any, ch: Challenge, text: str) -> str:
    frame = ch.frame or page.main_frame
    handle = await frame.evaluate_handle(
        r"""() => {
          const vis = e => { const r = e.getBoundingClientRect(); return r.width > 10 && r.height > 10; };
          const ins = [...document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),textarea')].filter(vis);
          return ins.find(e => /captcha/i.test((e.name||'')+(e.id||'')+(e.placeholder||'')+(e.getAttribute('aria-label')||''))) || ins[0] || null;
        }"""
    )
    el = handle.as_element()
    if el is None:
        raise RuntimeError("no text input found for the CAPTCHA answer")
    await el.fill(text, timeout=2500)
    return f"typed {len(text)} characters into the CAPTCHA answer field"


async def submit(page: Any, ch: Challenge) -> str:
    frame = ch.frame or page.main_frame
    for sel in ("#recaptcha-verify-button", ".button-submit", "button[type=submit]", "input[type=submit]", "input[type=button]", "[role=button]", "button"):
        try:
            loc = frame.locator(sel)
            n = min(await loc.count(), 12)
            for i in range(n):
                cand = loc.nth(i)
                if not await cand.is_visible():
                    continue
                label = (await cand.inner_text()) if not sel.startswith("input[") else (await cand.get_attribute("value") or "")
                if sel in {"#recaptcha-verify-button", ".button-submit"} or _SUBMIT_RE.match(label or ""):
                    await cand.click(timeout=2500)
                    return f"clicked {label.strip() or sel!r}"
        except Exception:
            continue
    raise RuntimeError("no Verify/Submit/Next button found in the challenge")


async def refresh(ch: Challenge) -> str:
    for sel in _RELOAD_SELECTORS:
        try:
            loc = ch.frame.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=2000)
                return "requested a new challenge"
        except Exception:
            continue
    raise RuntimeError("no reload/refresh control found")


async def clear_marks(page: Any) -> None:
    for fr in list(page.frames):
        try:
            await fr.evaluate(_CLEAR_MARKS_JS)
        except Exception:
            pass


# --------------------------------------------------------------------------------------------------------------
# minimal PDF writer (single JPEG page + caption), stdlib only
# --------------------------------------------------------------------------------------------------------------


def _jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            return (data[i + 7] << 8) | data[i + 8], (data[i + 5] << 8) | data[i + 6]
        seg = (data[i + 2] << 8) | data[i + 3]
        i += 2 + seg
    return 600, 400


def _pdf_escape(s: str) -> str:
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def jpeg_to_pdf(jpeg: bytes, width: int, height: int, caption: str = "") -> bytes:
    """One-page PDF: caption line above the (unmodified) JPEG. Page size follows the image at 0.75 pt/px."""
    iw, ih = width * 0.75, height * 0.75
    head = 36.0
    pw, ph = max(iw + 24, 240.0), ih + head + 12
    cap = _pdf_escape(caption[:160])
    content = (
        f"BT /F1 11 Tf 12 {ph - 22:.1f} Td ({cap}) Tj ET\n"
        f"q {iw:.1f} 0 0 {ih:.1f} 12 6 cm /Im0 Do Q\n"
    ).encode("latin-1")
    objs: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.1f} {ph:.1f}] /Contents 4 0 R "
            f"/Resources << /Font << /F1 5 0 R >> /XObject << /Im0 6 0 R >> >> >>"
        ).encode(),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB "
            f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpeg)} >>\nstream\n"
        ).encode()
        + jpeg
        + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
