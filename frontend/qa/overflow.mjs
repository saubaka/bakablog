// No horizontal overflow at any width, and no console errors or failed requests, on every page.
import { PAGES, WIDTHS, launch, open, main } from './common.mjs'

await main(async (browser) => {
  let bad = 0
  for (const entry of PAGES) {
    for (const w of WIDTHS) {
      const { ctx, page, errors: all } = await open(browser, entry, w, { query: 'motion=off', settle: 300 })
      // the 404 page is a real 404 response: the browser's own "Failed to load resource" line about it is expected
      const errors = entry.name === '404' ? all.filter((e) => !/status of 404/.test(e)) : all
      const r = await page.evaluate(() => {
        const de = document.documentElement
        const over = de.scrollWidth - de.clientWidth
        const wide = [...document.querySelectorAll('body *')].filter((e) => {
          const b = e.getBoundingClientRect()
          return b.width > 0 && b.right > de.clientWidth + 1 && getComputedStyle(e).position !== 'fixed' && !e.closest('.table-wrap, .tabs, .month-chips, .searchbox__list, .sheet, pre, .tabbar, .lightbox, .sprite')
        }).slice(0, 3).map((e) => `${e.tagName}.${String(e.className).split(' ')[0]} ${Math.round(e.getBoundingClientRect().right)}`)
        return { over, wide }
      })
      if (r.over > 0 || errors.length) { bad += 1; console.log(`✗ ${entry.name}@${w}: overflow ${r.over}px ${r.wide.join(' | ')} ${errors.slice(0, 3).join(' | ')}`) }
      await ctx.close()
    }
  }
  console.log(bad ? `${bad} page/width combinations have problems` : `OVERFLOW: all ${PAGES.length} pages x ${WIDTHS.length} widths clean (no overflow, no console errors)`)
  return bad
})
