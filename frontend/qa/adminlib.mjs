// Helpers for the admin QA scripts. They run against a SEPARATE instance with its own data (never the dev site), e.g.
//   cd backend && BLOG_DATA_DIR=$PWD/data-qa flask --app app seed-demo --owner qa-admin --password … && BLOG_DATA_DIR=$PWD/data-qa gunicorn -b 127.0.0.1:5310 wsgi:app
// The credentials live in backend/data-qa/credentials.json (0600, git-ignored); nothing secret is printed or written anywhere else.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { BROWSER, heightFor, launch } from './common.mjs'

export const ADMIN_BASE = process.env.BB_ADMIN_URL || 'http://127.0.0.1:5310'
const credentials = () => JSON.parse(readFileSync(join(process.cwd(), '../backend/data-qa/credentials.json'), 'utf8'))
export { BROWSER, launch }

/** Open an admin page (signed in through the API, so the test does not depend on the login form). */
export async function openAdmin(browser, path, width = 1280, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: opts.height ?? heightFor(width) }, deviceScaleFactor: opts.scale ?? 1, hasTouch: width <= 480, reducedMotion: opts.reduced ? 'reduce' : 'no-preference', acceptDownloads: true })
  const errors = []
  if (opts.login !== false) {
    const c = credentials()
    let res
    for (let attempt = 1; ; attempt += 1) {       // gunicorn closes idle keep-alive connections after 2 s; a request that races with that gets ECONNRESET: try again
      try { res = await ctx.request.post(`${ADMIN_BASE}/api/admin/auth/login`, { data: { username: c.username, password: c.password }, headers: { Origin: ADMIN_BASE } }); break } catch (e) { if (attempt >= 3 || !/ECONNRESET|socket hang up/.test(String(e))) throw e }
    }
    if (!res.ok()) throw new Error(`QA login failed: ${res.status()}`)
  }
  const page = await ctx.newPage()
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errors.push(`${m.type()}: ${m.text()}`) })
  page.on('requestfailed', (r) => errors.push(`requestfailed: ${r.url()}`))
  await page.goto(`${ADMIN_BASE}/admin${path}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.adm-shell, .adm-auth', { timeout: 8000 })
  await page.waitForTimeout(opts.settle ?? 400)
  return { ctx, page, errors, admin: (p) => `${ADMIN_BASE}/admin${p}` }
}

export const ADMIN_PAGES = [
  ['dashboard', '/'], ['posts', '/posts'], ['post-edit', '/posts/1'], ['post-new', '/posts/new'], ['moments', '/moments'], ['pages', '/pages'], ['page-edit', '/pages/1'], ['media', '/media'],
  ['trash', '/trash'], ['categories', '/categories'], ['tags', '/tags'], ['series', '/series'], ['home', '/home'], ['navigation', '/navigation'], ['appearance', '/appearance'],
  ['seo', '/seo'], ['stats', '/stats'], ['account', '/account'], ['backups', '/backups'], ['logs', '/logs'], ['system', '/system'],
]
