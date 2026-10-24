/* ==========================================================================
   Scroll motion engine.

   Every [data-fx] element has two progress numbers. Their TARGETS are a pure function of the scroll position:
     in  (0..1)  the element's top edge travels from 94% to 64% of the viewport height  -> entering
     out (0..1)  the element's bottom edge travels from 16% of the viewport height to 0 -> leaving
   What is SHOWN follows the target at a limited speed: a complete change takes at least MIN_MS, however far or fast the
   page scrolled. A slow scroll is followed exactly; a fling or an anchor jump makes elements glide instead of popping.
   The shown numbers are written as --fx-in / --fx-out and data-fx-state (pre | active | done | post); css/fx.css turns
   them into opacity / translate / scale / rotate / clip-path. Nothing is triggered once, so nothing can get stuck: the
   shown value always keeps moving towards the target of the current position. An element's very first picture and a
   focused element are placed at once.

   Cost control: positions are measured once per layout change (offsetTop chain, which ignores our own transforms, so
   there is no feedback loop); each frame is arithmetic on cached numbers, values are only written when they change,
   and the frame loop stops once nothing is catching up and 140 ms after scrolling stops.

   Public API: FX.init() FX.refresh() FX.setMode('full'|'soft'|'off') FX.getMode() FX.debug(bool) FX.stats()
   ========================================================================== */

const root = document.documentElement;
const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
const ease = (t) => 1 - Math.pow(1 - t, 3);
const round3 = (v) => Math.round(v * 1000) / 1000;

const ENTER_START = 0.94;   // top edge crosses 94% of the viewport -> starts
const ENTER_SPAN = 0.30;    // ... and is complete 30% of the viewport later
const EXIT_SPAN = 0.16;     // bottom edge inside the top 16% -> leaving
const STAGGER = 0.08;       // delay between neighbours in one row
const TALL = 0.9;           // taller than 90% of the viewport: fade in only, never fade out
const SETTLE_MS = 140;      // keep the frame loop alive this long after the last scroll event
const MIN_MS = 420;         // the shortest time a complete change (0 -> 1 or 1 -> 0) may take, however far or fast the page scrolled
const MAX_DT = 50;          // longest frame gap that counts as elapsed time (hidden tab, long task)
const SPREAD = 0.6;         // share of the heading progress spent staggering characters

const S = {
  items: [], map: new WeakMap(), vh: 0, raf: 0, last: 0, mode: 'full', ready: false, dbg: false,
  frameMs: 0, frames: 0, measureQ: 0, rotFlip: 1, prev: 0, moving: false,
};

/** One step of the shown value towards its target: never faster than 1 / MIN_MS per millisecond. */
const follow = (shown, goal, dt) => {
  const step = clamp(dt, 0, MAX_DT) / MIN_MS;
  return goal > shown ? Math.min(goal, shown + step) : Math.max(goal, shown - step);
};

/* ---------------------------------------------------------------- mode */
function readMode() {
  let m = 'full';
  try { m = new URLSearchParams(location.search).get('motion') || localStorage.getItem('bb:motion') || 'full'; } catch (_) { /* storage is optional */ }
  if (!['full', 'soft', 'off'].includes(m)) m = 'full';
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) m = 'off';
  return m;
}

/* ---------------------------------------------------------------- text: words, line breaks, per-character headings
   Chinese can be broken anywhere by the browser, which splits words like 差|点. The browser's own dictionary segmenter
   (Intl.Segmenter) finds the words; they are kept together (nowrap) and lines break only between words. Closing
   punctuation sticks to the word before it, opening punctuation to the word after it, so no line starts with ，。！ . */
const graphemeSeg = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter('zh', { granularity: 'grapheme' }) : null;
const wordSeg = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter('zh', { granularity: 'word' }) : null;
const graphemes = (s) => (graphemeSeg ? [...graphemeSeg.segment(s)].map((x) => x.segment) : Array.from(s));
const CLOSING = /^[，。、！？；：）》」』”’…—,.!?;:)\]}]+$/;   // must not start a line
const OPENING = /^[（《「『“‘([{]+$/;                          // must not end a line
const WRAP_MAX = 12;                                          // longer unbroken runs (URLs, long words) are left alone

function words(text) {
  let raw;
  if (wordSeg) raw = [...wordSeg.segment(text)].map((x) => x.segment);
  else raw = text.split(/(\s+)/).filter(Boolean);              // no segmenter: Latin words and spaces only, Chinese breaks as before
  const out = [];
  raw.forEach((g) => {
    if (/^\s+$/.test(g)) { out.push({ t: ' ', space: true }); return; }
    const prev = out[out.length - 1];
    if (prev && !prev.space && CLOSING.test(g)) { prev.t += g; return; }
    out.push({ t: g, space: false });
  });
  for (let i = out.length - 2; i >= 0; i -= 1) {
    if (!out[i].space && OPENING.test(out[i].t) && !out[i + 1].space) { out[i + 1].t = out[i].t + out[i + 1].t; out.splice(i, 1); }
  }
  return out;
}

/* A flex or grid container turns every child span into its own item, which pulls the words of a title apart.
   Text that sits directly inside one is first put into a single inline span, so the words keep flowing as one line. */
function calm(node) {
  if (node.nodeType !== 1 || node.matches('.ph-run, .ph, .fx-w, .fx-c') || !/flex|grid/.test(getComputedStyle(node).display)) return;
  [...node.childNodes].forEach((c) => {
    if (c.nodeType !== 3 || !c.nodeValue.trim()) return;
    const run = document.createElement('span');
    run.className = 'ph-run';
    c.replaceWith(run);
    run.append(c);
  });
}

/* Keep words together in a plain (not animated) text: titles, list entries. */
export function phrasify(el, force = false) {
  if (el.dataset.phrased || (el.dataset.fx === 'text' && !force)) return;
  el.dataset.phrased = '1';
  const walk = (node) => {
    calm(node);
    [...node.childNodes].forEach((child) => {
      if (child.nodeType === 3) {
        if (!child.nodeValue.trim()) return;
        const frag = document.createDocumentFragment();
        const toks = words(child.nodeValue);
        toks.forEach((tk, i) => {
          if (tk.space) { frag.append(document.createTextNode(' ')); return; }
          if (tk.t.length > WRAP_MAX) frag.append(document.createTextNode(tk.t));
          else { const w = document.createElement('span'); w.className = 'ph'; w.textContent = tk.t; frag.append(w); }
          if (toks[i + 1] && !toks[i + 1].space) frag.append(document.createElement('wbr'));
        });
        child.replaceWith(frag);
      } else if (child.nodeType === 1 && child.tagName !== 'BR' && !child.classList.contains('ph')) walk(child);
    });
  };
  walk(el);
}

function splitText(el) {
  if (el.dataset.fxSplit) return true;
  // a heading that was only grouped into words while motion was off starts over from its plain text
  if (el.dataset.phrased) { el.querySelectorAll('.ph').forEach((w) => w.replaceWith(...w.childNodes)); el.querySelectorAll('wbr').forEach((w) => w.remove()); el.querySelectorAll('.ph-run').forEach((w) => w.replaceWith(...w.childNodes)); el.normalize(); delete el.dataset.phrased; }
  const label = el.textContent.replace(/\s+/g, ' ').trim();
  const limit = window.innerWidth <= 760 ? 24 : 32;
  if (!label || label.length > limit) return false;
  if (!el.hasAttribute('aria-label')) el.setAttribute('aria-label', label);
  const chars = [];
  const walk = (node) => {
    calm(node);
    [...node.childNodes].forEach((child) => {
      if (child.nodeType === 3) {
        const frag = document.createDocumentFragment();
        const toks = words(child.nodeValue);
        toks.forEach((tk, i) => {
          if (tk.space) { frag.append(document.createTextNode(' ')); return; }
          const w = document.createElement('span');
          w.className = 'fx-w'; w.setAttribute('aria-hidden', 'true');
          graphemes(tk.t).forEach((g) => {
            const c = document.createElement('span');
            c.className = 'fx-c'; c.textContent = g;
            chars.push(c); w.append(c);
          });
          frag.append(w);
          if (toks[i + 1] && !toks[i + 1].space) frag.append(document.createElement('wbr'));
        });
        child.replaceWith(frag);
      } else if (child.nodeType === 1 && child.tagName !== 'BR') {
        if (child.classList.contains('hl')) child.classList.add('has-split');
        walk(child);
      }
    });
  };
  walk(el);
  const n = chars.length;
  chars.forEach((c, i) => c.style.setProperty('--co', (n > 1 ? (i / (n - 1)) * SPREAD : 0).toFixed(3)));
  el.style.setProperty('--sp', String(SPREAD));
  el.dataset.fxSplit = '1';
  return true;
}

/* ---------------------------------------------------------------- registration and measuring */
function docTop(el) {
  let y = 0;
  for (let e = el; e; e = e.offsetParent) y += e.offsetTop;
  return y;
}

function register(el) {
  if (S.map.has(el)) return;
  let type = el.dataset.fx || 'fade';
  if (type === 'text' && !splitText(el)) { type = 'fade'; el.dataset.fx = 'fade'; }
  if (getComputedStyle(el).position === 'sticky') console.warn('[fx] data-fx on a position:sticky element is not supported (it measures itself while moving); put it on a child:', el);
  const it = { el, type, top: 0, h: 0, tall: false, hidden: false, in: -1, out: -1, lin: -1, lout: -1, tin: 0, tout: 0, d: 9, state: '', stagI: 0, stagN: 1, forced: false, intro: null, sticky: null, local: 0 };
  if (!['drift', 'spine'].includes(type)) it.sticky = stickyAncestor(el);
  if (type === 'pop' && !el.style.getPropertyValue('--fx-rot')) { el.style.setProperty('--fx-rot', String(3 * S.rotFlip)); S.rotFlip *= -1; }
  S.map.set(el, it);
  S.items.push(it);
  measureItem(it);
}

/* An element inside a position:sticky box moves with the sticky box while it is stuck, so its document position is not a
   constant. For those the engine measures the (never transformed) sticky box each frame and adds the element's fixed offset
   inside it. */
function stickyAncestor(el) {
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    if (getComputedStyle(p).position === 'sticky') return p;
  }
  return null;
}
function offsetWithin(el, box) {
  let y = 0;
  for (let e = el; e && e !== box; e = e.offsetParent) y += e.offsetTop;
  return y;
}

function measureItem(it) {
  const el = it.el;
  it.hidden = el.offsetParent === null && getComputedStyle(el).position !== 'fixed';
  if (it.hidden) return;
  it.top = docTop(el);
  it.h = el.offsetHeight;
  it.tall = it.h > S.vh * TALL;
  if (it.sticky) {
    // the sticky box must be in this element's offsetParent chain; if it is not, fall back to the plain document position
    let inChain = false;
    for (let e = el.offsetParent; e; e = e.offsetParent) if (e === it.sticky) { inChain = true; break; }
    if (inChain) it.local = offsetWithin(el, it.sticky); else it.sticky = null;
  }
}

function assignStagger() {
  // children of [data-fx-stagger] containers are staggered by their column inside each visual row
  document.querySelectorAll('[data-fx-stagger]').forEach((box) => {
    const kids = [...box.querySelectorAll(':scope > [data-fx], :scope > * > [data-fx]')].map((el) => S.map.get(el)).filter((it) => it && !it.hidden);
    const rows = [];
    kids.forEach((it) => {
      const row = rows.find((r) => Math.abs(r.top - it.top) < 12);
      if (row) row.items.push(it); else rows.push({ top: it.top, items: [it] });
    });
    rows.forEach((r) => {
      r.items.sort((a, b) => a.el.offsetLeft - b.el.offsetLeft);
      const n = Math.min(r.items.length, 6);
      r.items.forEach((it, i) => { it.stagI = Math.min(i, 5); it.stagN = n; });
    });
    if (box.hasAttribute('data-fx-alt')) {
      kids.forEach((it, i) => it.el.style.setProperty('--fx-dx', i % 2 ? '1' : '-1'));
    }
  });
}

function measureAll() {
  S.vh = root.clientHeight || window.innerHeight;
  S.items.forEach(measureItem);
  assignStagger();
  schedule();
}

function queueMeasure() {
  if (S.measureQ) return;
  S.measureQ = requestAnimationFrame(() => { S.measureQ = 0; measureAll(); });
}

/* ---------------------------------------------------------------- the frame */
function setState(it, state) {
  if (it.state !== state) { it.state = state; it.el.setAttribute('data-fx-state', state); }
}

const stuck = new Map();   // sticky box -> its current top, read once per frame
function stickyTop(it) {
  let t = stuck.get(it.sticky);
  if (t === undefined) { t = it.sticky.getBoundingClientRect().top; stuck.set(it.sticky, t); }
  return t + it.local;
}

function update(it, sy, vh, now, dt) {
  if (it.hidden) return;
  if (it.type === 'drift') {
    const d = round3(clamp(((it.top - sy + it.h / 2) - vh / 2) / vh, -1, 1));
    if (d !== it.d) { it.d = d; it.el.style.setProperty('--fx-d', d); }
    setState(it, 'active');
    return;
  }
  if (it.type === 'spine') {
    const goal = round3(clamp((sy + vh * 0.7 - it.top) / Math.max(it.h, 1)));
    it.lin = it.lin < 0 ? goal : follow(it.lin, goal, dt);
    if (it.lin !== goal) S.moving = true;
    const p = round3(it.lin);
    if (p !== it.in) { it.in = p; it.el.style.setProperty('--fx-in', p); }
    setState(it, 'active');
    return;
  }
  let tin; let tout;
  if (it.forced) { tin = 1; tout = 0; }
  else {
    const top = it.sticky ? stickyTop(it) : it.top - sy;
    const bottom = top + it.h;
    tin = clamp((vh * ENTER_START - top) / (vh * ENTER_SPAN));
    if (it.stagN > 1) tin = clamp((tin - STAGGER * it.stagI) / (1 - STAGGER * (it.stagN - 1)));
    tout = it.tall ? 0 : clamp((vh * EXIT_SPAN - bottom) / (vh * EXIT_SPAN));
    if (it.intro) {
      const p = clamp((now - it.intro.start) / it.intro.dur);
      tin = Math.min(tin, p);
      if (p >= 1) it.intro = null;
    }
  }
  it.tin = tin; it.tout = tout;
  if (it.forced || it.lin < 0) { it.lin = tin; it.lout = tout; }
  else { it.lin = follow(it.lin, tin, dt); it.lout = follow(it.lout, tout, dt); }
  if (it.lin !== tin || it.lout !== tout) S.moving = true;
  const a = round3(ease(it.lin));
  const b = round3(ease(it.lout));
  if (a !== it.in) { it.in = a; it.el.style.setProperty('--fx-in', a); }
  if (b !== it.out) { it.out = b; it.el.style.setProperty('--fx-out', b); }
  setState(it, b >= 1 ? 'post' : a >= 1 && b <= 0 ? 'done' : a <= 0 && b <= 0 ? 'pre' : 'active');
  if (S.dbg && it.tag) { const t = `${it.type} in ${a.toFixed(2)} out ${b.toFixed(2)}`; if (it.tag.textContent !== t) it.tag.textContent = t; }
}

function frame(now) {
  S.raf = 0;
  const t0 = performance.now();
  const sy = Math.max(0, window.scrollY || window.pageYOffset || 0);
  const vh = S.vh;
  const dt = S.prev > 0 ? clamp(now - S.prev, 0, MAX_DT) : 1000 / 60;   // the first frame after an idle spell counts as one ordinary frame
  S.prev = now;
  S.moving = false;
  stuck.clear();
  // every layout read first, then the writes: a read after a write would make the browser recalculate styles in the middle of the frame
  for (let i = 0; i < S.items.length; i += 1) { const it = S.items[i]; if (it.sticky && !it.hidden) stickyTop(it); }
  for (let i = 0; i < S.items.length; i += 1) update(S.items[i], sy, vh, now, dt);
  S.frameMs = performance.now() - t0;
  S.frames += 1;
  const introRunning = S.items.some((it) => it.intro);
  if (introRunning || S.moving || performance.now() - S.last < SETTLE_MS) schedule();
  else S.prev = 0;
}

function schedule() {
  if (!S.ready || S.raf || S.mode === 'off') return;
  S.raf = requestAnimationFrame(frame);
}

function onScroll() { S.last = performance.now(); schedule(); }

/* ---------------------------------------------------------------- focus safety: a focused element is never transparent */
function nearest(el) {
  for (let e = el; e && e !== document.body; e = e.parentElement) { const it = S.map.get(e); if (it) return it; }
  return null;
}
function onFocusIn(e) { const it = nearest(e.target); if (it) { it.forced = true; S.last = performance.now(); schedule(); } }
function onFocusOut(e) { const it = nearest(e.target); if (it) { it.forced = false; S.last = performance.now(); schedule(); } }

/* ---------------------------------------------------------------- lifecycle */
function scan() {
  document.querySelectorAll('[data-fx]').forEach(register);
  S.items = S.items.filter((it) => { if (it.el.isConnected) return true; S.map.delete(it.el); return false; });
}

function startIntro() {
  // heroes get one time-driven entrance on load; after that they follow the scroll like everything else
  if ((window.scrollY || 0) > 8) return;
  const now = performance.now();
  S.items.forEach((it) => {
    const raw = it.el.getAttribute('data-fx-intro');
    if (raw === null || it.hidden) return;
    it.intro = { start: now + 140 + (parseInt(raw, 10) || 0) * 90, dur: 700 };
  });
}

function clearInline() {
  S.items.forEach((it) => {
    it.el.style.removeProperty('--fx-in'); it.el.style.removeProperty('--fx-out'); it.el.style.removeProperty('--fx-d');
    it.el.removeAttribute('data-fx-state'); it.in = it.out = it.lin = it.lout = -1; it.d = 9; it.state = '';
  });
}

const FX = {
  init() {
    S.mode = readMode();
    root.dataset.fxMode = S.mode;
    if (S.mode === 'off') {
      root.classList.add('fx-off'); root.classList.remove('fx-pending');
      document.querySelectorAll('[data-fx="text"]').forEach((el) => phrasify(el, true));   // still break between words
      return;
    }
    root.classList.remove('fx-off');
    S.vh = root.clientHeight || window.innerHeight;
    scan();
    measureAll();
    assignStagger();
    startIntro();
    S.ready = true;
    root.classList.add('fx-ready');
    frame(performance.now());          // first picture is computed before the pending guard is lifted
    root.classList.remove('fx-pending');
    if (!S.started) {
      S.started = true;
      window.addEventListener('scroll', onScroll, { passive: true });
      window.addEventListener('resize', queueMeasure, { passive: true });
      window.addEventListener('orientationchange', queueMeasure);
      window.addEventListener('load', queueMeasure);
      document.addEventListener('focusin', onFocusIn);
      document.addEventListener('focusout', onFocusOut);
      document.addEventListener('load', queueMeasure, true);   // images finishing change the layout above later items
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(queueMeasure);
      if ('ResizeObserver' in window) { const ro = new ResizeObserver(queueMeasure); ro.observe(document.body); }
    }
  },
  refresh() { if (!S.ready) return; scan(); measureAll(); S.last = performance.now(); schedule(); },
  setMode(m) {
    if (!['full', 'soft', 'off'].includes(m)) return;
    try { localStorage.setItem('bb:motion', m); } catch (_) { /* storage is optional */ }
    const wasOff = S.mode === 'off';
    S.mode = readMode();
    root.dataset.fxMode = S.mode;
    if (S.mode === 'off') { root.classList.add('fx-off'); clearInline(); return; }
    root.classList.remove('fx-off');
    if (!S.ready) { this.init(); return; }
    if (wasOff) { clearInline(); measureAll(); }
    S.last = performance.now(); schedule();
  },
  getMode() { return S.mode; },
  debug(on) {
    S.dbg = !!on;
    S.items.forEach((it) => {
      if (!it.el.hasAttribute('data-fx-debug')) return;
      if (on && !it.tag) { it.tag = document.createElement('span'); it.tag.className = 'fx-debug-tag'; it.el.append(it.tag); }
      if (!on && it.tag) { it.tag.remove(); it.tag = null; }
    });
    S.last = performance.now(); schedule();
  },
  stats() {
    const active = S.items.filter((it) => it.state === 'active').length;
    return { items: S.items.length, active, frameMs: Math.round(S.frameMs * 100) / 100, frames: S.frames, vh: S.vh, mode: S.mode, moving: S.moving };
  },
  /* for tests: the current numbers of an element */
  read(el) { const it = S.map.get(el); return it ? { type: it.type, in: it.in, out: it.out, lin: it.lin, lout: it.lout, tin: it.tin, tout: it.tout, state: it.state, top: it.top, h: it.h, tall: it.tall, hidden: it.hidden, forced: it.forced, sticky: !!it.sticky, local: it.local, intro: !!it.intro, stagI: it.stagI, stagN: it.stagN } : null; },
};

window.FX = FX;
export default FX;
