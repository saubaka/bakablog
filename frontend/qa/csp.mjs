// Security headers in practice: no Content-Security-Policy violation on any page (the CSP is `script-src 'self'; style-src 'self'`),
// no request leaves the site (no fonts, scripts, analytics or images from other hosts), every page answers with the CSP header,
// and no runtime error. Also walks the interactive states (search overlay, drawer, lightbox) because they create DOM later.
import { BASE, PAGES, open, main, sleep } from './common.mjs'

await main(async (browser) => {
  let bad = 0
  const origin = new URL(BASE).origin
  for (const entry of PAGES) {
    for (const w of [390, 1280]) {
      const foreign = []
      const headers = {}
      const { ctx, page, errors: all } = await open(browser, entry, w, { settle: 300, before: async (p) => {
        await p.addInitScript(() => {
          window.__csp = []
          document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(`${e.violatedDirective} ${e.blockedURI || ''} ${(e.sample || '').slice(0, 60)}`))
        })
        p.on('request', (r) => { const u = new URL(r.url()); if (u.origin !== origin && u.protocol.startsWith('http')) foreign.push(r.url()) })
        p.on('response', (r) => { if (r.request().resourceType() === 'document' && !headers.csp) headers.csp = r.headers()['content-security-policy'] || '' })
      } })
      const errors = entry.name === '404' ? all.filter((e) => !/status of 404/.test(e)) : all
      // interactive states
      await page.keyboard.press('/'); await sleep(250); await page.keyboard.type('备份'); await sleep(500); await page.keyboard.press('Escape')
      if (w <= 480) { await page.click('.tabbar button:has-text("更多")').catch(() => undefined); await sleep(350); await page.keyboard.press('Escape') }
      const pic = page.locator('.fig img, .gallery__item img, .moment__imgs button').first()
      if (await pic.count()) { await pic.click().catch(() => undefined); await sleep(350); await page.keyboard.press('Escape') }
      await sleep(200)
      const violations = await page.evaluate(() => window.__csp)
      const problems = []
      if (violations.length) problems.push(`CSP violations: ${violations.slice(0, 2).join(' | ')}`)
      if (foreign.length) problems.push(`requests to other hosts: ${foreign.slice(0, 2).join(' | ')}`)
      if (!/script-src 'self'/.test(headers.csp || '') || !/style-src 'self'/.test(headers.csp || '')) problems.push(`weak or missing CSP header: ${headers.csp}`)
      if (errors.length) problems.push(`console: ${errors.slice(0, 2).join(' | ')}`)
      if (problems.length) { bad += 1; console.log(`✗ ${entry.name}@${w}: ${problems.join('; ')}`) }
      await ctx.close()
    }
  }
  console.log(bad ? `CSP: ${bad} problem(s)` : `CSP: all clean (${PAGES.length} pages x 2 widths: no violations, no third-party requests, CSP header present)`)
  return bad
})
