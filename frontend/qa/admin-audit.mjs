// The design rules and the keyboard rules, checked on every admin page (and on the layers that float over it):
//   lines    one line colour, flat cards, no square "cards", no grey halos        (the public site's audit, same scan)
//   contrast text contrast on every theme preset (4.5:1, large text 3:1)
//   focus    every keyboard stop shows the one ring; <main> and the page title never do
//   nav      the sidebar pill glides once, straight to the new item, then the page changes; the first paint puts it on the item
import { ADMIN_PAGES, launch, openAdmin } from './adminlib.mjs'
import { scanContrast, scanLines } from './scans.mjs'

const FLOATING = '.adm-drawer, .adm-menu__list, .adm-palette, .adm-modal, .adm-confirm, .toast, dialog, .scrim, .adm-tabbar, .searchbox, .sheet'
const THEMES = ['default', 'sky', 'sakura', 'fog']
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const browser = await launch()
let bad = 0
const say = (ok, text) => { if (!ok) bad += 1; console.log(`${ok ? '✓' : '✗'} ${text}`) }

try {
  /* ---- lines ---- */
  {
    const all = { shadow: new Map(), border: new Map(), square: new Map() }
    for (const [name, path] of ADMIN_PAGES) {
      for (const w of [1280, 390]) {
        const { ctx, page } = await openAdmin(browser, path, w, { settle: 300, reduced: true })
        const states = ['page', 'palette']
        for (const state of states) {
          if (state === 'palette') { await page.keyboard.press(process.platform === 'darwin' ? 'Meta+k' : 'Control+k'); await sleep(250) }
          const r = await page.evaluate(scanLines, FLOATING)
          for (const k of Object.keys(all)) for (const line of r[k]) { const m = all[k].get(line) || new Set(); m.add(`${name}@${w}`); all[k].set(line, m) }
        }
        await ctx.close()
      }
    }
    for (const [k, title] of [['shadow', 'drop shadow on a non-floating element'], ['border', 'border colour that is not --line / --rose-line'], ['square', 'square "card"']]) {
      say(all[k].size === 0, `lines: ${title}: ${all[k].size}`)
      for (const [line, where] of all[k]) console.log(`    ${line}  [${[...where].slice(0, 3).join(', ')}]`)
    }
  }

  /* ---- contrast, every theme ---- */
  for (const theme of THEMES) {
    const agg = new Map(); let total = 0
    for (const [name, path] of ADMIN_PAGES) {
      const { ctx, page } = await openAdmin(browser, path, 1280, { settle: 250, reduced: true })
      await page.evaluate((th) => { const d = document.documentElement; if (th === 'default') d.removeAttribute('data-theme'); else d.setAttribute('data-theme', th) }, theme)
      await page.waitForTimeout(120)
      const r = await page.evaluate(scanContrast); total += r.n
      r.bad.forEach(([k, v]) => { const a = agg.get(k) || { c: 0, ex: v.ex, pages: new Set() }; a.c += v.c; a.pages.add(name); agg.set(k, a) })
      await ctx.close()
    }
    say(agg.size === 0, `contrast, theme ${theme}: ${total} text elements, ${agg.size} failing colour pairs`)
    for (const [k, v] of agg) console.log(`    ${v.c}× ${k}  e.g. ${v.ex}  [${[...v.pages].slice(0, 4).join(', ')}]`)
  }

  /* ---- focus ---- */
  {
    let stops = 0
    for (const [name, path] of ADMIN_PAGES) {
      const { ctx, page } = await openAdmin(browser, path, 1280, { settle: 400, reduced: true })
      const seen = new Set()
      for (let i = 0; i < 70; i += 1) {
        await page.keyboard.press('Tab')
        await sleep(25)
        const r = await page.evaluate(() => {
          const e = document.activeElement
          if (!e || e === document.body) return null
          const label = `${e.tagName.toLowerCase()}${e.id ? `#${e.id}` : ''}.${String(e.className).split(' ')[0]}`
          const cs = getComputedStyle(e)
          return { label, key: label + (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 12), style: cs.outlineStyle, width: cs.outlineWidth, color: cs.outlineColor, shadow: cs.boxShadow, tag: e.tagName }
        })
        if (!r) continue
        if (seen.has(r.key) && i > 3) break
        seen.add(r.key); stops += 1
        // a visible ring is the 2px outline (public rule), or — on the controls that draw their own focus halo — a ring-coloured box-shadow
        const ring = (r.style === 'solid' && r.width === '2px' && r.color === 'rgb(94, 142, 200)') || /rgb\(94, 142, 200\)|rgb\(230, 241, 252\)/.test(r.shadow)
        if (!ring) say(false, `focus ${name}: ${r.label} outline=${r.style} ${r.width} ${r.color} shadow=${r.shadow.slice(0, 40)}`)
      }
      const m = await page.evaluate(() => {
        const out = []
        for (const el of [document.querySelector('main'), document.querySelector('main h1')]) {
          if (!el) continue
          if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1')
          el.focus()
          const cs = getComputedStyle(el)
          out.push({ tag: el.tagName, style: cs.outlineStyle, shadow: cs.boxShadow })
        }
        return out
      })
      for (const x of m) if (x.style !== 'none' || x.shadow !== 'none') say(false, `focus ${name}: <${x.tag}> draws a ring`)
      await ctx.close()
    }
    say(true, `focus: ${stops} keyboard stops on ${ADMIN_PAGES.length} pages checked, <main> and titles ring-free`)
  }

  /* ---- the sidebar pill ---- */
  {
    const CASES = [['/', '/posts'], ['/posts', '/media'], ['/media', '/system'], ['/system', '/'], ['/', '/seo']]
    for (const [from, to] of CASES) {
      const { ctx, page } = await openAdmin(browser, from, 1280, { settle: 700, reduced: false })
      await page.evaluate(() => {
        window.__pill = []
        const t0 = performance.now()
        const tick = () => {
          const p = document.querySelector('.adm-nav__pill')
          // the pill's own offset inside the nav (a long sidebar scrolls when a link near the bottom is clicked; that moves every rect on screen, not the pill)
          if (p) { const cs = getComputedStyle(p); window.__pill.push([Math.round(performance.now() - t0), Math.round(parseFloat(cs.translate.split(' ')[1] || '0') * 10) / 10, Number(cs.opacity), location.pathname]) }
          requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      })
      const topOf = (h) => page.evaluate((href) => document.querySelector(`.adm-nav a[href="${href}"]`).getBoundingClientRect().top - document.querySelector('.adm-nav').getBoundingClientRect().top, h)
      const href = (p) => `/admin${p === '/' ? '/' : p}`
      const startTop = await topOf(href(from))
      await sleep(200)
      const first = await page.evaluate(() => window.__pill.filter((x) => x[2] > 0.05).map((x) => x[1]))
      const firstOk = first.length > 0 && first.every((y) => Math.abs(y - startTop) < 3)
      await page.evaluate(() => { window.__pill.length = 0 })
      await page.locator(`.adm-nav a[href="${href(to)}"]`).scrollIntoViewIfNeeded()
      await sleep(150)
      await page.evaluate(() => { window.__pill.length = 0 })
      await page.click(`.adm-nav a[href="${href(to)}"]`)
      await sleep(1300)
      const endTop = await topOf(href(to))
      const s = (await page.evaluate(() => window.__pill)).filter((x) => x[2] > 0.05)
      const ys = s.map((x) => x[1])
      const dir = Math.sign(endTop - startTop)
      let reversals = 0
      for (let i = 1; i < ys.length; i += 1) if ((ys[i] - ys[i - 1]) * dir < -0.6) reversals += 1
      const startsAtOld = Math.abs(ys[0] - startTop) < 3
      const endsAtNew = Math.abs(ys[ys.length - 1] - endTop) < 1.5
      const moves = new Set(ys.map((y) => Math.round(y))).size
      say(firstOk && reversals === 0 && startsAtOld && endsAtNew && moves > 3,
        `nav ${from} → ${to}: first paint on item=${firstOk}, starts ${ys[0]?.toFixed(0)} (old ${startTop.toFixed(0)}), ends ${ys[ys.length - 1]?.toFixed(0)} (new ${endTop.toFixed(0)}), ${moves} positions, ${reversals} reversals`)
      await ctx.close()
    }
  }
} finally { await browser.close() }
console.log(bad ? `ADMIN AUDIT: ${bad} problem(s)` : 'ADMIN AUDIT: lines, contrast (4 themes), focus and the sidebar pill are all clean')
process.exit(bad ? 1 : 0)
