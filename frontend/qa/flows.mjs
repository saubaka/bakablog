// End-to-end flows: what a visitor does, on a real browser against the running server.
// Every step is independent (a failed step does not stop the next), and the browser console must stay clean.
import { BASE, BROWSER, byName, launch, open, main, settled, sleep } from './common.mjs'

const results = []
let ctxCount = 0
const record = (name, ok, detail = '') => { results.push({ name, ok, detail }); console.log(`${ok ? '✓' : '✗'} ${name}${ok ? '' : ` — ${detail}`}`) }
async function flow(browser, name, target, width, fn, opts = {}) {
  if (process.env.ONLY && !name.includes(process.env.ONLY)) return
  ctxCount += 1
  const { ctx, page, errors } = await open(browser, target, width, { settle: 500, ...opts })
  const requests = []
  page.on('request', (r) => { if (r.url().startsWith(BASE)) requests.push(`${r.method()} ${r.url().slice(BASE.length)}`) })
  try {
    const check = async (label, cond, detail = '') => { if (!(await cond)) throw new Error(`${label}${detail ? ` (${detail})` : ''}`) }
    await fn({ page, check, requests, ctx })
    const ignorable = (e) => /status of 404/.test(e)
    const bad = errors.filter((e) => !ignorable(e))
    if (bad.length) throw new Error(`console: ${bad.slice(0, 2).join(' | ')}`)
    record(name, true)
  } catch (e) {
    const at = (String(e.stack || '').match(/flows\.mjs:(\d+)/) || [])[1]
    record(name, false, `${String(e.message || e).split('\n')[0]}${at ? ` [line ${at}]` : ''}`)
  } finally {
    await ctx.close()
  }
}
const y = (page) => page.evaluate(() => Math.round(scrollY))
const path = (page) => page.evaluate(() => location.pathname + location.search + location.hash)
const waitPath = (page, re, ms = 5000) => page.waitForFunction((src) => new RegExp(src).test(location.pathname + location.search), re.source, { timeout: ms })

await main(async (browser) => {
  const desktop = 1280
  const phone = 390

  await flow(browser, 'nav: home → blog (title, h1 focus, current item, scroll to top)', 'home', desktop, async ({ page, check }) => {
    await page.evaluate(() => window.scrollTo(0, 500))
    await sleep(150)
    await page.click('.nav a[href="/blog"]')
    await waitPath(page, /^\/blog$/)
    await page.waitForFunction(() => document.activeElement?.tagName === 'H1', null, { timeout: 4000 })
    await check('document title', (await page.title()).startsWith('博客'), await page.title())
    await check('current item', page.evaluate(() => document.querySelector('.nav [aria-current="page"]')?.textContent.trim() === '博客'))
    await sleep(400)
    await check('scrolled to top', (await y(page)) < 5, `y=${await y(page)}`)
  })

  // every way into a page starts at its top with the page head playing its own entrance, and the scroll-linked motion works right away
  for (const [label, from, link, re] of [
    ['menu → blog', 'home', '.nav a[href="/blog"]', /^\/blog$/],
    ['menu → moments', 'blog', '.nav a[href="/moments"]', /^\/moments$/],
    ['menu → archive', 'moments', '.nav a[href="/archive"]', /^\/archive$/],
    ['menu → home', 'blog', '.nav a[href="/"]', /^\/$/],
    ['card → post', 'blog', 'a.card:nth-of-type(4)', /^\/blog\/[^/]+$/],
    ['moment time → moment page', 'moments', '.moment time a, a.moment__link', /^\/moments\/\d+$/],
  ]) {
    await flow(browser, `enter: ${label}, from a scrolled page (page opens at its top, head plays its entrance, scroll motion responds)`, from, desktop, async ({ page, check }) => {
      const target = page.locator(link).first()
      if (!(await target.count())) return                       // the demo data has no such link: nothing to check
      await target.scrollIntoViewIfNeeded()
      await page.evaluate(() => window.scrollBy(0, 120))
      await sleep(900)
      const startY = await y(page)
      await page.evaluate(() => {
        window.__seen = { y: null, intro: 0, partial: 0 }
        const before = document.querySelector('main h1')              // the old page's heading does not count
        const t0 = performance.now()
        const tick = () => {
          const h = document.querySelector('main h1')
          if (h && h !== before && window.FX.read(h)) {
            const s = window.FX.read(h)
            if (window.__seen.y === null) window.__seen.y = Math.round(window.scrollY)
            if (s.intro) window.__seen.intro += 1
            if (s.in > 0.05 && s.in < 0.95) window.__seen.partial += 1
          }
          if (performance.now() - t0 < 2200) requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      })
      await target.click()
      await waitPath(page, re)
      await sleep(2300)
      const seen = await page.evaluate(() => window.__seen)
      await check('the page was already at its top when its head was placed', seen.y !== null && seen.y <= 8, `y=${seen.y} (started at ${startY})`)
      await check('the head played its entrance (intro clock ran and the heading was seen mid-way)', seen.intro > 3 && seen.partial > 3, JSON.stringify(seen))
      // and the scroll-linked motion works on this page: something below the fold is hidden until scrolled to, then arrives
      const below = await page.evaluate(() => {
        const vh = innerHeight
        const el = [...document.querySelectorAll('main [data-fx]')].find((e) => e.getBoundingClientRect().top > vh * 1.2 && window.FX.read(e) && !['drift', 'spine'].includes(window.FX.read(e).type))
        if (!el) return null
        el.setAttribute('data-qa-below', '1')
        return { state: window.FX.read(el).state }
      })
      if (below) {
        await check('an element far below is waiting (not yet shown)', below.state === 'pre', below.state)
        await page.evaluate(() => document.querySelector('[data-qa-below]').scrollIntoView({ block: 'center', behavior: 'instant' }))
        await settled(page)
        // (an element near the end of a short page cannot be scrolled to the middle of the screen, so "arrived" means: it reached where its position says it belongs, and that is well in)
        const after = await page.evaluate(() => { const s = window.FX.read(document.querySelector('[data-qa-below]')); return { state: s.state, lin: s.lin, tin: s.tin } })
        await check('it arrives once scrolled to', Math.abs(after.lin - after.tin) < 0.01 && after.tin > 0.5, JSON.stringify(after))
      }
    })
  }

  // every way into a page: not only its head enters, everything on the first screen does, one after another from the top; and leaving has its own exit
  for (const [label, from, link, re] of [
    ['menu → blog', 'home', '.nav a[href="/blog"]', /^\/blog$/],
    ['menu → moments', 'blog', '.nav a[href="/moments"]', /^\/moments$/],
    ['menu → archive', 'moments', '.nav a[href="/archive"]', /^\/archive$/],
  ]) {
    await flow(browser, `whole page enters: ${label}`, from, desktop, async ({ page, check }) => {
      await page.evaluate(() => window.scrollBy(0, 200))
      await sleep(700)
      await page.evaluate(() => {
        window.__old = document.querySelector('main h1')
        window.__log = { leaving: 0, leavingOf: 0, rows: [] }
        const t0 = performance.now()
        const tick = () => {
          const main = document.querySelector('main')
          const items = [...main.querySelectorAll('[data-fx]')].filter((e) => e.closest('.page-leave-active'))
          if (items.length) { window.__log.leaving = Math.max(window.__log.leaving, items.filter((e) => Number(getComputedStyle(e).opacity) < 0.5).length); window.__log.leavingOf = Math.max(window.__log.leavingOf, items.length) }
          const h = main.querySelector('h1')
          if (h && h !== window.__old) {
            const vh = innerHeight
            const els = [...main.querySelectorAll('[data-fx]')].filter((e) => { const r = e.getBoundingClientRect(); return r.top < vh * 0.9 && r.bottom > 0 && window.FX.read(e) && !['drift', 'spine'].includes(window.FX.read(e).type) })
            const travelling = (e) => { const r = window.FX.read(e); return !!r.intro || Math.abs(r.lin - r.tin) > 0.01 || Math.abs(r.lout - r.tout) > 0.01 }
            window.__log.rows.push([Math.round(performance.now() - t0), els.length, els.filter(travelling).length, els.filter((e) => !travelling(e) && window.FX.read(e).tin > 0).length])
          }
          if (performance.now() - t0 < 3000) requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      })
      await page.click(link)
      await waitPath(page, re)
      await sleep(3100)
      const log = await page.evaluate(() => window.__log)
      const rows = log.rows
      const peak = Math.max(...rows.map((r) => r[2]))
      const first = rows.find((r) => r[3] > 0)
      const total = rows.length ? rows[rows.length - 1][1] : 0                            // columns: time, items on the first screen, still travelling, arrived
      await check('the page that is left animates its content out', log.leavingOf > 3 && log.leaving > log.leavingOf * 0.5, JSON.stringify({ leaving: log.leaving, of: log.leavingOf }))
      await check('several things are entering at the same moment (a wave, not one element)', peak >= 4, `peak ${peak}`)
      await check('they do not all arrive at once (the first finishes while others are still on their way)', rows.some((r) => r[3] > 0 && r[2] > 0), 'no frame with both finished and in-progress items')
      await check('everything on the first screen ends where the scroll position says it belongs', rows[rows.length - 1][2] === 0 && total >= 5, `${rows[rows.length - 1]} of ${total}`)
      await check('nothing was visible at full strength before its turn (the first frame starts empty)', rows[0][3] <= 1, JSON.stringify(rows[0]))
    })
  }

  // the foot of every page is only the legal line: no brand block, no "browse" column, no "subscribe and contact" column
  for (const [name, width] of [['home', desktop], ['blog', phone], ['post', desktop], ['moments', phone], ['archive', desktop], ['page', phone], ['404', desktop], ['search', phone]]) {
    await flow(browser, `footer is only the legal line: ${name}@${width}`, byName(name), width, async ({ page, check }) => {
      const foot = await page.evaluate(() => { const f = document.querySelector('footer.site-footer'); return f ? { text: f.innerText.trim().replace(/\s+/g, ' '), links: [...f.querySelectorAll('a')].map((a) => a.textContent.trim()), headings: f.querySelectorAll('h1,h2,h3,ul,li').length } : null })
      await check('the footer exists', !!foot)
      await check('no columns, lists or headings', foot.headings === 0, JSON.stringify(foot))
      await check('none of the removed texts', !/订阅与联系|浏览|文章 RSS|动态 RSS|不是笨蛋|写代码，记日常/.test(foot.text), foot.text)
      await check('the copyright line is there', /©|版权|sau_baka/.test(foot.text), foot.text)
    })
  }

  await flow(browser, 'post: open from list, back restores scroll, no second fetch for the list', 'blog', desktop, async ({ page, check, requests }) => {
    const first = page.locator('a.card').nth(4)
    await first.scrollIntoViewIfNeeded()
    await settled(page)                                         // the card is still gliding in (it takes at least 0.4 s); WebKit's click scrolls a moving element by itself
    await sleep(100)
    const title = (await first.locator('.card__title').innerText()).trim().replace(/\s+/g, ' ')
    await first.click({ trial: true })
    const before = await y(page)
    await first.click()
    await waitPath(page, /^\/blog\/[^/]+$/)
    await page.waitForSelector('article .prose')
    await check('h1 = card title', (await page.locator('main h1').first().innerText()).replace(/\s+/g, ' ').includes(title.slice(0, 6)))
    await check('document title', (await page.title()).includes(title.slice(0, 6)), await page.title())
    await page.goBack()
    await waitPath(page, /^\/blog$/)
    await sleep(700)
    const after = await y(page)
    await check('scroll restored', Math.abs(after - before) < 60, `${before} → ${after}`)
    await check('back did not reload the page', !requests.includes('GET /blog'), requests.join(','))
  })

  await flow(browser, 'post: code copy button, TOC jump without reload, lightbox, footnote anchor', byName('post'), desktop, async ({ page, check, requests, ctx }) => {
    await ctx.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => undefined)   // Chromium only; WebKit asks differently
    const copy = page.locator('.code__copy').first()
    await copy.scrollIntoViewIfNeeded()
    await copy.click()
    await sleep(200)
    const said = await copy.innerText()
    await check('copy gives feedback', said.includes('已复制') || said.includes('复制失败'), said)
    if (BROWSER === 'chromium') {
      const text = await page.evaluate(() => navigator.clipboard.readText())
      await check('the code is on the clipboard', text.length > 5 && text === (await page.locator('.code pre').first().innerText()), text.slice(0, 30))
    }
    await sleep(1900)
    await check('copy label restored', (await copy.innerText()).trim() === '复制', await copy.innerText())
    const n = requests.length
    const link = page.locator('.toc a').nth(2)
    const id = (await link.getAttribute('href')).slice(1)
    await link.click()
    await sleep(1100)
    const top = await page.evaluate((i) => document.getElementById(i).getBoundingClientRect().top, id)
    await check('heading near the top after the TOC click', top > 60 && top < 200, `top=${top}`)
    await check('URL has the hash', decodeURIComponent(await path(page)).endsWith(`#${decodeURIComponent(id)}`), await path(page))
    await check('no data request for a hash change', !requests.slice(n).some((r) => r.includes('/api/')), requests.slice(n).join(','))
    const active = await page.evaluate(() => document.querySelector('.toc a.is-active')?.getAttribute('href'))
    await check('TOC marks the heading', active === `#${id}`, active)
    // lightbox on the gallery
    const img = page.locator('.gallery__item img').first()
    await img.scrollIntoViewIfNeeded()
    await img.click()
    await page.waitForSelector('.lightbox')
    const c1 = await page.locator('.lightbox__bar span').innerText()
    await page.keyboard.press('ArrowRight')
    const c2 = await page.locator('.lightbox__bar span').innerText()
    await check('lightbox moves to the next picture', c1 !== c2, `${c1} → ${c2}`)
    await page.keyboard.press('Escape')
    await check('lightbox closes', (await page.locator('.lightbox').count()) === 0)
    await check('focus returns to the picture', page.evaluate(() => document.activeElement?.tagName === 'IMG'))
  })

  await flow(browser, 'search overlay: "/" opens, results, arrows + Enter open a result, Esc closes, typing "/" in a field does not open it', 'blog', desktop, async ({ page, check }) => {
    await page.keyboard.press('/')
    await page.waitForSelector('dialog[open]')
    await check('input focused', page.evaluate(() => document.activeElement?.tagName === 'INPUT'))
    await page.keyboard.type('SQLite')
    await page.waitForSelector('.searchbox__item')
    const n = await page.locator('.searchbox__item').count()
    await check('has results', n >= 1, String(n))
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Enter')
    await page.waitForFunction(() => !document.querySelector('dialog[open]'))
    await page.waitForFunction(() => location.pathname !== '/blog')
    await page.waitForFunction(() => !document.documentElement.classList.contains('boot') && document.querySelector('main h1'))
    await sleep(500)
    await page.keyboard.press('Control+k')
    await page.waitForSelector('dialog[open]')
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('dialog[open]'))
    // not while typing
    await page.goto(`${BASE}/blog`)
    await page.waitForSelector('.searchfield input')
    await page.focus('.searchfield input')
    await page.keyboard.type('a/b')
    await check('"/" typed into a field does not open the overlay', (await page.locator('dialog[open]').count()) === 0)
  })

  await flow(browser, 'search page: results grouped, tabs, new query', { path: '/search?q=SQLite' }, desktop, async ({ page, check }) => {
    await check('has a post result', (await page.locator('.search-page__results .postrow').count()) >= 1)
    await page.fill('.search-page__field input', '汤圆')
    await page.keyboard.press('Enter')
    await page.waitForFunction(() => decodeURIComponent(location.search).includes('汤圆'))
    await page.waitForFunction(() => document.title.includes('汤圆'), null, { timeout: 4000 }).catch(() => undefined)
    await check('title follows the query', (await page.title()).includes('汤圆'), await page.title())
    await page.fill('.search-page__field input', 'zzzzzzzz')
    await page.keyboard.press('Enter')
    await page.waitForSelector('.empty strong:has-text("没有找到")')
    await check('empty state', (await page.locator('.empty strong').first().innerText()).includes('没有找到'))
  })

  await flow(browser, 'blog controls: category tab, tag chip, sort, view toggle, pager, live search field', 'blog', desktop, async ({ page, check }) => {
    await page.click('.tabs a.tab >> nth=1')
    await waitPath(page, /^\/category\//)
    await check('category page keeps the controls', (await page.locator('.filters').count()) === 1)
    await check('tab is current', (await page.locator('.tabs [aria-current]').count()) === 1)
    await page.click('.tabs a.tab >> nth=0')
    await waitPath(page, /^\/blog$/)
    await page.selectOption('select.select', 'old')
    await waitPath(page, /sort=old/)
    const oldest = await page.locator('main h2.card__title').first().innerText()
    await page.selectOption('select.select', 'new')
    await waitPath(page, /^\/blog$/)
    const newest = await page.locator('main h2.card__title').first().innerText()
    await check('sort changes the order', oldest !== newest)
    await page.click('.viewtoggle button[aria-label="列表"]')
    await page.waitForSelector('.postrow')
    await check('list view', (await page.locator('.postrow').count()) >= 5)
    await page.click('.viewtoggle button[aria-label="卡片"]')
    await page.click('.pager a:has-text("2")')
    await waitPath(page, /page=2/)
    await check('page 2 has posts', (await page.locator('main .card, main .postrow').count()) >= 1)
    await page.goto(`${BASE}/blog`)
    await page.waitForSelector('.searchfield input')
    await page.fill('.searchfield input', '备份')
    await waitPath(page, /q=/)
    await sleep(500)
    await check('live search narrows the list', (await page.locator('main .card').count()) >= 1 && (await page.locator('main .card').count()) < 9)
  })

  await flow(browser, 'moments: tag filter, month filter, picture viewer, link card opens in a new tab safely', 'moments', desktop, async ({ page, check }) => {
    await page.click('.moment-filters a:has-text("CSS")')
    await waitPath(page, /tag=css/)
    await sleep(400)
    const filtered = await page.locator('article.moment').count()
    await check('filtered list is shorter', filtered >= 1 && filtered < 5, String(filtered))
    await page.click('.month-nav a:has-text("全部")')
    await sleep(300)
    await check('"all months" keeps the tag filter', decodeURIComponent(await path(page)) === '/moments?tag=css')
    await page.click('.moment-filters a:has-text("全部")')
    await waitPath(page, /^\/moments$/)
    await sleep(300)
    await page.locator('.moment__imgs button').first().click()
    await page.waitForSelector('.lightbox')
    await page.keyboard.press('Escape')
    const card = page.locator('a.linkcard').first()
    await check('link card is external and safe', (await card.getAttribute('target')) === '_blank' && (await card.getAttribute('rel')) === 'noopener noreferrer')
    await page.locator('.moment__time').first().click()
    await waitPath(page, /^\/moments\/\d+$/)
    await page.waitForSelector('.moment-single article.moment')
  })

  await flow(browser, '404: real 404 status, own page, suggestions, search button works', { path: '/blog/not-a-post' }, desktop, async ({ page, check }) => {
    await check('h1', (await page.locator('main h1').innerText()).length > 0)
    await check('suggestions', (await page.locator('.related .card').count()) >= 1)
    await page.click('.lost__actions button')
    await page.waitForSelector('dialog[open]')
    const res = await page.request.get(`${BASE}/blog/not-a-post`, { headers: { Accept: 'text/html' } })
    await check('HTTP status 404', res.status() === 404, String(res.status()))
  })

  await flow(browser, 'phone: bottom bar, drawer with motion switch, TOC drawer, search button', byName('post'), phone, async ({ page, check }) => {
    await check('tab bar visible', page.locator('.tabbar').isVisible())
    await check('side menu hidden', !(await page.locator('.thread--side').isVisible()))
    await page.click('.tabbar button:has-text("更多")')
    await page.waitForSelector('.sheet.is-open')
    await page.click('.motion-switch button:has-text("关闭")')
    await check('motion off applied', page.evaluate(() => document.documentElement.dataset.fxMode === 'off' && document.documentElement.classList.contains('fx-off')))
    await check('choice remembered', page.evaluate(() => localStorage.getItem('bb:motion') === 'off'))
    await page.keyboard.press('Escape')
    await page.waitForFunction(() => !document.querySelector('.sheet.is-open'))
    await check('focus back on the button', page.evaluate(() => document.activeElement?.textContent?.includes('更多')))
    await page.evaluate(() => localStorage.removeItem('bb:motion'))
    await page.click('.toc-fab')
    await page.waitForSelector('.sheet.is-open')
    await page.locator('.sheet.is-open ol a').nth(1).click()
    await page.waitForFunction(() => !document.querySelector('.sheet.is-open'))
    await sleep(900)
    await check('TOC drawer scrolled to the heading', (await y(page)) > 300, `y=${await y(page)}`)
    await page.click('.tabbar button:has-text("搜索")')
    await page.waitForSelector('dialog[open]')
  })

  await flow(browser, 'visit beacon: one POST /api/track per page view', 'home', desktop, async ({ page, check, requests }) => {
    const before = requests.filter((r) => r === 'POST /api/track').length
    await page.click('.nav a[href="/blog"]')
    await waitPath(page, /^\/blog$/)
    await sleep(400)
    await page.click('.nav a[href="/moments"]')
    await waitPath(page, /^\/moments$/)
    await sleep(400)
    const n = requests.filter((r) => r === 'POST /api/track').length - before
    await check('two navigations, two beacons', n === 2, String(n))
    await page.click('.nav a[href="/moments"]')   // the page you are on: nothing happens
    await sleep(300)
    await check('no beacon for a repeated click', requests.filter((r) => r === 'POST /api/track').length - before === 2)
  })

  await flow(browser, 'appearance: theme / code theme / decor come from the site settings before first paint', 'home', desktop, async ({ page, check }) => {
    const r = await page.evaluate(() => ({ code: document.documentElement.dataset.codeTheme, lang: document.documentElement.lang, noTape: document.documentElement.classList.contains('no-tape') }))
    await check('code theme set', r.code === 'frost', r.code)
    await check('language from settings', r.lang === 'zh-CN', r.lang)
    await check('decor on by default', r.noTape === false)
  })

  await flow(browser, 'internal links in article text navigate inside the app; links to the server do not', byName('post'), desktop, async ({ page, check, requests }) => {
    await page.evaluate(() => {
      const p = document.querySelector('.prose p')
      p.insertAdjacentHTML('beforeend', ' <a id="t-in" href="/archive">归档</a>')
    })
    await page.click('#t-in')
    await waitPath(page, /^\/archive$/)
    await check('no full page load for an internal link', !requests.includes('GET /archive'), requests.join(','))
  })

  console.log(`\nFLOWS (${BROWSER}): ${results.filter((r) => r.ok).length}/${results.length} passed`)
  return results.filter((r) => !r.ok).length
})
