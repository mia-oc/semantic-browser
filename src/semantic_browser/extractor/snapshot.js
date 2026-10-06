/* Semantic Browser v2 snapshot — one DOM walk per frame.
 *
 * Returns { gen, title, url, scroll, nodes, flow, layer, frames, stats }.
 *  - nodes: interactive elements, landmarks and headings, in document order (legacy-compatible fields + new ones)
 *  - flow : compact token stream describing the reading order of the page (text, blocks, element refs, regions)
 *  - refs : each interactive element gets a stable integer id (per document) kept in window.__sb so actions can
 *           grab the *exact* element again (no name/ordinal guessing).
 * Handles open shadow roots, same-origin and (via per-frame calls from Python) cross-origin iframes.
 */
(opts) => {
  const T0 = performance.now();
  const MAX_NODES = opts.maxNodes || 3000;
  const MAX_FLOW = opts.maxFlow || 40000;
  const BUDGET_MS = opts.budgetMs || 400;
  const W = window;
  const REG = W.__sb || (W.__sb = { gen: Math.random().toString(36).slice(2, 8), next: 1, ids: new WeakMap(), els: new Map() });
  const VW = W.innerWidth || 1280, VH = W.innerHeight || 800;
  const SX = W.scrollX || 0, SY = W.scrollY || 0;

  const idFor = (el) => {
    let id = REG.ids.get(el);
    if (!id) { id = REG.next++; REG.ids.set(el, id); REG.els.set(id, new WeakRef(el)); }
    return id;
  };
  if (REG.els.size > 8000) { for (const [k, w] of REG.els) if (!w.deref()) REG.els.delete(k); }

  const SKIP = new Set(['script', 'style', 'noscript', 'template', 'head', 'link', 'meta', 'title', 'base', 'datalist', 'option', 'optgroup', 'source', 'track', 'param', 'map', 'defs', 'clippath', 'lineargradient', 'path', 'g', 'use', 'symbol', 'mask', 'pattern', 'filter']);
  const INLINE = new Set(['a', 'abbr', 'b', 'bdi', 'bdo', 'cite', 'code', 'data', 'dfn', 'em', 'font', 'i', 'kbd', 'label', 'mark', 'q', 's', 'samp', 'small', 'span', 'strong', 'sub', 'sup', 'time', 'u', 'var', 'wbr', 'img']);
  const LANDMARK = { nav: 'nav', header: 'header', footer: 'footer', aside: 'aside', main: 'main', form: 'form', dialog: 'dialog', article: 'article', section: 'section' };
  const ROLE_LANDMARK = { navigation: 'nav', banner: 'header', contentinfo: 'footer', complementary: 'aside', main: 'main', dialog: 'dialog', alertdialog: 'dialog', form: 'form', search: 'form' };
  const CLICK_ROLES = new Set(['button', 'link', 'tab', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'option', 'treeitem', 'switch', 'checkbox', 'radio', 'combobox', 'textbox', 'searchbox', 'slider', 'spinbutton', 'gridcell']);
  const FW_CLICK = ['ng-click', 'data-ng-click', 'ng-dblclick', 'ng-submit', 'on-click', 'v-on:click', '@click', 'x-on:click', 'x-on:submit', 'data-action', 'data-onclick', 'data-click', 'onclick'];
  const STANDARD = new Set(['a', 'abbr', 'address', 'area', 'article', 'aside', 'audio', 'b', 'base', 'bdi', 'bdo', 'blockquote', 'body', 'br', 'button', 'canvas', 'caption', 'cite', 'code', 'col', 'colgroup', 'data', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog', 'div', 'dl', 'dt', 'em', 'embed', 'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hgroup', 'hr', 'html', 'i', 'iframe', 'img', 'input', 'ins', 'kbd', 'label', 'legend', 'li', 'link', 'main', 'map', 'mark', 'menu', 'meta', 'meter', 'nav', 'noscript', 'object', 'ol', 'optgroup', 'option', 'output', 'p', 'param', 'picture', 'pre', 'progress', 'q', 'rp', 'rt', 'ruby', 's', 'samp', 'script', 'section', 'select', 'slot', 'small', 'source', 'span', 'strong', 'style', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'template', 'textarea', 'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'track', 'u', 'ul', 'var', 'video', 'wbr', 'svg']);
  const AD_HOST = /(doubleclick|googlesyndication|adsystem|adnxs|taboola|outbrain|criteo|amazon-adsystem|adservice|scorecardresearch|facebook\.com\/tr|googletagmanager|connect\.facebook)/i;
  const ICONS = ['search', 'close', 'menu', 'cart', 'basket', 'bag', 'user', 'account', 'login', 'next', 'prev', 'previous', 'back', 'arrow', 'play', 'pause', 'share', 'like', 'heart', 'star', 'filter', 'sort', 'settings', 'cog', 'plus', 'minus', 'add', 'remove', 'delete', 'trash', 'edit', 'download', 'upload', 'home', 'mail', 'email', 'phone', 'info', 'help', 'calendar', 'location', 'pin', 'notification', 'bell', 'chat', 'expand', 'collapse', 'chevron', 'more', 'upvote', 'downvote'];

  const nodes = [];
  const flow = [];
  const elOf = [];            // nodes index -> element (for ctx post-pass)
  const labelCount = new Map();
  const frames = [];
  const stats = { visited: 0, truncated: false };
  let layerSet = new Set();
  let layerEls = [];

  const cstyle = (el) => { try { return getComputedStyle(el); } catch (e) { return null; } };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const isVisible = (el) => {
    const s = cstyle(el);
    if (s && s.display === 'contents') return true;   // no box of its own, children decide
    try {
      if (el.checkVisibility) return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    } catch (e) { /* fall through */ }
    return !!s && s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
  };
  const rootOf = (el) => el.getRootNode ? el.getRootNode() : document;
  const kids = (el) => {
    if (el.shadowRoot) return Array.from(el.shadowRoot.childNodes);
    if (el.localName === 'slot') {
      const a = el.assignedNodes ? el.assignedNodes({ flatten: true }) : [];
      return a.length ? a : Array.from(el.childNodes);
    }
    return Array.from(el.childNodes);
  };

  // Visible text of a subtree (bounded) — used for accessible names.
  const textOf = (el, limit, skipSelf) => {
    let out = '';
    const rec = (n, depth) => {
      if (out.length >= limit || depth > 12) return;
      if (n.nodeType === 3) { out += n.data; return; }
      if (n.nodeType !== 1) return;
      const t = n.localName;
      if (SKIP.has(t) && t !== 'option') return;
      if (n.hasAttribute && n.hasAttribute('hidden')) return;
      if (n !== el && !isVisible(n)) return;
      if (t === 'img') { const alt = n.getAttribute('alt'); if (alt) out += ' ' + alt + ' '; return; }
      if (t === 'input' && /^(submit|button|reset)$/.test(n.type)) { out += ' ' + (n.value || '') + ' '; return; }
      const pad = !INLINE.has(t);
      if (pad) out += ' ';
      if (n.shadowRoot) { for (const c of n.shadowRoot.childNodes) rec(c, depth + 1); }
      else for (const c of kids(n)) rec(c, depth + 1);
      if (pad) out += ' ';
    };
    if (skipSelf) { for (const c of kids(el)) rec(c, 1); } else rec(el, 0);
    return norm(out).slice(0, limit);
  };

  const labelledBy = (el) => {
    const v = el.getAttribute('aria-labelledby');
    if (!v) return '';
    const r = rootOf(el);
    return norm(v.split(/\s+/).map((id) => { const t = r.getElementById ? r.getElementById(id) : null; return t ? textOf(t, 120) : ''; }).join(' '));
  };

  const iconHint = (el) => {
    const hay = ((el.id || '') + ' ' + (el.getAttribute('class') || '') + ' ' + (el.getAttribute('name') || '') + ' ' + (el.getAttribute('data-testid') || '') + ' ' + (el.getAttribute('data-icon') || '')).toLowerCase();
    for (const w of ICONS) if (hay.indexOf(w) >= 0) return w + ' (icon)';
    const inner = el.querySelector && el.querySelector('[class],[data-icon],svg use');
    if (inner) {
      const h2 = ((inner.getAttribute('class') || '') + ' ' + (inner.getAttribute('data-icon') || '') + ' ' + (inner.getAttribute('href') || inner.getAttribute('xlink:href') || '')).toLowerCase();
      for (const w of ICONS) if (h2.indexOf(w) >= 0) return w + ' (icon)';
    }
    return '';
  };

  const nameFor = (el, tag, role) => {
    let n = el.getAttribute('aria-label');
    if (n && norm(n)) return norm(n).slice(0, 160);
    n = labelledBy(el);
    if (n) return n.slice(0, 160);
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      const type = (el.type || '').toLowerCase();
      if (/^(submit|button|reset)$/.test(type)) { const v = el.value || el.getAttribute('value'); if (v) return norm(v).slice(0, 160); }
      if (type === 'image') { const a = el.getAttribute('alt') || el.getAttribute('title'); if (a) return norm(a); }
      if (el.labels && el.labels.length) { const t = norm(Array.from(el.labels).map((l) => textOf(l, 100, false)).join(' ')); if (t) return t.slice(0, 160); }
      const ph = el.getAttribute('placeholder'); if (ph) return norm(ph).slice(0, 160);
      const ti = el.getAttribute('title'); if (ti) return norm(ti).slice(0, 160);
      const nm = el.getAttribute('name') || el.id; if (nm) return norm(nm.replace(/[_-]+/g, ' ')).slice(0, 80);
      return iconHint(el) || '';
    }
    const t = textOf(el, 200, false);
    if (t) return t.length > 160 ? t.slice(0, 157) + '...' : t;
    const ti = el.getAttribute('title'); if (ti) return norm(ti).slice(0, 160);
    const d = el.querySelector && el.querySelector('[aria-label],[title],img[alt]');
    if (d) { const a = d.getAttribute('aria-label') || d.getAttribute('title') || d.getAttribute('alt'); if (a) return norm(a).slice(0, 160); }
    return iconHint(el);
  };

  const cssPath = (el) => {
    if (el.id) { try { return '#' + CSS.escape(el.id); } catch (e) { return ''; } }
    const tag = el.localName; let cls = '';
    try { cls = Array.from(el.classList || []).slice(0, 3).map((c) => '.' + CSS.escape(c)).join(''); } catch (e) { cls = ''; }
    return tag + cls;
  };

  const rectOf = (el) => { const r = el.getBoundingClientRect(); return { x: r.x + SX, y: r.y + SY, w: r.width, h: r.height, vx: r.x, vy: r.y }; };

  // ---- interactivity classification ------------------------------------------------------------------------
  const classify = (el, tag, role, cs, parentPointer) => {
    if (tag === 'body' || tag === 'html') return null;   // body.onclick mirrors window.onclick
    if (el.hasAttribute('disabled') && el.hasAttribute('hidden')) return null;
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'a' || tag === 'area') {
      if (el.hasAttribute('href')) return { kind: 'link', op: 'open' };
      if (el.hasAttribute('onclick') || role === 'button') return { kind: 'button', op: 'click' };
      return null;
    }
    if (tag === 'button' || tag === 'summary') return { kind: role === 'tab' ? 'tab' : 'button', op: 'click' };
    if (tag === 'input') {
      if (type === 'hidden') return null;
      if (/^(submit|button|reset|image)$/.test(type)) return { kind: 'button', op: 'click' };
      if (type === 'checkbox') return { kind: 'checkbox', op: 'toggle' };
      if (type === 'radio') return { kind: 'radio', op: 'toggle' };
      if (type === 'file') return { kind: 'file', op: 'upload' };
      if (type === 'range') return { kind: 'slider', op: 'fill' };
      return { kind: 'input', op: 'fill', requiresValue: true };
    }
    if (tag === 'textarea') return { kind: 'input', op: 'fill', requiresValue: true };
    if (tag === 'select') return { kind: 'select', op: 'select_option', requiresValue: true };
    if (el.isContentEditable && el.getAttribute('contenteditable') !== 'false' && el.getAttribute('contenteditable') !== null) return { kind: 'input', op: 'fill', requiresValue: true };
    if (role === 'textbox' || role === 'searchbox') return { kind: 'input', op: 'fill', requiresValue: true };
    if (role === 'combobox') {
      if (el.querySelector && el.querySelector('input,textarea')) return null; // the inner input is the control
      return { kind: 'combobox', op: 'click' };
    }
    if (role === 'checkbox' || role === 'switch' || role === 'menuitemcheckbox') return { kind: role === 'switch' ? 'switch' : 'checkbox', op: 'toggle' };
    if (role === 'radio' || role === 'menuitemradio') return { kind: 'radio', op: 'toggle' };
    if (role === 'link') return { kind: 'link', op: 'open' };
    if (role === 'tab') return { kind: 'tab', op: 'click' };
    if (CLICK_ROLES.has(role)) return { kind: role === 'combobox' ? 'combobox' : 'button', op: 'click' };
    const hasFw = FW_CLICK.some((a) => el.hasAttribute(a));
    if (hasFw || (typeof el.onclick === 'function')) return { kind: 'button', op: 'click', fw: true };
    const ti = el.getAttribute('tabindex');
    if (ti !== null && parseInt(ti, 10) >= 0 && tag !== 'body' && tag !== 'html') return { kind: 'button', op: 'click', weak: true };
    if (tag.indexOf('-') > 0 && !STANDARD.has(tag)) {
      const hasChildInteractive = el.querySelector && el.querySelector('button,a[href],input,select,textarea,[role=button],[role=link]');
      if (!hasChildInteractive && cs && cs.cursor === 'pointer') return { kind: 'button', op: 'click', custom: true };
      if (!hasChildInteractive && (hasFw)) return { kind: 'button', op: 'click', custom: true };
    }
    if (cs && cs.cursor === 'pointer' && !parentPointer && tag !== 'html' && tag !== 'body' && tag !== 'label') return { kind: 'button', op: 'click', pointer: true };
    return null;
  };

  const INLINE_DISPLAY = new Set(['inline', 'inline-block', 'inline-flex', 'inline-grid', 'contents', 'inline-table', 'ruby', 'table-cell', 'table-column', 'none']);
  const FLOW_BREAK = ['b'];
  let curRegionDepth = 0;
  const pushFlow = (t) => { if (flow.length < MAX_FLOW) flow.push(t); else stats.truncated = true; };

  const registerNode = (el, tag, role, cls, name, rect, inLayer, extra) => {
    const type = (el.getAttribute('type') || '').toLowerCase();
    const id = idFor(el);
    const node = Object.assign({
      ref: id, dom_index: nodes.length, tag, role: role || tag, name, type,
      id: el.id || '', href: tag === 'a' ? (el.getAttribute('href') || '') : (el.getAttribute('href') || ''),
      disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      checked: !!(el.checked === true || el.getAttribute('aria-checked') === 'true'),
      expanded: el.getAttribute('aria-expanded'),
      haspopup: el.getAttribute('aria-haspopup'),
      in_viewport: rect.vy < VH && rect.vy + rect.h > 0 && rect.vx < VW && rect.vx + rect.w > 0,
      frame_id: opts.frameKey || 'main',
      rect: { x: rect.x, y: rect.y, w: rect.w, h: rect.h },
      tabindex: el.getAttribute('tabindex') || '',
      has_click_handler: !!(cls && (cls.fw || cls.weak || cls.pointer)),
      css_selector: cssPath(el),
      text: '',
      kind: cls ? cls.kind : '', op: cls ? cls.op : '', requires_value: !!(cls && cls.requiresValue),
      in_layer: !!inLayer,
    }, extra || {});
    if (tag.indexOf('-') > 0 && !STANDARD.has(tag)) node.is_custom_element = true;
    if (cls && cls.kind === 'input') {
      const secret = el.type === 'password' || /^(cc-|current-password|new-password|one-time-code)/.test(el.getAttribute('autocomplete') || '');
      const v = secret ? (el.value ? '\u2022\u2022\u2022' : '') : (el.value !== undefined ? el.value : (el.textContent || ''));
      node.value = String(v || '').slice(0, 120);
    }
    if (tag === 'select') {
      node.options = Array.from(el.options || []).slice(0, 25).map((o) => norm(o.text).slice(0, 40));
      const so = el.selectedOptions && el.selectedOptions[0];
      node.value = so ? norm(so.text).slice(0, 60) : '';
    }
    if (cls && cls.kind === 'link') { const h = el.getAttribute('href') || ''; node.href = h.slice(0, 200); }
    nodes.push(node); elOf.push(el);
    if (cls && name) { const k = cls.op + '|' + name; labelCount.set(k, (labelCount.get(k) || 0) + 1); }
    return node;
  };

  // ---- main walk -------------------------------------------------------------------------------------------
  const walk = (n, st) => {
    if (stats.truncated || nodes.length >= MAX_NODES) { stats.truncated = true; return; }
    if (performance.now() - T0 > BUDGET_MS) { stats.truncated = true; return; }
    if (n.nodeType === 3) {
      const d = n.data;
      if (d) pushFlow(['t', d.replace(/\s+/g, ' ')]);   // whitespace-only nodes (&nbsp; between inlines) carry spacing
      return;
    }
    if (n.nodeType === 11) { for (const c of Array.from(n.childNodes)) walk(c, st); return; }
    if (n.nodeType !== 1) return;
    const el = n;
    const tag = el.localName;
    stats.visited++;
    if (SKIP.has(tag)) return;
    if (el.hasAttribute('hidden') && el.getAttribute('hidden') !== 'until-found') return;
    if (tag === 'svg' || tag === 'canvas' || tag === 'video' || tag === 'audio' || tag === 'picture') {
      if (!isVisible(el)) return;
      if (tag === 'svg') { const lbl = el.getAttribute('aria-label'); if (lbl) pushFlow(['t', ' ' + norm(lbl) + ' ']); return; }
      if (tag === 'canvas') { pushFlow(['t', ' [canvas] ']); return; }
      if (tag === 'video' || tag === 'audio') { pushFlow(['t', ' [' + tag + '] ']); return; }
    }
    if (!isVisible(el)) return;
    const role = (el.getAttribute('role') || '').toLowerCase();
    const cs = cstyle(el);
    const display = cs ? cs.display : 'block';

    // off-canvas / sr-only suppression (skip links, visually-hidden text)
    if (cs && (cs.position === 'absolute' || cs.position === 'fixed')) {
      const r0 = el.getBoundingClientRect();
      if (r0.width <= 2 && r0.height <= 2 && cs.overflow !== 'visible') return;
      if (r0.right < -20 || r0.bottom < -20) return;
    }

    if (tag === 'iframe' || tag === 'frame') {
      const r = el.getBoundingClientRect();
      const src = el.getAttribute('src') || '';
      if (r.width < 30 || r.height < 30 || AD_HOST.test(src)) return;
      const fid = idFor(el);
      frames.push({ ref: fid, src: src.slice(0, 200), title: el.getAttribute('title') || el.getAttribute('name') || '', x: r.x + SX, y: r.y + SY, w: r.width, h: r.height, idx: frames.length });
      pushFlow(['b', r.y + SY]);
      pushFlow(['f', frames.length - 1, el.getAttribute('title') || el.getAttribute('name') || '', src.slice(0, 120)]);
      pushFlow(FLOW_BREAK);
      return;
    }

    const isLayerRoot = layerSet.has(el);
    const stIn = isLayerRoot ? Object.assign({}, st, { inLayer: true }) : st;
    const parentPointer = st.pointer;
    let cls = null;
    if (!st.inInteractive || tag === 'button' || tag === 'a' || tag === 'input' || tag === 'select') {
      cls = classify(el, tag, role, cs, parentPointer);
    }
    // containers (tabindex/cursor/custom) that wrap real controls are layout, not controls
    if (cls && (cls.weak || cls.pointer || cls.custom) && el.querySelector && el.querySelector('a[href],button,input,select,textarea,[role=button],[role=link]')) cls = null;
    // framework hosts (<app-header onclick=fn>) that merely delegate clicks for >=2 real controls inside are layout too
    if (cls && cls.fw && !role && !/^(a|button|input|select|textarea|summary|label)$/.test(tag) && el.querySelectorAll &&
        el.querySelectorAll('a[href],button,input,select,textarea,[role=button],[role=link]').length >= 2) cls = null;
    // footnote/citation markers like [7] collide with our [n] refs and are almost never wanted
    if (cls && tag === 'a' && el.parentElement && el.parentElement.localName === 'sup' && /^\[.{1,10}\]$/.test(norm(el.textContent))) return;
    // nested interactive (e.g. icon span inside <a>) shouldn't register separately unless natively interactive
    if (cls && st.inInteractive && (cls.pointer || cls.weak || cls.fw && tag !== 'button' && tag !== 'a')) cls = null;

    // landmark / structural markers
    let landmark = LANDMARK[tag] || ROLE_LANDMARK[role] || null;
    if (tag === 'section' && !(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby'))) landmark = null;
    if (tag === 'article') landmark = null;
    if (isLayerRoot) landmark = 'layer';
    const isBlock = !INLINE_DISPLAY.has(display);
    const r = (isBlock || landmark || cls) ? rectOf(el) : null;

    if ((/^h[1-6]$/.test(tag) || role === 'heading') && !cls) {
      pushFlow(['b', r ? r.y : 0]);
      const lvl = /^h[1-6]$/.test(tag) ? parseInt(tag[1], 10) : parseInt(el.getAttribute('aria-level') || '2', 10);
      pushFlow(['h', lvl]);
      const text = textOf(el, 200, false);
      // headings may contain links: walk children so refs are kept
      const anyInteractive = el.querySelector && el.querySelector('a[href],button,[role=button],[role=link]');
      if (anyInteractive) { for (const c of kids(el)) walk(c, Object.assign({}, stIn, { pointer: false })); }
      else if (text) pushFlow(['t', text]);
      pushFlow(['H']);
      pushFlow(FLOW_BREAK);
      const nm = textOf(el, 160, false);
      if (nm) registerNode(el, tag, role || tag, null, nm, r || rectOf(el), stIn.inLayer, { kind: 'heading', level: lvl });
      return;
    }

    if (landmark) {
      const nm = norm(el.getAttribute('aria-label') || labelledBy(el) || (landmark === 'layer' ? '' : ''));
      let lname = nm;
      if (landmark === 'layer' && !lname) {
        const h = el.querySelector && el.querySelector('h1,h2,h3,[role=heading],[aria-label]');
        lname = h ? norm(h.getAttribute('aria-label') || textOf(h, 80, false)) : '';
      }
      pushFlow(['b', r ? r.y : 0]);
      pushFlow(['r', landmark, lname]);
      if (landmark !== 'article') registerNode(el, tag, role || tag, null, lname || tag, r, stIn.inLayer, { kind: 'landmark', landmark });
    }

    if (cls) {
      const rr = r || rectOf(el);
      const small = rr.w < 2 || rr.h < 2;
      let hiddenInput = null;
      if (small && (cls.kind === 'checkbox' || cls.kind === 'radio' || cls.kind === 'file')) {
        const lab = el.labels && el.labels[0];
        if (lab && isVisible(lab)) hiddenInput = lab;
      }
      if (!small || hiddenInput) {
        const name = nameFor(el, tag, role) || (hiddenInput ? textOf(hiddenInput, 100, false) : '');
        const node = registerNode(el, tag, role || tag, cls, name, hiddenInput ? rectOf(hiddenInput) : rr, stIn.inLayer, {
          click_proxy: hiddenInput ? idFor(hiddenInput) : 0,
        });
        if (cls.kind === 'checkbox' || cls.kind === 'radio' || cls.kind === 'switch') node.checked = !!(el.checked === true || el.getAttribute('aria-checked') === 'true');
        pushFlow(['e', node.ref, rr.y]);
        // Interactive elements that wrap rich content: swallow text, but keep nested natively-interactive controls.
        const nested = el.querySelectorAll ? el.querySelectorAll('a[href],button,input,select,textarea') : [];
        if (nested.length && tag !== 'select' && tag !== 'button' && tag !== 'a') {
          for (const c of kids(el)) walk(c, Object.assign({}, stIn, { inInteractive: false, pointer: true }));
        } else if (nested.length && (tag === 'a' || tag === 'button')) {
          for (const c of kids(el)) { if (c.nodeType === 1 && c.querySelector && (c.matches('a[href],button,input,select,textarea') || c.querySelector('a[href],button,input,select,textarea'))) walk(c, Object.assign({}, stIn, { inInteractive: true, pointer: true })); }
        }
        if (landmark) { pushFlow(['R']); pushFlow(FLOW_BREAK); }
        return;
      }
    }

    // plain container / inline element
    if (isBlock) pushFlow(['b', r ? r.y : 0]);
    if (tag === 'li') pushFlow(['li']);
    if (tag === 'td' || tag === 'th') pushFlow(['c']);
    if (tag === 'br') { pushFlow(FLOW_BREAK); return; }
    if (tag === 'hr') { pushFlow(FLOW_BREAK); return; }
    if (tag === 'img') {
      const alt = norm(el.getAttribute('alt') || '');
      if (alt.length > 2 && !st.inInteractive) pushFlow(['t', ' [img: ' + alt.slice(0, 80) + '] ']);
      return;
    }
    if (tag === 'input' || tag === 'select' || tag === 'textarea') { return; }
    const nextSt = Object.assign({}, stIn, { pointer: cs ? cs.cursor === 'pointer' : false });
    if (cls === null && cs && cs.cursor === 'pointer') nextSt.pointer = true;
    for (const c of kids(el)) walk(c, nextSt);
    if (isBlock) pushFlow(FLOW_BREAK);
    if (landmark) { pushFlow(['R']); pushFlow(FLOW_BREAK); }
  };

  // ---- overlay / blocking layer detection (before the walk, so tokens can be tagged) -----------------------
  const deepHit = (x, y) => {
    let el = document.elementFromPoint(x, y);
    let guard = 0;
    while (el && el.shadowRoot && guard++ < 6) {
      const inner = el.shadowRoot.elementFromPoint(x, y);
      if (!inner || inner === el) break;
      el = inner;
    }
    return el;
  };
  const upToFixed = (el) => {
    let best = null; let cur = el; let guard = 0;
    while (cur && guard++ < 60) {
      if (cur === document.body || cur === document.documentElement) break;
      const s = cstyle(cur);
      if (s && (s.position === 'fixed' || (s.position === 'sticky' && false))) best = cur;
      if (cur.localName === 'dialog' && cur.open) best = cur;
      const p = cur.parentNode;
      cur = p && p.nodeType === 11 ? p.host : p; // climb out of shadow roots
    }
    return best;
  };
  const detectLayers = () => {
    const pts = [[0.5, 0.5], [0.25, 0.5], [0.75, 0.5], [0.5, 0.3], [0.5, 0.7]];
    const hits = new Map();
    for (const [fx, fy] of pts) {
      const h = deepHit(VW * fx, VH * fy);
      if (!h) continue;
      const f = upToFixed(h);
      if (f) hits.set(f, (hits.get(f) || 0) + 1);
    }
    const out = [];
    for (const [f, c] of hits) {
      const r = f.getBoundingClientRect();
      const area = (Math.max(0, Math.min(r.right, VW) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, VH) - Math.max(r.top, 0))) / (VW * VH);
      if (c >= 2 && area >= 0.15) out.push(f);
    }
    return out;
  };
  try { layerEls = detectLayers(); layerSet = new Set(layerEls); } catch (e) { layerEls = []; }

  const body = document.body || document.documentElement;
  walk(body, { inLayer: false, inInteractive: false, pointer: false });

  // ---- coverage (occlusion) for in-viewport interactive nodes --------------------------------------------
  let covered = 0, checked = 0;
  for (let i = 0; i < nodes.length && checked < 400; i++) {
    const nd = nodes[i];
    if (!nd.op || !nd.in_viewport || nd.in_layer) continue;
    const el = elOf[i];
    const rc = el.getBoundingClientRect();
    const cx = Math.min(Math.max(rc.left + rc.width / 2, 1), VW - 1), cy = Math.min(Math.max(rc.top + rc.height / 2, 1), VH - 1);
    checked++;
    const h = deepHit(cx, cy);
    if (!h) continue;
    if (h === el || el.contains(h) || (h.contains && h.contains(el)) || (rootOf(h) !== document && (h.getRootNode().host === el || el.contains(h.getRootNode().host)))) continue;
    if (nd.click_proxy) continue;
    nd.covered = true; covered++;
  }

  // ---- duplicate-label disambiguation (context) ----------------------------------------------------------
  const ctxFor = (el, label) => {
    let c = el.parentElement; let depth = 0;
    while (c && depth++ < 7) {
      const t = c.localName;
      const rl = (c.getAttribute('role') || '');
      const sib = c.parentElement ? Array.from(c.parentElement.children).filter((x) => x.localName === t).length : 0;
      if (t === 'li' || t === 'tr' || t === 'article' || rl === 'listitem' || rl === 'row' || rl === 'article' || (sib >= 3 && t !== 'a' && t !== 'span' && t !== 'td')) {
        const h = c.querySelector('h1,h2,h3,h4,h5,h6,[role=heading],strong,b');
        let txt = h ? textOf(h, 60, false) : '';
        if (!txt || txt === label) {
          txt = textOf(c, 90, false);
          if (label) txt = txt.split(label).join(' ');
          txt = norm(txt);
          if (t === 'tr' && !txt) { const prev = c.previousElementSibling; if (prev) txt = textOf(prev, 60, false); }
        }
        return txt.slice(0, 50);
      }
      c = c.parentElement || (c.getRootNode && c.getRootNode().host) || null;
    }
    return '';
  };
  for (let i = 0; i < nodes.length; i++) {
    const nd = nodes[i];
    if (!nd.op || !nd.name) continue;
    if ((labelCount.get(nd.op + '|' + nd.name) || 0) > 1) { const c = ctxFor(elOf[i], nd.name); if (c) nd.ctx = c; }
  }

  // ---- layer descriptor -----------------------------------------------------------------------------------
  let layer = null;
  if (layerEls.length) {
    const L = layerEls[0];
    const members = nodes.filter((x) => x.in_layer && x.op).length;
    const txt = textOf(L, 120, false);
    layer = { name: norm(L.getAttribute('aria-label') || '') || (txt.slice(0, 80)), tag: L.localName, members, covered };
  }
  // landmarks flagged as layer inherit
  const doc = document.documentElement;
  return JSON.stringify({
    gen: REG.gen, title: document.title || '', url: location.href, ready: document.readyState,
    scroll: { x: SX, y: SY, h: Math.max(doc.scrollHeight, (document.body || doc).scrollHeight), vh: VH, vw: VW },
    nodes, flow, layer, frames, stats: { visited: stats.visited, truncated: stats.truncated, ms: Math.round(performance.now() - T0), covered },
  });
}
