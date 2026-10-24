// Screenshots of interactive states: search overlay, lightbox, sheets, filters, list view, design panel.
const { launch, BASE, sleep, heightFor } = require('./common');
const out = process.argv[2];
(async () => {
  const browser = await launch();
  const mk = async (w) => { const ctx = await browser.newContext({ viewport: { width: w, height: heightFor(w) }, hasTouch: w <= 480 }); const page = await ctx.newPage(); const errs = []; page.on('pageerror', (e) => errs.push(e.message)); page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errs.push(m.text()); }); return { ctx, page, errs }; };
  // desktop
  let { ctx, page, errs } = await mk(1280);
  await page.goto(`${BASE}/blog.html?motion=off`, { waitUntil: 'networkidle' }); await sleep(500);
  await page.keyboard.press('/'); await sleep(300); await page.keyboard.type('备份'); await sleep(300);
  await page.screenshot({ path: `${out}/i-search-1280.png` });
  await page.keyboard.press('Escape'); await sleep(200);
  await page.click('[data-cat="代码"]'); await sleep(300);
  await page.click('[data-view="list"]'); await sleep(400);
  await page.screenshot({ path: `${out}/i-bloglist-1280.png` });
  await page.goto(`${BASE}/moments.html?motion=off`, { waitUntil: 'networkidle' }); await sleep(400);
  await page.click('.moment__imgs.n3 button >> nth=0'); await sleep(500);
  await page.screenshot({ path: `${out}/i-lightbox-1280.png` });
  await page.keyboard.press('Escape');
  await page.goto(`${BASE}/home.html?motion=off`, { waitUntil: 'networkidle' }); await sleep(400);
  await page.click('.dpanel__btn'); await sleep(300);
  await page.screenshot({ path: `${out}/i-panel-1280.png`, clip: { x: 0, y: 500, width: 520, height: 400 } });
  if (errs.length) console.log('desktop errors', errs.slice(0, 3));
  await ctx.close();
  // phone
  ({ ctx, page, errs } = await mk(390));
  await page.goto(`${BASE}/post.html?motion=off`, { waitUntil: 'networkidle' }); await sleep(500);
  await page.evaluate(() => window.scrollTo({ top: 1400, behavior: 'instant' })); await sleep(300);
  await page.click('.toc-fab'); await sleep(600);
  await page.screenshot({ path: `${out}/i-tocsheet-390.png` });
  await page.keyboard.press('Escape'); await sleep(300);
  await page.click('.tabbar [data-open-sheet]'); await sleep(600);
  await page.screenshot({ path: `${out}/i-more-390.png` });
  await page.keyboard.press('Escape'); await sleep(300);
  await page.goto(`${BASE}/moments.html?motion=off`, { waitUntil: 'networkidle' }); await sleep(400);
  await page.evaluate(() => window.scrollTo({ top: 300, behavior: 'instant' })); await sleep(300);
  await page.screenshot({ path: `${out}/i-moments-390.png` });
  if (errs.length) console.log('phone errors', errs.slice(0, 3));
  await ctx.close();
  console.log('interaction screenshots written to', out);
  await browser.close();
})();
