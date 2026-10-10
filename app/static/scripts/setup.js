(() => {
  'use strict';

  // Administrator setup page: step tracking and password helpers.
  // Everything degrades to a plain, working form without it.
  const MIN_PASSWORD = 14;
  const strengthOf = (value) => {
    if (!value) return 0;
    const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((pattern) => pattern.test(value)).length;
    if (value.length < MIN_PASSWORD) return value.length < 8 ? 1 : 2;
    if (kinds >= 3 && value.length >= 18) return 4;
    return kinds >= 2 ? 3 : 2;
  };

  const init = (scope, signal) => {
    const root = scope.querySelector('[data-setup]');
    const form = root?.querySelector('[data-setup-form]');
    if (!root || !form) return null;

    const field = (name) => form.querySelector(`[name="${name}"]`);
    const username = field('username');
    const displayName = field('display_name');
    const password = field('password');
    const confirm = field('password_confirm');
    const setupCode = field('setup_code');
    const answer = field('human_answer');
    const steps = [...root.querySelectorAll('[data-setup-steps] [data-step]')];
    const stepsList = root.querySelector('[data-setup-steps]');
    const meter = form.querySelector('[data-setup-meter]');
    const strengthText = form.querySelector('[data-setup-strength]');
    const matchText = form.querySelector('[data-setup-match]');
    const peek = form.querySelector('[data-setup-peek]');
    const submit = form.querySelector('[data-setup-submit]');
    const mascot = root.querySelector('[data-setup-mascot]');
    const readyText = root.querySelector('[data-setup-ready-text]');
    const listen = (target, type, handler, options) => target?.addEventListener(type, handler, { ...options, signal });

    const done = {
      account: () => (username?.value.trim().length ?? 0) >= 3 && (displayName?.value.trim().length ?? 0) >= 1,
      password: () => (password?.value.length ?? 0) >= MIN_PASSWORD && password.value === confirm?.value,
      verify: () => (answer?.value.trim().length ?? 0) === 4 && (!setupCode || setupCode.value.trim().length > 0)
    };
    const order = ['account', 'password', 'verify'];
    let focusedGroup = '';

    const renderSteps = () => {
      const states = order.map((key) => done[key]());
      const firstOpen = states.indexOf(false);
      const current = focusedGroup && !states[order.indexOf(focusedGroup)] ? focusedGroup : (firstOpen < 0 ? '' : order[firstOpen]);
      steps.forEach((item) => {
        const complete = states[order.indexOf(item.dataset.step)];
        item.dataset.done = String(complete);
        if (item.dataset.step === current) item.setAttribute('aria-current', 'step');
        else item.removeAttribute('aria-current');
      });
      const finished = states.filter(Boolean).length;
      stepsList?.style.setProperty('--rail', String(Math.min(1, finished / (order.length - 1))));
      const ready = states.every(Boolean);
      if (mascot) mascot.dataset.setupReady = String(ready);
      if (readyText) readyText.textContent = ready ? '可以创建了' : '管理员待创建';
    };

    const renderPassword = () => {
      if (!password) return;
      const value = password.value;
      const level = strengthOf(value);
      if (meter) meter.dataset.level = String(level);
      if (strengthText) {
        if (!value) { strengthText.textContent = `至少 ${MIN_PASSWORD} 个字符`; delete strengthText.dataset.tone; }
        else if (value.length < MIN_PASSWORD) {
          strengthText.textContent = `还差 ${MIN_PASSWORD - value.length} 个字符`;
          strengthText.dataset.tone = 'warn';
        } else {
          strengthText.textContent = ['', '', '长度够了，再加点数字或符号更好', '长度够了，组合也不错', '很不错'][level] || '';
          strengthText.dataset.tone = 'ok';
        }
      }
      if (matchText) {
        if (!confirm?.value) { matchText.textContent = '再输一遍，防止打错'; delete matchText.dataset.tone; }
        else if (confirm.value === value) { matchText.textContent = '两次一样'; matchText.dataset.tone = 'ok'; }
        else { matchText.textContent = '两次不一样'; matchText.dataset.tone = 'warn'; }
      }
    };

    const refresh = () => { renderPassword(); renderSteps(); };
    listen(form, 'input', refresh);
    listen(form, 'focusin', (event) => {
      focusedGroup = event.target.closest('[data-setup-group]')?.dataset.setupGroup || '';
      renderSteps();
    });
    listen(form, 'focusout', () => { focusedGroup = ''; window.setTimeout(renderSteps, 0); });

    listen(peek, 'click', () => {
      const showing = peek.getAttribute('aria-pressed') !== 'true';
      peek.setAttribute('aria-pressed', String(showing));
      peek.setAttribute('aria-label', showing ? '隐藏密码' : '显示密码');
      peek.textContent = showing ? '隐藏' : '显示';
      [password, confirm].forEach((input) => {
        if (!input) return;
        input.type = showing ? 'text' : 'password';
        if (showing) input.dataset.peeked = ''; else delete input.dataset.peeked;
      });
    });

    let busyTimer = 0;
    listen(form, 'submit', () => {
      if (submit?.getAttribute('aria-busy') === 'true') return;
      // Mark busy after the browser has collected the form data (it reads the button value).
      busyTimer = window.setTimeout(() => submit?.setAttribute('aria-busy', 'true'), 0);
    });
    // Coming back through the bfcache must not leave the button stuck.
    listen(window, 'pageshow', () => submit?.removeAttribute('aria-busy'));

    // Every block of the form (heading, group titles, text boxes, captcha, button) slides in from the edge it is entering through and
    // slides back out the same side when it leaves, whichever way the page is scrolled.
    const boxes = [...root.querySelectorAll('.setup-card__head, .setup-group > legend, .setup-group > .setup-field, .setup-group > .setup-bundle, .setup-group > .human-check, .setup-submit-wrap')];
    let observer = null;
    if (boxes.length && 'IntersectionObserver' in window && !(matchMedia('(prefers-reduced-motion: reduce)').matches
      || document.documentElement.dataset.motion === 'reduce' || document.documentElement.dataset.performance === 'low')) {
      boxes.forEach((box) => box.classList.add('setup-reveal'));
      observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
        const box = entry.target;
        if (entry.isIntersecting) { box.dataset.setupReveal = 'in'; return; }
        const rootTop = entry.rootBounds ? entry.rootBounds.top : 0;
        box.dataset.setupReveal = entry.boundingClientRect.top < rootTop ? 'out-up' : 'out-down';
      }), { threshold: 0.18, rootMargin: '-3% 0px -3% 0px' });
      boxes.forEach((box) => observer.observe(box));
      signal.addEventListener('abort', () => observer?.disconnect(), { once: true });
    }

    refresh();
    // A server-side error on a later group points the steps at that group.
    const failing = form.querySelector('.has-error, .field-error');
    if (failing) focusedGroup = failing.closest('[data-setup-group]')?.dataset.setupGroup || '';
    renderSteps();
    focusedGroup = '';

    return () => { window.clearTimeout(busyTimer); observer?.disconnect(); };
  };

  if (window.CloudtracePage?.define) window.CloudtracePage.define('setup-page', init);
  else document.addEventListener('DOMContentLoaded', () => init(document, new AbortController().signal));
})();
