// Motion coverage: every piece of content on every public page has its own scroll motion (enter, scroll-linked, leave): text, cards, pictures,
// buttons, lists, the footer. An element counts as covered when it is, or sits inside, a [data-fx] element. Decorative or hidden parts do not count.
import { PAGES, open, main } from './common.mjs'

const CANDIDATES = 'h1,h2,h3,h4,h5,h6,p,li,blockquote,figure,pre,table,img,svg.doodle,.card,.postrow,.moment,.btn,.tag,.badge,.stamp,.kicker,.empty,.note,.bubble,.polaroid,.toc,form,input,select,details,dl,.pager,.tabs,.month-chips,.filters,.crumbs,.meta'

const scan = (sel) => {
  const out = []
  const roots = [...document.querySelectorAll('main, footer.site-footer')]
  const seen = new Set()
  roots.forEach((root) => root.querySelectorAll(sel).forEach((el) => {
    if (seen.has(el)) return
    seen.add(el)
    const cs = getComputedStyle(el)
    if (cs.display === 'none' || cs.visibility === 'hidden') return
    const r = el.getBoundingClientRect()
    if (r.width < 6 || r.height < 6) return
    if (el.closest('[aria-hidden="true"], .sr-only, dialog, .lightbox, .sheet, .searchbox, [inert]')) return
    if (el.closest('[data-fx]')) return
    if (cs.position === 'fixed' || el.closest('.toc-fab')) return                     // floating controls stay put; they do not scroll with the page
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) || /^(IMG|INPUT|SELECT|HR)$/.test(el.tagName) || el.matches('svg.doodle')
    if (!own) return                                                                                 // a container whose text lives in its (covered) children
    if (el.matches('svg') && !el.classList.contains('doodle')) return
    out.push(el)
  }))
  // only the outermost uncovered blocks: a paragraph inside an uncovered card is the card's problem
  const set = new Set(out)
  const top = out.filter((el) => { for (let p = el.parentElement; p; p = p.parentElement) if (set.has(p)) return false; return true })
  const label = (e) => `${e.tagName.toLowerCase()}${e.id ? `#${e.id}` : ''}${e.className && typeof e.className === 'string' ? `.${e.className.trim().split(/\s+/).slice(0, 2).join('.')}` : ''}`
  const text = (e) => (e.innerText || e.getAttribute('aria-label') || e.getAttribute('alt') || '').trim().replace(/\s+/g, ' ').slice(0, 24)
  return top.map((e) => `${label(e)} “${text(e)}” in ${label(e.parentElement)}`)
}

await main(async (browser) => {
  let bad = 0
  const which = process.env.PAGE ? process.env.PAGE.split(',') : PAGES.map((p) => p.name)
  for (const entry of PAGES.filter((p) => which.includes(p.name))) {
    for (const w of [1280, 390]) {
      const { ctx, page } = await open(browser, entry, w, { settle: 900 })
      const miss = await page.evaluate(scan, CANDIDATES)
      if (miss.length) bad += 1
      console.log(`${miss.length ? '✗' : '✓'} ${entry.name}@${w}: ${miss.length ? `${miss.length} block(s) without motion` : 'every block has motion'}`)
      miss.slice(0, Number(process.env.SHOW || 12)).forEach((m) => console.log(`     ${m}`))
      await ctx.close()
    }
  }
  console.log(bad ? `\nCOVERAGE: ${bad} page view(s) with uncovered content` : '\nCOVERAGE: every page is fully covered')
  return bad
})
