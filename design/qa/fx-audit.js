// Scroll motion audit. Checks the engine against an independent recomputation of the rules, in a real browser:
//  A  at many scroll positions (including jumps and flings) every element's numbers match the formula for its CURRENT layout
//     (a stale position cache would show up here), and opacity / transform follow the numbers
//  B  monotonic: scrolling down never makes in/out go backwards, scrolling up never makes them go forwards
//  C  after resizing the window the picture is still right
//  D  "reduce motion": everything is simply there, no transforms   E  no JavaScript: everything is visible
//  F  cost: the per-frame script time with the CPU slowed down 6x (a mid-range phone)
const { PAGES, launch, open, BASE, sleep } = require('./common');
const WIDTHS = (process.env.W || '390,768,1280').split(',').map(Number);
const only = process.env.PAGE ? process.env.PAGE.split(',') : ['home', 'blog', 'post', 'moments', 'archive', '404', 'fx-lab', 'index'];

const inPage = {
  // independent recomputation, run inside the page
  measure: () => {
    const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    const docTop = (el) => { let y = 0; for (let e = el; e; e = e.offsetParent) y += e.offsetTop; return y; };
    const vh = document.documentElement.clientHeight; const sy = Math.max(0, scrollY);
    const bad = []; let checked = 0;
    document.querySelectorAll('[data-fx]').forEach((el) => {
      const s = window.FX.read(el);
      if (!s || s.hidden || s.forced || s.intro || ['drift', 'spine'].includes(s.type)) return;
      const h = el.offsetHeight;
      let top = docTop(el); let t = top - sy;
      let st = null; for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { if (getComputedStyle(p).position === 'sticky') { st = p; break; } }
      if (st) { let y = 0; for (let e = el; e && e !== st; e = e.offsetParent) y += e.offsetTop; t = st.getBoundingClientRect().top + y; top = t + sy; }
      const bottom = t + h;
      let tin = clamp((vh * 0.94 - t) / (vh * 0.30));
      if (s.stagN > 1) tin = clamp((tin - 0.08 * s.stagI) / (1 - 0.08 * (s.stagN - 1)));
      const tall = h > vh * 0.9;
      const tout = tall ? 0 : clamp((vh * 0.16 - bottom) / (vh * 0.16));
      const ein = ease(tin); const eout = ease(tout);
      checked += 1;
      const why = [];
      if (!st && Math.abs(s.top - top) > 1.5) why.push(`stale top ${s.top}→${top}`);
      if (Math.abs(s.in - ein) > 0.012) why.push(`in ${s.in} expected ${ein.toFixed(3)}`);
      if (Math.abs(s.out - eout) > 0.012) why.push(`out ${s.out} expected ${eout.toFixed(3)}`);
      const op = Number(getComputedStyle(el).opacity);
      if (['rise', 'fade', 'pop', 'slide'].includes(s.type)) { const m = s.in * (1 - s.out); if (Math.abs(op - m) > 0.03) why.push(`opacity ${op} vs ${m.toFixed(3)}`); }
      if (s.state === 'done') { const cs = getComputedStyle(el); if (cs.translate !== 'none' || cs.scale !== 'none' || cs.rotate !== 'none') why.push(`done but translate=${cs.translate} scale=${cs.scale}`); }
      if (why.length) bad.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0] || el.dataset.fx} [${s.type}] ${why.join('; ')}`);
    });
    return { checked, bad };
  },
  series: () => {
    const out = {};
    document.querySelectorAll('[data-fx]').forEach((el, i) => { const s = window.FX.read(el); if (s && !s.hidden && !['drift', 'spine'].includes(s.type)) out[i] = [s.in, s.out]; });
    return out;
  },
};
const raf2 = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
// after a jump the elements glide for at least ~0.4 s: wait until they have arrived before comparing with the formula
const jump = async (page, y) => {
  await page.evaluate((v) => window.scrollTo({ top: v, behavior: 'instant' }), y); await raf2(page);
  await page.waitForFunction(() => !window.FX.stats().moving, null, { timeout: 4000, polling: 'raf' }).catch(() => undefined);
  await raf2(page); await sleep(40);
};

(async () => {
  const browser = await launch();
  let failures = 0; const summary = [];
  for (const name of only) {
    for (const w of WIDTHS) {
      const { ctx, page, errors } = await open(browser, name, w, { settle: 1800 });
      const total = await page.evaluate(() => document.documentElement.scrollHeight);
      const vh = await page.evaluate(() => document.documentElement.clientHeight);
      const items = await page.evaluate(() => document.querySelectorAll('[data-fx]').length);
      const problems = [];
      // A: many positions, jumps and flings
      const positions = []; for (let y = 0; y <= total - vh; y += Math.round(vh * 0.37)) positions.push(y);
      positions.push(total - vh);
      [0.5, 0.13, 0.91, 0.27, 0.66, 0.02].forEach((f) => positions.push(Math.round((total - vh) * f)));
      for (const y of positions) {
        await jump(page, y);
        const r = await page.evaluate(inPage.measure);
        if (r.bad.length) problems.push(`A @${y}: ${r.bad.slice(0, 3).join(' | ')}${r.bad.length > 3 ? ` (+${r.bad.length - 3})` : ''}`);
      }
      // B: monotonic down then up
      const down = []; const stepPx = Math.max(60, Math.round(vh / 12));
      const step = async (y) => { await page.evaluate((v) => window.scrollTo({ top: v, behavior: 'instant' }), y); await raf2(page); };   // small steps: the shown numbers never overtake their targets, no need to wait for each
      for (let y = 0; y <= total - vh; y += stepPx) { await step(y); down.push(await page.evaluate(inPage.series)); }
      await jump(page, total - vh);                          // let the last steps arrive, or they would look like a reversal
      const up = [];
      for (let y = total - vh; y >= 0; y -= stepPx) { await step(y); up.push(await page.evaluate(inPage.series)); }
      const keys = Object.keys(down[0] || {});
      let mono = 0;
      keys.forEach((k) => {
        for (let i = 1; i < down.length; i += 1) { if (!down[i][k] || !down[i - 1][k]) continue; if (down[i][k][0] < down[i - 1][k][0] - 0.004 || down[i][k][1] < down[i - 1][k][1] - 0.004) { mono += 1; break; } }
        for (let i = 1; i < up.length; i += 1) { if (!up[i][k] || !up[i - 1][k]) continue; if (up[i][k][0] > up[i - 1][k][0] + 0.004 || up[i][k][1] > up[i - 1][k][1] + 0.004) { mono += 1; break; } }
      });
      if (mono) problems.push(`B: ${mono} elements moved against the scroll direction`);
      // C: resize and check again
      await page.setViewportSize({ width: Math.max(320, w - 90), height: Math.round(vh * 0.9) });
      await sleep(350); await raf2(page);
      const total2 = await page.evaluate(() => document.documentElement.scrollHeight);
      for (const f of [0.3, 0.7]) { await jump(page, Math.round(total2 * f)); const r = await page.evaluate(inPage.measure); if (r.bad.length) problems.push(`C resize @${f}: ${r.bad.slice(0, 2).join(' | ')}`); }
      await page.setViewportSize({ width: w, height: vh });
      await sleep(300);
      // F: cost with the CPU slowed 6x
      const cdp = await ctx.newCDPSession(page);
      await cdp.send('Emulation.setCPUThrottlingRate', { rate: 6 });
      let worst = 0;
      for (let y = 0; y <= total - vh; y += stepPx * 2) { await page.evaluate((v) => window.scrollTo({ top: v, behavior: 'instant' }), y); await raf2(page); const ms = await page.evaluate(() => window.FX.stats().frameMs); worst = Math.max(worst, ms); }
      await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
      if (worst > 10) problems.push(`F: frame script ${worst} ms with 6x CPU slowdown (budget 10 ms)`);
      if (errors.length) problems.push('console: ' + errors.slice(0, 2).join(' | '));
      await ctx.close();
      summary.push(`${problems.length ? '✗' : '✓'} ${name}@${w}: ${items} items, ${positions.length} positions, worst frame ${worst.toFixed(2)} ms (6x slow)`);
      problems.forEach((p) => { failures += 1; summary.push('    ' + p); });
    }
  }
  // D: reduce motion
  for (const name of ['home', 'post', 'moments']) {
    const { ctx, page } = await open(browser, name, 1280, { reduced: true, settle: 600 });
    const r = await page.evaluate(() => {
      const off = document.documentElement.classList.contains('fx-off'); const pending = document.documentElement.classList.contains('fx-pending');
      const bad = [...document.querySelectorAll('[data-fx]')].filter((el) => { const cs = getComputedStyle(el); return Number(cs.opacity) < 0.999 || (cs.translate !== 'none' && el.dataset.fx !== 'drift') || cs.scale !== 'none' || cs.clipPath !== 'none'; });
      return { off, pending, bad: bad.length, n: document.querySelectorAll('[data-fx]').length };
    });
    const ok = r.off && !r.pending && !r.bad;
    if (!ok) failures += 1;
    summary.push(`${ok ? '✓' : '✗'} reduce-motion ${name}: fx-off=${r.off} pending=${r.pending} not-plain=${r.bad}/${r.n}`);
    await ctx.close();
  }
  // E: no JavaScript
  for (const name of ['home', 'post']) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, javaScriptEnabled: false });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/${name}.html`, { waitUntil: 'load' });
    await sleep(300);
    const r = await page.evaluate(() => [...document.querySelectorAll('[data-fx]')].filter((el) => Number(getComputedStyle(el).opacity) < 0.999).length).catch(() => -1);
    const ok = r === 0;
    if (!ok) failures += 1;
    summary.push(`${ok ? '✓' : '✗'} no-JS ${name}: ${r} elements not fully visible`);
    await ctx.close();
  }
  console.log(summary.join('\n'));
  console.log(failures ? `\nFX AUDIT: ${failures} problem(s)` : '\nFX AUDIT: all clean');
  await browser.close();
  process.exitCode = failures ? 1 : 0;
})();
