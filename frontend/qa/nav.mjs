// The menu's heart rides along the thread once per navigation: from the old bead to the new one, never stopping in between,
// with at most one small overshoot-and-settle at the end (the spring); and the first paint of a page puts it straight on the current bead
// (no glide in from somewhere else). Checked for the vertical thread on the left edge (desktop) and the horizontal one in the bottom bar (phone).
import { open, main, sleep } from './common.mjs'

const VARIANTS = [
  { name: 'side thread', width: 1280, nav: '.thread--side', axis: 'y', cases: [['/', '/blog'], ['/blog', '/moments'], ['/moments', '/archive'], ['/archive', '/'], ['/', '/moments']] },
  { name: 'bottom bar', width: 390, nav: '.thread--bottom', axis: 'x', cases: [['/', '/blog'], ['/blog', '/moments'], ['/moments', '/'], ['/', '/moments']] },
]

await main(async (browser) => {
  let bad = 0
  for (const v of VARIANTS) {
    for (const [from, to] of v.cases) {
      const { ctx, page } = await open(browser, { path: from }, v.width, { settle: 1200, before: async (p) => {
        await p.addInitScript(({ nav, axis }) => {
          window.__heart = []
          const t0 = performance.now()
          const tick = () => {
            const h = document.querySelector(`${nav} .thread__heart`)
            if (h) { const r = h.getBoundingClientRect(); const c = axis === 'y' ? r.top + r.height / 2 : r.left + r.width / 2; window.__heart.push([Math.round(performance.now() - t0), Math.round(c * 10) / 10, Number(getComputedStyle(h).opacity)]) }
            requestAnimationFrame(tick)
          }
          requestAnimationFrame(tick)
        }, { nav: v.nav, axis: v.axis })
      } })
      const center = (path) => page.evaluate(({ nav, axis, h }) => {
        const a = document.querySelector(`${nav} a[href="${h}"]`); if (!a) return null
        const dot = a.querySelector('.thread__dot').getBoundingClientRect()
        return axis === 'y' ? dot.top + dot.height / 2 : dot.left + dot.width / 2
      }, { nav: v.nav, axis: v.axis, h: path })
      const startC = await center(from)
      const first = (await page.evaluate(() => window.__heart)).filter((x) => x[2] > 0.05).map((x) => x[1])
      const firstOk = first.length > 0 && first.every((x) => Math.abs(x - startC) < 3)
      const currentOk = await page.evaluate(({ nav, h }) => document.querySelector(`${nav} [aria-current="page"]`)?.getAttribute('href') === h, { nav: v.nav, h: from })
      await page.evaluate(() => { window.__heart.length = 0 })
      await page.click(`${v.nav} a[href="${to}"]`)
      await sleep(1500)
      const endC = await center(to)
      const s = (await page.evaluate(() => window.__heart)).filter((x) => x[2] > 0.05).map((x) => x[1])
      const dir = Math.sign(endC - startC)
      const dist = Math.abs(endC - startC)
      let turns = 0; let overshoot = 0; let last = 0                     // turns = changes of direction (forward, then back after the overshoot, is one)
      for (let i = 1; i < s.length; i += 1) {
        const d = (s[i] - s[i - 1]) * dir
        const sign = d > 0.4 ? 1 : d < -0.4 ? -1 : 0
        if (sign !== 0) { if (last !== 0 && sign !== last) turns += 1; last = sign }
        overshoot = Math.max(overshoot, (s[i] - endC) * dir)
      }
      const startsAtOld = Math.abs(s[0] - startC) < 6
      const endsAtNew = Math.abs(s[s.length - 1] - endC) < 1.5
      const moves = new Set(s.map((x) => Math.round(x))).size
      const nowCurrent = await page.evaluate(({ nav, h }) => document.querySelector(`${nav} [aria-current="page"]`)?.getAttribute('href') === h, { nav: v.nav, h: to })
      const ok = firstOk && currentOk && nowCurrent && startsAtOld && endsAtNew && moves > 5 && turns <= 2 && overshoot < dist * 0.25
      if (!ok) bad += 1
      console.log(`${ok ? '✓' : '✗'} ${v.name} ${from} → ${to}: first paint on its bead=${firstOk}, aria-current ${currentOk}/${nowCurrent}, ${s[0]?.toFixed(0)} → ${s[s.length - 1]?.toFixed(0)} (bead ${startC.toFixed(0)} → ${endC.toFixed(0)}), ${moves} positions, ${turns} direction changes, overshoot ${overshoot.toFixed(1)}px of ${dist.toFixed(0)}px`)
      await ctx.close()
    }
  }
  return bad
})
