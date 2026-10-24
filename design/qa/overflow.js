// No horizontal overflow at any width, and no console errors, on every page.
const { PAGES, launch, open } = require('./common');
(async () => {
  const browser = await launch();
  let bad = 0;
  for (const name of PAGES) {
    for (const w of [320, 390, 768, 1024, 1280, 1440]) {
      const { ctx, page, errors } = await open(browser, name, w, { query: 'motion=off', settle: 300 });
      const r = await page.evaluate(() => {
        const de = document.documentElement; const over = de.scrollWidth - de.clientWidth;
        const wide = [...document.querySelectorAll('body *')].filter((e) => { const b = e.getBoundingClientRect(); return b.width > 0 && (b.right > de.clientWidth + 1) && getComputedStyle(e).position !== 'fixed' && !e.closest('.table-wrap, .tabs, .month-chips, .searchbox__list, .sheet, pre, .dpanel, .tabbar, .lightbox, .icon-grid'); }).slice(0, 3).map((e) => e.tagName + '.' + String(e.className).split(' ')[0] + ' ' + Math.round(e.getBoundingClientRect().right));
        return { over, wide };
      });
      const problem = r.over > 0 || errors.length;
      if (problem) { bad += 1; console.log(`✗ ${name}@${w}: overflow ${r.over}px ${r.wide.join(' | ')} ${errors.slice(0, 3).join(' | ')}`); }
      await ctx.close();
    }
  }
  console.log(bad ? `${bad} page/width combinations have problems` : 'overflow + console: all pages and widths clean');
  await browser.close();
  process.exitCode = bad ? 1 : 0;
})();
