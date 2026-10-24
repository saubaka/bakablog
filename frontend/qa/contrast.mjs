// Rendered text contrast on every page, for every theme preset and every code theme.
// Text under 24px (18.66px bold) needs 4.5:1, bigger text 3:1.
import { PAGES, launch, open, main } from './common.mjs'
import { scanContrast } from './scans.mjs'

const THEMES = ['default', 'sky', 'sakura', 'fog']
const CODE_THEMES = ['frost', 'blossom', 'fog']

await main(async (browser) => {
  let failures = 0
  const runs = [...THEMES.map((theme) => ({ label: `theme ${theme}`, theme, code: 'frost', pages: PAGES })), ...CODE_THEMES.filter((c) => c !== 'frost').map((code) => ({ label: `code theme ${code}`, theme: 'default', code, pages: PAGES.filter((p) => p.name === 'post') }))]
  for (const run of runs) {
    const agg = new Map(); let total = 0
    for (const entry of run.pages) {
      const { ctx, page } = await open(browser, entry, 1280, { query: 'motion=off', settle: 200 })
      await page.evaluate(({ th, code }) => {
        const d = document.documentElement
        if (th === 'default') d.removeAttribute('data-theme'); else d.setAttribute('data-theme', th)
        d.setAttribute('data-code-theme', code)
      }, { th: run.theme, code: run.code })
      await page.waitForTimeout(120)
      const r = await page.evaluate(scanContrast); total += r.n
      r.bad.forEach(([k, v]) => { const a = agg.get(k) || { c: 0, ex: v.ex, pages: new Set() }; a.c += v.c; a.pages.add(entry.name); agg.set(k, a) })
      await ctx.close()
    }
    console.log(`${agg.size ? '✗' : '✓'} ${run.label}: ${total} text elements, ${agg.size} failing colour pairs`)
    for (const [k, v] of agg) { failures += 1; console.log(`    ${v.c}× ${k}  e.g. ${v.ex}  [${[...v.pages].slice(0, 4).join(', ')}]`) }
  }
  return failures
})
