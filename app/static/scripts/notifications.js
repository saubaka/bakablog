/*
 * v1.39.0 - Project 8 adoption, phase 3: top droplet capsule notifications.
 *
 * One fixed host at the top centre replaces every lower-right toast. Each
 * notice is a small state machine: a droplet falls in and widens into a
 * capsule, a progress notice swaps its words inside the same capsule, and an
 * exit folds the capsule back into a droplet that falls away. Reading time is
 * separate from animation time and pauses on hover, focus, background stack
 * positions, hidden tabs and window blur. All text is written with
 * textContent; server messages are never parsed as HTML.
 */
(() => {
  'use strict';

  const doc = document;
  const root = doc.documentElement;
  const TONES = ['success', 'info', 'warning', 'error', 'loading'];
  const RESULT_TONES = ['success', 'info', 'warning', 'error'];
  const DEFAULT_MOTION = { enter: 780, exit: 680, textOut: 160, textIn: 340, stack: 320 };
  const PROGRESS_RESULT_MS = 3200;
  const VISIBLE_LAYERS = 3;
  const QUEUE_LIMIT = 8;
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const supportsPopover = typeof HTMLElement !== 'undefined' && 'showPopover' in HTMLElement.prototype;

  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const toneOf = (value) => {
    const tone = String(value || '').toLowerCase();
    if (tone === 'danger' || tone === 'fail' || tone === 'failure') return 'error';
    if (tone === 'message' || tone === 'notice') return 'info';
    return RESULT_TONES.includes(tone) ? tone : 'info';
  };

  function reducedMotion() {
    return root.dataset.motion === 'reduce'
      || root.dataset.performance === 'low'
      || reducedQuery.matches;
  }

  /* Per-type motion lives in <html data-notice-motion> (saved in the admin
     panel). Anything missing or out of range quietly falls back per field;
     configuration is never written from the browser. */
  const LIMITS = { enter: 3000, exit: 3000, text_out: 1000, text_in: 1000 };
  function normalizeMotion(source) {
    const types = {};
    const raw = source && typeof source === 'object' ? source : {};
    const rawTypes = raw.types && typeof raw.types === 'object' ? raw.types : {};
    TONES.forEach((tone) => {
      const values = rawTypes[tone] && typeof rawTypes[tone] === 'object' ? rawTypes[tone] : {};
      types[tone] = {};
      Object.entries(LIMITS).forEach(([key, maximum]) => {
        const fallback = { enter: DEFAULT_MOTION.enter, exit: DEFAULT_MOTION.exit, text_out: DEFAULT_MOTION.textOut, text_in: DEFAULT_MOTION.textIn }[key];
        const number = Number(values[key]);
        types[tone][key] = Number.isInteger(number) && number >= 0 && number <= maximum ? number : fallback;
      });
    });
    const stack = Number(raw.stack);
    return { types, stack: Number.isInteger(stack) && stack >= 0 && stack <= 1500 ? stack : DEFAULT_MOTION.stack };
  }
  let savedRaw = null;
  let savedMotion = normalizeMotion(null);
  function savedConfig() {
    const raw = root.dataset.noticeMotion || '';
    if (raw !== savedRaw) {
      savedRaw = raw;
      try { savedMotion = normalizeMotion(raw ? JSON.parse(raw) : null); } catch (_) { savedMotion = normalizeMotion(null); }
    }
    return savedMotion;
  }

  function timeline(tone = 'info', config = savedConfig()) {
    const reduced = reducedMotion();
    const values = config.types[tone] || config.types.info;
    const enter = reduced ? 0 : values.enter;
    const exit = reduced ? 0 : values.exit;
    const copyDelay = Math.floor(enter * 0.8);
    return {
      enter,
      exit,
      textOut: reduced ? 0 : values.text_out,
      textIn: reduced ? 0 : values.text_in,
      stack: reduced ? 0 : config.stack,
      copyDelay,
      copyIn: enter - copyDelay,
      copyOut: Math.round(exit * 0.18)
    };
  }

  /* The old administrator setting keeps its meaning: the base reading time. */
  function baseReadingTime() {
    const raw = Number.parseInt(root.dataset.toastDuration, 10);
    return Number.isFinite(raw) ? clamp(raw, 2000, 12000) : 5200;
  }

  function readingTime(tone, message, progressResult) {
    if (tone === 'error' || tone === 'loading') return null;
    if (progressResult) return PROGRESS_RESULT_MS;
    const base = baseReadingTime();
    const ceiling = Math.max(14000, base);
    let duration = Math.min(ceiling, base + Math.max(0, [...message].length - 14) * 65);
    if (tone === 'warning') duration = Math.min(ceiling, Math.round(duration * 1.35));
    return duration;
  }

  function estimateWidth(message, hasAction) {
    let text = 0;
    for (const character of message) text += /[⺀-￿]/.test(character) ? 13 : 7.2;
    // Padding, dot, gaps, close button and border take about 92px of the shell.
    return Math.round(Math.min(340, Math.max(hasAction ? 310 : 250, text + 92 + (hasAction ? 84 : 0))));
  }

  /* Reading clock: monotonic, pausable and never topped up after a resume. */
  function createReadingTimer(expire) {
    let remaining = null;
    let started = null;
    let token = 0;
    let disposed = false;
    let expired = false;
    let reasons = new Set();
    function stop() {
      if (started !== null && remaining !== null) remaining = Math.max(0, remaining - (performance.now() - started));
      started = null;
      window.clearTimeout(token);
      token = 0;
    }
    function arm() {
      if (disposed || expired || remaining === null || reasons.size) return;
      started = performance.now();
      token = window.setTimeout(() => {
        if (disposed || expired) return;
        token = 0; started = null; remaining = 0; expired = true;
        expire();
      }, remaining);
    }
    return {
      reset(duration) { if (disposed) return; stop(); remaining = duration; expired = false; arm(); },
      setReasons(next) {
        if (disposed) return;
        const updated = new Set(next);
        if (updated.size === reasons.size && [...updated].every((reason) => reasons.has(reason))) return;
        stop(); reasons = updated; arm();
      },
      inspect() {
        const elapsed = started === null ? 0 : performance.now() - started;
        return {
          remainingMs: remaining === null ? null : Math.max(0, Math.round(remaining - elapsed)),
          pauseReasons: [...reasons],
          running: started !== null
        };
      },
      dispose() { if (disposed) return; stop(); disposed = true; reasons.clear(); }
    };
  }

  /* animationend first, a bounded fallback for hidden tabs and interrupted animations. */
  function waitForPhase(element, eventName, matches, duration, done) {
    let settled = false;
    let timer = 0;
    const cleanup = () => { window.clearTimeout(timer); element.removeEventListener(eventName, ended); };
    const finish = () => { if (settled) return; settled = true; cleanup(); done(); };
    const ended = (event) => { if (event.target === element && matches(event)) finish(); };
    if (duration <= 0) queueMicrotask(finish);
    else { element.addEventListener(eventName, ended); timer = window.setTimeout(finish, duration + 60); }
    return { finish, cancel() { if (settled) return; settled = true; cleanup(); } };
  }
  const waitForAnimation = (element, name, duration, done) => waitForPhase(
    element, 'animationend', (event) => event.animationName === name, duration, done
  );
  const waitForStack = (element, duration, done) => waitForPhase(
    element, 'transitionend', (event) => event.propertyName === 'transform', duration, done
  );

  /* Newest first; cycling moves the foreground to the back without new timelines. */
  const cards = [];
  const allCards = new Set();

  function host() { return doc.getElementById('toast-region'); }

  function topModalDialog() {
    const open = [...doc.querySelectorAll('dialog[open]')].filter((dialog) => {
      if (dialog.classList.contains('is-closing')) return false;
      try { return dialog.matches(':modal'); } catch (_) { return true; }
    });
    return open[open.length - 1] || null;
  }

  /* A modal dialog makes everything outside it inert, so the host follows it. */
  function ensureHost() {
    const region = host();
    if (!region) return null;
    const parent = topModalDialog() || doc.body;
    if (region.parentElement !== parent) {
      if (supportsPopover && region.matches(':popover-open')) region.hidePopover();
      parent.append(region);
    }
    if (supportsPopover) {
      const open = region.matches(':popover-open');
      if (cards.length || allCards.size) {
        if (!open) { try { region.showPopover(); } catch (_) { /* The fixed host still renders. */ } }
      } else if (open) {
        region.hidePopover();
      }
    }
    region.classList.toggle('has-notices', allCards.size > 0);
    return region;
  }

  function restack() {
    const shared = reducedMotion() ? 0 : (cards[0]?.stackMs ?? DEFAULT_MOTION.stack);
    const width = cards.reduce((largest, card) => Math.max(largest, card.width), 0);
    cards.forEach((card, index) => {
      const depth = Math.min(index, VISIBLE_LAYERS);
      card.wrapper.style.setProperty('--notice-stack', `${shared}ms`);
      card.wrapper.style.setProperty('--stack-depth', String(depth));
      card.wrapper.style.setProperty('--capsule-width', `${width}px`);
      card.wrapper.style.zIndex = String(100 - index);
      card.wrapper.classList.toggle('is-background', index > 0);
      card.wrapper.classList.toggle('is-deep', index > VISIBLE_LAYERS);
      card.wrapper.setAttribute('aria-label', `${index === 0 ? '当前' : '背景'}通知 ${index + 1}/${cards.length}${cards.length > 1 ? '，按回车切换下一条' : ''}`);
      card.wrapper.tabIndex = index > VISIBLE_LAYERS ? -1 : 0;
      card.body.inert = index > 0;
      card.moveTo(index, shared);
      if (index > 0) card.settleEnter();
    });
    ensureHost();
  }

  function addCard(card) { cards.unshift(card); trimQueue(); restack(); }
  function removeCard(card) {
    const index = cards.indexOf(card);
    if (index !== -1) { cards.splice(index, 1); restack(); }
  }
  function promote(card) {
    const index = cards.indexOf(card);
    if (index > 0) { cards.splice(index, 1); cards.unshift(card); restack(); }
  }
  function cycle() {
    if (cards.length < 2) return;
    cards.push(cards.shift());
    restack();
  }

  /* Flood guard: hidden, finished notices go first; progress and errors stay longest. */
  function trimQueue() {
    while (cards.length > QUEUE_LIMIT) {
      const candidates = cards.slice(1).reverse();
      const victim = candidates.find((card) => !card.isPersistent())
        || candidates.find((card) => !card.isRunning())
        || candidates[0];
      if (!victim) return;
      victim.dispose();
    }
  }

  function syncEnvironment() {
    for (const card of allCards) {
      if (reducedMotion()) card.reduce();
      card.resume();
    }
  }

  let environmentReady = false;
  function initEnvironment() {
    if (environmentReady) return;
    environmentReady = true;
    reducedQuery.addEventListener?.('change', syncEnvironment);
    doc.addEventListener('visibilitychange', syncEnvironment);
    window.addEventListener('focus', syncEnvironment);
    window.addEventListener('blur', syncEnvironment);
    window.addEventListener('pageshow', syncEnvironment);
    new MutationObserver(() => { if (allCards.size) ensureHost(); })
      .observe(doc.body, { subtree: true, attributes: true, attributeFilter: ['open', 'class'] });
    new MutationObserver(syncEnvironment)
      .observe(root, { attributes: true, attributeFilter: ['data-motion', 'data-performance'] });
  }

  function display(notice) {
    const region = ensureHost();
    if (!region) return null;
    initEnvironment();
    const progress = notice.progress || null;
    const wrapper = doc.createElement('div');
    wrapper.className = 'notification-stack-card';
    wrapper.setAttribute('role', 'group');
    wrapper.dataset.motionSkip = '';
    const node = doc.createElement('div');
    const body = doc.createElement('div');
    body.className = 'notification-capsule__body';
    const dot = doc.createElement('span');
    dot.className = 'notification-capsule__dot';
    dot.setAttribute('aria-hidden', 'true');
    const text = doc.createElement('span');
    text.className = 'notification-capsule__text';
    text.textContent = notice.message;
    const close = doc.createElement('button');
    close.className = 'notification-capsule__close';
    close.type = 'button';
    close.setAttribute('aria-label', '关闭通知');
    close.textContent = '×';
    body.append(dot, text);

    let leaving = false;
    let disposed = false;
    let contentBusy = false;
    let actionBusy = false;
    let stackBusy = false;
    let hovered = false;
    let position = -1;
    let appliedVersion = progress?.settled ? progress.version : -1;
    let currentTone = progress && !progress.settled ? 'loading' : notice.tone;
    const width = estimateWidth(notice.message, Boolean(notice.action));
    const jobs = new Map();
    const config = notice.config || savedConfig();
    const motion = timeline(currentTone, config);

    const setTone = (tone) => {
      TONES.forEach((name) => node.classList.toggle(`notification-capsule--${name}`, name === tone));
      text.setAttribute('role', tone === 'error' ? 'alert' : 'status');
      text.setAttribute('aria-atomic', 'true');
      node.setAttribute('aria-busy', String(tone === 'loading'));
      node.dataset.tone = tone;
    };
    node.className = 'notification-capsule';
    setTone(currentTone);

    if (notice.action) {
      const action = doc.createElement('button');
      action.type = 'button';
      action.className = 'notification-capsule__action';
      action.textContent = notice.action.label;
      action.addEventListener('click', async (event) => {
        event.stopPropagation();
        if (action.disabled) return;
        action.disabled = true;
        actionBusy = true;
        resume();
        try {
          await notice.action.run();
          dismiss();
        } catch (error) {
          if (!leaving) notify(error instanceof Error && error.message ? error.message : '操作暂时未完成，请重试', 'error');
        } finally {
          action.disabled = false;
          actionBusy = false;
          resume();
        }
      });
      body.append(action);
    }
    body.append(close);
    node.append(body);
    wrapper.append(node);
    region.append(wrapper);
    wrapper.style.setProperty('--capsule-width', `${width}px`);

    const reading = createReadingTimer(() => dismiss());

    function applyTiming() {
      const current = timeline(currentTone, config);
      const values = {
        enter: current.enter, exit: current.exit, 'text-out': current.textOut, 'text-in': current.textIn,
        'copy-delay': current.copyDelay, 'copy-in': current.copyIn, 'copy-out': current.copyOut
      };
      Object.entries(values).forEach(([key, value]) => node.style.setProperty(`--notice-${key}`, `${value}ms`));
      return current;
    }
    function phase(key, element, animation, duration, done) {
      jobs.get(key)?.cancel();
      jobs.set(key, waitForAnimation(element, animation, duration, () => { jobs.delete(key); done(); }));
    }
    function cancelJobs() { jobs.forEach((job) => job.cancel()); jobs.clear(); }
    function settleEnter() { if (node.dataset.phase === 'enter') jobs.get('enter')?.finish(); }
    function reduce() {
      applyTiming();
      wrapper.style.setProperty('--notice-stack', '0ms');
      [...jobs.keys()].forEach((key) => jobs.get(key)?.finish());
    }
    function moveTo(index, duration) {
      const moved = position !== -1 && position !== index;
      position = index;
      if (moved) {
        jobs.get('stack')?.cancel();
        stackBusy = duration > 0;
        jobs.set('stack', waitForStack(wrapper, duration, () => { jobs.delete('stack'); stackBusy = false; resume(); }));
      }
      resume();
    }
    function resume() {
      if (disposed) return;
      const reasons = [];
      if (leaving) reasons.push('leaving');
      if (doc.hidden) reasons.push('hidden');
      if (!doc.hasFocus()) reasons.push('blur');
      if (cards[0] !== card) reasons.push('background');
      if (hovered) reasons.push('hover');
      if (wrapper.contains(doc.activeElement)) reasons.push('focus');
      if (node.dataset.phase === 'enter') reasons.push('enter');
      if (contentBusy) reasons.push('text');
      if (stackBusy) reasons.push('stack');
      if (actionBusy) reasons.push('action');
      reading.setReasons(reasons);
    }
    function dispose() {
      if (disposed) return;
      disposed = true;
      leaving = true;
      reading.dispose();
      cancelJobs();
      progress?.listeners.delete(applyProgress);
      resize?.disconnect();
      allCards.delete(card);
      removeCard(card);
      wrapper.remove();
      notice.signal?.removeEventListener('abort', dispose);
      ensureHost();
      progress?.owner?.removed();
    }
    function dismiss() {
      if (leaving) return;
      leaving = true;
      reading.dispose();
      cancelJobs();
      progress?.listeners.delete(applyProgress);
      resize?.disconnect();
      const current = applyTiming();
      node.dataset.phase = 'exit';
      node.classList.add('is-leaving');
      wrapper.classList.add('is-exiting');
      wrapper.classList.remove('is-background', 'is-deep');
      const hadFocus = wrapper.contains(doc.activeElement);
      wrapper.inert = true;
      removeCard(card);
      if (hadFocus) {
        const dialog = wrapper.closest('dialog[open]');
        const visible = (element) => element.getClientRects().length > 0 && !element.closest('[hidden],[inert]');
        const fallback = (dialog ? [...dialog.querySelectorAll('input:not([disabled]),textarea:not([disabled]),button:not([disabled])')]
          .find((element) => visible(element) && !wrapper.contains(element)) : null)
          || doc.getElementById('main-content');
        (cards[0]?.wrapper || fallback)?.focus?.({ preventScroll: true });
      }
      phase('exit', node, 'notification-drop-out', current.exit, dispose);
    }
    function applyProgress() {
      if (!progress) return;
      if (progress.canceled) { dismiss(); return; }
      const content = progress.settled ? progress.message : progress.updateMessage;
      if (!content || node.dataset.phase === 'enter' || contentBusy || leaving || progress.version === appliedVersion) return;
      contentBusy = true;
      appliedVersion = progress.version;
      resume();
      const completed = progress.settled;
      if (completed && progress.owner) progress.owner.resultPresented = true;
      currentTone = completed ? progress.tone : 'loading';
      const current = applyTiming();
      node.dataset.phase = 'text-out';
      node.classList.add('is-content-changing');
      phase('text-out', text, 'notification-word-out', current.textOut, () => {
        if (leaving) return;
        text.textContent = content;
        node.classList.remove('is-content-changing');
        setTone(currentTone);
        node.classList.add('is-content-arriving');
        node.dataset.phase = 'text-in';
        phase('text-in', text, 'notification-word-in', timeline(currentTone, config).textIn, () => {
          node.classList.remove('is-content-arriving');
          node.dataset.phase = completed ? 'complete' : 'capsule';
          if (completed) reading.reset(readingTime(currentTone, content, true));
          contentBusy = false;
          applyProgress();
          resume();
        });
      });
    }
    function inspect() {
      const state = reading.inspect();
      return {
        tone: currentTone,
        phase: disposed ? 'disposed' : node.dataset.phase || 'enter',
        remainingMs: state.remainingMs,
        pauseReasons: state.pauseReasons,
        position: cards.indexOf(card)
      };
    }

    const resize = 'ResizeObserver' in window ? new ResizeObserver(() => {
      if (cards[0] === card) region.style.setProperty('--stack-front-height', `${Math.max(52, node.offsetHeight)}px`);
    }) : null;
    resize?.observe(node);

    const card = {
      notice,
      wrapper,
      body,
      width,
      stackMs: motion.stack,
      moveTo,
      settleEnter,
      reduce,
      resume,
      dismiss,
      dispose,
      inspect,
      refresh(nextDuration) { reading.reset(nextDuration); resume(); },
      isPersistent: () => currentTone === 'error' || currentTone === 'loading',
      isRunning: () => Boolean(progress && !progress.settled)
    };

    close.addEventListener('click', (event) => { event.stopPropagation(); dismiss(); });
    wrapper.addEventListener('click', (event) => {
      if (event.target.closest('button,a,input')) return;
      const hadFocus = wrapper.contains(doc.activeElement);
      cycle();
      if (hadFocus) cards[0]?.wrapper.focus({ preventScroll: true });
    });
    wrapper.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        dismiss();
      } else if (event.target === wrapper && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        cycle();
        cards[0]?.wrapper.focus({ preventScroll: true });
      }
    });
    wrapper.addEventListener('pointerenter', () => { hovered = true; resume(); });
    wrapper.addEventListener('pointerleave', () => { hovered = false; resume(); });
    wrapper.addEventListener('focusin', resume);
    wrapper.addEventListener('focusout', () => queueMicrotask(resume));

    progress?.listeners.add(applyProgress);
    notice.signal?.addEventListener('abort', dispose, { once: true });
    allCards.add(card);
    applyTiming();
    node.dataset.phase = 'enter';
    reading.setReasons(['enter']);
    reading.reset(progress && !progress.settled ? null : readingTime(currentTone, notice.message, Boolean(progress)));
    phase('enter', node, 'notification-drop-in', motion.enter, () => {
      if (leaving) return;
      node.dataset.phase = progress?.settled && progress.owner?.resultPresented ? 'complete' : 'capsule';
      applyProgress();
      resume();
    });
    if (progress?.settled && progress.owner) progress.owner.resultPresented = true;
    addCard(card);
    return card;
  }

  function notify(message, tone = 'info', options = {}) {
    const text = String(message ?? '').trim();
    if (!text || options.signal?.aborted) return null;
    const resolvedTone = toneOf(tone);
    const preview = Boolean(options.previewConfig);
    const existing = !preview && cards.find((card) => !card.notice.progress && !card.notice.action && !options.action
      && !card.notice.config && card.notice.message === text && card.notice.tone === resolvedTone);
    if (existing) {
      promote(existing);
      existing.refresh(readingTime(resolvedTone, text, false));
      return handleFor(existing);
    }
    const card = display({
      message: text,
      tone: resolvedTone,
      action: options.action || null,
      config: preview ? normalizeMotion(options.previewConfig) : null,
      signal: options.signal || null
    });
    return card ? handleFor(card) : null;
  }

  function handleFor(card) {
    return { dismiss: () => card.dismiss(), inspect: () => card.inspect() };
  }

  /* One capsule per task: loading -> optional updates -> one terminal result. */
  function progress(message = '正在处理…', options = {}) {
    const state = { version: 0, settled: false, canceled: false, listeners: new Set(), tone: 'success', message: '', updateMessage: '' };
    let disposed = false;
    let waitingShown = false;
    const owner = { view: null, resultPresented: false, removed };
    state.owner = owner;
    const config = options.previewConfig ? normalizeMotion(options.previewConfig) : null;
    const signal = options.signal || null;
    function render() {
      if (disposed || owner.view || (state.settled ? owner.resultPresented : waitingShown)) return;
      owner.view = display(state.settled
        ? { message: state.message, tone: state.tone, progress: state, action: options.action || null, config, signal }
        : { message: String(message), tone: 'info', progress: state, action: null, config, signal });
      if (owner.view && !state.settled) waitingShown = true;
    }
    function removed() {
      owner.view = null;
      if (disposed) return;
      if (state.settled && owner.resultPresented) cleanup();
      else if (state.settled) render();
    }
    function cleanup() {
      if (disposed) return;
      disposed = true;
      state.canceled = true;
      state.listeners.clear();
      owner.view?.dispose();
      owner.view = null;
    }
    function settle(text, tone) {
      if (disposed || state.settled) return;
      state.settled = true;
      state.message = String(text || '操作已完成');
      state.tone = toneOf(tone);
      state.version += 1;
      state.listeners.forEach((listener) => listener());
    }
    state.listeners.add(render);
    if (signal?.aborted) cleanup();
    else {
      signal?.addEventListener('abort', cleanup, { once: true });
      render();
    }
    return {
      update(text) {
        if (disposed || state.settled || !text) return;
        state.updateMessage = String(text);
        state.version += 1;
        state.listeners.forEach((listener) => listener());
      },
      finish(text, tone = 'success') { settle(text, tone); },
      fail(text) { settle(text || '操作未能完成，请重试', 'error'); },
      cancel() {
        if (disposed) return;
        const view = owner.view;
        state.settled = true;
        cleanup();
        view?.dismiss();
      },
      inspect: () => owner.view?.inspect() || { tone: state.settled ? state.tone : 'loading', phase: disposed ? 'disposed' : 'hidden' }
    };
  }

  function dismissAll() { [...cards].forEach((card) => card.dismiss()); }
  function disposeAll() { [...allCards].forEach((card) => card.dispose()); }

  /* Server flashes are rendered as plain list items, then promoted here. */
  function adoptFlashes() {
    const source = doc.querySelector('[data-flash-source]');
    if (!source) return;
    const items = [...source.querySelectorAll('[data-flash-tone]')];
    source.remove();
    items.forEach((item) => notify(item.textContent, item.dataset.flashTone));
  }

  window.CloudtraceNotifications = {
    notify,
    progress,
    dismissAll,
    dispose: disposeAll,
    inspect: () => cards.map((card) => card.inspect())
  };

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', adoptFlashes, { once: true });
  else adoptFlashes();
})();
