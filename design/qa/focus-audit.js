// Keyboard: every stop shows the one focus ring (2px --ring), the page container (<main>) never does, and a focused
// element that was waiting below the fold is fully visible (not left transparent by the scroll motion).
const { PAGES, launch, open, sleep } = require('./common');
(async () => {
  const browser = await launch(); let bad = 0; let stops = 0;
  for (const name of PAGES) {
    const { ctx, page } = await open(browser, name, 1280, { settle: 900 });
    const seen = new Set();
    for (let i = 0; i < 90; i += 1) {
      await page.keyboard.press('Tab');
      await sleep(40);
      const r = await page.evaluate(() => {
        const e = document.activeElement; if (!e || e === document.body) return null;
        const label = `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}.${String(e.className).split(' ')[0]}`;
        let target = e;
        if (e.matches('input[type=checkbox], input[type=radio]')) target = e.nextElementSibling || e;   // the visible box next to a hidden input
        const cs = getComputedStyle(target);
        const fx = e.closest('[data-fx]');
        return { label, key: label + e.textContent.trim().slice(0, 12), style: cs.outlineStyle, width: cs.outlineWidth, color: cs.outlineColor, visible: e.matches(':focus-visible'), opacity: fx ? Number(getComputedStyle(fx).opacity) : 1, fxState: fx ? fx.getAttribute('data-fx-state') : null };
      });
      if (!r) continue;
      if (seen.has(r.key) && i > 3) break;   // the cycle closed
      seen.add(r.key); stops += 1;
      const ring = r.style === 'solid' && r.width === '2px' && r.color === 'rgb(94, 142, 200)';
      if (!ring || r.opacity < 0.99) { bad += 1; console.log(`✗ ${name}: ${r.label} outline=${r.style} ${r.width} ${r.color} opacity=${r.opacity} state=${r.fxState}`); }
    }
    // main must never draw a ring, even right after keyboard use (which is what makes a script focus() match :focus-visible)
    const m = await page.evaluate(() => { const main = document.querySelector('main'); main.focus(); const cs = getComputedStyle(main); return { style: cs.outlineStyle, shadow: cs.boxShadow, focused: document.activeElement === main, visible: main.matches(':focus-visible') }; });
    const mainOk = m.style === 'none' && m.shadow === 'none';
    if (!mainOk) { bad += 1; console.log(`✗ ${name}: <main> draws a ring (outline ${m.style}, shadow ${m.shadow})`); }
    await ctx.close();
  }
  // self-test of the audit: put the old bug back and make sure it is caught
  const { ctx, page } = await open(browser, 'home', 1280, { settle: 500 });
  await page.keyboard.press('Tab');
  await page.addStyleTag({ content: 'main:focus-visible { outline: 2px solid #5e8ec8 !important; }' });
  const caught = await page.evaluate(() => { const main = document.querySelector('main'); main.focus(); return getComputedStyle(main).outlineStyle !== 'none'; });
  console.log(caught ? '✓ self-test: a ring on <main> would be detected' : '✗ self-test: the audit would NOT notice a ring on <main>');
  if (!caught) bad += 1;
  await ctx.close();
  console.log(bad ? `FOCUS AUDIT: ${bad} problem(s), ${stops} stops` : `FOCUS AUDIT: all clean (${stops} keyboard stops on ${PAGES.length} pages, <main> ring-free)`);
  await browser.close(); process.exitCode = bad ? 1 : 0;
})();
