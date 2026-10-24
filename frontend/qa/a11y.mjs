// axe-core (WCAG 2.1 A + AA) on every page at phone and desktop width, with motion off so the scroll fade cannot hide text from the contrast rule.
// Serious and critical findings fail the run; moderate and minor ones are listed.
import AxeBuilder from '@axe-core/playwright'
import { PAGES, open, main } from './common.mjs'

await main(async (browser) => {
  let bad = 0
  const minor = new Map()
  for (const entry of PAGES) {
    for (const w of [390, 1280]) {
      const { ctx, page } = await open(browser, entry, w, { query: 'motion=off', settle: 400 })
      const res = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']).analyze()
      for (const v of res.violations) {
        const line = `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length}× e.g. ${v.nodes[0]?.target?.join(' ')}`
        if (v.impact === 'serious' || v.impact === 'critical') { bad += 1; console.log(`✗ ${entry.name}@${w}: ${line}`) }
        else minor.set(`${v.id} ${v.nodes[0]?.target?.join(' ')}`, `${entry.name}@${w}: ${line}`)
      }
      await ctx.close()
    }
  }
  if (minor.size) { console.log(`moderate / minor findings (${minor.size}):`); for (const l of minor.values()) console.log(`  · ${l}`) }
  console.log(bad ? `A11Y: ${bad} serious or critical finding(s)` : 'A11Y: no serious or critical finding on any page')
  return bad
})
