// Where does the time go while scrolling? Scrolls an article (or any page) the way a trackpad does and reports, from the browser's own trace:
//   frames (how many, how many were late), the main-thread time of each kind of work per frame (script, style recalculation, layout, paint, composite),
//   and how many style recalculations / layouts a frame needed (more than one is a read-after-write in somebody's code).
// Usage: PAGE=post WIDTH=1280 CPU=4 [QUERY=motion=off] node qa/profile.mjs
import { BROWSER, byName, open, main, sleep } from './common.mjs'

const NAME = process.env.PAGE || 'post'
const WIDTH = Number(process.env.WIDTH || 1280)
const CPU = Number(process.env.CPU || 4)
const SECONDS = Number(process.env.SECONDS || 4)

await main(async (browser) => {
  if (BROWSER !== 'chromium') { console.log('profile.mjs needs Chromium (it reads the browser trace)'); return 0 }
  const { ctx, page } = await open(browser, byName(NAME), WIDTH, { settle: 2200, ...(process.env.QUERY ? { query: process.env.QUERY } : {}) })
  const cdp = await ctx.newCDPSession(page)
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: CPU })
  await page.mouse.move(WIDTH / 2, 300)
  await page.evaluate(() => {
    window.__frames = []
    let last = performance.now()
    const tick = (now) => { window.__frames.push(now - last); last = now; requestAnimationFrame(tick) }
    requestAnimationFrame(tick)
  })
  const events = []
  cdp.on('Tracing.dataCollected', (e) => events.push(...e.value))
  await cdp.send('Tracing.start', { categories: 'devtools.timeline,disabled-by-default-devtools.timeline', transferMode: 'ReportEvents' })
  // a trackpad: a small wheel step every frame, with a gentle start and stop
  const t0 = Date.now()
  let n = 0
  while (Date.now() - t0 < SECONDS * 1000) {
    const k = (Date.now() - t0) / (SECONDS * 1000)
    const speed = Math.sin(Math.PI * k)                        // 0 → 1 → 0
    await page.mouse.wheel(0, Math.round(4 + speed * 38))
    n += 1
    await sleep(8)
  }
  await sleep(600)
  const done = new Promise((resolve) => cdp.once('Tracing.tracingComplete', resolve))
  await cdp.send('Tracing.end')
  await done
  const frames = await page.evaluate(() => window.__frames.slice(2))
  const sum = {}; const count = {}
  for (const e of events) {
    if (e.ph !== 'X' || !e.dur) continue
    const name = e.name
    if (!['UpdateLayoutTree', 'Layout', 'Paint', 'PrePaint', 'Layerize', 'Commit', 'FunctionCall', 'EvaluateScript', 'v8.callFunction', 'FireAnimationFrame', 'RunMicrotasks', 'HitTest', 'IntersectionObserverController::computeIntersections'].includes(name)) continue
    sum[name] = (sum[name] || 0) + e.dur / 1000
    count[name] = (count[name] || 0) + 1
  }
  const late = frames.filter((f) => f > 20).length
  const over = frames.filter((f) => f > 34).length
  frames.sort((a, b) => a - b)
  const avg = frames.reduce((a, b) => a + b, 0) / frames.length
  console.log(`${NAME}@${WIDTH}, CPU ${CPU}x, ${SECONDS}s, ${n} wheel steps`)
  console.log(`frames ${frames.length}: average ${avg.toFixed(1)} ms, p95 ${frames[Math.floor(frames.length * 0.95)].toFixed(1)} ms, worst ${frames[frames.length - 1].toFixed(1)} ms, > 20 ms: ${late}, > 34 ms (a dropped frame or more): ${over}`)
  for (const k of Object.keys(sum).sort((a, b) => sum[b] - sum[a])) console.log(`  ${k.padEnd(28)} ${sum[k].toFixed(0).padStart(6)} ms total, ${String(count[k]).padStart(5)} times, ${(sum[k] / frames.length).toFixed(2)} ms per frame, ${(count[k] / frames.length).toFixed(1)} per frame`)
  await ctx.close()
  return 0
})
