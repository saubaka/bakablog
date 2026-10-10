(() => {
  const key = 'cloud-diary-route-transition';
  const root = document.documentElement;
  const prepareComponentMotion = (
    'animate' in Element.prototype &&
    root.dataset.motion !== 'reduce' &&
    !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
  if (prepareComponentMotion) {
    root.classList.add('motion-preparing');
    window.__cloudtraceMotionFallback = window.setTimeout(() => {
      root.classList.remove('motion-preparing');
    }, 700);
  }
  const isPublicRoute = !window.location.pathname.startsWith('/admin/');
  // The original stretch preset remains available in the administration
  // workspace. Public pages use the quieter fade as their default so a route
  // curtain never competes with the page's own card outlines.
  if (isPublicRoute && root.dataset.pageTransition === 'stretch') {
    root.dataset.pageTransition = 'fade';
  }
  const duration = Math.max(300, Math.min(2400, Number.parseInt(root.dataset.transitionDuration, 10) || 720));
  const safeColor = (value, fallback) => /^#[0-9a-f]{6}$/i.test(value || '') ? value : fallback;
  const timing = {
    '--route-duration': duration,
    '--route-stretch-cover': Math.round(duration * .58),
    '--route-stretch-reveal': Math.round(duration * .86),
    '--route-fade-cover': Math.round(duration * .27),
    '--route-fade-reveal': Math.round(duration * .46),
    '--route-focus-cover': Math.round(duration * .42),
    '--route-focus-reveal': Math.round(duration * .69),
    '--route-reveal-delay': Math.round(duration * .08),
    '--route-content-delay': Math.round(duration * .16),
    '--route-editor-delay': Math.round(duration * .17),
    '--route-editor-canvas-delay': Math.round(duration * .29),
    '--route-editor-sidebar-delay': Math.round(duration * .42)
  };
  Object.entries(timing).forEach(([name, value]) => root.style.setProperty(name, `${value}ms`));
  const colors = {
    '--route-color-start': safeColor(root.dataset.transitionColorStart, '#EDF4FC'),
    '--route-color-middle': safeColor(root.dataset.transitionColorMiddle, '#F7F9FC'),
    '--route-color-end': safeColor(root.dataset.transitionColorEnd, '#F7E5ED'),
    '--dialog-accent': safeColor(root.dataset.dialogAccent, '#99ABCD'),
    '--component-motion-color': safeColor(root.dataset.componentMotionColor, '#D4E6F3')
  };
  Object.entries(colors).forEach(([name, value]) => root.style.setProperty(name, value));
  const safeNumber = (value, fallback, minimum, maximum) => {
    const parsed = Number.parseInt(value, 10);
    return Math.max(minimum, Math.min(maximum, Number.isFinite(parsed) ? parsed : fallback));
  };
  root.style.setProperty('--dialog-radius', `${safeNumber(root.dataset.dialogRadius, 22, 14, 42)}px`);
  root.style.setProperty('--dialog-width', `${safeNumber(root.dataset.dialogWidth, 510, 360, 720)}px`);
  root.style.setProperty('--dialog-backdrop-blur', `${safeNumber(root.dataset.dialogBackdropBlur, 6, 0, 30)}px`);
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return;
    sessionStorage.removeItem(key);
    const state = JSON.parse(raw);
    if (!state || Date.now() - Number(state.startedAt || 0) > 15000) return;
    root.classList.add('is-page-entering');
    if (state.targetKind === 'editor') root.classList.add('is-editor-transition');
  } catch (_) {
    // Transitions remain optional when session storage is unavailable.
  }
})();
