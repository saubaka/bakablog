/* Page behaviour for the prototype: navigation indicators, table of contents, search, lightbox, filters, design panel.
   The real site rebuilds these as Vue components; the rules (one movement per target, no ring on <main>, links stay links) carry over. */
import FX, { phrasify } from './fx.js';
import { POSTS, MOMENTS, PAGES } from './data.js';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* optional */ } },
  sget(k) { try { return sessionStorage.getItem(k); } catch (_) { return null; } },
  sset(k, v) { try { sessionStorage.setItem(k, v); } catch (_) { /* optional */ } },
  sdel(k) { try { sessionStorage.removeItem(k); } catch (_) { /* optional */ } },
};
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ------------------------------------------------------------------ motion hints for article content */
function autoFx() {
  $$('.prose > *').forEach((el) => {
    if (el.hasAttribute('data-fx')) return;
    let type = 'fade';
    if (el.matches('h2')) type = 'text';
    else if (el.matches('.callout, .code, .table-wrap, blockquote, .figure, .polaroid, .gallery')) type = 'rise';
    else if (el.matches('hr')) type = 'draw-x';
    el.setAttribute('data-fx', type);
  });
}

/* ------------------------------------------------------------------ sliding indicator: one movement per target.
   Across page loads the indicator starts where the previous page left it and glides to the new item. */
function indicator(box, indSel, key) {
  if (!box) return;
  const ind = $(indSel, box);
  const cur = $('[aria-current="page"]', box);
  if (!ind) return;
  const set = (p) => { ind.style.setProperty('--x', `${p.x}px`); ind.style.setProperty('--w', `${p.w}px`); };
  const measure = (el) => ({ x: el.offsetLeft, w: el.offsetWidth });
  if (cur) {
    const to = measure(cur);
    let from = to;
    const saved = store.sget(key);
    store.sdel(key);
    try { const p = JSON.parse(saved || 'null'); if (p && Date.now() - p.at < 6000) from = p; } catch (_) { /* ignore */ }
    set(from);
    if (from !== to) ind.classList.add('is-shown');   // already visible at the old spot, then one glide to the new one
    requestAnimationFrame(() => requestAnimationFrame(() => { ind.classList.add('is-ready', 'is-shown'); set(to); }));
    box.addEventListener('click', (e) => {
      const a = e.target.closest('a');
      if (!a || a.hasAttribute('aria-current') || a.target === '_blank') return;
      const m = measure(cur);
      store.sset(key, JSON.stringify({ x: m.x, w: m.w, at: Date.now() }));
    });
    window.addEventListener('resize', () => { ind.classList.remove('is-ready'); set(measure(cur)); ind.classList.add('is-shown'); requestAnimationFrame(() => ind.classList.add('is-ready')); }, { passive: true });
  }
}

/* ------------------------------------------------------------------ back to top with a progress ring */
function backTop() {
  const wrap = $('.backtop');
  if (!wrap) return;
  const ring = $('circle.fg', wrap);
  const r = 27; const c = 2 * Math.PI * r;
  ring.style.strokeDasharray = `${c}`;
  const tick = () => {
    const h = document.documentElement.scrollHeight - innerHeight;
    const p = h > 0 ? Math.min(1, scrollY / h) : 0;
    ring.style.strokeDashoffset = `${c * (1 - p)}`;
    wrap.classList.toggle('is-on', scrollY > 600);
  };
  addEventListener('scroll', () => requestAnimationFrame(tick), { passive: true });
  tick();
  $('button', wrap).addEventListener('click', () => scrollTo({ top: 0, behavior: reduced() ? 'auto' : 'smooth' }));
}

/* ------------------------------------------------------------------ reading bar (article page only) */
function readBar() {
  const bar = $('.readbar');
  const art = $('.prose');
  if (!bar || !art) return;
  const tick = () => {
    const top = art.getBoundingClientRect().top + scrollY;
    const p = Math.max(0, Math.min(1, (scrollY - top + innerHeight * 0.3) / (art.offsetHeight)));
    bar.style.setProperty('--p', p.toFixed(3));
    bar.classList.toggle('is-on', p > 0.005 && p < 0.998);
  };
  addEventListener('scroll', () => requestAnimationFrame(tick), { passive: true });
  tick();
}

/* ------------------------------------------------------------------ table of contents */
function toc() {
  const box = $('[data-toc]');
  const heads = $$('.prose h2, .prose h3');
  if (!box || !heads.length) return;
  heads.forEach((h, i) => { if (!h.id) h.id = `s${i + 1}`; });
  const build = (ol) => {
    heads.forEach((h) => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = `#${h.id}`;
      a.textContent = h.getAttribute('aria-label') || h.textContent.trim();
      if (h.tagName === 'H3') a.className = 'lv3';
      li.append(a); ol.append(li);
    });
  };
  const ol = $('ol', box);
  build(ol);
  const ind = document.createElement('i'); ind.className = 'toc__ind'; ol.prepend(ind);
  const links = $$('a', ol);
  let active = -1;
  const setActive = (i) => {
    if (i === active) return;
    active = i;
    links.forEach((a, k) => a.classList.toggle('is-active', k === i));
    const a = links[i];
    if (a) { ind.style.setProperty('--y', `${a.offsetTop}px`); ind.style.setProperty('--h', `${a.offsetHeight}px`); ind.classList.add('is-ready'); }
  };
  const tick = () => {
    let idx = 0;
    heads.forEach((h, i) => { if (h.getBoundingClientRect().top <= 140) idx = i; });
    setActive(idx);
  };
  addEventListener('scroll', () => requestAnimationFrame(tick), { passive: true });
  tick();
  // phone: the same list in a bottom sheet
  const sheet = $('#toc-sheet');
  if (sheet) {
    build($('ol', sheet));
    $('.toc-fab').addEventListener('click', () => openSheet(sheet));
    $$('a', sheet).forEach((a) => a.addEventListener('click', () => closeSheets()));
  }
}

/* ------------------------------------------------------------------ bottom sheets */
const scrim = document.createElement('div');
scrim.className = 'scrim';
document.body.append(scrim);
function openSheet(el) { el.classList.add('is-open'); scrim.classList.add('is-open'); }
function closeSheets() { $$('.sheet.is-open').forEach((s) => s.classList.remove('is-open')); scrim.classList.remove('is-open'); }
scrim.addEventListener('click', closeSheets);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheets(); });
$$('[data-open-sheet]').forEach((b) => b.addEventListener('click', () => openSheet($(b.dataset.openSheet))));

/* ------------------------------------------------------------------ code copy */
function copyButtons() {
  $$('.code__copy').forEach((b) => b.addEventListener('click', async () => {
    const pre = $('pre', b.closest('.code'));
    try { await navigator.clipboard.writeText(pre.innerText); } catch (_) { /* clipboard can be blocked on http */ }
    const label = $('span', b); const old = label.textContent;
    label.textContent = '已复制'; b.querySelector('use').setAttribute('href', '#i-check');
    setTimeout(() => { label.textContent = old; b.querySelector('use').setAttribute('href', '#i-copy'); }, 1600);
  }));
}

/* ------------------------------------------------------------------ lightbox */
function lightbox() {
  const items = $$('[data-lightbox]');
  if (!items.length) return;
  const box = document.createElement('div');
  box.className = 'lightbox';
  box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-label', '图片查看');
  box.innerHTML = '<div class="lightbox__bar"><span data-count></span><button class="icon-btn" aria-label="关闭"><svg class="i"><use href="#i-close"/></svg></button></div>'
    + '<button class="icon-btn lightbox__nav lightbox__nav--prev" aria-label="上一张"><svg class="i"><use href="#i-arrow-l"/></svg></button>'
    + '<img class="lightbox__img" alt=""><button class="icon-btn lightbox__nav lightbox__nav--next" aria-label="下一张"><svg class="i"><use href="#i-arrow-r"/></svg></button><p class="lightbox__cap"></p>';
  document.body.append(box);
  const img = $('.lightbox__img', box); const cap = $('.lightbox__cap', box); const count = $('[data-count]', box);
  let group = []; let i = 0; let opener = null;
  const show = (k) => {
    i = (k + group.length) % group.length;
    const g = group[i]; const im = $('img', g);
    img.src = im.getAttribute('src'); img.alt = im.alt;
    cap.textContent = g.dataset.cap || im.alt; count.textContent = `${i + 1} / ${group.length}`;
  };
  const open = (el) => {
    opener = el; group = items.filter((x) => x.dataset.group === el.dataset.group); show(group.indexOf(el));
    box.classList.add('is-open'); $('.icon-btn', box).focus();
    $('.lightbox__nav--prev', box).hidden = $('.lightbox__nav--next', box).hidden = group.length < 2;
  };
  const close = () => { box.classList.remove('is-open'); if (opener) opener.focus(); };
  items.forEach((el) => el.addEventListener('click', () => open(el)));
  $('.icon-btn', box).addEventListener('click', close);
  $('.lightbox__nav--prev', box).addEventListener('click', () => show(i - 1));
  $('.lightbox__nav--next', box).addEventListener('click', () => show(i + 1));
  box.addEventListener('click', (e) => { if (e.target === box) close(); });
  document.addEventListener('keydown', (e) => {
    if (!box.classList.contains('is-open')) return;
    if (e.key === 'Escape') close(); else if (e.key === 'ArrowLeft') show(i - 1); else if (e.key === 'ArrowRight') show(i + 1);
  });
  let x0 = null;
  box.addEventListener('pointerdown', (e) => { x0 = e.clientX; });
  box.addEventListener('pointerup', (e) => { if (x0 === null) return; const dx = e.clientX - x0; x0 = null; if (Math.abs(dx) > 50 && group.length > 1) show(dx < 0 ? i + 1 : i - 1); });
}

/* ------------------------------------------------------------------ search overlay */
function search() {
  const dlg = $('#search');
  if (!dlg) return;
  const input = $('input', dlg); const list = $('.searchbox__list', dlg);
  const all = [
    ...POSTS.map((p) => ({ g: '文章', icon: 'i-book', title: p.title, sum: p.sum, href: p.href, k: `${p.title}${p.sum}${p.tags.join('')}` })),
    ...MOMENTS.map((m) => ({ g: '动态', icon: 'i-chat', title: m.text, sum: `心情：${m.mood}`, href: m.href, k: `${m.text}${m.mood}` })),
    ...PAGES.map((p) => ({ g: '页面', icon: 'i-smile', title: p.title, sum: p.sum, href: p.href, k: `${p.title}${p.sum}` })),
  ];
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let sel = 0; let shown = [];
  const render = () => {
    const q = input.value.trim().toLowerCase();
    shown = q ? all.filter((x) => x.k.toLowerCase().includes(q)).slice(0, 8) : all.filter((x) => x.g === '文章').slice(0, 4);
    if (!shown.length) { list.innerHTML = `<div class="empty" style="margin:8px;border-style:dashed"><strong>没有找到「${esc(input.value)}」</strong><span>换个词试试？或者去归档里翻一翻。</span></div>`; return; }
    const hl = (s) => (q ? esc(s).replace(new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig'), (m) => `<mark>${m}</mark>`) : esc(s));
    let g = ''; let html = q ? '' : '<div class="searchbox__group">最近的文章</div>';
    shown.forEach((x, i) => {
      if (q && x.g !== g) { g = x.g; html += `<div class="searchbox__group">${g}</div>`; }
      html += `<a class="searchbox__item" href="${x.href}" role="option" aria-selected="${i === sel}"><span class="ico"><svg class="i"><use href="#${x.icon}"/></svg></span><span><strong>${hl(x.title)}</strong><small>${hl(x.sum)}</small></span></a>`;
    });
    list.innerHTML = html;
  };
  const move = (d) => { sel = (sel + d + shown.length) % shown.length; $$('.searchbox__item', list).forEach((a, i) => a.setAttribute('aria-selected', String(i === sel))); };
  const open = () => { if (!dlg.open) { dlg.showModal(); input.value = ''; sel = 0; render(); input.focus(); } };
  $$('[data-open-search]').forEach((b) => b.addEventListener('click', open));
  document.addEventListener('keydown', (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if ((e.key === '/' && !typing) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) { e.preventDefault(); open(); }
  });
  input.addEventListener('input', () => { sel = 0; render(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); move(1); } else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
    else if (e.key === 'Enter' && shown[sel]) location.href = shown[sel].href;
    else if (e.key === 'Escape') { e.preventDefault(); dlg.close(); }   // a search field would otherwise only clear its text on the first Esc
  });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  $('[data-close-search]', dlg)?.addEventListener('click', () => dlg.close());
}

/* ------------------------------------------------------------------ card grids: a last card alone in its row lies down across it */
let tidyGrids = () => {};
function gridTails() {
  const grids = $$('.grid-6').filter((g) => g.querySelector(':scope > .card'));
  if (!grids.length) return;
  tidyGrids = () => {
    let changed = false;
    grids.forEach((g) => {
      const cards = [...g.children].filter((c) => c.offsetParent !== null);
      const had = g.querySelector(':scope > .is-tail') !== null;
      cards.forEach((c) => c.classList.remove('is-tail'));
      const last = cards[cards.length - 1];
      const alone = last && last.offsetWidth < g.clientWidth - 2 && !cards.some((c) => c !== last && Math.abs(c.offsetTop - last.offsetTop) < 2);
      if (alone) last.classList.add('is-tail');
      if (had !== Boolean(alone)) changed = true;
    });
    if (changed) FX.refresh();
  };
  let raf = 0;
  addEventListener('resize', () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(tidyGrids); });
  tidyGrids();
}

/* ------------------------------------------------------------------ blog list: filters, sort, view toggle */
function blogFilters() {
  const root = $('[data-blog]');
  if (!root) return;
  const items = $$('[data-post]', root);
  const tabs = $$('[data-cat]', root); const chips = $$('[data-tag]', root);
  const q = $('[data-q]', root); const sort = $('[data-sort]', root); const count = $('[data-count]', root);
  const listBox = $('[data-list]', root);
  const state = { cat: 'all', tag: '', q: '', sort: 'new', view: store.get('bb:view') || 'grid' };
  const row = (el) => {
    const d = el.dataset; const [y, m, day] = d.date.split('-');
    const tags = d.tags.split(',').filter(Boolean).map((t) => `<span class="tag tag--sky">${t}</span>`).join('');
    return `<a class="postrow" href="${d.href}"><div class="stamp stamp--sm"><b>${day}</b><small>${m}月</small></div><div><h3 class="postrow__title">${d.title}</h3><p class="postrow__sum">${d.sum}</p><div class="postrow__tags">${tags}</div></div><svg class="i postrow__go" aria-hidden="true"><use href="#i-arrow-r"/></svg></a>`;
  };
  const apply = () => {
    let shown = items.filter((el) => {
      const d = el.dataset;
      const okCat = state.cat === 'all' || d.cat === state.cat;
      const okTag = !state.tag || d.tags.split(',').includes(state.tag);
      const okQ = !state.q || `${d.title}${d.sum}${d.tags}`.toLowerCase().includes(state.q);
      return okCat && okTag && okQ;
    });
    items.forEach((el) => { el.hidden = !shown.includes(el); });
    const filtered = state.cat !== 'all' || state.tag || state.q;
    root.classList.toggle('is-filtered', Boolean(filtered));
    const ordered = [...shown].sort((a, b) => (state.sort === 'new' ? b.dataset.date.localeCompare(a.dataset.date) : a.dataset.date.localeCompare(b.dataset.date)));
    listBox.innerHTML = ordered.map(row).join('') || '<div class="empty"><strong>这里什么也没有</strong><span>换个分类或者标签试试。</span></div>';
    count.textContent = `共 ${shown.length} 篇`;
    root.classList.toggle('is-list', state.view === 'list');
    $$('[data-view]', root).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === state.view)));
    $$('.postrow', listBox).forEach((r) => r.setAttribute('data-fx', 'fade'));
    tidyGrids();
    FX.refresh();
  };
  tabs.forEach((t) => t.addEventListener('click', () => { state.cat = t.dataset.cat; tabs.forEach((x) => x.setAttribute('aria-selected', String(x === t))); apply(); }));
  chips.forEach((c) => c.addEventListener('click', () => { state.tag = state.tag === c.dataset.tag ? '' : c.dataset.tag; chips.forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.tag === state.tag))); apply(); }));
  q.addEventListener('input', () => { state.q = q.value.trim().toLowerCase(); apply(); });
  sort.addEventListener('change', () => { state.sort = sort.value; apply(); });
  $$('[data-view]', root).forEach((b) => b.addEventListener('click', () => { state.view = b.dataset.view; store.set('bb:view', state.view); apply(); }));
  apply();
}

/* ------------------------------------------------------------------ moments: month index follows the page */
function monthNav() {
  const seps = $$('.month-sep[id]');
  const nav = $('.month-nav ol');
  if (!seps.length || !nav) return;
  const links = $$('a', nav);
  const ind = $('.toc__ind', nav);
  const tick = () => {
    let idx = 0;
    seps.forEach((s, i) => { if (s.getBoundingClientRect().top <= 160) idx = i; });
    links.forEach((a, k) => a.classList.toggle('is-active', k === idx));
    const a = links[idx];
    if (a && ind) { ind.style.setProperty('--y', `${a.offsetTop}px`); ind.style.setProperty('--h', `${a.offsetHeight}px`); ind.classList.add('is-ready'); }
  };
  addEventListener('scroll', () => requestAnimationFrame(tick), { passive: true });
  tick();
}

/* ------------------------------------------------------------------ prototype-only design panel */
function panel() {
  const el = document.createElement('div');
  el.className = 'dpanel';
  const theme = document.documentElement.getAttribute('data-theme') || 'default';
  const mode = FX.getMode();
  el.innerHTML = `<button class="dpanel__btn" aria-expanded="false" aria-controls="dpanel-body"><svg class="i"><use href="#i-sliders"/></svg><span>设计面板</span></button>
  <div class="dpanel__body" id="dpanel-body" role="group" aria-label="设计面板">
    <div><h2>主题（全部是浅色）</h2><div class="dpanel__row" data-group="theme">
      <button class="tag" data-v="default" aria-pressed="${theme === 'default'}">糖霜</button><button class="tag" data-v="sky" aria-pressed="${theme === 'sky'}">晴空</button><button class="tag" data-v="sakura" aria-pressed="${theme === 'sakura'}">樱花</button><button class="tag" data-v="fog" aria-pressed="${theme === 'fog'}">云雾</button></div></div>
    <div><h2>滚动动效</h2><div class="dpanel__row" data-group="motion">
      <button class="tag" data-v="full" aria-pressed="${mode === 'full'}">标准</button><button class="tag" data-v="soft" aria-pressed="${mode === 'soft'}">轻柔</button><button class="tag" data-v="off" aria-pressed="${mode === 'off'}">关闭</button></div>
      <small style="color:var(--ink-2);font-size:12px" data-note></small></div>
  </div>`;
  document.body.append(el);
  const btn = $('.dpanel__btn', el);
  btn.addEventListener('click', () => { const o = el.classList.toggle('is-open'); btn.setAttribute('aria-expanded', String(o)); });
  document.addEventListener('click', (e) => { if (!el.contains(e.target)) { el.classList.remove('is-open'); btn.setAttribute('aria-expanded', 'false'); } });
  const note = $('[data-note]', el);
  if (reduced()) note.textContent = '系统开启了「减少动态效果」，所以动效保持关闭。';
  $$('[data-group="theme"] .tag', el).forEach((b) => b.addEventListener('click', () => {
    const v = b.dataset.v;
    if (v === 'default') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', v);
    store.set('bb:theme', v === 'default' ? '' : v);
    $$('[data-group="theme"] .tag', el).forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  }));
  $$('[data-group="motion"] .tag', el).forEach((b) => b.addEventListener('click', () => {
    FX.setMode(b.dataset.v);
    $$('[data-group="motion"] .tag', el).forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  }));
}

/* ------------------------------------------------------------------ boot */
autoFx();
$$('.card__title, .postrow__title, .archive__item strong, .series li > a, .series li > span, .pn strong, .hub-card h3, .about__card h3, .lost h1').forEach(phrasify);
indicator($('.nav'), '.nav__ind', 'bb:ind:nav');
indicator($('.tabbar'), '.tabbar__ind', 'bb:ind:tab');
backTop(); readBar(); toc(); copyButtons(); lightbox(); search(); gridTails(); blogFilters(); monthNav(); panel();
FX.init();
window.__page = { FX };
