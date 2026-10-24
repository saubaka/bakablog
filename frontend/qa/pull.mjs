// Turning the page by scrolling past its edge (src/public/pull.ts), with the real wheel and, in Chromium, real touch.
//  A  past the bottom: the page is pulled up like a rubber band, then thrown off, the next menu entry opens and rises from below, everything ends at rest
//  B  past the top: the same the other way round, to the previous entry
//  C  nothing above the first entry, nothing below the last
//  D  an ordinary scroll that merely ends at the edge (even with momentum) never turns the page
//  E  letting go early springs back, with at most a small overshoot
//  F  off while an overlay is open
//  G  touch (Chromium): a long drag turns the page, a short one springs back
import { BROWSER, byName, open, main, settled, sleep } from './common.mjs'

const PATH = { blog: '/blog', moments: '/moments', home: '/', page: '/about' }
const results = []
const record = (name, ok, detail = '') => { results.push(ok); console.log(`${ok ? '✓' : '✗'} ${name}${ok ? '' : ` — ${detail}`}`) }

const watcher = () => {
  window.__trace = []
  const stage = document.querySelector('.page-stage')
  const t0 = performance.now()
  const tick = () => {
    const cs = getComputedStyle(stage)
    const m = /(-?[\d.]+)px\)?\s*$/.exec(cs.translate === 'none' ? '' : cs.translate)
    window.__trace.push([Math.round(performance.now() - t0), m ? Number(m[1]) : 0, Number(cs.opacity), location.pathname, Math.round(scrollY)])
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}
const trace = (page) => page.evaluate(() => window.__trace.slice())
const toBottom = (page) => page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }))
const wheel = async (page, dy, times, gap = 24) => { for (let i = 0; i < times; i += 1) { await page.mouse.wheel(0, dy); await sleep(gap) } }
const current = (page) => page.evaluate(() => document.querySelector('.thread--side [aria-current="page"], .thread--bottom [aria-current="page"]')?.getAttribute('href'))

await main(async (browser) => {
  const view = async (name, width = 1280) => {
    const { ctx, page, errors } = await open(browser, byName(name), width, { settle: 1800 })
    await page.mouse.move(width / 2, 300)
    await page.evaluate(watcher)
    return { ctx, page, errors }
  }

  // A / B: the whole turn, both ways
  for (const [label, from, to, down] of [['past the bottom', 'blog', 'moments', true], ['past the top', 'moments', 'blog', false]]) {
    const { ctx, page, errors } = await view(from)
    if (down) await toBottom(page)
    await sleep(350)                                                        // a pause: what follows is a new push
    const vh = await page.evaluate(() => innerHeight)
    await wheel(page, down ? 90 : -90, 3)
    await page.waitForFunction((p) => location.pathname === p, PATH[to], { timeout: 4000 }).catch(() => undefined)
    await sleep(1700)
    const tr = await trace(page)
    const ys = tr.map((r) => r[1])
    const sign = down ? -1 : 1
    const firstThrow = tr.findIndex((r) => Math.abs(r[1]) > 121)
    const pushing = tr.slice(0, firstThrow < 0 ? tr.length : firstThrow).filter((r) => r[3] === PATH[from] && r[1] !== 0).map((r) => r[1])
    const thrown = ys.some((y) => y * sign >= vh * 0.9)
    const afterThrow = tr.slice(tr.findIndex((r) => r[1] * sign >= vh * 0.9))
    const risingFrom = afterThrow.map((r) => r[1]).find((y) => y * sign < 0)      // the first frame the new page is on the other side
    let worst = 0                                                                     // the largest step between two frames that can actually be seen
    for (let i = 1; i < tr.length; i += 1) if (tr[i][2] > 0.05 && tr[i - 1][2] > 0.05) worst = Math.max(worst, Math.abs(tr[i][1] - tr[i - 1][1]))
    const last = tr[tr.length - 1]
    record(`${label}: the page follows the push, held back like a rubber band`, pushing.length > 2 && pushing.every((y) => y * sign > 0 && y * sign < 121), JSON.stringify(pushing.slice(0, 8)))
    record(`${label}: it is thrown off the screen, then the next entry rises from the other side`, thrown && risingFrom !== undefined && risingFrom * sign < 0 && Math.abs(risingFrom) > vh * 0.15, `thrown=${thrown} rising from ${risingFrom}`)
    record(`${label}: no visible frame jumps (largest step ${worst.toFixed(0)}px of ${vh}px)`, worst < vh * 0.35, `${worst}`)
    record(`${label}: it ends on ${PATH[to]} at rest, at the top, with the menu on that entry`, last[3] === PATH[to] && last[1] === 0 && last[2] === 1 && last[4] === 0 && (await current(page)) === PATH[to], JSON.stringify(last))
    record(`${label}: no console errors`, errors.length === 0, errors.slice(0, 2).join(' | '))
    await ctx.close()
  }

  // C: the edges of the menu
  {
    const { ctx, page } = await view('home')
    await sleep(350)
    await wheel(page, -90, 5)
    await sleep(600)
    const tr = await trace(page)
    record('nothing above the first entry', tr.every((r) => r[1] === 0 && r[3] === '/'), JSON.stringify(tr.filter((r) => r[1] !== 0 || r[3] !== '/').slice(0, 3)))
    await ctx.close()
  }
  {
    const { ctx, page } = await view('page')
    await toBottom(page); await sleep(350)
    await wheel(page, 90, 5)
    await sleep(600)
    const tr = await trace(page)
    record('nothing below the last entry', tr.every((r) => r[1] === 0 && r[3] === PATH.page), JSON.stringify(tr.filter((r) => r[1] !== 0 || r[3] !== PATH.page).slice(0, 3)))
    await ctx.close()
  }

  // D: an ordinary scroll that ends at the edge does not turn the page
  {
    const { ctx, page } = await view('blog')
    await wheel(page, 160, 70, 14)                                          // one long burst with no pause: from the top, past the end
    await sleep(1200)
    const tr = await trace(page)
    const at = await page.evaluate(() => ({ y: scrollY, h: document.documentElement.scrollHeight - innerHeight }))
    record('a long scroll that reaches the end is just a scroll', at.y >= at.h - 2 && tr.every((r) => r[1] === 0 && r[3] === PATH.blog), JSON.stringify({ at, moved: tr.filter((r) => r[1] !== 0 || r[3] !== PATH.blog).slice(0, 2) }))
    // ... and the next push, after a pause, does turn it
    await sleep(300)
    await wheel(page, 90, 3)
    await page.waitForFunction(() => location.pathname === '/moments', null, { timeout: 4000 }).catch(() => undefined)
    record('the push after a pause turns the page', (await page.evaluate(() => location.pathname)) === PATH.moments)
    await ctx.close()
  }

  // E: let go early
  {
    const { ctx, page } = await view('blog')
    await toBottom(page); await sleep(350)
    await wheel(page, 100, 1)
    await sleep(1400)
    const tr = await trace(page)
    const ys = tr.map((r) => r[1])
    const lowest = Math.min(...ys)
    const overshoot = Math.max(...ys.slice(ys.findIndex((y) => y < -5) + 1))
    record('a short push springs back to rest', lowest < -20 && ys[ys.length - 1] === 0 && tr[tr.length - 1][3] === PATH.blog, `lowest ${lowest}, last ${ys[ys.length - 1]}`)
    record('... with at most a small overshoot', overshoot <= 14, `overshoot ${overshoot}px`)
    await ctx.close()
  }

  // F: not while an overlay is open
  {
    const { ctx, page } = await view('blog')
    await toBottom(page); await sleep(350)
    await page.keyboard.press('/')
    await page.waitForSelector('dialog[open]')
    await wheel(page, 90, 4)
    await sleep(500)
    const tr = await trace(page)
    record('off while the search box is open', tr.every((r) => r[1] === 0 && r[3] === PATH.blog), JSON.stringify(tr.filter((r) => r[1] !== 0).slice(0, 2)))
    await ctx.close()
  }

  // G: touch
  if (BROWSER === 'chromium') {
    for (const [label, travel, turns] of [['a long drag', 190, true], ['a short drag', 50, false]]) {
      const { ctx, page } = await (async () => {
        const o = await open(browser, byName('blog'), 390, { settle: 1800 })
        await o.page.evaluate(watcher)
        return o
      })()
      await toBottom(page); await sleep(350)
      const cdp = await ctx.newCDPSession(page)
      const send = (type, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x: 195, y }] })
      await send('touchStart', 640)
      for (let i = 1; i <= 12; i += 1) { await send('touchMove', 640 - (travel * i) / 12); await sleep(16) }
      const mid = await trace(page)
      const held = mid.map((r) => r[1]).filter((y) => y < 0)
      await send('touchEnd', 0)
      await sleep(1900)
      const tr = await trace(page)
      const last = tr[tr.length - 1]
      record(`touch, ${label}: the page follows the finger`, held.length > 3 && Math.min(...held) > -121, JSON.stringify(held.slice(-3)))
      record(`touch, ${label}: ${turns ? 'lets go and the next entry opens' : 'lets go and it springs back'}`, turns ? last[3] === PATH.moments && last[1] === 0 : last[3] === PATH.blog && last[1] === 0, JSON.stringify(last))
      await ctx.close()
    }
  } else console.log('- touch: skipped (Playwright cannot send real touch drags to WebKit)')
  return results.filter((ok) => !ok).length
})
