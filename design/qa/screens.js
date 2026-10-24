// Viewport-sized screenshots at scroll offsets (what a visitor actually sees, including fixed elements).
// Usage: node qa/screens.js <outDir> <page> <width> <offsets comma|auto> [query]
const { chromium } = require('playwright');
const path = require('path');
const [out, name = 'home', width = '1280', offsetsArg = 'auto', query = 'motion=off'] = process.argv.slice(2);
const BASE = process.env.BB_URL || 'http://127.0.0.1:5200';
(async () => {
  const w = Number(width);
  const h = w <= 480 ? 844 : w <= 800 ? 1024 : 900;
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: w <= 480 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errors.push(m.text()); });
  await page.goto(`${BASE}/${name}.html?${query}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(700);
  const total = await page.evaluate(() => document.documentElement.scrollHeight);
  let offsets = offsetsArg === 'auto' ? [] : offsetsArg.split(',').map(Number);
  if (offsetsArg === 'auto') for (let y = 0; y < total; y += h - 60) offsets.push(y);
  let i = 0;
  for (const y of offsets) {
    await page.evaluate((yy) => window.scrollTo({ top: yy, behavior: 'instant' }), y);
    await page.waitForTimeout(450);
    const file = path.join(out, `${name}-${w}-${String(i).padStart(2, '0')}.png`);
    await page.screenshot({ path: file });
    i += 1;
  }
  console.log(`${name}@${w}: total=${total} shots=${offsets.length} first=${path.join(out, `${name}-${w}-00.png`)}${errors.length ? ' ERRORS ' + JSON.stringify(errors.slice(0, 4)) : ''}`);
  await browser.close();
})();
