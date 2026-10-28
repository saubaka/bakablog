// The menu thread (layout/ThreadNav.vue, thread.ts) and the way it is entered, in the real browser, both engines:
//  A  a click on a bead: the pink thread goes down to the NEW bead and stops there (never a thread below it, nothing left of it when the heart is home), the heart is on its way at
//     once, and the page (whose data was fetched beforehand) changes without another request
//  B  the same on a slow line: the heart moves at once, the old page stays shown until the new one's data is in, nothing blank in between
//  C  a push past the end of the page: the page leaves at once, no request is made on the way (the neighbours were fetched when the browser was idle), the rest of the push
//     (trackpad momentum) does not scroll the page that has just arrived
//  D  the same push on a slow line: the page stays where the hand left it, alive, and leaves when the data is in
//  E  the neighbouring pages are asked for by themselves, once
//  F  the bottom bar of a phone does the same as the side thread
//  G  reduced motion: the heart does not travel
//  H  UP: scrolling up the page, pushing past its top to the previous entry, and a click on the previous bead from the middle of a page: the pink thread is reeled in smoothly, it
//     never loses a stretch in a single frame (it used to drop in one frame when the page changed)
import { open, main, sleep } from './common.mjs'

let bad = 0
const check = (name, ok, detail = '') => { if (!ok) bad += 1; console.log(`${ok ? '✓' : '✗'} ${name}${detail ? `: ${detail}` : ''}`) }

/** Samples every frame: the pink thread (start / end along the thread), the heart, the page, the address. */
const sampler = ([nav, axis]) => {
  window.__s = []
  const t0 = performance.now()
  window.__t0 = t0
  const tick = () => {
    const sew = document.querySelector(`${nav} .thread__sew`)?.getBoundingClientRect()
    const heart = document.querySelector(`${nav} .thread__heart`)?.getBoundingClientRect()
    const stage = document.querySelector('.page-stage')
    const m = /(-?[\d.]+)px\)?\s*$/.exec(stage ? (getComputedStyle(stage).translate === 'none' ? '' : getComputedStyle(stage).translate) : '')
    if (sew && heart) {
      const y = axis === 'y'
      window.__s.push({ t: performance.now() - t0, a: y ? sew.top : sew.left, b: y ? sew.bottom : sew.right, h: y ? heart.top + heart.height / 2 : heart.left + heart.width / 2, stage: m ? Number(m[1]) : 0, path: location.pathname, y: scrollY, shown: !!document.querySelector('main h1') })
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}
const mark = (page) => page.evaluate(() => { window.__mark = performance.now() - window.__t0 })
const samples = (page) => page.evaluate(() => ({ s: window.__s.slice(), mark: window.__mark }))
const bead = (page, nav, axis, href) => page.evaluate(({ nav, axis, href }) => {
  const r = document.querySelector(`${nav} a[href="${href}"] .thread__dot`)?.getBoundingClientRect()
  return r ? (axis === 'y' ? r.top + r.height / 2 : r.left + r.width / 2) : null
}, { nav, axis, href })
const toBottom = (page) => page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }))

const run = async (browser, { width = 1280, gate = 0, reduced = false, startPath = 'blog' }, body) => {
  let release = () => undefined
  const held = new Promise((resolve) => { release = resolve })
  const asked = []
  const { ctx, page } = await open(browser, startPath, width, {
    settle: 300, reduced,
    before: async (p) => {
      p.on('request', (r) => { if (r.url().includes('/api/moments')) asked.push(Date.now()) })
      if (gate) await p.route('**/api/moments**', async (route) => { await held; await route.continue() })
    },
  })
  try { await body({ page, release, asked }) } finally { await ctx.close() }
}

await main(async (browser) => {
  const SIDE = ['.thread--side', 'y']
  const BOTTOM = ['.thread--bottom', 'x']

  /* ---- A: a click on a bead ---- */
  await run(browser, {}, async ({ page, asked }) => {
    await sleep(3400)                                                               // the browser has been idle: the neighbours are fetched
    check('E: the neighbouring pages were asked for without anyone asking', asked.length >= 1, `${asked.length} request(s) for the next page's data`)
    await page.evaluate(sampler, SIDE)
    await toBottom(page)
    await sleep(1300)
    const newBead = await bead(page, SIDE[0], SIDE[1], '/moments')
    const before = asked.length
    await mark(page)
    await page.click(`${SIDE[0]} a[href="/moments"]`)
    await sleep(2400)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const start = after[0]?.h
    const moved = after.find((r) => Math.abs(r.h - start) >= 1)
    const changed = after.find((r) => r.path === '/moments')
    const lowest = Math.max(...after.map((r) => r.b))
    const last = after[after.length - 1]
    check('A: the heart is on its way within a moment of the click', !!moved && moved.t - m < 220, `${moved ? Math.round(moved.t - m) : 'never'} ms`)
    check('A: the pink thread goes down to the new bead and never below it', lowest <= newBead + 1.5, `lowest edge ${lowest.toFixed(1)}, the new bead ${newBead?.toFixed(1)}`)
    check('A: when the heart is home nothing of the thread is left', last.b - last.a < 1.5 && Math.abs(last.h - newBead) < 1.5, `thread ${(last.b - last.a).toFixed(1)}px, heart ${last.h.toFixed(1)} vs ${newBead?.toFixed(1)}`)
    check('A: the page changed without another request (its data was in)', !!changed && changed.t - m < 600 && asked.length === before, `${changed ? Math.round(changed.t - m) : 'never'} ms, ${asked.length - before} new request(s)`)
  })

  /* ---- B: a click on a slow line ---- */
  await run(browser, { gate: 1 }, async ({ page, release }) => {
    await page.evaluate(sampler, SIDE)
    await toBottom(page)
    await sleep(1200)
    await mark(page)
    setTimeout(release, 1000)
    await page.click(`${SIDE[0]} a[href="/moments"]`)
    await sleep(2800)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const moved = after.find((r) => Math.abs(r.h - after[0].h) >= 1)
    const changed = after.find((r) => r.path === '/moments')
    const waiting = after.filter((r) => r.t - m > 250 && r.t - m < 850)
    check('B: slow line: the heart is on its way at once', !!moved && moved.t - m < 220, `${moved ? Math.round(moved.t - m) : 'never'} ms`)
    check('B: slow line: the page waits for its data (the heart does not)', !!changed && changed.t - m > 800, `${changed ? Math.round(changed.t - m) : 'never'} ms`)
    check('B: slow line: the old page stays on the screen meanwhile (nothing blank)', waiting.length > 5 && waiting.every((r) => r.shown && r.path === '/blog'), `${waiting.length} frames`)
  })

  /* ---- C: a push past the end of the page ---- */
  await run(browser, {}, async ({ page, asked }) => {
    await sleep(3400)
    await page.evaluate(sampler, SIDE)
    await toBottom(page)
    await sleep(1300)
    await page.mouse.move(640, 400)
    const before = asked.length
    const newBead = await bead(page, SIDE[0], SIDE[1], '/moments')
    await mark(page)
    for (let i = 0; i < 3; i += 1) { await page.mouse.wheel(0, 70); await sleep(16) }          // far enough: the page turns
    // the trackpad goes on for a moment after the finger has lifted (a real wheel call is too slow to imitate that: events every 16 ms are made in the page)
    const tail = await page.evaluate(async () => {
      const res = []
      for (let i = 0; i < 60; i += 1) { res.push(!window.dispatchEvent(new WheelEvent('wheel', { deltaY: 30, bubbles: true, cancelable: true }))); await new Promise((r) => setTimeout(r, 16)) }
      return res
    })
    await sleep(2400)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const moved = after.find((r) => Math.abs(r.h - after[0].h) >= 1)
    const gone = after.find((r) => r.stage <= -300)
    const changed = after.find((r) => r.path === '/moments')
    const lowest = Math.max(...after.map((r) => r.b))
    const last = after[after.length - 1]
    check('C: the heart is on its way within a moment of the push', !!moved && moved.t - m < 260, `${moved ? Math.round(moved.t - m) : 'never'} ms`)
    check('C: the page is thrown off the screen without waiting for anything', !!gone && gone.t - m < 800, `${gone ? Math.round(gone.t - m) : 'never'} ms`)
    check('C: no request on the way (the next page was in)', asked.length === before, `${asked.length - before} new request(s)`)
    check('C: the pink thread goes down to the new bead and never below it', lowest <= newBead + 1.5, `lowest edge ${lowest.toFixed(1)}, the new bead ${newBead?.toFixed(1)}`)
    check('C: the tail of the push (events every 16 ms for a second) is swallowed, it does not carry on into the new page', tail.every(Boolean), `${tail.filter(Boolean).length} of ${tail.length} prevented`)
    check('C: the new page is open, at its top', !!changed && last.path === '/moments' && last.y <= 2, `${last.path}, scrolled ${Math.round(last.y)}px`)
  })

  /* ---- D: a push on a slow line ---- */
  await run(browser, { gate: 1 }, async ({ page, release }) => {
    await page.evaluate(sampler, SIDE)
    await toBottom(page)
    await sleep(1300)
    await page.mouse.move(640, 400)
    await mark(page)
    setTimeout(release, 1300)
    for (let i = 0; i < 14; i += 1) { await page.mouse.wheel(0, 70); await sleep(16) }
    await sleep(3000)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const moved = after.find((r) => Math.abs(r.h - after[0].h) >= 1)
    const holding = after.filter((r) => r.t - m > 600 && r.t - m < 1150)
    const changed = after.find((r) => r.path === '/moments')
    check('D: slow line: the heart is on its way at once', !!moved && moved.t - m < 260, `${moved ? Math.round(moved.t - m) : 'never'} ms`)
    check('D: slow line: the page waits where the hand left it, alive (not thrown into an empty screen)', holding.length > 5 && holding.every((r) => r.stage < -30 && r.stage > -160 && r.shown), `${holding.length} frames, stage ${Math.min(...holding.map((r) => r.stage)).toFixed(0)}..${Math.max(...holding.map((r) => r.stage)).toFixed(0)}`)
    check('D: slow line: and the new page opens when its data is in', !!changed && changed.t - m > 1200, `${changed ? Math.round(changed.t - m) : 'never'} ms`)
  })

  /* ---- F: the bottom bar of a phone ---- */
  await run(browser, { width: 390 }, async ({ page, asked }) => {
    await sleep(3400)
    await page.evaluate(sampler, BOTTOM)
    await toBottom(page)
    await sleep(1300)
    const newBead = await bead(page, BOTTOM[0], BOTTOM[1], '/moments')
    const before = asked.length
    await mark(page)
    await page.click(`${BOTTOM[0]} a[href="/moments"]`)
    await sleep(2400)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const moved = after.find((r) => Math.abs(r.h - after[0].h) >= 1)
    const lowest = Math.max(...after.map((r) => r.b))
    const last = after[after.length - 1]
    check('F: phone: the heart is on its way within a moment of the tap', !!moved && moved.t - m < 260, `${moved ? Math.round(moved.t - m) : 'never'} ms`)
    check('F: phone: the pink thread goes along to the new bead and never past it', lowest <= newBead + 1.5, `furthest edge ${lowest.toFixed(1)}, the new bead ${newBead?.toFixed(1)}`)
    check('F: phone: nothing of the thread is left when the heart is home', last.b - last.a < 1.5 && Math.abs(last.h - newBead) < 1.5, `${(last.b - last.a).toFixed(1)}px`)
    check('F: phone: no request on the way', asked.length === before, `${asked.length - before} new request(s)`)
  })

  /* ---- G: reduced motion ---- */
  await run(browser, { reduced: true }, async ({ page }) => {
    await sleep(2500)
    await page.evaluate(sampler, SIDE)
    await sleep(300)
    await mark(page)
    await page.click(`${SIDE[0]} a[href="/moments"]`)
    await sleep(1800)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const positions = new Set(after.map((r) => Math.round(r.h)))
    check('G: reduced motion: the heart does not travel (it is on one bead, then on the next)', positions.size <= 3, `${positions.size} positions`)
  })

  /* ---- H: going up ---- */
  const biggestStep = (rows, key) => rows.reduce((m, r, i) => (i ? Math.max(m, Math.abs(key(r) - key(rows[i - 1]))) : m), 0)
  const length = (r) => r.b - r.a
  await run(browser, { startPath: 'moments' }, async ({ page }) => {
    await sleep(3200)
    await page.evaluate(sampler, SIDE)
    await page.mouse.move(640, 400)
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
    await sleep(1300)
    await mark(page)
    for (let i = 0; i < 3; i += 1) { await page.mouse.wheel(0, -70); await sleep(16) }            // far enough: the previous entry
    await sleep(2600)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const changed = after.find((r) => r.path === '/blog')
    const step = biggestStep(after, length)
    check('H: pushing up past the top: the page goes to the previous entry', !!changed, changed ? `${Math.round(changed.t - m)} ms` : 'never')
    check('H: pushing up past the top: the pink thread is reeled in smoothly, no stretch of it vanishes in one frame', step < 12, `the biggest change in one frame: ${step.toFixed(1)}px of an 88px bead`)
    check('H: pushing up past the top: nothing of the thread is left at the new bead', length(after[after.length - 1]) < 1.5, `${length(after[after.length - 1]).toFixed(1)}px`)
  })
  await run(browser, { startPath: 'moments' }, async ({ page }) => {
    await sleep(3200)
    await page.evaluate(sampler, SIDE)
    await page.mouse.move(640, 400)
    await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }))
    await sleep(1500)
    await mark(page)
    for (let i = 0; i < 40; i += 1) { await page.mouse.wheel(0, -90); await sleep(16) }              // up through the whole page
    await sleep(1600)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const step = biggestStep(after.filter((r) => r.path === '/moments'), length)
    check('H: scrolling up through a page: the pink thread shrinks smoothly', step < 8, `the biggest change in one frame: ${step.toFixed(1)}px`)
  })
  await run(browser, { startPath: 'moments' }, async ({ page }) => {
    await sleep(3200)
    await page.evaluate(sampler, SIDE)
    await page.evaluate(() => window.scrollTo({ top: Math.round((document.documentElement.scrollHeight - innerHeight) * 0.55), behavior: 'instant' }))
    await sleep(1500)
    await mark(page)
    await page.click(`${SIDE[0]} a[href="/blog"]`)                                                  // the previous bead, from the middle of a page that has been read halfway
    await sleep(2400)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const step = biggestStep(after, length)
    check('H: a click on the previous bead from the middle of a page: smooth', step < 12, `the biggest change in one frame: ${step.toFixed(1)}px`)
    check('H: ... and nothing of the thread is left at the new bead', length(after[after.length - 1]) < 1.5, `${length(after[after.length - 1]).toFixed(1)}px`)
  })

  await run(browser, {}, async ({ page }) => {
    await sleep(3200)
    await page.evaluate(sampler, SIDE)
    await page.evaluate(() => window.scrollTo({ top: Math.round((document.documentElement.scrollHeight - innerHeight) * 0.4), behavior: 'instant' }))
    await sleep(1500)
    await mark(page)
    await page.click(`${SIDE[0]} a[href="/moments"]`)                                               // the next bead, from a page that has been read only partly
    await sleep(2400)
    const { s, mark: m } = await samples(page)
    const after = s.filter((r) => r.t >= m - 40)
    const step = biggestStep(after, length)
    const newBead = await bead(page, SIDE[0], SIDE[1], '/moments')
    check('H: a click on the next bead from a page read only partly: smooth', step < 12, `the biggest change in one frame: ${step.toFixed(1)}px`)
    check('H: ... never below the new bead, and nothing of the thread left there', Math.max(...after.map((r) => r.b)) <= newBead + 1.5 && length(after[after.length - 1]) < 1.5, `lowest ${Math.max(...after.map((r) => r.b)).toFixed(1)} vs ${newBead?.toFixed(1)}`)
  })

  console.log(bad ? `THREAD: ${bad} problem(s)` : 'THREAD: all clean')
  return bad
})
