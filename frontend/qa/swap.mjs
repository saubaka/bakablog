// Motion that is not tied to scrolling, in the real browser, both engines (public/components SwapPane · Fold · Dropdown, public/slider.ts, SearchDialog, Lightbox):
//  A  the drop-down: the site's own (no <select>), opens with a motion, keyboard and outside press work, it sits above the list
//  B  no tag lists above the blog list or the moments timeline (tags stay on the cards); a tag filter from a moment is named by a chip that clears it
//  C  the card / list switch: the marker slides to the other button, the list is replaced with a direction, the box glides between the two heights (nothing jumps)
//  D  a live search on the blog: the list is replaced, the box glides, the line under the title folds away, the clear button comes and goes
//  E  months: the marker slides, the calendar and the timeline are replaced from the side the month is on
//  F  the search overlay: opens with a motion, its rows fold open, closing runs a motion before the dialog closes, a quick reopen is not lost, reduced motion is instant
//  G  the picture viewer: fades in, moves to the next picture, fades out before it is gone
//  H  reduced motion: the list is replaced at once and the box is never pinned
import { open, main, settled, sleep } from './common.mjs'

let bad = 0
const check = (name, ok, detail = '') => { if (!ok) bad += 1; console.log(`${ok ? '✓' : '✗'} ${name}${detail ? `: ${detail}` : ''}`) }

/** Probes that run inside the page every frame (the page's CSP forbids building functions from strings, so they are defined here once). */
const install = (page) => page.evaluate(() => {
  const op = (el) => (el ? Number(getComputedStyle(el).opacity) : -1)
  window.__probes = {
    dd: () => ({ op: op(document.querySelector('.dd__list')), n: document.querySelectorAll('.dd__list [role="option"]').length }),
    dlg: () => { const d = document.querySelector('dialog.dialog--search'); return { op: op(d), open: !!d?.open, shown: !!d?.classList.contains('is-shown'), rows: [...document.querySelectorAll('.searchbox__list .fold')].map((f) => Math.round(f.getBoundingClientRect().height)) } },
    lb: () => ({ op: op(document.querySelector('.lightbox')), on: !!document.querySelector('.lightbox') }),
    doc: () => {
      const sec = document.querySelector('.list-section, .moments-main')
      const swap = sec?.querySelector('.swap')
      return { h: document.documentElement.scrollHeight, box: swap ? Math.round(swap.getBoundingClientRect().height) : -1, pinned: swap ? swap.style.height : '', panes: swap ? swap.querySelectorAll(':scope > .swap__pane').length : 0, cls: swap ? [...swap.querySelectorAll(':scope > .swap__pane')].map((p) => p.className).join(' | ') : '', dir: swap?.dataset.dir }
    },
    cal: () => { const s = document.querySelector('.minical .swap'); return { label: document.querySelector('.minical__head')?.textContent, dir: s?.dataset.dir, panes: s?.querySelectorAll(':scope > .swap__pane').length ?? 0, cls: s ? [...s.querySelectorAll(':scope > .swap__pane')].map((p) => p.className).join(' | ') : '', bar: document.querySelector('.month-nav ol')?.style.getPropertyValue('--y') } },
  }
  window.__rec = (name, ms) => new Promise((resolve) => {
    const out = []
    const t0 = performance.now()
    const tick = () => {
      out.push({ t: Math.round(performance.now() - t0), ...window.__probes[name]() })
      if (performance.now() - t0 < ms) requestAnimationFrame(tick); else resolve(out)
    }
    requestAnimationFrame(tick)
  })
})
const rec = (page, name, ms) => page.evaluate(([n, m]) => window.__rec(n, m), [name, ms])
const maxStep = (xs, key) => xs.slice(1).reduce((m, r, i) => Math.max(m, Math.abs(r[key] - xs[i][key])), 0)

const view = async (browser, target, width, opts, body) => {
  const { ctx, page, errors } = await open(browser, target, width, { settle: 500, ...opts })
  await install(page)
  await settled(page)
  try { await body(page) } finally { check(`no console errors (${target})`, errors.length === 0, errors.slice(0, 2).join(' | ')); await ctx.close() }
}

await main(async (browser) => {
  /* ---------- A: the drop-down ---------- */
  await view(browser, 'blog', 1280, {}, async (page) => {
    check('A  no native <select> in the filter bar', (await page.locator('.filters select').count()) === 0)
    const btn = page.locator('.dd__btn')
    check('A  a combobox button that says what is chosen', (await btn.getAttribute('role')) === 'combobox' && (await btn.innerText()).includes('最新优先'))
    const p = rec(page, 'dd', 700)
    await btn.click()
    const frames = await p
    check('A  the list is closed first, then opens with a motion', frames[0].op === -1 || frames[0].op < 0.6, `first opacity ${frames[0].op}`)
    const last = frames[frames.length - 1]
    check('A  ... and ends fully shown with every choice', last.op >= 0.99 && last.n >= 2, `opacity ${last.op}, ${last.n} choices`)
    check('A  expanded is announced, and the chosen one is marked', (await btn.getAttribute('aria-expanded')) === 'true' && (await page.locator('.dd__list [aria-selected="true"]').innerText()).includes('最新优先'))
    const onTop = await page.evaluate(() => { const r = document.querySelector('.dd__list').getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height - 12); return !!el?.closest('.dd__list') })
    check('A  the list is drawn above the cards below it', onTop)
    await page.keyboard.press('Escape')
    await page.waitForSelector('.dd__list', { state: 'detached', timeout: 1500 }).catch(() => undefined)
    check('A  Escape closes it', (await page.locator('.dd__list').count()) === 0 && (await btn.getAttribute('aria-expanded')) === 'false')
    await page.keyboard.press('ArrowDown')
    await page.waitForSelector('.dd__list')
    await page.mouse.click(40, 300)
    await page.waitForSelector('.dd__list', { state: 'detached', timeout: 1500 }).catch(() => undefined)
    check('A  a press somewhere else closes it', (await page.locator('.dd__list').count()) === 0)
    await btn.focus()
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Enter')
    await page.waitForFunction(() => location.search.includes('sort=old'), null, { timeout: 4000 }).catch(() => undefined)
    check('A  the keyboard chooses: ↓ ↓ Enter', page.url().includes('sort=old'), page.url())
    check('A  the button shows the new choice', (await btn.innerText()).includes('最早优先'))
  })

  /* ---------- B: tags are not listed above the lists ---------- */
  await view(browser, 'blog', 1280, {}, async (page) => {
    check('B  the blog has no row of tag chips above the list', (await page.locator('.filters__tags').count()) === 0 && !(await page.locator('.filters').innerText()).includes('标签'))
    check('B  ... and the cards still carry their tags', (await page.locator('main .card .tag, main .card a.tag').count()) >= 1)
  })
  await view(browser, 'moments', 1280, {}, async (page) => {
    check('B  moments has no list of tags or moods above the timeline', (await page.locator('.moment-filters').count()) === 0 && (await page.locator('.moments-main').innerText()).split('\n').slice(0, 6).every((l) => !/^(标签|心情)$/.test(l.trim())))
    check('B  ... no filter chip while nothing is filtered', (await page.locator('.moment-now').count()) === 0)
    check('B  ... and each moment still carries its tags', (await page.locator('article.moment a.tag').count()) >= 1)
  })
  await view(browser, '/moments?tag=css', 1280, {}, async (page) => {
    check('B  a tag filter is named by a chip', (await page.locator('.moment-now').innerText()).includes('CSS'))
  })

  /* ---------- C: card / list switch ---------- */
  await view(browser, 'blog', 1280, {}, async (page) => {
    const thumb = () => page.evaluate(() => { const t = document.querySelector('.viewtoggle'); const m = getComputedStyle(t.querySelector('.slide')).translate; const b = t.querySelector('[aria-pressed="true"]'); return { x: parseFloat(m) || 0, want: b.offsetLeft, state: t.dataset.slide } })
    const a = await thumb()
    check('C  the marker sits under the pressed button, and the switch is "set"', Math.abs(a.x - a.want) < 1 && a.state === 'set', JSON.stringify(a))
    const before = await page.evaluate(() => document.documentElement.scrollHeight)
    const p = rec(page, 'doc', 1500)
    await page.click('.viewtoggle button[aria-label="列表"]')
    const frames = await p
    await sleep(100)
    const b = await thumb()
    check('C  the marker slid to the list button', Math.abs(b.x - b.want) < 1 && b.x > a.x + 20, `${a.x} -> ${b.x}`)
    check('C  the list is replaced from the right (cards -> rows)', frames.some((f) => f.dir === 'next' && f.cls.includes('swap-leave-active')) && (await page.locator('.postrow').count()) >= 5)
    check('C  old and new are never both in the page for long (out, then in)', frames.every((f) => f.panes <= 2) && frames.filter((f) => f.panes === 2).length <= 4, `${frames.filter((f) => f.panes === 2).length} frames`)
    check('C  the box was pinned while the old list left, and is free again', frames.some((f) => f.pinned) && frames[frames.length - 1].pinned === '', `last "${frames[frames.length - 1].pinned}"`)
    const step = maxStep(frames, 'h')
    const total = Math.abs(frames[frames.length - 1].h - before)
    check('C  the page height glides (no single-frame jump of more than 60% of the change)', total < 40 || step <= Math.max(60, total * 0.6), `change ${total}px, biggest step ${step}px`)
    await page.click('.viewtoggle button[aria-label="卡片"]')
    await page.waitForFunction(() => document.querySelectorAll('.grid-6').length === 1 && document.querySelectorAll('.swap__pane').length === 1, null, { timeout: 3000 }).catch(() => undefined)
    check('C  and back to cards, from the left', (await page.locator('.grid-6').count()) === 1 && (await page.locator('.list-section .swap').getAttribute('data-dir')) === 'prev')
  })

  /* ---------- D: live search on the blog ---------- */
  await view(browser, 'blog', 1280, {}, async (page) => {
    check('D  the line under the title is there', (await page.locator('.page-head .fold').count()) === 1)
    const before = await page.evaluate(() => document.documentElement.scrollHeight)
    const p = rec(page, 'doc', 2200)
    await page.focus('.searchfield input')
    await page.keyboard.type('备份', { delay: 90 })
    check('D  the clear button pops in once there is text', await page.waitForSelector('.searchfield__clear', { timeout: 1000 }).then(() => true, () => false))
    const frames = await p
    const now = await page.evaluate(() => ({ cards: document.querySelectorAll('main .card').length, line: document.querySelectorAll('.page-head .fold').length, h: document.documentElement.scrollHeight }))
    check('D  the list narrowed and the line under the title folded away', now.cards >= 1 && now.cards < 9 && now.line === 0, JSON.stringify(now))
    const step = maxStep(frames, 'h')
    const total = Math.abs(now.h - before)
    check('D  the page height glides while the results change', total < 60 || step <= Math.max(80, total * 0.6), `change ${total}px, biggest step ${step}px`)
    check('D  the box is free again afterwards', frames[frames.length - 1].pinned === '')
    await page.click('.searchfield__clear')
    await page.waitForFunction(() => document.querySelector('.searchfield input').value === '', null, { timeout: 1000 }).catch(() => undefined)
    await page.waitForFunction(() => !location.search.includes('q='), null, { timeout: 4000 }).catch(() => undefined)
    check('D  the clear button empties the field and the search', !page.url().includes('q=') && (await page.inputValue('.searchfield input')) === '')
    await page.waitForSelector('.searchfield__clear', { state: 'detached', timeout: 1500 }).catch(() => undefined)
    check('D  ... and goes away', (await page.locator('.searchfield__clear').count()) === 0)
  })

  /* ---------- E: months ---------- */
  await view(browser, 'moments', 1280, {}, async (page) => {
    const bar = () => page.evaluate(() => ({ y: parseFloat(document.querySelector('.month-nav ol').style.getPropertyValue('--y')) || 0, want: document.querySelector('.month-nav a.is-active').offsetTop, tr: parseFloat(getComputedStyle(document.querySelector('.month-nav .slide')).translate.split(' ')[1]) || 0 }))
    const a = await bar()
    check('E  the marker sits at "all"', Math.abs(a.y - a.want) < 1, JSON.stringify(a))
    const label = await page.evaluate(() => document.querySelector('.minical__head')?.textContent)
    const p = rec(page, 'cal', 1400)
    await page.click('.month-nav a:has-text("9 月")')
    const frames = await p
    await sleep(500)
    const b = await bar()
    check('E  the marker slid down to the month', Math.abs(b.y - b.want) < 1 && b.y > a.y + 10, `${a.y} -> ${b.y}`)
    check('E  the calendar is replaced from the left (an older month)', frames.some((f) => f.dir === 'prev' && f.cls.includes('swap-leave-active')) && frames.some((f) => f.cls.includes('swap-enter-active')))
    const now = await page.evaluate(() => document.querySelector('.minical__head')?.textContent)
    check('E  the calendar shows the new month', now !== label && now.includes('9 月'), `${label} -> ${now}`)
    check('E  the timeline shows that month only', (await page.locator('article.moment').count()) >= 1 && (await page.locator('.month-sep').count()) === 1 && (await page.locator('.month-sep').innerText()).includes('9 月'))
    await page.click('.month-nav a:has-text("全部")')
    await page.waitForFunction(() => document.querySelectorAll('.month-sep').length >= 1 && document.querySelectorAll('.swap__pane').length === 2, null, { timeout: 4000 }).catch(() => undefined)
    await sleep(600)
    check('E  back to all months: from the right, and the marker is back', (await page.locator('.minical .swap').getAttribute('data-dir')) === 'next' && Math.abs((await bar()).y - a.y) < 1)
  })

  /* ---------- F: the search overlay ---------- */
  await view(browser, 'blog', 1280, {}, async (page) => {
    let p = rec(page, 'dlg', 900)
    await page.keyboard.press('/')
    let frames = await p
    check('F  opens with a motion: starts see-through, ends fully shown', frames.some((f) => f.open && f.op < 0.6) && frames[frames.length - 1].op >= 0.99 && frames[frames.length - 1].shown, `first open frame ${frames.find((f) => f.open)?.op}, last ${frames[frames.length - 1].op}`)
    check('F  its first rows are folding open (not all at their height at the start)', frames.slice(0, 12).some((f) => f.rows.length && f.rows.some((h) => h < 20)), JSON.stringify(frames.slice(0, 8).map((f) => f.rows.length)))
    p = rec(page, 'dlg', 1500)
    await page.keyboard.type('SQLite', { delay: 60 })
    frames = await p
    const rows = await page.locator('.searchbox__item').count()
    check('F  results come in as rows', rows >= 1, String(rows))
    check('F  the list grows by folding (some frame had a row part-way open)', frames.some((f) => f.rows.some((h) => h > 2 && h < 24)) || frames.some((f) => f.rows.length > 3))
    check('F  arrow keys still select (aria-selected moves)', await (async () => { const a = await page.locator('[aria-selected="true"]').getAttribute('id'); await page.keyboard.press('ArrowDown'); const b = await page.locator('[aria-selected="true"]').getAttribute('id'); return !!a && !!b && a !== b })())
    p = rec(page, 'dlg', 800)
    await page.keyboard.press('Escape')
    frames = await p
    check('F  closing runs a motion first: the dialog is still open while it fades', frames.some((f) => f.open && f.op < 0.95 && !f.shown), `${frames.filter((f) => f.open && !f.shown).length} frames`)
    check('F  ... and is gone afterwards', !frames[frames.length - 1].open && (await page.locator('dialog[open]').count()) === 0)
    // a quick reopen while it is closing is not lost
    await page.keyboard.press('/')
    await page.waitForSelector('dialog[open]')
    await page.keyboard.press('Escape')
    await sleep(60)
    await page.evaluate(() => document.activeElement?.blur())      // (the focus is still in the field while it fades: "/" would be typed into it)
    await page.keyboard.press('/')
    await sleep(900)
    const again = await page.evaluate(() => { const d = document.querySelector('dialog.dialog--search'); return { open: d.open, shown: d.classList.contains('is-shown'), op: Number(getComputedStyle(d).opacity) } })
    check('F  closing and opening again quickly leaves it open and fully shown', again.open && again.shown && again.op >= 0.99, JSON.stringify(again))
    await page.keyboard.press('Escape')
    await page.waitForSelector('dialog[open]', { state: 'detached', timeout: 2000 }).catch(() => undefined)
    check('F  focus is not left inside the closed dialog', await page.evaluate(() => !document.activeElement?.closest('dialog')))
  })
  await view(browser, 'blog', 1280, { reduced: true }, async (page) => {
    await page.keyboard.press('/')
    await page.waitForSelector('dialog[open]')
    const op = await page.evaluate(() => Number(getComputedStyle(document.querySelector('dialog.dialog--search')).opacity))
    check('F  reduced motion: opens fully shown at once', op >= 0.99, String(op))
    await page.keyboard.press('Escape')
    await sleep(120)
    check('F  reduced motion: closes at once', (await page.locator('dialog[open]').count()) === 0)
  })

  /* ---------- G: the picture viewer ---------- */
  await view(browser, 'moments', 1280, {}, async (page) => {
    let p = rec(page, 'lb', 700)
    await page.locator('.moment__imgs button').first().click()
    let frames = await p
    check('G  the viewer fades in', frames.some((f) => f.on && f.op < 0.7) && frames[frames.length - 1].op >= 0.99, `first ${frames.find((f) => f.on)?.op}`)
    const many = (await page.locator('.lightbox__nav--next').count()) === 1
    if (many) {
      const c1 = await page.locator('.lightbox__bar span').innerText()
      await page.keyboard.press('ArrowRight')
      await sleep(700)
      check('G  the next picture comes in from the right', (await page.locator('.lightbox__bar span').innerText()) !== c1 && (await page.locator('.lightbox').getAttribute('data-dir')) === 'next')
    }
    p = rec(page, 'lb', 700)
    await page.keyboard.press('Escape')
    frames = await p
    check('G  it fades out before it is gone', frames.some((f) => f.on && f.op < 0.95) && !frames[frames.length - 1].on, `${frames.filter((f) => f.on).length} frames`)
    check('G  focus goes back to the picture', await page.evaluate(() => document.activeElement?.tagName === 'IMG' || document.activeElement?.closest('.moment__imgs') !== null))
  })

  /* ---------- H: reduced motion ---------- */
  await view(browser, 'blog', 1280, { reduced: true }, async (page) => {
    const p = rec(page, 'doc', 600)
    await page.click('.viewtoggle button[aria-label="列表"]')
    const frames = await p
    check('H  the list is replaced at once (never two lists, never a pinned box)', frames.every((f) => f.panes <= 1 && f.pinned === '') && (await page.locator('.postrow').count()) >= 5, `panes ${Math.max(...frames.map((f) => f.panes))}`)
    const lingering = frames.filter((f) => /swap-(enter|leave)/.test(f.cls)).length
    check('H  ... and the transition classes are gone within a few frames', lingering <= 12, `${lingering} frames`)
  })

  return bad
})
