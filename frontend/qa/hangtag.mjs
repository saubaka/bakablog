// The hanging progress tag (layout/ProgressTag.vue): it hangs at the height of the menu's topmost pin, rides down as the page is read, swings when the page is scrolled
// fast and settles, drops in when a page has arrived, is absent on a page that does not scroll, never leaves the thread or goes under the bottom bar, shows only
// while scrolling on small screens, and click takes you to the top. Checked in the real browser, both engines.
import { open, main, sleep } from './common.mjs'

let bad = 0
const check = (name, ok, detail = '') => { if (!ok) bad += 1; console.log(`${ok ? '✓' : '✗'} ${name}${detail ? `: ${detail}` : ''}`) }

const read = (page) => page.evaluate(() => {
  const mid = (el) => { const r = el?.getBoundingClientRect(); return r && r.height > 0 ? r.top + r.height / 2 : null }
  const root = document.querySelector('.ptag')
  const line = document.querySelector('.ptag__line')?.getBoundingClientRect()
  const pill = document.querySelector('.ptag__pill')?.getBoundingClientRect()
  const bar = document.querySelector('.thread--bottom')?.getBoundingClientRect()
  return {
    away: root?.hasAttribute('data-away') ?? true,
    text: document.querySelector('.ptag__pill b')?.textContent ?? '',
    ringY: mid(document.querySelector('.ptag__ring')),
    pinY: mid(document.querySelector('.thread--side .thread__pin')),
    lineTop: line?.top ?? null,
    lineBottom: line ? line.top + line.height : null,
    pillBottom: pill?.bottom ?? null,
    pillRight: pill?.right ?? null,
    barTop: bar && bar.height > 0 ? bar.top : null,
    angle: parseFloat(document.querySelector('.ptag__swing')?.style.rotate || '0'),
    scrollY: window.scrollY,
    room: document.documentElement.scrollHeight - window.innerHeight,
    vw: window.innerWidth,
    vh: window.innerHeight,
  }
})
const percentOf = (t) => parseInt(t, 10)

await main(async (browser) => {
  /* ---- a wide screen, a long page ---- */
  {
    const { ctx, page } = await open(browser, 'post', 1440, { settle: 2200 })
    let s = await read(page)
    check('desktop: the tag has dropped in and hangs on the thread', !s.away && s.text === '0%', `${s.text} away=${s.away}`)
    check('desktop: the thread starts at the height of the menu pin', s.pinY !== null && Math.abs(s.lineTop - s.pinY) <= 1.5, `thread ${s.lineTop?.toFixed(1)} vs pin ${s.pinY?.toFixed(1)}`)
    check('desktop: at the top the ring sits on the start of the thread', Math.abs(s.ringY - s.lineTop) <= 1.5, `ring ${s.ringY?.toFixed(1)} vs ${s.lineTop?.toFixed(1)}`)

    await page.evaluate(() => window.scrollTo({ top: (document.documentElement.scrollHeight - innerHeight) / 2, behavior: 'instant' }))
    await sleep(1800)
    s = await read(page)
    const half = (s.ringY - s.lineTop) / (s.lineBottom - s.lineTop)
    check('desktop: halfway down the page the tag is halfway down the thread', Math.abs(half - 0.5) < 0.04 && Math.abs(percentOf(s.text) - 50) <= 3, `${s.text}, ${(half * 100).toFixed(1)}% of the thread`)
    check('desktop: the swing has died down when scrolling stopped', Math.abs(s.angle) < 0.2, `${s.angle}°`)

    // a hard jump to the end: the tag swings and overshoots a little, never leaves the thread, then settles
    await page.evaluate(() => { window.__tag = []; const t0 = performance.now(); const tick = () => { const r = document.querySelector('.ptag__ring')?.getBoundingClientRect(); const sw = parseFloat(document.querySelector('.ptag__swing')?.style.rotate || '0'); const pr = document.querySelector('.ptag__pill')?.getBoundingClientRect(); window.__tag.push([performance.now() - t0, r ? r.top + r.height / 2 : 0, sw, pr ? pr.right : 0]); if (performance.now() - t0 < 2600) requestAnimationFrame(tick) }; requestAnimationFrame(tick); window.scrollTo({ top: 1e6, behavior: 'instant' }) })
    await sleep(2900)
    const trace = await page.evaluate(() => window.__tag)
    s = await read(page)
    const maxAngle = Math.max(...trace.map((t) => Math.abs(t[2])))
    const maxY = Math.max(...trace.map((t) => t[1]))
    check('desktop: a hard jump makes the tag swing, within reason', maxAngle > 1 && maxAngle < 35, `largest swing ${maxAngle.toFixed(1)}°`)
    const maxRight = Math.max(...trace.map((t) => t[3]))
    check('desktop: ... and the swinging tag stays inside the screen', maxRight <= s.vw, `furthest right ${maxRight.toFixed(1)} / ${s.vw}`)
    check('desktop: ... never leaves the thread', maxY <= s.lineBottom + 1, `lowest ${maxY.toFixed(1)} vs end of the thread ${s.lineBottom.toFixed(1)}`)
    check('desktop: ... and has settled at the end showing 100%', s.text === '100%' && Math.abs(s.angle) < 0.2 && Math.abs(s.ringY - s.lineBottom) <= 1.5, `${s.text}, ${s.angle}°, ring ${s.ringY?.toFixed(1)} vs ${s.lineBottom?.toFixed(1)}`)
    check('desktop: at the end the tag is still on the screen', s.pillBottom <= s.vh && s.pillRight <= s.vw, `pill bottom ${s.pillBottom?.toFixed(1)} / ${s.vh}`)

    await page.click('.ptag__tag')
    await sleep(2400)
    s = await read(page)
    check('desktop: a click on the tag goes back to the top', s.scrollY === 0 && s.text === '0%', `scrollY ${s.scrollY}, ${s.text}`)
    await ctx.close()
  }

  /* ---- a page that does not scroll has no tag ---- */
  {
    const { ctx, page } = await open(browser, '404', 1440, { settle: 2000 })
    const s = await read(page)
    check('a page that barely scrolls has no tag', s.room <= 120 && s.away, `room ${s.room}px, away=${s.away}`)
    await ctx.close()
  }

  /* ---- a phone: only while scrolling, above the bottom bar ---- */
  {
    const { ctx, page } = await open(browser, 'post', 390, { settle: 600 })
    await page.evaluate(() => window.scrollBy({ top: 300, behavior: 'instant' }))
    await sleep(700)
    let s = await read(page)
    check('phone: the tag hangs out while the page is scrolled', !s.away, `away=${s.away}`)
    check('phone: it is smaller than the page margin allows it to be wide', s.pillRight <= s.vw + 1, `pill right ${s.pillRight?.toFixed(1)} / ${s.vw}`)
    await sleep(2600)
    s = await read(page)
    check('phone: it goes away again when scrolling stops', s.away, `away=${s.away}`)
    await page.evaluate(() => window.scrollTo({ top: 1e6, behavior: 'instant' }))
    await sleep(900)
    s = await read(page)
    check('phone: at the end it hangs above the bottom bar', !s.away && s.barTop !== null && s.pillBottom <= s.barTop, `pill bottom ${s.pillBottom?.toFixed(1)}, bar top ${s.barTop?.toFixed(1)}`)
    await ctx.close()
  }

  /* ---- reduced motion: no swing, no bounce, but it still follows ---- */
  {
    const { ctx, page } = await open(browser, 'post', 1440, { settle: 1200, reduced: true })
    await page.evaluate(() => window.scrollTo({ top: 1e6, behavior: 'instant' }))
    await sleep(500)
    const s = await read(page)
    check('reduced motion: the tag follows at once and does not swing', s.text === '100%' && s.angle === 0, `${s.text}, ${s.angle}°`)
    await ctx.close()
  }

  console.log(bad ? `HANGTAG: ${bad} problem(s)` : 'HANGTAG: all clean')
  return bad
})
