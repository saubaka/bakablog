/* Runs in <head>, before the first paint, as a plain script (ES5, no imports): it sets what the CSS needs on <html> so
   the page never flashes the wrong theme or the wrong motion state.
     - theme, code theme, decor switches: from the site settings the server inlined as #bb-data
     - motion level: system "reduce motion" > ?motion= > the visitor's saved choice > the site default
     - html.fx-pending hides [data-fx] elements until the engine has positioned them; html.boot hides the server's plain copy
       of the page until the app has replaced it. Both are lifted by the app, and by a timer in case the app never starts.
   Without JavaScript none of these classes exist, so the plain page is fully visible. Keep readMode() in step with
   src/fx/engine.ts (tests/boot.test.ts runs both). */
(function () {
  var d = document.documentElement;
  var site = null;
  try {
    var node = document.getElementById('bb-data');
    if (node) { var parsed = JSON.parse(node.textContent || 'null'); site = parsed && parsed.site; }
  } catch (e) { /* the app falls back to /api/site */ }

  function store(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  var modes = ['full', 'soft', 'off'];

  var theme = site && site.theme;
  if (theme && theme !== 'default') d.setAttribute('data-theme', theme);
  if (site && site.code_theme) d.setAttribute('data-code-theme', site.code_theme);
  if (site && site.decor) {
    if (site.decor.tape === false) d.classList.add('no-tape');
    if (site.decor.doodles === false) d.classList.add('no-doodles');
  }

  var fallback = site && modes.indexOf(site.motion) >= 0 ? site.motion : 'full';
  var m = fallback;
  try { m = new URLSearchParams(location.search).get('motion') || store('bb:motion') || fallback; } catch (e) { m = store('bb:motion') || fallback; }
  if (modes.indexOf(m) < 0) m = fallback;
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) m = 'off';
  d.setAttribute('data-fx-mode', m);

  d.classList.add('boot');
  if (m === 'off') d.classList.add('fx-off'); else d.classList.add('fx-pending');
  setTimeout(function () { d.classList.remove('fx-pending'); d.classList.remove('boot'); }, 2600);
})();
