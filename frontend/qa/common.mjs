// Shared helpers for the QA scripts (run against a RUNNING server: `make -C backend serve` after `npm run build`).
//   BB_URL    where the site is            (default http://127.0.0.1:5300)
//   BROWSER   chromium | webkit            (default chromium; `npm run qa` runs both)
//   CHROME    path of a Chromium binary    (default: the Chromium that Playwright already cached)
import { existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { chromium, webkit } from 'playwright'

export const BASE = process.env.BB_URL || 'http://127.0.0.1:5300'
export const BROWSER = process.env.BROWSER || 'chromium'

/** Every kind of public page the site has. `slug` values come from the demo content (`flask --app app seed-demo`). */
export const PAGES = [
  { name: 'home', path: '/' },
  { name: 'blog', path: '/blog' },
  { name: 'post', path: '/blog/sqlite-backup' },
  { name: 'category', path: '/category/dai-ma' },
  { name: 'series', path: '/series/ba-bo-ke-zuo-cheng-zi-ji-xi-huan-de-yang-zi' },
  { name: 'moments', path: '/moments' },
  { name: 'moment', path: '/moments/1' },
  { name: 'archive', path: '/archive' },
  { name: 'page', path: '/about' },
  { name: 'search', path: '/search?q=SQLite' },
  { name: '404', path: '/no-such-page' },
]
export const byName = (n) => PAGES.find((p) => p.name === n)
export const WIDTHS = [320, 390, 768, 1024, 1280, 1440]
export const heightFor = (w) => (w <= 480 ? 844 : w <= 800 ? 1024 : 900)
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const cachedChromium = () => {
  const p = join(homedir(), 'Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')
  return existsSync(p) ? p : undefined
}
export const launch = (which = BROWSER) =>
  which === 'webkit' ? webkit.launch() : chromium.launch({ executablePath: process.env.CHROME || cachedChromium() })

/** Open a page the way a visitor does and wait until the app has drawn it. Collects console errors and failed requests. */
export async function open(browser, target, width, opts = {}) {
  const ctx = await browser.newContext({
    viewport: { width, height: opts.height ?? heightFor(width) },
    deviceScaleFactor: opts.scale ?? 1,
    hasTouch: width <= 480,
    reducedMotion: opts.reduced ? 'reduce' : 'no-preference',
    javaScriptEnabled: opts.js !== false,
  })
  const page = await ctx.newPage()
  if (opts.before) await opts.before(page)
  const errors = []
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errors.push(`${m.type()}: ${m.text()}`) })
  page.on('requestfailed', (r) => errors.push(`requestfailed: ${r.url()}`))
  const entry = typeof target === 'string' ? (byName(target) ?? { path: target }) : target
  const sep = entry.path.includes('?') ? '&' : '?'
  const url = `${BASE}${entry.path}${opts.query ? sep + opts.query : ''}`
  await page.goto(url, { waitUntil: 'networkidle' })
  if (opts.js !== false) await page.waitForFunction(() => !document.documentElement.classList.contains('boot'), null, { timeout: 8000 }).catch(() => undefined)
  await page.waitForTimeout(opts.settle ?? 700)
  return { ctx, page, errors }
}

export const raf2 = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))))

/** Wait until the scroll motion has caught up with the scroll position (elements glide for at least ~0.4 s after a jump). */
export async function settled(page, ms = 4000) {
  await raf2(page)
  await page.waitForFunction(() => !window.FX || !window.FX.stats().moving, null, { timeout: ms, polling: 'raf' }).catch(() => undefined)
  await raf2(page)
}

/** The CLI wrapper of every audit: prints, sets the exit code, never leaves a browser running. */
export async function main(fn) {
  const browser = await launch()
  let code = 0
  try { code = (await fn(browser)) ? 1 : 0 } catch (e) { console.error(e); code = 1 } finally { await browser.close() }
  process.exit(code)
}
