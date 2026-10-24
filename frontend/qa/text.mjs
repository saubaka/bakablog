// Title word grouping: words that were split into spans must still read as one line of text.
// - no .ph / .fx-w span may be an item of a flex or grid container (that pulls the words apart),
// - two neighbouring word spans that sit on the same line and are joined only by <wbr> must touch.
import { PAGES, open, main } from './common.mjs'

await main(async (browser) => {
  let bad = 0
  let checked = 0
  for (const entry of PAGES) {
    for (const w of [390, 768, 1280]) {
      for (const query of ['motion=off', 'motion=full']) {
        const { ctx, page } = await open(browser, entry, w, { query })
        const res = await page.evaluate(() => {
          const out = []; let n = 0
          document.querySelectorAll('.ph, .fx-w').forEach((el) => {
            n += 1
            const d = getComputedStyle(el.parentElement).display
            if (/flex|grid/.test(d)) out.push(`flex/grid item: "${el.textContent}" in <${el.parentElement.tagName.toLowerCase()} class="${el.parentElement.className}">`)
            const nx = el.nextSibling && el.nextSibling.tagName === 'WBR' ? el.nextSibling.nextSibling : null
            if (nx && nx.nodeType === 1 && (nx.classList.contains('ph') || nx.classList.contains('fx-w'))) {
              const a = el.getBoundingClientRect(); const b = nx.getBoundingClientRect()
              if (Math.abs(a.top - b.top) < 3 && b.left - a.right > 2) out.push(`gap ${(b.left - a.right).toFixed(1)}px between "${el.textContent}" and "${nx.textContent}"`)
            }
          })
          return { out, n }
        })
        checked += res.n
        if (res.out.length) { bad += res.out.length; console.log(`✗ ${entry.name}@${w} ${query}:`); res.out.slice(0, 6).forEach((l) => console.log(`   ${l}`)) }
        await ctx.close()
      }
    }
  }
  console.log(bad ? `TEXT AUDIT: ${bad} problem(s)` : `TEXT AUDIT: all clean (${checked} word spans checked)`)
  return bad
})
