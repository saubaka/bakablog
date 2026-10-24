// Frame times while scrolling, in either engine (no trace needed): scrolls with a trackpad-like stream of wheel steps and reports the distribution of the
// time between frames. Run it before and after a change to the scroll path. Usage: BROWSER=webkit PAGE=post node qa/framerate.mjs
import { BROWSER, byName, open, main, sleep } from './common.mjs'

const NAMES = (process.env.PAGE || 'post,blog,moments,home').split(',')
const WIDTH = Number(process.env.WIDTH || 1280)
const SECONDS = Number(process.env.SECONDS || 4)

await main(async (browser) => {
  for (const name of NAMES) {
    const { ctx, page } = await open(browser, byName(name), WIDTH, { settle: 2400 })
    await page.mouse.move(WIDTH / 2, 300)
    await page.evaluate(() => {
      window.__f = []
      let last = performance.now()
      const tick = (now) => { window.__f.push(now - last); last = now; requestAnimationFrame(tick) }
      requestAnimationFrame(tick)
    })
    const t0 = Date.now()
    while (Date.now() - t0 < SECONDS * 1000) {
      const k = (Date.now() - t0) / (SECONDS * 1000)
      await page.mouse.wheel(0, Math.round(4 + Math.sin(Math.PI * k) * 38))
      await sleep(8)
    }
    await sleep(400)
    const f = (await page.evaluate(() => window.__f.slice(3))).sort((a, b) => a - b)
    const q = (p) => f[Math.min(f.length - 1, Math.floor(f.length * p))]
    const avg = f.reduce((a, b) => a + b, 0) / f.length
    console.log(`${BROWSER} ${name.padEnd(8)} frames ${String(f.length).padStart(4)}  avg ${avg.toFixed(1)} ms  p50 ${q(0.5).toFixed(1)}  p95 ${q(0.95).toFixed(1)}  p99 ${q(0.99).toFixed(1)}  worst ${f[f.length - 1].toFixed(1)}  late(>20ms) ${f.filter((x) => x > 20).length}  dropped(>34ms) ${f.filter((x) => x > 34).length}`)
    await ctx.close()
  }
})
