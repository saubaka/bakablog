// Loading speed as a phone on a slow connection sees it (Chromium only: it needs the DevTools protocol).
//   network  1.6 Mbit/s down, 750 kbit/s up, 150 ms round trip   (the "Slow 4G" profile Lighthouse uses for mobile)
//   CPU      4x slower than this machine
//   cache    cold (cache disabled), text compressed the way nginx will do it (a tiny gzip proxy stands in front of the server)
// Budgets (docs/PLAN.md section 0): LCP <= 2.0 s, CLS <= 0.05. Reported too: FCP, requests, bytes on the wire, long tasks (total blocking time).
// Lighthouse itself is not used (it needs a Chrome the project does not ship); these are the same metrics from the same browser APIs.
import http from 'node:http'
import { gzipSync } from 'node:zlib'
import { BASE, launch, PAGES } from './common.mjs'

const BUDGET = { lcp: 2000, cls: 0.05 }
const RUNS = Number(process.env.PERF_RUNS || 3)
const target = new URL(BASE)

/* gzip proxy: what nginx's `gzip on` does for text */
const COMPRESSIBLE = /^(text\/|application\/(javascript|json|xml|manifest\+json)|image\/svg)/
const proxy = http.createServer((req, res) => {
  const up = http.request({ host: target.hostname, port: target.port, path: req.url, method: req.method, headers: { ...req.headers, 'accept-encoding': 'identity' } }, (r) => {
    const chunks = []
    r.on('data', (c) => chunks.push(c))
    r.on('end', () => {
      let body = Buffer.concat(chunks)
      const headers = { ...r.headers }
      if (COMPRESSIBLE.test(String(headers['content-type'] || '')) && body.length > 512 && /gzip/.test(String(req.headers['accept-encoding'] || ''))) {
        body = gzipSync(body, { level: 6 })
        headers['content-encoding'] = 'gzip'
        headers.vary = 'Accept-Encoding'
      }
      headers['content-length'] = body.length
      res.writeHead(r.statusCode, headers)
      res.end(body)
    })
  })
  up.on('error', () => { res.writeHead(502); res.end() })
  req.pipe(up)
})
await new Promise((ok) => proxy.listen(0, '127.0.0.1', ok))
const proxied = `http://127.0.0.1:${proxy.address().port}`

const median = (a) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)]
const browser = await launch()
let bad = 0
const rows = []
try {
  for (const entry of PAGES.filter((p) => ['home', 'blog', 'post', 'moments', 'archive', 'page'].includes(p.name))) {
    const runs = []
    for (let i = 0; i < RUNS; i += 1) {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true })
      const page = await ctx.newPage()
      const cdp = await ctx.newCDPSession(page)
      await cdp.send('Network.enable')
      await cdp.send('Network.setCacheDisabled', { cacheDisabled: true })
      await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 })
      await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 })
      let wire = 0
      let requests = 0
      cdp.on('Network.loadingFinished', (e) => { wire += e.encodedDataLength; requests += 1 })
      await page.addInitScript(() => {
        window.__m = { lcp: 0, cls: 0, fcp: 0, tbt: 0 }
        new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__m.lcp = e.startTime }).observe({ type: 'largest-contentful-paint', buffered: true })
        new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__m.cls += e.value }).observe({ type: 'layout-shift', buffered: true })
        new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') window.__m.fcp = e.startTime }).observe({ type: 'paint', buffered: true })
        new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__m.tbt += Math.max(0, e.duration - 50) }).observe({ type: 'longtask', buffered: true })
      })
      await page.goto(`${proxied}${entry.path}`, { waitUntil: 'load', timeout: 60000 })
      await page.waitForTimeout(1500)
      await page.mouse.click(5, 5).catch(() => undefined)      // LCP is final after the first input
      const m = await page.evaluate(() => window.__m)
      runs.push({ ...m, wire, requests })
      await ctx.close()
    }
    const r = { name: entry.name, lcp: median(runs.map((x) => x.lcp)), cls: median(runs.map((x) => x.cls)), fcp: median(runs.map((x) => x.fcp)), tbt: median(runs.map((x) => x.tbt)), wire: median(runs.map((x) => x.wire)), requests: median(runs.map((x) => x.requests)) }
    rows.push(r)
    const ok = r.lcp <= BUDGET.lcp && r.cls <= BUDGET.cls
    if (!ok) bad += 1
    console.log(`${ok ? '✓' : '✗'} ${r.name.padEnd(8)} LCP ${(r.lcp / 1000).toFixed(2)} s · FCP ${(r.fcp / 1000).toFixed(2)} s · CLS ${r.cls.toFixed(3)} · blocking ${Math.round(r.tbt)} ms · ${r.requests} requests · ${(r.wire / 1024).toFixed(0)} KB on the wire`)
  }
} finally { await browser.close(); proxy.close() }
console.log(bad ? `PERF: ${bad} page(s) over budget (LCP <= ${BUDGET.lcp / 1000} s, CLS <= ${BUDGET.cls}; median of ${RUNS} cold loads, Slow 4G, 4x CPU)` : `PERF: all pages within budget (LCP <= ${BUDGET.lcp / 1000} s, CLS <= ${BUDGET.cls}; median of ${RUNS} cold loads, Slow 4G, 4x CPU)`)
process.exit(bad ? 1 : 0)
