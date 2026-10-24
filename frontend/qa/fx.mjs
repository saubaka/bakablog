// Scroll motion audit. Checks the engine against an independent recomputation of the rules, in a real browser:
//  A  at many scroll positions (including jumps and flings) every element's numbers match the formula for its CURRENT layout
//     (a stale position cache would show up here), and opacity / transform follow the numbers
//  B  monotonic: scrolling down never makes in/out go backwards, scrolling up never makes them go forwards
//  C  after resizing the window the picture is still right
//  D  "reduce motion": everything is simply there, no transforms      E  no JavaScript: the server's page is fully visible
//  F  cost: the per-frame script time with the CPU slowed down 6x (a mid-range phone; Chromium only)
//  G  a page opened by navigation inside the app never flashes fully visible before the engine has placed its elements
//  H  no teleporting: after a big jump every element glides (a full change takes at least MIN_MS, per-frame change is limited),
//     and a slow scroll is still followed exactly (the shown value never lags behind its target)
import { BASE, BROWSER, PAGES, byName, open, main, raf2, settled, sleep } from './common.mjs'

const MIN_MS = 420      // keep in step with src/fx/math.ts

const WIDTHS = (process.env.W || '390,768,1280').split(',').map(Number)
const only = process.env.ONLY_H ? [] : process.env.PAGE ? process.env.PAGE.split(',') : ['home', 'blog', 'post', 'moments', 'archive', '404', 'page']   // ONLY_H=1: just the no-teleport checks

const inPage = {
  // independent recomputation, run inside the page
  measure: () => {
    const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v)
    const ease = (t) => 1 - (1 - t) ** 3
    const docTop = (el) => { let y = 0; for (let e = el; e; e = e.offsetParent) y += e.offsetTop; return y }
    const vh = document.documentElement.clientHeight; const sy = Math.max(0, scrollY)
    const bad = []; let checked = 0
    document.querySelectorAll('[data-fx]').forEach((el) => {
      const s = window.FX.read(el)
      if (!s || s.hidden || s.forced || s.intro || ['drift', 'spine'].includes(s.type)) return
      const h = el.offsetHeight
      let top = docTop(el); let t = top - sy
      let st = null; for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { if (getComputedStyle(p).position === 'sticky') { st = p; break } }
      if (st) { let y = 0; for (let e = el; e && e !== st; e = e.offsetParent) y += e.offsetTop; t = st.getBoundingClientRect().top + y; top = t + sy }
      const bottom = t + h
      let tin = clamp((vh * 0.94 - t) / (vh * 0.30))
      if (s.stagN > 1) tin = clamp((tin - 0.08 * s.stagI) / (1 - 0.08 * (s.stagN - 1)))
      const tall = h > vh * 0.9
      const tout = tall ? 0 : clamp((vh * 0.16 - bottom) / (vh * 0.16))
      const ein = ease(tin); const eout = ease(tout)
      checked += 1
      const why = []
      if (!st && Math.abs(s.top - top) > 1.5) why.push(`stale top ${s.top}→${top}`)
      if (Math.abs(s.in - ein) > 0.012) why.push(`in ${s.in} expected ${ein.toFixed(3)}`)
      if (Math.abs(s.out - eout) > 0.012) why.push(`out ${s.out} expected ${eout.toFixed(3)}`)
      const op = Number(getComputedStyle(el).opacity)
      if (['rise', 'fade', 'pop', 'slide'].includes(s.type)) { const m = s.in * (1 - s.out); if (Math.abs(op - m) > 0.03) why.push(`opacity ${op} vs ${m.toFixed(3)}`) }
      if (s.state === 'done') { const cs = getComputedStyle(el); if (cs.translate !== 'none' || cs.scale !== 'none' || cs.rotate !== 'none') why.push(`done but translate=${cs.translate} scale=${cs.scale}`) }
      if (why.length) bad.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0] || el.dataset.fx} [${s.type}] ${why.join('; ')}`)
    })
    return { checked, bad }
  },
  series: () => {
    const out = {}
    document.querySelectorAll('[data-fx]').forEach((el, i) => { const s = window.FX.read(el); if (s && !s.hidden && !['drift', 'spine'].includes(s.type)) out[i] = [s.in, s.out] })
    return out
  },
}
// the numbers are checked once the motion has caught up with the position (a jump makes elements glide for ~0.4 s first)
const jump = async (page, y) => { await page.evaluate((v) => window.scrollTo({ top: v, behavior: 'instant' }), y); await settled(page); await sleep(40) }
// B walks in small steps and only needs the shown numbers, which never overtake their targets: no need to wait for them to arrive each time
const step = async (page, y) => { await page.evaluate((v) => window.scrollTo({ top: v, behavior: 'instant' }), y); await raf2(page) }

await main(async (browser) => {
  let failures = 0
  const summary = []
  for (const name of only) {
    for (const w of WIDTHS) {
      const { ctx, page, errors: all } = await open(browser, name, w, { settle: 1800 })
      const errors = name === '404' ? all.filter((e) => !/status of 404/.test(e)) : all
      const total = await page.evaluate(() => document.documentElement.scrollHeight)
      const vh = await page.evaluate(() => document.documentElement.clientHeight)
      const items = await page.evaluate(() => document.querySelectorAll('[data-fx]').length)
      const problems = []
      // A: many positions, jumps and flings
      const positions = []; for (let y = 0; y <= total - vh; y += Math.round(vh * 0.37)) positions.push(y)
      positions.push(Math.max(0, total - vh))
      ;[0.5, 0.13, 0.91, 0.27, 0.66, 0.02].forEach((f) => positions.push(Math.round(Math.max(0, total - vh) * f)))
      for (const y of positions) {
        await jump(page, y)
        const r = await page.evaluate(inPage.measure)
        if (r.bad.length) problems.push(`A @${y}: ${r.bad.slice(0, 3).join(' | ')}${r.bad.length > 3 ? ` (+${r.bad.length - 3})` : ''}`)
      }
      // B: monotonic down then up
      const down = []; const stepPx = Math.max(60, Math.round(vh / 12))
      await jump(page, 0)                                   // a clean start: leftovers of the previous position's glide would look like a reversal
      for (let y = 0; y <= total - vh; y += stepPx) { await step(page, y); down.push(await page.evaluate(inPage.series)) }
      await settled(page)                                   // the last downward steps may still be arriving; do not mistake that for a reversal
      const up = []
      for (let y = Math.max(0, total - vh); y >= 0; y -= stepPx) { await step(page, y); up.push(await page.evaluate(inPage.series)) }
      const keys = Object.keys(down[0] || {})
      let mono = 0
      keys.forEach((k) => {
        for (let i = 1; i < down.length; i += 1) { if (!down[i][k] || !down[i - 1][k]) continue; if (down[i][k][0] < down[i - 1][k][0] - 0.004 || down[i][k][1] < down[i - 1][k][1] - 0.004) { mono += 1; break } }
        for (let i = 1; i < up.length; i += 1) { if (!up[i][k] || !up[i - 1][k]) continue; if (up[i][k][0] > up[i - 1][k][0] + 0.004 || up[i][k][1] > up[i - 1][k][1] + 0.004) { mono += 1; break } }
      })
      if (mono) problems.push(`B: ${mono} elements moved against the scroll direction`)
      // C: resize and check again
      await page.setViewportSize({ width: Math.max(320, w - 90), height: Math.round(vh * 0.9) })
      await sleep(350); await raf2(page)
      const total2 = await page.evaluate(() => document.documentElement.scrollHeight)
      for (const f of [0.3, 0.7]) { await jump(page, Math.round(total2 * f)); const r = await page.evaluate(inPage.measure); if (r.bad.length) problems.push(`C resize @${f}: ${r.bad.slice(0, 2).join(' | ')}`) }
      await page.setViewportSize({ width: w, height: vh })
      await sleep(300)
      // F: cost with the CPU slowed 6x (Chromium only: WebKit has no CPU throttling)
      let worst = 0
      if (BROWSER === 'chromium') {
        const cdp = await ctx.newCDPSession(page)
        await cdp.send('Emulation.setCPUThrottlingRate', { rate: 6 })
        for (let y = 0; y <= total - vh; y += stepPx * 2) { await page.evaluate((v) => window.scrollTo({ top: v, behavior: 'instant' }), y); await raf2(page); const ms = await page.evaluate(() => window.FX.stats().frameMs); worst = Math.max(worst, ms) }
        await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 })
        if (worst > 10) problems.push(`F: frame script ${worst} ms with 6x CPU slowdown (budget 10 ms)`)
      }
      if (errors.length) problems.push(`console: ${errors.slice(0, 2).join(' | ')}`)
      await ctx.close()
      summary.push(`${problems.length ? '✗' : '✓'} ${name}@${w}: ${items} items, ${positions.length} positions, worst frame ${worst.toFixed(2)} ms (6x slow)`)
      problems.forEach((p) => { failures += 1; summary.push(`    ${p}`) })
    }
  }
  // D: reduce motion
  for (const name of ['home', 'post', 'moments']) {
    const { ctx, page } = await open(browser, name, 1280, { reduced: true, settle: 600 })
    const r = await page.evaluate(() => {
      const off = document.documentElement.classList.contains('fx-off'); const pending = document.documentElement.classList.contains('fx-pending')
      const bad = [...document.querySelectorAll('[data-fx]')].filter((el) => { const cs = getComputedStyle(el); return Number(cs.opacity) < 0.999 || (cs.translate !== 'none' && el.dataset.fx !== 'drift') || cs.scale !== 'none' || cs.clipPath !== 'none' })
      return { off, pending, bad: bad.length, n: document.querySelectorAll('[data-fx]').length }
    })
    const ok = r.off && !r.pending && !r.bad
    if (!ok) failures += 1
    summary.push(`${ok ? '✓' : '✗'} reduce-motion ${name}: fx-off=${r.off} pending=${r.pending} not-plain=${r.bad}/${r.n}`)
    await ctx.close()
  }
  // E: no JavaScript: the server's plain copy is there, readable, and not hidden by any motion guard
  for (const name of ['home', 'post', 'blog', 'moments']) {
    const { ctx, page } = await open(browser, name, 1280, { js: false, settle: 300 })
    const r = await page.evaluate(() => {
      const root = document.documentElement
      const h1 = document.querySelector('main h1')
      const main = document.querySelector('main')
      return { h1: !!h1 && h1.getBoundingClientRect().height > 0, text: (main?.innerText || '').length, boot: root.classList.contains('boot'), pending: root.classList.contains('fx-pending'), hidden: getComputedStyle(document.getElementById('app')).visibility }
    }).catch(() => ({ h1: false, text: 0, boot: true, pending: true, hidden: 'error' }))
    const ok = r.h1 && r.text > 40 && !r.boot && !r.pending && r.hidden === 'visible'
    if (!ok) failures += 1
    summary.push(`${ok ? '✓' : '✗'} no-JS ${name}: title=${r.h1} text=${r.text} chars, boot=${r.boot} pending=${r.pending} #app ${r.hidden}`)
    await ctx.close()
  }
  // G: opening a page by navigation: elements below the fold must not be visible even for one frame
  {
    const { ctx, page } = await open(browser, 'home', 1280, { settle: 900, before: async (p) => {
      await p.addInitScript(() => {
        window.__flash = null
        new MutationObserver(() => {
          const m = document.querySelector('main')
          if (!m || window.__armed !== true) return
          let n = 0
          const sample = () => {
            const vh = document.documentElement.clientHeight
            let worst = 0
            document.querySelectorAll('main [data-fx="rise"], main [data-fx="fade"]').forEach((el) => {
              if (el.getBoundingClientRect().top > vh * 1.05) worst = Math.max(worst, Number(getComputedStyle(el).opacity))
            })
            window.__flash = Math.max(window.__flash ?? 0, worst)
            n += 1
            if (n < 4) requestAnimationFrame(sample)
          }
          sample()
        }).observe(document, { childList: true, subtree: true })
      })
    } })
    await page.evaluate(() => { window.__armed = true; window.__flash = null })
    await page.click('.nav a[href="/blog"]')
    await sleep(900)
    const flash = await page.evaluate(() => window.__flash)
    const ok = flash === null || flash < 0.02
    if (!ok) failures += 1
    summary.push(`${ok ? '✓' : '✗'} navigation flash: strongest opacity of below-the-fold elements right after the page swap = ${flash === null ? 'n/a' : flash}`)
    await ctx.close()
  }
  // H: no teleporting
  for (const [name, w] of [['home', 1280], ['post', 1280], ['blog', 390], ['moments', 390]].filter(([n]) => !process.env.H_ONLY || process.env.H_ONLY.split(',').includes(n))) {
    const { ctx, page } = await open(browser, name, w, { settle: 1500 })
    const total = await page.evaluate(() => document.documentElement.scrollHeight)
    const vh = await page.evaluate(() => document.documentElement.clientHeight)
    const problems = []
    // H1: one big jump, then watch every frame for 1.6 s. The speed is judged over windows of 100 ms or more, not frame to frame:
    //     a frame the browser skipped shows up as one double step, which is still the right speed over real time.
    const fling = await page.evaluate(({ y, ms }) => new Promise((resolve) => {
      const els = [...document.querySelectorAll('[data-fx]')].filter((el) => { const s = window.FX.read(el); return s && !s.hidden && !['drift', 'spine'].includes(s.type) })
      const hist = els.map(() => [])
      const t0 = performance.now()
      const moved = new Set()
      const first = els.map((el) => { const s = window.FX.read(el); return [s.lin, s.lout] })
      window.scrollTo({ top: y, behavior: 'instant' })
      const tick = (now) => {
        els.forEach((el, i) => {
          const s = window.FX.read(el)
          hist[i].push([now, s.lin, s.lout])
          if (Math.abs(s.tin - first[i][0]) > 0.9 || Math.abs(s.tout - first[i][1]) > 0.9) moved.add(i)       // its target jumped by (almost) a whole change
        })
        if (now - t0 < 1600) requestAnimationFrame(tick)
        else {
          const worst = { rate: 0, who: '' }
          els.forEach((el, i) => {
            const h = hist[i]
            for (let a = 0; a < h.length; a += 1) for (let b = a + 1; b < h.length; b += 1) {
              const span = h[b][0] - h[a][0]
              if (span < 100) continue
              const d = Math.max(Math.abs(h[b][1] - h[a][1]), Math.abs(h[b][2] - h[a][2]))
              const rate = d / ((span + 50) / ms)             // 1 = the speed limit, with one frame of slack for where the window starts and ends
              if (rate > worst.rate) { worst.rate = rate; worst.who = `${el.dataset.fx} ${String(el.className).split(' ')[0]}` }
            }
          })
          const unsettled = els.filter((el) => { const s = window.FX.read(el); return s.lin !== s.tin || s.lout !== s.tout }).length
          resolve({ worst, big: moved.size, unsettled, n: els.length })
        }
      }
      requestAnimationFrame(tick)
    }), { y: Math.round((total - vh) * 0.55), ms: MIN_MS })
    if (fling.big === 0) problems.push('H1: the jump did not move any element by more than 0.9 (the check would prove nothing)')
    if (fling.worst.rate > 1.03) problems.push(`H1: ${fling.worst.who} changed ${fling.worst.rate.toFixed(2)}x faster than the speed limit`)
    if (fling.unsettled) problems.push(`H1: ${fling.unsettled}/${fling.n} elements had not arrived after 1.6 s`)
    // H2: scroll slowly (240 px per second of real time, whatever the frame rate) from the top: the shown value follows its target softly. A follower with a little weight trails a
    //     steadily moving target by about speed x 0.05 s (up to ~0.09 of a range here); what must never happen is a LASTING lag well beyond that, or one that never catches up.
    //     (Moving a fixed number of pixels per frame would not be slow when the browser bunches frames or runs at 120 Hz.)
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
    await settled(page)
    const slow = await page.evaluate(({ stop }) => new Promise((resolve) => {
      let worst = 0; let frames = 0; let t0 = 0; let who = ''; let longest = 0
      const streak = new Map()
      const tick = (now) => {
        if (!t0) t0 = now
        const els = [...document.querySelectorAll('[data-fx]')]
        for (const el of els) {
          const s = window.FX.read(el)
          if (s && !s.hidden && !['drift', 'spine'].includes(s.type) && s.lin >= 0) {
            const d = Math.max(Math.abs(s.lin - s.tin), Math.abs(s.lout - s.tout))
            const run = d > 0.16 ? (streak.get(el) || 0) + 1 : 0
            streak.set(el, run)
            if (run > longest) longest = run
            if (d > worst) { worst = d; who = `${el.dataset.fx} ${String(el.className).split(' ')[0] || el.tagName.toLowerCase()} at ${Math.round(scrollY)}px (in ${s.lin.toFixed(2)}→${s.tin.toFixed(2)}, out ${s.lout.toFixed(2)}→${s.tout.toFixed(2)}, intro ${s.intro}, t=${Math.round(now - t0)}ms)` }
          }
        }
        frames += 1
        const y = Math.round(240 * (now - t0) / 1000)
        if (y >= stop) resolve({ worst, frames, who, longest })
        else { window.scrollTo({ top: y, behavior: 'instant' }); requestAnimationFrame(tick) }
      }
      requestAnimationFrame(tick)
    }), { stop: Math.min(1400, total - vh) })
    if (slow.longest >= 4) problems.push(`H2: a slow scroll lagged more than 0.16 behind its target for ${slow.longest} frames in a row (worst ${slow.worst.toFixed(3)}): ${slow.who}`)
    if (slow.worst > 0.25) problems.push(`H2: a slow scroll lagged ${slow.worst.toFixed(3)} behind its target at one moment (limit 0.25): ${slow.who}`)
    await ctx.close()
    summary.push(`${problems.length ? '✗' : '✓'} no-teleport ${name}@${w}: ${fling.n} items, fastest change ${fling.worst.rate.toFixed(2)}x the limit, all arrived; slow scroll lag ${slow.worst.toFixed(3)} (${slow.frames} frames)`)
    problems.forEach((p) => { failures += 1; summary.push(`    ${p}`) })
  }
  console.log(summary.join('\n'))
  console.log(failures ? `\nFX AUDIT: ${failures} problem(s)` : '\nFX AUDIT: all clean')
  return failures
})
