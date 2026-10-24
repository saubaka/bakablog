// Shared helpers for the QA scripts.
const { chromium } = require('playwright');
const BASE = process.env.BB_URL || 'http://127.0.0.1:5200';
const PAGES = ['index', 'home', 'blog', 'post', 'moments', 'archive', '404', 'components', 'fx-lab'];
const launch = () => chromium.launch({ executablePath: process.env.CHROME });
const heightFor = (w) => (w <= 480 ? 844 : w <= 800 ? 1024 : 900);
async function open(browser, name, width, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: heightFor(width) }, deviceScaleFactor: 1, hasTouch: width <= 480, reducedMotion: opts.reduced ? 'reduce' : 'no-preference' });
  const page = await ctx.newPage();
  if (opts.before) await opts.before(page);
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errors.push(m.type() + ': ' + m.text()); });
  page.on('requestfailed', (r) => errors.push('requestfailed: ' + r.url()));
  await page.goto(`${BASE}/${name}.html${opts.query ? '?' + opts.query : ''}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(opts.settle ?? 700);
  return { ctx, page, errors };
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
module.exports = { BASE, PAGES, launch, open, heightFor, sleep };
