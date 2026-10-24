// The admin on every page: no horizontal overflow at six widths, no console error / warning / CSP violation / failed request, and axe-core (WCAG 2.1 A + AA)
// at phone and desktop width. Runs against the separate QA instance (see qa/adminlib.mjs).
import AxeBuilder from '@axe-core/playwright'
import { ADMIN_PAGES, launch, openAdmin } from './adminlib.mjs'
import { WIDTHS } from './common.mjs'

const pages = ADMIN_PAGES.filter(([name]) => !process.env.ONLY_PAGE || process.env.ONLY_PAGE.split(',').includes(name))
const widths = WIDTHS.filter(w => !process.env.ONLY_WIDTH || String(w) === process.env.ONLY_WIDTH)
if (!pages.length || !widths.length) throw new Error('no matching admin page / width')
const browser = await launch()
async function bounded(promise, label) {
  let timer
  try {
    return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${label}: exceeded 60 seconds`)), 60_000) })])
  } finally { clearTimeout(timer) }
}
let bad = 0
const minor = new Map()
try {
  for (const [name, path] of pages) {
    for (const w of widths) {
      if (process.env.QA_PROGRESS) console.log(`checking ${name}@${w}`)
      const { ctx, page, errors } = await openAdmin(browser, path, w, { settle: 350, reduced: true })
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      if (over > 0) {
        const culprit = await page.evaluate(() => [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1).slice(0, 3).map((e) => `${e.tagName.toLowerCase()}.${String(e.className).slice(0, 40)}`))
        console.log(`✗ ${name}@${w}: overflows by ${over}px (${culprit.join(', ')})`); bad += 1
      }
      if (errors.length) { console.log(`✗ ${name}@${w}: ${errors.slice(0, 2).join(' | ')}`); bad += 1 }
      if (w === 390 || w === 1280) {
        const res = await bounded(new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']).analyze(), `axe ${name}@${w}`)
        for (const v of res.violations) {
          const line = `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length}× e.g. ${v.nodes[0]?.target?.join(' ')}`
          if (v.impact === 'serious' || v.impact === 'critical') { bad += 1; console.log(`✗ ${name}@${w}: ${line}`) }
          else minor.set(`${v.id} ${v.nodes[0]?.target?.join(' ')}`, `${name}@${w}: ${line}`)
        }
      }
      await ctx.close()
    }
  }
} finally { await browser.close() }
if (minor.size) { console.log(`moderate / minor findings (${minor.size}):`); for (const l of minor.values()) console.log(`  · ${l}`) }
console.log(bad ? `ADMIN PAGES: ${bad} problem(s)` : `ADMIN PAGES: ${pages.length} pages x ${widths.length} widths clean (no overflow, no console error), axe: no serious or critical finding`)
process.exit(bad ? 1 : 0)
