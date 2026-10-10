/*
 * v1.40.0 - Project 8 adoption, phase 4: progressive same-shell navigation.
 *
 * Page modules register an init(scope, signal) function and may return a
 * cleanup. They run once on the first document; after an enhanced navigation
 * the previous page's modules are disposed and every module is mounted again
 * on the new region only. The persistent shell (navigation, sidebar,
 * notification host and global dialogs) is never re-bound.
 *
 * Navigation is only attempted for ordinary same-origin GET pages that share
 * the current shell. The old page stays on screen until the new HTML is
 * ready; anything unexpected (other layout, page-specific scripts, errors,
 * different theme) falls back to a normal browser navigation. Fetched HTML is
 * parsed inertly and its scripts are never executed.
 */
(() => {
  'use strict';

  const doc = document;
  const root = doc.documentElement;
  const REGION = '[data-navigation-region]';
  const NATIVE_PATH = /^\/(?:admin\/(?:posts\/(?:new|\d+\/edit)|pages\/(?:new|\d+\/edit)|logout)\/?|bakaadmin|auth\/|out\/|static\/|media\/|feed|sitemap|robots|healthz|readyz|demo\/)/;
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reducedMotion = () => root.dataset.motion === 'reduce' || root.dataset.performance === 'low' || reducedQuery.matches;

  /* ---------- Page modules ---------- */

  const modules = [];
  let mounted = [];

  function runModule(module, scope) {
    const controller = new AbortController();
    let cleanup = null;
    try {
      cleanup = module.init(scope, controller.signal) || null;
    } catch (error) {
      window.setTimeout(() => { throw error; }, 0);
    }
    mounted.push({ module, controller, cleanup });
  }

  function define(name, init) {
    const module = { name, init };
    modules.push(module);
    runModule(module, doc);
  }

  function unmount() {
    const current = mounted.reverse();
    mounted = [];
    current.forEach(({ controller, cleanup }) => {
      controller.abort();
      if (typeof cleanup === 'function') {
        try { cleanup(); } catch (error) { window.setTimeout(() => { throw error; }, 0); }
      }
    });
  }

  function mount(scope) { modules.forEach((module) => runModule(module, scope)); }

  /* ---------- Unsaved form guard ---------- */

  const guardedForm = (target) => {
    const form = target?.closest?.('form');
    if (!form || form.dataset.noDirtyGuard !== undefined) return null;
    if ((form.getAttribute('method') || 'get').toLowerCase() !== 'post') return null;
    return form.closest(REGION) ? form : null;
  };
  const markDirty = (event) => {
    if (!event.isTrusted) return;
    const form = guardedForm(event.target);
    if (form) form.dataset.dirty = 'true';
  };
  doc.addEventListener('input', markDirty, true);
  doc.addEventListener('change', markDirty, true);
  doc.addEventListener('submit', (event) => { delete event.target.dataset?.dirty; }, true);

  const hasUnsavedChanges = () => Boolean(doc.querySelector(`${REGION} form[data-dirty="true"]`));
  async function confirmLeave() {
    if (!hasUnsavedChanges()) return true;
    const ask = window.CloudDiary?.confirm;
    const approved = ask
      ? await ask('页面上有尚未保存的修改，离开后这些修改会丢失。确定要离开吗？', '离开此页面')
      : true;
    if (approved) doc.querySelectorAll(`${REGION} form[data-dirty="true"]`).forEach((form) => { delete form.dataset.dirty; });
    return approved;
  }

  /* ---------- Shell compatibility ---------- */

  const meta = (source, name) => source.querySelector(`meta[name="${name}"]`)?.content || '';
  const assetList = (source) => [
    ...[...source.querySelectorAll('head script[src]')].map((item) => `s:${item.getAttribute('src')}`),
    ...[...source.querySelectorAll('head link[rel="stylesheet"]')].map((item) => `c:${item.getAttribute('href')}`)
  ].join('|');
  const shellKey = (source) => [
    meta(source, 'cloudtrace-navigation'),
    source.documentElement.dataset.themeSignature || '',
    source.querySelector(REGION)?.dataset.navigationRegion || '',
    source.querySelector(REGION)?.dataset.shellSignature || '',
    assetList(source)
  ].join('#');
  let currentShell = '';

  const isEnhancedDocument = () => meta(doc, 'cloudtrace-navigation') === 'enhanced'
    && Boolean(doc.querySelector(REGION))
    && 'fetch' in window && 'DOMParser' in window && typeof history.pushState === 'function';

  function shouldHandle(url, link = null) {
    if (!isEnhancedDocument()) return false;
    if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol)) return false;
    if (NATIVE_PATH.test(url.pathname)) return false;
    if (link && (link.closest('[data-navigation="native"]') || link.dataset.noTransition !== undefined
      || link.matches('[data-image-preview],[data-gallery-image],[data-external-link-bypass],[data-open-dialog]'))) return false;
    return true;
  }

  /* ---------- Navigation ---------- */

  let token = 0;
  let controller = null;
  let loadingTimer = 0;
  let renderedKey = location.pathname + location.search;
  // Network wait and visual swap are measured separately so slow responses
  // are never disguised as animation time.
  let lastTiming = null;

  const saveScroll = () => {
    try {
      const state = history.state && typeof history.state === 'object' ? history.state : {};
      history.replaceState({ ...state, cloudtrace: { scrollY: Math.round(window.scrollY) } }, '', location.href);
    } catch (_) { /* history state is optional */ }
  };

  function setLoading(active) {
    window.clearTimeout(loadingTimer);
    if (active) {
      // Fast responses never flash a loading state.
      loadingTimer = window.setTimeout(() => root.classList.add('is-route-loading'), 140);
    } else {
      root.classList.remove('is-route-loading');
    }
  }

  function fallback(url, mode) {
    setLoading(false);
    if (mode === 'pop') location.reload();
    else location.assign(url);
  }

  const syncHead = (next) => {
    doc.title = next.title;
    const selectors = [
      'meta[name="description"]', 'meta[name="keywords"]', 'meta[name="robots"]', 'meta[name="author"]',
      'link[rel="canonical"]', 'link[rel="alternate"]', 'script[type="application/ld+json"]'
    ];
    selectors.forEach((selector) => {
      const fresh = next.head.querySelector(selector);
      const existing = doc.head.querySelector(selector);
      if (fresh && existing) existing.replaceWith(doc.importNode(fresh, true));
      else if (fresh) doc.head.append(doc.importNode(fresh, true));
      else existing?.remove();
    });
    doc.head.querySelectorAll('meta[property^="og:"],meta[name^="twitter:"]').forEach((item) => item.remove());
    next.head.querySelectorAll('meta[property^="og:"],meta[name^="twitter:"]').forEach((item) => {
      doc.head.append(doc.importNode(item, true));
    });
  };

  /* Current-page markers are the only shell differences between pages. */
  const syncShell = (next) => {
    const mark = (selector, attribute = 'href') => {
      const fresh = new Map();
      next.querySelectorAll(selector).forEach((item) => {
        const key = item.getAttribute(attribute);
        fresh.set(key, Boolean(fresh.get(key)) || item.classList.contains('is-current'));
      });
      doc.querySelectorAll(selector).forEach((item) => {
        const key = item.getAttribute(attribute);
        if (!fresh.has(key)) return;
        const current = fresh.get(key);
        item.classList.toggle('is-current', current);
        if (current) item.setAttribute('aria-current', 'page');
        else item.removeAttribute('aria-current');
      });
    };
    ['.site-nav a[href]', '.mobile-bottom-nav a[href]', '#mobile-drawer a[href]', '.admin-nav a[href]'].forEach((selector) => mark(selector));
    mark('.mobile-bottom-nav button[aria-controls]', 'aria-controls');
  };

  /* Page-level body classes (for example search-body) follow the page. */
  const syncBodyClass = (next) => {
    const previous = (doc.body.dataset.bodyClass || '').split(/\s+/).filter(Boolean);
    const incoming = (next.body.dataset.bodyClass || '').split(/\s+/).filter(Boolean);
    previous.forEach((name) => doc.body.classList.remove(name));
    incoming.forEach((name) => doc.body.classList.add(name));
    doc.body.dataset.bodyClass = incoming.join(' ');
  };

  const prepareRegion = (region) => {
    region.querySelectorAll('script:not([type="application/json"])').forEach((item) => item.remove());
    return region;
  };

  const adoptFlashes = (next) => {
    const items = [...next.querySelectorAll('[data-flash-source] [data-flash-tone]')];
    items.forEach((item) => window.CloudtraceNotifications?.notify(item.textContent, item.dataset.flashTone));
  };

  const scrollToTarget = (url, scrollY) => {
    const hash = url.hash ? decodeURIComponent(url.hash.slice(1)) : '';
    const target = hash ? doc.getElementById(hash) : null;
    if (target) target.scrollIntoView({ block: 'start' });
    else window.scrollTo({ top: scrollY ?? 0, left: 0, behavior: 'instant' });
  };

  const wait = (milliseconds, ticket) => new Promise((resolve) => {
    window.setTimeout(() => resolve(ticket === token), milliseconds);
  });

  async function swap(next, url, mode, scrollY, ticket) {
    const region = doc.querySelector(REGION);
    const fresh = next.querySelector(REGION);
    const animated = !reducedMotion();
    if (animated && mode === 'push') {
      region.classList.add('is-route-leaving');
      if (!await wait(150, ticket)) { region.classList.remove('is-route-leaving'); return; }
    }
    window.CloudDiary?.closeDrawers?.();
    unmount();
    const incoming = prepareRegion(doc.adoptNode(fresh));
    if (animated) incoming.classList.add('is-route-entering');
    region.replaceWith(incoming);
    window.CloudtraceMotion?.prepare?.(incoming);
    syncHead(next);
    if (mode === 'push') history.pushState({ cloudtrace: { scrollY: 0 } }, '', url.href);
    else if (location.href !== url.href) history.replaceState({ cloudtrace: { scrollY: scrollY ?? 0 } }, '', url.href);
    renderedKey = url.pathname + url.search;
    syncShell(next);
    syncBodyClass(next);
    mount(incoming);
    scrollToTarget(url, mode === 'pop' ? scrollY : 0);
    (incoming.matches('#main-content') ? incoming : incoming.querySelector('#main-content') || incoming)
      .focus({ preventScroll: true });
    adoptFlashes(next);
    setLoading(false);
    window.dispatchEvent(new CustomEvent('cloudtrace:navigated', { detail: { url: url.href, mode } }));
    if (animated) {
      const done = () => incoming.classList.remove('is-route-entering');
      incoming.addEventListener('animationend', (event) => { if (event.target === incoming) done(); }, { once: true });
      window.setTimeout(done, 420);
    }
  }

  async function navigate(input, { mode = 'push', scrollY = null } = {}) {
    const url = new URL(input, location.href);
    const ticket = ++token;
    controller?.abort();
    if (mode === 'push') {
      if (!await confirmLeave()) return false;
      if (ticket !== token) return false;
      saveScroll();
    }
    controller = new AbortController();
    setLoading(true);
    const startedAt = performance.now();
    try {
      const response = await fetch(url.href, {
        credentials: 'same-origin',
        cache: 'no-store',
        signal: controller.signal,
        headers: { Accept: 'text/html', 'X-Cloudtrace-Navigation': '1' }
      });
      if (ticket !== token) return false;
      const finalUrl = new URL(response.url || url.href);
      finalUrl.hash = url.hash;
      const type = response.headers.get('content-type') || '';
      if (!response.ok || finalUrl.origin !== location.origin || !type.includes('text/html')
        || NATIVE_PATH.test(finalUrl.pathname)) {
        fallback(finalUrl.href, mode);
        return false;
      }
      const html = await response.text();
      if (ticket !== token) return false;
      const next = new DOMParser().parseFromString(html, 'text/html');
      if (!next.querySelector(REGION) || shellKey(next) !== currentShell) {
        fallback(finalUrl.href, mode);
        return false;
      }
      const receivedAt = performance.now();
      await swap(next, finalUrl, mode, scrollY, ticket);
      lastTiming = {
        url: finalUrl.pathname + finalUrl.search,
        mode,
        networkMs: Math.round(receivedAt - startedAt),
        swapMs: Math.round(performance.now() - receivedAt)
      };
      return true;
    } catch (error) {
      if (error?.name === 'AbortError' || ticket !== token) return false;
      fallback(url.href, mode);
      return false;
    }
  }

  window.addEventListener('popstate', async (event) => {
    if (!isEnhancedDocument()) return;
    const key = location.pathname + location.search;
    if (key === renderedKey) return;
    if (hasUnsavedChanges()) {
      const leavingTo = location.href;
      history.pushState({ cloudtrace: { scrollY: Math.round(window.scrollY) } }, '', new URL(renderedKey, location.href).href);
      if (!await confirmLeave()) return;
      history.replaceState(event.state, '', leavingTo);
    }
    navigate(location.href, { mode: 'pop', scrollY: event.state?.cloudtrace?.scrollY ?? 0 });
  });

  window.addEventListener('pagehide', saveScroll);

  function start() {
    if (!isEnhancedDocument()) return;
    currentShell = shellKey(doc);
    try { history.scrollRestoration = 'manual'; } catch (_) { /* optional */ }
    const saved = history.state?.cloudtrace?.scrollY;
    const entry = performance.getEntriesByType?.('navigation')?.[0];
    if (entry?.type === 'back_forward' && Number.isFinite(saved)) {
      window.requestAnimationFrame(() => window.scrollTo({ top: saved, left: 0, behavior: 'instant' }));
    }
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start, { once: true });
  else start();

  window.CloudtracePage = {
    define,
    mount,
    unmount,
    navigate,
    shouldHandle,
    confirmLeave,
    hasUnsavedChanges,
    inspect: () => ({
      modules: modules.map((module) => module.name),
      mounted: mounted.length,
      renderedKey,
      enhanced: isEnhancedDocument(),
      lastTiming
    })
  };
})();
