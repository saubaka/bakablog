// Screenshots of prototype pages at given widths. Usage: node qa/shots.js <outDir> <pages comma> <widths comma> [full|view] [extraQuery]
const { chromium } = require('playwright');
const path = require('path');
const [out, pages = 'home', widths = '1280', mode = 'full', extra = 'motion=off'] = process.argv.slice(2);
const BASE = process.env.BB_URL || 'http://127.0.0.1:5200';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  for (const w of widths.split(',').map(Number)) {
    const h = w <= 480 ? 844 : w <= 800 ? 1024 : 900;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: w <= 480 });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errors.push(m.text()); });
    for (const name of pages.split(',')) {
      await page.goto(`${BASE}/${name}.html?${extra}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(600);
      const file = path.join(out, `${name}-${w}.png`);
      await page.screenshot({ path: file, fullPage: mode === 'full' });
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      console.log(`${name}@${w}: ${file} overflow=${over}${errors.length ? ' ERRORS ' + JSON.stringify(errors.slice(0, 4)) : ''}`);
      errors.length = 0;
    }
    await ctx.close();
  }
  await browser.close();
})();
