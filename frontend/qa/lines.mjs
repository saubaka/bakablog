// One line colour, flat cards, no square "cards", no grey halos. Floating layers may have a (blue) shadow.
import { PAGES, launch, open, main } from './common.mjs'
import { scanLines } from './scans.mjs'

const FLOATING = '.sheet, .toast, dialog, .tabbar, .lightbox, .scrim, .searchbox, .dd__list'

await main(async (browser) => {
  let bad = 0
  const all = { shadow: new Map(), border: new Map(), square: new Map() }
  for (const entry of PAGES) {
    for (const w of [1280, 390]) {
      const { ctx, page } = await open(browser, entry, w, { query: 'motion=off', settle: 300 })
      // open the floating layers too: search overlay (and the phone drawer) are part of what a visitor sees
      for (const state of ['page', 'search']) {
        if (state === 'search') { await page.keyboard.press('/'); await page.waitForTimeout(250) }
        const r = await page.evaluate(scanLines, FLOATING)
        for (const k of Object.keys(all)) for (const line of r[k]) { const m = all[k].get(line) || new Set(); m.add(`${entry.name}@${w}`); all[k].set(line, m) }
      }
      await ctx.close()
    }
  }
  for (const [k, title] of [['shadow', 'drop shadow on a non-floating element'], ['border', 'border colour that is not --line / --rose-line'], ['square', 'square "card"']]) {
    console.log(`${all[k].size ? '✗' : '✓'} ${title}: ${all[k].size}`)
    for (const [line, where] of all[k]) { bad += 1; console.log(`    ${line}  [${[...where].slice(0, 3).join(', ')}]`) }
  }
  return bad
})
