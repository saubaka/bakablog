// The sliding indicator moves once per navigation: from where the previous page left it to the new item, never back and forth.
const { launch, BASE, sleep, heightFor } = require('./common');
const CASES = [['home', 'blog'], ['blog', 'moments'], ['moments', 'archive'], ['archive', 'home'], ['home', 'moments']];
const HREF = { home: 'home.html', blog: 'blog.html', moments: 'moments.html', archive: 'archive.html' };
(async () => {
  const browser = await launch(); let bad = 0;
  for (const [from, to] of CASES) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: heightFor(1280) } });
    const page = await ctx.newPage();
    await page.addInitScript(() => {
      window.__ind = [];
      const t0 = performance.now();
      const tick = () => {
        const i = document.querySelector('.nav__ind');
        if (i) { const cs = getComputedStyle(i); const r = i.getBoundingClientRect(); window.__ind.push([Math.round(performance.now() - t0), Math.round(r.left * 10) / 10, Number(cs.opacity)]); }
        if (performance.now() - t0 < 1400) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    await page.goto(`${BASE}/${HREF[from]}?motion=off`, { waitUntil: 'networkidle' });
    await sleep(700);
    const startLeft = await page.evaluate(() => document.querySelector('.nav__ind').getBoundingClientRect().left);
    await Promise.all([page.waitForLoadState('domcontentloaded'), page.click(`.nav a[href="${HREF[to]}"]`)]);
    await page.waitForLoadState('networkidle'); await sleep(900);
    const endLeft = await page.evaluate(() => document.querySelector('.nav__ind').getBoundingClientRect().left);
    const s = (await page.evaluate(() => window.__ind)).filter((x) => x[2] > 0.05);
    const lefts = s.map((x) => x[1]);
    const dir = Math.sign(endLeft - startLeft);
    let reversals = 0;
    for (let i = 1; i < lefts.length; i += 1) if ((lefts[i] - lefts[i - 1]) * dir < -0.6) reversals += 1;
    const first = lefts[0];
    const startsAtOld = Math.abs(first - startLeft) < 3;
    const endsAtNew = Math.abs(lefts[lefts.length - 1] - endLeft) < 1.5;
    const moves = new Set(lefts.map((x) => Math.round(x))).size;
    const ok = reversals === 0 && startsAtOld && endsAtNew && moves > 3;
    if (!ok) bad += 1;
    console.log(`${ok ? '✓' : '✗'} ${from} → ${to}: starts ${first.toFixed(0)}px (old item ${startLeft.toFixed(0)}), ends ${lefts[lefts.length - 1].toFixed(0)}px (new item ${endLeft.toFixed(0)}), ${moves} distinct positions, ${reversals} reversals`);
    await ctx.close();
  }
  await browser.close(); process.exitCode = bad ? 1 : 0;
})();
